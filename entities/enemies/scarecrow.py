import pygame
from entities.entity import Entity
from components.physics_body import PhysicsBody 
from components.health import Health
from components.hitbox import Hitbox

class Scarecrow(Entity):
    def __init__(self, game, x, y):
        super().__init__(game, x, y)
        self.body = self.add(PhysicsBody, 32, 50)
        self.hp = self.add(Health, 30)
        self.touch_hb = self.add(Hitbox, -16, -24, 32, 50,
                                 damage=10, team="enemy", knockback=300)
        self.touch_hb.active = True
        
        #Ataque frontal
        self.hb_forward = self.add(Hitbox, 16, -24, 16, 50,
                                 damage=10, team="enemy", knockback=300)
        self.hb_forward.active = False

        #Ataque baixo
        self.hb_down = self.add(Hitbox, -16, 26, 32, 24,
                                 damage=15, team="enemy", knockback=400)
        self.hb_down.active = False

        self.state = "idle"
        self.timer = 1.2
        self.dir = 1

        self.duration = {
            "idle": 1.2,
            "telegraph": 0.5,
            "attack_fwd": 0.3,
            "attack_down": 0.5,
            "dash": 0.3,
            "recovery": 0.7,
        }

    def update(self, dt):
        self.hp.update(dt)
        self.touch_hb.tick(dt)
        self.hb_forward.tick(dt)
        self.hb_down.tick(dt)

        self.timer -= dt

        if self.state == "idle":
            self._update_idle(dt)
        elif self.state == "telegraph":
            self._update_telegraph(dt)
        elif self.state == "attack_fwd":    
            self._update_attack_fwd(dt)
        elif self.state == "attack_down":
            self._update_attack_down(dt)
        elif self.state == "dash":
            self._update_dash(dt)
        elif self.state == "recovery":
            self._update_recovery(dt)

    def _update_idle(self, dt):
        self.vel.x=0

        if self.timer <= 0:
            self._change_state("telegraph")

    def _update_telegraph(self, dt):
        self.vel.x=0
        player = self.game.states.current.player
        dx = player.pos.x - self.pos.x
        self.dor = 1 if dx > 0 else -1

        if self.timer <= 0:
            self._choose_and_start_attack()
    
    def _update_recovery(self, dt):
        self.vel.x=0

        if self.timer <= 0:
            self._change_state("idle")

    def _update_attack_fwd(self, dt):
        self.vel.x = 100 * self.dir

        if self.timer <= 0:
            self.hb_forward.active = False
            self._change_state("recovery")

    def _update_attack_down(self, dt):
        self.vel.x = 0

        if self.timer <= 0:
            self.hb_down.active = False
            self._change_state("recovery")

    def _update_dash(self, dt):
        self.vel.x =self.dir *320

        if self.body.on_wall:
            self.hb_forward.active = False
            self._change_state("recovery")
            return
        
        if self.timer <= 0:
            self.hb_forward.active = False
            self._change_state("recovery")
    

    def draw(self, surface, camera):
        colors = {
            "idle":       (150, 150, 100),
            "telegraph":  (255, 200,   0),
            "attack_fwd": (255,  60,  60),
            "attack_dwn": (255,  60,  60),
            "dash":       (255, 120,   0),
            "recovery":   ( 80, 180,  80),
        }

        color = colors.get(self.state, (255, 255, 255))
        dr = camera.apply_rect(self.body.rect)
        pygame.draw.rect(surface, color, dr)

        if self.hb_forward.active:
            pygame.draw.rect(surface, (60, 60, 255),
                            camera.apply_rect(self.hb_forward.rect), 2)

        if self.hb_down.active:
            pygame.draw.rect(surface, (60, 60, 255),
                            camera.apply_rect(self.hb_down.rect), 2)

    def _change_state(self, new_state):
        self.state = new_state
        self.timer = self.duration[new_state]

    def _choose_and_start_attack(self):
        player = self.game.states.current.player
        dx = player.pos.x - self.pos.x
        dy = player.pos.y - self.pos.y

        self.dir = 1 if dx > 0 else -1

        dist =abs(dx)

        if dist > 200:
            self._start_dash()
        elif abs(dy) < 20:
            self._start_attack_fwd()
        else:
            self._start_attack_down()

    def _start_attack_fwd(self):
        self._change_state("attack_fwd")
        self.hb_forward.active = True

        self.hb_forward.offset.x = 16 if self.dir == 1 else -52

    def _start_attack_down(self):
        self._change_state("attack_down")
        self.hb_down.active = True

    def _start_dash(self):
        self._change_state("dash")
        self.hb_forward.active = True
        self.hb_forward.offset.x = 16 if self.dir == 1 else -52


