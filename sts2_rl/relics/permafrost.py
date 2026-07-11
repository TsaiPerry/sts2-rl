from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic
from ..cards import CardType
from ..valueprops import ValueProp

if TYPE_CHECKING:
    from ..cards import Card


@register_relic
class Permafrost(Relic):
    """The first Power card you play each combat grants 7 Block."""

    id = "permafrost"
    name = "Permafrost"
    rarity = RelicRarity.UNCOMMON

    BLOCK = 7

    def __init__(self) -> None:
        super().__init__()
        self._activated = False

    def on_card_played(self, card: Card) -> None:
        if card.card_type == CardType.POWER and not self._activated:
            self._activated = True
            from ..cmds import BlockCmd
            BlockCmd.apply(self.hooks, self.player, self.BLOCK, props=ValueProp.UNPOWERED)
