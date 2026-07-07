import pygame
from entities.entity import Entity
from components.physics_body import PhysicsBody 
from components.health import Health
from components.hitbox import Hitbox
from components.animation import AnimationController as Animation

class Crawler(Entity):
    def __init__(self, game, x, y):
        super().__init__(game, x, y)
        self.team = "enemy"
        
        self.body = self.add(PhysicsBody, 32, 24)
        self.hp = self.add(Health, 50)
        
        self.touch_hb = self.add(Hitbox, -16, -12, 32, 24, damage=10, team="enemy", knockback=200)
        self.touch_hb.active = True
        
        sheet = game.assets.image('assets/images/entities/crawler_sheet.png')
        
        # Inicializa animação
        self.anim = Animation(self, sheet, 32, 24, fps=8)
        self.anim.add("walk", 0, 0, 1)
        self.anim.add("hit", 0, 2, 2)
        self.anim.play("walk")
        
        self.dir = -1
        self.vel.x = self.dir * 80
        
        # Variáveis para a lógica de hit
        self.hit_timer = 0
        self.last_hp = self.hp.current

    def update(self, dt):
        self.hp.update(dt)
        self.touch_hb.tick(dt)
        
        # Lógica de detecção de dano
        if self.hp.current < self.last_hp:
            self.hit_timer = 0.4  # Duração da animação de hit
        self.last_hp = self.hp.current
        
        # Lógica de animação (prioriza hit se hit_timer > 0)
        should_flip = (self.dir == 1)
        if self.hit_timer > 0:
            self.hit_timer -= dt
            self.anim.play("hit", flip_x=should_flip)
        else:
            self.anim.play("walk", flip_x=should_flip)
            
        self.anim.update(dt)

        # Mata se cair fora do mapa
        if self.pos.y > 1000:
            self.kill()
            return

        # Lógica de movimentação
        if self.body.on_wall:
            self.dir *= -1
        self.vel.x = self.dir * 80

    def draw(self, surface, camera):
        # 1. Pega o frame atual do controlador
        frame = self.anim.image
        
        # 2. Redimensiona visualmente
        novo_w = int(32 * 1.25)
        novo_h = int(24 * 1.25)
        frame_maior = pygame.transform.scale(frame, (novo_w, novo_h))
        
        # 3. Desenha a posição ajustada
        pos_draw = camera.apply(self.pos)
        x_draw = pos_draw[0] - novo_w // 2
        y_draw = pos_draw[1] - novo_h + 6
        
        surface.blit(frame_maior, (x_draw, y_draw))