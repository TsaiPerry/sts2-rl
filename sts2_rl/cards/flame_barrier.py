from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class FlameBarrierCard(Card):
    """Skill (Uncommon, 2E) — gain 12 block; this turn, deal 4 damage back to
    any creature that attacks you.

    Source: FlameBarrier.cs
      Cost 2 | Skill | Uncommon | TargetType.Self
      OnPlay: GainBlock(12, Move), then PowerCmd.Apply<FlameBarrierPower>(4)
      OnUpgrade: block +4 (→ 16), damage back +2 (→ 6)
    """
    id = "flame_barrier"
    name = "Flame Barrier"
    card_type = CardType.SKILL
    rarity = CardRarity.UNCOMMON
    target_type = TargetType.SELF

    def _init_vars(self) -> None:
        self._energy_cost = 2
        self._block = 12
        self._damage_back = 4

    def _on_upgrade(self) -> None:
        self._block += 4
        self._damage_back += 2

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import BlockCmd, PowerCmd
        from ..powers import FlameBarrierPower
        BlockCmd.apply(ctx.hooks, ctx.player, self._block, card=self)
        PowerCmd.apply(
            ctx.hooks, ctx.player, FlameBarrierPower, self._damage_back, applier=ctx.player
        )
