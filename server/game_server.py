"""
Servidor dedicado headless.

Roda uma única sala. UDP assíncrono + tickrate fixo (60 Hz lógico) +
snapshot rate (30 Hz por padrão).

Arquitetura:

    asyncio loop
    ├── DatagramEndpoint (recebe pacotes, enfileira por player)
    ├── _tick_loop()   — roda Simulation a 60 Hz
    ├── _send_snapshot — a cada 2 ticks, manda snapshot pra todos
    └── _ack_pending   — retransmite eventos críticos sem ack

Não importa pygame.display/font/mixer. Importa apenas pygame.math/Rect
indiretamente via PhysicsBody/Hitbox (estruturas de dado, OK em servidor).
"""
from __future__ import annotations
import asyncio
import hmac
import logging
import time
from typing import Dict, Optional, Tuple

from shared.protocol import (
    PROTOCOL_VERSION, encode, decode, codec_name,
    MSG_HELLO, MSG_HELLO_ACK, MSG_HELLO_NACK,
    MSG_INPUT, MSG_SNAPSHOT, MSG_EVENT, MSG_EVENT_ACK,
    MSG_PING, MSG_PONG, MSG_DISCONNECT,
    bitmask_to_input_dict,
)
from shared.snapshot import make_delta
from shared.lag_comp import LagCompHistory

log = logging.getLogger("server.game")

TICK_HZ = 60
SNAP_DIVISOR = 2          # snapshot a cada 2 ticks = 30 Hz
FIXED_DT = 1.0 / TICK_HZ
EVENT_RETRY = 0.1
EVENT_MAX_RETRIES = 8
CLIENT_TIMEOUT = 8.0


class ClientSession:
    """Estado de um cliente conectado."""

    __slots__ = ("addr", "net_id", "nick", "last_recv", "last_input_tick",
                 "last_ack_snap_tick", "last_snap_sent", "ping_rtt")

    def __init__(self, addr, net_id: str, nick: str):
        self.addr = addr
        self.net_id = net_id
        self.nick = nick
        self.last_recv = time.monotonic()
        self.last_input_tick = 0
        self.last_ack_snap_tick = 0
        # snapshot enviado para este cliente — base para delta
        self.last_snap_sent: Optional[dict] = None
        self.ping_rtt = 0.0


class _Protocol(asyncio.DatagramProtocol):
    """Wrapper asyncio → callbacks do GameServer."""

    def __init__(self, server: "GameServer"):
        self.server = server
        self.transport = None

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data: bytes, addr):
        self.server.on_packet(data, addr)

    def error_received(self, exc):
        log.debug("socket error: %s", exc)


class GameServer:
    """Loop principal do servidor dedicado de uma sala."""

    def __init__(self, port: int, mode: str = "vs",
                 max_players: int = 2,
                 token_secret: str = "",
                 idle_timeout: float = 60.0):
        self.port = port
        self.mode = mode
        self.max_players = max_players
        self.token_secret = token_secret.encode() if token_secret else b""
        self.idle_timeout = idle_timeout

        self.protocol: Optional[_Protocol] = None
        self.transport = None
        self.clients: Dict[Tuple[str, int], ClientSession] = {}
        self.inputs_latest: Dict[str, dict] = {}   # net_id → último input_dict
        self.simulation = None    # criada após primeiro player chegar
        self.lag_history = LagCompHistory(window_ticks=TICK_HZ)
        self._tick = 0
        self._stop = False
        self._idle_since: Optional[float] = None
        self._pending_events: Dict[int, dict] = {}  # seq → {addr, payload, sent, retries}
        self._event_seq = 0

    # ── Lifecycle ─────────────────────────────────────────────────────────

    async def run(self):
        loop = asyncio.get_running_loop()
        self.transport, self.protocol = await loop.create_datagram_endpoint(
            lambda: _Protocol(self),
            local_addr=("0.0.0.0", self.port),
        )
        log.info("escutando UDP 0.0.0.0:%d codec=%s", self.port, codec_name())

        next_tick = time.monotonic()
        try:
            while not self._stop:
                next_tick += FIXED_DT
                self._do_tick()
                self._check_idle()
                wait = next_tick - time.monotonic()
                if wait > 0:
                    await asyncio.sleep(wait)
                else:
                    # atrasado — reseta o relógio para não acumular
                    if wait < -FIXED_DT * 3:
                        log.warning("tick atrasado %.1f ms — resetando", -wait * 1000)
                        next_tick = time.monotonic()
        finally:
            self._broadcast_disconnect()
            if self.transport:
                self.transport.close()

    def request_stop(self):
        self._stop = True

    # ── Tick ──────────────────────────────────────────────────────────────

    def _do_tick(self):
        if self.simulation is None:
            return
        self._tick += 1

        # roda física + combate + match
        self.simulation.tick(self.inputs_latest, FIXED_DT)

        # grava histórico p/ lag comp
        snap = self.simulation.snapshot()
        for net_id, st in snap.get("pl", {}).items():
            self.lag_history.record(net_id, self._tick, st)

        # snapshot rate (a cada SNAP_DIVISOR ticks)
        if self._tick % SNAP_DIVISOR == 0:
            self._send_snapshots(snap)

        self._retry_pending_events()
        self._reap_stale_clients()

    def _send_snapshots(self, snap: dict):
        """Manda snapshot delta para cada cliente."""
        for client in list(self.clients.values()):
            # ack que ESTE cliente confirmou — usamos como base do delta
            base = client.last_snap_sent
            delta = make_delta(base, snap)
            payload = {
                "tk": self._tick,
                "bt": (base.get("t") if base else 0),
                "ack": client.last_input_tick,
                "d": delta,
            }
            client.last_snap_sent = snap
            self._send(MSG_SNAPSHOT, client.addr, **payload)

    def _check_idle(self):
        if not self.clients:
            if self._idle_since is None:
                self._idle_since = time.monotonic()
            elif time.monotonic() - self._idle_since > self.idle_timeout:
                log.info("idle %.0fs — encerrando", self.idle_timeout)
                self._stop = True
        else:
            self._idle_since = None

    # ── Packet handling ───────────────────────────────────────────────────

    def on_packet(self, raw: bytes, addr):
        msg = decode(raw)
        if not msg:
            return
        t = msg.get("t")

        if t == MSG_HELLO:
            self._handle_hello(msg, addr)
            return

        client = self.clients.get(addr)
        if client is None:
            return  # ignora qualquer mensagem antes do HELLO
        client.last_recv = time.monotonic()

        if t == MSG_INPUT:
            self._handle_input(client, msg)
        elif t == MSG_PING:
            self._send(MSG_PONG, addr, id=msg.get("id", 0),
                       ts0=msg.get("ts", 0.0))
        elif t == MSG_PONG:
            ts0 = msg.get("ts0", 0.0)
            if ts0:
                client.ping_rtt = max(0.0, time.monotonic() - ts0)
        elif t == MSG_EVENT_ACK:
            seq = msg.get("seq")
            self._pending_events.pop(seq, None)
        elif t == MSG_DISCONNECT:
            log.info("[%s] disconnect", client.net_id)
            self._drop_client(addr)

    def _handle_hello(self, msg, addr):
        if msg.get("v") != PROTOCOL_VERSION:
            self._send(MSG_HELLO_NACK, addr, reason="version",
                       expected=PROTOCOL_VERSION)
            return
        if len(self.clients) >= self.max_players:
            self._send(MSG_HELLO_NACK, addr, reason="full")
            return
        nick = str(msg.get("nick", "anon"))[:20]
        token = msg.get("tok", "")
        if self.token_secret and not self._verify_token(nick, token):
            self._send(MSG_HELLO_NACK, addr, reason="bad_token")
            return

        # Atribui net_id sequencial: primeiro = p1, segundo = p2
        net_id = f"p{len(self.clients) + 1}"
        client = ClientSession(addr, net_id, nick)
        self.clients[addr] = client
        log.info("[%s/%s] hello de %s:%d", net_id, nick, addr[0], addr[1])

        self._ensure_simulation()
        self._spawn_player_for(client)

        self._send(MSG_HELLO_ACK, addr,
                   v=PROTOCOL_VERSION,
                   id=net_id,
                   mode=self.mode,
                   tick=self._tick)

        if len(self.clients) == self.max_players:
            log.info("sala cheia — partida pode começar")

    def _verify_token(self, nick: str, token: str) -> bool:
        """HMAC simples — token = hex(hmac_sha256(secret, nick))."""
        if not token or not self.token_secret:
            return False
        try:
            expected = hmac.new(
                self.token_secret, nick.encode(), "sha256"
            ).hexdigest()
            return hmac.compare_digest(expected, token)
        except Exception:
            return False

    def _handle_input(self, client: ClientSession, msg: dict):
        tk = int(msg.get("tk", 0))
        if tk <= client.last_input_tick:
            return  # input antigo (UDP fora de ordem)
        client.last_input_tick = tk

        ack_snap = int(msg.get("ak", 0))
        if ack_snap > client.last_ack_snap_tick:
            client.last_ack_snap_tick = ack_snap

        mask = int(msg.get("m", 0))
        inp = bitmask_to_input_dict(mask)
        self.inputs_latest[client.net_id] = inp

    # ── Simulação e spawn ─────────────────────────────────────────────────

    def _ensure_simulation(self):
        if self.simulation is not None:
            return
        # Tilemap de fallback (servidor não tem TMX). Para versus, arena
        # fixa em settings — mantemos uma arena retangular simples.
        from world.tilemap import Tilemap
        from engine.simulation import Simulation

        tm = Tilemap(32)
        # chão da arena
        for gx in range(80):
            tm.add_tile(gx, 18)
        # paredes laterais — invisíveis ao player mas evitam tunneling
        for gy in range(0, 19):
            tm.add_tile(0, gy)
            tm.add_tile(79, gy)
        world_h = 19 * 32

        self.simulation = Simulation(tm, world_h)

        # listeners ligados ao envio de eventos confiáveis
        self.simulation.on_died = self._on_entity_died

    def _spawn_player_for(self, client: ClientSession):
        from entities.player import Player
        # Spawns simples — futuro: ler do TMX da arena.
        spawns = {"p1": (200.0, 500.0), "p2": (1800.0, 500.0)}
        sx, sy = spawns.get(client.net_id, (300.0, 500.0))
        # Player precisa de um game-like com event_bus + assets.
        # Servidor injeta stubs mínimos.
        stub = _ServerGameStub()
        player = Player(stub, sx, sy, team_id=client.net_id)
        for ab in player.abilities:
            player.abilities[ab] = True
        self.simulation.add_player(client.net_id, player)
        log.info("spawn %s @ (%.0f, %.0f)", client.net_id, sx, sy)

    def _on_entity_died(self, entity):
        # Achar net_id desse player
        for net_id, p in self.simulation.players.items():
            if p is entity:
                self.send_event_to_all("died", id=net_id)
                # respawn automático em modo versus depois de delay curto
                # — futuro: integrar com VersusMatch
                return

    # ── Envio ─────────────────────────────────────────────────────────────

    def _send(self, msg_type, addr, **payload):
        if not self.transport:
            return
        try:
            self.transport.sendto(encode(msg_type, **payload), addr)
        except OSError:
            pass

    def send_event_to_all(self, ev_type: str, **data):
        """Evento crítico com retransmissão até ACK de cada cliente."""
        seq = self._event_seq
        self._event_seq += 1
        for client in self.clients.values():
            payload = {"seq": seq, "ev": ev_type, **data}
            self._send(MSG_EVENT, client.addr, **payload)
            self._pending_events[(seq, client.addr)] = {
                "payload": payload, "addr": client.addr,
                "sent": time.monotonic(), "retries": 0,
            }

    def _retry_pending_events(self):
        now = time.monotonic()
        for key, info in list(self._pending_events.items()):
            if now - info["sent"] > EVENT_RETRY:
                if info["retries"] >= EVENT_MAX_RETRIES:
                    del self._pending_events[key]
                    continue
                self._send(MSG_EVENT, info["addr"], **info["payload"])
                info["sent"] = now
                info["retries"] += 1

    def _broadcast_disconnect(self):
        for client in list(self.clients.values()):
            self._send(MSG_DISCONNECT, client.addr, reason="shutdown")

    def _reap_stale_clients(self):
        now = time.monotonic()
        for addr, client in list(self.clients.items()):
            if now - client.last_recv > CLIENT_TIMEOUT:
                log.info("[%s] timeout", client.net_id)
                self._drop_client(addr)

    def _drop_client(self, addr):
        client = self.clients.pop(addr, None)
        if client and self.simulation:
            p = self.simulation.players.pop(client.net_id, None)
            if p:
                p.alive = False
        self.inputs_latest.pop(client.net_id, None) if client else None


# ── Stubs para Player rodar headless ─────────────────────────────────────
# Player.__init__ chama game.assets.image(...) e game.events.subscribe(...).
# Aqui implementamos versões mínimas — sem disco, sem render.

class _DummyAnimation:
    """Substitui AnimationController quando o Player precisa anexar um
    `anim` sem ter sheet de verdade. Mantém só o nome do estado atual."""

    def __init__(self, *a, **kw):
        self._current = "idle"

    def add(self, *a, **kw):  pass
    def play(self, name, **kw):
        self._current = name
    def update(self, dt):  pass
    def draw(self, *a, **kw):  pass


class _DummyAssets:
    def image(self, path):
        return None
    def sound(self, path):
        return None


class _DummyEvents:
    def subscribe(self, *a, **kw):  pass
    def unsubscribe(self, *a, **kw):  pass
    def emit(self, *a, **kw):  pass


class _ServerGameStub:
    """Game-like para o Player viver no servidor headless."""

    def __init__(self):
        self.assets = _DummyAssets()
        self.events = _DummyEvents()
        # state machine não existe no servidor — Player nunca consulta isso
        self.states = None


# Monkey patch defensivo: se algum entity tentar instanciar AnimationController
# no servidor, fornecemos a versão dummy. Isso permite que o Player.__init__
# (que faz self.add(AnimationController, ...)) funcione sem display.
def _patch_animation_for_headless():
    try:
        from components import animation
        original = animation.AnimationController

        class _Wrapper(_DummyAnimation):
            def __init__(self, entity, sheet, fw, fh, fps=12):
                _DummyAnimation.__init__(self)
                self.entity = entity
                self._real = original if sheet is not None else None
                # Se sheet é None (assets dummy), fica em modo dummy total
        animation.AnimationController = _Wrapper
    except ImportError:
        pass


_patch_animation_for_headless()
