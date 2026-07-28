from __future__ import annotations

from typing import TYPE_CHECKING

from ..valueprops import ValueProp, is_powered_attack
from .base import Relic, RelicRarity, register_relic
from ..cards import CardType

if TYPE_CHECKING:
    from ..cards import Card
    from ..creatures import Creature


@register_relic
class PenNib(Relic):
    """Every 10th Attack you play deals double damage. The 10th Attack is
    marked as it starts (before_card_played) and doubled through the damage
    multiplier for every hit it deals, then unmarked once it resolves."""

    id = "pen_nib"
    name = "Pen Nib"
    rarity = RelicRarity.UNCOMMON

    ATTACKS = 10

    def __init__(self) -> None:
        super().__init__()
        self._attacks_played = 0
        self._card_to_double: Card | None = None

    def before_card_played(self, card: Card, target: Creature | None = None) -> None:
        if card.card_type != CardType.ATTACK:
            return
        self._attacks_played = (self._attacks_played + 1) % self.ATTACKS
        if self._attacks_played == 0:
            self._card_to_double = card

    def modify_damage_multiplicative(
        self,
        target: Creature,
        amount: int,
        dealer: Creature | None,
        card: Card | None,
        props: ValueProp = ValueProp.NONE,
    ) -> float:
        if not is_powered_attack(props):   # PenNib.cs:108
            return 1.0
        if dealer is self.player and card is not None and card is self._card_to_double:
            return 2.0
        return 1.0

    def on_card_played(self, card: Card,
                       is_auto_play: bool = False) -> None:
        if card is self._card_to_double:
            self._card_to_double = None
