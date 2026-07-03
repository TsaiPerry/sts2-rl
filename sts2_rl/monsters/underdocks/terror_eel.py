from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ..base import Encounter, Intent, MoveType
from ..state_machine import MachineMonster, MonsterMoveStateMachine, MoveState

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem

_CRASH_DMG = 16
_THRASH_DMG = 3
_THRASH_HITS = 3
_THRASH_VIGOR = 6
_SHRIEK_HP = 70
_TERROR_VULN = 99


class TerrorEel(MachineMonster):
    """Elite. Alternates CRASH (16) and THRASH (3×3, then +6 Vigor for the
    next CRASH). Shriek 70: the first unblocked hit that leaves it at or
    below 70 HP stuns it for a turn, after which it screams TERROR
    (Vulnerable 99) and resumes at CRASH."""

    min_hp = 140
    max_hp = 140

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())
        from ...cmds import PowerCmd
        from ...powers import ShriekPower
        PowerCmd.apply(hooks, self, ShriekPower, _SHRIEK_HP)

    def build_machine(self) -> MonsterMoveStateMachine:
        crash = MoveState(
            "CRASH_MOVE", self._crash, Intent(MoveType.ATTACK, damage=_CRASH_DMG)
        )
        thrash = MoveState(
            "THRASH_MOVE", self._thrash,
            Intent(MoveType.ATTACK, damage=_THRASH_DMG, hits=_THRASH_HITS,
                   also=(MoveType.BUFF,)),
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
        terror = self.machine.states["TERROR_MOVE"]
        self.machine.force_current_state(terror)
        self._current_move = terror
        from ...cmds import CreatureCmd
        CreatureCmd.stun(self._hooks, self)

    def _crash(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _CRASH_DMG, 1)

    def _thrash(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _THRASH_DMG, _THRASH_HITS)
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
