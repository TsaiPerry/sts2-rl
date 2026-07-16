from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class FishingRod(Relic):
    """FishingRod.cs — after every 3rd Monster combat, upgrade a random
    upgradable card in the deck."""

    id = "fishing_rod"
    name = "Fishing Rod"
    rarity = RelicRarity.ANCIENT
    COMBATS = 3

    def __init__(self) -> None:
        super().__init__()
        self.combats_seen = 0

    def after_combat_end(self, run, room_type) -> None:
        from ..rooms import RoomType

        if room_type != RoomType.MONSTER:
            return
        self.combats_seen += 1
        if self.combats_seen % self.COMBATS == 0:
            upgradable = [c for c in run.deck if c.is_upgradable]
            if upgradable:
                run.rng.choice(upgradable).upgrade()
