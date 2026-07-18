from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..cards import Card
    from ..player import PlayerCombatState


@register_relic
class BrilliantScarf(Relic):
    """BrilliantScarf.cs — every 5th card you play each turn costs 0
    (TryModifyEnergyCostInCombatLate when CardsPlayedThisTurn == CardsVar(5)
    - 1; the per-turn counter resets at your turn start and ignores
    auto-plays)."""

    id = "brilliant_scarf"
    name = "Brilliant Scarf"
    rarity = RelicRarity.ANCIENT

    CARDS = 5

    def __init__(self) -> None:
        super().__init__()
        self.cards_played_this_turn = 0

    def modify_card_energy_cost(self, card: "Card", cost: int) -> int:
        if self.cards_played_this_turn == self.CARDS - 1:
            return 0
        return cost

    def on_card_played(self, card: "Card") -> None:
        self.cards_played_this_turn += 1

    def on_player_turn_start(self, player: PlayerCombatState) -> None:
        self.cards_played_this_turn = 0
