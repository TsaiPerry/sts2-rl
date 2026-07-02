from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class PillageCard(Card):
    """Attack (Uncommon, 1E) — deal 6 damage; draw cards until you draw a non-Attack.

    Source: Pillage.cs
      Cost 1 | Attack | Uncommon | TargetType.AnyEnemy
      OnPlay: Attack(6); then do { draw } while (drawn is an Attack and hand
      not full).
      OnUpgrade: damage +3 (→ 9)
    """
    id = "pillage"
    name = "Pillage"
    card_type = CardType.ATTACK
    rarity = CardRarity.UNCOMMON
    target_type = TargetType.ANY_ENEMY

    def _init_vars(self) -> None:
        self._energy_cost = 1
        self._damage = 6

    def _on_upgrade(self) -> None:
        self._damage += 3

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import DamageCmd, DrawCmd
        DamageCmd.deal(ctx.hooks, ctx.resolve_target(target_idx), self._damage, dealer=ctx.player, card=self)
        player = ctx.player
        while True:
            before = len(player.hand)
            DrawCmd.draw(player, 1)
            if len(player.hand) == before:  # nothing drawn (empty piles / full hand)
                break
            if player.hand[-1].card_type != CardType.ATTACK:
                break
            if len(player.hand) >= player.MAX_HAND_SIZE:
                break
