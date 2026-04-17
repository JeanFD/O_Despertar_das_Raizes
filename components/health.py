class Health:
    def __init__(self, entity, max_hp):
        self.entity = entity
        self.max_hp = max_hp
        self.current = max_hp
        self.invicible = 0.0

    def take_damage(self, amount, knockback=None):
        if self.invicible > 0:
            return
        self.current -= amount
        self.invicible = 0.5

        if knockback and hasattr(self.entity, "vel"):
            self.entity.vel.x = knockback[0]
            self.entity.vel.y = knockback[1]

        self.entity.game.events.emit(
            "entity_damaged",
            entity=self.entity, amount=amount, remaining=self.current
        )

        if self.current <= 0:
            self.entity.kill()

    def update(self, dt):
        self.invicible = max(0.0, self.invicible - dt)
        