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
        # Coleta TODAS as hitboxes (não só ativas). Suporta entidades com
        # múltiplas hitboxes (alguns inimigos/armadilhas registram em lista).
        all_hitboxes = []
        for e in entities:
            if not e.alive:
                continue
            for hb in e._components.values():
                items = hb if isinstance(hb, list) else [hb]
                for item in items:
                    if isinstance(item, Hitbox):
                        all_hitboxes.append((e, item))

        attackers = [(e, hb) for e, hb in all_hitboxes if hb.active]
        defenders = [
            (e, e.get(Health), e.get(PhysicsBody))
            for e in entities if e.get(Health) and e.alive
        ]

        # Decrementa cooldowns de TODAS as hitboxes, mesmo as inativas. Sem
        # isso, o cooldown por alvo (register_hit) fica preso quando a hitbox
        # desativa entre golpes — bug do plunge: 2º plunge não dava dano no
        # mesmo alvo porque o cd registrado no shockwave anterior nunca expirava.
        for _, hb in all_hitboxes:
            hb.tick(dt)

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
                    if getattr(de, "parry_timer", 0) > 0:
                        de.parry_timer = 0
                        de.hp.invicible = getattr(de, "PARRY_IFRAMES", 0.5)

                        if hasattr(ae, "vel"):
                            ae.vel.x = -ae.vel.x * 0.3 if ae.vel.x else 0
                        if hasattr(ae, "stun_timer"):
                            ae.stun_timer = 0.6
                        atk_hp = ae.get(Health)
                        if atk_hp:
                            atk_hp.take_damage(30)
                        ahb.register_hit(id(de))
                        de.game.events.emit("parry_success", entity=de)
                        continue

                    dir_x = 1 if de.pos.x > ae.pos.x else -1
                    kb_y = -getattr(ahb, "knockback_y", 200)
                    kb = (dir_x * ahb.knockback, kb_y)
                    dhp.take_damage(ahb.damage, kb)
                    ahb.register_hit(id(de), cd=0.6)

                    # Reembolso de stamina ao acertar — Player (e só Player)
                    # ganha um pouco de fôlego ao conectar um golpe. Projéteis
                    # não têm stamina, então não fazem nada aqui. Mantém pressão
                    # ofensiva sem precisar farmar regen ocioso.
                    gain = getattr(ae, "STAMINA_GAIN_ON_HIT", 0.0)
                    if gain and hasattr(ae, "stamina") and hasattr(ae, "max_stamina"):
                        ae.stamina = min(ae.max_stamina, ae.stamina + gain)

                    if hasattr(ae, 'lifetime'):
                        ae.alive = False
