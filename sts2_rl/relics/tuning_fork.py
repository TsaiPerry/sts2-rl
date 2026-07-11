from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic
from ..cards import CardType
from ..valueprops import ValueProp

if TYPE_CHECKING:
    from ..cards import Card


@register_relic
class TuningFork(Relic):
    """Every time you play 10 Skills, gain 7 Block. (The game's counter persists
    across the run; the sim's is per-combat, like Happy Flower.)"""

    id = "tuning_fork"
    name = "Tuning Fork"
    rarity = RelicRarity.UNCOMMON

    SKILLS = 10
    BLOCK = 7

    def __init__(self) -> None:
        super().__init__()
        self._skills_played = 0

    def on_card_played(self, card: Card) -> None:
        if card.card_type != CardType.SKILL:
            return
        self._skills_played += 1
        if self._skills_played >= self.SKILLS:
            self._skills_played -= self.SKILLS
            from ..cmds import BlockCmd
            BlockCmd.apply(self.hooks, self.player, self.BLOCK, props=ValueProp.UNPOWERED)
