import pygame

class AnimationController:
    def __init__(self, entity, sheet, frame_w, frame_h, fps=12):
        self.entity     = entity
        self.sheet      = sheet
        self.frame_w    = frame_w
        self.frame_h    = frame_h
        self.fps        = fps
        self._anims     = {}
        self._current    = ""
        self.frame      = 0
        self.timer      = 0.0
        self._flip_x    = False
        self.image      = None

    def add(self, name, row, start ,end):
        """Define uma animação: linha do sheet, frame inicial, frame final."""
        self._anims[name] = (row, start, end)

    def play(self, name, flip_x = False):
        if name != self._current:
            self._current   = name
            self._frame     = 0
            self._timer     = 0.0
        self._flip_x        = flip_x

    def update(self, dt):
        if not self._current:
            return
        self._timer += dt
        spf = 1.0 / self.fps

        if self._timer >= spf:
            self._timer -= spf
            row, start, end = self._anims[self._current]
            self._frame = start + (self._frame - start + 1) % (end - start + 1)

        row, _, _ = self._anims[self._current]
        x = self._frame * self.frame_w
        y = row         * self.frame_h
        frame = self.sheet.subsurface((x, y, self.frame_w, self.frame_h))
        if self._flip_x:
            frame = pygame.transform.flip(frame, True, False)
        self.image = frame

    def draw(self, surface, pos, camera):
        if self.image:
            dx, dy = camera.apply(pos)
            surface.blit(self.image, (dx - self.frame_w // 2, dy - self.frame_h))