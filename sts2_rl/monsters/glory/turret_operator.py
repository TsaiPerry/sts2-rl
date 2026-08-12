from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ...actmap import AscensionLevel
from ..base import Encounter, Intent, MoveType, asc_value
from ..state_machine import (
    ConditionalBranchState,
    MachineMonster,
    MonsterMoveStateMachine,
    MoveState,
)

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem

_FIRE_DMG = 3          # TurretOperator.cs:33 base
_FIRE_DMG_ASC = 4      # DeadlyEnemies
_FIRE_HITS = 5
_RELOAD_STR = 1
_SHIELD_SLAM_DMG = 6         # LivingShield.cs:26 -- plain const, not ascension-gated
_SMASH_DMG = 16              # LivingShield.cs:28 base
_SMASH_DMG_ASC = 18          # DeadlyEnemies (asc 9+)
_ENRAGE_STR = 3              # LivingShield.cs:30 -- plain const, not ascension-gated
_RAMPART_BLOCK = 25


class TurretOperator(MachineMonster):
    """Unloads (3×5) twice, then Reloads (+1 Strength), looping. Kept alive and
    shielded by its Living Shield escort.

    Source: TurretOperator.cs (non-ascension values)."""
    name = "Turret Operator"

    min_hp = 41
    max_hp = 41
    min_hp_asc = 51   # TurretOperator.cs:27 -- ToughEnemies (MaxInitialHp == MinInitialHp)
    max_hp_asc = 51

    def _fire_dmg(self) -> int:
        """TurretOperator.cs:33 `FireDamage` -- read at both the telegraphed
        Intent (both UNLOAD states) and the executed attack."""
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _FIRE_DMG_ASC, _FIRE_DMG)

    def build_machine(self) -> MonsterMoveStateMachine:
        unload1 = MoveState(
            "UNLOAD_MOVE", self._unload,
            lambda: Intent(MoveType.ATTACK, damage=self._fire_dmg(), hits=_FIRE_HITS),
        )
        unload2 = MoveState(
            "UNLOAD_MOVE_2", self._unload,
            lambda: Intent(MoveType.ATTACK, damage=self._fire_dmg(), hits=_FIRE_HITS),
        )
        reload = MoveState("RELOAD_MOVE", self._reload, Intent(MoveType.BUFF))
        unload1.follow_up = unload2
        unload2.follow_up = reload
        reload.follow_up = unload1
        return MonsterMoveStateMachine([unload1, unload2, reload], unload1)

    def _unload(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._fire_dmg(), _FIRE_HITS)

    def _reload(self, ctx: CombatCtx) -> None:
        from ...cmds import PowerCmd
        from ...powers import StrengthPower
        PowerCmd.apply(ctx.hooks, self, StrengthPower, _RELOAD_STR)


class LivingShield(MachineMonster):
    """Shield Slams (6) while it has allies; once alone it Smashes (16) and
    enrages (+3 Strength) each turn. Starts with Rampart 25, which shields any
    Turret Operator ally at the start of the player's turn.

    Source: LivingShield.cs (non-ascension values)."""
    name = "Living Shield"

    min_hp = 55
    max_hp = 55
    min_hp_asc = 65      # LivingShield.cs:18 ToughEnemies (asc 8+)
    max_hp_asc = 65      # LivingShield.cs:20 `MaxInitialHp => MinInitialHp`

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())
        from ...cmds import PowerCmd
        from ...powers import RampartPower
        PowerCmd.apply(hooks, self, RampartPower, _RAMPART_BLOCK)

    def _smash_dmg(self) -> int:
        """LivingShield.cs:28 `SmashDamage` -- read at both the telegraphed
        Intent (current_intent) and the executed attack (_smash)."""
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _SMASH_DMG_ASC, _SMASH_DMG)

    def _ally_count(self) -> int:
        combat = self._hooks.combat
        if combat is None:
            return 0
        return sum(
            1 for c in combat.enemies if c is not self and not c.is_gone
        )

    def build_machine(self) -> MonsterMoveStateMachine:
        shield_slam = MoveState(
            "SHIELD_SLAM_MOVE", self._shield_slam,
            Intent(MoveType.ATTACK, damage=_SHIELD_SLAM_DMG),
        )
        smash = MoveState(
            "SMASH_MOVE", self._smash,
            lambda: Intent(MoveType.ATTACK, damage=self._smash_dmg(),
                            also=(MoveType.BUFF,)),
        )
        branch = ConditionalBranchState("SHIELD_SLAM_BRANCH")
        branch.add_state(shield_slam, lambda: self._ally_count() > 0)
        branch.add_state(smash, lambda: self._ally_count() == 0)
        shield_slam.follow_up = branch
        smash.follow_up = smash
        return MonsterMoveStateMachine([shield_slam, smash, branch], shield_slam)

    def _shield_slam(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _SHIELD_SLAM_DMG, 1)

    def _smash(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._smash_dmg(), 1)
        from ...cmds import PowerCmd
        from ...powers import StrengthPower
        PowerCmd.apply(ctx.hooks, self, StrengthPower, _ENRAGE_STR)


TURRET_OPERATOR_WEAK = Encounter(
    id="turret_operator_weak",
    monster_classes=[LivingShield, TurretOperator],
)
