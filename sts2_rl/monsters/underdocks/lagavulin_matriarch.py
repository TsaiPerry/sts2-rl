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

_SLASH_DMG = 19               # LagavulinMatriarch.cs:53 base
_SLASH_DMG_ASC = 21           # DeadlyEnemies (asc 9+)
_SLASH2_DMG = 12              # LagavulinMatriarch.cs:55 base
_SLASH2_DMG_ASC = 14          # DeadlyEnemies (asc 9+)
_SLASH2_BLOCK = 12            # LagavulinMatriarch.cs:57 base -- gated on ToughEnemies
_SLASH2_BLOCK_ASC = 14        # ToughEnemies (asc 8+)
_DISEMBOWEL_DMG = 9           # LagavulinMatriarch.cs:59 base
_DISEMBOWEL_DMG_ASC = 10      # DeadlyEnemies (asc 9+)
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
    min_hp_asc = 233     # LagavulinMatriarch.cs:49 ToughEnemies (asc 8+)
    max_hp_asc = 233     # LagavulinMatriarch.cs:51 `MaxInitialHp => MinInitialHp`

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        self.is_awake = False
        super().__init__(hooks, rng or random.Random())
        from ...cmds import PowerCmd
        from ...powers import AsleepPower, PlatingPower
        PowerCmd.apply(hooks, self, PlatingPower, _PLATING)
        PowerCmd.apply(hooks, self, AsleepPower, _ASLEEP_TURNS)

    def _slash_dmg(self) -> int:
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _SLASH_DMG_ASC, _SLASH_DMG)

    def _slash2_dmg(self) -> int:
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _SLASH2_DMG_ASC, _SLASH2_DMG)

    def _slash2_block(self) -> int:
        return asc_value(self._hooks, AscensionLevel.TOUGH_ENEMIES,
                          _SLASH2_BLOCK_ASC, _SLASH2_BLOCK)

    def _disembowel_dmg(self) -> int:
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _DISEMBOWEL_DMG_ASC, _DISEMBOWEL_DMG)

    def build_machine(self) -> MonsterMoveStateMachine:
        sleep = MoveState("SLEEP_MOVE", self._sleep, Intent(MoveType.SLEEP))
        slash = MoveState(
            "SLASH_MOVE", self._slash,
            lambda: Intent(MoveType.ATTACK, damage=self._slash_dmg()),
        )
        slash2 = MoveState(
            "SLASH2_MOVE", self._slash2,
            lambda: Intent(MoveType.ATTACK, damage=self._slash2_dmg(),
                            also=(MoveType.DEFEND,)),
        )
        disembowel = MoveState(
            "DISEMBOWEL_MOVE", self._disembowel,
            lambda: Intent(MoveType.ATTACK, damage=self._disembowel_dmg(),
                            hits=_DISEMBOWEL_HITS),
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
        if stunned:
            # AsleepPower.cs:33 -- CreatureCmd.Stun(Owner, WakeUpMove, "SLASH_MOVE"):
            # id is the stun's FollowUpStateId, so she resumes at SLASH after the stun.
            from ...cmds import CreatureCmd
            CreatureCmd.stun(self._hooks, self, next_move_key="SLASH_MOVE")
            return
        # Natural wake: WakeUpMove (LagavulinMatriarch.cs:189-199) only flips IsAwake;
        # SLEEP_MOVE's SLEEP_BRANCH follow-up walks to SLASH on its own next turn.

    def _sleep(self, ctx: CombatCtx) -> None:
        pass

    def _slash(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._slash_dmg(), 1)

    def _slash2(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._slash2_dmg(), 1)
        from ...cmds import BlockCmd
        BlockCmd.apply(ctx.hooks, self, self._slash2_block())

    def _disembowel(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._disembowel_dmg(), _DISEMBOWEL_HITS)

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
