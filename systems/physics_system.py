from components.physics_body import PhysicsBody

GRAVITY = 1800
MAX_FALL = 900

class PhysicsSystem:
    def __init__(self, ground_y):
        self.ground_y = ground_y

    def update(self, entities, dt):
        for e in entities:
            body = e.get(PhysicsBody)
            if not body:
                continue

            e.vel.y = min(e.vel.y + GRAVITY * dt, MAX_FALL)

            e.pos.x += e.vel.x * dt
            e.pos.y += e.vel.y * dt

            # Colisão com chão fake
            if e.pos.y + body.height >= self.ground_y:
                e.pos.y = self.ground_y - body.height
                e.vel.y = 0
                body.on_ground = True
            else:
                body.on_ground = False