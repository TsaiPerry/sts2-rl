from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class FightMeCard(Card):
    """Attack (Uncommon, 2E) — deal 5 damage twice; gain 3 Strength; the target gains 1 Strength.

    Source: FightMe.cs
      Cost 2 | Attack | Uncommon | TargetType.AnyEnemy
      Damage 5 × Repeat 2, then Strength 3 (self) and Strength 1 (target)
      OnUpgrade: damage +1 (→ 6), self Strength +1 (→ 4)
    """
    id = "fight_me"
    name = "Fight Me"
    card_type = CardType.ATTACK
    rarity = CardRarity.UNCOMMON
    target_type = TargetType.ANY_ENEMY

    def _init_vars(self) -> None:
        self._energy_cost = 2
        self._damage = 5
        self._hits = 2
        self._strength = 3
        self._enemy_strength = 1

    def _on_upgrade(self) -> None:
        self._damage += 1
        self._strength += 1

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import DamageCmd, StrengthCmd
        target = ctx.resolve_target(target_idx)
        for _ in range(self._hits):
            if target.is_gone or ctx.player.is_dead:
                break
            DamageCmd.deal(ctx.hooks, target, self._damage, dealer=ctx.player, card=self)
        StrengthCmd.apply(ctx.hooks, ctx.player, self._strength, card=self)
        if not target.is_gone:
            StrengthCmd.apply(ctx.hooks, target, self._enemy_strength, card=self)
