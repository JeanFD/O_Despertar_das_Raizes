import pygame
from settings import SCREEN_W, SCREEN_H

class Camera:
    def __init__(self, world_w, world_h):
        self.offset     = pygame.math.Vector2(0,0)
        self.world_w    = world_w
        self.world_h    = world_h
        self._target    = None
        self.smoothing  = 6.0

    def follow(self, target):
        self._target = target
    
    def update(self, dt):
        if not self._target:
            return
        
        ideal_x = self._target.pos.x - SCREEN_W / 2
        ideal_y = self._target.pos.y - SCREEN_H /2 - 60

        self.offset.x += (ideal_x - self.offset.x) * self.smoothing * dt
        self.offset.y += (ideal_y - self.offset.y) * self.smoothing * dt

        self.offset.x = max(0, min(self.offset.x, self.world_w - SCREEN_W))
        self.offset.y = max(0, min(self.offset.y, self.world_h - SCREEN_H))

    def apply(self, pos):
        return (int(pos.x - self.offset.x), int(pos.y - self.offset.y))
    
    def apply_rect(self, rect):
        return rect.move(-int(self.offset.x), -int(self.offset.y))