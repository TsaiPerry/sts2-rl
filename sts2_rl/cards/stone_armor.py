from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class StoneArmorCard(Card):
    """Power (Uncommon, 1E) — gain 4 Plating: gain 4 block at the end of your
    turn; Plating decays by 1 at the start of each turn.

    Source: StoneArmor.cs
      Cost 1 | Power | Uncommon | TargetType.Self
      OnPlay: PowerCmd.Apply<PlatingPower>(4)
      OnUpgrade: plating +2 (→ 6)
    """
    id = "stone_armor"
    name = "Stone Armor"
    card_type = CardType.POWER
    rarity = CardRarity.UNCOMMON
    target_type = TargetType.SELF

    def _init_vars(self) -> None:
        self._energy_cost = 1
        self._plating = 4

    def _on_upgrade(self) -> None:
        self._plating += 2

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import PowerCmd
        from ..powers import PlatingPower
        PowerCmd.apply(
            ctx.hooks, ctx.player, PlatingPower, self._plating, applier=ctx.player
        )
