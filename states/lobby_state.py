# states/lobby_state.py
import socket
import threading
import pygame
from states.base_state import BaseState
from ui.menu_ui import draw_gradient_bg, draw_title, draw_hint_bar


class LobbyState(BaseState):
    """
    Sala de espera: host aguarda cliente conectar, cliente tenta conectar.
    Toda comunicação de rede roda em thread separada para não travar o render.
    """

    def __init__(self, game, is_host: bool,
                 game_mode=None, host_ip=None):
        super().__init__(game)
        self.is_host   = is_host
        self.game_mode = game_mode
        self.host_ip   = host_ip
        self._net      = None
        self._status   = ""
        self._error    = ""
        self._ready    = False
        self._tick     = 0

    def on_enter(self):
        if self.is_host:
            threading.Thread(target=self._host_thread, daemon=True).start()
        else:
            threading.Thread(target=self._client_thread, daemon=True).start()

    def _host_thread(self):
        from network.host import Host
        from settings import HOST_PORT
        try:
            ips = _get_lan_ips()
            ip_str = " / ".join(ips) if ips else "IP não detectado"
            self._status = (f"Aguardando conexão na porta {HOST_PORT}...\n"
                            f"Seu IP na rede: {ip_str}")
        except Exception:
            self._status = "Aguardando conexão..."

        try:
            net = Host(self.game_mode)
        except OSError as e:
            self._error = (f"Não foi possível abrir a porta {HOST_PORT} UDP.\n"
                           f"Erro: {e}\n"
                           "Tente fechar e reabrir o jogo.")
            return

        if net.wait_for_client(timeout=120.0):
            self._net = net
            self._status = "Cliente conectado! Iniciando..."
            self._ready = True
        else:
            net.close()
            self._error = "Tempo esgotado. Nenhum cliente se conectou."

    def _client_thread(self):
        from network.client import Client
        from settings import HOST_PORT
        self._status = f"Conectando a {self.host_ip}:{HOST_PORT}..."
        try:
            net = Client()
        except OSError as e:
            self._error = f"Erro ao abrir socket local: {e}"
            return

        if net.connect(self.host_ip, timeout=15.0):
            self._net = net
            self.game_mode = net.game_mode
            self._status = f"Conectado!  Modo: {self.game_mode}"
            self._ready = True
        else:
            net.close()
            self._error = (f"Sem resposta de {self.host_ip}:{HOST_PORT}\n"
                           "Verifique:\n"
                           "1) O host está na tela de espera?\n"
                           "2) Firewall liberado? (veja test_net.py)\n"
                           "3) IP correto?")

    def handle_event(self, event):
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            if self._net:
                self._net.close()
                self._net = None
            self.game.states.pop()

    def update(self, dt):
        self._tick += 1
        if self._ready and self._net:
            self._launch_gameplay()

    def _launch_gameplay(self):
        from states.multiplayer_gameplay import MultiplayerGameplayState
        state = MultiplayerGameplayState(
            self.game,
            net=self._net,
            is_host=self.is_host,
            game_mode=self.game_mode,
        )
        self.game.states.change(state)

    def draw(self, surface):
        draw_gradient_bg(surface)
        draw_title(surface, "SALA DE ESPERA", surface.get_height() // 6)

        W, H = surface.get_size()
        f = pygame.font.SysFont("consolas,monospace", 22)

        text = self._error if self._error else self._status
        color = (255, 80, 80) if self._error else (180, 220, 180)
        lines = text.split("\n")
        start_y = H // 2 - (len(lines) * 28) // 2

        for i, line in enumerate(lines):
            t = f.render(line, True, color)
            surface.blit(t, (W // 2 - t.get_width() // 2, start_y + i * 28))

        if not self._error:
            self._draw_spinner(surface, W // 2, H // 2 + 90)

        draw_hint_bar(surface, "ESC cancelar")

    def _draw_spinner(self, surface, cx, cy):
        import math
        t = self._tick / 8
        for i in range(8):
            angle = math.pi * 2 * i / 8 + t
            ax = cx + math.cos(angle) * 20
            ay = cy + math.sin(angle) * 20
            a = int(40 + 215 * (i / 8))
            pygame.draw.circle(surface, (a, a, 200), (int(ax), int(ay)), 4)


def _get_lan_ips() -> list[str]:
    """
    Retorna lista de IPs LAN desta máquina (Wi-Fi / Ethernet).
    Usa o truque de connect UDP para forçar o SO a escolher
    a interface correta — não envia dados de verdade.
    """
    import socket
    found = []

    # Método 1: connect trick (mais confiável — pega o IP da rota padrão)
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        if not ip.startswith("127."):
            found.append(ip)
    except Exception:
        pass

    # Método 2: getaddrinfo (captura múltiplas interfaces)
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127.") and ip not in found:
                found.append(ip)
    except Exception:
        pass

    return found if found else ["127.0.0.1 (local only)"]
