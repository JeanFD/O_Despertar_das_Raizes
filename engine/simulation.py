"""
Mundo simulável headless.

Encapsula a parte autoritativa do jogo (física, combate, regras de match)
em uma classe que NÃO depende de display/render/audio. Permite que o
mesmo código rode:

    - no cliente, para client-side prediction (cliente roda a própria
      simulação localmente e reconcilia com o servidor);
    - no servidor dedicado (headless), como fonte de verdade autoritativa.

Decisões de design:
    - tick(inputs, dt) é determinístico para um conjunto fixo de inputs.
      Usar FIXED_DT = 1/60 em ambos os lados garante mesmo resultado.
    - Não emite eventos do pygame, não toca pygame.mixer, não toca
      pygame.display. Importa apenas pygame.math/Rect (estruturas de dado).
    - Recebe `event_bus` injetado — sem ele, eventos viram no-op (servidor
      headless pode passar um EventBus dummy ou o real).
"""
from __future__ import annotations
from typing import Dict, List, Optional

from systems.physics_system import PhysicsSystem
from systems.combat_system import CombatSystem


class Simulation:
    """Estado autoritativo de uma partida em andamento.

    Uso típico no servidor:
        sim = Simulation(tilemap, world_h)
        sim.add_player("p1", spawn_x, spawn_y)
        sim.add_player("p2", spawn_x, spawn_y)
        # a cada tick:
        sim.tick({"p1": input_dict_p1, "p2": input_dict_p2}, 1/60)

    Uso no cliente (prediction):
        sim_local = Simulation(...)
        sim_local.tick({"p_local": ...}, dt)
        # ao receber snapshot autoritativo, faz rollback+replay
    """

    def __init__(self, tilemap, world_h: float):
        self.tilemap = tilemap
        self.world_h = world_h
        self.physics = PhysicsSystem(tilemap)
        self.combat = CombatSystem()
        self.entities: List = []
        self.players: Dict[str, object] = {}  # net_id → Player
        self.tick_count = 0
        # listeners pluggáveis. Mantém Simulation desacoplada do EventBus
        # do cliente — server passa funções simples.
        self.on_damage = None      # callable(entity, amount, remaining)
        self.on_died = None        # callable(entity)
        self.on_respawn = None     # callable(entity, x, y)

    # ── Composição ────────────────────────────────────────────────────────

    def add_entity(self, e):
        self.entities.append(e)
        return e

    def add_player(self, net_id: str, player):
        self.players[net_id] = player
        self.entities.append(player)
        return player

    def remove_dead(self, keep=()):
        """Filtra entidades mortas, preservando referências importantes."""
        self.entities = [
            e for e in self.entities
            if e.alive or e in keep or e in self.players.values()
        ]

    # ── Loop autoritativo ─────────────────────────────────────────────────

    def tick(self, inputs: Dict[str, dict], dt: float) -> dict:
        """Avança a simulação um passo. inputs é {net_id: input_dict}.

        Retorna um dict com transições do tick (eventos discretos a serem
        replicados aos clientes).
        """
        self.tick_count += 1
        transitions = []

        # 1. Aplicar inputs nos players autoritativos
        for net_id, player in self.players.items():
            inp = inputs.get(net_id)
            if inp is None:
                continue
            if hasattr(player, "apply_net_input"):
                player.apply_net_input(inp)

        # 2. Spawnar projéteis pendentes (callback marcado pelo input)
        self._spawn_pending_projectiles()

        # 3. Física e combate
        self.physics.update(self.entities, dt)
        self.combat.update(self.entities, dt)

        # 4. Update lógico
        for e in self.entities:
            e.update(dt)

        # 5. Ring-out: cai abaixo do mundo → morre
        for net_id, player in list(self.players.items()):
            if player.pos.y > self.world_h + 300:
                if player.alive:
                    player.alive = False
                    if self.on_died:
                        self.on_died(player)
                    transitions.append({"ev": "ringout", "id": net_id})

        # 6. Limpa mortos (preservando players p/ permitir respawn)
        self.remove_dead(keep=tuple(self.players.values()))

        return {"transitions": transitions, "tick": self.tick_count}

    def _spawn_pending_projectiles(self):
        from entities.projectile import Projectile
        for player in self.players.values():
            if getattr(player, "_spawn_projectile_callback", False):
                player._spawn_projectile_callback = False
                proj = Projectile(
                    game=getattr(player, "game", None),
                    x=player.pos.x, y=player.pos.y,
                    direction=player.facing, team=player.team,
                )
                self.entities.append(proj)

    # ── Serialização para snapshot ────────────────────────────────────────

    def snapshot(self) -> dict:
        """Estado compacto e serializável da simulação. Útil para o servidor
        gerar snapshots periódicos. O encoding final (msgpack/json/binário)
        vive em shared/snapshot.py."""
        from components.health import Health
        from components.animation import AnimationController
        from entities.projectile import Projectile

        players_state = {}
        for net_id, e in self.players.items():
            hp = e.get(Health)
            anim = e.get(AnimationController)
            anim_name = anim._current if anim and anim._current else "idle"
            st = {
                "x": round(e.pos.x, 2),
                "y": round(e.pos.y, 2),
                "vx": round(e.vel.x, 2),
                "vy": round(e.vel.y, 2),
                "fc": getattr(e, "facing", 1),
                "hp": hp.current if hp else 0,
                "an": anim_name,
                "al": bool(e.alive),
            }
            if hasattr(e, "debug_snapshot"):
                st["dbg"] = e.debug_snapshot()
            if hasattr(e, "stamina"):
                st["st"] = round(e.stamina, 1)
            players_state[net_id] = st

        proj_state = [
            e.to_net() for e in self.entities
            if isinstance(e, Projectile) and e.alive
        ]
        return {
            "t": self.tick_count,
            "pl": players_state,
            "pr": proj_state,
        }

    # ── Rollback (para client-side prediction) ────────────────────────────

    def capture_state(self) -> dict:
        """Captura snapshot completo + estado interno de cada player para
        permitir restauração exata. Usado pelo cliente quando precisa
        rebobinar e reaplicar inputs."""
        captured = {"tick": self.tick_count, "players": {}}
        for net_id, p in self.players.items():
            captured["players"][net_id] = {
                "x": p.pos.x, "y": p.pos.y,
                "vx": p.vel.x, "vy": p.vel.y,
                "facing": p.facing,
                "alive": p.alive,
            }
            # estado de timers/abilities — opcional, mas evita drift
            for attr in ("attack_timer", "dash_timer", "dash_cd",
                         "ranged_cd", "plunge_timer", "plunge_cd",
                         "parry_timer", "parry_cd", "stun_timer",
                         "jump_buffer", "coyote_timer", "stamina",
                         "jumps_left", "wall_jump_lockout"):
                if hasattr(p, attr):
                    captured["players"][net_id][attr] = getattr(p, attr)
        return captured

    def restore_state(self, captured: dict):
        """Restaura snapshot capturado por capture_state."""
        self.tick_count = captured["tick"]
        for net_id, st in captured["players"].items():
            p = self.players.get(net_id)
            if not p:
                continue
            p.pos.x = st["x"]
            p.pos.y = st["y"]
            p.vel.x = st["vx"]
            p.vel.y = st["vy"]
            p.facing = st["facing"]
            p.alive = st["alive"]
            for k, v in st.items():
                if k in ("x", "y", "vx", "vy", "facing", "alive"):
                    continue
                if hasattr(p, k):
                    setattr(p, k, v)
