# states/multiplayer_menu.py
import pygame
from states.base_state import BaseState
from ui.menu_ui import (
    draw_gradient_bg, draw_title, draw_menu_items,
    draw_hint_bar, draw_particles, C_TEXT, C_HIGHLIGHT,
)

_ITEMS_MAIN = ["Hospedar Partida", "Entrar na Partida", "Voltar"]
_ITEMS_MODE = ["Co-op  (dois protagonistas)", "Boss Battle", "Voltar"]


class MultiplayerMenu(BaseState):
    """
    Navegação de modo multiplayer e configuração de conexão.

    Fluxo:
        main → [Hospedar] → mode → LobbyState (host)
             → [Entrar]   → ip_input → LobbyState (client)
             → [Voltar]   → MainMenu
    """

    def on_enter(self):
        self._phase = "main"
        self._sel = 0
        self._items = _ITEMS_MAIN
        self._game_mode = None
        self._ip = ""
        self._error = ""
        self._tick = 0

    def handle_event(self, event):
        if event.type != pygame.KEYDOWN:
            return
        if self._phase in ("main", "mode"):
            self._nav_key(event.key)
        elif self._phase == "ip_input":
            self._ip_key(event.key)

    def _nav_key(self, key):
        if key in (pygame.K_UP, pygame.K_w):
            self._sel = (self._sel - 1) % len(self._items)
        elif key in (pygame.K_DOWN, pygame.K_s):
            self._sel = (self._sel + 1) % len(self._items)
        elif key in (pygame.K_RETURN, pygame.K_SPACE):
            self._confirm()
        elif key == pygame.K_ESCAPE:
            self._back()

    def _ip_key(self, key):
        if key == pygame.K_RETURN:
            if self._ip:
                self._launch_client()
        elif key == pygame.K_ESCAPE:
            self._phase = "main"
            self._items = _ITEMS_MAIN
            self._sel = 1
            self._error = ""
        elif key == pygame.K_BACKSPACE:
            self._ip = self._ip[:-1]
        else:
            ch = pygame.key.name(key)
            if len(ch) == 1 and (ch.isdigit() or ch == "."):
                if len(self._ip) < 15:
                    self._ip += ch

    def _confirm(self):
        if self._phase == "main":
            if self._sel == 0:
                self._phase = "mode"
                self._items = _ITEMS_MODE
                self._sel = 0
            elif self._sel == 1:
                self._phase = "ip_input"
                self._ip = ""
                self._error = ""
            else:
                self.game.states.pop()
        elif self._phase == "mode":
            if self._sel == 0:
                self._game_mode = "coop"
                self._launch_host()
            elif self._sel == 1:
                self._game_mode = "boss"
                self._launch_host()
            else:
                self._phase = "main"
                self._items = _ITEMS_MAIN
                self._sel = 0

    def _back(self):
        if self._phase == "mode":
            self._phase = "main"
            self._items = _ITEMS_MAIN
            self._sel = 0
        else:
            self.game.states.pop()

    def _launch_host(self):
        from states.lobby_state import LobbyState
        self.game.states.change(LobbyState(self.game, is_host=True,
                                            game_mode=self._game_mode))

    def _launch_client(self):
        from states.lobby_state import LobbyState
        self.game.states.change(LobbyState(self.game, is_host=False,
                                            host_ip=self._ip))

    def update(self, dt):
        self._tick += 1

    def draw(self, surface):
        draw_gradient_bg(surface)
        draw_particles(surface, self._tick)
        draw_title(surface, "MULTIPLAYER", surface.get_height() // 6)

        if self._phase == "ip_input":
            self._draw_ip_screen(surface)
        else:
            W, H = surface.get_size()
            draw_menu_items(surface, self._items, self._sel, x=0, y=H // 2 - 40, spacing=48, size=24)

        if self._error:
            W, H = surface.get_size()
            f = pygame.font.SysFont("consolas,monospace", 18)
            t = f.render(self._error, True, (255, 80, 80))
            surface.blit(t, (W // 2 - t.get_width() // 2, H - 100))

        hint = "↑↓ navegar   ENTER confirmar   ESC voltar"
        if self._phase == "ip_input":
            hint = "Digite o IP do host   ENTER conectar   ESC voltar"
        draw_hint_bar(surface, hint)

    def _draw_ip_screen(self, surface):
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
