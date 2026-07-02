from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class PrimalForceCard(Card):
    """Skill (Rare, 0E) — transform all Attacks in your hand into Giant Rocks.

    Source: PrimalForce.cs
      Cost 0 | Skill | Rare | TargetType.Self
      OnPlay: every Attack in hand is transformed into a Giant Rock
      (16 damage, 1E token attack).
      OnUpgrade: the created Giant Rocks are upgraded (20 damage).
    """
    id = "primal_force"
    name = "Primal Force"
    card_type = CardType.SKILL
    rarity = CardRarity.RARE
    target_type = TargetType.SELF

    def _init_vars(self) -> None:
        self._energy_cost = 0

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from .giant_rock import GiantRockCard
        player = ctx.player
        for idx, card in enumerate(player.hand):
            if card.card_type != CardType.ATTACK:
                continue
            rock = GiantRockCard()
            if self.upgrade_level > 0:
                rock.upgrade()
            player.hand[idx] = rock
            ctx.hooks.on_card_entered_combat(rock)
