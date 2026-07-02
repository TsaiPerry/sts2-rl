from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx
    from ..creatures import Creature


@register_card
class PerfectedStrikeCard(Card):
    """Attack (Common, 2E) — deal 6 + 2 damage per card with "Strike" you own.

    Source: PerfectedStrike.cs
      Cost 2 | Attack | Common | TargetType.AnyEnemy | Strike tag
      CalculationBase 6, ExtraDamage 2, multiplier = count of Strike-tagged
      cards across all piles (AllCards) — includes this card itself.
      OnUpgrade: extra damage +1 (→ 6 + 3×count)
    """
    id = "perfected_strike"
    name = "Perfected Strike"
    card_type = CardType.ATTACK
    rarity = CardRarity.COMMON
    target_type = TargetType.ANY_ENEMY
    tags = frozenset({"strike"})

    def _init_vars(self) -> None:
        self._energy_cost = 2
        self._base = 6
        self._extra = 2

    def _on_upgrade(self) -> None:
        self._extra += 1

    def calc_damage(self, ctx: CombatCtx, target: Creature | None = None) -> int:
        strikes = sum(1 for c in ctx.player.all_cards if "strike" in c.tags)
        return self._base + self._extra * strikes

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import DamageCmd
        target = ctx.resolve_target(target_idx)
        DamageCmd.deal(ctx.hooks, target, self.calc_damage(ctx, target), dealer=ctx.player, card=self)
