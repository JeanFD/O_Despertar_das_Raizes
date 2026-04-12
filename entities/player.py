# entities/player.py — substitua tudo
import pygame
from entities.entity import Entity
from components.physics_body import PhysicsBody
from components.animation import AnimationController

MOVE_SPEED = 220
JUMP_FORCE = -600

class Player(Entity):
    def __init__(self, game, x, y):
        super().__init__(game, x, y)
        sheet     = game.assets.image("assets/images/sprites/player.png")
        self.body = self.add(PhysicsBody, 24, 40)
        self.anim = self.add(AnimationController, sheet, 48, 48, fps=12)

        self.anim.add("idle", 0, 0, 3)
        self.anim.add("run",  1, 0, 7)
        self.anim.add("jump", 2, 0, 0)
        self.anim.add("fall", 2, 1, 1)

        self.facing = 1

    def handle_input(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_SPACE and self.body.on_ground:
                self.vel.y = JUMP_FORCE

    def update_input(self, keys):
        self.vel.x = 0
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            self.vel.x =  MOVE_SPEED
            self.facing = 1
        if keys[pygame.K_LEFT] or keys[pygame.K_a]:
            self.vel.x = -MOVE_SPEED
            self.facing = -1

    def update(self, dt):
        # Decide qual animação tocar
        body = self.body
        if not body.on_ground:
            anim = "jump" if self.vel.y < 0 else "fall"
        elif abs(self.vel.x) > 10:
            anim = "run"
        else:
            anim = "idle"
        self.anim.play(anim, flip_x=(self.facing == -1))
        self.anim.update(dt)

    def draw(self, surface, camera):
        self.anim.draw(surface, self.pos, camera)