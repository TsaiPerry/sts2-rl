from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class InfernoCard(Card):
    """Power (Uncommon, 1E) — at the start of your turn, lose 1 HP per Inferno
    played this combat; whenever you lose HP on your turn, deal 6 damage to
    ALL enemies.

    Source: Inferno.cs
      Cost 1 | Power | Uncommon | TargetType.Self
      OnPlay: PowerCmd.Apply<InfernoPower>(6), then IncrementSelfDamage()
      OnUpgrade: power +3 (→ 9)
    """
    id = "inferno"
    name = "Inferno"
    card_type = CardType.POWER
    rarity = CardRarity.UNCOMMON
    target_type = TargetType.SELF

    def _init_vars(self) -> None:
        self._energy_cost = 1
        self._power_amount = 6

    def _on_upgrade(self) -> None:
        self._power_amount += 3

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import PowerCmd
        from ..powers import InfernoPower
        PowerCmd.apply(
            ctx.hooks, ctx.player, InfernoPower, self._power_amount, applier=ctx.player
        )
        power = ctx.player.powers.get("inferno")
        if power is not None:
            power.increment_self_damage()
