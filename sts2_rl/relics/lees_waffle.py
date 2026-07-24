from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class LeesWaffle(Relic):
    """LeesWaffle.cs — upon pickup, raise Max HP by 7 (GainMaxHp, which heals 7)
    then heal to full (Heal(MaxHp - CurrentHp))."""

    id = "lees_waffle"
    name = "Lee's Waffle"
    rarity = RelicRarity.SHOP
    has_upon_pickup_effect = True  # RelicModel.HasUponPickupEffect

    MAX_HP = 7

    def after_obtained(self, run) -> None:
        run.gain_max_hp(self.MAX_HP)
        run.heal(run.max_hp - run.hp)

    def undo_after_obtained(self, run) -> None:
        # Conformance-runner un-grant (see Relic.undo_after_obtained): give
        # back the max HP and the heal that came with it.
        run.lose_max_hp(self.MAX_HP)
        run.hp = min(run.hp, run.max_hp)
