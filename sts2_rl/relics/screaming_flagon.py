from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic
from ..valueprops import DamageProps

if TYPE_CHECKING:
    from ..player import PlayerCombatState


@register_relic
class ScreamingFlagon(Relic):
    """At the end of your turn, if your hand is empty, deal 20 damage to ALL
    enemies."""

    id = "screaming_flagon"
    name = "Screaming Flagon"
    rarity = RelicRarity.SHOP

    DAMAGE = 20

    def on_player_turn_end(self, player: PlayerCombatState) -> None:
        if player.hand:
            return
        from ..cmds import DamageCmd
        for enemy in self.living_enemies():
            DamageCmd.deal(
                self.hooks, enemy, self.DAMAGE,
                dealer=player, props=DamageProps.NON_CARD_UNPOWERED,
            )
        self._check_win()
