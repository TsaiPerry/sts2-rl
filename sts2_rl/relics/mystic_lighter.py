from __future__ import annotations

from typing import TYPE_CHECKING

from ..valueprops import ValueProp, is_powered_attack
from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..cards import Card
    from ..creatures import Creature


@register_relic
class MysticLighter(Relic):
    """MysticLighter.cs — your Enchanted attacks deal 9 additional damage
    (ModifyDamageAdditive: IsPoweredAttack, the source card has an
    Enchantment, and the card is the owner's)."""

    id = "mystic_lighter"
    name = "Mystic Lighter"
    rarity = RelicRarity.SHOP

    EXTRA_DAMAGE = 9   # DamageVar(9, ValueProp.Unpowered)

    def modify_damage_additive(
        self,
        target: "Creature",
        amount: int,
        dealer: "Creature | None",
        card: "Card | None",
        props: ValueProp = ValueProp.NONE,
    ) -> int:
        if not is_powered_attack(props):        # MysticLighter.cs:18-21
            return 0
        if card is None or card.enchantment is None:
            return 0
        if dealer is not self.player:
            return 0
        return self.EXTRA_DAMAGE
