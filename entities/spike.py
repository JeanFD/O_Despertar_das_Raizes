import pygame
from entities.entity import Entity
from components.physics_body import PhysicsBody
from components.hitbox import Hitbox
from components.animation import AnimationController

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

        sheet = game.assets.image("assets/images/entities/spike_walk_sheet.png")
        self.anim = AnimationController(self, sheet, frame_w=64, frame_h=24, fps=6)
        self.anim.add("walk", row=0, start=0, end=1)
        self.anim.play("walk")

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

        self.anim.play("walk", flip_x=(self.dir == -1))
        self.anim.update(dt)

    def draw(self, surface, camera):
        self.anim.draw(surface, self.pos, camera)