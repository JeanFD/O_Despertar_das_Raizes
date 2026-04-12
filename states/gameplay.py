import pygame
from settings import SCREEN_W, SCREEN_H
from states.base_state import BaseState

GRAVITY = 1800
MOVE_SPEED = 220
JUMP_FORCE = -600

class GameplayState(BaseState):
    def on_enter(self):
        self.player_x = SCREEN_W // 2
        self.player_y = SCREEN_H //2
        self.player_vx = 0
        self.player_vy = 0
        self.player_w = 32
        self.player_h = 48
        self.on_ground = False
        self.ground_y = SCREEN_H - 80

    def handle_event(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_SPACE and self.on_ground:
                self.player_vy = JUMP_FORCE

    def update(self, dt):
        keys = pygame.key.get_pressed()
        self.player_vx = 0
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            self.player_vx = MOVE_SPEED
        if keys[pygame.K_LEFT] or keys[pygame.K_a]:
            self.player_vx = -MOVE_SPEED

        self.player_vy += GRAVITY * dt
        self.player_x += self.player_vx * dt
        self.player_y += self.player_vy * dt

        if self.player_y + self.player_h >= self.ground_y:
            self.player_y = self.ground_y - self.player_h
            self.player_vy = 0
            self.on_ground = True
        else:
            self.on_ground = False

    def draw(self, surface):
        pygame.draw.rect(surface, (90, 60, 30), (0, self.ground_y, SCREEN_W, SCREEN_H - self.ground_y))
        pygame.draw.rect(surface, (255, 255, 255), (self.player_x, self.player_y, self.player_w, self.player_h))
