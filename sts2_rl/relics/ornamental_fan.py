from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic
from ..cards import CardType
from ..valueprops import ValueProp

if TYPE_CHECKING:
    from ..cards import Card
    from ..player import PlayerCombatState


@register_relic
class OrnamentalFan(Relic):
    """Every time you play 3 Attacks in a single turn, gain 4 Block."""

    id = "ornamental_fan"
    name = "Ornamental Fan"
    rarity = RelicRarity.UNCOMMON

    ATTACKS = 3
    BLOCK = 4

    def __init__(self) -> None:
        super().__init__()
        self._attacks_this_turn = 0

    def before_side_turn_start(self, player: PlayerCombatState) -> None:
        self._attacks_this_turn = 0

    def on_card_played(self, card: Card,
                       is_auto_play: bool = False) -> None:
        if card.card_type != CardType.ATTACK:
            return
        self._attacks_this_turn += 1
        if self._attacks_this_turn % self.ATTACKS == 0:
            from ..cmds import BlockCmd
            BlockCmd.apply(self.hooks, self.player, self.BLOCK, props=ValueProp.UNPOWERED)
