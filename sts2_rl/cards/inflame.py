from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class InflameCard(Card):
    """Power (Uncommon, 1E) — gain 2 Strength.

    Source: Inflame.cs
      Cost 1 | Power | Uncommon | TargetType.Self → StrengthPower 2
      OnUpgrade: Strength +1 (→ 3)
    """
    id = "inflame"
    name = "Inflame"
    card_type = CardType.POWER
    rarity = CardRarity.UNCOMMON
    target_type = TargetType.SELF

    def _init_vars(self) -> None:
        self._energy_cost = 1
        self._strength = 2

    def _on_upgrade(self) -> None:
        self._strength += 1

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import StrengthCmd
        StrengthCmd.apply(ctx.hooks, ctx.player, self._strength, card=self)
