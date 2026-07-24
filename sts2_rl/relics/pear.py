from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class Pear(Relic):
    """Pear.cs — upon pickup, raise Max HP by 10 (AfterObtained →
    CreatureCmd.GainMaxHp(10), which also heals 10)."""

    id = "pear"
    name = "Pear"
    rarity = RelicRarity.UNCOMMON
    has_upon_pickup_effect = True  # RelicModel.HasUponPickupEffect

    MAX_HP = 10

    def after_obtained(self, run) -> None:
        run.gain_max_hp(self.MAX_HP)

    def undo_after_obtained(self, run) -> None:
        # Conformance-runner un-grant (see Relic.undo_after_obtained): give
        # back the max HP and the heal that came with it.
        run.lose_max_hp(self.MAX_HP)
        run.hp = min(run.hp, run.max_hp)
