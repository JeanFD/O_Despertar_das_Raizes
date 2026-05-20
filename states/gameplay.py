import pygame
from settings import SCREEN_W, SCREEN_H
from states.base_state import BaseState
from entities.player import Player
from entities.pickup import AbilityPickup
from entities.projectile import Projectile
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
        self._spawn_xy = (float(spawn["x"]), float(spawn["y"]))
        self.player = Player(self.game, *self._spawn_xy)
        self.entities = [self.player]
        # Evita empilhar RespawnState múltiplas vezes (death dispara um frame
        # antes da tela ser empurrada; sem flag, push repete a cada frame).
        self._respawn_pushed = False

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
        for data in self.level.spawn_points.get("scarecrow", []):
            from entities.enemies.scarecrow import Scarecrow
            self.entities.append(Scarecrow(self.game, data["x"], data["y"]))
        for data in self.level.spawn_points.get("spike", []):
            from entities.spike import Spike 
            props = data.get("props", {})
            x_min = props.get("x_min", data["x"] - 100)
            x_max = props.get("x_max", data["x"] + 100)
            self.entities.append(Spike(self.game, data["x"], data["y"], x_min, x_max))

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
        # Não processa input/física enquanto a tela de respawn estiver no topo.
        if self._respawn_pushed:
            return

        keys = pygame.key.get_pressed()
        self.player.update_input(keys)
        if getattr(self.player, '_spawn_projectile_callback', False):
            self.player._spawn_projectile_callback = False
            proj = Projectile(x=self.player.pos.x, y=self.player.pos.y, direction=self.player.facing, team=self.player.team, game=self.game)
            self.entities.append(proj)
        self.physics.update(self.entities, dt)
        self.combat.update(self.entities, dt)
        for e in self.entities:
            e.update(dt)

        # Queda fora do mundo equivale a morte. Define HP=0 antes do filtro
        # para que o player saia da lista pelo mesmo caminho de "morreu por dano".
        if self.player.pos.y > self.level.height + 300:
            self.player.hp.current = 0
            self.player.alive = False

        # Mantém referência do player mesmo morto (não filtra ele aqui), só
        # tira do loop de update. Isso garante que self.player ainda existe
        # quando o callback de respawn for chamado para reposicioná-lo.
        self.entities = [e for e in self.entities
                         if e.alive or e is self.player]

        if not self.player.alive and not self._respawn_pushed:
            self._show_respawn_screen()

        self.camera.update(dt)

    def _show_respawn_screen(self):
        from states.respawn_state import RespawnState
        self._respawn_pushed = True
        self.game.states.push(RespawnState(
            self.game,
            on_respawn=self._respawn_player,
            on_quit=self._quit_to_menu,
        ))

    def _respawn_player(self):
        """Reposiciona o player no spawn original com HP/stamina cheios e
        reespawna inimigos/pickups do mapa, devolvendo o mundo ao estado
        inicial. Mantém só o player na lista (reset duro do nível)."""
        x, y = self._spawn_xy
        self.player.reset_for_round(x, y, facing=1)
        self.entities = [self.player]
        self._spawn_map_entities()
        self._respawn_pushed = False

    def _quit_to_menu(self):
        from states.main_menu import MainMenu
        self.game.states.change(MainMenu(self.game))

        

    def draw(self, surface):
    # 1. Parallax
        for layer in self.parallax_layers:
            layer.draw(surface, self.camera.offset)
        self.level.draw_layer(surface, "background", self.camera)
        self.render.draw_entities(surface, self.entities, self.camera)
        self.level.draw_layer(surface, "collision", self.camera)
        self.level.draw_layer(surface, "foreground", self.camera)
        self.hud.draw(surface)