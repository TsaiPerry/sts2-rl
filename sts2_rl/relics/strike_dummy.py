from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..cards import Card
    from ..creatures import Creature


@register_relic
class StrikeDummy(Relic):
    """Strike cards (cards with "Strike" in the name) deal 3 additional
    damage."""

    id = "strike_dummy"
    name = "Strike Dummy"
    rarity = RelicRarity.COMMON

    EXTRA_DAMAGE = 3

    def modify_damage_additive(
        self,
        target: Creature,
        amount: int,
        dealer: Creature | None,
        card: Card | None,
    ) -> int:
        if card is not None and "strike" in card.tags and dealer is self.player:
            return self.EXTRA_DAMAGE
        return 0
