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

    def on_card_played(self, card: "Card") -> None:
        self.cards_played_this_turn += 1

    def on_player_turn_end(self, player: PlayerCombatState) -> None:
        from ..cmds import PowerCmd
        from ..powers import DiamondDiademPower

        if self.cards_played_this_turn <= self.CARD_THRESHOLD:
            PowerCmd.apply(
                self.hooks, player, DiamondDiademPower, 1, applier=player,
            )
        self.cards_played_this_turn = 0
