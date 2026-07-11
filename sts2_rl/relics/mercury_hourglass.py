from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic
from ..valueprops import DamageProps

if TYPE_CHECKING:
    from ..player import PlayerCombatState


@register_relic
class MercuryHourglass(Relic):
    """At the start of each of your turns, deal 3 damage to ALL enemies."""

    id = "mercury_hourglass"
    name = "Mercury Hourglass"
    rarity = RelicRarity.UNCOMMON

    DAMAGE = 3

    def on_player_turn_started(self, player: PlayerCombatState) -> None:
        from ..cmds import DamageCmd
        for enemy in self.living_enemies():
            DamageCmd.deal(
                self.hooks, enemy, self.DAMAGE,
                dealer=player, props=DamageProps.NON_CARD_UNPOWERED,
            )
        self._check_win()
