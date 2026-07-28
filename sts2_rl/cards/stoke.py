from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class StokeCard(Card):
    """Skill (Rare, 1E) — exhaust your hand; add that many random cards from
    the Ironclad pool to your hand (upgraded: they enter upgraded).

    Source: Stoke.cs
      Cost 1 | Skill | Rare | TargetType.Self
      OnPlay: exhaust every card in hand (per-card, so on-exhaust triggers
        fire for each), then CardFactory.GetForCombat(pool, count) — repeats
        allowed — into the hand; upgraded: CardCmd.Upgrade on the generated
        cards first
      OnUpgrade: generated cards are upgraded (no value change)
    """
    id = "stoke"
    name = "Stoke"
    card_type = CardType.SKILL
    rarity = CardRarity.RARE
    target_type = TargetType.SELF

    def _init_vars(self) -> None:
        self._energy_cost = 1

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import CardPileCmd, ExhaustCmd
        from .pool import get_for_combat_parity, random_pool_cards
        hand = list(ctx.player.hand)
        for card in hand:
            ExhaustCmd.exhaust(ctx.hooks, ctx.player, card)
        # GetForCombat(pool, exhaustCount) — parity draws one CombatCardGeneration
        # NextItem per generated card; legacy keeps the shared-Random path.
        crng = ctx.combat.combat_rng
        if crng.is_parity:
            new_cards = get_for_combat_parity(
                crng.card_gen, len(hand), pool=ctx.combat.card_pool
            )
        else:
            new_cards = random_pool_cards(
                ctx.combat._rng, len(hand), pool=ctx.combat.card_pool
            )
        for card in new_cards:
            if self.upgrade_level > 0:
                card.upgrade()
            CardPileCmd.add_to_hand(ctx.hooks, ctx.player, card)
