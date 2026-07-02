from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class RageCard(Card):
    """Skill (Uncommon, 0E) — this turn, gain 3 block whenever you play an
    Attack.

    Source: Rage.cs
      Cost 0 | Skill | Uncommon | TargetType.Self
      OnPlay: PowerCmd.Apply<RagePower>(3)
      OnUpgrade: power +2 (→ 5)
    """
    id = "rage"
    name = "Rage"
    card_type = CardType.SKILL
    rarity = CardRarity.UNCOMMON
    target_type = TargetType.SELF

    def _init_vars(self) -> None:
        self._energy_cost = 0
        self._power_amount = 3

    def _on_upgrade(self) -> None:
        self._power_amount += 2

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import PowerCmd
        from ..powers import RagePower
        PowerCmd.apply(
            ctx.hooks, ctx.player, RagePower, self._power_amount, applier=ctx.player
        )
