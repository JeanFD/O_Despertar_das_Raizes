"""
Buffer de interpolação para entidades remotas.

Substitui o LERP exponencial do RemotePlayer original por uma técnica
profissional (Source-style):

1. Cliente enfileira snapshots vindos do servidor com timestamp real.
2. Renderiza com um delay configurável (interp window — default 100 ms).
3. A cada frame, acha os dois snapshots em volta do tempo de render e
   interpola linearmente entre eles.
4. Se o buffer secar (perda de pacotes), extrapola por até MAX_EXTRAP
   usando a última velocidade conhecida. Acima disso, congela.

Resultado: movimento fluido mesmo com perda de pacote ou jitter de
latência, ao custo de exibir o remoto sempre ~100 ms atrasado.
"""
from __future__ import annotations
import time
from collections import deque
from typing import Any, Optional


INTERP_DELAY_DEFAULT = 0.10   # 100 ms — janela de interpolação
MAX_EXTRAP           = 0.20   # 200 ms — limite de extrapolação


class InterpBuffer:
    """Fila ordenada por tempo de chegada. Mantém um histórico curto."""

    def __init__(self,
                 interp_delay: float = INTERP_DELAY_DEFAULT,
                 max_extrap: float = MAX_EXTRAP,
                 max_size: int = 32):
        self.interp_delay = interp_delay
        self.max_extrap = max_extrap
        self._buf: deque = deque(maxlen=max_size)
        self._frozen_at: Optional[float] = None

    def push(self, state: dict, recv_time: Optional[float] = None):
        """Adiciona snapshot ao buffer. recv_time default: agora."""
        t = recv_time if recv_time is not None else time.monotonic()
        # ignora snapshots fora de ordem (tick antigo) — UDP pode reorderar
        if self._buf and "tick" in state and "tick" in self._buf[-1][1]:
            if state["tick"] <= self._buf[-1][1]["tick"]:
                return
        self._buf.append((t, state))
        self._frozen_at = None

    def sample(self, now: Optional[float] = None) -> Optional[dict]:
        """Retorna o estado interpolado para o tempo atual.

        Modos:
          - dois snapshots em volta de (now - interp_delay): interpola
          - render_time depois do último snapshot: extrapola até MAX_EXTRAP
          - extrapolação esgotada: congela no último snapshot
          - buffer vazio: None
        """
        if not self._buf:
            return None
        t_now = now if now is not None else time.monotonic()
        render_time = t_now - self.interp_delay

        # Acha o par (a, b) tal que a.t <= render_time <= b.t
        a = b = None
        for i in range(len(self._buf) - 1):
            ta = self._buf[i][0]
            tb = self._buf[i + 1][0]
            if ta <= render_time <= tb:
                a, b = self._buf[i], self._buf[i + 1]
                break

        if a is not None and b is not None:
            ta, sa = a
            tb, sb = b
            span = tb - ta
            alpha = (render_time - ta) / span if span > 1e-6 else 0.0
            return _lerp_state(sa, sb, alpha)

        # Sem par — usar último snapshot
        last_t, last_s = self._buf[-1]
        if render_time < self._buf[0][0]:
            # render_time anterior a tudo — usa primeiro
            return dict(self._buf[0][1])

        # render_time depois do último — extrapola pelo tempo passado
        extrap_dt = render_time - last_t
        if extrap_dt <= self.max_extrap:
            return _extrapolate(last_s, extrap_dt)

        # Esgotou — congela
        return dict(last_s)


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _lerp_state(a: dict, b: dict, alpha: float) -> dict:
    """Interpolação linear de campos numéricos comuns; resto vem de b."""
    out = dict(b)
    for k in ("x", "y", "vx", "vy", "hp", "st"):
        if k in a and k in b:
            try:
                out[k] = _lerp(float(a[k]), float(b[k]), alpha)
            except (TypeError, ValueError):
                pass
    return out


def _extrapolate(state: dict, dt: float) -> dict:
    """Extrapola usando vx/vy. Não atualiza animação ou facing."""
    out = dict(state)
    if "x" in state and "vx" in state:
        out["x"] = state["x"] + state["vx"] * dt
    if "y" in state and "vy" in state:
        out["y"] = state["y"] + state["vy"] * dt
    return out
