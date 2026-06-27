from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class SweepCard(Card):
    """Hits every living enemy for 4 damage.

    play_card routes ALL_ENEMIES cards by calling on_play once per living
    enemy, passing that enemy's index as target_idx each time.
    """
    id = "sweep"
    name = "Sweep"
    card_type = CardType.ATTACK
    rarity = CardRarity.BASIC
    target_type = TargetType.ALL_ENEMIES

    def _init_vars(self) -> None:
        self._energy_cost = 1
        self._damage = 4

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import DamageCmd
        DamageCmd.deal(ctx.hooks, ctx.resolve_target(target_idx), self._damage, dealer=ctx.player, card=self)
