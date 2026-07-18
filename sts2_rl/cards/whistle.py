from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class WhistleCard(Card):
    """Whistle.cs — 3-cost Ancient Attack (Exhaust): deal 33 damage and STUN
    the target (upgrade: 44). Granted by Tanx's Whistle."""

    id = "whistle"
    name = "Whistle"
    card_type = CardType.ATTACK
    rarity = CardRarity.ANCIENT
    target_type = TargetType.ANY_ENEMY
    exhausts = True

    def _init_vars(self) -> None:
        self._energy_cost = 3
        self._damage = 33

    def _on_upgrade(self) -> None:
        self._damage += 11

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import CreatureCmd, DamageCmd

        target = ctx.resolve_target(target_idx)
        DamageCmd.deal(
            ctx.hooks, target, self._damage, dealer=ctx.player, card=self,
        )
        if not target.is_gone:
            CreatureCmd.stun(ctx.hooks, target)
