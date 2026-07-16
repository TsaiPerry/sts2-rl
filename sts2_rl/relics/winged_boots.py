from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class WingedBoots(Relic):
    """WingedBoots.cs — you may travel to any point on the next map row
    (ignoring paths) 3 times."""

    id = "winged_boots"
    name = "Winged Boots"
    rarity = RelicRarity.ANCIENT
    USES = 3

    def __init__(self) -> None:
        super().__init__()
        self.times_used = 0

    @property
    def is_used_up(self) -> bool:
        return self.times_used >= self.USES

    def should_allow_free_travel(self) -> bool:
        return not self.is_used_up

    def on_free_travel_used(self, run) -> None:
        self.times_used += 1
