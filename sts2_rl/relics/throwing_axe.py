from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..cards import Card
    from ..creatures import Creature


@register_relic
class ThrowingAxe(Relic):
    """ThrowingAxe.cs — the FIRST card you play each combat is played twice
    (ModifyCardPlayCount +1, once per combat; AfterModifyingCardPlayCount
    marks it used — the sim marks it inside the modifier, which only fires on
    an actual play)."""

    id = "throwing_axe"
    name = "Throwing Axe"
    rarity = RelicRarity.ANCIENT

    def __init__(self) -> None:
        super().__init__()
        self.used_this_combat = False

    def on_combat_start(self) -> None:
        self.used_this_combat = False

    def modify_card_play_count(
        self, card: "Card", target: "Creature | None", count: int,
    ) -> int:
        if self.used_this_combat:
            return count
        self.used_this_combat = True
        return count + 1
