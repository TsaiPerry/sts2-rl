from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class CorruptionCard(Card):
    """Power (Ancient, 3E) — Skills cost 0; when you play a Skill, exhaust it.

    Source: Corruption.cs
      Cost 3 | Power | Ancient | TargetType.Self
      OnPlay: PowerCmd.Apply<CorruptionPower>(1)
      OnUpgrade: cost -1 (→ 2)
    """
    id = "corruption"
    name = "Corruption"
    card_type = CardType.POWER
    rarity = CardRarity.ANCIENT
    target_type = TargetType.SELF

    def _init_vars(self) -> None:
        self._energy_cost = 3
        self._power_amount = 1  # DynamicVar("Power", 1m), Corruption.cs:17

    def _on_upgrade(self) -> None:
        self._energy_cost = max(0, self._energy_cost - 1)

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import PowerCmd
        from ..powers import CorruptionPower
        PowerCmd.apply(
            ctx.hooks, ctx.player, CorruptionPower, self._power_amount,
            applier=ctx.player,
        )
