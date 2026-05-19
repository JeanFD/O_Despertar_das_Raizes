import pygame
from entities.entity import Entity
from components.hitbox import Hitbox

RANGED_CD = 0.7

class Projectile(Entity):
    SPEED = 400
    LIFETIME = 1.5
    DAMAGE = 15

    def __init__(self, game, x, y, direction, team):
        super().__init__(game, x, y)
        self.direction = direction
        self.lifetime = self.LIFETIME
        self.team = team

        self.hb = self.add(Hitbox, 0, -6, 12, 12, damage=self.DAMAGE, team=team, knockback=150)
        self.hb.active = True

    def update(self, dt):
        self.lifetime -= dt
        self.pos.x += self.direction * self.SPEED * dt
        if self.lifetime <= 0:
            self.alive = False

    def draw(self, surface, camera):
        sx = int(self.pos.x - camera.offset.x)
        sy = int(self.pos.y - camera.offset.y) - 6
        pygame.draw.circle(surface, (255, 200, 50), (sx, sy), 6)
        tail_x = sx - self.direction * 14
        pygame.draw.line(surface, (255, 120, 0), (sx, sy), (tail_x, sy), 3)
