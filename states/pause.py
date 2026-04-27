import pygame
from states.base_state import BaseState
from ui.menu_ui import (
    draw_panel, draw_title, draw_menu_items,
    draw_hint_bar, C_HIGHLIGHT, C_TEXT, C_ACCENT
)

class PauseState(BaseState):

    def on_enter(self):
        self.selected = 0
        self.items = [
            "Continuar",
            "Salvar Jogo",
            "Configuracoes",
            "Menu Principal",
        ]

        self._bg_snapshot = self.game.screen.copy()

    def handle_event(self, event):
        if event.type != pygame.KEYDOWN:
            return
        
        if event.key == pygame.K_ESCAPE:
            self.game.states.pop()

        elif event.key in (pygame.K_UP, pygame.K_w):
            self.selected = (self.selected - 1) % len(self.items)

        elif event.key in (pygame.K_DOWN, pygame.K_s):
            self.selected = (self.selected + 1) % len(self.items)

        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            self._confirm()

    def _confirm(self):
        choice = self.items[self.selected]

        if choice == "Continuar":
            self.game.states.pop()

        elif choice == "Salvar Jogo":
            from states.save_menu import SaveMenu
            self.game.states.push(SaveMenu(self.game, mode = "save"))

        elif choice == "Configuracoes":
            from states.settings_state import SettingsState
            self.game.states.push(SettingsState(self.game))

        elif choice == "Menu Principal":
            self._back_to_menu()

    def _back_to_menu(self):
        self.game.states.pop()
        from states.main_menu import MainMenu
        self.game.states.change(MainMenu(self.game))

    def update(self, dt):
        pass

    def draw(self, surface):
        sw, sh = surface.get_size()

        surface.blit(self._bg_snapshot, (0, 0))

        overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        surface.blit(overlay, (0, 0))

        panel_w, panel_h = 320, 300
        panel_rect = pygame.Rect(sw // 2 - panel_w // 2, sh // 2 - panel_h // 2, panel_w, panel_h)
        draw_panel(surface, panel_rect, alpha=230)

        draw_title(surface, "PAUSE", panel_rect.top + 20, size=32)

        draw_menu_items(surface, self.items, self.selected, x=0, y=panel_rect.top + 80, spacing=44, size=20)

        draw_hint_bar(surface, "ESC = retomar          ENTER = selecionar")

        