# server/dedicated_conn.py
import socket
import threading
import time
import queue
from network.protocol import encode, decode, MSG_PING, MSG_PONG, MSG_HELLO, MSG_HELLO_ACK, MSG_GAME_START

BUFFER             = 8192
HEARTBEAT_INTERVAL = 1.0
NET_TIMEOUT        = 5.0


class DedicatedServerConn:
    """
    Camada de rede do servidor dedicado. Gerencia 2 clientes UDP.

    Fluxo:
      1. wait_for_clients() — síncrono, bloqueia até 2 HELLOs chegarem.
         Envia HELLO_ACK com player_id (1 ou 2) para cada cliente.
         Ao retornar, inicia o recv thread.
      2. get_inputs(dt)    — chame uma vez por frame no game loop.
         Retorna (inp_p1 | None, inp_p2 | None).
      3. broadcast_state() — envia snapshot para ambos.
      4. broadcast_event() — evento crítico com retransmissão para ambos.
    """

    def __init__(self, port: int, game_mode: str):
        self.port      = port
        self.game_mode = game_mode

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("", port))

        self._clients: dict  = {}      # addr → player_id
        self._addrs:   dict  = {}      # player_id → addr
        self._queues         = {1: queue.Queue(), 2: queue.Queue()}
        self._last_seen      = {1: 0.0, 2: 0.0}

        self._seq            = 0
        self._pending_acks: dict = {1: {}, 2: {}}  # pid → {seq: (type, payload, sent, retries)}

        self.connected = [False, False]   # índice 0=p1, 1=p2
        self._running  = False

    # ── Inicialização ────────────────────────────────────────────────────────

    def wait_for_clients(self, timeout: float = 300.0) -> bool:
        """Bloqueia até receber HELLO de 2 clientes distintos."""
        self.sock.settimeout(0.5)
        deadline  = time.monotonic() + timeout
        registered: set = set()

        while time.monotonic() < deadline:
            try:
                data, addr = self.sock.recvfrom(BUFFER)
            except socket.timeout:
                continue

            msg = decode(data)
            t   = msg.get("t")

            # Responde PING de clientes já registrados para manter conexão viva
            # enquanto espera o segundo jogador.
            if t == MSG_PING and addr in registered:
                try:
                    self.sock.sendto(encode(MSG_PONG, id=msg.get("id")), addr)
                except OSError:
                    pass
                self._last_seen[self._clients[addr]] = time.monotonic()
                continue

            if t != MSG_HELLO:
                continue

            if addr not in registered:
                pid = len(registered) + 1
                self._clients[addr] = pid
                self._addrs[pid]    = addr
                self._last_seen[pid] = time.monotonic()
                registered.add(addr)
                self.connected[pid - 1] = True

                self.sock.sendto(
                    encode(MSG_HELLO_ACK, mode=self.game_mode, player_id=pid),
                    addr,
                )
                print(f"[server] Jogador {pid} conectado: {addr}")

            if len(registered) == 2:
                print("[server] Dois jogadores conectados. Iniciando partida.")
                # Avisa ambos que o jogo vai começar
                for a in registered:
                    try:
                        self.sock.sendto(encode(MSG_GAME_START), a)
                    except OSError:
                        pass
                self._start_threads()
                return True

        return False

    def _start_threads(self):
        self.sock.settimeout(0.005)
        self._running = True
        threading.Thread(target=self._recv_loop,      daemon=True).start()
        threading.Thread(target=self._heartbeat_loop, daemon=True).start()

    # ── Game loop API ────────────────────────────────────────────────────────

    def get_inputs(self, dt: float):
        """Drena as filas. Retorna (inp_p1 | None, inp_p2 | None)."""
        from network.protocol import MSG_INPUT, MSG_EVENT_ACK, MSG_DISCONNECT

        inputs = {1: None, 2: None}

        for pid in (1, 2):
            msgs = []
            try:
                while True:
                    msgs.append(self._queues[pid].get_nowait())
            except queue.Empty:
                pass

            for msg in msgs:
                t = msg.get("t")
                if t == MSG_INPUT:
                    # UDP pode reordenar dentro do mesmo lote: fica com o input
                    # de maior tk, nunca com um atrasado.
                    if inputs[pid] is None or msg.get("tk", 0) >= inputs[pid].get("tk", 0):
                        inputs[pid] = msg
                    self._last_seen[pid] = time.monotonic()
                elif t == MSG_EVENT_ACK:
                    self._pending_acks[pid].pop(msg.get("seq"), None)
                elif t == MSG_DISCONNECT:
                    self.connected[pid - 1] = False

        self._retransmit_pending()

        now = time.monotonic()
        for pid in (1, 2):
            if self.connected[pid - 1] and now - self._last_seen[pid] > NET_TIMEOUT:
                print(f"[server] Jogador {pid} timeout.")
                self.connected[pid - 1] = False

        return inputs[1], inputs[2]

    def broadcast_state(self, state: dict):
        for pid in (1, 2):
            self._send_to(pid, "ST", **state)

    def broadcast_event(self, event_type: str, **data):
        for pid in (1, 2):
            self.send_event(pid, event_type, **data)

    def send_event(self, pid: int, event_type: str, **data):
        """Evento crítico com retransmissão até ACK."""
        seq     = self._seq
        self._seq += 1
        payload = {"seq": seq, "ev": event_type, **data}
        self._send_to(pid, "EV", **payload)
        self._pending_acks[pid][seq] = ("EV", payload, time.monotonic(), 0)

    def close(self):
        from network.protocol import MSG_DISCONNECT
        self._running = False
        for pid in (1, 2):
            if self._addrs.get(pid):
                try:
                    self.sock.sendto(encode(MSG_DISCONNECT), self._addrs[pid])
                except OSError:
                    pass
        try:
            self.sock.close()
        except OSError:
            pass

    # ── Internos ─────────────────────────────────────────────────────────────

    def _send_to(self, pid: int, msg_type: str, **payload):
        addr = self._addrs.get(pid)
        if addr and self.connected[pid - 1]:
            try:
                self.sock.sendto(encode(msg_type, **payload), addr)
            except OSError:
                pass

    def _recv_loop(self):
        while self._running:
            try:
                data, addr = self.sock.recvfrom(BUFFER)
                msg = decode(data)
                if not msg:
                    continue

                pid = self._clients.get(addr)
                if pid is None:
                    continue

                self._last_seen[pid] = time.monotonic()
                t = msg.get("t")

                if t == MSG_PING:
                    try:
                        self.sock.sendto(encode(MSG_PONG, id=msg.get("id")), addr)
                    except OSError:
                        pass
                elif t != MSG_PONG:
                    self._queues[pid].put(msg)

            except socket.timeout:
                pass
            except OSError:
                break

    def _heartbeat_loop(self):
        while self._running:
            time.sleep(HEARTBEAT_INTERVAL)
            for pid in (1, 2):
                if self._addrs.get(pid):
                    try:
                        self.sock.sendto(encode(MSG_PING, id=0), self._addrs[pid])
                    except OSError:
                        pass

    def _retransmit_pending(self):
        now = time.monotonic()
        for pid in (1, 2):
            for seq, (mtype, payload, sent, retries) in list(self._pending_acks[pid].items()):
                if now - sent > 0.1:
                    if retries < 8:
                        self._send_to(pid, mtype, **payload)
                        self._pending_acks[pid][seq] = (mtype, payload, now, retries + 1)
                    else:
                        del self._pending_acks[pid][seq]
