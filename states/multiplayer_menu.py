# states/multiplayer_menu.py
import pygame
from states.base_state import BaseState
from ui.menu_ui import (
    draw_gradient_bg, draw_title, draw_menu_items,
    draw_hint_bar, draw_particles, C_TEXT, C_HIGHLIGHT,
)

_ITEMS_MAIN = ["Hospedar Partida", "Entrar na Partida", "Voltar"]
_ITEMS_MODE = [
    "Co-op  (dois protagonistas)",
    "Versus (1v1)",
    "Boss Battle",
    "Voltar",
]


class MultiplayerMenu(BaseState):
    """
    Fluxo:
        main → [Hospedar] → mode  → LobbyState(host)
             → [Entrar]   → searching → seleciona host → LobbyState(client)
                                      → ip_input (fallback manual)
    """

    def on_enter(self):
        self._phase     = "main"
        self._sel       = 0
        self._items     = _ITEMS_MAIN
        self._game_mode = None
        self._tick      = 0
        self._error     = ""

        # fase searching
        self._finder      = None
        self._found       = []   # lista de (ip, mode)
        self._host_sel    = 0

        # fase ip_input (fallback)
        self._ip = ""

    def on_exit(self):
        if self._finder:
            self._finder.close()
            self._finder = None

    # ── Eventos ───────────────────────────────────────────────────────────────

    def handle_event(self, event):
        if event.type != pygame.KEYDOWN:
            return
        key = event.key

        if self._phase in ("main", "mode"):
            self._nav_key(key)
        elif self._phase == "searching":
            self._search_key(key)
        elif self._phase == "ip_input":
            self._ip_key(key)

    def _nav_key(self, key):
        if key in (pygame.K_UP, pygame.K_w):
            self._sel = (self._sel - 1) % len(self._items)
        elif key in (pygame.K_DOWN, pygame.K_s):
            self._sel = (self._sel + 1) % len(self._items)
        elif key in (pygame.K_RETURN, pygame.K_SPACE):
            self._confirm()
        elif key == pygame.K_ESCAPE:
            self._back()

    def _search_key(self, key):
        items = self._found + [("__manual__", "")]
        n = len(items)
        if key in (pygame.K_UP, pygame.K_w):
            self._host_sel = (self._host_sel - 1) % n
        elif key in (pygame.K_DOWN, pygame.K_s):
            self._host_sel = (self._host_sel + 1) % n
        elif key in (pygame.K_RETURN, pygame.K_SPACE):
            self._pick_host()
        elif key == pygame.K_r:
            self._start_search()
        elif key == pygame.K_ESCAPE:
            if self._finder:
                self._finder.close()
                self._finder = None
            self._phase = "main"
            self._sel   = 1

    _NUMPAD = {
        pygame.K_KP0: "0", pygame.K_KP1: "1", pygame.K_KP2: "2",
        pygame.K_KP3: "3", pygame.K_KP4: "4", pygame.K_KP5: "5",
        pygame.K_KP6: "6", pygame.K_KP7: "7", pygame.K_KP8: "8",
        pygame.K_KP9: "9", pygame.K_KP_PERIOD: ".",
    }

    def _ip_key(self, key):
        if key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            if self._ip:
                self._launch_client(self._ip)
        elif key == pygame.K_ESCAPE:
            self._phase    = "searching"
        elif key == pygame.K_BACKSPACE:
            self._ip = self._ip[:-1]
        else:
            ch = self._NUMPAD.get(key) or pygame.key.name(key)
            if len(ch) == 1 and (ch.isdigit() or ch == "."):
                if len(self._ip) < 15:
                    self._ip += ch

    # ── Lógica ────────────────────────────────────────────────────────────────

    def _confirm(self):
        if self._phase == "main":
            if self._sel == 0:
                self._phase = "mode"
                self._items = _ITEMS_MODE
                self._sel   = 0
            elif self._sel == 1:
                self._start_search()
            else:
                self.game.states.pop()
        elif self._phase == "mode":
            if self._sel == 0:
                self._game_mode = "coop"
                self._launch_host()
            elif self._sel == 1:
                self._game_mode = "vs"
                self._launch_host()
            elif self._sel == 2:
                self._game_mode = "boss"
                self._launch_host()
            else:
                self._phase = "main"
                self._items = _ITEMS_MAIN
                self._sel   = 0

    def _back(self):
        if self._phase == "mode":
            self._phase = "main"
            self._items = _ITEMS_MAIN
            self._sel   = 0
        else:
            self.game.states.pop()

    def _start_search(self):
        from network.discovery import HostFinder
        if self._finder:
            self._finder.close()
        self._finder   = HostFinder()
        self._found    = []
        self._host_sel = 0
        self._phase    = "searching"
        self._finder.start_search()

    def _pick_host(self):
        items = self._found + [("__manual__", "")]
        if not items:
            return
        ip, _ = items[self._host_sel]
        if ip == "__manual__":
            self._ip    = ""
            self._phase = "ip_input"
        else:
            self._launch_client(ip)

    def _launch_host(self):
        from states.lobby_state import LobbyState
        self.game.states.change(LobbyState(self.game, is_host=True,
                                            game_mode=self._game_mode))

    def _launch_client(self, ip: str):
        from states.lobby_state import LobbyState
        self.game.states.change(LobbyState(self.game, is_host=False,
                                            host_ip=ip))

    # ── Update / Draw ─────────────────────────────────────────────────────────

    def update(self, dt):
        self._tick += 1
        if self._phase == "searching" and self._finder:
            self._found = list(self._finder.found.items())

    def draw(self, surface):
        draw_gradient_bg(surface)
        draw_particles(surface, self._tick)
        draw_title(surface, "MULTIPLAYER", surface.get_height() // 6)

        if self._phase in ("main", "mode"):
            W, H = surface.get_size()
            draw_menu_items(surface, self._items, self._sel,
                            x=0, y=H // 2 - 40, spacing=48, size=24)
        elif self._phase == "searching":
            self._draw_search(surface)
        elif self._phase == "ip_input":
            self._draw_ip(surface)

        if self._error:
            W, H = surface.get_size()
            f = pygame.font.SysFont("consolas,monospace", 18)
            t = f.render(self._error, True, (255, 80, 80))
            surface.blit(t, (W // 2 - t.get_width() // 2, H - 100))

        hint = "↑↓ navegar   ENTER confirmar   ESC voltar"
        if self._phase == "searching":
            hint = "↑↓ navegar   ENTER conectar   R nova busca   ESC voltar"
        elif self._phase == "ip_input":
            hint = "Digite o IP   ENTER conectar   ESC voltar"
        draw_hint_bar(surface, hint)

    def _draw_search(self, surface):
        W, H = surface.get_size()
        f_title = pygame.font.SysFont("consolas,monospace", 20)
        f_item  = pygame.font.SysFont("consolas,monospace", 22)

        # Status da busca
        if self._finder and self._finder.searching:
            import math
            status = "Procurando partidas na rede"
            dots = "." * (1 + (self._tick // 20) % 3)
            s_txt = f_title.render(status + dots, True, (160, 200, 160))
        else:
            n = len(self._found)
            msg = f"{n} partida(s) encontrada(s)  —  R para buscar novamente"
            s_txt = f_title.render(msg, True, (160, 160, 200))
        surface.blit(s_txt, (W // 2 - s_txt.get_width() // 2, H // 2 - 130))

        # Lista de hosts + opção manual
        display_items = [f"{ip}   [{mode.upper()}]" for ip, mode in self._found]
        display_items.append("Inserir IP manualmente")

        start_y = H // 2 - 60
        for i, label in enumerate(display_items):
            selected = (i == self._host_sel)
            color = (255, 220, 60) if selected else (180, 180, 200)
            prefix = "▶ " if selected else "  "
            t = f_item.render(prefix + label, True, color)
            surface.blit(t, (W // 2 - t.get_width() // 2, start_y + i * 36))

        if len(display_items) == 1:   # só a opção manual
            hint_t = f_title.render("Nenhuma partida encontrada. Verifique se o host está aguardando.",
                                     True, (140, 100, 100))
            surface.blit(hint_t, (W // 2 - hint_t.get_width() // 2, H // 2 + 20))

    def _draw_ip(self, surface):
        W, H = surface.get_size()
        fl = pygame.font.SysFont("consolas,monospace", 20)
        fi = pygame.font.SysFont("consolas,monospace", 28)

        lbl = fl.render("IP do Host:", True, (180, 180, 200))
        surface.blit(lbl, (W // 2 - lbl.get_width() // 2, H // 2 - 60))

        box = pygame.Rect(W // 2 - 160, H // 2 - 20, 320, 44)
        pygame.draw.rect(surface, (30, 30, 50), box, border_radius=6)
        pygame.draw.rect(surface, (100, 100, 180), box, 2, border_radius=6)

        cursor = "|" if (self._tick // 30) % 2 == 0 else " "
        inp_t = fi.render(self._ip + cursor, True, (230, 230, 255))
        surface.blit(inp_t, (box.x + 12, box.y + 7))

        hint_t = fl.render("ex: 192.168.1.5", True, (100, 100, 120))
        surface.blit(hint_t, (W // 2 - hint_t.get_width() // 2, H // 2 + 34))
