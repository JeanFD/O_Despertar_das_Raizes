# states/multiplayer_gameplay.py
import pygame
from states.base_state import BaseState
from entities.player import Player
from entities.remote_player import RemotePlayer
from entities.boss import Boss
from systems.physics_system import PhysicsSystem
from systems.combat_system import CombatSystem
from systems.render_system import RenderSystem
from engine.camera import Camera
from world.tilemap import Tilemap
from components.health import Health
from components.physics_body import PhysicsBody


class MultiplayerGameplayState(BaseState):
    """
    Estado de gameplay para ambos os modos multiplayer.

    ╔══════════════╦══════════════════════════════╦══════════════════════════════╗
    ║              ║          CO-OP               ║        BOSS BATTLE           ║
    ╠══════════════╬══════════════════════════════╬══════════════════════════════╣
    ║ HOST local   ║ Player  (P1, teclas locais)  ║ Player (protagonista, local) ║
    ║ HOST remoto  ║ Player  (P2, input da rede)  ║ Boss   (boss, input da rede) ║
    ╠══════════════╬══════════════════════════════╬══════════════════════════════╣
    ║ CLIENT local ║ Player  (P2, teclas locais)  ║ Boss   (boss, teclas locais) ║
    ║ CLIENT remoto║ RemotePlayer (P1, interp.)   ║ RemotePlayer (prot., interp.)║
    ╚══════════════╩══════════════════════════════╩══════════════════════════════╝

    O HOST roda física completa em todas as entidades (autoritativo).
    O CLIENTE prediz localmente e recebe estado autoritativo do host.
    """

    def __init__(self, game, net, is_host: bool, game_mode: str):
        super().__init__(game)
        self.net       = net
        self.is_host   = is_host
        self.game_mode = game_mode

        self._local_entity  = None
        self._remote_entity = None
        self._entities      = []

        self._physics  = None
        self._combat   = CombatSystem()
        self._render   = RenderSystem()
        self._camera   = None
        self._tilemap  = None
        self._level    = None

        self._disconnected = False
        self._paused = False
        self._jump_pressed = False
        self._tick = 0
        self._last_client_input: dict = {}

    # ── Inicialização ─────────────────────────────────────────────────────────

    def on_enter(self):
        self._load_world()
        self._physics = PhysicsSystem(self._tilemap)
        self._camera  = Camera(self._world_w, self._world_h)

        self._spawn_entities()
        self._camera.follow(self._local_entity)

        if self.is_host:
            self.game.events.subscribe("entity_damaged", self._on_damage_host)

    def on_exit(self):
        if self.is_host:
            self.game.events.unsubscribe("entity_damaged", self._on_damage_host)
        if self.net:
            self.net.close()

    def _load_world(self):
        """Carrega o mesmo mapa do single player. Fallback em plataformas fixas."""
        try:
            from world.level import Level
            self._level   = Level(self.game, "assets/maps/world.tmx")
            self._tilemap = self._level.tilemap
            self._world_w = self._level.width
            self._world_h = self._level.height
        except Exception as e:
            print(f"[MP] Usando tilemap de fallback: {e}")
            self._level   = None
            self._tilemap = self._fallback_tilemap()
            self._world_w = 3200
            self._world_h = 800

    def _fallback_tilemap(self):
        tm = Tilemap(32)
        for gx in range(100):   # chão
            tm.add_tile(gx, 24)
        for gx in range(5, 15):
            tm.add_tile(gx, 19)
        for gx in range(25, 40):
            tm.add_tile(gx, 16)
        for gx in range(55, 70):
            tm.add_tile(gx, 19)
        return tm

    def _get_spawns(self):
        """
        Devolve (sp1, sp2) usando os spawn points reais do mapa TMX.
        sp1 = spawn "player" do mapa (mesmo do single player).
        sp2 = spawn "player2" se existir, senão sp1 deslocado 120px à direita.
        """
        default = {"x": 200.0, "y": 300.0}

        if self._level:
            pts = self._level.spawn_points
            p1_data = pts.get("player", [default])[0]
            p2_data = pts.get("player2", [])
            sp1 = (float(p1_data["x"]), float(p1_data["y"]))
            if p2_data:
                sp2 = (float(p2_data[0]["x"]), float(p2_data[0]["y"]))
            else:
                sp2 = (sp1[0] + 120.0, sp1[1])
        else:
            sp1 = (200.0, 680.0)
            sp2 = (320.0, 680.0)

        return sp1, sp2

    def _spawn_entities(self):
        sp1, sp2 = self._get_spawns()

        if self.game_mode == "coop":
            if self.is_host:
                self._local_entity  = Player(self.game, *sp1)
                self._remote_entity = Player(self.game, *sp2)
            else:
                self._local_entity  = Player(self.game, *sp2)
                self._remote_entity = RemotePlayer(self.game, *sp1)

        elif self.game_mode == "boss":
            if self.is_host:
                self._local_entity  = Player(self.game, *sp1)
                self._remote_entity = Boss(self.game, *sp2)
            else:
                self._local_entity  = Boss(self.game, *sp2)
                self._remote_entity = RemotePlayer(self.game, *sp1)

        self._entities = [self._local_entity, self._remote_entity]

    # ── Eventos ───────────────────────────────────────────────────────────────

    def handle_event(self, event):
        if event.type != pygame.KEYDOWN:
            return
        key = event.key

        if key == pygame.K_ESCAPE:
            if self._disconnected:
                self._quit_to_menu()
            else:
                self._paused = not self._paused
            return

        if self._paused:
            if key == pygame.K_q:
                self._quit_to_menu()
            return

        if isinstance(self._local_entity, Player):
            if key in (pygame.K_SPACE, pygame.K_UP, pygame.K_w):
                self._jump_pressed = True
                self._local_entity.jump_buffer = 0.10
        elif isinstance(self._local_entity, Boss):
            if key == pygame.K_UP:
                self._local_entity.apply_jump_event()

    # ── Update ────────────────────────────────────────────────────────────────

    def update(self, dt: float):
        if self._disconnected or self._paused:
            return
        self._tick += 1

        if self.is_host:
            self._update_host(dt)
        else:
            self._update_client(dt)

        self._camera.update(dt)
        # Nunca remove local/remote do jogo — apenas entidades auxiliares
        self._entities = [
            e for e in self._entities
            if e.alive or e is self._local_entity or e is self._remote_entity
        ]

    def _update_host(self, dt: float):
        # 1. Input local → entidade local
        keys = pygame.key.get_pressed()
        if isinstance(self._local_entity, Player):
            self._local_entity.update_input(keys)

        # 2. Input da rede → entidade remota no host
        # Cacheia o último input recebido para reaplicar quando não chega pacote novo,
        # garantindo que vel.x seja zerado ao soltar a tecla.
        client_msg = self.net.update(dt)
        if client_msg:
            self._last_client_input = client_msg
        if self._last_client_input and isinstance(self._remote_entity, (Player, Boss)):
            self._remote_entity.apply_net_input(self._last_client_input)

        self._spawn_pending_projectiles()

        if not self.net.connected:
            self._disconnected = True
            return

        # 3. Física e combate autoritativos
        self._physics.update(self._entities, dt)
        self._combat.update(self._entities, dt)

        # 4. Update lógico de todas as entidades
        for e in self._entities:
            e.update(dt)

        # 5. Respawn: se caiu abaixo do mundo, volta ao spawn com penalidade de HP
        self._check_respawn()

        # 6. Envia snapshot ao cliente
        self.net.broadcast_state(self._build_snapshot())

    def _update_client(self, dt: float):
        # 1. Envia input para o host (host é autoritativo — sem predição local)
        self.net.send_input(self._collect_net_input())

        # 2. Recebe estado autoritativo
        state, events = self.net.update(dt)

        if not self.net.connected:
            self._disconnected = True
            return

        # 3. Aplica estado à entidade remota e reconcilia local com p2
        if state:
            if isinstance(self._remote_entity, RemotePlayer):
                self._remote_entity.apply_state(state.get("p1", {}))
            self._reconcile_local(state.get("p2", {}))

        # 4. Processa eventos críticos
        for ev in events:
            self._apply_network_event(ev)

        # 5. Update lógico — animação, timers (sem física: host é autoritativo)
        for e in self._entities:
            e.update(dt)

    def _spawn_pending_projectiles(self):
        from entities.projectile import Projectile
        for p in (self._local_entity, self._remote_entity):
            if isinstance(p, Player) and getattr(p, '_spawn_projectile_callback', False):
                p._spawn_projectile_callback = False
                self._entities.append(
                    Projectile(game=self.game, x=p.pos.x, y=p.pos.y,
                               direction=p.facing, team=p.team)
                )

    def _collect_net_input(self) -> dict:
        if isinstance(self._local_entity, Boss):
            return self._local_entity.get_input_snapshot()
        keys = pygame.key.get_pressed()
        ju = int(self._jump_pressed)
        self._jump_pressed = False
        down = keys[pygame.K_s] or keys[pygame.K_DOWN]
        shift = keys[pygame.K_LSHIFT]
        return {
            "l":  int(keys[pygame.K_a]     or keys[pygame.K_LEFT]),
            "r":  int(keys[pygame.K_d]     or keys[pygame.K_RIGHT]),
            "ju": ju,
            "da": int(shift and not down),
            "at": int(keys[pygame.K_z]),
            "rn": int(keys[pygame.K_x] or keys[pygame.K_k]),
            "pl": int(shift and down),
            "pa": int(keys[pygame.K_c] or keys[pygame.K_l]),
        }

    # ── Snapshot ──────────────────────────────────────────────────────────────

    def _build_snapshot(self) -> dict:
        return {
            "p1": self._entity_state(self._local_entity),
            "p2": self._entity_state(self._remote_entity),
        }

    def _check_respawn(self):
        """Host: reposiciona entidades que caíram abaixo do mundo."""
        sp1, sp2 = self._get_spawns()
        spawns = {
            self._local_entity:  sp1,
            self._remote_entity: sp2,
        }
        for entity, sp in spawns.items():
            if entity and entity.pos.y > self._world_h + 300:
                entity.pos.x = float(sp[0])
                entity.pos.y = float(sp[1])
                entity.vel.x = 0.0
                entity.vel.y = 0.0
                entity.alive = True
                hp = entity.get(Health)
                if hp:
                    hp.current = max(10, hp.current - 20)
                    hp.invicible = 1.0

    def _reconcile_local(self, s: dict):
        """
        Aplica estado autoritativo do host à entidade local do cliente.
        Em LAN a latência é < 5 ms — snapeia direto sem threshold para
        eliminar qualquer acúmulo de desincronização.
        """
        e = self._local_entity
        if not e or not s:
            return
        e.pos.x = s.get("x", e.pos.x)
        e.pos.y = s.get("y", e.pos.y)
        e.vel.x = s.get("vx", e.vel.x)
        e.vel.y = s.get("vy", e.vel.y)
        hp = e.get(Health)
        if hp and "hp" in s:
            hp.current = s["hp"]

    def _entity_state(self, e) -> dict:
        if e is None:
            return {}
        hp = e.get(Health)
        from components.animation import AnimationController
        anim = e.get(AnimationController)
        anim_name = anim._current if anim and anim._current else "idle"
        return {
            "x":      e.pos.x,
            "y":      e.pos.y,
            "vx":     e.vel.x,
            "vy":     e.vel.y,
            "facing": getattr(e, "facing", 1),
            "hp":     hp.current if hp else 0,
            "anim":   anim_name,
        }

    # ── Eventos críticos ──────────────────────────────────────────────────────

    def _on_damage_host(self, entity, amount, remaining):
        """Callback no host: replica dano ao cliente com ACK."""
        if entity is self._local_entity:
            target = "p1"
        elif entity is self._remote_entity:
            target = "p2"
        else:
            return
        self.net.send_event("dmg", target=target,
                            amount=amount, remaining=remaining)

    def _apply_network_event(self, ev: dict):
        ev_type = ev.get("ev")
        if ev_type == "dmg":
            target_key = ev.get("target")
            remaining  = ev.get("remaining", 0)
            # "p2" no snapshot do host = entidade local do cliente
            entity = (self._local_entity
                      if target_key == "p2"
                      else self._remote_entity)
            if entity:
                hp = entity.get(Health)
                if hp:
                    hp.current = float(remaining)
                    hp.invicible = 0.3

        elif ev_type == "ability":
            ability = ev.get("name")
            if ability and hasattr(self._local_entity, "abilities"):
                self._local_entity.abilities[ability] = True

    # ── Draw ──────────────────────────────────────────────────────────────────

    def draw(self, surface):
        surface.fill((15, 12, 25))

        if self._level:
            self._level.draw_layer(surface, "background", self._camera)

        if self._tilemap:
            self._tilemap.draw(surface, self._camera)

        self._render.draw_entities(surface, self._entities, self._camera)
        self._draw_player_labels(surface)

        if self._level:
            self._level.draw_layer(surface, "foreground", self._camera)

        self._draw_hud(surface)
        self._draw_net_info(surface)

        if self._paused:
            self._draw_pause_overlay(surface)
        elif self._disconnected:
            self._draw_disconnect_overlay(surface)

    def _draw_player_labels(self, surface):
        f = pygame.font.SysFont("consolas,monospace", 14, bold=True)
        for entity, label, color in (
            (self._local_entity,  "VOCÊ",   (80, 255, 120)),
            (self._remote_entity, "P1" if self.is_host else "P2", (100, 180, 255)),
        ):
            if entity is None:
                continue
            sx, sy = self._camera.apply(entity.pos)
            txt = f.render(label, True, color)
            surface.blit(txt, (int(sx) - txt.get_width() // 2, int(sy) - 58))

    def _draw_hud(self, surface):
        hp_local = self._local_entity.get(Health) if self._local_entity else None
        if hp_local:
            _bar(surface, 20, 20, 200, 16,
                 hp_local.current, hp_local.max_hp,
                 (220, 50, 50), (60, 20, 20))
            if hasattr(self._local_entity, "abilities"):
                _draw_abilities(surface, self._local_entity.abilities, 20, 46)

        hp_remote = self._remote_entity.get(Health) if self._remote_entity else None
        if hp_remote:
            W = surface.get_width()
            bw = 200
            label  = "P2" if self.game_mode == "coop" else "BOSS"
            color  = (50, 50, 220) if self.game_mode == "coop" else (220, 50, 50)
            _bar(surface, W - bw - 20, 20, bw, 16,
                 hp_remote.current, hp_remote.max_hp, color, (20, 20, 60))
            f = pygame.font.SysFont("consolas,monospace", 14)
            lbl = f.render(label, True, (180, 180, 180))
            surface.blit(lbl, (W - bw - 20 - lbl.get_width() - 6, 22))

    def _draw_net_info(self, surface):
        W, H = surface.get_size()
        f = pygame.font.SysFont("consolas,monospace", 13)
        role = "HOST" if self.is_host else "CLIENT"
        txt = f.render(f"{role}  {self.game_mode.upper()}", True, (80, 80, 100))
        surface.blit(txt, (W - txt.get_width() - 8, H - 20))

    def _draw_pause_overlay(self, surface):
        W, H = surface.get_size()
        ov = pygame.Surface((W, H), pygame.SRCALPHA)
        ov.fill((0, 0, 0, 160))
        surface.blit(ov, (0, 0))
        f1 = pygame.font.SysFont("consolas,monospace", 42)
        f2 = pygame.font.SysFont("consolas,monospace", 22)
        t1 = f1.render("PAUSADO", True, (255, 255, 255))
        t2 = f2.render("ESC — continuar     Q — sair ao menu", True, (180, 180, 180))
        surface.blit(t1, (W // 2 - t1.get_width() // 2, H // 2 - 50))
        surface.blit(t2, (W // 2 - t2.get_width() // 2, H // 2 + 16))

    def _draw_disconnect_overlay(self, surface):
        W, H = surface.get_size()
        ov = pygame.Surface((W, H), pygame.SRCALPHA)
        ov.fill((0, 0, 0, 170))
        surface.blit(ov, (0, 0))
        f1 = pygame.font.SysFont("consolas,monospace", 38)
        f2 = pygame.font.SysFont("consolas,monospace", 22)
        t1 = f1.render("Conexão Perdida", True, (255, 80, 80))
        t2 = f2.render("Pressione ESC para voltar ao menu", True, (200, 200, 200))
        surface.blit(t1, (W // 2 - t1.get_width() // 2, H // 2 - 40))
        surface.blit(t2, (W // 2 - t2.get_width() // 2, H // 2 + 20))

    def _quit_to_menu(self):
        from states.main_menu import MainMenu
        self.game.states.change(MainMenu(self.game))


# ── Utilitários de HUD ────────────────────────────────────────────────────────

def _bar(surf, x, y, w, h, cur, mx, fg, bg):
    pygame.draw.rect(surf, bg, (x, y, w, h), border_radius=4)
    fill = int(w * (max(0.0, cur) / max(mx, 1)))
    if fill:
        pygame.draw.rect(surf, fg, (x, y, fill, h), border_radius=4)
    pygame.draw.rect(surf, (255, 255, 255), (x, y, w, h), 1, border_radius=4)


def _draw_abilities(surf, abilities, x, y):
    for unlocked in abilities.values():
        col = (200, 200, 60) if unlocked else (50, 50, 50)
        pygame.draw.rect(surf, col, (x, y, 18, 18), 0 if unlocked else 1)
        x += 24
