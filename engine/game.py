import pygame
import sys
from settings import SCREEN_W, SCREEN_H, TITLE, FPS

class Game:
    def __init__(self):
        pygame.init()
        pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)

        self.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
        pygame.display.set_caption(TITLE)
        self.clock = pygame.time.Clock()
        self.running = True

        from engine.asset_manager import AssetManager
        self.assets = AssetManager()

        from engine.event_bus import EventBus
        self.events = EventBus()

        from engine.state_machine import StateMachine
        self.states = StateMachine(self)

        from engine.settings_manager import SettingsManager
        self.settings = SettingsManager()

        self._fps_font = pygame.font.SysFont("consolas,monospace", 16)

        # Aplica o modo de tela conforme a setting persistida ANTES de
        # empilhar o menu, para abrir já no modo correto sem flicker.
        self.apply_fullscreen()

        from states.main_menu import MainMenu
        self.states.push(MainMenu(self))

    def apply_fullscreen(self):
        """(Re)cria a janela conforme a setting 'fullscreen'. Único ponto
        que controla modo de tela e visibilidade do cursor — chamado no
        startup e pelo SettingsState ao togglear."""
        is_full = self.settings.get("fullscreen")
        flags = pygame.FULLSCREEN if is_full else 0
        self.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H), flags)
        # Em fullscreen o cursor sobre a área de jogo distrai e não tem
        # função; em janela mantemos visível para arrastar/redimensionar.
        pygame.mouse.set_visible(not is_full)


        

        # engine/game.py — no __init__
        

    def run(self):
        # Limite de dt por frame. Quando a janela perde foco / muda de tela /
        # o SO suspende o processo, clock.tick devolve um delta enorme na 1ª
        # frame após o resume — isso bastava para os players atravessarem o
        # chão (AABB simples sem sweep) e cair no ring-out. Capando em ~33 ms
        # garantimos que cada passo de física move <1 tile e a colisão pega.
        MAX_FRAME_DT = 1.0 / 30.0

        while self.running:
            dt = self.clock.tick(FPS) / 1000.0
            if dt > MAX_FRAME_DT:
                dt = MAX_FRAME_DT

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                self.states.handle_event(event)

            self.states.update(dt)
            self.screen.fill((20, 20, 30))
            self.states.draw(self.screen)

            if self.settings.get("show_fps"):
                fps_surf = self._fps_font.render(
                    f"FPS: {self.clock.get_fps():.0f}", True, (200, 200, 200)
                )
                self.screen.blit(fps_surf, (8, 8))

            pygame.display.flip()

        pygame.quit()
        sys.exit()