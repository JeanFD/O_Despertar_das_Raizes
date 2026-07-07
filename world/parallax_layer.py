import pygame
from settings import SCREEN_W, SCREEN_H

# Folga vertical acima/abaixo da tela. As camadas sao escaladas mais altas
# que a tela por esta margem para que o parallax vertical possa desloca-las
# sem revelar borda. Precisa ser > que o maior deslocamento vertical possivel
# (max offset.y * maior vy_factor).
VERT_MARGIN = 180


class ParallaxLayer:
    def __init__(self, image, speed_factor, scroll_y=True, vy_scale=0.4):
        # As artes de background sao pequenas (~240px). Escala para preencher
        # a altura da tela + margem (folga p/ o scroll vertical), mantendo a
        # proporcao; o tiling horizontal (draw) cobre a largura.
        # transform.scale (nearest) preserva o pixel art.
        target_h = SCREEN_H + VERT_MARGIN
        img_h = image.get_height()
        if img_h and img_h != target_h:
            factor = target_h / img_h
            new_w = max(1, round(image.get_width() * factor))
            image = pygame.transform.scale(image, (new_w, target_h))

        self.image        = image
        self.speed_factor = speed_factor  # horizontal: 0 parado; 1 move junto
        self.scroll_y     = scroll_y
        # Vertical mais sutil que o horizontal (evita enjoo e borda visivel).
        self.vy_factor    = speed_factor * vy_scale

    def draw(self, surface, camera_offset):
        img_w = self.image.get_width()
        img_h = self.image.get_height()

        ox = int(camera_offset.x * self.speed_factor)
        oy = int(camera_offset.y * self.vy_factor) if self.scroll_y else 0

        # Vertical: ancora a imagem sempre cobrindo a tela. blit_y fica entre
        # SCREEN_H - img_h (base colada embaixo) e 0 (topo colado em cima); a
        # margem extra absorve o deslocamento sem deixar buraco.
        blit_y = min(0, max(SCREEN_H - img_h, -oy))

        # Horizontal: tiling continuo com wrap pelo modulo da largura.
        start_x = -(ox % img_w)
        x = start_x
        while x < SCREEN_W:
            surface.blit(self.image, (x, blit_y))
            x += img_w
