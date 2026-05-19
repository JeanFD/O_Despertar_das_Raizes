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

DASH_DOWN_SPEED = 1200
PLUNGE_HOP_FORCE = -500
PLUNGE_DAMAGE = 35
PLUNGE_RADIUS = 40
PLUNGE_CD = 0.6

ATTACK_TIME = 0.18
RANGED_CD = 0.7

ATTACK_HB_OX = 20
ATTACK_HB_OY = -32
ATTACK_HB_W = 26
ATTACK_HB_H = 32
ATTACK_HB_DAMAGE = 20
ATTACK_HB_KNOCKBACK = 250

PARRY_WINDOW = 0.20
PARRY_CD = 1.0
PARRY_STUN = 0.6
PARRY_REFLECT = 30
PARRY_IFRAMES = 0.5

class Player(Entity):
    def __init__(self, game, x, y, team_id: str = "player"):
        super().__init__(game, x, y)

        self.team = team_id

        from components.health import Health
        self.hp = self.add(Health, 100)

        from components.hitbox import Hitbox
        self.attack_hb = self.add(Hitbox, 20, -32, 26, 32, damage=20, team=team_id, knockback=250)

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

        self.ranged_cd = 0.0
        self._spawn_projectile_callback = False

        self.plunge_timer = 0.0
        self.plunge_cd = 0.0
        self.plunge_pending = False
        self.plunge_landing = False

        self.parry_timer = 0.0
        self.parry_cd = 0.0
        self.stun_timer = 0.0

        self._was_shift = False
        self._was_parry = False
        self._was_attack = False
        self._was_ranged = False
        self._net_was_da = False
        self._net_was_pl = False
        self._net_was_pa = False
        self._net_was_at = False
        self._net_was_rn = False

        self.wall_jump_lockout = 0.0

        self.jumps_left = 1

        self.abilities = {
            "double_jump": True,
            "dash": True,
            "wall_jump": True,
            "plunge": True,
            "ranged": True,
            "parry": True
        }

    def update_input(self, keys):
        # Edge detection (one-shot por aperto) — atualizar SEMPRE,
        # mesmo durante stun/dash, para não disparar ao soltar o bloqueio.
        shift_held = keys[pygame.K_LSHIFT]
        parry_held = keys[pygame.K_c] or keys[pygame.K_l]
        attack_held = keys[pygame.K_z] or keys[pygame.K_j]
        ranged_held = keys[pygame.K_x] or keys[pygame.K_k]
        shift_edge = shift_held and not self._was_shift
        parry_edge = parry_held and not self._was_parry
        attack_edge = attack_held and not self._was_attack
        ranged_edge = ranged_held and not self._was_ranged
        self._was_shift = shift_held
        self._was_parry = parry_held
        self._was_attack = attack_held
        self._was_ranged = ranged_held

        if self.stun_timer > 0:
            return

        if self.dash_timer > 0:
            return

        # TRAVA DE MOVIMENTO: Só obedece as setas se não estiver no meio de um wall jump
        if self.wall_jump_lockout <= 0:
            self.vel.x = 0
            if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
                self.vel.x =  MOVE_SPEED
                self.facing = 1
            if keys[pygame.K_LEFT] or keys[pygame.K_a]:
                self.vel.x = -MOVE_SPEED
                self.facing = -1

        keys_down_pressed = keys[pygame.K_DOWN] or keys[pygame.K_s]
        if (shift_edge and keys_down_pressed
                and self.plunge_timer <= 0 and self.plunge_cd <= 0
                and not self.plunge_pending
                and self.abilities.get("plunge")):
            if self.body.on_ground:
                self.vel.y = PLUNGE_HOP_FORCE
                self.vel.x = 0
                self.plunge_pending = True
            else:
                self.plunge_timer = 0.5
                self.vel.y = DASH_DOWN_SPEED
                self.vel.x = 0
        elif (shift_edge and self.dash_cd <= 0
              and not self.plunge_pending and self.plunge_timer <= 0
              and self.abilities["dash"]):
            self.dash_timer = DASH_TIME
            self.dash_cd    = DASH_CD
            self.vel.x      = self.facing * DASH_SPEED
            self.vel.y      = 0

        if attack_edge and self.attack_timer <= 0:
            self.attack_timer = ATTACK_TIME

        if ranged_edge and self.ranged_cd <= 0 and self.abilities.get("ranged"):
            self.ranged_cd = RANGED_CD
            self._spawn_projectile_callback = True
        if parry_edge:
            if (self.parry_cd <= 0 and self.parry_timer <= 0 and self.abilities.get("parry")):
                self.parry_timer = PARRY_WINDOW
                self.parry_cd = PARRY_CD
        

    def update(self, dt):
        self.dash_timer = max(0.0, self.dash_timer - dt)
        self.dash_cd = max(0.0, self.dash_cd - dt)
        self.ranged_cd = max(0.0, self.ranged_cd - dt)
        self.plunge_cd = max(0.0, self.plunge_cd - dt)
        self.wall_jump_lockout = max(0.0, self.wall_jump_lockout - dt)
        self.parry_timer = max(0.0, self.parry_timer - dt)
        self.parry_cd = max(0.0, self.parry_cd - dt)
        self.stun_timer = max(0.0, self.stun_timer - dt)

        self.attack_timer = max(0.0, self.attack_timer - dt)
        self.attack_hb.active = self.attack_timer > 0

        # Restaura hitbox normal após o shockwave do plunge terminar
        if self.plunge_landing and self.attack_timer <= 0:
            self.plunge_landing = False
            self.attack_hb.size = (ATTACK_HB_W, ATTACK_HB_H)
            self.attack_hb.offset.y = ATTACK_HB_OY
            self.attack_hb.damage = ATTACK_HB_DAMAGE
            self.attack_hb.knockback = ATTACK_HB_KNOCKBACK

        # Enquanto o shockwave estiver ativo, não sobrescreve offset.x baseado em facing
        if not self.plunge_landing:
            self.attack_hb.offset.x = ATTACK_HB_OX if self.facing == 1 else -(ATTACK_HB_OX + ATTACK_HB_W + 10)

        self._update_jump(dt)
        self.hp.update(dt)
        body = self.body

        if body.on_wall and not body.on_ground and self.vel.y > 0:
            self.vel.y = min(self.vel.y, 90)

        if self.dash_timer > 0 and self.plunge_timer <= 0:
            self.vel.y = 0

        # Hop do chão: converte para plunge quando atingir o apex (vel.y >= 0)
        if self.plunge_pending and self.vel.y >= 0:
            self.plunge_pending = False
            self.plunge_timer = 0.5
            self.vel.y = DASH_DOWN_SPEED
            self.vel.x = 0

        if not body.on_ground:
            anim = "jump" if self.vel.y < 0 else "fall"
        elif abs(self.vel.x) > 10:
            anim = "run"
        else:
            anim = "idle"
        self.anim.play(anim, flip_x=(self.facing == -1))
        self.anim.update(dt)

        if self.plunge_timer > 0 and self.body.on_ground:
            self.plunge_timer = 0
            self.plunge_cd = PLUNGE_CD
            self.plunge_landing = True
            self._trigger_plunge_landing()


        if self.plunge_timer > 0:
            self.plunge_timer -= dt


    def _update_jump(self, dt):
        body = self.body
        
        if body.on_ground:
            self.coyote_timer = COYOTE_TIME
            self.jumps_left = 1 if self.abilities["double_jump"] else 0
        else:
            self.coyote_timer = max(0.0, self.coyote_timer - dt)
            
        self.jump_buffer = max(0.0, self.jump_buffer - dt)

        can_normal_jump = self.coyote_timer > 0 or self.jumps_left > 0
        can_wall_jump = body.on_wall and self.abilities.get("wall_jump", False)

        if self.jump_buffer > 0:
            if can_wall_jump:
                self.vel.y = JUMP_FORCE * 0.95 
                self.vel.x = -self.facing * MOVE_SPEED * 1.0 
                self.facing = -self.facing
                
                #self.jumps_left = 1 if self.abilities.get("double_jump") else 0
                
                self.wall_jump_lockout = 0.18
                
                self.jump_buffer = 0.0
                
            elif can_normal_jump:
                self.vel.y = JUMP_FORCE
                if self.coyote_timer <= 0:
                    self.jumps_left -= 1
                    
                self.jump_buffer = 0.0
                self.coyote_timer = 0.0

    def reset_for_round(self, x: float, y: float, facing: int = 1):
        """Reposiciona o player para o início de um round de versus.

        Não altera abilities (configuração externa do modo), só estado volátil:
        posição, velocidade, HP, timers de ataque/dash, buffers de pulo.
        """
        self.pos.x = float(x)
        self.pos.y = float(y)
        self.vel.x = 0.0
        self.vel.y = 0.0
        self.facing = facing
        self.alive = True
        self.hp.current = self.hp.max_hp
        self.hp.invicible = 0.5
        self.attack_timer = 0.0
        self.attack_hb.active = False
        self.dash_timer = 0.0
        self.dash_cd = 0.0
        self.jump_buffer = 0.0
        self.coyote_timer = 0.0
        self.jumps_left = 1 if self.abilities.get("double_jump") else 0
        self.parry_timer = 0.0
        self.parry_cd = 0.0
        self.stun_timer = 0.0

    def apply_net_input(self, inp: dict):
        """Aplica dict de inputs recebido pela rede. Espelha update_input()."""
        # Edge detection — atualizar SEMPRE, mesmo durante stun/dash
        da_held = bool(inp.get("da"))
        pl_held = bool(inp.get("pl"))
        pa_held = bool(inp.get("pa"))
        at_held = bool(inp.get("at"))
        rn_held = bool(inp.get("rn"))
        da_edge = da_held and not self._net_was_da
        pl_edge = pl_held and not self._net_was_pl
        pa_edge = pa_held and not self._net_was_pa
        at_edge = at_held and not self._net_was_at
        rn_edge = rn_held and not self._net_was_rn
        self._net_was_da = da_held
        self._net_was_pl = pl_held
        self._net_was_pa = pa_held
        self._net_was_at = at_held
        self._net_was_rn = rn_held

        if self.stun_timer > 0:
            return
        if self.dash_timer > 0:
            return
        self.vel.x = 0
        if inp.get("r"):
            self.vel.x =  MOVE_SPEED
            self.facing = 1
        if inp.get("l"):
            self.vel.x = -MOVE_SPEED
            self.facing = -1
        if da_edge and self.dash_cd <= 0 and self.abilities["dash"]:
            self.dash_timer = DASH_TIME
            self.dash_cd    = DASH_CD
            self.vel.x      = self.facing * DASH_SPEED
            self.vel.y      = 0
        if at_edge and self.attack_timer <= 0:
            self.attack_timer = ATTACK_TIME
        if inp.get("ju"):
            self.jump_buffer = JUMP_BUFFER
        if rn_edge and self.ranged_cd <= 0 and self.abilities.get("ranged"):
            self.ranged_cd = RANGED_CD
            self._spawn_projectile_callback = True
        if pl_edge and self.abilities.get("plunge"):
            if self.plunge_timer <= 0 and self.plunge_cd <= 0 and not self.plunge_pending:
                if self.body.on_ground:
                    self.vel.y = PLUNGE_HOP_FORCE
                    self.vel.x = 0
                    self.plunge_pending = True
                else:
                    self.plunge_timer = 0.5
                    self.vel.y = DASH_DOWN_SPEED
                    self.vel.x = 0
        if pa_edge and self.parry_cd <= 0 and self.parry_timer <= 0 and self.abilities.get("parry"):
            self.parry_timer = PARRY_WINDOW
            self.parry_cd = PARRY_CD

    def draw(self, surface, camera):
        self.anim.draw(surface, self.pos, camera)
        if self.parry_timer > 0:
            sx = int(self.pos.x - camera.offset.x) + 12
            sy = int(self.pos.y - camera.offset.y) - 20
            pygame.draw.circle(surface, (255, 255, 200), (sx, sy), 22, 2)

    def _trigger_plunge_landing(self):
        """Shockwave de área quando o plunge pousa. Restauração no update."""
        body_half = 12  # PhysicsBody width 24 / 2
        self.attack_hb.offset.x = body_half - PLUNGE_RADIUS
        self.attack_hb.offset.y = -16
        self.attack_hb.size = (PLUNGE_RADIUS * 2, 16)
        self.attack_hb.damage = PLUNGE_DAMAGE
        self.attack_hb.knockback = 350
        self.attack_hb.active = True
        self.attack_timer = 0.08
