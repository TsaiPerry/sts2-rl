from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..player import PlayerCombatState


@register_relic
class MrStruggles(Relic):
    """MrStruggles.cs — at the start of each of your turns, deal damage equal
    to the turn number to ALL enemies (Unpowered: not boosted by Strength).
    Scales up the longer a fight drags on. One of the three dolls in the Doll
    Room event."""

    id = "mr_struggles"
    name = "Mr. Struggles"
    rarity = RelicRarity.EVENT

    def on_player_turn_started(self, player: PlayerCombatState) -> None:
        from ..cmds import DamageCmd
        from ..valueprops import DamageProps

        for enemy in self.living_enemies():
            DamageCmd.deal(
                self.hooks, enemy, self.turn,
                dealer=self.combat.player,
                props=DamageProps.NON_CARD_UNPOWERED,
            )
