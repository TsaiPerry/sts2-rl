from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class InfernalBladeCard(Card):
    """Skill (Uncommon, 1E) — add a random Attack to your hand; it costs 0
    this turn. Exhaust.

    Source: InfernalBlade.cs
      Cost 1 | Skill | Uncommon | TargetType.Self | Exhaust keyword
      OnPlay: CardFactory.GetDistinctForCombat(pool attacks, 1) →
        SetToFreeThisTurn → AddGeneratedCardToCombat(Hand)
      OnUpgrade: cost -1 (→ 0)
    """
    id = "infernal_blade"
    name = "Infernal Blade"
    card_type = CardType.SKILL
    rarity = CardRarity.UNCOMMON
    target_type = TargetType.SELF
    exhausts = True

    def _init_vars(self) -> None:
        self._energy_cost = 1

    def _on_upgrade(self) -> None:
        self._energy_cost -= 1

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import CardPileCmd
        from .pool import get_distinct_for_combat_parity, random_pool_cards
        crng = ctx.combat.combat_rng
        if crng.is_parity:
            # GetDistinctForCombat draws on Rng.CombatCardGeneration.
            cards = get_distinct_for_combat_parity(
                crng.card_gen, 1, CardType.ATTACK, pool=ctx.combat.card_pool
            )
        else:
            cards = random_pool_cards(
                ctx.combat._rng, 1, card_type=CardType.ATTACK, distinct=True,
                pool=ctx.combat.card_pool,
            )
        if cards:
            cards[0].set_free_this_turn()
            CardPileCmd.add_to_hand(ctx.hooks, ctx.player, cards[0])
