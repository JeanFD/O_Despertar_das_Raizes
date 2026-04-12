import pygame
from settings import SCREEN_W, SCREEN_H
from states.base_state import BaseState
from entities.player import Player
from systems.physics_system import PhysicsSystem
from world.tilemap import Tilemap

TILE = 32

class GameplayState(BaseState):
    def on_enter(self):
        self.tilemap = Tilemap(TILE)
        self._build_test_map()

        self.player = Player(self.game, 200, 200)
        self.ground_y = SCREEN_H - 80
        self.entities = [self.player]
        self.physics = PhysicsSystem(self.tilemap)

    def _build_test_map(self):
        # Chão
        for x in range(0, SCREEN_W // TILE):
            self.tilemap.add_tile(x, (SCREEN_H // TILE) - 2)
            self.tilemap.add_tile(x, (SCREEN_H // TILE) - 1)
        # Algumas plataformas
        for x in range(8, 14):
            self.tilemap.add_tile(x, 14)
        for x in range(20, 26):
            self.tilemap.add_tile(x, 11)
        # Uma parede
        for y in range(10, 18):
            self.tilemap.add_tile(30, y)

    def handle_event(self, event):
        self.player.handle_input(event)

    def update(self, dt):
        keys = pygame.key.get_pressed()
        self.player.update_input(keys)
        self.physics.update(self.entities, dt)
        
    def draw(self, surface):
        self.tilemap.draw(surface)
        for e in self.entities:
            e.draw(surface)