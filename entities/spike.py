import pygame
from entities.entity import Entity
from components.physics_body import PhysicsBody
from components.hitbox import Hitbox

class Spike(Entity):
    def __init__(self, game, x, y, x_min, x_max, speed=200):
        super().__init__(game, x, y)
        self.body  = self.add(PhysicsBody, 32, 16)
        self.hb    = self.add(Hitbox, -16, -16, 32, 16,
                              damage=15, team="enemy", knockback=400, knockback_y=300)
        self.hb.active = True

        self.x_min = x_min
        self.x_max = x_max
        self.speed = speed
        self.dir   = 1  # começa indo para a direita

    def update(self, dt):
        self.hb.tick(dt)

        if self.pos.x >= self.x_max:
            self.dir = -1
        elif self.pos.x <= self.x_min:
            self.dir = 1

        # inverte também se bater na parede
        if self.body.on_wall:
            self.dir *= -1

        self.vel.x = self.dir * self.speed

    def draw(self, surface, camera):
        dr = camera.apply_rect(self.body.rect)
        pygame.draw.rect(surface, (180, 50, 50), dr)  # vermelho escuro