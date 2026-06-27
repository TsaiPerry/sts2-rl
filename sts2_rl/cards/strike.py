from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class StrikeCard(Card):
    id = "strike"
    name = "Strike"
    card_type = CardType.ATTACK
    rarity = CardRarity.BASIC
    target_type = TargetType.ANY_ENEMY

    def _init_vars(self) -> None:
        self._energy_cost = 1
        self._damage = 6

    def _on_upgrade(self) -> None:
        self._damage += 3

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import DamageCmd
        DamageCmd.deal(ctx.hooks, ctx.resolve_target(target_idx), self._damage, dealer=ctx.player, card=self)
