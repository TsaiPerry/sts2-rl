from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic
from ..valueprops import ValueProp

if TYPE_CHECKING:
    from ..cards import Card

@register_relic
class IntimidatingHelmet(Relic):
    """Whenever you play a card by spending 2 or more energy, gain 4 Block."""

    id = "intimidating_helmet"
    name = "Intimidating Helmet"
    rarity = RelicRarity.RARE

    def on_energy_spent(self, card: Card, amount: int) -> None:
        if amount >= 2:
            from ..cmds import BlockCmd
            BlockCmd.apply(self.hooks, self.player, 4, props=ValueProp.UNPOWERED)
