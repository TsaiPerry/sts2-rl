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

    def after_player_turn_end(self, player: PlayerCombatState) -> None:
        # ParryingShield.cs is AfterSideTurnEnd, i.e. Hook.AfterTurnEnd — after
        # the turn-end card effects, so block Plating just added counts.
        if player.block < self.BLOCK_THRESHOLD:
            return
        # ParryingShield.cs:28 — RunState.Rng.CombatTargets.NextItem over
        # `HittableEnemies`, not "the enemies that are not gone". The shield
        # fires at every player turn end, i.e. straight after the player's own
        # attacks, which is exactly when a creature sits alive-but-unhittable
        # mid-revival; aiming at one lost the 6 damage AND drew the index over
        # a list one longer than the game's, desyncing CombatTargets for the
        # rest of the fight.
        candidates = self.hittable_enemies()
        if not candidates:
            return
        from ..cmds import DamageCmd
        target = self.combat.combat_rng.targets.choice(candidates)
        DamageCmd.deal(
            self.hooks, target, self.DAMAGE,
            dealer=player, props=DamageProps.NON_CARD_UNPOWERED,
        )
        self._check_win()
