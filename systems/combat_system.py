from components.hitbox import Hitbox
from components.health import Health
from components.physics_body import PhysicsBody


class CombatSystem:
    def update(self, entities, dt):
        attackers = []
        for e in entities:
            if not e.alive:
                continue
            for hb in e._components.values():
                items = hb if isinstance(hb, list) else [hb]
                for item in items:
                    if isinstance(item, Hitbox) and item.active:
                        attackers.append((e, item))

        defenders = [
            (e, e.get(Health), e.get(PhysicsBody))
            for e in entities if e.get(Health) and e.alive
        ]

        for ae, ahb in attackers:
            for de, dhp, dbody in defenders:
                if de is ae:
                    continue
                if not ahb.can_hit(id(de)):
                    continue

                de_team = getattr(de, "team", None)
                if ahb.team and de_team and ahb.team == de_team:
                    continue

                if dbody and ahb.rect.colliderect(dbody.rect):
                    dir_x = 1 if de.pos.x > ae.pos.x else -1
                    kb_y = -getattr(ahb, "knockback_y", 200)
                    kb = (dir_x * ahb.knockback, kb_y)
                    dhp.take_damage(ahb.damage, kb)
                    ahb.register_hit(id(de), cd=0.6)

            ahb.tick(dt)