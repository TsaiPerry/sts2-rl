from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class HeadbuttCard(Card):
    """Attack (Common, 1E) — deal 9 damage; put a CHOSEN card from your
    discard pile on top of your draw pile.

    Source: Headbutt.cs
      Cost 1 | Attack | Common | TargetType.AnyEnemy
      OnPlay: attack 9 → CardSelectCmd.FromCombatPile(discard, 1) →
        CardPileCmd.Add(card, Draw, Top)
      OnUpgrade: damage +3 (→ 12)

    Headbutt can never pick itself: while it resolves it is in the Play pile
    (CardModel.cs:1875), not the discard. That used to need an explicit
    `c is not self` predicate here, because the sim parked a resolving card in
    the discard pile; round 13 (R5) made the Play pile real and the
    deviation is gone.
    """
    id = "headbutt"
    name = "Headbutt"
    card_type = CardType.ATTACK
    rarity = CardRarity.COMMON
    target_type = TargetType.ANY_ENEMY

    def _init_vars(self) -> None:
        self._energy_cost = 1
        self._damage = 9

    def _on_upgrade(self) -> None:
        self._damage += 3

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import CardSelectCmd, DamageCmd
        target = ctx.resolve_target(target_idx)
        DamageCmd.deal(ctx.hooks, target, self._damage, dealer=ctx.player, card=self)
        chosen = CardSelectCmd.from_pile(
            ctx.hooks, ctx.player.discard_pile, "to_draw_top",
        )
        if chosen:
            ctx.player.discard_pile.remove(chosen[0])
            ctx.player.draw_pile.append(chosen[0])  # end of list = top of pile
