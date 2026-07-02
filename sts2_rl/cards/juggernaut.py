from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class JuggernautCard(Card):
    """Power (Rare, 2E) — whenever you gain block, deal 6 damage to a random
    enemy.

    Source: Juggernaut.cs
      Cost 2 | Power | Rare | TargetType.Self
      OnPlay: PowerCmd.Apply<JuggernautPower>(6)
      OnUpgrade: power +2 (→ 8)
    """
    id = "juggernaut"
    name = "Juggernaut"
    card_type = CardType.POWER
    rarity = CardRarity.RARE
    target_type = TargetType.SELF

    def _init_vars(self) -> None:
        self._energy_cost = 2
        self._power_amount = 6

    def _on_upgrade(self) -> None:
        self._power_amount += 2

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import PowerCmd
        from ..powers import JuggernautPower
        PowerCmd.apply(
            ctx.hooks, ctx.player, JuggernautPower, self._power_amount, applier=ctx.player
        )
