"""Slumbering Beetle (Hive). Sources: SlumberingBeetle.cs,
SlumberingBeetleNormal.cs."""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ..base import Encounter, Intent, Monster, MoveType
from ..state_machine import (
    ConditionalBranchState,
    MachineMonster,
    MonsterMoveStateMachine,
    MoveState,
)

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...creatures import Creature
    from ...hooks import HookSystem

_ROLLOUT_DMG = 16
_ROLLOUT_STR = 2
_PLATING = 15
_SLUMBER = 3


class SlumberingBeetle(MachineMonster):
    """Sleeps behind Plating 15 for 3 turns (Slumber 3; unblocked damage also
    counts down a turn and wakes it stunned at 0). Awake it ROLLs OUT every
    turn: 16 damage + 2 self Strength."""
    name = "Slumbering Beetle"

    min_hp = 86
    max_hp = 86

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        self.is_awake = False
        # The body handed to CreatureCmd.Stun, waiting for the stunned turn.
        self._pending_stun_move = None
        super().__init__(hooks, rng or random.Random())
        from ...cmds import PowerCmd
        from ...powers import PlatingPower, SlumberPower
        PowerCmd.apply(hooks, self, PlatingPower, _PLATING)
        PowerCmd.apply(hooks, self, SlumberPower, _SLUMBER)

    def build_machine(self) -> MonsterMoveStateMachine:
        snore = MoveState("SNORE_MOVE", self._snore, Intent(MoveType.SLEEP))
        rollout = MoveState(
            "ROLL_OUT_MOVE", self._rollout,
            Intent(MoveType.ATTACK, damage=_ROLLOUT_DMG, also=(MoveType.BUFF,)),
        )
        branch = ConditionalBranchState("SNORE_NEXT")
        branch.add_state(snore, lambda: "slumber" in self.powers)
        branch.add_state(rollout, lambda: "slumber" not in self.powers)
        snore.follow_up = branch
        rollout.follow_up = rollout
        return MonsterMoveStateMachine([snore, branch, rollout], snore)

    def wake_up(self, stunned: bool) -> None:
        """Called by SlumberPower. WakeUpMove (SlumberingBeetle.cs:96-108) sets
        IsAwake and drops the Plating.

        The natural wake (AfterSideTurnEnd) awaits WakeUpMove inline. The damage
        wake does NOT: SlumberPower.cs:29 passes it to
        CreatureCmd.Stun(Owner, WakeUpMove, "ROLL_OUT_MOVE"), which makes it the
        stunned turn's perform body — so the beetle keeps its Plating for the
        rest of the player's turn and wakes on its own turn."""
        from ...cmds import CreatureCmd
        if stunned:
            self._pending_stun_move = self._wake_up_move
            # SlumberPower.cs:29 — CreatureCmd.Stun(Owner, WakeUpMove,
            # "ROLL_OUT_MOVE"): the id is the stun's FollowUpStateId, so the
            # machine resumes at ROLL_OUT after the stunned turn. Forcing the
            # state by hand was this port's stand-in for a nextMoveId that
            # CreatureCmd.stun used to drop for a MachineMonster.
            CreatureCmd.stun(self._hooks, self, next_move_key="ROLL_OUT_MOVE")
            return
        # The natural wake touches the machine not at all: WakeUpMove
        # (SlumberingBeetle.cs:96-108) only flips IsAwake and drops the
        # Plating, and SNORE_MOVE's follow-up is the SNORE_NEXT conditional
        # whose second arm is `!HasPower<SlumberPower>`
        # (SlumberingBeetle.cs:115-117) — the next player-turn-start roll walks
        # it to ROLL_OUT on its own. Force-setting ROLL_OUT here was the old
        # roll-inside-the-move world's stand-in for that, and now double-
        # advances (ROLL_OUT's follow-up is itself, so nothing broke visibly on
        # the beetle; the Matriarch's chain made the same bug fatal).
        self._wake_up_move()

    def _wake_up_move(self) -> None:
        """WakeUpMove's body (SlumberingBeetle.cs:96-108)."""
        from ...cmds import PowerCmd
        self.is_awake = True
        if "plating" in self.powers:
            PowerCmd.remove(self._hooks, self, "plating")

    def take_turn(self, ctx: CombatCtx) -> None:
        """Run the pending stun-move body as this turn's perform body.

        `CreatureCmd.Stun(creature, stunMove, nextMoveId)` (CreatureCmd.cs:884-904)
        does not run `stunMove`: `Creature.StunInternal` (Creature.cs:524-544)
        hangs it on a synthetic "STUNNED" MoveState, so the body is that move's
        PERFORM body and runs on the victim's stunned turn — inside
        MonsterModel.PerformMove, i.e. exactly here. This used to be a
        registered hook listener on the sim-only per-enemy `on_enemy_turn_start`
        slot; that slot is gone (turn_structure G5), and the side-scoped hooks
        that replaced it all fire either before every enemy has moved or after,
        neither of which is where a move body belongs.
        """
        body, self._pending_stun_move = self._pending_stun_move, None
        if body is not None:
            body()
        super().take_turn(ctx)

    def _snore(self, ctx: CombatCtx) -> None:
        pass

    def _rollout(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _ROLLOUT_DMG, 1)
        from ...cmds import PowerCmd
        from ...powers import StrengthPower
        PowerCmd.apply(ctx.hooks, self, StrengthPower, _ROLLOUT_STR)


@dataclass
class SlumberingBeetleEncounter(Encounter):
    """Bowlbug Rock + Bowlbug Silk guarding a Slumbering Beetle."""

    monster_classes: list = field(default_factory=list)

    def create_monsters(self, hooks: HookSystem, rng: random.Random, selection_rng=None) -> list[Monster]:
        from .bowlbugs import BowlbugRock, BowlbugSilk
        return [
            BowlbugRock(hooks, rng),
            BowlbugSilk(hooks, rng),
            SlumberingBeetle(hooks, rng),
        ]


SLUMBERING_BEETLE_NORMAL = SlumberingBeetleEncounter(id="slumbering_beetle_normal")
