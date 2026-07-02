from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class ViciousCard(Card):
    """Power (Uncommon, 1E) — whenever you apply Vulnerable, draw 1 card.

    Source: Vicious.cs
      Cost 1 | Power | Uncommon | TargetType.Self
      OnPlay: PowerCmd.Apply<ViciousPower>(1)
      OnUpgrade: cards +1 (→ 2)
    """
    id = "vicious"
    name = "Vicious"
    card_type = CardType.POWER
    rarity = CardRarity.UNCOMMON
    target_type = TargetType.SELF

    def _init_vars(self) -> None:
        self._energy_cost = 1
        self._cards = 1

    def _on_upgrade(self) -> None:
        self._cards += 1

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import PowerCmd
        from ..powers import ViciousPower
        PowerCmd.apply(
            ctx.hooks, ctx.player, ViciousPower, self._cards, applier=ctx.player
        )
