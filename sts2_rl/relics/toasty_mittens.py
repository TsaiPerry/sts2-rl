from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..player import PlayerCombatState


@register_relic
class ToastyMittens(Relic):
    """ToastyMittens.cs — at the start of each turn (BeforeHandDraw), exhaust
    the top card of the draw pile (reshuffling first if needed). On turn 1 the
    first non-Innate card is taken instead, so Innate cards aren't burned."""

    id = "toasty_mittens"
    name = "Toasty Mittens"
    rarity = RelicRarity.ANCIENT

    STRENGTH = 1   # PowerVar<StrengthPower>(1m), ToastyMittens.cs:20

    def on_player_turn_start(self, player: PlayerCombatState) -> None:
        from ..cmds import ExhaustCmd, PowerCmd
        from ..powers import StrengthPower

        # ToastyMittens.cs:50 sits OUTSIDE the `if (cardModel != null)` branch
        # that guards the exhaust (:46-49), so the Strength lands EVERY turn —
        # including a turn where both piles are empty and nothing is exhausted.
        # The port had no Strength at all.
        def _grant() -> None:
            PowerCmd.apply(self.hooks, player, StrengthPower, self.STRENGTH,
                           applier=player)

        if not player.draw_pile and player.discard_pile:
            player.reshuffle_discard_into_draw()
        # The sim's draw-pile top is the list END (see PerfectFit).
        pile = player.draw_pile
        if not pile:
            _grant()
            return
        card = None
        if self.turn == 1:
            card = next(
                (c for c in reversed(pile) if not c.innate), None,
            )
        if card is None:
            card = pile[-1]
        pile.remove(card)
        player.exhaust_pile.append(card)
        self.hooks.on_card_exhausted(card)
        _grant()
