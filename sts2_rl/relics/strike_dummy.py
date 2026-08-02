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
        # damage_pipeline/G3, relic/strike_dummy (round 14): StrikeDummy.cs:
        # 33-36 declines only when BOTH `dealer != Owner.Creature` AND
        # `cardSource.Owner != Owner` -- either disjunct alone is enough to
        # keep the bonus. The sim has no enemy-owned CardModel (every card
        # in this scope belongs to the player), so `cardSource.Owner ==
        # Owner` (self.player) always holds and the second disjunct can
        # never be true -- the AND can never be satisfied, so the relic
        # never actually declines on dealer grounds. The old `dealer is
        # self.player` guard dropped the bonus whenever a Strike card's
        # damage was attributed to a non-player dealer even though the card
        # itself is still the player's; today every ported Strike-tagged
        # attack card deals with dealer=ctx.player (grepped), so this was
        # unobservable, but the guard was still wrong and would have bitten
        # the first ported effect that routes card damage through a
        # different dealer (a delegated or reflected hit).
        return self.EXTRA_DAMAGE
