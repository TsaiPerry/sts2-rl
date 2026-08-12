from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ...actmap import AscensionLevel
from ..base import Encounter, Intent, MoveType, asc_value
from ..state_machine import MachineMonster, MonsterMoveStateMachine, MoveState

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem

_CRASH_DMG = 16          # TerrorEel.cs:41 base
_CRASH_DMG_ASC = 18      # DeadlyEnemies (asc 9+)
_THRASH_DMG = 3          # TerrorEel.cs:43 base
_THRASH_DMG_ASC = 4      # DeadlyEnemies (asc 9+)
_THRASH_HITS = 3
_THRASH_VIGOR = 6
_SHRIEK_HP = 70          # TerrorEel.cs:39 base (ToughEnemies)
_SHRIEK_HP_ASC = 75
_TERROR_VULN = 99


class TerrorEel(MachineMonster):
    """Elite. Alternates CRASH (16) and THRASH (3×3, then +6 Vigor for the
    next CRASH). Shriek 70: the first unblocked hit that leaves it at or
    below 70 HP stuns it for a turn, after which it screams TERROR
    (Vulnerable 99) and resumes at CRASH."""
    name = "Terror Eel"

    min_hp = 140          # TerrorEel.cs:35 base
    max_hp = 140
    min_hp_asc = 150      # TerrorEel.cs:35 ToughEnemies (MaxInitialHp => MinInitialHp)
    max_hp_asc = 150

    def _shriek_amount(self) -> int:
        """TerrorEel.cs:39 `ShriekAmount` -- ToughEnemies gate."""
        return asc_value(self._hooks, AscensionLevel.TOUGH_ENEMIES,
                          _SHRIEK_HP_ASC, _SHRIEK_HP)

    def _crash_dmg(self) -> int:
        """TerrorEel.cs:41 `CrashDamage` -- a C# PROPERTY re-read at both the
        telegraphed Intent (:71) and the executed attack (:88), so both
        sites call this rather than a value cached at construction."""
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _CRASH_DMG_ASC, _CRASH_DMG)

    def _thrash_dmg(self) -> int:
        """TerrorEel.cs:43 `ThrashDamage` -- re-read at both the telegraphed
        Intent (:72) and the executed attack (:96)."""
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _THRASH_DMG_ASC, _THRASH_DMG)

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())
        from ...cmds import PowerCmd
        from ...powers import ShriekPower
        PowerCmd.apply(hooks, self, ShriekPower, self._shriek_amount())

    def build_machine(self) -> MonsterMoveStateMachine:
        crash = MoveState(
            "CRASH_MOVE", self._crash,
            lambda: Intent(MoveType.ATTACK, damage=self._crash_dmg()),
        )
        thrash = MoveState(
            "THRASH_MOVE", self._thrash,
            lambda: Intent(MoveType.ATTACK, damage=self._thrash_dmg(),
                            hits=_THRASH_HITS, also=(MoveType.BUFF,)),
        )
        # must_perform_once pins the machine on TERROR even if the trigger
        # lands mid-turn (thorns during the eel's own attack) and the
        # end-of-turn roll runs afterwards.
        terror = MoveState(
            "TERROR_MOVE", self._terror, Intent(MoveType.DEBUFF),
            must_perform_once_before_transitioning=True,
        )
        crash.follow_up = thrash
        thrash.follow_up = crash
        terror.follow_up = crash
        return MonsterMoveStateMachine([crash, thrash, terror], crash)

    def trigger_terror(self) -> None:
        """Called by ShriekPower: the eel loses its next turn and screams
        TERROR after (mirrors CreatureCmd.Stun(owner, TerrorState.StateId))."""
        # ShriekPower.cs:30 — CreatureCmd.Stun(Owner, TerrorState.StateId):
        # the id is the stun's FollowUpStateId, so TERROR is the move performed
        # on the turn AFTER the stunned one.
        from ...cmds import CreatureCmd
        CreatureCmd.stun(self._hooks, self, next_move_key="TERROR_MOVE")

    def _crash(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._crash_dmg(), 1)

    def _thrash(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._thrash_dmg(), _THRASH_HITS)
        from ...cmds import PowerCmd
        from ...powers import VigorPower
        PowerCmd.apply(ctx.hooks, self, VigorPower, _THRASH_VIGOR)

    def _terror(self, ctx: CombatCtx) -> None:
        from ...cmds import PowerCmd
        from ...powers import VulnerablePower
        PowerCmd.apply(ctx.hooks, ctx.player, VulnerablePower, _TERROR_VULN)


TERROR_EEL_ELITE = Encounter(
    id="terror_eel_elite",
    monster_classes=[TerrorEel],
)
