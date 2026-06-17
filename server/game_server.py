# server/game_server.py
# Servidor dedicado headless — rode com: python server/game_server.py
# Precisa de todo o diretório do jogo no VPS (assets/, entities/, etc.)
import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

# Garante que o root do projeto está no path quando rodado de qualquer dir
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame
pygame.init()
pygame.display.set_mode((1, 1))

import time

from server.dedicated_conn import DedicatedServerConn
from engine.event_bus import EventBus
from entities.player import Player
from entities.projectile import Projectile
from systems.physics_system import PhysicsSystem
from systems.combat_system import CombatSystem
from engine.versus_match import (
    VersusMatch, PHASE_FIGHTING, PHASE_ROUND_END, PHASE_MATCH_END,
)
from world.arena import build_fallback_tilemap, default_spawns, default_size, ringout_y_for
from components.health import Health
from settings import SERVER_PORT, FIXED_DT


class _HeadlessGame:
    """Mock mínimo do objeto game para rodar sistemas headless."""

    class _Assets:
        def image(self, _path):
            return pygame.Surface((1024, 1024))

        def font(self, _path, _size):
            return pygame.font.SysFont("monospace", _size)

    def __init__(self):
        self.assets = self._Assets()
        self.events = EventBus()


def _entity_state(e) -> dict:
    from components.animation import AnimationController
    hp   = e.get(Health)
    anim = e.get(AnimationController)
    return {
        "x":      e.pos.x,
        "y":      e.pos.y,
        "vx":     e.vel.x,
        "vy":     e.vel.y,
        "facing": getattr(e, "facing", 1),
        "hp":     hp.current if hp else 0,
        "anim":   anim._current if anim and anim._current else "idle",
        "alive":  bool(getattr(e, "alive", True)),
        "dbg":    e.debug_snapshot() if isinstance(e, Player) else {},
        "sta":    e.stamina if isinstance(e, Player) else 0.0,
    }


def run_match(conn: DedicatedServerConn, best_of: int = 3):
    game = _HeadlessGame()

    # ── Carregar mundo ───────────────────────────────────────────────────────
    try:
        from world.level import Level
        level    = Level(game, "assets/maps/arena.tmx")
        tilemap  = level.tilemap
        world_w  = level.width
        world_h  = level.height
        pts      = level.spawn_points
        sp1_data = pts.get("player",  [{"x": 200, "y": 300}])[0]
        sp2_data = pts.get("player2", [{"x": 900, "y": 300}])[0]
        sp1      = (float(sp1_data["x"]), float(sp1_data["y"]))
        sp2      = (float(sp2_data["x"]), float(sp2_data["y"]))
    except Exception as e:
        print(f"[server] arena.tmx indisponível, usando fallback: {e}")
        tilemap         = build_fallback_tilemap()
        world_w, world_h = default_size()
        sp1, sp2        = default_spawns()

    ringout_y = ringout_y_for(world_h)

    # ── Entidades ────────────────────────────────────────────────────────────
    p1 = Player(game, *sp1, team_id="p1")
    p1.facing = 1
    for ab in p1.abilities:
        p1.abilities[ab] = True

    p2 = Player(game, *sp2, team_id="p2")
    p2.facing = -1
    for ab in p2.abilities:
        p2.abilities[ab] = True

    # ── Sistemas ─────────────────────────────────────────────────────────────
    physics  = PhysicsSystem(tilemap)
    combat   = CombatSystem()
    match    = VersusMatch(best_of=best_of)
    entities = [p1, p2]

    last_input = {1: {}, 2: {}}
    last_ack   = {1: 0,  2: 0}

    def on_damage(entity, amount, remaining):
        target = "p1" if entity is p1 else ("p2" if entity is p2 else None)
        if target:
            conn.broadcast_event("dmg", target=target,
                                 amount=amount, remaining=remaining)

    game.events.subscribe("entity_damaged", on_damage)

    def build_snapshot() -> dict:
        proj = [e.to_net() for e in entities
                if isinstance(e, Projectile) and e.alive]
        return {
            "p1":    _entity_state(p1),
            "p2":    _entity_state(p2),
            "proj":  proj,
            "match": match.to_dict(),
            "ack1":  last_ack[1],
            "ack2":  last_ack[2],
        }

    def reset_round():
        p1.reset_for_round(*sp1, facing=1)
        p2.reset_for_round(*sp2, facing=-1)

    def check_ringout():
        for player in (p1, p2):
            if player.pos.y > ringout_y:
                hp = player.get(Health)
                if hp:
                    hp.current = 0
                player.alive = False

    def spawn_projectiles():
        for player in (p1, p2):
            if getattr(player, "_spawn_projectile_callback", False):
                player._spawn_projectile_callback = False
                entities.append(
                    Projectile(game=game, x=player.pos.x, y=player.pos.y,
                               direction=player.facing, team=player.team)
                )

    # ── Game loop ─────────────────────────────────────────────────────────────
    print("[server] Partida iniciada.")
    next_tick = time.monotonic()

    while True:
        now        = time.monotonic()
        sleep_time = next_tick - now
        if sleep_time > 0:
            time.sleep(sleep_time)
        next_tick = time.monotonic() + FIXED_DT

        if not all(conn.connected):
            print("[server] Jogador desconectou. Encerrando partida.")
            break

        # ── Inputs ──────────────────────────────────────────────────────────
        inp1, inp2 = conn.get_inputs(FIXED_DT)

        for pid, inp in ((1, inp1), (2, inp2)):
            if inp:
                tk = inp.get("tk", 0)
                if tk > last_ack[pid]:
                    last_ack[pid] = tk
                last_input[pid] = inp

        # ── Aplica inputs ────────────────────────────────────────────────────
        if match.can_act:
            if last_input[1]:
                p1.apply_net_input(last_input[1])
            if last_input[2]:
                p2.apply_net_input(last_input[2])
            spawn_projectiles()
        else:
            p1.vel.x = 0.0
            p2.vel.x = 0.0

        # ── Física e combate ─────────────────────────────────────────────────
        if match.phase in (PHASE_FIGHTING, PHASE_ROUND_END):
            physics.update(entities, FIXED_DT)
        if match.phase == PHASE_FIGHTING:
            combat.update(entities, FIXED_DT)

        for e in list(entities):
            e.update(FIXED_DT)

        entities[:] = [e for e in entities
                       if getattr(e, "alive", True) or e is p1 or e is p2]

        if match.phase == PHASE_FIGHTING:
            check_ringout()

        # ── Engine de regras ─────────────────────────────────────────────────
        hp1 = p1.get(Health)
        hp2 = p2.get(Health)
        result = match.tick(
            FIXED_DT,
            p1.alive, float(hp1.current) if hp1 else 0.0,
            p2.alive, float(hp2.current) if hp2 else 0.0,
        )

        for tr in result["transitions"]:
            ev      = tr["ev"]
            payload = {k: v for k, v in tr.items() if k != "ev"}
            conn.broadcast_event(ev, **payload)
            if ev == "next_round":
                reset_round()

        conn.broadcast_state(build_snapshot())

        # ── Fim de partida ────────────────────────────────────────────────────
        if match.phase == PHASE_MATCH_END:
            time.sleep(4.0)
            conn.broadcast_event(
                "go_post_match",
                s1=match.score_p1,
                s2=match.score_p2,
                winner=match.match_winner or 0,
                bo=best_of,
            )
            time.sleep(1.0)
            break

    game.events.unsubscribe("entity_damaged", on_damage)
    print("[server] Partida encerrada.")


def main():
    print(f"[server] Servidor de jogo na porta UDP {SERVER_PORT}")
    while True:
        print("[server] Aguardando 2 jogadores (timeout 5 min)...")
        conn = DedicatedServerConn(SERVER_PORT, "vs")

        if conn.wait_for_clients(timeout=300.0):
            try:
                run_match(conn, best_of=3)
            except Exception:
                import traceback
                traceback.print_exc()
        else:
            print("[server] Nenhum jogador conectou no tempo limite.")

        conn.close()
        time.sleep(2.0)


if __name__ == "__main__":
    main()
