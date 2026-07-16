from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class SmallCapsule(Relic):
    """SmallCapsule.cs — a reward screen with one grab-bag relic (auto-taken
    in the sim)."""

    id = "small_capsule"
    name = "Small Capsule"
    rarity = RelicRarity.ANCIENT

    def after_obtained(self, run) -> None:
        run.obtain_relic_from_grab_bag()
