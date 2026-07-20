from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class IronWaveCard(Card):
    """Attack (Common, 1E) — gain 5 block, then deal 5 damage.

    Source: IronWave.cs
      Cost 1 | Attack | Common | TargetType.AnyEnemy
      OnPlay: GainBlock(5) first, then Attack(5)
      OnUpgrade: damage +2 (→ 7), block +2 (→ 7)
    """
    id = "iron_wave"
    gains_block = True  # CardModel.GainsBlock
    name = "Iron Wave"
    card_type = CardType.ATTACK
    rarity = CardRarity.COMMON
    target_type = TargetType.ANY_ENEMY

    def _init_vars(self) -> None:
        self._energy_cost = 1
        self._damage = 5
        self._block = 5

    def _on_upgrade(self) -> None:
        self._damage += 2
        self._block += 2

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import BlockCmd, DamageCmd
        BlockCmd.apply(ctx.hooks, ctx.player, self._block, card=self)
        DamageCmd.deal(ctx.hooks, ctx.resolve_target(target_idx), self._damage, dealer=ctx.player, card=self)
