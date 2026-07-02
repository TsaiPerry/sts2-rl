from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class CrimsonMantleCard(Card):
    """Power (Rare, 1E) — at the start of your turn, lose 1 HP per Crimson
    Mantle played this combat, then gain 8 block.

    Source: CrimsonMantle.cs
      Cost 1 | Power | Rare | TargetType.Self
      OnPlay: PowerCmd.Apply<CrimsonMantlePower>(8), then IncrementSelfDamage()
      OnUpgrade: power +2 (→ 10)
    """
    id = "crimson_mantle"
    name = "Crimson Mantle"
    card_type = CardType.POWER
    rarity = CardRarity.RARE
    target_type = TargetType.SELF

    def _init_vars(self) -> None:
        self._energy_cost = 1
        self._power_amount = 8

    def _on_upgrade(self) -> None:
        self._power_amount += 2

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import PowerCmd
        from ..powers import CrimsonMantlePower
        PowerCmd.apply(
            ctx.hooks, ctx.player, CrimsonMantlePower, self._power_amount, applier=ctx.player
        )
        power = ctx.player.powers.get("crimson_mantle")
        if power is not None:
            power.increment_self_damage()
