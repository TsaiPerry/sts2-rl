from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..player import PlayerCombatState


@register_relic
class VexingPuzzlebox(Relic):
    """At the start of your first turn, add a random card from your pool to your
    hand; it costs 0 this turn."""

    id = "vexing_puzzlebox"
    name = "Vexing Puzzlebox"
    rarity = RelicRarity.RARE

    def on_player_turn_started(self, player: PlayerCombatState) -> None:
        if self.turn != 1:
            return
        from ..cards.pool import random_pool_cards
        from ..cmds import CardPileCmd
        cards = random_pool_cards(self.combat._rng, 1)
        if not cards:
            return
        card = cards[0]
        card.set_free_this_turn()
        CardPileCmd.add_to_hand(self.hooks, player, card)
