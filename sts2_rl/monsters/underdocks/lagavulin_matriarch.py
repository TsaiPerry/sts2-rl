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

_SLASH_DMG = 19
_SLASH2_DMG = 12
_SLASH2_BLOCK = 12
_DISEMBOWEL_DMG = 9
_DISEMBOWEL_HITS = 2
_SIPHON_STR_DEX = 2
_PLATING = 12
_ASLEEP_TURNS = 3


class LagavulinMatriarch(MachineMonster):
    """Underdocks boss. Sleeps behind Plating 12 for 3 turns (Asleep) — or
    until unblocked damage wakes her, which removes the Plating and costs her
    a turn waking up. Awake she loops SLASH (19) → DISEMBOWEL (9×2) → SLASH2
    (12 + 12 block) → SOUL_SIPHON (player -2 Str/-2 Dex, self +2 Str)."""
    name = "Lagavulin Matriarch"

    min_hp = 222
    max_hp = 222

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        self.is_awake = False
        super().__init__(hooks, rng or random.Random())
        from ...cmds import PowerCmd
        from ...powers import AsleepPower, PlatingPower
        PowerCmd.apply(hooks, self, PlatingPower, _PLATING)
        PowerCmd.apply(hooks, self, AsleepPower, _ASLEEP_TURNS)

    def build_machine(self) -> MonsterMoveStateMachine:
        sleep = MoveState("SLEEP_MOVE", self._sleep, Intent(MoveType.SLEEP))
        slash = MoveState(
            "SLASH_MOVE", self._slash, Intent(MoveType.ATTACK, damage=_SLASH_DMG)
        )
        slash2 = MoveState(
            "SLASH2_MOVE", self._slash2,
            Intent(MoveType.ATTACK, damage=_SLASH2_DMG, also=(MoveType.DEFEND,)),
        )
        disembowel = MoveState(
            "DISEMBOWEL_MOVE", self._disembowel,
            Intent(MoveType.ATTACK, damage=_DISEMBOWEL_DMG, hits=_DISEMBOWEL_HITS),
        )
        soul_siphon = MoveState(
            "SOUL_SIPHON_MOVE", self._soul_siphon,
            Intent(MoveType.DEBUFF, also=(MoveType.BUFF,)),
        )
        sleep_branch = ConditionalBranchState("SLEEP_BRANCH")
        sleep_branch.add_state(sleep, lambda: "asleep" in self.powers)
        sleep_branch.add_state(slash, lambda: "asleep" not in self.powers)
        sleep.follow_up = sleep_branch
        slash.follow_up = disembowel
        disembowel.follow_up = slash2
        slash2.follow_up = soul_siphon
        soul_siphon.follow_up = slash
        return MonsterMoveStateMachine(
            [sleep_branch, sleep, slash, slash2, soul_siphon, disembowel], sleep
        )

    def wake_up(self, *, stunned: bool) -> None:
        """Called by AsleepPower. Waking from damage costs her next turn
        (mirrors CreatureCmd.Stun(WakeUpMove, "SLASH_MOVE")); a natural wake
        goes straight to SLASH."""
        if self.is_awake:
            return
        self.is_awake = True
        slash = self.machine.states["SLASH_MOVE"]
        self.machine.force_current_state(slash)
        self._current_move = slash
        if stunned:
            from ...cmds import CreatureCmd
            CreatureCmd.stun(self._hooks, self)

    def _sleep(self, ctx: CombatCtx) -> None:
        pass

    def _slash(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _SLASH_DMG, 1)

    def _slash2(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _SLASH2_DMG, 1)
        from ...cmds import BlockCmd
        BlockCmd.apply(ctx.hooks, self, _SLASH2_BLOCK)

    def _disembowel(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _DISEMBOWEL_DMG, _DISEMBOWEL_HITS)

    def _soul_siphon(self, ctx: CombatCtx) -> None:
        from ...cmds import PowerCmd
        from ...powers import DexterityPower, StrengthPower
        PowerCmd.apply(ctx.hooks, ctx.player, StrengthPower, -_SIPHON_STR_DEX)
        PowerCmd.apply(ctx.hooks, ctx.player, DexterityPower, -_SIPHON_STR_DEX)
        PowerCmd.apply(ctx.hooks, self, StrengthPower, _SIPHON_STR_DEX)


LAGAVULIN_MATRIARCH_BOSS = Encounter(
    id="lagavulin_matriarch_boss",
    monster_classes=[LagavulinMatriarch],
)
