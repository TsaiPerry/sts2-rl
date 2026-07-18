from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class RelaxCard(Card):
    """Relax.cs — 3-cost Ancient Skill (Exhaust): gain 15 Block, draw 2 extra
    cards and gain 2 extra Energy next turn (upgrade: 17 / 3 / 3). Granted by
    Pael's Horn."""

    id = "relax"
    name = "Relax"
    card_type = CardType.SKILL
    rarity = CardRarity.ANCIENT
    target_type = TargetType.SELF
    exhausts = True

    def _init_vars(self) -> None:
        self._energy_cost = 3
        self._block = 15
        self._cards = 2
        self._energy = 2

    def _on_upgrade(self) -> None:
        self._block += 2
        self._cards += 1
        self._energy += 1

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import BlockCmd, PowerCmd
        from ..powers import DrawCardsNextTurnPower, EnergyNextTurnPower

        BlockCmd.apply(ctx.hooks, ctx.player, self._block, card=self)
        PowerCmd.apply(
            ctx.hooks, ctx.player, DrawCardsNextTurnPower, self._cards,
            applier=ctx.player,
        )
        PowerCmd.apply(
            ctx.hooks, ctx.player, EnergyNextTurnPower, self._energy,
            applier=ctx.player,
        )
