# network/server_client.py
import time
from network.connection import UDPConnection
from network.protocol import (
    MSG_HELLO, MSG_HELLO_ACK, MSG_GAME_START, MSG_INPUT,
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
    - game_started fica True quando servidor envia START (ambos conectados).
    - update() devolve (snapshot | None, lista_de_eventos) — mesma API do Client.
    """

    def __init__(self):
        self.conn         = UDPConnection(0)   # porta efêmera
        self.conn.set_remote(SERVER_HOST, SERVER_PORT)
        self.connected    = False
        self.game_started = False
        self.player_id    = None
        self.game_mode    = None
        self._acked: set  = set()
        # ts do último snapshot APLICADO. UDP pode reordenar: snapshots com ts
        # menor são atrasados e devem ser ignorados, senão o estado (inclusive
        # o nome da animação) "volta no tempo" e pisca entre ações.
        self._last_state_ts = 0.0

    def connect(self, timeout: float = 30.0) -> bool:
        """Handshake inicial — retorna quando recebe HELLO_ACK.

        Processa o LOTE INTEIRO de mensagens antes de retornar. O servidor
        envia GAME_START logo após o HELLO_ACK e, para o 2º jogador, os dois
        pacotes costumam chegar no mesmo poll(). Se retornássemos no HELLO_ACK
        sem olhar o resto do lote, o GAME_START seria descartado (poll já o
        removeu da fila) e o P2 ficaria preso na tela de espera para sempre,
        porque o servidor manda GAME_START uma única vez, sem retransmissão.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not self.connected:
                self.conn.send(MSG_HELLO)
            time.sleep(0.05)
            for msg in self.conn.poll():
                t = msg.get("t")
                if t == MSG_HELLO_ACK:
                    self.player_id = msg.get("player_id")
                    self.game_mode = msg.get("mode")
                    self.connected = True
                elif t == MSG_GAME_START:
                    self.game_started = True
                elif t == MSG_STATE:
                    # Snapshot já chegando ⇒ partida em andamento mesmo que o
                    # GAME_START tenha se perdido. Defesa contra perda de UDP.
                    self.game_started = True
            if self.connected:
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
            if t == MSG_GAME_START:
                self.game_started = True
            elif t == MSG_STATE:
                # Receber snapshot implica que a partida já está rodando —
                # cobre o caso de o GAME_START ter se perdido no caminho.
                self.game_started = True
                # Só aceita snapshots mais novos que o último aplicado; os
                # atrasados (reordenados pelo UDP) são descartados para não
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

        if self.connected and time.monotonic() - self.conn.last_recv_at > NET_TIMEOUT:
            self.connected = False

        return last_state, events

    def close(self):
        if self.connected:
            self.conn.send(MSG_DISCONNECT)
        self.conn.close()
