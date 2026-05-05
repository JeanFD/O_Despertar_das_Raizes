# states/versus_post_match.py
"""
Lobby pós-partida do modo Versus.

Reusa a MESMA conexão UDP que estava em uso. on_exit só fecha a conexão
se este state ainda for o "dono" do net — quando aceitamos a revanche
e empurramos um novo VersusGameplayState, transferimos a posse antes do
states.change(...) e on_exit não fecha.

Sincronização:
- Host autoritativo. Mantém {ready_p1, ready_p2}.
- Cliente envia toggle ("rd": 0|1) via send_input.
- Host re-broadcast de estado a cada frame.
- Quando ambos prontos → host emite "rematch_start" (ACK) e ambos
  transitam para um VersusGameplayState novo, com a mesma conexão.
- "Sair" do post-match fecha a conexão; o outro lado detecta
  desconexão e cai pro menu (mensagem amigável).
"""

import pygame
from states.base_state import BaseState
from ui.menu_ui import draw_gradient_bg, draw_particles, draw_hint_bar


class VersusPostMatchState(BaseState):

    def __init__(self, game, net, is_host: bool, best_of: int,
                 score_p1: int, score_p2: int, winner: int):
        super().__init__(game)
        self.net      = net
        self.is_host  = is_host
        self.best_of  = best_of
        self.score_p1 = score_p1
        self.score_p2 = score_p2
        self.winner   = winner   # 0=draw, 1=p1, 2=p2

        # 0 = REMATCH (toggle ready), 1 = LEAVE
        self._sel = 0

        # Estado de votos: somente host é autoritativo.
        self._ready_p1 = False
        self._ready_p2 = False

        self._owns_net     = True
        self._disconnected = False
        self._tick         = 0

        # Lado local: P1 se sou host, P2 se sou cliente.
        # Toggle de input enviado a cada frame até o host registrar.
        self._local_ready_pending = False

    # ── Ciclo de vida ─────────────────────────────────────────────────────────

    def on_exit(self):
        if self._owns_net and self.net:
            self.net.close()

    # ── Eventos ───────────────────────────────────────────────────────────────

    def handle_event(self, event):
        if event.type != pygame.KEYDOWN:
            return
        key = event.key

        if self._disconnected:
            if key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_SPACE):
                self._leave()
            return

        if key in (pygame.K_LEFT, pygame.K_a, pygame.K_RIGHT, pygame.K_d):
            self._sel = 1 - self._sel
        elif key in (pygame.K_RETURN, pygame.K_SPACE):
            if self._sel == 0:
                self._toggle_ready()
            else:
                self._leave()
        elif key == pygame.K_ESCAPE:
            self._leave()

    def _toggle_ready(self):
        if self.is_host:
            self._ready_p1 = not self._ready_p1
        else:
            # Cliente: inverte localmente, host vai confirmar via snapshot.
            self._ready_p2 = not self._ready_p2
            self._local_ready_pending = self._ready_p2

    def _leave(self):
        from states.main_menu import MainMenu
        # Fecha conexão (envia MSG_DISCONNECT). on_exit não vai fechar
        # de novo porque marcamos que já não somos donos.
        if self.net:
            try:
                self.net.close()
            except Exception:
                pass
        self._owns_net = False
        self.net = None
        self.game.states.change(MainMenu(self.game))

    # ── Update ────────────────────────────────────────────────────────────────

    def update(self, dt):
        self._tick += 1
        if self._disconnected or self.net is None:
            return

        if self.is_host:
            self._update_host(dt)
        else:
            self._update_client(dt)

    def _update_host(self, dt):
        msg = self.net.update(dt)
        if msg is not None and "rd" in msg:
            self._ready_p2 = bool(msg.get("rd", 0))

        if not self.net.connected:
            self._disconnected = True
            return

        self.net.broadcast_state({
            "r1": int(self._ready_p1),
            "r2": int(self._ready_p2),
            "s1": self.score_p1,
            "s2": self.score_p2,
            "w":  self.winner,
            "bo": self.best_of,
        })

        if self._ready_p1 and self._ready_p2:
            self._start_rematch()

    def _update_client(self, dt):
        # Comunica nosso voto continuamente (host trata como toggle absoluto).
        self.net.send_input({"rd": int(self._ready_p2)})

        state, events = self.net.update(dt)

        if not self.net.connected:
            self._disconnected = True
            return

        if state:
            self._ready_p1 = bool(state.get("r1", 0))
            # Confiamos no host se houver divergência (ele é autoritativo).
            self._ready_p2 = bool(state.get("r2", self._ready_p2))
            self.score_p1 = int(state.get("s1", self.score_p1))
            self.score_p2 = int(state.get("s2", self.score_p2))
            self.winner   = int(state.get("w",  self.winner))
            self.best_of  = int(state.get("bo", self.best_of))

        for ev in events:
            if ev.get("ev") == "rematch_start":
                self._start_rematch()
                return

    def _start_rematch(self):
        if not self._owns_net or self.net is None:
            return  # já transitamos, evita re-entrância
        if self.is_host:
            # Host avisa o cliente que vamos voltar pra arena.
            self.net.send_event("rematch_start", bo=self.best_of)
        from states.versus_gameplay import VersusGameplayState
        new_state = VersusGameplayState(
            self.game, net=self.net, is_host=self.is_host, best_of=self.best_of,
        )
        # Transferimos a posse: on_exit deste state NÃO deve fechar net.
        self._owns_net = False
        self.game.states.change(new_state)

    # ── Draw ──────────────────────────────────────────────────────────────────

    def draw(self, surface):
        draw_gradient_bg(surface)
        draw_particles(surface, self._tick)
        W, H = surface.get_size()

        # Banner do vencedor
        f_big   = pygame.font.SysFont("consolas,monospace", 56, bold=True)
        f_score = pygame.font.SysFont("consolas,monospace", 38, bold=True)
        f_lab   = pygame.font.SysFont("consolas,monospace", 18)

        if self.winner == 1:
            title, color = "PLAYER 1 WINS", (90, 200, 255)
        elif self.winner == 2:
            title, color = "PLAYER 2 WINS", (255, 140, 90)
        else:
            title, color = "DRAW", (220, 220, 220)

        t = f_big.render(title, True, color)
        sh = f_big.render(title, True, (0, 0, 0))
        tx = W // 2 - t.get_width() // 2
        ty = H // 6
        surface.blit(sh, (tx + 3, ty + 3))
        surface.blit(t, (tx, ty))

        # Placar central
        score = f_score.render(f"{self.score_p1}  —  {self.score_p2}",
                                True, (240, 240, 250))
        surface.blit(score, (W // 2 - score.get_width() // 2, ty + 80))
        bo = f_lab.render(f"Best of {self.best_of}", True, (170, 170, 200))
        surface.blit(bo, (W // 2 - bo.get_width() // 2, ty + 130))

        # Indicadores de READY
        self._draw_ready_card(surface,
                              x=W // 4 - 110, y=H // 2 + 30,
                              label="P1", ready=self._ready_p1,
                              is_local=self.is_host)
        self._draw_ready_card(surface,
                              x=3 * W // 4 - 110, y=H // 2 + 30,
                              label="P2", ready=self._ready_p2,
                              is_local=not self.is_host)

        # Botões (REMATCH / LEAVE)
        self._draw_buttons(surface)

        if self._disconnected:
            self._draw_disconnect_overlay(surface)

        local_label = "P1 (você)" if self.is_host else "P2 (você)"
        draw_hint_bar(
            surface,
            f"{local_label}    ←/→ navegar    ENTER confirmar    ESC sair"
        )

    def _draw_ready_card(self, surface, x, y, label, ready, is_local):
        w, h = 220, 90
        bg = (40, 80, 50) if ready else (50, 40, 50)
        border = (100, 220, 130) if ready else (90, 90, 110)
        pygame.draw.rect(surface, bg, (x, y, w, h), border_radius=10)
        pygame.draw.rect(surface, border, (x, y, w, h), 2, border_radius=10)

        f_l = pygame.font.SysFont("consolas,monospace", 22, bold=True)
        f_s = pygame.font.SysFont("consolas,monospace", 18)
        col_l = (220, 240, 255)
        l = f_l.render(label + ("  (você)" if is_local else ""), True, col_l)
        surface.blit(l, (x + 14, y + 10))

        status = "READY" if ready else "NOT READY"
        col_s  = (90, 240, 130) if ready else (200, 120, 120)
        s = f_s.render(status, True, col_s)
        surface.blit(s, (x + 14, y + 50))

    def _draw_buttons(self, surface):
        W, H = surface.get_size()
        btns = [("REMATCH", 0), ("LEAVE", 1)]
        f = pygame.font.SysFont("consolas,monospace", 22, bold=True)
        bx = W // 2 - 250
        by = H - 130
        for label, idx in btns:
            selected = (idx == self._sel)
            color_bg = (60, 60, 90) if not selected else (90, 100, 160)
            color_fg = (240, 240, 255) if selected else (180, 180, 200)
            border  = (210, 220, 255) if selected else (90, 90, 120)
            pygame.draw.rect(surface, color_bg, (bx, by, 220, 56), border_radius=8)
            pygame.draw.rect(surface, border,  (bx, by, 220, 56), 2, border_radius=8)
            t = f.render(label, True, color_fg)
            surface.blit(t, (bx + 110 - t.get_width() // 2,
                              by + 28 - t.get_height() // 2))
            bx += 280

    def _draw_disconnect_overlay(self, surface):
        W, H = surface.get_size()
        ov = pygame.Surface((W, H), pygame.SRCALPHA)
        ov.fill((0, 0, 0, 180))
        surface.blit(ov, (0, 0))
        f1 = pygame.font.SysFont("consolas,monospace", 38, bold=True)
        f2 = pygame.font.SysFont("consolas,monospace", 22)
        t1 = f1.render("Conexão Perdida", True, (255, 80, 80))
        t2 = f2.render("Pressione ENTER ou ESC para voltar ao menu",
                        True, (220, 220, 220))
        surface.blit(t1, (W // 2 - t1.get_width() // 2, H // 2 - 40))
        surface.blit(t2, (W // 2 - t2.get_width() // 2, H // 2 + 20))
