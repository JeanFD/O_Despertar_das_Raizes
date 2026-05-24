"""
Lobby HTTP minimalista.

Endpoints:
    GET  /api/health                    healthcheck
    GET  /api/rooms                     listar salas abertas
    POST /api/rooms                     criar sala
                 body: {name, mode, nick, max_players?}
                 resp: {room_id, server_host, server_port, token, nick}
    POST /api/rooms/{id}/join           pegar token de entrada
                 body: {nick}
                 resp: {server_host, server_port, token, nick}

Spawn de game_server por sala: subprocess.Popen com argumentos. systemd
em produção (Fase 8) substitui isso por units instanciadas.

Sem auth real (qualquer pessoa pode criar/listar). Em produção, colocar
rate limit no nginx + IP allowlist se necessário.
"""
from __future__ import annotations
import hmac
import json
import logging
import os
import secrets
import socketserver
import subprocess
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler
from typing import Dict, Optional

log = logging.getLogger("server.lobby")


class Room:
    __slots__ = ("id", "name", "mode", "max_players", "server_host",
                 "server_port", "created_at", "process", "nicks",
                 "last_seen")

    def __init__(self, room_id, name, mode, max_players,
                 server_host, server_port):
        self.id = room_id
        self.name = name
        self.mode = mode
        self.max_players = max_players
        self.server_host = server_host
        self.server_port = server_port
        self.created_at = time.time()
        self.process: Optional[subprocess.Popen] = None
        self.nicks: list = []
        self.last_seen = time.time()

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "mode": self.mode,
            "players": len(self.nicks),
            "max": self.max_players,
            "created_at": self.created_at,
        }


class LobbyApp:
    def __init__(self, token_secret: str, server_host: str,
                 port_low: int, port_high: int, server_cmd: str = ""):
        self.token_secret = token_secret.encode()
        self.server_host = server_host
        self.port_low = port_low
        self.port_high = port_high
        # comando para spawnar — permite override em dev (ex: "python -m server")
        self.server_cmd = server_cmd or f"{sys.executable} -m server"
        self.rooms: Dict[str, Room] = {}
        self._used_ports: set = set()
        self._lock = threading.Lock()
        self._started_at = time.time()
        # GC thread — remove salas zumbis
        threading.Thread(target=self._gc_loop, daemon=True).start()

    # ── API ────────────────────────────────────────────────────────────────

    def list_rooms(self):
        with self._lock:
            return [
                r.to_dict() for r in self.rooms.values()
                if len(r.nicks) < r.max_players
                and r.process and r.process.poll() is None
            ]

    def create_room(self, name: str, mode: str, nick: str,
                    max_players: int = 2):
        if mode not in ("vs", "coop", "boss"):
            raise ValueError("invalid mode")
        if not (1 <= max_players <= 4):
            raise ValueError("invalid max_players")
        nick = (nick or "anon")[:20]

        with self._lock:
            port = self._alloc_port()
            if port is None:
                raise RuntimeError("no_free_ports")
            room_id = uuid.uuid4().hex[:12]
            room = Room(room_id, name[:30], mode, max_players,
                        self.server_host, port)
            # Spawn game_server como subprocess
            cmd = (self.server_cmd.split() +
                   ["--port", str(port),
                    "--mode", mode,
                    "--max-players", str(max_players),
                    "--token-secret", self.token_secret.decode(),
                    "--idle-timeout", "60"])
            try:
                room.process = subprocess.Popen(cmd)
            except Exception as e:
                self._used_ports.discard(port)
                raise RuntimeError(f"spawn_failed: {e}") from None
            self.rooms[room_id] = room

        # Espera o servidor abrir o socket
        time.sleep(0.4)

        token = self._token_for(nick)
        room.nicks.append(nick)
        return {
            "room_id": room_id,
            "server_host": room.server_host,
            "server_port": room.server_port,
            "token": token,
            "nick": nick,
        }

    def join_room(self, room_id: str, nick: str):
        with self._lock:
            room = self.rooms.get(room_id)
            if not room:
                raise ValueError("room_not_found")
            if room.process and room.process.poll() is not None:
                raise ValueError("room_dead")
            if len(room.nicks) >= room.max_players:
                raise ValueError("room_full")
            nick = (nick or "anon")[:20]
            room.nicks.append(nick)

        token = self._token_for(nick)
        return {
            "server_host": room.server_host,
            "server_port": room.server_port,
            "token": token,
            "nick": nick,
        }

    def health(self):
        with self._lock:
            active = sum(1 for r in self.rooms.values()
                         if r.process and r.process.poll() is None)
        return {
            "ok": True,
            "uptime_s": int(time.time() - self._started_at),
            "rooms_total": len(self.rooms),
            "rooms_active": active,
            "port_range": f"{self.port_low}-{self.port_high}",
        }

    # ── Internos ───────────────────────────────────────────────────────────

    def _token_for(self, nick: str) -> str:
        return hmac.new(self.token_secret, nick.encode(), "sha256").hexdigest()

    def _alloc_port(self) -> Optional[int]:
        for p in range(self.port_low, self.port_high + 1):
            if p not in self._used_ports:
                self._used_ports.add(p)
                return p
        return None

    def _gc_loop(self):
        while True:
            time.sleep(10.0)
            with self._lock:
                dead = []
                for rid, r in self.rooms.items():
                    if r.process and r.process.poll() is not None:
                        dead.append(rid)
                for rid in dead:
                    r = self.rooms.pop(rid)
                    self._used_ports.discard(r.server_port)
                    log.info("gc removeu sala %s (pid encerrado)", rid)


# ── HTTP handler stdlib ──────────────────────────────────────────────────

class _Handler(BaseHTTPRequestHandler):
    app: LobbyApp = None  # type: ignore

    def log_message(self, fmt, *args):
        log.info("%s - %s", self.address_string(), fmt % args)

    def _json(self, status, body: dict):
        raw = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(raw)

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {}

    def do_GET(self):
        if self.path == "/api/health":
            self._json(200, self.app.health())
            return
        if self.path == "/api/rooms":
            self._json(200, {"rooms": self.app.list_rooms()})
            return
        self._json(404, {"error": "not_found"})

    def do_POST(self):
        body = self._read_body()
        if self.path == "/api/rooms":
            try:
                resp = self.app.create_room(
                    name=str(body.get("name", "Sala")),
                    mode=str(body.get("mode", "vs")),
                    nick=str(body.get("nick", "anon")),
                    max_players=int(body.get("max_players", 2)),
                )
                self._json(200, resp)
            except ValueError as e:
                self._json(400, {"error": str(e)})
            except Exception as e:
                self._json(500, {"error": str(e)})
            return
        if self.path.startswith("/api/rooms/") and self.path.endswith("/join"):
            room_id = self.path[len("/api/rooms/"):-len("/join")]
            try:
                resp = self.app.join_room(room_id, nick=str(body.get("nick", "anon")))
                self._json(200, resp)
            except ValueError as e:
                self._json(404, {"error": str(e)})
            except Exception as e:
                self._json(500, {"error": str(e)})
            return
        self._json(404, {"error": "not_found"})

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()


class _ThreadingServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True


def serve(app: LobbyApp, host: str, port: int):
    _Handler.app = app
    server = _ThreadingServer((host, port), _Handler)
    log.info("lobby HTTP escutando em http://%s:%d", host, port)
    log.info("game_server host público=%s ports=%d-%d",
             app.server_host, app.port_low, app.port_high)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log.info("interrupção — encerrando lobby")
    finally:
        server.server_close()
