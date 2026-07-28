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
        from ..cards.pool import get_distinct_for_combat_parity, random_pool_cards
        from ..cmds import CardPileCmd

        # ChoicesParadox.cs:34 passes RunState.Rng.CombatCardGeneration to
        # GetDistinctForCombat (== UnstableShuffle(rng).Take(5)); parity routes
        # there, legacy keeps the shared-Random sample byte-for-byte.
        crng = self.combat.combat_rng
        if crng.is_parity:
            options = get_distinct_for_combat_parity(
                crng.card_gen, self.CARDS, pool=self.combat.card_pool
            )
        else:
            options = random_pool_cards(
                self.combat._rng, self.CARDS, distinct=True,
                pool=self.combat.card_pool,
            )
        if not options:
            return
        for card in options:
            card.retain = True
        # ChoicesParadox.cs:46 is `CardSelectorPrefs(prompt, 1)` — the 2-arg
        # ctor (CardSelectorPrefs.cs:63-67 -> `this(prompt, n, n)`), so
        # MinSelect == MaxSelect == 1 and the screen cannot be left empty.
        # A purpose in driver.SKIPPABLE_PURPOSES would offer a decline the
        # game forbids.
        for card in self.combat.select_cards("choose_a_card", options, 1):
            CardPileCmd.add_to_hand(self.hooks, player, card)
