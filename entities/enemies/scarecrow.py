import pygame
import random
from entities.entity import Entity
from components.physics_body import PhysicsBody 
from components.health import Health
from components.hitbox import Hitbox

class Scarecrow(Entity):
    def __init__(self, game, x, y):
        super().__init__(game, x, y)
        self.body     = self.add(PhysicsBody, 32, 50)
        self.hp       = self.add(Health, 150)

        self.touch_hb = self.add(Hitbox, -16, -24, 32, 50,
                                 damage=5, team="enemy", knockback=150)
        self.touch_hb.active = True

        self.hb_down = self.add(Hitbox, -48, -10, 200, 24,
                                damage=12, team="enemy", knockback=500, knockback_y=50)
        self.hb_down.active = False

        self.hb_front = self.add(Hitbox, 0, -64, 70, 64,
                                damage=18, team="enemy", knockback=300)
        self.hb_front.active = False
        self.team = "enemy"

        self.state       = "idle"
        self.timer       = 1.5
        self.dir         = 1
        self.next_attack = None  # decisão congelada no telegraph

        self.duration = {
            "idle":        1.5,  # andando em direção ao player
            "telegraph":   0.7,  # pausa de aviso — player vê o que vem
            "dash":        2.0,  # tempo máximo do dash
            "attack_down": 0.4,  # rasteira
            "attack_front": 0.5,  # corte vertical
            "recovery":    1.0,  # vulnerável — janela de punição longa
        }

    # ------------------------------------------------------------------ update

    def update(self, dt):
        self.hp.update(dt)

        if self.pos.y > 1000:
            self.kill()
            return

        self.timer -= dt

        if self.state == "idle":
            self._update_idle(dt)
        elif self.state == "telegraph":
            self._update_telegraph(dt)
        elif self.state == "dash":
            self._update_dash(dt)
        elif self.state == "attack_down":
            self._update_attack_down(dt)
        elif self.state == "attack_front":
            self._update_attack_front(dt)
        elif self.state == "recovery":
            self._update_recovery(dt)


    def _update_idle(self, dt):
        # anda devagar em direção ao player
        player = self.game.states.current.player
        dx = player.pos.x - self.pos.x
        self.dir = 1 if dx > 0 else -1
        self.vel.x = self.dir * 80

        if self.body.on_wall:
            self.vel.x = 0

        if self.timer <= 0:
            self._change_state("telegraph")

    def _update_telegraph(self, dt):
        # para, olha pro player e decide o ataque
        self.vel.x = 0
        player = self.game.states.current.player
        dx = player.pos.x - self.pos.x
        dy = player.pos.y - self.pos.y
        self.dir = 1 if dx > 0 else -1

        if self.next_attack is None:
            self.next_attack = random.choice(["down", "front"])

        if self.timer <= 0:
            self._start_dash()

    def _update_dash(self, dt):
        # corre em direção ao player para executar o ataque já decidido
        player = self.game.states.current.player
        dx = player.pos.x - self.pos.x
        dist = abs(dx)

        # chegou perto — executa o ataque decidido 
        if dist <= 60:
            self.vel.x = 0
            if self.next_attack == "front":
                self._start_attack_front()
            else:
                self._start_attack_down()
            return

        self.vel.x = self.dir * 320

        # bateu na parede — desiste
        if self.body.on_wall:
            self.vel.x = 0
            self.next_attack = None
            self._change_state("recovery")
            return

        # player fugiu longe demais
        if self.timer <= 0:
            self.vel.x = 0
            self.next_attack = None
            self._change_state("recovery")

    def _update_attack_down(self, dt):
        # rasteira — parado durante o golpe
        self.vel.x = 0
        
        if self.timer <= 0:
            self.hb_down.active = False
            self.hb_down._cd.clear()  # limpa cooldowns ao desativar
            self.next_attack = None
            self._change_state("recovery")

    def _update_attack_front(self, dt):
        # corte vertical — parado durante o golpe
        self.vel.x = 0

        if self.timer <= 0:
            self.hb_front.active = False
            self.next_attack = None
            self._change_state("recovery")

    def _update_recovery(self, dt):
        # parado e vulnerável — janela longa para o player punir
        self.vel.x = 0

        if self.timer <= 0:
            self._change_state("idle")

    # ------------------------------------------------------------------ ataques

    def _start_dash(self):
        self._change_state("dash")
        # atualiza o offset da hitbox front para o lado certo já aqui
        self.hb_front.offset.x = 0 if self.dir == 1 else -48

    def _start_attack_down(self):
        # rasteira: hitbox centrada no espantalho, varre os dois lados
        self._change_state("attack_down")
        self.hb_down.active = True

    def _start_attack_front(self):
        # front: hitbox na frente, do lado que ele está olhando
        self._change_state("attack_front")
        self.hb_front.active = True
        self.hb_front.offset.x = 0 if self.dir == 1 else -48

    # ------------------------------------------------------------------ utils

    def _change_state(self, new_state):
        self.state = new_state
        self.timer = self.duration[new_state]

    # ------------------------------------------------------------------ draw

    def draw(self, surface, camera):
        colors = {
            "idle":        (150, 150, 100),  # cinza-amarelado — andando
            "telegraph":   (255, 200,   0),  # amarelo — aviso
            "dash":        (255, 120,   0),  # laranja — correndo
            "attack_down": (255,  60,  60),  # vermelho — rasteira
            "attack_front": (200,   0, 200),  # roxo — front
            "recovery":    ( 80, 180,  80),  # verde — vulnerável
        }

        color = colors.get(self.state, (255, 255, 255))
        dr = camera.apply_rect(self.body.rect)
        pygame.draw.rect(surface, color, dr)

        if self.hb_down.active:
            pygame.draw.rect(surface, (255, 200, 0),
                             camera.apply_rect(self.hb_down.rect), 2)

        if self.hb_front.active:
            pygame.draw.rect(surface, (200, 0, 200),
                             camera.apply_rect(self.hb_front.rect), 2)