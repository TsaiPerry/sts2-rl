from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class TrueGritCard(Card):
    """Skill (Common, 1E) — gain 7 block; exhaust a random card from your hand.

    Source: TrueGrit.cs
      Cost 1 | Skill | Common | TargetType.Self
      OnPlay: GainBlock(7), then exhaust a random hand card
      OnUpgrade: block +2 (→ 9)

    Deviation: the upgraded card lets the player CHOOSE the card to exhaust;
    the sim has no in-combat selection screens, so the upgraded version also
    exhausts randomly.
    """
    id = "true_grit"
    name = "True Grit"
    card_type = CardType.SKILL
    rarity = CardRarity.COMMON
    target_type = TargetType.SELF

    def _init_vars(self) -> None:
        self._energy_cost = 1
        self._block = 7

    def _on_upgrade(self) -> None:
        self._block += 2

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import BlockCmd, ExhaustCmd
        BlockCmd.apply(ctx.hooks, ctx.player, self._block, card=self)
        if ctx.player.hand:
            victim = ctx.combat._rng.choice(ctx.player.hand)
            ExhaustCmd.exhaust(ctx.hooks, ctx.player, victim)
