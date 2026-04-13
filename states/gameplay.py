import pygame
from settings import SCREEN_W, SCREEN_H
from states.base_state import BaseState
from entities.player import Player
from systems.physics_system import PhysicsSystem
from world.tilemap import Tilemap
from engine.camera import Camera
from world.parallax_layer import ParallaxLayer
TILE = 32

class GameplayState(BaseState):
    def on_enter(self):
        from world.level import Level
        self.level = Level(self.game, "assets/maps/world.tmx")

        from systems.combat_system import CombatSystem
        self.combat = CombatSystem()

        spawn = self.level.spawn_points.get("player", [{"x": 200, "y": 200}])[0]
        self.player = Player(self.game, spawn["x"], spawn["y"])
        self.entities = [self.player]

        self.physics = PhysicsSystem(self.level.tilemap)
        self.camera  = Camera(self.level.width, self.level.height)
        self.camera.follow(self.player)

        self.parallax_layers = [
            ParallaxLayer(self.game.assets.image("assets/images/backgrounds/sky.png"),         0.0),
            ParallaxLayer(self.game.assets.image("assets/images/backgrounds/mountains.png"),  0.1),
            ParallaxLayer(self.game.assets.image("assets/images/backgrounds/clouds.png"),         0.2),
            ParallaxLayer(self.game.assets.image("assets/images/backgrounds/forest_far.png"), 0.3),
            ParallaxLayer(self.game.assets.image("assets/images/backgrounds/forest_near.png"),0.6),
        ]
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
        self.combat.update(self.entities, dt)
        for e in self.entities:
            e.update(dt)
        self.camera.update(dt)

    # draw — passe a câmera
    def draw(self, surface):
        for layer in self.parallax_layers:
            layer.draw(surface, self.camera.offset)
        self.level.draw_layer(surface, "background", self.camera)
        self.level.draw_layer(surface, "collision",  self.camera)
        for e in self.entities:
            e.draw(surface, self.camera)
        self.level.draw_layer(surface, "foreground", self.camera)