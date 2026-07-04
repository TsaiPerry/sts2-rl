"""Kaiser Crab (Hive boss) — the Crusher and Rocket arms. Sources:
Crusher.cs, Rocket.cs, KaiserCrabBoss.cs."""
from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ..base import Encounter, Intent, MoveType
from ..state_machine import MachineMonster, MonsterMoveStateMachine, MoveState

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem

# Crusher (left arm)
_THRASH_DMG = 12
_ENLARGING_DMG = 4
_BUG_STING_DMG = 6
_BUG_STING_HITS = 2
_BUG_STING_WEAK = 2
_BUG_STING_FRAIL = 2
_ADAPT_STR = 2
_GUARDED_DMG = 12
_GUARDED_BLOCK = 18

# Rocket (right arm)
_RETICLE_DMG = 3
_PRECISION_DMG = 18
_CHARGE_STR = 2
_LASER_DMG = 31


class Crusher(MachineMonster):
    """The Kaiser Crab's left arm. Fixed cycle: THRASH (12) → ENLARGING_STRIKE
    (4) → BUG_STING (6x2 + Weak 2 + Frail 2) → ADAPT (+2 Strength) →
    GUARDED_STRIKE (12 + 18 block). Back-attacks for 50% more while you face
    the Rocket; rages (+6 Strength, 99 block) if the Rocket dies first."""

    min_hp = 209
    max_hp = 209

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())
        from ...cmds import PowerCmd
        from ...powers import BackAttackLeftPower, CrabRagePower
        PowerCmd.apply(hooks, self, BackAttackLeftPower, 1)
        PowerCmd.apply(hooks, self, CrabRagePower, 1)

    def build_machine(self) -> MonsterMoveStateMachine:
        thrash = MoveState(
            "THRASH_MOVE", self._thrash, Intent(MoveType.ATTACK, damage=_THRASH_DMG)
        )
        enlarging = MoveState(
            "ENLARGING_STRIKE_MOVE", self._enlarging,
            Intent(MoveType.ATTACK, damage=_ENLARGING_DMG),
        )
        bug_sting = MoveState(
            "BUG_STING_MOVE", self._bug_sting,
            Intent(MoveType.ATTACK, damage=_BUG_STING_DMG, hits=_BUG_STING_HITS,
                   also=(MoveType.DEBUFF,)),
        )
        adapt = MoveState("ADAPT_MOVE", self._adapt, Intent(MoveType.BUFF))
        guarded = MoveState(
            "GUARDED_STRIKE_MOVE", self._guarded,
            Intent(MoveType.ATTACK, damage=_GUARDED_DMG, also=(MoveType.DEFEND,)),
        )
        thrash.follow_up = enlarging
        enlarging.follow_up = bug_sting
        bug_sting.follow_up = adapt
        adapt.follow_up = guarded
        guarded.follow_up = thrash
        return MonsterMoveStateMachine(
            [thrash, enlarging, bug_sting, adapt, guarded], thrash
        )

    def _thrash(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _THRASH_DMG, 1)

    def _enlarging(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _ENLARGING_DMG, 1)

    def _bug_sting(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _BUG_STING_DMG, _BUG_STING_HITS)
        from ...cmds import PowerCmd
        from ...powers import FrailPower, WeakPower
        PowerCmd.apply(ctx.hooks, ctx.player, WeakPower, _BUG_STING_WEAK, applier=self)
        PowerCmd.apply(ctx.hooks, ctx.player, FrailPower, _BUG_STING_FRAIL, applier=self)

    def _adapt(self, ctx: CombatCtx) -> None:
        from ...cmds import PowerCmd
        from ...powers import StrengthPower
        PowerCmd.apply(ctx.hooks, self, StrengthPower, _ADAPT_STR)

    def _guarded(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _GUARDED_DMG, 1)
        from ...cmds import BlockCmd
        BlockCmd.apply(ctx.hooks, self, _GUARDED_BLOCK)


class Rocket(MachineMonster):
    """The Kaiser Crab's right arm. Applies Surrounded to the player at spawn.
    Fixed cycle: TARGETING_RETICLE (3) → PRECISION_BEAM (18) → CHARGE_UP (+2
    Strength) → LASER (31) → RECHARGE (nothing)."""

    min_hp = 199
    max_hp = 199

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())
        from ...cmds import PowerCmd
        from ...powers import BackAttackRightPower, CrabRagePower, SurroundedPower
        combat = hooks.combat
        if combat is not None:
            PowerCmd.apply(hooks, combat.player, SurroundedPower, 1, applier=self)
        PowerCmd.apply(hooks, self, BackAttackRightPower, 1)
        PowerCmd.apply(hooks, self, CrabRagePower, 1)

    def build_machine(self) -> MonsterMoveStateMachine:
        reticle = MoveState(
            "TARGETING_RETICLE_MOVE", self._reticle,
            Intent(MoveType.ATTACK, damage=_RETICLE_DMG),
        )
        precision = MoveState(
            "PRECISION_BEAM_MOVE", self._precision,
            Intent(MoveType.ATTACK, damage=_PRECISION_DMG),
        )
        charge = MoveState("CHARGE_UP_MOVE", self._charge, Intent(MoveType.BUFF))
        laser = MoveState(
            "LASER_MOVE", self._laser, Intent(MoveType.ATTACK, damage=_LASER_DMG)
        )
        recharge = MoveState("RECHARGE_MOVE", self._recharge, Intent(MoveType.SLEEP))
        reticle.follow_up = precision
        precision.follow_up = charge
        charge.follow_up = laser
        laser.follow_up = recharge
        recharge.follow_up = reticle
        return MonsterMoveStateMachine(
            [reticle, precision, charge, laser, recharge], reticle
        )

    def _reticle(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _RETICLE_DMG, 1)

    def _precision(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _PRECISION_DMG, 1)

    def _charge(self, ctx: CombatCtx) -> None:
        from ...cmds import PowerCmd
        from ...powers import StrengthPower
        PowerCmd.apply(ctx.hooks, self, StrengthPower, _CHARGE_STR)

    def _laser(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _LASER_DMG, 1)

    def _recharge(self, ctx: CombatCtx) -> None:
        pass


KAISER_CRAB_BOSS = Encounter(
    id="kaiser_crab_boss",
    monster_classes=[Crusher, Rocket],
)
