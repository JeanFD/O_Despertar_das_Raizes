import pygame
from entities.entity import Entity
from components.physics_body import PhysicsBody 
from components.health import Health
from components.hitbox import Hitbox

class Crawler(Entity):
    def __init__(self, game, x, y):
        super().__init__(game, x, y)
        self.body = self.add(PhysicsBody, 32, 24)
        self.hp = self.add(Health, 30)
        self.touch_hb = self.add(Hitbox, -16, -24, 32, 24, damage=10, team="enemy", knockback=200)
        self.touch_hb.active = True
        self.dir = -1
        self.vel.x = self.dir * 80

    def update(self, dt):
        self.hp.update(dt)
        self.touch_hb.tick(dt)

        if self.body.on_wall:
            self.dir *= -1
        self.vel.x = self.dir * 80

    def draw(self, surface, camera):
        dr = camera.apply_rect(self.body.rect)
        pygame.draw.rect(surface, (200, 80, 80), dr)