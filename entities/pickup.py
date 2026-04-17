import pygame
from entities.entity import Entity

class AbilityPickup(Entity):
    def __init__(self,game,x,y,ability_type):
        super().__init__(game, x, y)
        self.ability_type = ability_type

    def update(self, dt):
        player = self.game.states.current.player
        pr = pygame.Rect(self.pos.x - 16, self.pos.y - 32, 32, 32)
        if player.body.rect.colliderect(pr):
            self.game.events.emit("item_collected", item_type=self.ability_type)
            self.kill()

    def draw(self, surface, camera):
        dr = camera.apply_rect(pygame.Rect(self.pos.x - 12, self.pos.y-24, 24, 24))
        pygame.draw.rect(surface, (255, 220, 100), dr)