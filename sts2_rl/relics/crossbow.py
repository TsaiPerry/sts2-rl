from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..player import PlayerCombatState


@register_relic
class Crossbow(Relic):
    """Crossbow.cs — at the start of EACH of your turns, add a random Attack
    from your character's card pool to your hand; it costs 0 this turn
    (GetDistinctForCombat 1 + SetToFreeThisTurn)."""

    id = "crossbow"
    name = "Crossbow"
    rarity = RelicRarity.ANCIENT

    def on_player_turn_started(self, player: PlayerCombatState) -> None:
        from ..cards import CardType
        from ..cards.pool import random_pool_cards
        from ..cmds import CardPileCmd

        cards = random_pool_cards(
            self.combat._rng, 1, card_type=CardType.ATTACK, distinct=True,
            pool=self.combat.card_pool,
        )
        for card in cards:
            card.set_free_this_turn()
            CardPileCmd.add_to_hand(self.hooks, player, card)
