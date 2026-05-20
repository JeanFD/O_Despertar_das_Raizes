# entities/remote_projectile.py
import pygame
from entities.entity import Entity

LERP_SPEED = 22.0


class RemoteProjectile(Entity):
    """
    Representação visual de um projétil sincronizado via rede.

    Replica a aparência do Projectile (mesmo desenho) mas não
    participa do CombatSystem (sem Hitbox ativa) nem do PhysicsSystem.
    O host é autoritativo: posição e direção vêm de apply_state().
    """

    net_remote = True

    def __init__(self, game, x: float, y: float, direction: int, net_id: int):
        super().__init__(game, x, y)
        self.direction = direction
        self.net_id = net_id
        self._target_x = float(x)
        self._target_y = float(y)

    def apply_state(self, s: dict):
        self._target_x = float(s.get("x", self._target_x))
        self._target_y = float(s.get("y", self._target_y))
        self.direction = int(s.get("d", self.direction))

    def update(self, dt: float):
        alpha = min(1.0, LERP_SPEED * dt)
        self.pos.x += (self._target_x - self.pos.x) * alpha
        self.pos.y += (self._target_y - self.pos.y) * alpha

    def draw(self, surface, camera):
        sx = int(self.pos.x - camera.offset.x)
        sy = int(self.pos.y - camera.offset.y) - 6
        pygame.draw.circle(surface, (255, 200, 50), (sx, sy), 6)
        tail_x = sx - self.direction * 14
        pygame.draw.line(surface, (255, 120, 0), (sx, sy), (tail_x, sy), 3)
