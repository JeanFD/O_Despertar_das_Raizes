# states/credits_state.py
"""
Tela de creditos — acessivel pelo menu principal.
E empilhada (push), entao ao sair (pop) volta para o menu.
Os creditos rolam de baixo para cima automaticamente; UP/DOWN ajustam
a velocidade e ESC/ENTER voltam.
"""
import pygame
from states.base_state import BaseState
from ui.menu_ui import (
    draw_gradient_bg, draw_particles, draw_title, draw_hint_bar,
    C_TEXT, C_TEXT_DIM, C_ACCENT,
)


# Estrutura dos creditos. Cada bloco: (tipo, texto)
#   "role"  -> funcao/area (destaque)
#   "name"  -> pessoa responsavel
#   "gap"   -> espaco vertical
#   "head"  -> cabecalho de secao
CREDITS = [
    ("gap", 40),
    ("head", "UMA CRIACAO DE"),
    ("gap", 8),

    ("role", "Jean Ferreira Dias"),
    ("gap", 20),
    ("role", "Lara Domingos Viana"),
    ("gap", 56),

    ("head", "ENGINE E PROGRAMACAO"),
    ("gap", 8),
    ("role", "Game loop e state machine"),      ("name", "Jean Ferreira Dias"),
    ("role", "Habilidades"),                    ("name", "Jean Ferreira Dias"),
    ("role", "Camera e parallax"),              ("name", "Jean Ferreira Dias"),
    ("gap", 48),

    ("head", "NARRATIVA E DESIGN"),
    ("gap", 8),
    ("role", "Narrativa"),                      ("name", "Lara Domingos Viana"),
    ("role", "Balanceamento e progressao"),     ("name", "Lara Domingos Viana"),
    ("role", "Trilha e efeitos sonoros"),       ("name", "Lara Domingos Viana"),
    ("gap", 48),

    ("head", "MULTIPLAYER"),
    ("gap", 8),
    ("role", "Netcode UDP autoritativo"),       ("name", "Jean Ferreira Dias"),
    ("role", "Servidor dedicado (VPS)"),        ("name", "Jean Ferreira Dias"),
    ("gap", 48),

    ("head", "ARTE E ANIMACAO"),
    ("gap", 8),
    ("role", "Cenarios e ambientacao"),         ("name", "Lara Domingos Viana"),
    ("role", "Inimigos e criaturas"),           ("name", "Lara Domingos Viana"),
    ("gap", 48),

    ("head", "PROTAGONISTA"),
    ("gap", 8),
    ("role", "Player e controle"),              ("name", "Jean Ferreira Dias"),
    ("role", "Arte e animacao"),                ("name", "Jean Ferreira Dias"),
    ("gap", 48),

    ("head", "BOSS"),
    ("gap", 8),
    ("role", "Inteligencia do boss"),           ("name", "Lara Domingos Viana"),
    ("role", "Arte e animacao"),                ("name", "Lara Domingos Viana"),
    ("gap", 64),

    ("head", "O DESPERTAR DAS RAIZES"),
    ("gap", 8),
    ("name", "Obrigado por jogar!"),
    ("gap", 120),
]

SPEED_DEFAULT = 40.0   # pixels por segundo
SPEED_FAST = 160.0


class CreditsState(BaseState):

    def on_enter(self):
        self.scroll = 0.0
        self.tick = 0
        self.speed = SPEED_DEFAULT
        # Mesma trilha do menu. play_music e idempotente (ignora se ja tocando),
        # entao vindo do MainMenu a musica continua sem cortar.
        self.game.sound.play_music("assets/audio/music/menu_theme.mp3")
        self._build_lines()

    def _build_lines(self):
        """Renderiza cada bloco uma vez e mede a altura total."""
        self.font_head = pygame.font.SysFont("consolas,monospace", 16, bold=True)
        self.font_role = pygame.font.SysFont("consolas,monospace", 24, bold=True)
        self.font_name = pygame.font.SysFont("consolas,monospace", 18)

        self.lines = []   # (surface, altura_do_bloco)
        for kind, value in CREDITS:
            if kind == "gap":
                self.lines.append((None, value))
            elif kind == "head":
                surf = self.font_head.render(value, True, C_TEXT_DIM)
                self.lines.append((surf, 34))
            elif kind == "role":
                surf = self.font_role.render(value, True, C_ACCENT)
                self.lines.append((surf, 32))
            elif kind == "name":
                surf = self.font_name.render(value, True, C_TEXT)
                self.lines.append((surf, 28))

        self.total_h = sum(h for _, h in self.lines)

    def handle_event(self, event):
        if event.type != pygame.KEYDOWN:
            return
        if event.key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_SPACE):
            self.game.sound.play("menu_confirm")
            self.game.states.pop()

    def update(self, dt):
        self.tick += 1

        keys = pygame.key.get_pressed()
        self.speed = SPEED_FAST if (keys[pygame.K_DOWN] or keys[pygame.K_s]) else SPEED_DEFAULT
        if keys[pygame.K_UP] or keys[pygame.K_w]:
            self.speed = -SPEED_FAST

        self.scroll += self.speed * dt

        # Rola em loop: quando tudo passou pelo topo, reinicia
        sh = 720
        if self.scroll > self.total_h + sh:
            self.scroll = 0.0
        if self.scroll < 0:
            self.scroll = 0.0

    def draw(self, surface):
        draw_gradient_bg(surface)
        draw_particles(surface, self.tick)

        sw, sh = surface.get_size()

        # Titulo fixo no topo
        draw_title(surface, "CREDITOS", 30, size=36)

        # Area de rolagem (abaixo do titulo, acima da hint bar)
        clip_top = 90
        clip_bottom = sh - 45
        prev_clip = surface.get_clip()
        surface.set_clip(pygame.Rect(0, clip_top, sw, clip_bottom - clip_top))

        y = clip_bottom - self.scroll
        for surf, h in self.lines:
            if surf is not None:
                # so desenha o que estiver dentro da area visivel
                if clip_top - h < y < clip_bottom:
                    x = sw // 2 - surf.get_width() // 2
                    surface.blit(surf, (x, int(y)))
            y += h

        surface.set_clip(prev_clip)

        draw_hint_bar(surface, "DOWN = acelerar   UP = voltar   ESC = sair")
