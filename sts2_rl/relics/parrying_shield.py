from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic
from ..valueprops import DamageProps

if TYPE_CHECKING:
    from ..player import PlayerCombatState


@register_relic
class ParryingShield(Relic):
    """At the end of your turn, if you have 10 or more Block, deal 6 damage to
    a random enemy."""

    id = "parrying_shield"
    name = "Parrying Shield"
    rarity = RelicRarity.UNCOMMON

    BLOCK_THRESHOLD = 10
    DAMAGE = 6

    def on_player_turn_end(self, player: PlayerCombatState) -> None:
        if player.block < self.BLOCK_THRESHOLD:
            return
        living = self.living_enemies()
        if not living:
            return
        from ..cmds import DamageCmd
        target = self.combat._rng.choice(living)
        DamageCmd.deal(
            self.hooks, target, self.DAMAGE,
            dealer=player, props=DamageProps.NON_CARD_UNPOWERED,
        )
        self._check_win()
