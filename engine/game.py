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

        #Empilha o estado inicial.
        from states.gameplay import GameplayState
        self.states.push(GameplayState(self))

        

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
            pygame.display.flip()

        pygame.quit()
        sys.exit()