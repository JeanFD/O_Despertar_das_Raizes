# states/play_state.py
"""
Estado de gameplay atualizado.
- Abre pause com ESC
- Suporta load_data vindo do SaveMenu
- Salva com F5, carrega com F9
"""
import pygame
from states.base_state       import BaseState
from settings                import SCREEN_W, SCREEN_H, GRAVITY, MAX_FALL
from entities.player         import Player
from engine.camera           import Camera
from systems.physics_system  import PhysicsSystem
from components.physics_body import PhysicsBody
from components.health       import Health
from ui.hud                  import HUD

WORLD_W = 3000
WORLD_H = 800


class PlayState(BaseState):

    def __init__(self, game):
        super().__init__(game)
        self.load_data = None      # preenchido pelo SaveMenu se for carregar

    def on_enter(self):
        self.camera = Camera(WORLD_W, WORLD_H)

        # Level de teste
        self.tiles = [
            pygame.Rect(0,    720, 3000, 80),
            pygame.Rect(200,  620, 150,  20),
            pygame.Rect(500,  550, 200,  20),
            pygame.Rect(800,  480, 120,  20),
            pygame.Rect(1000, 580, 200,  20),
            pygame.Rect(1300, 500, 150,  20),
            pygame.Rect(1550, 420, 200,  20),
            pygame.Rect(1850, 520, 120,  20),
            pygame.Rect(2100, 450, 200,  20),
            pygame.Rect(2400, 600, 300,  20),
            pygame.Rect(0,    0,   20,   800),
            pygame.Rect(2980, 0,   20,   800),
        ]

        # Física
        from world.tilemap import Tilemap
        tm = Tilemap(32)
        tm.collision_rects = self.tiles
        self.physics = PhysicsSystem(tm)

        # Player
        self.player = Player(self.game, 100, 600)
        self.camera.follow(self.player)

        # HUD
        self.hud = HUD(self.game)
        self.hud.set_player(self.player)

        # Se veio do SaveMenu com dados para carregar
        if self.load_data:
            self._apply_load_data(self.load_data)

    def _apply_load_data(self, data: dict):
        """Aplica dados de um save ao estado atual."""
        if "position" in data:
            self.player.pos.x = data["position"][0]
            self.player.pos.y = data["position"][1]

        if "abilities" in data:
            for k, v in data["abilities"].items():
                if k in self.player.abilities:
                    self.player.abilities[k] = v

        if "health" in data and hasattr(self.player, "hp"):
            self.player.hp.current = data["health"]

    def handle_event(self, event):
        if event.type != pygame.KEYDOWN:
            return

        # Pause
        if event.key == pygame.K_ESCAPE:
            from states.pause import PauseState
            self.game.states.push(PauseState(self.game))
            return

        # Quick save / quick load
        if event.key == pygame.K_F5:
            self._quick_save()
        elif event.key == pygame.K_F9:
            self._quick_load()

        # Pulo
        if event.key in (pygame.K_SPACE, pygame.K_UP, pygame.K_w):
            self.player.jump_buffer = 0.10

    def _quick_save(self):
        """Salva no slot 0 rapidamente."""
        from data.save_system import SaveSystem
        from datetime import datetime
        save = SaveSystem()
        data = {
            "position":  [self.player.pos.x, self.player.pos.y],
            "abilities": dict(self.player.abilities),
            "health":    self.player.hp.current if hasattr(self.player, "hp") else 100,
            "state":     getattr(self.player, "state", "idle"),
            "saved_at":  datetime.now().strftime("%d/%m/%Y %H:%M"),
        }
        save.save(0, data)

    def _quick_load(self):
        """Carrega do slot 0 rapidamente."""
        from data.save_system import SaveSystem
        save = SaveSystem()
        data = save.load(0)
        if data:
            self._apply_load_data(data)

    def update(self, dt):
        keys = pygame.key.get_pressed()
        self.player.update_input(keys)
        self.physics.update([self.player], dt)
        self.camera.update(dt)

        # Atualizar health timer
        if hasattr(self.player, "hp"):
            self.player.hp.update(dt)

    def draw(self, surface):
        surface.fill((8, 5, 20))

        # Tiles
        for tile in self.tiles:
            sr = self.camera.apply_rect(tile)
            if sr.right > 0 and sr.left < SCREEN_W:
                pygame.draw.rect(surface, (60, 60, 80), sr)

        # Player
        self.player.draw(surface, self.camera)

        # HUD
        self.hud.draw(surface)

        # Info de debug
        font = pygame.font.SysFont("consolas,monospace", 16)
        lines = [
            f"State: {getattr(self.player, 'state', 'idle')}",
            f"Pos: ({self.player.pos.x:.0f}, {self.player.pos.y:.0f})",
            f"ESC=pause  F5=save  F9=load",
            f"A/D=mover  SPACE=pular  SHIFT=dash",
        ]
        for i, line in enumerate(lines):
            surf = font.render(line, True, (100, 95, 120))
            surface.blit(surf, (SCREEN_W - 310, 10 + i * 18))
