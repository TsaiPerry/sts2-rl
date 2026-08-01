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
        # DynamicVar("Power", 3m), FeelNoPain.cs:16 -- the card itself grants
        # NO block (that would be `_block`, which `Card.base_block` reads);
        # this is the amount handed to FeelNoPainPower, so it belongs in the
        # same `_power_amount` slot Rage/Corruption/Stampede use for their
        # own generic "Power" var (all four are literally `DynamicVar("Power",
        # ...)` in the C# source). Storing it as `_block` used to make
        # `Card.base_block` misreport this as a block-granting card -- exactly
        # what cards/base.py's GainsBlock docstring warns about.
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
