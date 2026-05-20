import pygame

class HUD:
    def __init__(self, game):
        self.game = game
        self.player = None

    def set_player(self, player):
        self.player = player

    def draw(self, surface):
        if not self.player:
            return
        self._bar(surface, 20, 20, 200, 16,
                  self.player.hp.current, self.player.hp.max_hp,
                  (220, 50, 50), (60, 20, 20))

        # Barra de estamina (mais fina, logo abaixo da HP). Funciona como
        # mana/especial: só enche ao acertar inimigos.
        if hasattr(self.player, "stamina") and hasattr(self.player, "max_stamina"):
            self._bar(surface, 20, 40, 200, 6,
                      self.player.stamina, self.player.max_stamina,
                      (90, 220, 230), (20, 40, 50))

        x = 20
        for name, unlocked in self.player.abilities.items():
            col = (200, 200, 60) if unlocked else (60, 60, 60)
            pygame.draw.rect(surface, col, (x, 54, 18, 18),
                             0 if unlocked else 1)
            x += 24

    def _bar(self, surf, x, y, w, h, cur, mx, fg, bg):
        pygame.draw.rect(surf, bg, (x, y, w, h), border_radius=4)
        fill = int(w * (cur / max(mx, 1)))
        if fill:
            pygame.draw.rect(surf, fg, (x, y, fill, h), border_radius=4)
        pygame.draw.rect(surf, (255, 255, 255), (x, y, w, h), 1, border_radius=4)