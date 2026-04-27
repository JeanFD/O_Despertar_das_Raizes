# states/settings_state.py
"""
Tela de configurações — acessível tanto do menu principal quanto do pause.
É empilhada (push), então ao sair (pop) volta para onde veio.
"""
import pygame
from states.base_state import BaseState
from ui.menu_ui import (
    draw_gradient_bg, draw_panel, draw_title,
    draw_slider, draw_toggle, draw_hint_bar,
    C_HIGHLIGHT, C_TEXT, C_TEXT_DIM, C_ACCENT
)


# Cada item é: (chave, tipo, rótulo)
# tipo: "slider" (0.0-1.0) | "toggle" (bool) | "action"
SETTINGS_ITEMS = [
    ("master_volume", "slider",  "Volume Geral"),
    ("music_volume",  "slider",  "Musica"),
    ("sfx_volume",    "slider",  "Efeitos"),
    ("fullscreen",    "toggle",  "Tela Cheia"),
    ("screen_shake",  "toggle",  "Screen Shake"),
    ("show_fps",      "toggle",  "Mostrar FPS"),
    ("_back",         "action",  "< Voltar"),
]


class SettingsState(BaseState):

    def on_enter(self):
        self.selected = 0

        # Se o Game ainda não tem SettingsManager, cria um
        if not hasattr(self.game, "settings"):
            from engine.settings_manager import SettingsManager
            self.game.settings = SettingsManager()

    def on_exit(self):
        # Salva ao sair
        if hasattr(self.game, "settings"):
            self.game.settings.save()
            self.game.settings.apply_audio()

    def handle_event(self, event):
        if event.type != pygame.KEYDOWN:
            return

        if event.key == pygame.K_ESCAPE:
            self.game.states.pop()
            return

        if event.key in (pygame.K_UP, pygame.K_w):
            self.selected = (self.selected - 1) % len(SETTINGS_ITEMS)

        elif event.key in (pygame.K_DOWN, pygame.K_s):
            self.selected = (self.selected + 1) % len(SETTINGS_ITEMS)

        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            self._confirm()

        elif event.key in (pygame.K_LEFT, pygame.K_a):
            self._adjust(-0.1)

        elif event.key in (pygame.K_RIGHT, pygame.K_d):
            self._adjust(0.1)

    def _confirm(self):
        key, kind, _ = SETTINGS_ITEMS[self.selected]

        if key == "_back":
            self.game.states.pop()

        elif kind == "toggle":
            self.game.settings.toggle(key)
            # Aplicar tela cheia imediatamente
            if key == "fullscreen":
                self._apply_fullscreen()

    def _adjust(self, step: float):
        key, kind, _ = SETTINGS_ITEMS[self.selected]
        if kind == "slider":
            self.game.settings.cycle(key, step, 0.0, 1.0)
        elif kind == "toggle":
            self.game.settings.toggle(key)
            if key == "fullscreen":
                self._apply_fullscreen()

    def _apply_fullscreen(self):
        from settings import SCREEN_W, SCREEN_H
        is_full = self.game.settings.get("fullscreen")
        if is_full:
            self.game.screen = pygame.display.set_mode(
                (SCREEN_W, SCREEN_H), pygame.FULLSCREEN)
        else:
            self.game.screen = pygame.display.set_mode(
                (SCREEN_W, SCREEN_H))

    def update(self, dt):
        pass

    def draw(self, surface):
        sw, sh = surface.get_size()

        # Fundo
        draw_gradient_bg(surface)

        # Painel
        panel_w, panel_h = 500, 420
        panel_rect = pygame.Rect(sw // 2 - panel_w // 2,
                                  sh // 2 - panel_h // 2,
                                  panel_w, panel_h)
        draw_panel(surface, panel_rect)

        # Título
        draw_title(surface, "CONFIGURACOES", panel_rect.top + 16, size=28)

        # Items
        item_x = panel_rect.left + 40
        item_y = panel_rect.top + 70
        spacing = 44

        settings = self.game.settings

        for i, (key, kind, label) in enumerate(SETTINGS_ITEMS):
            y = item_y + i * spacing
            is_sel = (i == self.selected)

            if kind == "slider":
                draw_slider(surface, item_x, y, panel_w - 80,
                            settings.get(key), label, selected=is_sel)

            elif kind == "toggle":
                draw_toggle(surface, item_x, y,
                            settings.get(key), label, selected=is_sel)

            elif kind == "action":
                font  = pygame.font.SysFont("consolas,monospace", 20)
                color = C_ACCENT if is_sel else C_TEXT_DIM
                txt   = font.render(label, True, color)
                surface.blit(txt, (item_x, y))

            # Seta de seleção
            if is_sel:
                import math
                t = pygame.time.get_ticks() / 400
                ox = int(math.sin(t) * 4)
                arrow_font = pygame.font.SysFont("consolas,monospace", 20)
                arrow = arrow_font.render(">", True, C_ACCENT)
                surface.blit(arrow, (item_x - 20 + ox, y))

        # Dicas
        key, kind, _ = SETTINGS_ITEMS[self.selected]
        if kind == "slider":
            hints = "LEFT/RIGHT = ajustar    ESC = voltar"
        elif kind == "toggle":
            hints = "ENTER = alternar    ESC = voltar"
        else:
            hints = "ENTER = confirmar    ESC = voltar"
        draw_hint_bar(surface, hints)
