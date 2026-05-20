import pygame
from states.base_state import BaseState
from ui.menu_ui import (
    draw_panel, draw_title, draw_menu_items,
    draw_hint_bar, C_DANGER,
)


class RespawnState(BaseState):
    """Tela de game over com opções de renascer ou voltar ao menu.

    Disparada pelo GameplayState quando o player morre. Empilhada por
    cima do gameplay; renderiza um snapshot da última frame como fundo
    escurecido para preservar o contexto visual do que matou o jogador.

    Os callbacks (on_respawn, on_quit) são fornecidos pelo state que
    empilhou, mantendo a tela agnóstica do modo de jogo — qualquer
    estado pode reusar (single, multiplayer co-op, etc.).
    """

    def __init__(self, game, on_respawn, on_quit):
        super().__init__(game)
        self._on_respawn = on_respawn
        self._on_quit = on_quit

    def on_enter(self):
        self.selected = 0
        self.items = ["Renascer", "Menu Principal"]
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
        if choice == "Renascer":
            self.game.states.pop()
            self._on_respawn()
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

        # Pulso suave no título para chamar atenção sem ser irritante.
        import math
        pulse = 30 + int(20 * (0.5 + 0.5 * math.sin(self._t * 3)))
        color = (min(255, C_DANGER[0]),
                 max(0, C_DANGER[1] - pulse // 4),
                 max(0, C_DANGER[2] - pulse // 4))
        draw_title(surface, "VOCÊ MORREU", panel_rect.top + 28, size=34, color=color)

        draw_menu_items(
            surface, self.items, self.selected,
            x=0, y=panel_rect.top + 120, spacing=44, size=20,
        )

        draw_hint_bar(surface, "ENTER = confirmar")
