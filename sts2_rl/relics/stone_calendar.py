from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic
from ..valueprops import DamageProps

if TYPE_CHECKING:
    from ..player import PlayerCombatState


@register_relic
class StoneCalendar(Relic):
    """At the end of turn 7, deal 52 damage to ALL enemies."""

    id = "stone_calendar"
    name = "Stone Calendar"
    rarity = RelicRarity.RARE

    DAMAGE_TURN = 7
    DAMAGE = 52

    def on_player_turn_end(self, player: PlayerCombatState) -> None:
        if self.turn != self.DAMAGE_TURN:
            return
        from ..cmds import DamageCmd
        for enemy in self.living_enemies():
            DamageCmd.deal(
                self.hooks, enemy, self.DAMAGE,
                dealer=player, props=DamageProps.NON_CARD_UNPOWERED,
            )
        self._check_win()
