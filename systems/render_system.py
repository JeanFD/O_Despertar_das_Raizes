class RenderSystem:
    def draw_entities(self, surface, entities, camera):
        sorted_ents = sorted([e for e in entities if e.alive], key=lambda e: e.pos.y)
        for e in sorted_ents:
            e.draw(surface, camera)