# entities/boss.py
import pygame
from entities.entity import Entity
from components.physics_body import PhysicsBody
from components.health import Health
from components.hitbox import Hitbox

KEY_LEFT   = pygame.K_LEFT
KEY_RIGHT  = pygame.K_RIGHT
KEY_JUMP   = pygame.K_UP
KEY_ATTACK = pygame.K_KP0

BOSS_SPEED      = 160
BOSS_JUMP_FORCE = -520
BOSS_HP         = 300
BOSS_W          = 48
BOSS_H          = 64
ATTACK_CD       = 0.55
COYOTE_TIME     = 0.08


class Boss(Entity):
    """
    Entidade Boss controlada por jogador.

    No modo Boss Battle:
    - No CLIENTE: captura teclas locais → get_input_snapshot()
    - No HOST:    recebe dict da rede  → apply_net_input(inp)

    Ambos os lados rodam update() para física e animação.
    """

    def __init__(self, game, x: float, y: float):
        super().__init__(game, x, y)

        self.add(PhysicsBody, BOSS_W, BOSS_H)
        self.hp = self.add(Health, BOSS_HP)
        self._hb = self.add(
            Hitbox,
            ox=0, oy=-BOSS_H,
            w=BOSS_W + 24, h=BOSS_H,
            damage=25, team="enemy", knockback=380,
        )

        self.facing = 1
        self._attack_timer = 0.0
        self._coyote = 0.0
        self._jump_buffer = 0.0

    def get_input_snapshot(self) -> dict:
        """Serializa estado das teclas para envio pela rede."""
        keys = pygame.key.get_pressed()
        return {
            "l": int(keys[KEY_LEFT]),
            "r": int(keys[KEY_RIGHT]),
            "j": int(keys[KEY_JUMP]),
            "a": int(keys[KEY_ATTACK]),
        }

    def apply_jump_event(self):
        """Chamado no handle_event do estado ao pressionar KEY_JUMP."""
        self._jump_buffer = 0.12

    def apply_net_input(self, inp: dict):
        """Aplica dict de input recebido pelo host."""
        self.vel.x = 0
        if inp.get("l"):
            self.vel.x -= BOSS_SPEED
            self.facing = -1
        if inp.get("r"):
            self.vel.x += BOSS_SPEED
            self.facing = 1
        if inp.get("j"):
            self._jump_buffer = 0.12
        if inp.get("a") and self._attack_timer <= 0:
            self._attack_timer = ATTACK_CD

    def update(self, dt: float):
        body = self.get(PhysicsBody)

        if body.on_ground:
            self._coyote = COYOTE_TIME
        else:
            self._coyote = max(0.0, self._coyote - dt)

        self._jump_buffer = max(0.0, self._jump_buffer - dt)

        if self._jump_buffer > 0 and (self._coyote > 0 or body.on_ground):
            self.vel.y = BOSS_JUMP_FORCE
            self._jump_buffer = 0.0
            self._coyote = 0.0

        if body.on_wall and not body.on_ground and self.vel.y > 0:
            self.vel.y = min(self.vel.y, 80)

        self._attack_timer = max(0.0, self._attack_timer - dt)
        self._hb.active = self._attack_timer > 0
        self._hb.tick(dt)

        self.hp.update(dt)
        if self.hp.current <= 0:
            self.alive = False

    def draw(self, surface, camera):
        body = self.get(PhysicsBody)
        if not body:
            return
        r = camera.apply_rect(body.rect)
        color = (200, 30, 30) if not self._hb.active else (255, 100, 40)
        pygame.draw.rect(surface, color, r)
        if self._hb.active:
            hr = camera.apply_rect(self._hb.rect)
            pygame.draw.rect(surface, (255, 60, 60), hr, 2)
        self._draw_hp_bar(surface, r)

    def _draw_hp_bar(self, surface, screen_rect):
        bw = BOSS_W + 20
        ratio = max(0.0, self.hp.current / self.hp.max_hp)
        bx = screen_rect.centerx - bw // 2
        by = screen_rect.top - 10
        pygame.draw.rect(surface, (50, 0, 0), (bx, by, bw, 6))
        if ratio > 0:
            pygame.draw.rect(surface, (210, 30, 30), (bx, by, int(bw * ratio), 6))

    def get_state_snapshot(self) -> dict:
        return {
            "x": self.pos.x, "y": self.pos.y,
            "vx": self.vel.x, "vy": self.vel.y,
            "facing": self.facing,
            "hp": self.hp.current,
            "atk": int(self._hb.active),
        }
