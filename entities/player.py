# entities/player.py — substitua tudo
import pygame
from entities.entity import Entity
from components.physics_body import PhysicsBody
from components.animation import AnimationController

MOVE_SPEED = 220
JUMP_FORCE = -600

COYOTE_TIME = 0.10
JUMP_BUFFER = 0.10

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

        self.coyote_timer = 0.0
        self.jump_buffer = 0;0


    def handle_input(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_SPACE:
                self.jump_buffer = JUMP_BUFFER

    def update_input(self, keys):
        self.vel.x = 0
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            self.vel.x =  MOVE_SPEED
            self.facing = 1
        if keys[pygame.K_LEFT] or keys[pygame.K_a]:
            self.vel.x = -MOVE_SPEED
            self.facing = -1

    def update(self, dt):
        self._update_jump(dt)
        body = self.body
        if not body.on_ground:
            anim = "jump" if self.vel.y < 0 else "fall"
        elif abs(self.vel.x) > 10:
            anim = "run"
        else:
            anim = "idle"
        self.anim.play(anim, flip_x=(self.facing == -1))
        self.anim.update(dt)

    def _update_jump(self, dt):
        body = self.body
        # Atualiza coyote
        if body.on_ground:
            self.coyote_timer = COYOTE_TIME
        else:
            self.coyote_timer = max(0.0, self.coyote_timer - dt)
        # Atualiza buffer
        self.jump_buffer = max(0.0, self.jump_buffer - dt)

        # Se ambos estão ativos, pula
        if self.jump_buffer > 0 and self.coyote_timer > 0:
            self.vel.y       = JUMP_FORCE
            self.jump_buffer  = 0.0
            self.coyote_timer = 0.0

    def draw(self, surface, camera):
        self.anim.draw(surface, self.pos, camera)