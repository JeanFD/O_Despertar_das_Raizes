# server/matchmaking.py
# Rode com: python server/matchmaking.py
# API HTTP simples de lobby — uma partida por vez.
import threading
import time
import random
import string
from http.server import BaseHTTPRequestHandler, HTTPServer
import json

_LOBBY_TTL = 120.0   # lobby expira em 2 min sem ninguém entrar

_state_lock = threading.Lock()
_lobby = None   # None | {"code": str, "ts": float, "full": bool}


def _gen_code() -> str:
    chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(random.choices(chars, k=6))


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"[matchmaking] {self.address_string()} — {fmt % args}")

    def _send(self, code: int, body: dict):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path != "/lobbies":
            self._send(404, {"error": "not found"})
            return
        with _state_lock:
            lb = _lobby
            if lb and not lb["full"] and time.time() - lb["ts"] < _LOBBY_TTL:
                self._send(200, {"lobbies": [{"code": lb["code"]}]})
            else:
                self._send(200, {"lobbies": []})

    def do_POST(self):
        global _lobby

        if self.path == "/lobbies":
            with _state_lock:
                # Não abre novo lobby se já há um ativo
                if _lobby and not _lobby["full"] and time.time() - _lobby["ts"] < _LOBBY_TTL:
                    self._send(409, {"error": "servidor ocupado"})
                    return
                code = _gen_code()
                _lobby = {"code": code, "ts": time.time(), "full": False}
            print(f"[matchmaking] Lobby criado: {code}")
            self._send(200, {"code": code})

        elif self.path.startswith("/lobbies/") and self.path.endswith("/join"):
            code = self.path.split("/")[2]
            with _state_lock:
                lb = _lobby
                if not lb or lb["code"] != code:
                    self._send(404, {"error": "lobby não encontrado"})
                    return
                if lb["full"]:
                    self._send(409, {"error": "lobby cheio"})
                    return
                lb["full"] = True
            print(f"[matchmaking] Lobby {code} — segundo jogador entrou.")
            self._send(200, {"ok": True})

        else:
            self._send(404, {"error": "not found"})


def run(port: int = 8080):
    server = HTTPServer(("0.0.0.0", port), _Handler)
    print(f"[matchmaking] HTTP na porta {port}")
    server.serve_forever()


if __name__ == "__main__":
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    run(port)
