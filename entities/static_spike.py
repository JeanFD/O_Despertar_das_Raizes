import pygame
from entities.entity import Entity
from components.hitbox import Hitbox

class StaticSpike(Entity):
    """Espinho fixo no chão. Não se move, não tem PhysicsBody, só dá dano no contato."""

    def __init__(self, game, x, y, damage=15, knockback=400, knockback_y=300):
        super().__init__(game, x, y)

        self.hb = self.add(Hitbox, -16, -16, 32, 16,
                            damage=damage, team="enemy",
                            knockback=knockback, knockback_y=knockback_y)
        self.hb.active = True

    def update(self, dt):
        self.hb.tick(dt)

    def draw(self, surface, camera):
        rect = pygame.Rect(self.pos.x - 16, self.pos.y - 16, 32, 16)
        dr = camera.apply_rect(rect)
        pygame.draw.rect(surface, (180, 50, 50), dr)