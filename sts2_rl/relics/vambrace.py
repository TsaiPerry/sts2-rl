from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..cards import Card
    from ..creatures import Creature


@register_relic
class Vambrace(Relic):
    """The first time you gain Block from a card each combat, double it. The
    multiplier hook stays stateless (safe for previews); the one-shot flag is
    set from the real on_block_gained event."""

    id = "vambrace"
    name = "Vambrace"
    rarity = RelicRarity.UNCOMMON

    def __init__(self) -> None:
        super().__init__()
        self._used = False

    def modify_block_multiplicative(
        self,
        target: Creature,
        amount: int,
        card: Card | None = None,
    ) -> float:
        if not self._used and card is not None and target is self.player:
            return 2.0
        return 1.0

    def on_block_gained(
        self, target: Creature, amount: int, card: Card | None = None
    ) -> None:
        if not self._used and card is not None and target is self.player and amount > 0:
            self._used = True
