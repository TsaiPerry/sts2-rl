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

    def on_player_turn_start(self, player: PlayerCombatState) -> None:
        from ..cmds import ExhaustCmd

        if not player.draw_pile and player.discard_pile:
            player.reshuffle_discard_into_draw()
        # The sim's draw-pile top is the list END (see PerfectFit).
        pile = player.draw_pile
        if not pile:
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
