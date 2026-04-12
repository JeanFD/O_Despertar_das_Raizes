import pygame
from settings import SCREEN_W, SCREEN_H
from states.base_state import BaseState
from entities.player import Player
from systems.physics_system import PhysicsSystem
from world.tilemap import Tilemap
from engine.camera import Camera
TILE = 32

class GameplayState(BaseState):
    def on_enter(self):
        from world.level import Level
        self.level = Level(self.game, "assets/maps/world.tmx")

        spawn = self.level.spawn_points.get("player", [{"x": 200, "y": 200}])[0]
        self.player = Player(self.game, spawn["x"], spawn["y"])
        self.entities = [self.player]

        self.physics = PhysicsSystem(self.level.tilemap)
        self.camera  = Camera(self.level.width, self.level.height)
        self.camera.follow(self.player)
    # Faça um mapa maior — substitua _build_test_map
    def _build_test_map(self):
        for x in range(0, 100):
            self.tilemap.add_tile(x, 25)
            self.tilemap.add_tile(x, 26)
        for x in range(8, 14):
            self.tilemap.add_tile(x, 20)
        for x in range(20, 26):
            self.tilemap.add_tile(x, 17)
        for y in range(15, 25):
            self.tilemap.add_tile(40, y)
        for x in range(45, 55):
            self.tilemap.add_tile(x, 18)

    def handle_event(self, event):
        self.player.handle_input(event)

    # update — adicione no fim
    def update(self, dt):
        keys = pygame.key.get_pressed()
        self.player.update_input(keys)
        self.physics.update(self.entities, dt)
        self.camera.update(dt)

    # draw — passe a câmera
    def draw(self, surface):
        self.level.draw_layer(surface, "background", self.camera)
        self.level.draw_layer(surface, "collision",  self.camera)
        for e in self.entities:
            e.draw(surface, self.camera)
        self.level.draw_layer(surface, "foreground", self.camera)