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

    # HP the grant actually healed, for undo_after_obtained (sim-only).
    _healed = 0

    def after_obtained(self, run) -> None:
        before = run.hp
        run.gain_max_hp(self.MAX_HP)
        run.heal(run.max_hp - run.hp)
        self._healed = run.hp - before

    def undo_after_obtained(self, run) -> None:
        # Conformance-runner un-grant (see Relic.undo_after_obtained): give
        # back the max HP and the heal that came with it. `lose_max_hp` only
        # CLAMPS current HP to the restored maximum, so the heal survives
        # unless it is subtracted explicitly.
        run.hp = max(1, run.hp - self._healed)
        self._healed = 0
        run.lose_max_hp(self.MAX_HP)
