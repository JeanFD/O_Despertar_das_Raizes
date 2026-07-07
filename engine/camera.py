import pygame
from settings import SCREEN_W, SCREEN_H

class Camera:
    def __init__(self, world_w, world_h):
        self.offset     = pygame.math.Vector2(0,0)
        self.world_w    = world_w
        self.world_h    = world_h
        self._target    = None
        self.smoothing  = 6.0

        # Regiao do mundo que a camera pode revelar (esq, topo, dir, baixo).
        # Default = mapa inteiro; states podem restringir via set_bounds para
        # travar nas bordas dos blocos (chao e paredes) e nao mostrar o vazio
        # alem deles.
        self.left, self.top    = 0, 0
        self.right, self.bottom = world_w, world_h

    def follow(self, target):
        self._target = target

    def set_bounds(self, left, top, right, bottom):
        self.left, self.top    = left, top
        self.right, self.bottom = right, bottom

    def update(self, dt):
        if not self._target:
            return

        ideal_x = self._target.pos.x - SCREEN_W / 2
        ideal_y = self._target.pos.y - SCREEN_H /2 - 60

        self.offset.x += (ideal_x - self.offset.x) * self.smoothing * dt
        self.offset.y += (ideal_y - self.offset.y) * self.smoothing * dt

        # max(min_edge, ...) garante que, se a regiao for menor que a tela num
        # eixo, a camera fica presa na borda inicial (min vence).
        self.offset.x = max(self.left, min(self.offset.x, self.right - SCREEN_W))
        self.offset.y = max(self.top,  min(self.offset.y, self.bottom - SCREEN_H))

    def apply(self, pos):
        return (int(pos.x - self.offset.x), int(pos.y - self.offset.y))
    
    def apply_rect(self, rect):
        return rect.move(-int(self.offset.x), -int(self.offset.y))