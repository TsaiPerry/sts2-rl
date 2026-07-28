from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..cards import Card
    from ..player import PlayerCombatState


@register_relic
class VelvetChoker(Relic):
    """VelvetChoker.cs — gain 1 extra energy each turn, but you cannot play
    more than 6 cards in a single turn (ShouldPlay is false once the count is
    reached). Offered by the Darv shrine in act 3."""

    id = "velvet_choker"
    name = "Velvet Choker"
    rarity = RelicRarity.ANCIENT

    ENERGY = 1
    CARDS_PER_TURN = 6

    def __init__(self) -> None:
        super().__init__()
        self.cards_played_this_turn = 0

    def modify_max_energy(self, player: PlayerCombatState, amount: int) -> int:
        return amount + self.ENERGY

    def should_play_card(self, card: Card, auto_play: bool = False) -> bool:
        return self.cards_played_this_turn < self.CARDS_PER_TURN

    def on_card_played(self, card: Card,
                       is_auto_play: bool = False) -> None:
        self.cards_played_this_turn += 1

    def on_player_turn_start(self, player: PlayerCombatState) -> None:
        # The source resets on AfterRoomEntered (once per combat); the sim
        # resets per turn, which is what the 6-cards-PER-TURN rule needs and
        # what the counter display implies (DisplayAmount is per turn).
        self.cards_played_this_turn = 0
