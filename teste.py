import pygame

# Configurações
TILE_SIZE = 32
CORES = [
    (100, 100, 100), # 0: Cinza escuro (Colisão)
    (60, 60, 70),    # 1: Cinza azulado (Background)
    (150, 150, 150), # 2: Cinza claro (Plataformas)
    (200, 100, 100)  # 3: Avermelhado (Dano/Perigo)
]

pygame.init()
# Cria uma fileira de 4 tiles (128x32 pixels)
surface = pygame.Surface((TILE_SIZE * len(CORES), TILE_SIZE))

for i, cor in enumerate(CORES):
    rect = (i * TILE_SIZE, 0, TILE_SIZE, TILE_SIZE)
    # Desenha o quadrado preenchido
    pygame.draw.rect(surface, cor, rect)
    # Desenha uma borda leve para você enxergar a grade
    pygame.draw.rect(surface, (30, 30, 30), rect, 1)

# Salva na pasta de assets
import os
os.makedirs("assets/images", exist_ok=True)
pygame.image.save(surface, "assets/images/placeholder_tileset.png")
print("Tileset gerado em assets/images/placeholder_tileset.png")