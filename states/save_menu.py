# states/save_menu.py
"""
Menu de saves — funciona em dois modos:
  mode="save"  → escolher slot para salvar (vindo do pause)
  mode="load"  → escolher slot para carregar (vindo do menu)

Mostra até 4 slots com preview: posição, habilidades, HP, data.
"""
import pygame
import json
import os
from datetime import datetime
from states.base_state import BaseState
from ui.menu_ui import (
    draw_gradient_bg, draw_panel, draw_title, draw_hint_bar,
    C_TEXT, C_TEXT_DIM, C_HIGHLIGHT, C_HIGHLIGHT_BG,
    C_PANEL, C_PANEL_EDGE, C_ACCENT, C_DANGER, C_SUCCESS, C_BAR_BG
)

SAVE_DIR   = "data/saves"
NUM_SLOTS  = 4


def _load_slot_info(slot: int) -> dict | None:
    """Lê o JSON de um slot sem afetar o jogo."""
    path = f"{SAVE_DIR}/slot_{slot}.json"
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


class SaveMenu(BaseState):

    def __init__(self, game, mode: str = "load"):
        super().__init__(game)
        self.mode = mode              # "save" ou "load"

    def on_enter(self):
        self.selected     = 0
        self.confirm_del  = -1        # slot aguardando confirmação de delete
        self.message      = ""
        self.message_timer = 0.0
        self._refresh_slots()

    def _refresh_slots(self):
        os.makedirs(SAVE_DIR, exist_ok=True)
        self.slots = []
        for i in range(NUM_SLOTS):
            info = _load_slot_info(i)
            self.slots.append(info)

    def handle_event(self, event):
        if event.type != pygame.KEYDOWN:
            return

        # Se esperando confirmação de delete
        if self.confirm_del >= 0:
            if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                self._delete_slot(self.confirm_del)
                self.confirm_del = -1
            else:
                self.confirm_del = -1
                self.message = ""
            return

        if event.key == pygame.K_ESCAPE:
            self.game.states.pop()

        elif event.key in (pygame.K_UP, pygame.K_w):
            self.selected = (self.selected - 1) % (NUM_SLOTS + 1)  # +1 pro "Voltar"

        elif event.key in (pygame.K_DOWN, pygame.K_s):
            self.selected = (self.selected + 1) % (NUM_SLOTS + 1)

        elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
            if self.selected == NUM_SLOTS:
                # "Voltar"
                self.game.states.pop()
            else:
                self._action_slot(self.selected)

        elif event.key == pygame.K_DELETE or event.key == pygame.K_BACKSPACE:
            if self.selected < NUM_SLOTS and self.slots[self.selected]:
                self.confirm_del = self.selected
                self.message = f"ENTER para apagar slot {self.selected + 1}, outra tecla cancela"

    def _action_slot(self, slot: int):
        if self.mode == "save":
            self._save_to_slot(slot)
        else:
            self._load_from_slot(slot)

    def _save_to_slot(self, slot: int):
        """Salva o estado atual do gameplay no slot."""
        # Navega a stack para encontrar o PlayState
        play = self._find_play_state()
        if not play:
            self._show_message("Nenhum jogo em andamento!")
            return

        player = play.player
        data = {
            "position":   [player.pos.x, player.pos.y],
            "abilities":  dict(player.abilities),
            "health":     player.hp.current if hasattr(player, "hp") else 100,
            "state":      getattr(player, "state", "idle"),
            "saved_at":   datetime.now().strftime("%d/%m/%Y %H:%M"),
        }

        os.makedirs(SAVE_DIR, exist_ok=True)
        path = f"{SAVE_DIR}/slot_{slot}.json"
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

        # Atualiza settings com último slot usado
        if hasattr(self.game, "settings"):
            self.game.settings.set("last_save_slot", slot)
            self.game.settings.save()

        self._refresh_slots()
        self._show_message(f"Salvo no slot {slot + 1}!")

    def _load_from_slot(self, slot: int):
        """Carrega o save e inicia o gameplay."""
        info = self.slots[slot]
        if not info:
            self._show_message("Slot vazio!")
            return

        # Volta até o menu e inicia gameplay com dados do save
        from states.gameplay import GameplayState

        play_state = GameplayState(self.game)
        play_state.load_data = info     # GameplayState vai ler isso no on_enter

        # Limpa a stack inteira e coloca o gameplay
        while self.game.states._stack:
            self.game.states.pop()
        self.game.states.push(play_state)

    def _delete_slot(self, slot: int):
        path = f"{SAVE_DIR}/slot_{slot}.json"
        if os.path.exists(path):
            os.remove(path)
        self._refresh_slots()
        self._show_message(f"Slot {slot + 1} apagado.")

    def _find_play_state(self):
        for state in self.game.states._stack:
            if type(state).__name__ in ("PlayState", "GameplayState"):
                return state
        return None

    def _show_message(self, msg: str):
        self.message = msg
        self.message_timer = 2.5

    def update(self, dt):
        if self.message_timer > 0:
            self.message_timer -= dt
            if self.message_timer <= 0:
                self.message = ""

    def draw(self, surface):
        sw, sh = surface.get_size()
        draw_gradient_bg(surface)

        # Título
        title = "SALVAR JOGO" if self.mode == "save" else "CARREGAR JOGO"
        draw_title(surface, title, 30, size=30)

        # Slots
        slot_w, slot_h = 460, 80
        start_y = 90
        spacing = 90

        for i in range(NUM_SLOTS):
            x = sw // 2 - slot_w // 2
            y = start_y + i * spacing
            is_sel = (i == self.selected)
            info   = self.slots[i]

            self._draw_slot_card(surface, x, y, slot_w, slot_h,
                                  i, info, is_sel)

        # Botão "Voltar"
        back_y  = start_y + NUM_SLOTS * spacing + 10
        is_back = (self.selected == NUM_SLOTS)
        font    = pygame.font.SysFont("consolas,monospace", 20)
        color   = C_ACCENT if is_back else C_TEXT_DIM
        txt     = font.render("< Voltar", True, color)
        surface.blit(txt, (sw // 2 - txt.get_width() // 2, back_y))

        if is_back:
            import math
            t = pygame.time.get_ticks() / 400
            ox = int(math.sin(t) * 4)
            arrow = font.render(">", True, C_ACCENT)
            surface.blit(arrow, (sw // 2 - txt.get_width() // 2 - 24 + ox, back_y))

        # Mensagem temporária
        if self.message:
            msg_font = pygame.font.SysFont("consolas,monospace", 18)
            msg_surf = msg_font.render(self.message, True, C_ACCENT)
            surface.blit(msg_surf, (sw // 2 - msg_surf.get_width() // 2, sh - 60))

        # Dicas
        if self.confirm_del >= 0:
            hints = "ENTER = confirmar    qualquer outra = cancelar"
        else:
            hints = "ENTER = selecionar    DEL = apagar    ESC = voltar"
        draw_hint_bar(surface, hints)

    def _draw_slot_card(self, surface, x, y, w, h,
                         slot_num, info, selected):
        """Desenha um card de slot individual."""
        rect = pygame.Rect(x, y, w, h)

        # Fundo do card
        bg_color = C_HIGHLIGHT_BG if selected else C_PANEL
        edge_color = C_HIGHLIGHT if selected else C_PANEL_EDGE

        card = pygame.Surface((w, h), pygame.SRCALPHA)
        card.fill((*bg_color, 220))
        pygame.draw.rect(card, (*edge_color, 220), (0, 0, w, h), 2, border_radius=6)
        surface.blit(card, (x, y))

        # Seta de seleção
        if selected:
            import math
            t  = pygame.time.get_ticks() / 400
            ox = int(math.sin(t) * 4)
            arrow_font = pygame.font.SysFont("consolas,monospace", 22)
            arrow = arrow_font.render(">", True, C_ACCENT)
            surface.blit(arrow, (x - 24 + ox, y + h // 2 - 11))

        font_title = pygame.font.SysFont("consolas,monospace", 18, bold=True)
        font_info  = pygame.font.SysFont("consolas,monospace", 14)

        if info:
            # Slot com dados
            color = C_TEXT if selected else C_TEXT_DIM

            # Título do slot
            title = font_title.render(f"Slot {slot_num + 1}", True, color)
            surface.blit(title, (x + 16, y + 10))

            # Data do save
            saved_at = info.get("saved_at", "???")
            date_surf = font_info.render(saved_at, True, C_TEXT_DIM)
            surface.blit(date_surf, (x + w - date_surf.get_width() - 16, y + 12))

            # Posição
            pos = info.get("position", [0, 0])
            pos_txt = font_info.render(
                f"Pos: ({pos[0]:.0f}, {pos[1]:.0f})", True, C_TEXT_DIM)
            surface.blit(pos_txt, (x + 16, y + 36))

            # HP
            hp = info.get("health", 0)
            hp_txt = font_info.render(f"HP: {hp}", True, C_TEXT_DIM)
            surface.blit(hp_txt, (x + 200, y + 36))

            # Habilidades como ícones
            abilities = info.get("abilities", {})
            icon_x = x + 16
            icon_y = y + 56
            for name, unlocked in abilities.items():
                col = C_SUCCESS if unlocked else (50, 45, 65)
                pygame.draw.rect(surface, col,
                                 (icon_x, icon_y, 14, 14),
                                 0 if unlocked else 1, border_radius=2)
                icon_x += 20

        else:
            # Slot vazio
            empty_color = C_TEXT_DIM
            title = font_title.render(f"Slot {slot_num + 1}", True, empty_color)
            surface.blit(title, (x + 16, y + 10))

            empty = font_info.render("- vazio -", True, (60, 55, 80))
            surface.blit(empty, (x + 16, y + 38))
