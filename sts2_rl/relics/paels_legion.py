from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..cards import Card
    from ..creatures import Creature


@register_relic
class PaelsLegion(Relic):
    """PaelsLegion.cs — an event pet (AddsPet): while off cooldown, the first
    card play that gains you Block each turn has its Block DOUBLED
    (ModifyBlockMultiplicative ×2 on the owner's card block), then the pet
    sleeps for 2 turns (DynamicVar "Turns"; the cooldown ticks down at each
    player turn start). The pet creature itself is cosmetic — the block
    doubling lives on the relic — so the sim models the pet as the AddsPet
    flag (gating Pael's Legion at the shrine) without a combat creature."""

    id = "paels_legion"
    name = "Pael's Legion"
    rarity = RelicRarity.ANCIENT
    adds_pet = True

    COOLDOWN_TURNS = 2

    def __init__(self) -> None:
        super().__init__()
        self.cooldown = 0
        # The card play currently being doubled (mirrors AffectedCardPlay:
        # only ONE play per activation starts the cooldown).
        self._affected_card: "Card | None" = None

    def modify_block_multiplicative(
        self, target: "Creature", amount: int, card: "Card | None" = None,
    ) -> float:
        # Owner's card-sourced block only, while awake.
        if card is None or self.cooldown > 0 or target is not self.player:
            return 1.0
        self._affected_card = card
        return 2.0

    def on_card_played(self, card: "Card") -> None:
        # AfterCardPlayed: the doubled play ends — start the cooldown.
        if self._affected_card is card:
            self._affected_card = None
            self.cooldown = self.COOLDOWN_TURNS

    def on_player_turn_start(self, player) -> None:
        # AfterSideTurnStart: tick the cooldown down.
        if self.cooldown > 0:
            self.cooldown -= 1
