from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic
from ..cards import CardType

if TYPE_CHECKING:
    from ..cards import Card
    from ..player import PlayerCombatState


@register_relic
class Shuriken(Relic):
    """Every time you play 3 Attacks in a single turn, gain 1 Strength."""

    id = "shuriken"
    name = "Shuriken"
    rarity = RelicRarity.RARE

    ATTACKS = 3

    def __init__(self) -> None:
        super().__init__()
        self._attacks_this_turn = 0

    def before_side_turn_start(self, player: PlayerCombatState) -> None:
        self._attacks_this_turn = 0

    def on_card_played(self, card: Card,
                       is_auto_play: bool = False) -> None:
        if card.card_type != CardType.ATTACK:
            return
        self._attacks_this_turn += 1
        if self._attacks_this_turn % self.ATTACKS == 0:
            from ..cmds import PowerCmd
            from ..powers import StrengthPower
            PowerCmd.apply(
                self.hooks, self.player, StrengthPower, 1, applier=self.player
            )
