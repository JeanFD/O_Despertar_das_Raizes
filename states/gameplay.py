import pygame
from settings import SCREEN_W, SCREEN_H
from states.base_state import BaseState
from entities.player import Player

GRAVITY = 1800

class GameplayState(BaseState):
    def on_enter(self):
        self.player = Player(self.game, SCREEN_W //2, SCREEN_H // 2)
        self.ground_y = SCREEN_H - 80

    def handle_event(self, event):
        self.player.handle_input(event)

    def update(self, dt):
        keys = pygame.key.get_pressed()
        self.player.update_input(keys)

        self.player.vel.y += GRAVITY * dt
        self.player.pos.x += self.player.vel.x * dt
        self.player.pos.y += self.player.vel.y * dt

        body = self.player.body
        if self.player.pos.y + body.height >= self.ground_y:
            self.player.pos.y = self.ground_y - body.height
            self.player.vel.y = 0
            body.on_ground = True
        else:
            body.on_ground = False

    def draw(self, surface):
        pygame.draw.rect(surface, (90, 60, 30), (0, self.ground_y, SCREEN_W, SCREEN_H - self.ground_y))
        self.player.draw(surface)
