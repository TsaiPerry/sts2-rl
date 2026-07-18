from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..player import PlayerCombatState


@register_relic
class ChoicesParadox(Relic):
    """ChoicesParadox.cs — on turn 1 (AfterPlayerTurnStart), generate 5
    distinct cards from your character's pool (CardsVar(5)), give each
    Retain, and choose 1 to add to your hand."""

    id = "choices_paradox"
    name = "Choice's Paradox"
    rarity = RelicRarity.ANCIENT

    CARDS = 5

    def on_player_turn_started(self, player: PlayerCombatState) -> None:
        if self.turn != 1:
            return
        from ..cards.pool import random_pool_cards
        from ..cmds import CardPileCmd

        options = random_pool_cards(
            self.combat._rng, self.CARDS, distinct=True,
        )
        if not options:
            return
        for card in options:
            card.retain = True
        for card in self.combat.select_cards("obtain", options, 1):
            CardPileCmd.add_to_hand(self.hooks, player, card)
