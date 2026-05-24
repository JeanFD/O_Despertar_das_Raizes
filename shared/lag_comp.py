"""
Lag compensation no servidor (Source-style).

Servidor mantém histórico de posições por entidade nos últimos N ticks
(default 60 = 1 segundo a 60 Hz). Quando processa um ataque do cliente,
"rebobina" os alvos para o tick em que o cliente fez o ataque (now -
rtt/2) antes de testar a hitbox, então restaura o estado atual.

Custo: ~32 bytes × 60 ticks × N players = ~4 KB/player. Trivial.

Sem isso, em latência > 50 ms, o cliente atira na posição "antiga" do
alvo (o que ele vê), mas o servidor testa contra a posição "atual" — o
alvo já se moveu. Resultado: hit/miss frustrante e injusto.
"""
from __future__ import annotations
from collections import deque
from typing import Any, Deque, Dict


class LagCompHistory:
    """Ring buffer de estados por entidade indexado por tick."""

    def __init__(self, window_ticks: int = 60):
        self.window = window_ticks
        # entity_id → deque[(tick, snapshot_dict)]
        self._hist: Dict[Any, Deque] = {}

    def record(self, entity_id: Any, tick: int, snap: dict):
        d = self._hist.get(entity_id)
        if d is None:
            d = deque(maxlen=self.window)
            self._hist[entity_id] = d
        d.append((tick, dict(snap)))

    def state_at(self, entity_id: Any, target_tick: int):
        """Devolve o snapshot mais próximo de target_tick (sem extrapolar)."""
        d = self._hist.get(entity_id)
        if not d:
            return None
        # busca linear — 60 elementos no máximo
        best = None
        best_delta = None
        for tk, snap in d:
            delta = abs(tk - target_tick)
            if best_delta is None or delta < best_delta:
                best = snap
                best_delta = delta
        return best


class RewindContext:
    """Context manager que aplica estados antigos e restaura ao sair.

        with RewindContext(sim, history, rewind_tick):
            combat_system.check_hits(...)   # roda contra posições antigas
        # entidades já voltaram para o estado atual
    """

    def __init__(self, simulation, history: LagCompHistory, target_tick: int,
                 exclude_ids: tuple = ()):
        self.sim = simulation
        self.history = history
        self.target_tick = target_tick
        self.exclude = set(exclude_ids)
        self._saved: dict = {}

    def __enter__(self):
        for net_id, p in self.sim.players.items():
            if net_id in self.exclude:
                continue
            self._saved[net_id] = {
                "x": p.pos.x, "y": p.pos.y,
                "vx": p.vel.x, "vy": p.vel.y,
            }
            past = self.history.state_at(net_id, self.target_tick)
            if past:
                p.pos.x = past.get("x", p.pos.x)
                p.pos.y = past.get("y", p.pos.y)
        return self

    def __exit__(self, *args):
        for net_id, saved in self._saved.items():
            p = self.sim.players.get(net_id)
            if not p:
                continue
            p.pos.x = saved["x"]
            p.pos.y = saved["y"]
            p.vel.x = saved["vx"]
            p.vel.y = saved["vy"]
