# network/server_client.py
import time
from network.connection import UDPConnection
from network.protocol import (
    MSG_HELLO, MSG_HELLO_ACK, MSG_INPUT,
    MSG_STATE, MSG_EVENT, MSG_EVENT_ACK, MSG_DISCONNECT,
)
from settings import SERVER_HOST, SERVER_PORT, NET_TIMEOUT


class ServerClient:
    """
    Lado cliente para o servidor dedicado.

    Diferenças em relação ao Client P2P:
    - Usa porta 0 (OS escolhe) — não conflita com outro cliente no mesmo PC.
    - Conecta em SERVER_HOST:SERVER_PORT (IP fixo do VPS).
    - Recebe player_id (1 ou 2) no handshake.
    - update() devolve (snapshot | None, lista_de_eventos) — mesma API do Client.
    """

    def __init__(self):
        self.conn      = UDPConnection(0)   # porta efêmera
        self.conn.set_remote(SERVER_HOST, SERVER_PORT)
        self.connected = False
        self.player_id = None
        self.game_mode = None
        self._acked: set = set()

    def connect(self, timeout: float = 30.0) -> bool:
        """Handshake com o servidor. Chame em thread separada."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.conn.send(MSG_HELLO)
            time.sleep(0.05)
            for msg in self.conn.poll():
                if msg.get("t") == MSG_HELLO_ACK:
                    self.player_id = msg.get("player_id")
                    self.game_mode = msg.get("mode")
                    self.connected = True
                    return True
        return False

    def send_input(self, inp: dict):
        self.conn.send(MSG_INPUT, **inp)

    def update(self, dt: float):
        """Processa mensagens recebidas. Retorna (snapshot | None, eventos)."""
        last_state = None
        events     = []

        for msg in self.conn.poll():
            t = msg.get("t")
            if t == MSG_STATE:
                last_state = msg
            elif t == MSG_EVENT:
                seq = msg.get("seq")
                self.conn.send(MSG_EVENT_ACK, seq=seq)
                if seq not in self._acked:
                    self._acked.add(seq)
                    events.append(msg)
            elif t == MSG_DISCONNECT:
                self.connected = False

        if self.connected and time.monotonic() - self.conn.last_recv_at > NET_TIMEOUT:
            self.connected = False

        return last_state, events

    def close(self):
        if self.connected:
            self.conn.send(MSG_DISCONNECT)
        self.conn.close()
