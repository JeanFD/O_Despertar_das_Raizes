# network/connection.py
import socket
import threading
import time
import queue
from network.protocol import encode, decode, MSG_PING, MSG_PONG

BUFFER             = 4096
HEARTBEAT_INTERVAL = 1.0   # PING a cada 1s — basta para manter < NET_TIMEOUT


class UDPConnection:
    """
    Wrapper thread-safe sobre um socket UDP.

    Threads internas:
    - recv_loop:      lê pacotes, atualiza last_recv_at e enfileira p/ o jogo.
                      Pacotes PING são respondidos automaticamente (PONG)
                      sem passar pelo main loop.
    - heartbeat_loop: envia MSG_PING a cada HEARTBEAT_INTERVAL segundos.
                      Garante que mesmo se o main loop do peer congelar
                      (alt-tab, troca de tela), a recv thread dele continua
                      respondendo PONG e a conexão não cai por timeout.

    `last_recv_at` é atualizado para QUALQUER pacote recebido (PING/PONG/jogo).
    Use-o em vez de timestamps mantidos pelo main loop para detectar timeout
    — assim, freezes do loop não derrubam a sessão.
    """

    def __init__(self, local_port: int):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("", local_port))
        self.sock.settimeout(0.005)

        self._recv_q: queue.Queue = queue.Queue()
        self._remote_addr = None
        self._running = True
        self.last_recv_at = time.monotonic()

        self._thread = threading.Thread(target=self._recv_loop, daemon=True)
        self._thread.start()

        self._hb_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self._hb_thread.start()

    def set_remote(self, host: str, port: int):
        self._remote_addr = (host, port)

    def send(self, msg_type: str, **payload):
        if not self._remote_addr:
            return
        try:
            self.sock.sendto(encode(msg_type, **payload), self._remote_addr)
        except OSError:
            pass

    def poll(self) -> list:
        """Drena a fila de recebidos. Chame uma vez por frame."""
        msgs = []
        try:
            while True:
                msgs.append(self._recv_q.get_nowait())
        except queue.Empty:
            pass
        return msgs

    def close(self):
        self._running = False
        try:
            self.sock.close()
        except OSError:
            pass

    def _recv_loop(self):
        while self._running:
            try:
                data, addr = self.sock.recvfrom(BUFFER)
                msg = decode(data)
                if not msg:
                    continue
                if self._remote_addr is None:
                    self._remote_addr = addr
                # Qualquer pacote conta como "peer está vivo".
                self.last_recv_at = time.monotonic()
                t = msg.get("t")
                if t == MSG_PING:
                    try:
                        self.sock.sendto(encode(MSG_PONG, id=msg.get("id")), addr)
                    except OSError:
                        pass
                elif t == MSG_PONG:
                    # já contabilizado em last_recv_at
                    pass
                else:
                    self._recv_q.put(msg)
            except socket.timeout:
                pass
            except OSError:
                break

    def _heartbeat_loop(self):
        while self._running:
            time.sleep(HEARTBEAT_INTERVAL)
            if not self._running:
                break
            if self._remote_addr is not None:
                try:
                    self.sock.sendto(
                        encode(MSG_PING, id=0), self._remote_addr
                    )
                except OSError:
                    break
