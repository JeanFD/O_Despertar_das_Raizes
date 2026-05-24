"""
Cliente UDP do servidor dedicado (arquitetura 2.0).

Diferente de network/client.py (legado P2P/LAN), este cliente:
- usa shared/protocol.py (msgpack binário, schema versionado);
- aceita endereço servidor:porta vindo do matchmaker HTTP;
- expõe send_input(bitmask, tick) para o gameplay enviar input em 30 Hz;
- entrega snapshots e eventos críticos por callback.
"""
from __future__ import annotations
import socket
import threading
import time
import queue
from typing import Optional, Tuple

from shared.protocol import (
    PROTOCOL_VERSION, encode, decode,
    MSG_HELLO, MSG_HELLO_ACK, MSG_HELLO_NACK,
    MSG_INPUT, MSG_SNAPSHOT, MSG_EVENT, MSG_EVENT_ACK,
    MSG_PING, MSG_PONG, MSG_DISCONNECT,
)

CONNECT_TIMEOUT = 8.0
HEARTBEAT_INTERVAL = 1.0
SESSION_TIMEOUT = 8.0
BUFFER = 4096


class OnlineClient:
    """Cliente UDP da nova arquitetura.

    Estado interno:
        connected:  True após HELLO_ACK
        my_id:      "p1" ou "p2" (atribuído pelo servidor)
        room_mode:  string do modo
        rtt:        round-trip estimado (s)

    Threads:
        recv: drena socket, responde PING, enfileira snapshots/eventos
        heartbeat: manda PING a cada HEARTBEAT_INTERVAL
    """

    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("", 0))  # porta efêmera
        self.sock.settimeout(0.005)

        self._remote: Optional[Tuple[str, int]] = None
        self._running = True
        self.connected = False
        self.my_id: Optional[str] = None
        self.room_mode: Optional[str] = None
        self.rtt: float = 0.0
        self.last_recv = time.monotonic()
        self.last_disconnect_reason: Optional[str] = None
        self._ack_event_seqs: set = set()

        self._snap_q: queue.Queue = queue.Queue()
        self._event_q: queue.Queue = queue.Queue()

        self._recv_t = threading.Thread(target=self._recv_loop, daemon=True)
        self._recv_t.start()
        self._hb_t = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self._hb_t.start()

    # ── API ───────────────────────────────────────────────────────────────

    def connect(self, host: str, port: int, nick: str, token: str = "",
                timeout: float = CONNECT_TIMEOUT) -> bool:
        """Handshake bloqueante. Retorna True se conectou."""
        self._remote = (host, port)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self._raw_send(MSG_HELLO, v=PROTOCOL_VERSION, nick=nick, tok=token)
            t0 = time.monotonic()
            while time.monotonic() - t0 < 0.2:
                try:
                    raw, _ = self.sock.recvfrom(BUFFER)
                except socket.timeout:
                    continue
                except OSError:
                    return False
                msg = decode(raw)
                t = msg.get("t")
                if t == MSG_HELLO_ACK:
                    self.connected = True
                    self.my_id = msg.get("id")
                    self.room_mode = msg.get("mode")
                    self.last_recv = time.monotonic()
                    return True
                if t == MSG_HELLO_NACK:
                    self.last_disconnect_reason = msg.get("reason", "unknown")
                    return False
        return False

    def send_input(self, bitmask: int, tick: int, ack_snap_tick: int = 0):
        """Envia input. Chamado pelo gameplay tipicamente a 30 Hz."""
        self._raw_send(MSG_INPUT, tk=tick, m=bitmask, ak=ack_snap_tick)

    def poll_snapshots(self) -> list:
        """Drena snapshots recebidos. Cada item é (recv_time, payload_dict)."""
        out = []
        try:
            while True:
                out.append(self._snap_q.get_nowait())
        except queue.Empty:
            pass
        return out

    def poll_events(self) -> list:
        """Drena eventos críticos confirmados."""
        out = []
        try:
            while True:
                out.append(self._event_q.get_nowait())
        except queue.Empty:
            pass
        return out

    def alive(self) -> bool:
        if not self.connected:
            return False
        return (time.monotonic() - self.last_recv) < SESSION_TIMEOUT

    def close(self):
        if self.connected and self._remote:
            self._raw_send(MSG_DISCONNECT)
        self._running = False
        try:
            self.sock.close()
        except OSError:
            pass

    # ── Threads ───────────────────────────────────────────────────────────

    def _recv_loop(self):
        while self._running:
            try:
                raw, _ = self.sock.recvfrom(BUFFER)
            except socket.timeout:
                continue
            except OSError:
                break
            msg = decode(raw)
            if not msg:
                continue
            self.last_recv = time.monotonic()
            t = msg.get("t")
            if t == MSG_SNAPSHOT:
                self._snap_q.put((self.last_recv, msg))
            elif t == MSG_PONG:
                ts0 = msg.get("ts0", 0.0)
                if ts0:
                    self.rtt = max(0.0, time.monotonic() - ts0)
            elif t == MSG_EVENT:
                seq = msg.get("seq")
                self._raw_send(MSG_EVENT_ACK, seq=seq)
                if seq not in self._ack_event_seqs:
                    self._ack_event_seqs.add(seq)
                    self._event_q.put(msg)
            elif t == MSG_DISCONNECT:
                self.connected = False
                self.last_disconnect_reason = msg.get("reason", "server_bye")

    def _heartbeat_loop(self):
        while self._running:
            time.sleep(HEARTBEAT_INTERVAL)
            if not self._running or not self._remote:
                continue
            self._raw_send(MSG_PING, id=0, ts=time.monotonic())

    def _raw_send(self, msg_type, **payload):
        if not self._remote:
            return
        try:
            self.sock.sendto(encode(msg_type, **payload), self._remote)
        except OSError:
            pass
