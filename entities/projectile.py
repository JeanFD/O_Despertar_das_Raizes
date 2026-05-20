import pygame
from entities.entity import Entity
from components.hitbox import Hitbox

RANGED_CD = 0.7

class Projectile(Entity):
    SPEED = 400
    LIFETIME = 1.5
    DAMAGE = 8

    # ID monotônico para tracking via rede (host → cliente).
    _next_id = 1

    def __init__(self, game, x, y, direction, team, net_id: int | None = None):
        super().__init__(game, x, y)
        self.direction = direction
        self.lifetime = self.LIFETIME
        self.team = team

        # Cada projétil tem um id estável para o cliente correlacionar
        # snapshots consecutivos. Se vier explícito (replay), usa esse.
        if net_id is None:
            self.net_id = Projectile._next_id
            Projectile._next_id += 1
        else:
            self.net_id = net_id

        self.hb = self.add(Hitbox, 0, -6, 12, 12, damage=self.DAMAGE, team=team, knockback=150)
        self.hb.active = True

    def to_net(self) -> dict:
        """Estado mínimo para sincronizar com o cliente."""
        return {
            "id": self.net_id,
            "x":  self.pos.x,
            "y":  self.pos.y,
            "d":  self.direction,
        }

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

        # Debug: hitbox do projétil
        if self.hb.active:
            r = camera.apply_rect(self.hb.rect)
            pygame.draw.rect(surface, (255, 60, 60), r, 1)
