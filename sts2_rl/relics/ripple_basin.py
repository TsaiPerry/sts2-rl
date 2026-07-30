from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic
from ..cards import CardType
from ..valueprops import ValueProp

if TYPE_CHECKING:
    from ..cards import Card
    from ..player import PlayerCombatState


@register_relic
class RippleBasin(Relic):
    """At the end of your turn, if you played no Attacks this turn, gain 4
    Block."""

    id = "ripple_basin"
    name = "Ripple Basin"
    rarity = RelicRarity.UNCOMMON

    BLOCK = 4

    def __init__(self) -> None:
        super().__init__()
        self._attack_this_turn = False

    def before_side_turn_start(self, player: PlayerCombatState) -> None:
        self._attack_this_turn = False

    def on_card_played(self, card: Card,
                       is_auto_play: bool = False) -> None:
        if card.card_type == CardType.ATTACK:
            self._attack_this_turn = True

    def on_player_turn_end(self, player: PlayerCombatState) -> None:
        if not self._attack_this_turn:
            from ..cmds import BlockCmd
            BlockCmd.apply(self.hooks, player, self.BLOCK, props=ValueProp.UNPOWERED)
