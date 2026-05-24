"""
Fila de inputs do cliente para client-side prediction + reconciliation.

Cada input tem um tick monotônico. Servidor confirma o último tick que
processou no campo `ack_inp` de cada snapshot. Cliente:

1. Mantém todos os inputs ainda não confirmados.
2. Roda Simulation localmente aplicando o input do tick atual.
3. Ao receber snapshot do servidor:
   a. Descarta inputs com tick <= ack_inp.
   b. Restaura Simulation para o estado do snapshot (rollback).
   c. Reaplica os inputs restantes, em ordem (replay).
   Resultado: prediction sem drift permanente.
"""
from __future__ import annotations
from collections import deque
from typing import Deque, Dict, Optional


class InputBuffer:
    """Inputs locais ainda não confirmados pelo servidor."""

    def __init__(self, max_size: int = 256):
        self._buf: Deque[tuple[int, dict]] = deque(maxlen=max_size)
        self._next_tick: int = 1

    def push(self, inp: dict) -> int:
        """Adiciona input, atribui tick monotônico. Retorna o tick."""
        tick = self._next_tick
        self._next_tick += 1
        self._buf.append((tick, dict(inp)))
        return tick

    def prune_acked(self, ack_tick: int):
        """Remove inputs com tick <= ack_tick."""
        while self._buf and self._buf[0][0] <= ack_tick:
            self._buf.popleft()

    def pending(self) -> list:
        """Retorna inputs pendentes em ordem (tick crescente)."""
        return list(self._buf)

    @property
    def latest_tick(self) -> int:
        return self._next_tick - 1

    def __len__(self):
        return len(self._buf)
