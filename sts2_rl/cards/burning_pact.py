from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class BurningPactCard(Card):
    """Skill (Uncommon, 1E) — exhaust a CHOSEN card from your hand; draw 2.

    Source: BurningPact.cs
      Cost 1 | Skill | Uncommon | TargetType.Self
      OnPlay: CardSelectCmd.FromHand(1, exhaust prompt) → CardCmd.Exhaust →
        Draw(2)
      OnUpgrade: cards +1 (→ 3)
    """
    id = "burning_pact"
    name = "Burning Pact"
    card_type = CardType.SKILL
    rarity = CardRarity.UNCOMMON
    target_type = TargetType.SELF

    def _init_vars(self) -> None:
        self._energy_cost = 1
        self._cards = 2

    def _on_upgrade(self) -> None:
        self._cards += 1

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import CardSelectCmd, DrawCmd, ExhaustCmd
        chosen = CardSelectCmd.from_hand(ctx.hooks, ctx.player, "exhaust")
        if chosen:
            ExhaustCmd.exhaust(ctx.hooks, ctx.player, chosen[0])
        DrawCmd.draw(ctx.player, self._cards)
