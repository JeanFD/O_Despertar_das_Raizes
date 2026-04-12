# world/level.py
import pygame
import pytmx

class Level:
    def __init__(self, game, path):
        self.game = game
        self.tmx  = pytmx.load_pygame(path, pixelalpha=True)
        self.tile_size = self.tmx.tilewidth
        self.width  = self.tmx.width  * self.tile_size
        self.height = self.tmx.height * self.tile_size

        # importa nosso Tilemap
        from world.tilemap import Tilemap
        self.tilemap = Tilemap(self.tile_size)

        self._tiles = {}                 # nome_da_layer -> [(rect, surface)]
        self.spawn_points = {}           # tipo -> [{"x":..,"y":..,"props":..}]
        self.triggers = []
        self._parse()

    def _parse(self):
        ts = self.tile_size
        for layer in self.tmx.layers:
            if isinstance(layer, pytmx.TiledTileLayer):
                surfaces = []
                for x, y, surf in layer.tiles():
                    if surf:
                        rect = pygame.Rect(x * ts, y * ts, ts, ts)
                        surfaces.append((rect, surf))
                        if layer.name == "collision":
                            self.tilemap.collision_rects.append(rect)
                self._tiles[layer.name] = surfaces

            elif isinstance(layer, pytmx.TiledObjectGroup):
                for obj in layer:
                    data = {
                        "x": obj.x, "y": obj.y,
                        "w": obj.width, "h": obj.height,
                        "type": (obj.type or ""),
                        "props": dict(obj.properties or {})
                    }
                    if layer.name == "entities":
                        self.spawn_points.setdefault(data["type"], []).append(data)
                    elif layer.name == "triggers":
                        self.triggers.append(data)

    def draw_layer(self, surface, name, camera):
        sw, sh = surface.get_size()
        for rect, img in self._tiles.get(name, []):
            dr = camera.apply_rect(rect)
            if -64 < dr.x < sw + 64 and -64 < dr.y < sh + 64:
                surface.blit(img, dr)