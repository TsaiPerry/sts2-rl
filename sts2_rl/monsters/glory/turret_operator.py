from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ..base import Encounter, Intent, MoveType
from ..state_machine import (
    ConditionalBranchState,
    MachineMonster,
    MonsterMoveStateMachine,
    MoveState,
)

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem

_FIRE_DMG = 3
_FIRE_HITS = 5
_RELOAD_STR = 1
_SHIELD_SLAM_DMG = 6
_SMASH_DMG = 16
_ENRAGE_STR = 3
_RAMPART_BLOCK = 25


class TurretOperator(MachineMonster):
    """Unloads (3×5) twice, then Reloads (+1 Strength), looping. Kept alive and
    shielded by its Living Shield escort.

    Source: TurretOperator.cs (non-ascension values)."""
    name = "Turret Operator"

    min_hp = 41
    max_hp = 41

    def build_machine(self) -> MonsterMoveStateMachine:
        unload1 = MoveState(
            "UNLOAD_MOVE", self._unload,
            Intent(MoveType.ATTACK, damage=_FIRE_DMG, hits=_FIRE_HITS),
        )
        unload2 = MoveState(
            "UNLOAD_MOVE_2", self._unload,
            Intent(MoveType.ATTACK, damage=_FIRE_DMG, hits=_FIRE_HITS),
        )
        reload = MoveState("RELOAD_MOVE", self._reload, Intent(MoveType.BUFF))
        unload1.follow_up = unload2
        unload2.follow_up = reload
        reload.follow_up = unload1
        return MonsterMoveStateMachine([unload1, unload2, reload], unload1)

    def _unload(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _FIRE_DMG, _FIRE_HITS)

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

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())
        from ...cmds import PowerCmd
        from ...powers import RampartPower
        PowerCmd.apply(hooks, self, RampartPower, _RAMPART_BLOCK)

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
            Intent(MoveType.ATTACK, damage=_SMASH_DMG, also=(MoveType.BUFF,)),
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
        self._execute_attack(ctx, _SMASH_DMG, 1)
        from ...cmds import PowerCmd
        from ...powers import StrengthPower
        PowerCmd.apply(ctx.hooks, self, StrengthPower, _ENRAGE_STR)


TURRET_OPERATOR_WEAK = Encounter(
    id="turret_operator_weak",
    monster_classes=[LivingShield, TurretOperator],
)
