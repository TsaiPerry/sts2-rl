from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class CrueltyCard(Card):
    """Power (Rare, 1E) — your attacks against Vulnerable enemies deal 25%
    additional damage (Vulnerable's ×1.5 becomes ×1.75).

    Source: Cruelty.cs
      Cost 1 | Power | Rare | TargetType.Self
      OnPlay: PowerCmd.Apply<CrueltyPower>(25)
      OnUpgrade: power +25 (→ 50, i.e. ×2.0 vs Vulnerable)
    """
    id = "cruelty"
    name = "Cruelty"
    card_type = CardType.POWER
    rarity = CardRarity.RARE
    target_type = TargetType.SELF

    def _init_vars(self) -> None:
        self._energy_cost = 1
        self._power_amount = 25

    def _on_upgrade(self) -> None:
        self._power_amount += 25

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import PowerCmd
        from ..powers import CrueltyPower
        PowerCmd.apply(
            ctx.hooks, ctx.player, CrueltyPower, self._power_amount, applier=ctx.player
        )
