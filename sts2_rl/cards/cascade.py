from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class CascadeCard(Card):
    """Skill (Rare, X) — auto-play the top X cards of your draw pile.

    Source: Cascade.cs
      Cost X | Skill | Rare | TargetType.Self
      OnPlay: num = ResolveEnergyXValue() (+1 if upgraded);
        CardPileCmd.AutoPlayFromDrawPile(num, Top, forceExhaust: false) —
        the cards are pulled off the draw pile first (reshuffling the discard
        pile in when needed), then auto-played in order
      OnUpgrade: plays X+1 cards
    """
    id = "cascade"
    name = "Cascade"
    card_type = CardType.SKILL
    rarity = CardRarity.RARE
    target_type = TargetType.SELF
    energy_cost_x = True

    def _init_vars(self) -> None:
        self._energy_cost = 0

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        num = self.captured_x + (1 if self.upgrade_level > 0 else 0)
        # In the game the resolving card sits in the Play pile; here it is
        # already in the discard pile, so step out of it while resolving —
        # otherwise a reshuffle could sweep Cascade up and auto-play itself.
        in_discard = self in ctx.player.discard_pile
        if in_discard:
            ctx.player.discard_pile.remove(self)
        try:
            # Pull all num cards off the draw pile before playing any (mirrors
            # AutoPlayFromDrawPile moving them to the Play pile in one pass).
            cards = []
            for _ in range(num):
                if not ctx.player.draw_pile:
                    if not ctx.player.discard_pile:
                        break
                    ctx.player.reshuffle_discard_into_draw()
                cards.append(ctx.player.draw_pile.pop())
            for card in cards:
                if ctx.combat.is_over or ctx.player.is_dead:
                    break
                ctx.combat.auto_play_card(card)
        finally:
            if in_discard:
                ctx.player.discard_pile.append(self)
