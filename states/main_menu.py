import pygame
import sys
from states.base_state import BaseState
from ui.menu_ui import (
    draw_gradient_bg, draw_title, draw_menu_items,
    draw_hint_bar, draw_particles, C_TEXT_DIM
)

class MainMenu(BaseState):
    def on_enter(self):
        self.selected = 0
        self.tick = 0

        self.has_save = self._check_saves()

        self.items = [
            "Novo Jogo",
            "Continuar",
            "Multiplayer",
            "Configurações",
            "Sair",
        ]
    
    def _check_saves(self) -> bool:
        import os
        save_dir = "data/saves"
        if not os.path.exists(save_dir):
            return False
        return any(f.startswith("slot_") and f.endswith(".json") for f in os.listdir(save_dir))
    
    def handle_event(self, event):
        if event.type != pygame.KEYDOWN:
            return

        if event.key in (pygame.K_UP, pygame.K_w):
            self.selected = (self.selected - 1) % len(self.items)

        elif event.key in (pygame.K_DOWN, pygame.K_s):
            self.selected = (self.selected + 1) % len(self.items)

        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            self._confirm()

        elif event.key == pygame.K_ESCAPE:
            pygame.quit()
            sys.exit()

    def _confirm(self):
        choice = self.items[self.selected]

        if choice == "Novo Jogo":
            self._start_new_game()
        
        elif choice == "Continuar":
            if self.has_save:
                self._open_save_menu(mode="load")

        elif choice == "Multiplayer":
            self._open_multiplayer()

        elif choice == "Configurações":
            self._open_settings()

        elif choice == "Sair":
            pygame.quit()
            sys.exit()

    def _start_new_game(self):
        from states.gameplay import GameplayState
        self.game.states.change(GameplayState(self.game))

    def _open_save_menu(self, mode="load"):
        from states.save_menu import SaveMenu
        self.game.states.push(SaveMenu(self.game, mode=mode))

    def _open_multiplayer(self):
        from states.multiplayer_menu import MultiplayerMenu
        self.game.states.push(MultiplayerMenu(self.game))

    def _open_settings(self):
        from states.settings_state import SettingsState
        self.game.states.push(SettingsState(self.game))

    def update(self, dt):
        self.tick += 1

    def draw(self, surface):
        draw_gradient_bg(surface)
        draw_particles(surface, self.tick)

        sw, sh = surface.get_size()

        draw_title(surface, "METROIDVANIA", sh // 6, size=48)

        font_sub = pygame.font.SysFont("consolas,monospace", 14)
        sub = font_sub.render("Um tutorial que funciona de verdade", True, C_TEXT_DIM)
        surface.blit(sub, (sw // 2 - sub.get_width() // 2, sh // 6 + 56))

        from ui.menu_ui import C_HIGHLIGHT, C_TEXT
        colors = []
        for i, item in enumerate(self.items):
            if item == "Continuar" and not self.has_save:
                colors.append(C_TEXT_DIM)
            elif i == self.selected:
                colors.append(C_HIGHLIGHT)
            else:
                colors.append(C_TEXT)

        menu_y = sh // 2 - 40
        draw_menu_items(surface, self.items, self.selected, x=0, y=menu_y, spacing=48, size=24, colors=colors)

        draw_hint_bar(surface, "UP/DOWN = navegar   ENTER = selecionar   ESC = sair") 
