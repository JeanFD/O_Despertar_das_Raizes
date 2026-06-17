# states/multiplayer_menu.py
import threading
import pygame
from states.base_state import BaseState
from ui.menu_ui import (
    draw_gradient_bg, draw_title, draw_menu_items,
    draw_hint_bar, draw_particles, C_TEXT, C_HIGHLIGHT,
)

_ITEMS_MAIN = ["Criar Partida", "Entrar na Partida", "Voltar"]


class MultiplayerMenu(BaseState):
    """
    Fluxo dedicated-server:

        main → [Criar]  → fase "hosting"  → mostra código → ServerLobbyState
             → [Entrar] → fase "joining"  → lista lobbies / input código
                                          → POST join → ServerLobbyState
    """

    def on_enter(self):
        self._phase    = "main"
        self._sel      = 0
        self._items    = _ITEMS_MAIN
        self._tick     = 0
        self._error    = ""

        # Fase hosting
        self._lobby_code = ""

        # Fase joining
        self._lobbies    = []      # lista de códigos disponíveis
        self._lobby_sel  = 0
        self._searching  = False

        # Fase code_input (fallback manual)
        self._code_input = ""

        # Flag para mudança de estado segura na thread principal
        self._go_to_lobby = False

    # ── Eventos ───────────────────────────────────────────────────────────────

    def handle_event(self, event):
        if event.type != pygame.KEYDOWN:
            return
        key = event.key

        if self._phase == "main":
            self._nav_key(key)
        elif self._phase == "hosting":
            if key == pygame.K_ESCAPE:
                self._phase = "main"
        elif self._phase == "joining":
            self._join_key(key)
        elif self._phase == "code_input":
            self._code_key(key)

    def _nav_key(self, key):
        if key in (pygame.K_UP, pygame.K_w):
            self._sel = (self._sel - 1) % len(self._items)
        elif key in (pygame.K_DOWN, pygame.K_s):
            self._sel = (self._sel + 1) % len(self._items)
        elif key in (pygame.K_RETURN, pygame.K_SPACE):
            self._confirm()
        elif key == pygame.K_ESCAPE:
            self.game.states.pop()

    def _join_key(self, key):
        items = self._lobbies + ["__manual__"]
        n = len(items)
        if key in (pygame.K_UP, pygame.K_w):
            self._lobby_sel = (self._lobby_sel - 1) % n
        elif key in (pygame.K_DOWN, pygame.K_s):
            self._lobby_sel = (self._lobby_sel + 1) % n
        elif key in (pygame.K_RETURN, pygame.K_SPACE):
            self._pick_lobby()
        elif key == pygame.K_r:
            self._fetch_lobbies()
        elif key == pygame.K_ESCAPE:
            self._phase = "main"

    _ALLOWED = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")

    def _code_key(self, key):
        if key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            if len(self._code_input) >= 4:
                self._do_join(self._code_input)
        elif key == pygame.K_ESCAPE:
            self._phase = "joining"
        elif key == pygame.K_BACKSPACE:
            self._code_input = self._code_input[:-1]
        else:
            ch = pygame.key.name(key).upper()
            if len(ch) == 1 and ch in self._ALLOWED and len(self._code_input) < 8:
                self._code_input += ch

    # ── Lógica ────────────────────────────────────────────────────────────────

    def _confirm(self):
        if self._sel == 0:
            self._do_create()
        elif self._sel == 1:
            self._fetch_lobbies()
            self._phase = "joining"
        else:
            self.game.states.pop()

    def _do_create(self):
        """POST /lobbies → recebe código → entra como P1."""
        self._error = ""
        threading.Thread(target=self._create_thread, daemon=True).start()
        self._phase = "hosting"
        self._lobby_code = "..."

    def _create_thread(self):
        import urllib.request, urllib.error, json
        from settings import MATCHMAKING_HOST, MATCHMAKING_PORT
        url = f"http://{MATCHMAKING_HOST}:{MATCHMAKING_PORT}/lobbies"
        try:
            req = urllib.request.Request(url, data=b"", method="POST")
            with urllib.request.urlopen(req, timeout=5) as r:
                body = json.loads(r.read())
            self._lobby_code = body.get("code", "ERRO")
        except Exception as e:
            self._lobby_code = ""
            self._error = f"Erro ao criar lobby: {e}"
            self._phase = "main"

    def _fetch_lobbies(self):
        self._searching = True
        threading.Thread(target=self._fetch_thread, daemon=True).start()

    def _fetch_thread(self):
        import urllib.request, json
        from settings import MATCHMAKING_HOST, MATCHMAKING_PORT
        url = f"http://{MATCHMAKING_HOST}:{MATCHMAKING_PORT}/lobbies"
        try:
            with urllib.request.urlopen(url, timeout=5) as r:
                body = json.loads(r.read())
            self._lobbies = [lb["code"] for lb in body.get("lobbies", [])]
        except Exception:
            self._lobbies = []
        finally:
            self._searching = False
            self._lobby_sel = 0

    def _pick_lobby(self):
        items = self._lobbies + ["__manual__"]
        if not items:
            return
        chosen = items[self._lobby_sel]
        if chosen == "__manual__":
            self._code_input = ""
            self._phase = "code_input"
        else:
            self._do_join(chosen)

    def _do_join(self, code: str):
        self._error = ""
        threading.Thread(target=self._join_thread,
                         args=(code,), daemon=True).start()

    def _join_thread(self, code: str):
        import urllib.request, urllib.error, json
        from settings import MATCHMAKING_HOST, MATCHMAKING_PORT
        url = f"http://{MATCHMAKING_HOST}:{MATCHMAKING_PORT}/lobbies/{code}/join"
        try:
            req = urllib.request.Request(url, data=b"", method="POST")
            with urllib.request.urlopen(req, timeout=5) as r:
                body = json.loads(r.read())
            if body.get("ok"):
                self._go_to_lobby = True   # sinaliza para o update() na thread principal
            else:
                self._error = body.get("error", "Erro ao entrar no lobby.")
        except urllib.error.HTTPError as e:
            body = json.loads(e.read())
            self._error = body.get("error", f"HTTP {e.code}")
        except Exception as e:
            self._error = f"Erro de conexão: {e}"

    def _go_to_server_lobby(self):
        from states.lobby_state import ServerLobbyState
        self.game.states.change(ServerLobbyState(self.game))

    # ── Update / Draw ─────────────────────────────────────────────────────────

    def update(self, dt):
        self._tick += 1

        # Mudanças de estado sempre na thread principal (evita race condition)
        if self._go_to_lobby:
            self._go_to_lobby = False
            self._go_to_server_lobby()
            return

        # P1: quando o código chegou do servidor HTTP, conecta ao game server
        if (self._phase == "hosting"
                and self._lobby_code
                and self._lobby_code != "..."
                and not getattr(self, "_host_connecting", False)):
            self._host_connecting = True
            self._go_to_server_lobby()

    def draw(self, surface):
        draw_gradient_bg(surface)
        draw_particles(surface, self._tick)
        draw_title(surface, "MULTIPLAYER", surface.get_height() // 6)

        if self._phase == "main":
            W, H = surface.get_size()
            draw_menu_items(surface, self._items, self._sel,
                            x=0, y=H // 2 - 40, spacing=48, size=24)
        elif self._phase == "hosting":
            self._draw_hosting(surface)
        elif self._phase == "joining":
            self._draw_joining(surface)
        elif self._phase == "code_input":
            self._draw_code_input(surface)

        if self._error:
            W, H = surface.get_size()
            f = pygame.font.SysFont("consolas,monospace", 18)
            t = f.render(self._error, True, (255, 80, 80))
            surface.blit(t, (W // 2 - t.get_width() // 2, H - 100))

        hints = {
            "main":       "↑↓ navegar   ENTER confirmar   ESC voltar",
            "hosting":    "Aguarde o outro jogador entrar   ESC cancelar",
            "joining":    "↑↓ navegar   ENTER entrar   R atualizar   ESC voltar",
            "code_input": "Digite o código   ENTER confirmar   ESC voltar",
        }
        draw_hint_bar(surface, hints.get(self._phase, ""))

    def _draw_hosting(self, surface):
        W, H = surface.get_size()
        f_lbl  = pygame.font.SysFont("consolas,monospace", 20)
        f_code = pygame.font.SysFont("consolas,monospace", 52, bold=True)

        lbl = f_lbl.render("Compartilhe este código com o outro jogador:", True, (160, 200, 160))
        surface.blit(lbl, (W // 2 - lbl.get_width() // 2, H // 2 - 70))

        code_txt = f_code.render(self._lobby_code, True, (255, 220, 60))
        surface.blit(code_txt, (W // 2 - code_txt.get_width() // 2, H // 2 - 20))

        # spinner de espera
        import math
        cy = H // 2 + 80
        for i in range(8):
            angle = math.pi * 2 * i / 8 + self._tick / 8
            ax = W // 2 + math.cos(angle) * 20
            ay = cy   + math.sin(angle) * 20
            a  = int(40 + 215 * (i / 8))
            pygame.draw.circle(surface, (a, a, 200), (int(ax), int(ay)), 4)


    def _draw_joining(self, surface):
        W, H = surface.get_size()
        f_title = pygame.font.SysFont("consolas,monospace", 20)
        f_item  = pygame.font.SysFont("consolas,monospace", 22)

        if self._searching:
            import math
            dots = "." * (1 + (self._tick // 20) % 3)
            s_txt = f_title.render("Procurando partidas" + dots, True, (160, 200, 160))
        else:
            n   = len(self._lobbies)
            msg = f"{n} partida(s) disponível(is)  —  R para atualizar"
            s_txt = f_title.render(msg, True, (160, 160, 200))
        surface.blit(s_txt, (W // 2 - s_txt.get_width() // 2, H // 2 - 130))

        display = self._lobbies + ["Inserir código manualmente"]
        start_y = H // 2 - 60
        for i, label in enumerate(display):
            selected = (i == self._lobby_sel)
            color    = (255, 220, 60) if selected else (180, 180, 200)
            prefix   = "▶ " if selected else "  "
            t = f_item.render(prefix + label, True, color)
            surface.blit(t, (W // 2 - t.get_width() // 2, start_y + i * 36))

    def _draw_code_input(self, surface):
        W, H = surface.get_size()
        fl = pygame.font.SysFont("consolas,monospace", 20)
        fi = pygame.font.SysFont("consolas,monospace", 36)

        lbl = fl.render("Código da partida:", True, (180, 180, 200))
        surface.blit(lbl, (W // 2 - lbl.get_width() // 2, H // 2 - 60))

        box = pygame.Rect(W // 2 - 160, H // 2 - 24, 320, 50)
        pygame.draw.rect(surface, (30, 30, 50), box, border_radius=6)
        pygame.draw.rect(surface, (100, 100, 180), box, 2, border_radius=6)

        cursor  = "|" if (self._tick // 30) % 2 == 0 else " "
        inp_txt = fi.render(self._code_input + cursor, True, (230, 230, 255))
        surface.blit(inp_txt, (box.x + 14, box.y + 8))
