from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..cards import Card
    from ..creatures import Creature


@register_relic
class TheBoot(Relic):
    """When you would deal 4 or less unblocked damage with a powered attack,
    deal 5 instead.

    Source: TheBoot.cs — ModifyHpLostAfterOstyLate: for a powered attack from
    the owner against an enemy, if the HP that would be lost is between 1 and 4,
    raise it to the 5 minimum. Granted by the Trash Heap event."""

    id = "the_boot"
    name = "The Boot"
    rarity = RelicRarity.EVENT

    MINIMUM = 5

    def modify_hp_lost_late(
        self,
        target: Creature,
        amount: int,
        dealer: Creature | None,
        card: Card | None,
    ) -> int:
        # TheBoot.cs:26 is ModifyHpLostAfterOsty**Late** — the second complete
        # AfterOsty pass (Hook.cs:1753-1760), after the plain one
        # (Hook.cs:1745-1752) that Tungsten Rod is on. Sharing Tungsten Rod's
        # pass made the outcome depend on relic acquisition order.
        if dealer is not self.player or target is self.player:
            return amount
        # IsPoweredAttack: a card attack that isn't marked unpowered.
        if card is None or card.is_unpowered:
            return amount
        if 1 <= amount < self.MINIMUM:
            return self.MINIMUM
        return amount
