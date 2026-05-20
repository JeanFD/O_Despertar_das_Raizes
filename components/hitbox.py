import pygame

class Hitbox:
    def __init__(self, entity, ox, oy, w, h, damage, team, knockback=200.0, knockback_y=200):
        self.entity = entity
        self.offset = pygame.math.Vector2(ox, oy)
        self.size = (w, h)
        self.damage = damage
        self.team = team
        self.knockback = knockback
        self.knockback_y = knockback_y
        self.active = False
        self._cd = {}

    @property
    def rect(self):
        e = self.entity
        return pygame.Rect(e.pos.x + self.offset.x, e.pos.y + self.offset.y, *self.size)

    def can_hit(self, tid):
        return self._cd.get(tid, 0) <= 0

    def register_hit(self, tid, cd=0.6):
        self._cd[tid] = cd

    def tick(self, dt):
        for k in list(self._cd):
            self._cd[k] -= dt
            if self._cd[k] <= 0:
                del self._cd[k]