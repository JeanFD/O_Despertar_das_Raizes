import pygame
from settings import SCREEN_W, SCREEN_H
from states.base_state import BaseState
from entities.player import Player
from entities.pickup import AbilityPickup
from systems.physics_system import PhysicsSystem
from world.tilemap import Tilemap
from engine.camera import Camera
from world.parallax_layer import ParallaxLayer

TILE = 32

class GameplayState(BaseState):
    def on_enter(self):
        from world.level import Level
        self.level = Level(self.game, "assets/maps/world.tmx")

        spawn = self.level.spawn_points.get("player", [{"x": 200, "y": 200}])[0]
        self.player = Player(self.game, spawn["x"], spawn["y"])
        self.entities = [self.player]

        from data.save_system import SaveSystem
        self.saves = SaveSystem(self.game)
        self.current_level_path = "assets/maps/world.tmx"

        data = getattr(self, "load_data", None)
        if data:
            self.player.pos.x = data["position"][0]
            self.player.pos.y = data["position"][1]
            for k, v in data.get("abilities", {}).items():
                self.player.abilities[k] = v
            self.player.hp.current = data.get("health", 100)

        from systems.combat_system import CombatSystem
        self.combat = CombatSystem()

        from systems.ability_system import AbilitySystem
        self.abilities_sys = AbilitySystem(self.game)
        self.abilities_sys.set_player(self.player)

        from ui.hud import HUD
        self.hud = HUD(self.game)
        self.hud.set_player(self.player)

        from systems.render_system import RenderSystem
        self.render = RenderSystem()

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
        self._spawn_map_entities()
        


    def _spawn_map_entities(self):
        for data in self.level.spawn_points.get("ability_pickup", []):
            ab = data["props"].get("ability")
            if ab:
                self.entities.append(AbilityPickup(self.game, data["x"], data["y"], ab))
        for data in self.level.spawn_points.get("crawler", []):
            from entities.enemies.crawler import Crawler
            self.entities.append(Crawler(self.game, data["x"], data["y"]))

    def handle_event(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                from states.pause import PauseState
                self.game.states.push(PauseState(self.game))
            elif event.key in (pygame.K_SPACE, pygame.K_UP, pygame.K_w):
                self.player.jump_buffer = 0.10
            elif event.key == pygame.K_F5:
                self.saves.save(0, self)
                print("Saved!")

    def update(self, dt):
        keys = pygame.key.get_pressed()
        self.player.update_input(keys)
        self.physics.update(self.entities, dt)
        self.combat.update(self.entities, dt)
        for e in self.entities:
            e.update(dt)
        self.entities = [e for e in self.entities if e.alive]
        self.camera.update(dt)

    def draw(self, surface):
    # 1. Parallax
        for layer in self.parallax_layers:
            layer.draw(surface, self.camera.offset)
        self.level.draw_layer(surface, "background", self.camera)
        self.render.draw_entities(surface, self.entities, self.camera)
        self.level.draw_layer(surface, "collision", self.camera)
        self.level.draw_layer(surface, "foreground", self.camera)
        self.hud.draw(surface)