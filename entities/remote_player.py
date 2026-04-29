# entities/remote_player.py
import pygame
from entities.entity import Entity
from components.physics_body import PhysicsBody
from components.health import Health

LERP_SPEED = 18.0


class RemotePlayer(Entity):
    """
    Representação visual do jogador remoto.

    Recebe snapshots via apply_state() e interpola suavemente
    entre posição atual e posição autoritativa do host.
    Não participa do PhysicsSystem (net_remote=True).
    """

    net_remote = True

    def __init__(self, game, x: float, y: float):
        super().__init__(game, x, y)

        self.add(PhysicsBody, 24, 40)
        self.hp = self.add(Health, 100)

        self._target_x = float(x)
        self._target_y = float(y)
        self.facing = 1
        self._anim_name = "idle"
        self._has_anim = False
        self.anim = None

        try:
            from components.animation import AnimationController
            sheet = game.assets.image("assets/images/sprites/player.png")
            self.anim = self.add(AnimationController, sheet, 48, 48, fps=12)
            self.anim.add("idle", 0, 0, 3)
            self.anim.add("run",  1, 0, 7)
            self.anim.add("jump", 2, 0, 0)
            self.anim.add("fall", 2, 1, 1)
            self._has_anim = True
        except Exception:
            pass

    def apply_state(self, s: dict):
        """Aplica snapshot recebido do host."""
        self._target_x  = s.get("x", self._target_x)
        self._target_y  = s.get("y", self._target_y)
        self.vel.x      = s.get("vx", 0.0)
        self.vel.y      = s.get("vy", 0.0)
        self.facing     = s.get("facing", 1)
        self._anim_name = s.get("anim", "idle")
        remote_hp = s.get("hp")
        if remote_hp is not None:
            self.hp.current = float(remote_hp)

    def update(self, dt: float):
        alpha = min(1.0, LERP_SPEED * dt)
        self.pos.x += (self._target_x - self.pos.x) * alpha
        self.pos.y += (self._target_y - self.pos.y) * alpha

        self.hp.update(dt)
        if self.hp.current <= 0:
            self.alive = False

        if self._has_anim:
            self.anim.play(self._anim_name, flip_x=(self.facing == -1))
            self.anim.update(dt)

    def draw(self, surface, camera):
        if self._has_anim:
            self.anim.draw(surface, self.pos, camera)
        else:
            body = self.get(PhysicsBody)
            if body:
                r = camera.apply_rect(body.rect)
                pygame.draw.rect(surface, (80, 100, 220), r)
                pygame.draw.rect(surface, (140, 160, 255), r, 2)

        self._draw_hp_bar(surface, camera)

    def _draw_hp_bar(self, surface, camera):
        body = self.get(PhysicsBody)
        if not body:
            return
        sx, sy = camera.apply(self.pos)
        bar_w = 32
        ratio = max(0.0, self.hp.current / self.hp.max_hp)
        bg = pygame.Rect(sx - 16, sy - 52, bar_w, 4)
        pygame.draw.rect(surface, (60, 0, 0), bg)
        if ratio > 0:
            pygame.draw.rect(surface, (0, 200, 80),
                             pygame.Rect(bg.x, bg.y, int(bar_w * ratio), 4))
