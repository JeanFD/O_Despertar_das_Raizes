# world/arena.py
"""
Helpers do mapa de arena para o modo Versus 1v1.

O mapa em si vive em `assets/maps/arena.tmx` (editável no Tiled).
Spawns 'player' (P1) e 'player2' (P2) saem dos object groups do TMX,
exatamente como o mapa do co-op.

Este módulo guarda apenas:
- ARENA_TMX_PATH      → path do TMX
- DEFAULT_ARENA_*     → fallback para spawns/dimensões caso o TMX falhe
- ringout_y_for(level) → linha Y abaixo da qual conta como ring-out
- build_fallback_tilemap() → tilemap programático equivalente, usado
                              somente como rede de segurança
"""

from world.tilemap import Tilemap


ARENA_TMX_PATH = "assets/maps/arena.tmx"

# Dimensões do TMX padrão (40 cols × 22 rows × 32px = 1280×704)
ARENA_TILE = 32
ARENA_W    = 1280
ARENA_H    = 704

DEFAULT_SPAWN_P1 = (112.0, 640.0)
DEFAULT_SPAWN_P2 = (1168.0, 640.0)


def ringout_y_for(world_h: int) -> float:
    """Y abaixo do qual o jogador é considerado caído (ring-out)."""
    return float(world_h) + 80.0


def default_spawns() -> tuple[tuple[float, float], tuple[float, float]]:
    return DEFAULT_SPAWN_P1, DEFAULT_SPAWN_P2


def default_size() -> tuple[int, int]:
    return ARENA_W, ARENA_H


def build_fallback_tilemap() -> Tilemap:
    """Tilemap programático com layout idêntico ao arena.tmx.

    Só é usado se o TMX não carregar (asset faltando, erro pytmx, etc).
    O design do mapa edita-se no Tiled — esta função apenas espelha o
    layout para garantir que o jogo nunca quebre na ausência do arquivo.
    """
    tm = Tilemap(ARENA_TILE)
    cols = ARENA_W // ARENA_TILE   # 40
    rows = ARENA_H // ARENA_TILE   # 22

    # Paredes laterais
    for gy in range(rows):
        tm.add_tile(0, gy)
        tm.add_tile(cols - 1, gy)

    # Plataforma central
    for gx in range(16, 24):
        tm.add_tile(gx, 12)

    # Plataformas médias
    for gx in range(8, 12):
        tm.add_tile(gx, 15)
    for gx in range(28, 32):
        tm.add_tile(gx, 15)

    # Chão com gap (cols 8..31 vazio)
    for gy in (20, 21):
        for gx in range(1, 8):
            tm.add_tile(gx, gy)
        for gx in range(32, 39):
            tm.add_tile(gx, gy)

    return tm
