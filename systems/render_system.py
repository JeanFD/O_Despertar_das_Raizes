from entities.player import Player

class RenderSystem:
    def draw_entities(self, surface, entities, camera):
        def draw_order(e):
            # player sempre desenhado por último (na frente de tudo)
            if isinstance(e, Player):
                return 1
            return 0

        sorted_ents = sorted(
            [e for e in entities if e.alive],
            key=draw_order
        )
        for e in sorted_ents:
            e.draw(surface, camera)

    