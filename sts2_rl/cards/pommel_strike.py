from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class PommelStrikeCard(Card):
    """Attack (Common, 1E) — deal 9 damage; draw 1 card.

    Source: PommelStrike.cs
      Cost 1 | Attack | Common | TargetType.AnyEnemy | Strike tag
      OnUpgrade: damage +1 (→ 10), draw +1 (→ 2)
    """
    id = "pommel_strike"
    name = "Pommel Strike"
    card_type = CardType.ATTACK
    rarity = CardRarity.COMMON
    target_type = TargetType.ANY_ENEMY
    tags = frozenset({"strike"})

    def _init_vars(self) -> None:
        self._energy_cost = 1
        self._damage = 9
        self._cards = 1

    def _on_upgrade(self) -> None:
        self._damage += 1
        self._cards += 1

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import DamageCmd, DrawCmd
        DamageCmd.deal(ctx.hooks, ctx.resolve_target(target_idx), self._damage, dealer=ctx.player, card=self)
        DrawCmd.draw(ctx.player, self._cards)
