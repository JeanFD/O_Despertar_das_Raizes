import pygame
import os

# Configurações do tutorial
FRAME_W = 48
FRAME_H = 48

# Definição das cores para cada linha de animação
# Linha 0: Idle (Azul), Linha 1: Run (Verde), Linha 2: Jump/Fall (Vermelho/Laranja)
COLORS = [
    [(0, 100, 255), (50, 150, 255)], # Tons de Azul (Idle)
    [(0, 200, 100), (50, 255, 150)], # Tons de Verde (Run)
    [(255, 100, 0), (255, 200, 0)]   # Vermelho e Laranja (Jump/Fall)
]

# Quantidade de frames por linha
ROW_FRAMES = [4, 8, 2] 

pygame.init()

# Largura total baseada na maior linha (8 frames * 48px = 384px)
sheet_w = FRAME_W * 8
sheet_h = FRAME_H * 3
surface = pygame.Surface((sheet_w, sheet_h), pygame.SRCALPHA)

for row, num_frames in enumerate(ROW_FRAMES):
    for frame in range(num_frames):
        rect = (frame * FRAME_W, row * FRAME_H, FRAME_W, FRAME_H)
        
        # Intercala cores para podermos ver o "piscar" da animação
        color = COLORS[row][frame % 2]
        
        # Desenha o corpo do player (um quadrado menor centralizado)
        # Deixamos um espaço embaixo (chão do frame) para o centro-inferior
        player_rect = (frame * FRAME_W + 12, row * FRAME_H + 8, 24, 40)
        pygame.draw.rect(surface, color, player_rect)
        
        # Desenha um detalhe (olho) para sabermos para onde ele está olhando
        eye_rect = (frame * FRAME_W + 28, row * FRAME_H + 16, 6, 6)
        pygame.draw.rect(surface, (255, 255, 255), eye_rect)

# Salva na pasta correta
os.makedirs("assets/images/sprites", exist_ok=True)
pygame.image.save(surface, "assets/images/sprites/player.png")
print("Spritesheet do Player gerado em assets/images/sprites/player.png")