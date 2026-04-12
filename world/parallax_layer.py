import pygame
from settings import SCREEN_W

class ParallaxLayer:
    def __init__(self, image,speed_factor, scroll_y=False):
        self.image      = image
        self.speed_factor = speed_factor # 0 parado; 1 move junto
        self.scroll_y = scroll_y

    def draw(self, surface, camera_offset):
        ox = int(camera_offset.x * self.speed_factor)
        oy = int(camera_offset.y * self.speed_factor) if self.scroll_y else 0

        img_w = self.image.get_width()
        start_x = -(ox % img_w)
        x = start_x
        while x < SCREEN_W:
            surface.blit(self.image, (x, -oy))
            x += img_w