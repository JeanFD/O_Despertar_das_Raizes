# entities/remote_player.py
import pygame
from entities.entity import Entity
from components.physics_body import PhysicsBody
from components.health import Health
from entities.player import PARRY_WINDOW, PARRY_CD

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

        # Debug overlay (recebido via snapshot)
        self._dbg_atk_active = False
        self._dbg_atk_rect = None
        self._dbg_plunge_landing = False
        self._dbg_plunge_timer = 0.0
        self._dbg_parry_timer = 0.0
        self._dbg_parry_cd = 0.0

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
        """Aplica snapshot recebido do host. Host é autoritativo:
        confiamos cegamente em alive/hp/posição."""
        self._target_x  = s.get("x", self._target_x)
        self._target_y  = s.get("y", self._target_y)
        self.vel.x      = s.get("vx", 0.0)
        self.vel.y      = s.get("vy", 0.0)
        self.facing     = s.get("facing", 1)
        self._anim_name = s.get("anim", "idle")
        remote_hp = s.get("hp")
        if remote_hp is not None:
            self.hp.current = float(remote_hp)

        # Sincroniza 'alive' com o snapshot. Sem isso, após uma morte/ring-out
        # no round 1, o RemotePlayer ficava com alive=False permanentemente
        # e o RenderSystem o ocultava no round 2 (player invisível).
        if "alive" in s:
            new_alive = bool(s["alive"])
            # Reviveu: snap direto para o spawn, sem lerp do "cadáver".
            if new_alive and not self.alive:
                self.pos.x = self._target_x
                self.pos.y = self._target_y
            self.alive = new_alive

        # Debug overlay fields (presentes quando a fonte é um Player)
        dbg = s.get("dbg")
        if dbg is not None:
            self._dbg_atk_active     = bool(dbg.get("atk_a"))
            self._dbg_atk_rect       = dbg.get("atk_r")
            self._dbg_plunge_landing = bool(dbg.get("pl_lnd"))
            self._dbg_plunge_timer   = float(dbg.get("pl_t", 0.0))
            self._dbg_parry_timer    = float(dbg.get("par_t", 0.0))
            self._dbg_parry_cd       = float(dbg.get("par_cd", 0.0))

    def update(self, dt: float):
        alpha = min(1.0, LERP_SPEED * dt)
        self.pos.x += (self._target_x - self.pos.x) * alpha
        self.pos.y += (self._target_y - self.pos.y) * alpha

        # NÃO sincroniza alive aqui a partir de hp — o host manda alive
        # explícito via apply_state(). Inferir local levava ao bug do
        # round 2 (alive ficava preso em False mesmo com hp resetado).
        self.hp.update(dt)

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
        self._draw_debug_overlay(surface, camera)

    def _draw_debug_overlay(self, surface, camera):
        """Reproduz os overlays de debug do Player.draw usando o estado
        recebido via snapshot. Mantém paridade visual entre host e cliente."""
        # Hitbox do ataque (vermelho normal, amarelo durante shockwave do plunge)
        if self._dbg_atk_active and self._dbg_atk_rect:
            x, y, w, h = self._dbg_atk_rect
            rect = pygame.Rect(x, y, w, h)
            screen_rect = camera.apply_rect(rect)
            color = (255, 200, 0) if self._dbg_plunge_landing else (255, 60, 60)
            pygame.draw.rect(surface, color, screen_rect, 2)

        # Telegraph do plunge
        if self._dbg_plunge_timer > 0:
            sx = int(self.pos.x - camera.offset.x)
            sy = int(self.pos.y - camera.offset.y)
            pygame.draw.line(surface, (255, 140, 0),
                             (sx, sy), (sx, sy + 30), 3)

        # Parry ativo
        if self._dbg_parry_timer > 0:
            sx = int(self.pos.x - camera.offset.x) + 12
            sy = int(self.pos.y - camera.offset.y) - 20
            pygame.draw.circle(surface, (255, 255, 200), (sx, sy), 22, 2)
            inner = int(8 + (self._dbg_parry_timer / PARRY_WINDOW) * 14)
            pygame.draw.circle(surface, (255, 255, 120), (sx, sy), inner, 1)
        elif self._dbg_parry_cd > 0:
            sx = int(self.pos.x - camera.offset.x) + 12
            sy = int(self.pos.y - camera.offset.y) - 20
            ratio = self._dbg_parry_cd / PARRY_CD
            pygame.draw.circle(surface, (90, 90, 90), (sx, sy),
                               int(8 + (1 - ratio) * 14), 1)

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
