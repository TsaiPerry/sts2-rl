from __future__ import annotations

from typing import TYPE_CHECKING

from ..valueprops import ValueProp, is_powered_attack
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
        props: ValueProp = ValueProp.NONE,
    ) -> int:
        if not is_powered_attack(props):   # StrikeDummy.cs
            return 0
        if card is None or "strike" not in card.tags:
            return 0
        # StrikeDummy.cs:33-36 declines only when BOTH `dealer != Owner.Creature`
        # AND `cardSource.Owner != Owner`. The sim has no enemy-owned CardModel,
        # so `cardSource.Owner == Owner` always holds and the AND can never be
        # satisfied -- don't gate on `dealer is self.player` alone, that would
        # wrongly drop the bonus for a delegated/reflected hit.
        return self.EXTRA_DAMAGE
