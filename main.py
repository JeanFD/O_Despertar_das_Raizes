import pygame
import sys
from settings import TITLE, SCREEN_W, SCREEN_H, FPS

pygame.init()
screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
pygame.display.set_caption(TITLE)
clock = pygame.time.Clock()

on_ground = False

player_x = SCREEN_W // 2
player_y = SCREEN_H // 2
GROUND_Y = SCREEN_H - 80
player_w = 32
player_h = 48

player_vy = 0
GRAVITY = 1800 #px/s²

player_vx = 0
MOVE_SPEED = 220

running = True
while running:
    dt = clock.tick(FPS) / 1000.0
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_SPACE and on_ground:
                player_vy = -600
    keys = pygame.key.get_pressed()
    player_vx = 0
    if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
        player_vx =  MOVE_SPEED
    if keys[pygame.K_LEFT] or keys[pygame.K_a]:
        player_vx = -MOVE_SPEED

    player_x += player_vx * dt

    screen.fill((20, 20, 30)) # cor de fundo
    player_vy += GRAVITY * dt
    player_y += player_vy * dt
    if player_y + player_h >= GROUND_Y:
        player_y = GROUND_Y - player_h
        player_vy = 0
        on_ground = True
    else:
        on_ground = False
    pygame.draw.rect(screen, (255, 255, 255), (player_x, player_y, player_w, player_h))
    pygame.draw.rect(screen, (90, 60, 30),
                 (0, GROUND_Y, SCREEN_W, SCREEN_H - GROUND_Y))
    pygame.display.flip()

pygame.quit()
sys.exit()


