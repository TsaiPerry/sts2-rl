from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class OneTwoPunchCard(Card):
    """Skill (Rare, 1E) — the next Attack you play this turn is played twice.

    Source: OneTwoPunch.cs
      Cost 1 | Skill | Rare | TargetType.Self
      OnPlay: PowerCmd.Apply<OneTwoPunchPower>(1)
      OnUpgrade: attacks +1 (→ 2)
    """
    id = "one_two_punch"
    name = "One-Two Punch"
    card_type = CardType.SKILL
    rarity = CardRarity.RARE
    target_type = TargetType.SELF

    def _init_vars(self) -> None:
        self._energy_cost = 1
        self._attacks = 1

    def _on_upgrade(self) -> None:
        self._attacks += 1

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import PowerCmd
        from ..powers import OneTwoPunchPower
        PowerCmd.apply(
            ctx.hooks, ctx.player, OneTwoPunchPower, self._attacks, applier=ctx.player
        )
