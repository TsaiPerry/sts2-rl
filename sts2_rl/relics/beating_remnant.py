from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic
from ..valueprops import ValueProp

if TYPE_CHECKING:
    from ..cards import Card
    from ..creatures import Creature
    from ..player import PlayerCombatState

@register_relic
class BeatingRemnant(Relic):
    """You cannot lose more than 20 HP per turn."""

    id = "beating_remnant"
    name = "Beating Remnant"
    rarity = RelicRarity.RARE

    MAX_HP_LOSS = 20

    def __init__(self) -> None:
        super().__init__()
        self._received_this_turn = 0

    def modify_hp_lost(
        self,
        target: Creature,
        amount: int,
        dealer: Creature | None,
        card: Card | None,
    ) -> int:
        if target is not self.player:
            return amount
        return min(amount, self.MAX_HP_LOSS - self._received_this_turn)

    def on_damage_received(
        self,
        target: Creature,
        amount: int,
        dealer: Creature | None,
        card: Card | None,
        props: ValueProp,
    ) -> None:
        if target is self.player:
            self._received_this_turn += amount

    def on_player_turn_start(self, player: PlayerCombatState) -> None:
        self._received_this_turn = 0
