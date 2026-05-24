"""
Delta encoding de snapshots.

O servidor manda snapshot a 30 Hz. Em vez de mandar o estado completo
toda vez, manda apenas o que mudou desde o último snapshot que o cliente
confirmou (ack). Em movimento constante, ~70% do payload some.

Algoritmo:
- Servidor mantém histórico dos últimos N snapshots por cliente.
- Cada SNAPSHOT vai com (tick, base_tick) — "delta a partir do snapshot
  do tick base_tick". Se base_tick = 0, é um snapshot completo.
- Cliente confirma o último tick recebido em cada INP que envia.
- Servidor descarta histórico até o tick ack confirmado.

Para a fase atual implementamos delta simples: apenas omitimos chaves
cujo valor não mudou. Compressão real (varint, fixed-point) fica para
otimização futura — já é grátis se msgpack for usado.
"""
from typing import Optional


def make_delta(prev: Optional[dict], curr: dict) -> dict:
    """Gera delta `curr` relativo a `prev`. Se prev for None, devolve curr."""
    if prev is None:
        return curr
    return _diff(prev, curr)


def _diff(a: dict, b: dict) -> dict:
    """Diff recursivo: chaves em `b` que diferem de `a` (ou são novas)."""
    out = {}
    for k, vb in b.items():
        va = a.get(k)
        if isinstance(vb, dict) and isinstance(va, dict):
            sub = _diff(va, vb)
            if sub:
                out[k] = sub
        elif vb != va:
            out[k] = vb
    return out


def apply_delta(base: dict, delta: dict) -> dict:
    """Aplica delta sobre base. Retorna NOVO dict (não muta base)."""
    out = dict(base)
    for k, v in delta.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = apply_delta(out[k], v)
        else:
            out[k] = v
    return out
