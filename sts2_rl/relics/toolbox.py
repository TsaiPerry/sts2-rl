from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class Toolbox(Relic):
    """Toolbox.cs — at the start of your first turn, choose 1 of 3 random
    Colorless cards to add to your hand (BeforeHandDraw on turn 1 →
    GetDistinctForCombat over the ColorlessCardPool + choose-a-card screen).
    The sim's pre-draw turn-start slot is on_player_turn_start."""

    id = "toolbox"
    name = "Toolbox"
    rarity = RelicRarity.SHOP
    CARDS = 3

    def on_player_turn_start(self, player) -> None:
        combat = self.combat
        if combat is None or combat.turn != 1:
            return
        from ..cards.pool import COLORLESS_POOL, random_pool_cards
        from ..cmds import CardPileCmd

        options = random_pool_cards(
            combat._rng, self.CARDS, distinct=True, pool=COLORLESS_POOL
        )
        chosen = combat.select_cards("obtain", options, 1)
        for card in chosen:
            CardPileCmd.add_to_hand(combat.hooks, player, card)
