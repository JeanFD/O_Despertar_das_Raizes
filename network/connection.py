# network/connection.py
import socket
import threading
import queue
from network.protocol import encode, decode, MSG_PING, MSG_PONG

BUFFER = 4096


class UDPConnection:
    """
    Wrapper thread-safe sobre um socket UDP.

    A thread interna fica em loop recebendo dados e empurrando
    para recv_queue. O jogo consome poll() a cada frame sem bloquear.
    """

    def __init__(self, local_port: int):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("", local_port))
        self.sock.settimeout(0.005)

        self._recv_q: queue.Queue = queue.Queue()
        self._remote_addr = None
        self._running = True

        self._thread = threading.Thread(target=self._recv_loop, daemon=True)
        self._thread.start()

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
                if msg["t"] == MSG_PING:
                    self.sock.sendto(encode(MSG_PONG, id=msg.get("id")), addr)
                else:
                    self._recv_q.put(msg)
            except socket.timeout:
                pass
            except OSError:
                break
