from components.hitbox import Hitbox
from components.health import Health
from components.physics_body import PhysicsBody


class CombatSystem:
    """
    Resolve dano por hitbox/hurtbox.

    Regra de times:
    - Se o hitbox e a entidade defensora têm `team` definido e iguais,
      o golpe é ignorado (sem fogo amigo).
    - Se algum dos lados não tem time, o comportamento antigo é mantido
      (qualquer entidade que não seja o atacante pode receber dano).
    """

    def update(self, entities, dt):
        attackers = [(e, e.get(Hitbox)) for e in entities if e.get(Hitbox) and e.get(Hitbox).active]
        defenders = [(e, e.get(Health), e.get(PhysicsBody)) for e in entities if e.get(Health)]

        for ae, ahb in attackers:
            ahb.tick(dt)
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
                    kb = (dir_x * ahb.knockback, -200)
                    dhp.take_damage(ahb.damage, kb)
                    ahb.register_hit(id(de))
                    if hasattr(ae, 'lifetime'):
                        ae.alive = False

