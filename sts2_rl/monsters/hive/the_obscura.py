"""The Obscura and its Parafright illusion (Hive). Sources: TheObscura.cs,
Parafright.cs, TheObscuraNormal.cs."""
from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ..base import Encounter, Intent, Monster, MoveType
from ..state_machine import (
    MachineMonster,
    MonsterMoveStateMachine,
    MoveRepeatType,
    MoveState,
    RandomBranchState,
)

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem

_GAZE_DMG = 10
_HARDENING_DMG = 6
_HARDENING_BLOCK = 6
_WAIL_STR = 3
_SLAM_DMG = 16


class Parafright(Monster):
    """Illusion summoned by The Obscura: SLAMs for 16 every turn and cannot
    truly die — IllusionPower revives it to full HP on its next turn."""

    min_hp = 21
    max_hp = 21

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())
        from ...cmds import PowerCmd
        from ...powers import IllusionPower
        PowerCmd.apply(hooks, self, IllusionPower, 1)

    @property
    def _illusion(self):
        return self.powers.get("illusion")

    @property
    def current_intent(self) -> Intent:
        if self.stunned:
            return Intent(MoveType.STUN)
        illusion = self._illusion
        if illusion is not None and illusion.is_reviving:
            return Intent(MoveType.HEAL)  # revive turn
        return Intent(MoveType.ATTACK, damage=_SLAM_DMG)

    def take_turn(self, ctx: CombatCtx) -> None:
        illusion = self._illusion
        if illusion is not None and illusion.is_reviving:
            illusion.revive()
            return
        self._execute_attack(ctx, _SLAM_DMG, 1)


class TheObscura(MachineMonster):
    """Opens with ILLUSION (summons a Parafright), then rolls PIERCING_GAZE
    (10), WAIL (+3 Strength to all allies), and HARDENING_STRIKE (6 + 6 block)
    — never the same move twice in a row."""
    name = "The Obscura"

    min_hp = 123
    max_hp = 123

    def build_machine(self) -> MonsterMoveStateMachine:
        illusion = MoveState("ILLUSION_MOVE", self._illusion, Intent(MoveType.SUMMON))
        gaze = MoveState(
            "PIERCING_GAZE_MOVE", self._gaze,
            Intent(MoveType.ATTACK, damage=_GAZE_DMG),
        )
        wail = MoveState("SAIL_MOVE", self._wail, Intent(MoveType.BUFF))
        hardening = MoveState(
            "HARDENING_STRIKE_MOVE", self._hardening,
            Intent(MoveType.ATTACK, damage=_HARDENING_DMG, also=(MoveType.DEFEND,)),
        )
        rand = RandomBranchState("RAND")
        rand.add_branch(gaze, 1.0, MoveRepeatType.CANNOT_REPEAT)
        rand.add_branch(wail, 1.0, MoveRepeatType.CANNOT_REPEAT)
        rand.add_branch(hardening, 1.0, MoveRepeatType.CANNOT_REPEAT)
        illusion.follow_up = rand
        gaze.follow_up = rand
        wail.follow_up = rand
        hardening.follow_up = rand
        return MonsterMoveStateMachine(
            [illusion, gaze, wail, hardening, rand], illusion
        )

    def _illusion(self, ctx: CombatCtx) -> None:
        from ...cmds import CreatureCmd
        # TheObscura.cs:84 — `CreatureCmd.Add<Parafright>(CombatState,
        # "illusion")`, index 0, so the Parafright re-sorts ahead of the
        # Obscura the instant it lands.
        CreatureCmd.add(
            ctx.hooks, Parafright(ctx.hooks, self._rng), slot_name="illusion",
        )

    def _gaze(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _GAZE_DMG, 1)

    def _wail(self, ctx: CombatCtx) -> None:
        from ...cmds import PowerCmd
        from ...powers import StrengthPower
        # GetTeammatesOf includes the caster itself.
        for enemy in ctx.enemies:
            if not enemy.is_gone:
                PowerCmd.apply(ctx.hooks, enemy, StrengthPower, _WAIL_STR)

    def _hardening(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _HARDENING_DMG, 1)
        from ...cmds import BlockCmd
        BlockCmd.apply(ctx.hooks, self, _HARDENING_BLOCK)


THE_OBSCURA_NORMAL = Encounter(
    id="the_obscura_normal",
    monster_classes=[TheObscura],
    # TheObscuraNormal.cs:15,25-28 — same shape as Fogmog: the Obscura sits
    # in "obscura" (index 1) and the ILLUSION summon takes "illusion"
    # (index 0), which re-sorts the Parafright ahead of it.
    slots=("illusion", "obscura"),
    monster_slots=("obscura",),
)
