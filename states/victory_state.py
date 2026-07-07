import math
import pygame
from states.base_state import BaseState
from ui.menu_ui import (
    draw_panel, draw_title, draw_menu_items,
    draw_hint_bar, C_SUCCESS,
)


class VictoryState(BaseState):
    """Tela de vitória, disparada pelo GameplayState quando o espantalho morre.

    Empilhada por cima do gameplay (a state machine desenha a pilha inteira),
    usa um snapshot da última frame como fundo escurecido para preservar o
    contexto. Agnóstica do que causou a vitória — recebe os callbacks
    (on_replay, on_quit) de quem a empilhou, igual à RespawnState.
    """

    def __init__(self, game, on_replay, on_quit):
        super().__init__(game)
        self._on_replay = on_replay
        self._on_quit = on_quit

    def on_enter(self):
        self.selected = 0
        self.items = ["Jogar de Novo", "Menu Principal"]
        self._bg_snapshot = self.game.screen.copy()
        self._t = 0.0

    def handle_event(self, event):
        if event.type != pygame.KEYDOWN:
            return
        if event.key in (pygame.K_UP, pygame.K_w):
            self.selected = (self.selected - 1) % len(self.items)
        elif event.key in (pygame.K_DOWN, pygame.K_s):
            self.selected = (self.selected + 1) % len(self.items)
        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            self._confirm()

    def _confirm(self):
        choice = self.items[self.selected]
        if choice == "Jogar de Novo":
            self.game.states.pop()
            self._on_replay()
        elif choice == "Menu Principal":
            self.game.states.pop()
            self._on_quit()

    def update(self, dt):
        self._t += dt

    def draw(self, surface):
        sw, sh = surface.get_size()
        surface.blit(self._bg_snapshot, (0, 0))

        overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        surface.blit(overlay, (0, 0))

        panel_w, panel_h = 380, 260
        panel_rect = pygame.Rect(
            sw // 2 - panel_w // 2, sh // 2 - panel_h // 2,
            panel_w, panel_h,
        )
        draw_panel(surface, panel_rect, alpha=235)

        # Pulso suave no verde de vitória para dar vida ao título.
        pulse = int(30 * (0.5 + 0.5 * math.sin(self._t * 3)))
        color = (min(255, C_SUCCESS[0] + pulse),
                 min(255, C_SUCCESS[1] + pulse),
                 min(255, C_SUCCESS[2] + pulse))
        draw_title(surface, "VITÓRIA!", panel_rect.top + 28, size=38, color=color)

        draw_menu_items(
            surface, self.items, self.selected,
            x=0, y=panel_rect.top + 120, spacing=44, size=20,
        )

        draw_hint_bar(surface, "ENTER = confirmar")
