# network/client.py
import time
from settings import HOST_PORT, CLIENT_PORT, NET_TIMEOUT
from network.connection import UDPConnection
from network.protocol import (
    MSG_HELLO, MSG_HELLO_ACK, MSG_INPUT,
    MSG_STATE, MSG_EVENT, MSG_EVENT_ACK, MSG_DISCONNECT,
)


class Client:
    """
    Lado cliente da conexão multiplayer.

    Responsabilidades:
    - Conectar ao host pelo IP informado (connect)
    - Enviar inputs locais todo frame (send_input)
    - Receber snapshots e eventos do host (update)
    """

    def __init__(self):
        self.conn = UDPConnection(CLIENT_PORT)
        self.connected = False
        self.game_mode = None
        self.player_id = None
        self._last_seen = 0.0
        self._acked: set = set()
        # ts do último snapshot APLICADO. UDP pode reordenar: snapshots com ts
        # menor que este são atrasados e devem ser descartados, senão o estado
        # (inclusive o nome da animação) "volta no tempo" e pisca.
        self._last_state_ts = 0.0

    def connect(self, host_ip: str, timeout: float = 15.0) -> bool:
        """Tenta handshake com o host. Chame em thread separada."""
        self.conn.set_remote(host_ip, HOST_PORT)
        deadline = time.monotonic() + timeout

        while time.monotonic() < deadline:
            self.conn.send(MSG_HELLO)
            time.sleep(0.05)
            for msg in self.conn.poll():
                if msg.get("t") == MSG_HELLO_ACK:
                    self.game_mode = msg.get("mode")
                    self.player_id = msg.get("player_id")
                    self.connected = True
                    self._last_seen = time.monotonic()
                    return True

        return False

    def send_input(self, inp: dict):
        """Envia dict de inputs para o host. Chame todo frame."""
        self.conn.send(MSG_INPUT, **inp)

    def update(self, dt: float):
        """
        Processa mensagens recebidas.
        Retorna (ultimo_snapshot | None, lista_de_eventos_criticos).
        """
        last_state = None
        events = []

        for msg in self.conn.poll():
            t = msg.get("t")
            if t == MSG_STATE:
                self._last_seen = time.monotonic()
                # Só aceita snapshots mais novos que o último aplicado; os
                # atrasados (reordenados pelo UDP) são ignorados para não
                # regredir o estado e piscar a animação.
                ts = msg.get("ts", 0.0)
                if ts >= self._last_state_ts:
                    self._last_state_ts = ts
                    last_state = msg
            elif t == MSG_EVENT:
                seq = msg.get("seq")
                self.conn.send(MSG_EVENT_ACK, seq=seq)
                if seq not in self._acked:
                    self._acked.add(seq)
                    events.append(msg)
            elif t == MSG_DISCONNECT:
                self.connected = False

        # Timeout robusto via recv thread (heartbeat-aware).
        if self.connected and time.monotonic() - self.conn.last_recv_at > NET_TIMEOUT:
            self.connected = False

        return last_state, events

    def close(self):
        if self.connected:
            self.conn.send(MSG_DISCONNECT)
        self.conn.close()
