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
        from ..cards.pool import get_distinct_for_combat_parity, random_pool_cards
        from ..cmds import CardPileCmd
        # VexingPuzzlebox.AfterPlayerTurnStart: one card from the character pool
        # via GetDistinctForCombat(..., 1, Rng.CombatCardGeneration). Parity
        # routes to the CombatCardGeneration stream + game UnstableShuffle;
        # legacy keeps the shared-Random sample (byte-for-byte RL behaviour).
        crng = self.combat.combat_rng
        if crng.is_parity:
            cards = get_distinct_for_combat_parity(
                crng.card_gen, 1, pool=self.combat.card_pool
            )
        else:
            cards = random_pool_cards(
                self.combat._rng, 1, pool=self.combat.card_pool
            )
        if not cards:
            return
        card = cards[0]
        card.set_free_this_turn()
        CardPileCmd.add_to_hand(self.hooks, player, card)
