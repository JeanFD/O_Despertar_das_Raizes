# network/host.py
import time
from settings import HOST_PORT, NET_TIMEOUT
from network.connection import UDPConnection
from network.protocol import (
    MSG_HELLO, MSG_HELLO_ACK, MSG_INPUT,
    MSG_STATE, MSG_EVENT, MSG_EVENT_ACK, MSG_DISCONNECT,
)


class Host:
    """
    Lado host da conexão multiplayer.

    Responsabilidades:
    - Aguardar o cliente conectar (wait_for_client)
    - Receber inputs do cliente a cada frame (update)
    - Enviar snapshots de estado ao cliente (broadcast_state)
    - Entregar eventos críticos com garantia de ACK (send_event)
    """

    def __init__(self, game_mode: str):
        self.conn = UDPConnection(HOST_PORT)
        self.game_mode = game_mode
        self.connected = False
        self._last_seen = 0.0
        self._seq = 0
        self._pending_acks: dict = {}  # seq → (mtype, payload, sent_time, retries)

    def wait_for_client(self, timeout: float = 120.0) -> bool:
        """Bloqueia até cliente enviar MSG_HELLO ou timeout expirar."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for msg in self.conn.poll():
                if msg.get("t") == MSG_HELLO:
                    self.connected = True
                    self._last_seen = time.monotonic()
                    self.conn.send(MSG_HELLO_ACK,
                                   mode=self.game_mode,
                                   player_id=1)
                    return True
            time.sleep(0.01)
        return False

    def update(self, dt: float):
        """
        Processa mensagens recebidas.
        Retorna o último input do cliente como dict, ou None.
        """
        last_input = None

        for msg in self.conn.poll():
            t = msg.get("t")
            if t == MSG_INPUT:
                last_input = msg
                self._last_seen = time.monotonic()
            elif t == MSG_EVENT_ACK:
                self._pending_acks.pop(msg.get("seq"), None)
            elif t == MSG_DISCONNECT:
                self.connected = False

        self._retransmit_pending()

        if self.connected and time.monotonic() - self._last_seen > NET_TIMEOUT:
            self.connected = False

        return last_input

    def broadcast_state(self, state: dict):
        """Envia snapshot autoritativo ao cliente. Chamado todo frame."""
        self.conn.send(MSG_STATE, **state)

    def send_event(self, event_type: str, **data):
        """Envia evento crítico com retransmissão até ACK ser recebido."""
        seq = self._seq
        self._seq += 1
        payload = {"seq": seq, "ev": event_type, **data}
        self.conn.send(MSG_EVENT, **payload)
        self._pending_acks[seq] = (MSG_EVENT, payload, time.monotonic(), 0)

    def close(self):
        if self.connected:
            self.conn.send(MSG_DISCONNECT)
        self.conn.close()

    def _retransmit_pending(self):
        now = time.monotonic()
        for seq, (mtype, payload, sent, retries) in list(self._pending_acks.items()):
            if now - sent > 0.1:
                if retries < 8:
                    self.conn.send(mtype, **payload)
                    self._pending_acks[seq] = (mtype, payload, now, retries + 1)
                else:
                    del self._pending_acks[seq]
