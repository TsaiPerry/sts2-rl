from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class FeelNoPainCard(Card):
    """Power (Uncommon, 1E) — whenever a card is exhausted, gain 3 block.

    Source: FeelNoPain.cs
      Cost 1 | Power | Uncommon | TargetType.Self → FeelNoPainPower 3
      OnUpgrade: block per exhaust +1 (→ 4)
    """
    id = "feel_no_pain"
    name = "Feel No Pain"
    card_type = CardType.POWER
    rarity = CardRarity.UNCOMMON
    target_type = TargetType.SELF

    def _init_vars(self) -> None:
        self._energy_cost = 1
        # DynamicVar("Power", 3m), FeelNoPain.cs:16 -- grants no block itself;
        # belongs in `_power_amount` (shared slot with Rage/Corruption/
        # Stampede's own "Power" var), not `_block` (would misreport as
        # block-granting per cards/base.py's GainsBlock docstring).
        self._power_amount = 3

    def _on_upgrade(self) -> None:
        self._power_amount += 1

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import PowerCmd
        from ..powers import FeelNoPainPower
        PowerCmd.apply(
            ctx.hooks, ctx.player, FeelNoPainPower, self._power_amount,
            applier=ctx.player,
        )
