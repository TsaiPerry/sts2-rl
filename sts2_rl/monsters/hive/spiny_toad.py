"""Spiny Toad (Hive). Sources: SpinyToad.cs, SpinyToadNormal.cs."""
from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ..base import Encounter, Intent, MoveType
from ..state_machine import MachineMonster, MonsterMoveStateMachine, MoveState

if TYPE_CHECKING:
    from ...combat import CombatCtx

_LASH_DMG = 17
_EXPLOSION_DMG = 23
_THORNS = 5


class SpinyToad(MachineMonster):
    """Cycle: PROTRUDING_SPIKES (+5 Thorns) → SPIKE_EXPLOSION (23, spends the
    Thorns) → TONGUE_LASH (17)."""

    name = "Spiny Toad"  # localization/eng/monsters.json SPINY_TOAD.name
    min_hp = 116
    max_hp = 119

    def build_machine(self) -> MonsterMoveStateMachine:
        spikes = MoveState(
            "PROTRUDING_SPIKES_MOVE", self._spikes, Intent(MoveType.BUFF)
        )
        explosion = MoveState(
            "SPIKE_EXPLOSION_MOVE", self._explosion,
            Intent(MoveType.ATTACK, damage=_EXPLOSION_DMG),
        )
        lash = MoveState(
            "TONGUE_LASH_MOVE", self._lash, Intent(MoveType.ATTACK, damage=_LASH_DMG)
        )
        spikes.follow_up = explosion
        explosion.follow_up = lash
        lash.follow_up = spikes
        return MonsterMoveStateMachine([spikes, explosion, lash], spikes)

    def _spikes(self, ctx: CombatCtx) -> None:
        from ...cmds import PowerCmd
        from ...powers import ThornsPower
        PowerCmd.apply(ctx.hooks, self, ThornsPower, _THORNS)

    def _explosion(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _EXPLOSION_DMG, 1)
        from ...cmds import PowerCmd
        from ...powers import ThornsPower
        PowerCmd.apply(ctx.hooks, self, ThornsPower, -_THORNS)

    def _lash(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _LASH_DMG, 1)


SPINY_TOAD_NORMAL = Encounter(
    id="spiny_toad_normal",
    monster_classes=[SpinyToad],
)
