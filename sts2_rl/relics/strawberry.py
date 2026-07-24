from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class Strawberry(Relic):
    """Strawberry.cs — upon pickup, raise Max HP by 7 (AfterObtained →
    CreatureCmd.GainMaxHp(7), which also heals 7)."""

    id = "strawberry"
    name = "Strawberry"
    rarity = RelicRarity.COMMON
    has_upon_pickup_effect = True  # RelicModel.HasUponPickupEffect

    MAX_HP = 7

    def after_obtained(self, run) -> None:
        run.gain_max_hp(self.MAX_HP)

    def undo_after_obtained(self, run) -> None:
        # Conformance-runner un-grant (see Relic.undo_after_obtained): give
        # back the max HP and the heal that came with it.
        run.lose_max_hp(self.MAX_HP)
        run.hp = min(run.hp, run.max_hp)
