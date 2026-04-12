import pygame
from settings import SCREEN_W, SCREEN_H
from states.base_state import BaseState
from entities.player import Player
from systems.physics_system import PhysicsSystem

GRAVITY = 1800

class GameplayState(BaseState):
    def on_enter(self):
        self.player = Player(self.game, SCREEN_W //2, SCREEN_H // 2)
        self.ground_y = SCREEN_H - 80
        self.entities = [self.player]
        self.physics = PhysicsSystem(self.ground_y)

    def handle_event(self, event):
        self.player.handle_input(event)

    def update(self, dt):
        keys = pygame.key.get_pressed()
        self.player.update_input(keys)
        self.physics.update(self.entities, dt)
        
    def draw(self, surface):
        pygame.draw.rect(surface, (90, 60, 30), (0, self.ground_y, SCREEN_W, SCREEN_H - self.ground_y))
        for e in self.entities:
            e.draw(surface)