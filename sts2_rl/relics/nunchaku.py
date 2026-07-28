from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic
from ..cards import CardType

if TYPE_CHECKING:
    from ..cards import Card


@register_relic
class Nunchaku(Relic):
    """Every time you play 10 Attacks, gain 1 energy. (The game's counter
    persists across the run; the sim's is per-combat, like Happy Flower.)"""

    id = "nunchaku"
    name = "Nunchaku"
    rarity = RelicRarity.UNCOMMON

    ATTACKS = 10

    def __init__(self) -> None:
        super().__init__()
        self._attacks_played = 0

    def on_card_played(self, card: Card,
                       is_auto_play: bool = False) -> None:
        if card.card_type != CardType.ATTACK:
            return
        self._attacks_played += 1
        if self._attacks_played % self.ATTACKS == 0:
            from ..cmds import EnergyCmd
            EnergyCmd.gain(self.hooks, self.player, 1)
