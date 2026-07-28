from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic
from ..valueprops import ValueProp

if TYPE_CHECKING:
    from ..cards import Card
    from ..creatures import Creature

@register_relic
class CentennialPuzzle(Relic):
    """The first time you lose HP each combat, draw 3 cards."""

    id = "centennial_puzzle"
    name = "Centennial Puzzle"
    rarity = RelicRarity.COMMON

    def __init__(self) -> None:
        super().__init__()
        self._used_this_combat = False

    def reset_for_combat(self) -> None:
        # CentennialPuzzle.AfterCombatEnd (:53-57).
        self._used_this_combat = False

    def on_damage_received(
        self,
        target: Creature,
        amount: int,
        dealer: Creature | None,
        card: Card | None,
        props: ValueProp,
    ) -> None:
        if target is self.player and amount > 0 and not self._used_this_combat:
            from ..cmds import DrawCmd
            self._used_this_combat = True
            DrawCmd.draw(self.player, 3)
