from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx
    from ..creatures import Creature


@register_card
class AshenStrikeCard(Card):
    """Attack (Uncommon, 1E) — deal 6 + 3 damage per card in the exhaust pile.

    Source: AshenStrike.cs
      Cost 1 | Attack | Uncommon | TargetType.AnyEnemy | Strike tag
      CalculationBase 6, ExtraDamage 3, multiplier = exhaust pile count
      OnUpgrade: extra damage +1 (→ 6 + 4×count)
    """
    id = "ashen_strike"
    name = "Ashen Strike"
    card_type = CardType.ATTACK
    rarity = CardRarity.UNCOMMON
    target_type = TargetType.ANY_ENEMY
    tags = frozenset({"strike"})

    def _init_vars(self) -> None:
        self._energy_cost = 1
        self._base = 6
        self._extra = 3

    def _on_upgrade(self) -> None:
        self._extra += 1

    def calc_damage(self, ctx: CombatCtx, target: Creature | None = None) -> int:
        return self._base + self._extra * len(ctx.player.exhaust_pile)

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import DamageCmd
        target = ctx.resolve_target(target_idx)
        DamageCmd.deal(ctx.hooks, target, self.calc_damage(ctx, target), dealer=ctx.player, card=self)
