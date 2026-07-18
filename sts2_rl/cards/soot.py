from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class SootCard(Card):
    """Soot.cs — Unplayable Status. Biiig Hug shuffles one into the draw pile
    after every reshuffle."""

    id = "soot"
    name = "Soot"
    card_type = CardType.STATUS
    rarity = CardRarity.STATUS
    target_type = TargetType.NONE
    is_playable = False
    max_upgrade_level = 0
    is_unpowered = True
    can_be_generated_in_combat = False

    def _init_vars(self) -> None:
        self._energy_cost = 0

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        pass
