import pygame
from entities.entity import Entity
from components.physics_body import PhysicsBody
from components.animation import AnimationController

MOVE_SPEED = 220
JUMP_FORCE = -600


def sheet_path_for(team_id: str) -> str:
    """Sheet por identidade do jogador — P1 e P2 com aparência diferente.

    Usado por Player E RemotePlayer para que a escolha do sprite dependa de
    QUEM é o jogador (p1/p2), não da classe. Assim os dois ficam visualmente
    distintos em qualquer tela (host, cliente ou servidor dedicado).
    """
    if team_id == "p2":
        return "assets/images/sprites/player_p2.png"
    return "assets/images/sprites/player.png"


def hitboxes_enabled(game) -> bool:
    """True se a setting 'Mostrar Hitboxes' estiver ligada. Gate único para
    todos os overlays de debug (corpo, ataque, parry, plunge)."""
    s = getattr(game, "settings", None)
    return bool(s and s.get("show_hitboxes"))

COYOTE_TIME = 0.10
JUMP_BUFFER = 0.10

DASH_SPEED = 550
DASH_TIME  = 0.18
DASH_CD    = 0.80

DASH_DOWN_SPEED = 1200
PLUNGE_HOP_FORCE = -500
PLUNGE_DAMAGE = 22
PLUNGE_RADIUS = 40
PLUNGE_CD = 0.6

ATTACK_TIME = 0.18
RANGED_CD = 0.7

ATTACK_HB_OX = 20
ATTACK_HB_OY = -32
ATTACK_HB_W = 26
ATTACK_HB_H = 32
ATTACK_HB_DAMAGE = 12
ATTACK_HB_KNOCKBACK = 250

PARRY_WINDOW = 0.20
PARRY_CD = 1.0
PARRY_STUN = 0.6
PARRY_REFLECT = 18
PARRY_IFRAMES = 0.5

MAX_STAMINA   = 100.0
# Sem regen passivo: a barra funciona como "mana/especial" — só enche
# ao acertar um inimigo. Incentiva pressão ofensiva e evita usar abilidades
# enquanto se foge. Começa no máximo para não punir o spawn.
# Dash normal NÃO custa stamina (mobilidade básica, não habilidade especial).
COST_PLUNGE  = 25.0
COST_RANGED  = 15.0
COST_PARRY   = 12.0
STAMINA_GAIN_ON_HIT = 22.0  # ganho por acertar um inimigo


class _NetKeys:
    """Adapter que faz um dict de input (rede) se comportar como
    pygame.key.get_pressed(). Permite que update_input rode com inputs
    locais OU remotos sem duplicar lógica.

    Campos esperados no dict (todos booleanos / 0-1):
        l   K_a  / K_LEFT
        r   K_d  / K_RIGHT
        dn  K_s  / K_DOWN
        sh  K_LSHIFT
        at  K_z  / K_j
        rn  K_x  / K_k
        pa  K_c  / K_l

    Pulo (jump) é tratado fora — via inp.get("ju") setando jump_buffer.
    """
    _MAP = {
        pygame.K_LEFT:   "l",  pygame.K_a:      "l",
        pygame.K_RIGHT:  "r",  pygame.K_d:      "r",
        pygame.K_DOWN:   "dn", pygame.K_s:      "dn",
        pygame.K_LSHIFT: "sh",
        pygame.K_z:      "at", pygame.K_j:      "at",
        pygame.K_x:      "rn", pygame.K_k:      "rn",
        pygame.K_c:      "pa", pygame.K_l:      "pa",
    }

    def __init__(self, inp: dict):
        self._inp = inp

    def __getitem__(self, key):
        field = self._MAP.get(key)
        if field is None:
            return False
        return bool(self._inp.get(field))


class Player(Entity):
    # Lido por CombatSystem via getattr para reembolso de stamina ao acertar.
    STAMINA_GAIN_ON_HIT = STAMINA_GAIN_ON_HIT

    def __init__(self, game, x, y, team_id: str = "player"):
        super().__init__(game, x, y)

        self.team = team_id

        from components.health import Health
        self.hp = self.add(Health, 100)

        from components.hitbox import Hitbox
        self.attack_hb = self.add(Hitbox, 20, -32, 26, 32, damage=20, team=team_id, knockback=250)

        self.attack_timer = 0.0

        sheet     = game.assets.image(sheet_path_for(team_id))
        self.body = self.add(PhysicsBody, 24, 40)
        self.anim = self.add(AnimationController, sheet, 96, 64, fps=12)

        # Sheet unificado 96x64 (grid 8x8). Corpo (hitbox 24x40) ancorado na
        # base-centro da celula; cada acao tem sua propria linha, com a hitbox
        # de golpe cabendo no frame largo. Ver assets/images/sprites/player.png.
        self.anim.add("idle",   0, 0, 3)
        self.anim.add("run",    1, 0, 7)
        self.anim.add("jump",   2, 0, 2)
        self.anim.add("fall",   3, 0, 2)
        self.anim.add("attack", 4, 0, 3)
        self.anim.add("ranged", 5, 0, 3)
        self.anim.add("plunge", 6, 0, 3)
        self.anim.add("parry",  7, 0, 2)
        self.anim.add("dash",   8, 0, 1)
        self.anim.add("wall_slide", 9, 0, 1)
        self.anim.add("hurt",   10, 0, 3)

        self.facing = 1

        self.coyote_timer = 0.0
        self.jump_buffer = 0.0

        self.dash_timer = 0.0
        self.dash_cd    = 0.0

        self.ranged_cd = 0.0
        # Janela curta só para exibir a pose de arremesso (o ranged em si é
        # instantâneo — dispara o projétil e volta). Sem isso não haveria
        # estado durável para a anim "ranged" aparecer.
        self.ranged_anim_timer = 0.0
        self._spawn_projectile_callback = False

        self.plunge_timer = 0.0
        self.plunge_cd = 0.0
        self.plunge_pending = False
        self.plunge_landing = False

        self.parry_timer = 0.0
        self.parry_cd = 0.0
        self.stun_timer = 0.0

        self.max_stamina = MAX_STAMINA
        self.stamina = MAX_STAMINA

        # Cliente: nome de animação autoritativo recebido via snapshot.
        # Quando setado, sobrepõe a lógica local (que depende de on_ground,
        # não calculado no cliente sem PhysicsSystem). No host fica None.
        self._authoritative_anim: str | None = None

        # Edge detection — única fonte (usada tanto por input local quanto
        # por input de rede, que delega para update_input via _NetKeys).
        self._was_shift = False
        self._was_parry = False
        self._was_attack = False
        self._was_ranged = False

        self.wall_jump_lockout = 0.0

        self.jumps_left = 1

        self.abilities = {
            "double_jump": True,
            "dash": True,
            "wall_jump": True,
            "plunge": False,
            "ranged": False,
            "parry": False
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
                and self.abilities.get("plunge")
                and self.stamina >= COST_PLUNGE):
            self.stamina -= COST_PLUNGE
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
            self.game.sound.play("player_attack")

        if (ranged_edge and self.ranged_cd <= 0 and self.abilities.get("ranged")
                and self.stamina >= COST_RANGED):
            self.stamina -= COST_RANGED
            self.ranged_cd = RANGED_CD
            self.ranged_anim_timer = 0.25
            self._spawn_projectile_callback = True
        if parry_edge:
            if (self.parry_cd <= 0 and self.parry_timer <= 0
                    and self.abilities.get("parry")
                    and self.stamina >= COST_PARRY):
                self.stamina -= COST_PARRY
                self.parry_timer = PARRY_WINDOW
                self.parry_cd = PARRY_CD
        

    def update(self, dt):
        self.dash_timer = max(0.0, self.dash_timer - dt)
        self.dash_cd = max(0.0, self.dash_cd - dt)
        self.ranged_cd = max(0.0, self.ranged_cd - dt)
        self.ranged_anim_timer = max(0.0, self.ranged_anim_timer - dt)
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
            if body.on_wall and self.vel.y > 0:
                anim = "wall_slide"      # descendo colado na parede
            else:
                anim = "jump" if self.vel.y < 0 else "fall"
        elif abs(self.vel.x) > 10:
            anim = "run"
        else:
            anim = "idle"
        # Ações sobrepõem o movimento, em ordem de prioridade. plunge vem antes
        # de attack porque o shockwave de pouso também usa attack_timer.
        if self.plunge_timer > 0 or self.plunge_landing:
            anim = "plunge"
        elif self.attack_timer > 0:
            anim = "attack"
        elif self.parry_timer > 0:
            anim = "parry"
        elif self.ranged_anim_timer > 0:
            anim = "ranged"
        elif self.stun_timer > 0:
            anim = "hurt"                # atordoado (ex.: golpe defendido no parry)
        elif self.dash_timer > 0:
            anim = "dash"
        # No cliente, on_ground não é calculado (PhysicsSystem só roda no host),
        # então a lógica acima trava em "fall". Quando vem snapshot do host,
        # usamos o anim autoritativo para refletir o estado real.
        if self._authoritative_anim:
            anim = self._authoritative_anim
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
        self.stamina = self.max_stamina

    def apply_net_input(self, inp: dict):
        """Aplica dict de inputs recebido pela rede.

        Delega 100% para update_input via _NetKeys — a lógica de input vive
        em UM lugar só. Qualquer mudança em update_input (nova habilidade,
        regra, ajuste de cooldown) automaticamente vale para o jogador remoto.

        Pulo é tratado à parte porque update_input não processa pulo (vem
        via KEYDOWN no handle_event do estado, equivalente ao 'ju' aqui).
        """
        self.update_input(_NetKeys(inp))
        if inp.get("ju"):
            self.jump_buffer = JUMP_BUFFER

    def draw(self, surface, camera):
        self.anim.draw(surface, self.pos, camera)

        # Todos os overlays de hitbox só aparecem com a setting ligada.
        if not hitboxes_enabled(self.game):
            return

        # Caixa de colisão do corpo (verde)
        pygame.draw.rect(surface, (60, 220, 120),
                         camera.apply_rect(self.body.rect), 1)

        # Debug: hitboxes do ataque (normal e shockwave do plunge)
        if self.attack_hb.active:
            r = camera.apply_rect(self.attack_hb.rect)
            # Vermelho p/ ataque normal, amarelo p/ shockwave do plunge
            color = (255, 200, 0) if self.plunge_landing else (255, 60, 60)
            pygame.draw.rect(surface, color, r, 2)

        # Debug: telegraph do plunge (mergulho em andamento)
        if self.plunge_timer > 0:
            sx = int(self.pos.x - camera.offset.x)
            sy = int(self.pos.y - camera.offset.y)
            pygame.draw.line(surface, (255, 140, 0),
                             (sx, sy), (sx, sy + 30), 3)

        # Debug/feedback: janela de parry ativa (anel branco)
        if self.parry_timer > 0:
            sx = int(self.pos.x - camera.offset.x) + 12
            sy = int(self.pos.y - camera.offset.y) - 20
            pygame.draw.circle(surface, (255, 255, 200), (sx, sy), 22, 2)
            # Pulsa o raio interno para feedback de janela "fresca"
            inner = int(8 + (self.parry_timer / PARRY_WINDOW) * 14)
            pygame.draw.circle(surface, (255, 255, 120), (sx, sy), inner, 1)
        # Cooldown: anel apagado pra mostrar "parry indisponível"
        elif self.parry_cd > 0:
            sx = int(self.pos.x - camera.offset.x) + 12
            sy = int(self.pos.y - camera.offset.y) - 20
            ratio = self.parry_cd / PARRY_CD
            pygame.draw.circle(surface, (90, 90, 90), (sx, sy),
                               int(8 + (1 - ratio) * 14), 1)

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

    def debug_snapshot(self) -> dict:
        """Estado mínimo para o RemotePlayer renderizar overlays de debug
        (hitboxes, parry, plunge). Serializado para o cliente via snapshot.
        """
        r = self.attack_hb.rect
        return {
            "atk_a":  bool(self.attack_hb.active),
            "atk_r":  [r.x, r.y, r.w, r.h] if self.attack_hb.active else None,
            "pl_lnd": bool(self.plunge_landing),
            "pl_t":   float(self.plunge_timer),
            "par_t":  float(self.parry_timer),
            "par_cd": float(self.parry_cd),
        }

    def apply_dbg(self, dbg: dict):
        """Cliente: aplica overlay debug autoritativo do host no Player local.

        Sem isso, o jogador-2 (cliente) nunca veria a própria hitbox de
        ataque/parry/plunge — todo o estado de combate vive no host. Os
        timers ficam com valor "qualquer >0" enquanto o snapshot diz que
        estão ativos; o reconcile do próximo frame rebota tudo.
        """
        if not dbg:
            return
        atk_a = bool(dbg.get("atk_a"))
        atk_r = dbg.get("atk_r")
        if atk_a and atk_r:
            x, y, w, h = atk_r
            self.attack_hb.size = (w, h)
            self.attack_hb.offset.x = x - self.pos.x
            self.attack_hb.offset.y = y - self.pos.y
            self.attack_hb.active = True
            # Mantém attack_timer > 0 para o Player.update não desativar
            # nem resetar size/offset enquanto a janela do golpe está aberta.
            self.attack_timer = max(self.attack_timer, 0.05)
        else:
            self.attack_hb.active = False
            self.attack_timer = 0.0

        self.plunge_landing = bool(dbg.get("pl_lnd"))
        self.plunge_timer   = float(dbg.get("pl_t", 0.0))
        self.parry_timer    = float(dbg.get("par_t", 0.0))
        self.parry_cd       = float(dbg.get("par_cd", 0.0))
