import pygame
from entities.entity import Entity
from components.physics_body import PhysicsBody

MOVE_SPEED = 220
JUMP_FORCE = -600

class Player(Entity):
    def __init__(self, game, x, y):
        super().__init__(game, x, y)
        self.body = self.add(PhysicsBody, 32, 48)

    def handle_input(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_SPACE and self.body.on_ground:
                self.vel.y = JUMP_FORCE

    def update_input(self, keys):
        self.vel.x = 0
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            self.vel.x = MOVE_SPEED
        if keys[pygame.K_LEFT] or keys[pygame.K_a]:
            self.vel.x = -MOVE_SPEED

    def draw(self, surface):
        pygame.draw.rect(surface, (255,255,255), self.body.rect)