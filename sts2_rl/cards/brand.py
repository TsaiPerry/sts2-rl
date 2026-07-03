from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class BrandCard(Card):
    """Skill (Rare, 0E) — lose 1 HP; exhaust a CHOSEN card from your hand;
    gain 1 Strength.

    Source: Brand.cs
      Cost 0 | Skill | Rare | TargetType.Self
      OnPlay: Damage(owner, 1, Unblockable|Unpowered|Move) →
        CardSelectCmd.FromHand(1, exhaust prompt) → CardCmd.Exhaust →
        StrengthPower 1
      OnUpgrade: Strength +1 (→ 2)
    """
    id = "brand"
    name = "Brand"
    card_type = CardType.SKILL
    rarity = CardRarity.RARE
    target_type = TargetType.SELF

    def _init_vars(self) -> None:
        self._energy_cost = 0
        self._hp_loss = 1
        self._strength = 1

    def _on_upgrade(self) -> None:
        self._strength += 1

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import CardSelectCmd, DamageCmd, ExhaustCmd, StrengthCmd
        from ..valueprops import DamageProps
        DamageCmd.deal(
            ctx.hooks, ctx.player, self._hp_loss,
            dealer=ctx.player, card=self, props=DamageProps.CARD_HP_LOSS,
        )
        if ctx.player.is_dead:
            return
        chosen = CardSelectCmd.from_hand(ctx.hooks, ctx.player, "exhaust")
        if chosen:
            ExhaustCmd.exhaust(ctx.hooks, ctx.player, chosen[0])
        StrengthCmd.apply(ctx.hooks, ctx.player, self._strength, card=self)
