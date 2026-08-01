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

_FIRST_FORM_HP = 100
_SECOND_FORM_HP = 200
_THIRD_FORM_HP = 300
_ENRAGE = 2
_BITE_DMG = 20
_SKULL_BASH_DMG = 14
_SKULL_BASH_VULN = 1
_MULTI_CLAW_DMG = 10
_MULTI_CLAW_BASE_HITS = 3
_LACERATE_DMG = 10
_LACERATE_HITS = 3
_BIG_POUNCE_DMG = 45
_GROWL_BURN = 3
_GROWL_STR = 2


class TestSubject(MachineMonster):
    """A three-phase boss. Phase 1 (100 HP): Bite (20) ↔ Skull Bash (14 +
    Vulnerable 1). When killed it Respawns (Adaptable prevents death) at 200 HP
    for phase 2 (Multi-Claw 10×3, +1 hit each use, and Painful Stabs adds Wounds
    on unblocked hits), then again at 300 HP for phase 3 (Lacerate 10×3 → Big
    Pounce 45 → Burning Growl [3 Burn + 2 Strength], with Nemesis granting
    Intangible every other turn). Its third death is final. Starts with Enrage 2.

    Source: TestSubject.cs / AdaptablePower.cs (non-ascension values).

    Its displayed Title is "Test Subject #C{Count}" where TestSubject.cs:72
    fills Count from `SaveManager.Instance.Progress.TestSubjectKills + 8` — a
    PROFILE-lifetime counter, not run state, so no run seed can reproduce it
    (the same encounter reads #C71 / #C106 / #C114 across the three recordings
    that fight it). The sim carries the un-numbered name and the conformance
    driver accepts the recorded suffix (combat_driver._name_matches)."""

    name = "Test Subject"
    min_hp = _FIRST_FORM_HP
    max_hp = _FIRST_FORM_HP

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        self._respawns = 0
        self._extra_claw_hits = 0
        super().__init__(hooks, rng or random.Random())
        from ...cmds import PowerCmd
        from ...powers import AdaptablePower, EnragePower
        PowerCmd.apply(hooks, self, AdaptablePower, 1)
        PowerCmd.apply(hooks, self, EnragePower, _ENRAGE)

    def _multi_claw_hits(self) -> int:
        return _MULTI_CLAW_BASE_HITS + self._extra_claw_hits

    def build_machine(self) -> MonsterMoveStateMachine:
        dead = MoveState(
            "RESPAWN_MOVE", self._respawn,
            Intent(MoveType.HEAL, also=(MoveType.BUFF,)),
            must_perform_once_before_transitioning=True,
        )
        bite = MoveState(
            "BITE_MOVE", self._bite, Intent(MoveType.ATTACK, damage=_BITE_DMG)
        )
        skull_bash = MoveState(
            "SKULL_BASH_MOVE", self._skull_bash,
            Intent(MoveType.ATTACK, damage=_SKULL_BASH_DMG, also=(MoveType.DEBUFF,)),
        )
        multi_claw = MoveState(
            "MULTI_CLAW_MOVE", self._multi_claw,
            lambda: Intent(
                MoveType.ATTACK, damage=_MULTI_CLAW_DMG, hits=self._multi_claw_hits()
            ),
        )
        lacerate = MoveState(
            "PHASE3_LACERATE_MOVE", self._lacerate,
            Intent(MoveType.ATTACK, damage=_LACERATE_DMG, hits=_LACERATE_HITS),
        )
        pounce = MoveState(
            "BIG_POUNCE", self._pounce,
            Intent(MoveType.ATTACK, damage=_BIG_POUNCE_DMG),
        )
        growl = MoveState(
            "BURNING_GROWL_MOVE", self._growl,
            # TestSubject.cs:201 `new StatusIntent(BurningGrowlBurnCount)` --
            # non-ascension BurningGrowlBurnCount = 3 (TestSubject.cs:101),
            # same value as _GROWL_BURN.
            Intent(MoveType.STATUS_CARD, also=(MoveType.BUFF,),
                   status_count=_GROWL_BURN),
        )
        revive_branch = ConditionalBranchState("REVIVE_BRANCH")
        bite.follow_up = skull_bash
        skull_bash.follow_up = bite
        multi_claw.follow_up = multi_claw
        lacerate.follow_up = pounce
        pounce.follow_up = growl
        growl.follow_up = lacerate
        dead.follow_up = revive_branch
        revive_branch.add_state(multi_claw, lambda: self._respawns < 2)
        revive_branch.add_state(lacerate, lambda: self._respawns >= 2)
        self._dead_state = dead
        return MonsterMoveStateMachine(
            [dead, bite, skull_bash, multi_claw, lacerate, pounce, growl,
             revive_branch],
            bite,
        )

    def trigger_dead_state(self) -> None:
        """Called by Adaptable when a killing blow lands: force the Respawn move
        (mirrors TestSubject.TriggerDeadState → SetMoveImmediate)."""
        self.machine.force_current_state(self._dead_state)
        self._current_move = self._dead_state

    def _revive(self, form_hp: int) -> None:
        delta = form_hp - self.hp
        self.max_hp = form_hp
        self.hp = form_hp
        self._hooks.on_hp_changed(self, delta)

    def _respawn(self, ctx: CombatCtx) -> None:
        self._respawns += 1
        from ...cmds import PowerCmd
        from ...powers import AdaptablePower, NemesisPower, PainfulStabsPower
        adaptable = self.powers.get("adaptable")
        if isinstance(adaptable, AdaptablePower):
            adaptable.do_revive()
        if self._respawns == 1:
            self._revive(_SECOND_FORM_HP)
            PowerCmd.apply(ctx.hooks, self, PainfulStabsPower, 1)
        elif self._respawns == 2:
            self._revive(_THIRD_FORM_HP)
            PowerCmd.apply(ctx.hooks, self, NemesisPower, 1)
            PowerCmd.remove(ctx.hooks, self, "adaptable")
            PowerCmd.remove(ctx.hooks, self, "painful_stabs")

    def _bite(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _BITE_DMG, 1)

    def _skull_bash(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _SKULL_BASH_DMG, 1)
        from ...cmds import PowerCmd
        from ...powers import VulnerablePower
        PowerCmd.apply(ctx.hooks, ctx.player, VulnerablePower, _SKULL_BASH_VULN)

    def _multi_claw(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _MULTI_CLAW_DMG, self._multi_claw_hits())
        self._extra_claw_hits += 1

    def _lacerate(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _LACERATE_DMG, _LACERATE_HITS)

    def _pounce(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _BIG_POUNCE_DMG, 1)

    def _growl(self, ctx: CombatCtx) -> None:
        from ...cards import BurnCard
        from ...cmds import CardPileCmd, PowerCmd
        from ...powers import StrengthPower
        for _ in range(_GROWL_BURN):
            CardPileCmd.add_to_discard(ctx.hooks, ctx.player, BurnCard())
        PowerCmd.apply(ctx.hooks, self, StrengthPower, _GROWL_STR)


TEST_SUBJECT_BOSS = Encounter(
    id="test_subject_boss",
    monster_classes=[TestSubject],
)
