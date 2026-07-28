from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..cards import Card
    from ..player import PlayerCombatState


@register_relic
class DiamondDiadem(Relic):
    """DiamondDiadem.cs — at the end of your turn, if you played at most 2
    cards ("CardThreshold" = 2), gain the Diamond Diadem power (attack damage
    against you is halved until the enemy turn ends)."""

    id = "diamond_diadem"
    name = "Diamond Diadem"
    rarity = RelicRarity.ANCIENT

    CARD_THRESHOLD = 2

    def __init__(self) -> None:
        super().__init__()
        self.cards_played_this_turn = 0

    def reset_for_combat(self) -> None:
        # DiamondDiadem.AfterCombatEnd (:78-84). The turn-end reset below is
        # not enough: a combat that ends inside play_card never reaches
        # on_player_turn_end, so the counter carried into the next fight and
        # turn 1 granted no power (3 > 2) where the game grants it.
        self.cards_played_this_turn = 0

    def on_card_played(self, card: "Card",
                       is_auto_play: bool = False) -> None:
        self.cards_played_this_turn += 1

    def on_player_turn_end(self, player: PlayerCombatState) -> None:
        from ..cmds import PowerCmd
        from ..powers import DiamondDiademPower

        if self.cards_played_this_turn <= self.CARD_THRESHOLD:
            PowerCmd.apply(
                self.hooks, player, DiamondDiademPower, 1, applier=player,
            )
        self.cards_played_this_turn = 0
