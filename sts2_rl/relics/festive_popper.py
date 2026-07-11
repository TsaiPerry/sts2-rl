from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic
from ..valueprops import DamageProps

if TYPE_CHECKING:
    from ..player import PlayerCombatState

@register_relic
class FestivePopper(Relic):
    """At the start of combat, deal 9 damage to ALL enemies."""

    id = "festive_popper"
    name = "Festive Popper"
    rarity = RelicRarity.COMMON

    DAMAGE = 9

    def on_player_turn_started(self, player: PlayerCombatState) -> None:
        if self.turn == 1:
            from ..cmds import DamageCmd
            for enemy in self.living_enemies():
                DamageCmd.deal(
                    self.hooks, enemy, self.DAMAGE,
                    dealer=player, props=DamageProps.NON_CARD_UNPOWERED,
                )
            self._check_win()
