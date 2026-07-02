from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class PyreCard(Card):
    """Power (Rare, 2E) — gain 1 extra energy at the start of each turn.

    Source: Pyre.cs
      Cost 2 | Power | Rare | TargetType.Self
      OnPlay: PowerCmd.Apply<PyrePower>(1)
      OnUpgrade: energy +1 (→ 2)
    """
    id = "pyre"
    name = "Pyre"
    card_type = CardType.POWER
    rarity = CardRarity.RARE
    target_type = TargetType.SELF

    def _init_vars(self) -> None:
        self._energy_cost = 2
        self._energy_gain = 1

    def _on_upgrade(self) -> None:
        self._energy_gain += 1

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import PowerCmd
        from ..powers import PyrePower
        PowerCmd.apply(
            ctx.hooks, ctx.player, PyrePower, self._energy_gain, applier=ctx.player
        )
