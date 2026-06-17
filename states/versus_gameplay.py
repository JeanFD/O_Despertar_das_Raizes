# states/versus_gameplay.py
"""
Estado de gameplay do modo Versus 1v1.

Arquitetura idêntica ao co-op:
- Host autoritativo. Cliente envia inputs e renderiza estado recebido.
- Reusa a MESMA classe Player (entities/player.py). Apenas atribuímos
  `team_id` distinto por jogador (p1/p2) para que o CombatSystem
  permita dano entre eles. Qualquer evolução futura no Player vale
  automaticamente para o versus.
- Reusa PhysicsSystem, CombatSystem, RenderSystem, AnimationController.
- A engine de regras (rounds, score, timer) está em engine/versus_match.py.

Diagrama de papéis:

    HOST                                CLIENT
    ──────────────────────────────────  ──────────────────────────────────
    local  = Player(team="p1")          local  = Player(team="p2")
    remote = Player(team="p2")          remote = RemotePlayer (interp.)
    ↳ controla pelo teclado             ↳ controla pelo teclado
    ↳ recebe input do cliente           ↳ envia input ao host
    Roda física + combate.              Recebe snapshots do host.
    Roda VersusMatch (autoritativo).    Aplica match snapshot recebido.
    Emite eventos críticos com ACK.     Replica pontuação/banners.
"""

import pygame
from states.base_state import BaseState
from entities.player import Player
from entities.remote_player import RemotePlayer
from systems.physics_system import PhysicsSystem
from systems.combat_system import CombatSystem
from systems.render_system import RenderSystem
from engine.camera import Camera
from engine.versus_match import (
    VersusMatch,
    PHASE_READY, PHASE_COUNTDOWN, PHASE_FIGHTING,
    PHASE_ROUND_END, PHASE_MATCH_END,
)
from world.arena import (
    ARENA_TMX_PATH,
    build_fallback_tilemap, default_spawns, default_size, ringout_y_for,
)
from components.health import Health


class VersusGameplayState(BaseState):

    def __init__(self, game, net, is_host: bool, best_of: int = 3,
                 player_id: int = None):
        super().__init__(game)
        self.net       = net
        self.is_host   = is_host
        self.best_of   = best_of
        # player_id define qual entidade é local quando is_host=False.
        # 1 → P1 é local (P2 é RemotePlayer); 2 → P2 é local (P1 é RemotePlayer).
        # Defaults para comportamento original do modo P2P.
        self._player_id = player_id if player_id is not None else (1 if is_host else 2)

        # Posse da conexão. Por default este state fecha net em on_exit;
        # quando transferimos a conexão para o pós-partida (revanche) ou
        # para qualquer outro state que reutiliza a mesma sessão, marcamos
        # _owns_net=False antes de chamar states.change(...).
        self._owns_net = True

        # Após match_winner ser decidido, esperamos esse delay no MATCH_END
        # antes de empurrar o lobby pós-partida (host emite evento p/ sincr).
        self._post_match_delay = 4.0
        self._went_to_post = False

        self._physics  = None
        self._combat   = CombatSystem()
        self._render   = RenderSystem()
        self._camera   = None
        self._tilemap  = None
        self._level    = None

        # Preenchidos por _load_world(); fallback caso o TMX falhe.
        self._world_w, self._world_h = default_size()
        self._sp1, self._sp2 = default_spawns()

        # Personagens — sempre 2 Players (mesma classe do single).
        # No host: P1 é local; P2 é remoto controlado por input da rede.
        # No cliente: P2 é local; P1 é RemotePlayer (interpolado).
        self._p1 = None
        self._p2 = None
        self._local_entity  = None   # 'p1' ou 'p2' do host/client
        self._remote_entity = None   # contraparte
        self._entities      = []

        # Match: somente o host roda autoritativamente. O cliente recebe
        # snapshot a cada frame e mantém apenas para renderizar HUD.
        self.match = VersusMatch(best_of=best_of)

        # Banner transitório no cliente (mostra "K.O.!", "WINNER", etc.)
        self._banner_text  = ""
        self._banner_color = (255, 255, 255)
        self._banner_timer = 0.0

        self._jump_pressed = False
        self._last_client_input: dict = {}
        self._disconnected = False
        self._paused = False
        self._tick = 0

        # Cliente: net_id → RemoteProjectile para sync via snapshot.
        self._remote_projectiles: dict = {}

        # Sequência monotônica de inputs do cliente (envio).
        # Host ecoa o último processado em snapshots ("ack") — base para
        # predição/reconciliação futura sobre WAN.
        self._input_tick = 0
        # Host: último tick recebido do cliente, devolvido no snapshot.
        self._last_ack_tick = 0

    # ── Ciclo de vida ─────────────────────────────────────────────────────────

    def on_enter(self):
        self._load_world()
        self._physics = PhysicsSystem(self._tilemap)
        self._camera  = Camera(self._world_w, self._world_h)
        # Câmera fixa: arena cabe em uma tela. Sem follow().

        self._spawn_entities()
        self._set_banner_for_phase()

    def _load_world(self):
        """Carrega o mapa da arena via TMX. Se falhar, usa fallback Python."""
        try:
            from world.level import Level
            self._level   = Level(self.game, ARENA_TMX_PATH)
            self._tilemap = self._level.tilemap
            self._world_w = self._level.width
            self._world_h = self._level.height
            self._sp1, self._sp2 = self._spawns_from_level(self._level)
        except Exception as e:
            print(f"[VS] arena.tmx indisponível, usando fallback: {e}")
            self._level   = None
            self._tilemap = build_fallback_tilemap()
            # Dimensões e spawns ficam com os defaults definidos no __init__.

    def _spawns_from_level(self, level):
        """Lê spawns 'player' (P1) e 'player2' (P2) do object group do TMX."""
        sp1, sp2 = default_spawns()
        pts = level.spawn_points
        if pts.get("player"):
            p = pts["player"][0]
            sp1 = (float(p["x"]), float(p["y"]))
        if pts.get("player2"):
            p = pts["player2"][0]
            sp2 = (float(p["x"]), float(p["y"]))
        return sp1, sp2

    def on_exit(self):
        if self._owns_net and self.net:
            self.net.close()

    # ── Spawn / reset ─────────────────────────────────────────────────────────

    def _spawn_entities(self):
        self._p1 = Player(self.game, *self._sp1, team_id="p1")
        self._p1.facing = 1
        self._p2 = Player(self.game, *self._sp2, team_id="p2")
        self._p2.facing = -1

        if not self.is_host:
            # Quem é RemotePlayer depende de qual player_id este cliente tem.
            if self._player_id == 1:
                # Sou P1 local → P2 é remoto
                self._p2 = RemotePlayer(self.game, *self._sp2)
                self._p2.team = "p2"
            else:
                # Sou P2 local → P1 é remoto (comportamento P2P original)
                self._p1 = RemotePlayer(self.game, *self._sp1)
                self._p1.team = "p1"

        if self.is_host or self._player_id == 1:
            self._local_entity, self._remote_entity = self._p1, self._p2
        else:
            self._local_entity, self._remote_entity = self._p2, self._p1

        self._entities = [self._p1, self._p2]
        self._unlock_all_abilities()

    def _unlock_all_abilities(self):
        """Versus: ambos jogadores começam com todas as habilidades liberadas.
        O default do Player.__init__ tem algumas em False (para progressão
        single player); aqui forçamos paridade total."""
        for e in (self._p1, self._p2):
            if isinstance(e, Player):
                for ability in e.abilities:
                    e.abilities[ability] = True

    def _reset_round(self):
        """Host: reposiciona ambos os players para um novo round."""
        if isinstance(self._p1, Player):
            self._p1.reset_for_round(*self._sp1, facing=1)
        if isinstance(self._p2, Player):
            self._p2.reset_for_round(*self._sp2, facing=-1)

    # ── Eventos de input ──────────────────────────────────────────────────────

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

        if not self.match.can_act:
            return

        if isinstance(self._local_entity, Player):
            if key in (pygame.K_SPACE, pygame.K_UP, pygame.K_w):
                self._jump_pressed = True
                self._local_entity.jump_buffer = 0.10

    # ── Update ────────────────────────────────────────────────────────────────

    def update(self, dt: float):
        if self._disconnected or self._paused:
            return
        self._tick += 1
        self._banner_timer = max(0.0, self._banner_timer - dt)

        if self.is_host:
            self._update_host(dt)
        else:
            self._update_client(dt)

        self._camera.update(dt)

    def _update_host(self, dt: float):
        # 1) Inputs (somente válidos durante FIGHTING)
        if self.match.can_act:
            keys = pygame.key.get_pressed()
            if isinstance(self._local_entity, Player):
                self._local_entity.update_input(keys)

            client_msg = self.net.update(dt)
            if client_msg:
                self._last_client_input = client_msg
                # Captura tick — base para futura reconciliação. Ignora
                # pacotes antigos (out-of-order UDP) para nunca regredir.
                tk = client_msg.get("tk", 0)
                if tk > self._last_ack_tick:
                    self._last_ack_tick = tk
            if self._last_client_input and isinstance(self._remote_entity, Player):
                self._remote_entity.apply_net_input(self._last_client_input)

            self._spawn_pending_projectiles()
        else:
            # Drena a fila para não acumular, mas zera velocidades
            self.net.update(dt)
            for e in (self._p1, self._p2):
                if isinstance(e, Player):
                    e.vel.x = 0.0

        if not self.net.connected:
            self._disconnected = True
            return

        # 2) Física e combate só durante FIGHTING (e ROUND_END p/ inércia visual)
        if self.match.phase in (PHASE_FIGHTING, PHASE_ROUND_END):
            self._physics.update(self._entities, dt)
        if self.match.phase == PHASE_FIGHTING:
            self._combat.update(self._entities, dt)

        for e in self._entities:
            e.update(dt)

        # 3) Ring-out: cair abaixo do mundo zera HP (conta como KO)
        if self.match.phase == PHASE_FIGHTING:
            self._check_ringout()

        # 4) Avança a engine de regras
        result = self.match.tick(
            dt,
            self._p1.alive, self._hp_of(self._p1),
            self._p2.alive, self._hp_of(self._p2),
        )

        # 5) Replica eventos críticos ao cliente e aplica side-effects locais
        for tr in result["transitions"]:
            self.net.send_event(tr["ev"], **{k: v for k, v in tr.items() if k != "ev"})
            self._apply_transition_local(tr)

        # 6) Snapshot autoritativo
        self.net.broadcast_state(self._build_snapshot())

        # 7) Após o banner final, host conduz ambos para o lobby pós-partida
        if (self.match.phase == PHASE_MATCH_END
                and not self._went_to_post):
            self._post_match_delay -= dt
            if self._post_match_delay <= 0:
                self._went_to_post = True
                self.net.send_event(
                    "go_post_match",
                    s1=self.match.score_p1,
                    s2=self.match.score_p2,
                    winner=self.match.match_winner or 0,
                    bo=self.best_of,
                )
                self._goto_post_match(
                    self.match.score_p1,
                    self.match.score_p2,
                    self.match.match_winner or 0,
                )

    def _update_client(self, dt: float):
        # 1) Envia input local somente durante FIGHTING
        if self.match.can_act:
            self.net.send_input(self._collect_net_input())
            # Predição cosmética: vira o sprite local imediatamente baseado
            # nas teclas, sem esperar o snapshot. Reconcile sobrescreve no
            # próximo snapshot — qualquer divergência some em ~1 frame.
            self._predict_local_facing()
        else:
            self._last_client_input = {}

        # 2) Recebe estado e eventos
        state, events = self.net.update(dt)

        if not self.net.connected:
            self._disconnected = True
            return

        # 3) Aplica estado — usa player_id para saber qual chave é "local"
        if state:
            if self._player_id == 1:
                self._reconcile_local(state.get("p1", {}))
                if isinstance(self._p2, RemotePlayer):
                    self._p2.apply_state(state.get("p2", {}))
            else:
                if isinstance(self._p1, RemotePlayer):
                    self._p1.apply_state(state.get("p1", {}))
                self._reconcile_local(state.get("p2", {}))
            self._sync_remote_projectiles(state.get("proj", []))
            mstate = state.get("match")
            if mstate:
                self.match.apply_dict(mstate)
                self._set_banner_for_phase()

        # 4) Eventos críticos
        for ev in events:
            self._apply_network_event(ev)

        # 5) Update lógico
        for e in self._entities:
            e.update(dt)

    def _spawn_pending_projectiles(self):
        from entities.projectile import Projectile
        for p in (self._p1, self._p2):
            if isinstance(p, Player) and getattr(p, '_spawn_projectile_callback', False):
                p._spawn_projectile_callback = False
                self._entities.append(
                    Projectile(game=self.game, x=p.pos.x, y=p.pos.y,
                               direction=p.facing, team=p.team)
                )
        self._entities = [e for e in self._entities if getattr(e, 'alive', True)]

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _hp_of(self, e) -> float:
        hp = e.get(Health) if e else None
        return float(hp.current) if hp else 0.0

    def _check_ringout(self):
        threshold = ringout_y_for(self._world_h)
        for e in (self._p1, self._p2):
            if e and e.pos.y > threshold:
                hp = e.get(Health)
                if hp:
                    hp.current = 0
                e.alive = False

    def _collect_net_input(self) -> dict:
        """Empacota o estado bruto do teclado + número de tick.

        Decisões (dash vs plunge, edge detection) NÃO são feitas aqui — o
        host roda update_input em ambos os players, garantindo paridade.
        Esse formato também é amigável a futura predição/reconciliação
        (basta o cliente bufferizar (tk, dict) e re-aplicar).
        """
        keys = pygame.key.get_pressed()
        ju = int(self._jump_pressed)
        self._jump_pressed = False
        self._input_tick += 1
        return {
            "tk": self._input_tick,
            "l":  int(keys[pygame.K_a]      or keys[pygame.K_LEFT]),
            "r":  int(keys[pygame.K_d]      or keys[pygame.K_RIGHT]),
            "dn": int(keys[pygame.K_s]      or keys[pygame.K_DOWN]),
            "sh": int(keys[pygame.K_LSHIFT]),
            "at": int(keys[pygame.K_z]      or keys[pygame.K_j]),
            "rn": int(keys[pygame.K_x]      or keys[pygame.K_k]),
            "pa": int(keys[pygame.K_c]      or keys[pygame.K_l]),
            "ju": ju,
        }

    def _build_snapshot(self) -> dict:
        from entities.projectile import Projectile
        proj = [e.to_net() for e in self._entities
                if isinstance(e, Projectile) and e.alive]
        return {
            "p1":    self._entity_state(self._p1),
            "p2":    self._entity_state(self._p2),
            "proj":  proj,
            "match": self.match.to_dict(),
            # Eco do último tick de input do cliente processado.
            # Cliente usa para descartar inputs já confirmados ao reconciliar.
            "ack":   self._last_ack_tick,
        }

    def _entity_state(self, e) -> dict:
        if e is None:
            return {}
        hp = e.get(Health)
        from components.animation import AnimationController
        anim = e.get(AnimationController)
        anim_name = anim._current if anim and anim._current else "idle"
        state = {
            "x":      e.pos.x,
            "y":      e.pos.y,
            "vx":     e.vel.x,
            "vy":     e.vel.y,
            "facing": getattr(e, "facing", 1),
            "hp":     hp.current if hp else 0,
            "anim":   anim_name,
            "alive":  bool(getattr(e, "alive", True)),
        }
        if isinstance(e, Player):
            state["dbg"] = e.debug_snapshot()
            state["sta"] = e.stamina
        return state

    def _predict_local_facing(self):
        """Atualiza apenas facing do jogador local, sem tocar em timers ou
        hitboxes (que continuam autoritativos no host). Pequena predição
        cosmética para o sprite virar na hora no cliente."""
        e = self._local_entity
        if not isinstance(e, Player):
            return
        keys = pygame.key.get_pressed()
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            e.facing = 1
        elif keys[pygame.K_LEFT] or keys[pygame.K_a]:
            e.facing = -1

    def _reconcile_local(self, s: dict):
        """Snapeia direto o estado autoritativo do host na entidade local."""
        e = self._local_entity
        if not e or not s:
            return
        e.pos.x = s.get("x", e.pos.x)
        e.pos.y = s.get("y", e.pos.y)
        e.vel.x = s.get("vx", e.vel.x)
        e.vel.y = s.get("vy", e.vel.y)
        e.facing = s.get("facing", getattr(e, "facing", 1))
        e.alive = s.get("alive", e.alive)
        hp = e.get(Health)
        if hp and "hp" in s:
            hp.current = s["hp"]
        if isinstance(e, Player):
            if "sta" in s:
                e.stamina = float(s["sta"])
            if "dbg" in s:
                e.apply_dbg(s["dbg"])
            if "anim" in s:
                e._authoritative_anim = s["anim"]

    def _sync_remote_projectiles(self, proj_list: list):
        """Cliente: replica projéteis autoritativos do host.

        Cria RemoteProjectile para ids novos, atualiza posição dos existentes,
        e marca como inativo os que sumiram do snapshot.
        """
        from entities.remote_projectile import RemoteProjectile
        seen = set()
        for s in proj_list:
            pid = s.get("id")
            if pid is None:
                continue
            seen.add(pid)
            rp = self._remote_projectiles.get(pid)
            if rp is None:
                rp = RemoteProjectile(self.game, s.get("x", 0.0), s.get("y", 0.0),
                                      int(s.get("d", 1)), pid)
                self._remote_projectiles[pid] = rp
                self._entities.append(rp)
            else:
                rp.apply_state(s)

        for pid in list(self._remote_projectiles.keys()):
            if pid not in seen:
                rp = self._remote_projectiles.pop(pid)
                rp.alive = False
        self._entities = [e for e in self._entities if getattr(e, 'alive', True)
                          or e is self._p1 or e is self._p2]

    # ── Transições / eventos ──────────────────────────────────────────────────

    def _apply_transition_local(self, tr: dict):
        ev = tr.get("ev")
        if ev == "round_start":
            self._banner_set("FIGHT!", (255, 230, 90), 1.4)
        elif ev == "round_end":
            self._banner_set(self._round_end_text(tr), (255, 80, 80), 2.2)
        elif ev == "next_round":
            # Host reseta os personagens — cliente recebe via reconcile.
            self._reset_round()
            self._banner_set(f"ROUND {tr.get('round', '?')}", (200, 220, 255), 1.2)
        elif ev == "match_end":
            w = tr.get("winner")
            if w == 0:
                self._banner_set("DRAW", (200, 200, 200), 999)
            else:
                self._banner_set(f"PLAYER {w} WINS", (255, 220, 60), 999)

    def _apply_network_event(self, ev: dict):
        """Cliente: recebe transições e gera banners equivalentes."""
        ev_type = ev.get("ev")
        if ev_type == "round_start":
            self._banner_set("FIGHT!", (255, 230, 90), 1.4)
        elif ev_type == "round_end":
            self._banner_set(self._round_end_text(ev), (255, 80, 80), 2.2)
        elif ev_type == "next_round":
            self._banner_set(f"ROUND {ev.get('round', '?')}", (200, 220, 255), 1.2)
        elif ev_type == "match_end":
            w = ev.get("winner")
            if w == 0:
                self._banner_set("DRAW", (200, 200, 200), 999)
            else:
                self._banner_set(f"PLAYER {w} WINS", (255, 220, 60), 999)
        elif ev_type == "go_post_match":
            if not self._went_to_post:
                self._went_to_post = True
                self._goto_post_match(
                    int(ev.get("s1", 0)),
                    int(ev.get("s2", 0)),
                    int(ev.get("winner", 0)),
                    best_of_override=int(ev.get("bo", self.best_of)),
                )

    def _round_end_text(self, info: dict) -> str:
        winner = info.get("winner", 0)
        if winner == 0:
            return "DOUBLE K.O."
        return f"K.O. — P{winner}"

    def _banner_set(self, text: str, color, duration: float):
        self._banner_text  = text
        self._banner_color = color
        self._banner_timer = duration

    def _set_banner_for_phase(self):
        """Define banner adequado às fases não-críticas (READY/COUNTDOWN)."""
        if self.match.phase == PHASE_READY:
            self._banner_set(f"ROUND {self.match.round_idx}", (200, 220, 255), 1.2)

    # ── Draw ──────────────────────────────────────────────────────────────────

    def draw(self, surface):
        surface.fill((18, 14, 30))
        self._draw_arena_bg(surface)

        if self._level:
            self._level.draw_layer(surface, "background", self._camera)

        if self._tilemap:
            self._tilemap.draw(surface, self._camera)

        self._render.draw_entities(surface, self._entities, self._camera)
        self._draw_player_labels(surface)

        if self._level:
            self._level.draw_layer(surface, "foreground", self._camera)

        self._draw_hud(surface)
        self._draw_phase_overlay(surface)
        self._draw_net_info(surface)

        if self._paused:
            self._draw_pause_overlay(surface)
        elif self._disconnected:
            self._draw_disconnect_overlay(surface)

    def _draw_arena_bg(self, surface):
        W, H = surface.get_size()
        for i in range(8):
            y = int(H * (i / 8.0))
            c = 22 + i * 4
            pygame.draw.rect(surface, (c, c // 2 + 10, c + 12), (0, y, W, H // 8 + 1))

    def _draw_player_labels(self, surface):
        f = pygame.font.SysFont("consolas,monospace", 14, bold=True)
        for entity, label, color in (
            (self._p1, "P1", (120, 200, 255)),
            (self._p2, "P2", (255, 160, 120)),
        ):
            if entity is None:
                continue
            sx, sy = self._camera.apply(entity.pos)
            txt = f.render(label, True, color)
            surface.blit(txt, (int(sx) - txt.get_width() // 2, int(sy) - 64))

    def _draw_hud(self, surface):
        W, _ = surface.get_size()

        # Barras de HP
        hp1 = self._p1.get(Health) if self._p1 else None
        hp2 = self._p2.get(Health) if self._p2 else None
        if hp1:
            _bar(surface, 24, 24, 360, 22,
                 hp1.current, hp1.max_hp,
                 (90, 200, 255), (10, 30, 50), label="P1")
        if hp2:
            _bar(surface, W - 24 - 360, 24, 360, 22,
                 hp2.current, hp2.max_hp,
                 (255, 140, 90), (50, 25, 10), label="P2", reverse=True)

        # Barras de stamina (logo abaixo da HP, mais finas)
        if isinstance(self._p1, Player):
            _bar(surface, 24, 50, 360, 7,
                 self._p1.stamina, self._p1.max_stamina,
                 (90, 220, 230), (15, 35, 50))
        if isinstance(self._p2, Player):
            _bar(surface, W - 24 - 360, 50, 360, 7,
                 self._p2.stamina, self._p2.max_stamina,
                 (255, 200, 120), (45, 30, 15), reverse=True)

        # Score (●○○) — placar de rounds (empurrado abaixo da stamina)
        _draw_score_dots(surface, 24, 66,
                         self.match.score_p1, self.match.rounds_to_win,
                         (90, 200, 255))
        _draw_score_dots(surface, W - 24 - self.match.rounds_to_win * 22, 66,
                         self.match.score_p2, self.match.rounds_to_win,
                         (255, 140, 90))

        # Round # e timer central
        f_round = pygame.font.SysFont("consolas,monospace", 16, bold=True)
        rt = f_round.render(f"ROUND {self.match.round_idx} / {self.match.best_of}",
                            True, (220, 220, 240))
        surface.blit(rt, (W // 2 - rt.get_width() // 2, 16))

        if self.match.phase == PHASE_FIGHTING:
            time_left = max(0.0, self.match.fight_left)
            color = (220, 220, 220) if time_left > 10 else (255, 80, 80)
            f_t = pygame.font.SysFont("consolas,monospace", 36, bold=True)
            tt = f_t.render(f"{int(time_left):02d}", True, color)
            surface.blit(tt, (W // 2 - tt.get_width() // 2, 36))

    def _draw_phase_overlay(self, surface):
        W, H = surface.get_size()
        phase = self.match.phase

        # Banner persistente (FIGHT, K.O., WINNER, ROUND N)
        if self._banner_timer > 0 and self._banner_text:
            f = pygame.font.SysFont("consolas,monospace", 64, bold=True)
            t = f.render(self._banner_text, True, self._banner_color)
            shadow = f.render(self._banner_text, True, (0, 0, 0))
            x = W // 2 - t.get_width() // 2
            y = H // 2 - 40
            surface.blit(shadow, (x + 3, y + 3))
            surface.blit(t, (x, y))

        # Countdown 3, 2, 1
        if phase == PHASE_COUNTDOWN:
            n = max(1, int(self.match.timer + 0.999))
            n = min(n, 3)
            big = pygame.font.SysFont("consolas,monospace", 140, bold=True)
            t = big.render(str(n), True, (255, 220, 60))
            sh = big.render(str(n), True, (0, 0, 0))
            x = W // 2 - t.get_width() // 2
            y = H // 2 - t.get_height() // 2 - 40
            surface.blit(sh, (x + 4, y + 4))
            surface.blit(t, (x, y))

        if phase == PHASE_MATCH_END:
            ov = pygame.Surface((W, H), pygame.SRCALPHA)
            ov.fill((0, 0, 0, 140))
            surface.blit(ov, (0, 0))
            big = pygame.font.SysFont("consolas,monospace", 64, bold=True)
            small = pygame.font.SysFont("consolas,monospace", 22)
            mw = self.match.match_winner
            txt = "DRAW"
            color = (220, 220, 220)
            if mw == 1:
                txt = "PLAYER 1 WINS"
                color = (90, 200, 255)
            elif mw == 2:
                txt = "PLAYER 2 WINS"
                color = (255, 140, 90)
            t1 = big.render(txt, True, color)
            t2 = small.render(
                f"{self.match.score_p1} — {self.match.score_p2}     ESC para sair",
                True, (220, 220, 230)
            )
            surface.blit(t1, (W // 2 - t1.get_width() // 2, H // 2 - 40))
            surface.blit(t2, (W // 2 - t2.get_width() // 2, H // 2 + 36))

    def _draw_net_info(self, surface):
        W, H = surface.get_size()
        f = pygame.font.SysFont("consolas,monospace", 13)
        role = "HOST" if self.is_host else f"P{self._player_id}"
        txt = f.render(f"{role}  VERSUS", True, (90, 90, 110))
        surface.blit(txt, (W - txt.get_width() - 8, H - 20))

    def _draw_pause_overlay(self, surface):
        W, H = surface.get_size()
        ov = pygame.Surface((W, H), pygame.SRCALPHA)
        ov.fill((0, 0, 0, 160))
        surface.blit(ov, (0, 0))
        f1 = pygame.font.SysFont("consolas,monospace", 42, bold=True)
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
        f1 = pygame.font.SysFont("consolas,monospace", 38, bold=True)
        f2 = pygame.font.SysFont("consolas,monospace", 22)
        t1 = f1.render("Conexão Perdida", True, (255, 80, 80))
        t2 = f2.render("Pressione ESC para voltar ao menu", True, (200, 200, 200))
        surface.blit(t1, (W // 2 - t1.get_width() // 2, H // 2 - 40))
        surface.blit(t2, (W // 2 - t2.get_width() // 2, H // 2 + 20))

    def _quit_to_menu(self):
        # Saída explícita: este state mantém a posse do net e o on_exit fecha.
        from states.main_menu import MainMenu
        self.game.states.change(MainMenu(self.game))

    def _goto_post_match(self, s1: int, s2: int, winner: int,
                         best_of_override: int | None = None):
        """Transfere a conexão para o lobby pós-partida."""
        from states.versus_post_match import VersusPostMatchState
        bo = best_of_override if best_of_override is not None else self.best_of
        post = VersusPostMatchState(
            self.game,
            net=self.net,
            is_host=self.is_host,
            best_of=bo,
            score_p1=s1,
            score_p2=s2,
            winner=winner,
        )
        # Transferimos a posse do net antes da troca; on_exit deste state
        # NÃO deve fechar a conexão pois o pós-partida vai reusá-la.
        self._owns_net = False
        self.game.states.change(post)


# ── Helpers de HUD ────────────────────────────────────────────────────────────

def _bar(surf, x, y, w, h, cur, mx, fg, bg, label="", reverse=False):
    pygame.draw.rect(surf, bg, (x, y, w, h), border_radius=4)
    fill = int(w * (max(0.0, cur) / max(mx, 1)))
    if fill:
        if reverse:
            pygame.draw.rect(surf, fg, (x + w - fill, y, fill, h), border_radius=4)
        else:
            pygame.draw.rect(surf, fg, (x, y, fill, h), border_radius=4)
    pygame.draw.rect(surf, (240, 240, 240), (x, y, w, h), 2, border_radius=4)
    if label:
        f = pygame.font.SysFont("consolas,monospace", 13, bold=True)
        t = f.render(label, True, (240, 240, 240))
        if reverse:
            surf.blit(t, (x + w - t.get_width() - 6, y + h // 2 - t.get_height() // 2))
        else:
            surf.blit(t, (x + 6, y + h // 2 - t.get_height() // 2))


def _draw_score_dots(surf, x, y, score, total, fg):
    radius = 7
    spacing = 22
    for i in range(total):
        cx = x + i * spacing + radius
        cy = y + radius
        if i < score:
            pygame.draw.circle(surf, fg, (cx, cy), radius)
            pygame.draw.circle(surf, (255, 255, 255), (cx, cy), radius, 1)
        else:
            pygame.draw.circle(surf, (40, 40, 60), (cx, cy), radius)
            pygame.draw.circle(surf, (90, 90, 120), (cx, cy), radius, 1)
