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

        from states.main_menu import MainMenu
        self.states.push(MainMenu(self))


        

        # engine/game.py — no __init__
        

    def run(self):
        while self.running:
            dt = self.clock.tick(FPS) / 1000.0

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