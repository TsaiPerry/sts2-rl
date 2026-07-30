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

    def after_side_turn_start(self, player: PlayerCombatState) -> None:
        from ..cards import CardType
        from ..cards.pool import get_distinct_for_combat_parity
        from ..cmds import CardPileCmd

        # Crossbow.cs:31 -- GetDistinctForCombat on Rng.CombatCardGeneration,
        # whose TakeRandom is UnstableShuffle + Take(1), not `rng.sample`.
        cards = get_distinct_for_combat_parity(
            self.combat.combat_rng.card_gen, 1, CardType.ATTACK,
            pool=self.combat.card_pool,
        )
        for card in cards:
            card.set_free_this_turn()
            CardPileCmd.add_to_hand(self.hooks, player, card)
