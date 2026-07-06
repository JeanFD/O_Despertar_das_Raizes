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

        self.image = game.assets.image("assets/images/entities/static_spike.png")

    def update(self, dt):
        self.hb.tick(dt)

    def draw(self, surface, camera):
        img_rect = self.image.get_rect(midbottom=(self.pos.x, self.pos.y))
        dr = camera.apply_rect(img_rect)
        surface.blit(self.image, dr)