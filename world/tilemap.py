import pygame

class Tilemap:
    def __init__(self, tile_size):
        self.tile_size = tile_size
        self.collision_rects = []

    def add_tile(self,gx, gy):
        ts = self.tile_size
        self.collision_rects.append(pygame.Rect(gx*ts, gy *ts, ts, ts))

    def get_nearby_rects(self, rect):
        ts = self.tile_size
        x0 = rect.left // ts - 1
        x1 = rect.right // ts + 1
        y0=rect.top // ts - 1
        y1 = rect.bottom // ts + 1
        return [
            t for t in self.collision_rects if x0 <= t.x // ts <= x1 and y0 <= t.y // ts <= y1
        ]
    
    # world/tilemap.py — substitua o draw
    def draw(self, surface, camera):
        for r in self.collision_rects:
            dr = camera.apply_rect(r)
            # culling: só desenha o que está na tela
            if -64 < dr.x < surface.get_width() + 64 and -64 < dr.y < surface.get_height() + 64:
                pygame.draw.rect(surface, (60, 60, 80), dr)
                pygame.draw.rect(surface, (90, 90, 110), dr, 1)