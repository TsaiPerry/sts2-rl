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
        from ..cards.pool import (
            COLORLESS_POOL, get_distinct_for_combat_parity, random_pool_cards,
        )
        from ..cmds import CardPileCmd

        # Toolbox.cs:27 passes RunState.Rng.CombatCardGeneration to
        # GetDistinctForCombat (== UnstableShuffle(rng).Take(3)); parity routes
        # there, legacy keeps the shared-Random sample byte-for-byte.
        crng = combat.combat_rng
        if crng.is_parity:
            options = get_distinct_for_combat_parity(
                crng.card_gen, self.CARDS, pool=COLORLESS_POOL
            )
        else:
            options = random_pool_cards(
                combat._rng, self.CARDS, distinct=True, pool=COLORLESS_POOL
            )
        # Toolbox.cs:28 is the `FromChooseACardScreen(context, cards, player)`
        # overload without `canSkip`, which DEFAULTS to false (CardSelectCmd
        # .cs:216) — the player must take one of the three. The sim models a
        # decline exactly when the purpose is in driver.SKIPPABLE_PURPOSES, so
        # this screen must NOT use one that is ("obtain" is).
        # `FromChooseACardScreen` (CardSelectCmd.cs:216-261) has no auto-select
        # shortcut at all — has_shortcut=False.
        chosen = combat.select_cards("choose_a_card", options, 1, has_shortcut=False)
        for card in chosen:
            CardPileCmd.add_to_hand(combat.hooks, player, card)
