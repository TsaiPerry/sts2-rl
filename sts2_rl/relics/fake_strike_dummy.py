from __future__ import annotations

from typing import TYPE_CHECKING

from ..valueprops import ValueProp, is_powered_attack
from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..cards import Card
    from ..creatures import Creature


@register_relic
class FakeStrikeDummy(Relic):
    """FakeStrikeDummy.cs — Strike cards deal 1 additional damage (the real
    Strike Dummy gives 3). Fake Merchant knock-off, 50 gold."""

    id = "fake_strike_dummy"
    name = "Fake Strike Dummy"
    rarity = RelicRarity.EVENT
    merchant_cost_override = 50  # RelicModel.MerchantCost

    EXTRA_DAMAGE = 1

    def modify_damage_additive(
        self,
        target: Creature,
        amount: int,
        dealer: Creature | None,
        card: Card | None,
        props: ValueProp = ValueProp.NONE,
    ) -> int:
        if not is_powered_attack(props):   # FakeStrikeDummy.cs
            return 0
        if card is not None and "strike" in card.tags and dealer is self.player:
            return self.EXTRA_DAMAGE
        return 0
