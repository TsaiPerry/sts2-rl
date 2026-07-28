from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic
from ..cards import CardType

if TYPE_CHECKING:
    from ..cards import Card
    from ..player import PlayerCombatState

@register_relic
class ArtOfWar(Relic):
    """If you played no Attacks last turn, gain 1 extra energy at the start
    of your turn (from turn 2 on)."""

    id = "art_of_war"
    name = "Art of War"
    rarity = RelicRarity.RARE

    def __init__(self) -> None:
        super().__init__()
        self._attacks_last_turn = False
        self._attacks_this_turn = False

    def on_card_played(self, card: Card,
                       is_auto_play: bool = False) -> None:
        if card.card_type != CardType.ATTACK:
            return
        if self._attacks_last_turn:
            return
        self._attacks_this_turn = True

    def on_player_turn_end(self, player: PlayerCombatState) -> None:
        self._attacks_last_turn = self._attacks_this_turn
        self._attacks_this_turn = False

    def on_energy_reset(self, player: PlayerCombatState) -> None:
        if self.turn <= 1:
            return
        if not self._attacks_last_turn:
            from ..cmds import EnergyCmd
            EnergyCmd.gain(self.hooks, player, 1)
        self._attacks_last_turn = False
        self._attacks_this_turn = False
