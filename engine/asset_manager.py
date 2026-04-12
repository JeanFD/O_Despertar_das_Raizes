import pygame

class AssetManager:
    def __init__(self):
        self._images = {}
        self._sounds = {}
        self._fonts = {}

    def image(self, path):
        if path not in self._images:
            self._images[path] = pygame.image.load(path).convert_alpha()
        return self._images[path]
    
    def sound(self, path):
        if path not in self._sounds:
            self._sounds[path] = pygame.mixer.Soud(path)
        return self._sounds[path]
    
    def play(self, path, volume=0.5):
        s = self.soudn(path)
        s.set_volume(volume)
        s.play()

    def font(self, path, size):
        key = (path, size)
        if key not in self._fonts:
            self._fonts[key] = pygame.font.Font(path, size)
        return self._fonts[key]