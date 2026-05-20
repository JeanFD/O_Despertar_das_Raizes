import pygame

class Entity:
    def __init__(self, game, x, y):
        self.game = game
        self. pos = pygame.math.Vector2(x, y)
        self.vel = pygame.math.Vector2(0, 0)
        self.alive=True
        self._components = {}

    def add(self, cls, *args, **kwargs):
        comp = cls(self, *args, **kwargs)
        # se já existe esse tipo, guarda como lista
        if cls in self._components:
            existing = self._components[cls]
            if isinstance(existing, list):
                existing.append(comp)
            else:
                self._components[cls] = [existing, comp]
        else:
            self._components[cls] = comp
        return comp
    
    def get(self, cls):
        return self._components.get(cls)
    
    def has(self, cls):
        return cls in self._components
    
    def update(self, dt): pass
    def draw(self, surface): pass
    def kill(self): self.alive = False