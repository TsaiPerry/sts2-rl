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
        # Cascade.cs:23 is ONE statement: `await CardPileCmd.AutoPlayFromDraw
        # Pile(choiceContext, Owner, num, CardPilePosition.Top,
        # forceExhaust: false)`. This method used to reimplement the verb's
        # two phases inline, which meant its phase-1 picks were parked in NO
        # pile (C# parks them in `PileType.Play`, CardPileCmd.cs:954) and its
        # per-card break tested `combat.is_over` where C# tests only
        # `item.Owner.Creature.IsDead` (:958).
        #
        # It also had to take ITSELF out of the discard pile for the duration
        # and put it back in a `finally`, because the sim parked a resolving
        # card in the discard and a reshuffle would otherwise have handed
        # Cascade back to the draw pile for its own verb to replay. That is
        # structural now: the resolving card sits in `PileType.Play`
        # (CardModel.cs:1875) and `CardPileCmd.Shuffle` reads only the Draw and
        # Discard piles (CardPileCmd.cs:870-871). Round 13, R5.
        from ..cmds import CardPileCmd
        CardPileCmd.auto_play_from_draw_pile(
            ctx.hooks, ctx.player, num, position="top", force_exhaust=False)
