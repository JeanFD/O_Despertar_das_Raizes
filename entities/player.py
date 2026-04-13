# entities/player.py — substitua tudo
import pygame
from entities.entity import Entity
from components.physics_body import PhysicsBody
from components.animation import AnimationController

MOVE_SPEED = 220
JUMP_FORCE = -600

COYOTE_TIME = 0.10
JUMP_BUFFER = 0.10

DASH_SPEED = 550
DASH_TIME  = 0.18
DASH_CD    = 0.80

ATTACK_TIME = 0.18

class Player(Entity):
    def __init__(self, game, x, y):
        super().__init__(game, x, y)
        
        from components.health import Health
        self.hp = self.add(Health, 100)

        from components.hitbox import Hitbox
        self.attack_hb = self.add(Hitbox, 20, -32, 26, 32, damage=20, team="player", knockback=250)

        self.attack_timer = 0.0

        sheet     = game.assets.image("assets/images/sprites/player.png")
        self.body = self.add(PhysicsBody, 24, 40)
        self.anim = self.add(AnimationController, sheet, 48, 48, fps=12)

        self.anim.add("idle", 0, 0, 3)
        self.anim.add("run",  1, 0, 7)
        self.anim.add("jump", 2, 0, 0)
        self.anim.add("fall", 2, 1, 1)

        self.facing = 1

        self.coyote_timer = 0.0
        self.jump_buffer = 0.0

        self.dash_timer = 0.0
        self.dash_cd    = 0.0

    def handle_input(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_SPACE:
                self.jump_buffer = JUMP_BUFFER

    def update_input(self, keys):
        if self.dash_timer > 0:
            return
        
        if keys[pygame.K_z] or keys[pygame.K_j]:
            if self.attack_timer <= 0:
                self.attack_timer = ATTACK_TIME
        
        self.vel.x = 0
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            self.vel.x =  MOVE_SPEED
            self.facing = 1
        if keys[pygame.K_LEFT] or keys[pygame.K_a]:
            self.vel.x = -MOVE_SPEED
            self.facing = -1
        if keys[pygame.K_LSHIFT] and self.dash_cd <= 0:
            self.dash_timer = DASH_TIME
            self.dash_cd    = DASH_CD
            self.vel.x      = self.facing * DASH_SPEED
            self.vel.y      = 0

    def update(self, dt):
        self.dash_timer = max(0.0, self.dash_timer - dt)
        self.dash_cd = max(0.0, self.dash_cd - dt)

        self.attack_timer = max(0.0, self.attack_timer - dt)
        self.attack_hb.active = self.attack_timer > 0

        self.attack_hb.offset.x = 20 if self.facing == 1 else -56

        self._update_jump(dt)
        self.hp.update(dt)
        body = self.body

        if body.on_wall and not body.on_ground and self.vel.y > 0:
            self.vel.y = min(self.vel.y, 90)

        if self.dash_timer > 0:
            self.vel.y = 0

      

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
        elif self.jump_buffer > 0  and body.on_wall and not body.on_ground:
            self.vel.y = JUMP_FORCE * 0.9
            self.vel.x = -body.on_wall * MOVE_SPEED * 1.2
            self.jump_buffer = 0.0

    def draw(self, surface, camera):
        self.anim.draw(surface, self.pos, camera)