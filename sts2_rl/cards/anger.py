from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class AngerCard(Card):
    """Attack (Common, 0E) — deal 6 damage; add a copy of this card to the discard pile.

    Source: Anger.cs
      Cost 0 | Attack | Common | TargetType.AnyEnemy
      OnPlay: DamageCmd.Attack(6), then CreateClone() → discard pile
      OnUpgrade: damage +2 (→ 8)
    """
    id = "anger"
    name = "Anger"
    card_type = CardType.ATTACK
    rarity = CardRarity.COMMON
    target_type = TargetType.ANY_ENEMY

    def _init_vars(self) -> None:
        self._energy_cost = 0
        self._damage = 6

    def _on_upgrade(self) -> None:
        self._damage += 2

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import CardPileCmd, DamageCmd
        DamageCmd.deal(ctx.hooks, ctx.resolve_target(target_idx), self._damage, dealer=ctx.player, card=self)
        clone = AngerCard()
        for _ in range(self.upgrade_level):
            clone.upgrade()
        CardPileCmd.add_to_discard(ctx.hooks, ctx.player, clone)
