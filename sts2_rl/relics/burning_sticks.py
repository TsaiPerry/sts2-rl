from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic
from ..cards import CardType

if TYPE_CHECKING:
    from ..cards import Card

@register_relic
class BurningSticks(Relic):
    """The first time you exhaust a Skill each combat, add a copy of it to
    your hand."""

    id = "burning_sticks"
    name = "Burning Sticks"
    rarity = RelicRarity.SHOP

    def __init__(self) -> None:
        super().__init__()
        self._used_this_combat = False

    def on_card_exhausted(self, card: Card) -> None:
        if self._used_this_combat or card.card_type != CardType.SKILL:
            return
        from ..cards import make_card
        from ..cmds import CardPileCmd
        self._used_this_combat = True
        clone = make_card(card.id)
        for _ in range(card.upgrade_level):
            clone.upgrade()
        CardPileCmd.add_to_hand(self.hooks, self.player, clone)
