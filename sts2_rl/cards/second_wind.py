from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class SecondWindCard(Card):
    """Skill (Uncommon, 1E) — exhaust every non-Attack in your hand; gain 5 block per card.

    Source: SecondWind.cs
      Cost 1 | Skill | Uncommon | TargetType.Self
      OnPlay: for each non-Attack in hand: exhaust it, then GainBlock(5)
      OnUpgrade: block +2 (→ 7)
    """
    id = "second_wind"
    gains_block = True  # CardModel.GainsBlock
    name = "Second Wind"
    card_type = CardType.SKILL
    rarity = CardRarity.UNCOMMON
    target_type = TargetType.SELF

    def _init_vars(self) -> None:
        self._energy_cost = 1
        self._block = 5

    def _on_upgrade(self) -> None:
        self._block += 2

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import BlockCmd, ExhaustCmd
        non_attacks = [c for c in ctx.player.hand if c.card_type != CardType.ATTACK]
        for card in non_attacks:
            ExhaustCmd.exhaust(ctx.hooks, ctx.player, card)
            BlockCmd.apply(ctx.hooks, ctx.player, self._block, card=self)
