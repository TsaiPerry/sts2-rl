from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class StampedeCard(Card):
    """Power (Uncommon, 2E) — when you end your turn, play a random Attack from
    your hand (for free).

    Source: Stampede.cs
      Cost 2 | Power | Uncommon | TargetType.Self
      OnPlay: PowerCmd.Apply<StampedePower>(1)
      OnUpgrade: cost -1 (→ 1)
    """
    id = "stampede"
    name = "Stampede"
    card_type = CardType.POWER
    rarity = CardRarity.UNCOMMON
    target_type = TargetType.SELF

    def _init_vars(self) -> None:
        self._energy_cost = 2

    def _on_upgrade(self) -> None:
        self._energy_cost = max(0, self._energy_cost - 1)

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import PowerCmd
        from ..powers import StampedePower
        PowerCmd.apply(ctx.hooks, ctx.player, StampedePower, 1, applier=ctx.player)
