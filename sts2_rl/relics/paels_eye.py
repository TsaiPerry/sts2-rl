from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..player import PlayerCombatState


@register_relic
class PaelsEye(Relic):
    """PaelsEye.cs — once per combat, ending your turn without having played
    any cards exhausts your hand and grants an extra player turn (the enemy
    side is skipped). ShouldTakeExtraTurn + BeforeSideTurnEndEarly (hand
    exhaust) + AfterTakingExtraTurn (mark used) — the sim folds the latter two
    into the on_extra_turn notification."""

    id = "paels_eye"
    name = "Pael's Eye"
    rarity = RelicRarity.ANCIENT

    def __init__(self) -> None:
        super().__init__()
        self.used_this_combat = False

    def _any_cards_played_this_turn(self) -> bool:
        from ..history import CardPlayedEntry

        return any(
            True for _ in self.combat.history.of_type(
                CardPlayedEntry, this_turn=True,
            )
        )

    def should_take_extra_turn(self, player: PlayerCombatState) -> bool:
        return (
            not self.used_this_combat
            and not self._any_cards_played_this_turn()
        )

    def on_extra_turn(self, player: PlayerCombatState) -> None:
        from ..cmds import ExhaustCmd

        for card in list(player.hand):
            ExhaustCmd.exhaust(self.hooks, player, card)
        self.used_this_combat = True
