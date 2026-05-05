# network/discovery.py
import socket
import threading
import time

DISCOVERY_PORT = 7779
_DISCOVER  = b"DR_FIND"
_ANNOUNCE  = b"DR_HOST:"   # seguido do game_mode em bytes


class HostAnnouncer:
    """
    Roda no host. Escuta broadcasts DISCOVER na porta 7779
    e responde unicast de volta ao cliente.
    """

    def __init__(self, game_mode: str):
        self._mode    = game_mode
        self._running = False
        self._sock    = None
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("", DISCOVERY_PORT))
            s.settimeout(0.2)
            self._sock    = s
            self._running = True
            threading.Thread(target=self._loop, daemon=True).start()
        except OSError:
            pass   # porta ocupada — discovery não funciona mas jogo continua

    def _loop(self):
        while self._running and self._sock:
            try:
                data, addr = self._sock.recvfrom(64)
                if data == _DISCOVER:
                    self._sock.sendto(_ANNOUNCE + self._mode.encode(), addr)
            except socket.timeout:
                pass
            except OSError:
                break

    def close(self):
        self._running = False
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass


class HostFinder:
    """
    Roda no cliente. Manda broadcast DISCOVER e coleta respostas de hosts
    ativos na mesma rede. Roda em thread separada; consulte .found e .searching.
    """

    def __init__(self):
        self.found: dict[str, str] = {}   # ip → game_mode
        self._running = False
        self._sock = None
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            s.settimeout(0.15)
            self._sock = s
        except OSError:
            pass

    @property
    def searching(self) -> bool:
        return self._running

    def start_search(self):
        self.found = {}
        self._running = True
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        deadline = time.monotonic() + 3.0
        while self._running and time.monotonic() < deadline:
            if self._sock:
                try:
                    self._sock.sendto(_DISCOVER, ("255.255.255.255", DISCOVERY_PORT))
                except OSError:
                    pass
                try:
                    while True:
                        data, addr = self._sock.recvfrom(64)
                        if data.startswith(_ANNOUNCE):
                            mode = data[len(_ANNOUNCE):].decode("utf-8", errors="ignore")
                            self.found[addr[0]] = mode
                except (socket.timeout, OSError):
                    pass
            time.sleep(0.3)
        self._running = False

    def close(self):
        self._running = False
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
