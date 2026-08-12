"""Spiny Toad (Hive). Sources: SpinyToad.cs, SpinyToadNormal.cs."""
from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ...actmap import AscensionLevel
from ..base import Encounter, Intent, MoveType, asc_value
from ..state_machine import MachineMonster, MonsterMoveStateMachine, MoveState

if TYPE_CHECKING:
    from ...combat import CombatCtx

_LASH_DMG = 17          # SpinyToad.cs:33 base
_LASH_DMG_ASC = 19      # SpinyToad.cs:33 DeadlyEnemies
_EXPLOSION_DMG = 23     # SpinyToad.cs:35 base
_EXPLOSION_DMG_ASC = 25  # SpinyToad.cs:35 DeadlyEnemies
_THORNS = 5


class SpinyToad(MachineMonster):
    """Cycle: PROTRUDING_SPIKES (+5 Thorns) → SPIKE_EXPLOSION (23, spends the
    Thorns) → TONGUE_LASH (17)."""

    name = "Spiny Toad"  # localization/eng/monsters.json SPINY_TOAD.name
    min_hp = 116
    max_hp = 119
    min_hp_asc = 121  # SpinyToad.cs:29 ToughEnemies
    max_hp_asc = 124  # SpinyToad.cs:31 ToughEnemies

    def _lash_dmg(self) -> int:
        """SpinyToad.cs:33 `LashDamage` -- a C# PROPERTY re-read at both the
        telegraphed Intent (:61) and the executed attack (:98)."""
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _LASH_DMG_ASC, _LASH_DMG)

    def _explosion_dmg(self) -> int:
        """SpinyToad.cs:35 `ExplosionDamage` -- a C# PROPERTY re-read at both
        the telegraphed Intent (:60) and the executed attack (:88)."""
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _EXPLOSION_DMG_ASC, _EXPLOSION_DMG)

    def build_machine(self) -> MonsterMoveStateMachine:
        spikes = MoveState(
            "PROTRUDING_SPIKES_MOVE", self._spikes, Intent(MoveType.BUFF)
        )
        explosion = MoveState(
            "SPIKE_EXPLOSION_MOVE", self._explosion,
            lambda: Intent(MoveType.ATTACK, damage=self._explosion_dmg()),
        )
        lash = MoveState(
            "TONGUE_LASH_MOVE", self._lash,
            lambda: Intent(MoveType.ATTACK, damage=self._lash_dmg()),
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
        self._execute_attack(ctx, self._explosion_dmg(), 1)
        from ...cmds import PowerCmd
        from ...powers import ThornsPower
        PowerCmd.apply(ctx.hooks, self, ThornsPower, -_THORNS)

    def _lash(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._lash_dmg(), 1)


SPINY_TOAD_NORMAL = Encounter(
    id="spiny_toad_normal",
    monster_classes=[SpinyToad],
)
