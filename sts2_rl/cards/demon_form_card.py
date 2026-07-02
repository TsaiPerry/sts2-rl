from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class DemonFormCard(Card):
    """Power (Rare, 3E) — at the start of your turn, gain 2 Strength.

    Source: DemonForm.cs
      Cost 3 | Power | Rare | TargetType.Self → DemonFormPower 2
      OnUpgrade: Strength per turn +1 (→ 3)
    """
    id = "demon_form"
    name = "Demon Form"
    card_type = CardType.POWER
    rarity = CardRarity.RARE
    target_type = TargetType.SELF

    def _init_vars(self) -> None:
        self._energy_cost = 3
        self._strength = 2

    def _on_upgrade(self) -> None:
        self._strength += 1

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import PowerCmd
        from ..powers import DemonFormPower
        PowerCmd.apply(ctx.hooks, ctx.player, DemonFormPower, self._strength, applier=ctx.player)
