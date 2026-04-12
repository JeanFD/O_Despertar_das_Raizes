import pygame

class PhysicsBody:
    def __init__(self, entity, width, height):
        self.entity = entity
        self.width = width
        self.height = height
        self.on_ground = False
        self.on_wall = 0 # -1 esq, 0 nada, 1 dir

    @property
    def rect(self):
        e = self.entity
        return pygame.Rect(e.pos.x - self.width / 2, e.pos.y - self.height, self.width, self.height)