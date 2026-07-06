import pygame
from components.physics_body import PhysicsBody

GRAVITY = 1800
MAX_FALL = 900

class PhysicsSystem:
    def __init__(self, tilemap):
        self.tilemap = tilemap

    def update(self, entities, dt):
        for e in entities:
            if getattr(e, "net_remote", False):
                continue
            body = e.get(PhysicsBody)
            if not body:
                continue
            self._gravity(e, dt)
            self._move_x(e, body, dt)
            self._move_y(e, body, dt)

    def _gravity(self, e, dt):
        if getattr(e, 'plunge_timer', 0) > 0:
            return
        e.vel.y = min(e.vel.y + GRAVITY * dt, MAX_FALL)
    
    def _move_x(self, e, body, dt):
        e.pos.x += e.vel.x * dt
        body.on_wall = 0
        for tile in self.tilemap.get_nearby_rects(body.rect):
            if body.rect.colliderect(tile):
                if e.vel.x > 0:
                    e.pos.x = tile.left - body.width / 2
                    body.on_wall = 1
                elif e.vel.x < 0:
                    e.pos.x = tile.right + body.width / 2
                    body.on_wall = -1
                e.vel.x = 0

    def _move_y(self, e, body, dt):
        e.pos.y += e.vel.y * dt
        body.on_ground = False
        for tile in self.tilemap.get_nearby_rects(body.rect):
            if body.rect.colliderect(tile):
                if e.vel.y > 0:
                    e.pos.y = tile.top
                    body.on_ground = True
                elif e.vel.y < 0:
                    e.pos.y = tile.bottom + body.height
                e.vel.y = 0

        # Contato de apoio: em repouso o rect fica exatamente encostado no topo
        # do tile (bottom == tile.top). pygame.Rect trunca o pos.y float, entao
        # o ~0.5px que a gravidade acumula por frame some, e colliderect()
        # ignora bordas que so se tocam — on_ground oscilava e a anim piscava
        # "fall". Uma sonda de 1px abaixo dos pes mantem on_ground estavel
        # enquanto o corpo esta apoiado, sem afetar quem esta caindo/subindo.
        if not body.on_ground and e.vel.y >= 0:
            foot = body.rect
            probe = pygame.Rect(foot.x, foot.bottom, foot.width, 1)
            for tile in self.tilemap.get_nearby_rects(probe):
                if probe.colliderect(tile):
                    body.on_ground = True
                    break