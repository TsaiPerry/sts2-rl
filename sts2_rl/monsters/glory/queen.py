from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ...hooks import CAT_POWER
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

# TorchHeadAmalgam
_TACKLE_DMG = 18
_WEAK_TACKLE_DMG = 14
_BEAM_DMG = 8
_BEAM_HITS = 3

# Queen
_PUPPET_CHAINS = 3
_MINE_DEBUFF = 99
_BURN_BRIGHT_ALLY_STR = 1
_BURN_BRIGHT_BLOCK = 20
_OFF_WITH_HEAD_DMG = 3
_OFF_WITH_HEAD_HITS = 5
_EXECUTION_DMG = 15
_ENRAGE_STR = 2


class TorchHeadAmalgam(MachineMonster):
    """The Queen's minion: Tackle (18) → Tackle (18) → Soul Beam (8×3) → two
    Weak Tackles (14) → Soul Beam → loop. Marked a minion (its survival does
    not keep combat going once the Queen falls).

    Source: TorchHeadAmalgam.cs (non-ascension values)."""
    name = "Torch Head Amalgam"

    min_hp = 199
    max_hp = 199

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())
        from ...cmds import PowerCmd
        from ...powers import MinionPower
        PowerCmd.apply(hooks, self, MinionPower, 1)

    def build_machine(self) -> MonsterMoveStateMachine:
        tackle1 = MoveState(
            "TACKLE_MOVE", self._tackle, Intent(MoveType.ATTACK, damage=_TACKLE_DMG)
        )
        tackle2 = MoveState(
            "TACKLE_2_MOVE", self._tackle, Intent(MoveType.ATTACK, damage=_TACKLE_DMG)
        )
        beam = MoveState(
            "BEAM_MOVE", self._beam,
            Intent(MoveType.ATTACK, damage=_BEAM_DMG, hits=_BEAM_HITS),
        )
        weak1 = MoveState(
            "TACKLE_3_MOVE", self._weak_tackle,
            Intent(MoveType.ATTACK, damage=_WEAK_TACKLE_DMG),
        )
        weak2 = MoveState(
            "TACKLE_4_MOVE", self._weak_tackle,
            Intent(MoveType.ATTACK, damage=_WEAK_TACKLE_DMG),
        )
        tackle1.follow_up = tackle2
        tackle2.follow_up = beam
        beam.follow_up = weak1
        weak1.follow_up = weak2
        weak2.follow_up = beam
        return MonsterMoveStateMachine([tackle1, tackle2, beam, weak1, weak2], tackle1)

    def _tackle(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _TACKLE_DMG, 1)

    def _weak_tackle(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _WEAK_TACKLE_DMG, 1)

    def _beam(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _BEAM_DMG, _BEAM_HITS)


class _AmalgamDeathListener:
    """Stand-in for Queen.AfterDeath (Queen.cs:221-234).

    CombatState.IterateHookListeners (CombatState.cs:413-420) adds a monster's
    MonsterModel to the listener walk right after that creature's Powers, but
    the sim has no MonsterModel listener category at all (hook_dispatch G5), so
    the Queen registers this listener in that slot instead."""

    hook_category = CAT_POWER + 1

    def __init__(self, queen: Queen) -> None:
        self.queen = queen
        self.owner = queen  # dispatch-order slot: the Queen's own creature

    def on_death(self, creature: Creature,
                 was_removal_prevented: bool = False) -> None:
        if isinstance(creature, TorchHeadAmalgam) and not self.queen.is_dead:
            self.queen.on_amalgam_died()


class Queen(MachineMonster):
    """Puppet Strings (Chains of Binding 3) → You Are Mine (Frail/Weak/
    Vulnerable 99) → while the Torch Head Amalgam lives, Burn Bright For Me
    (buff the amalgam + gain 20 block) loops; once the amalgam dies she switches
    to Off With Your Head (3×5) → Execution (15) → Enrage (+2 Strength) → loop.

    Source: Queen.cs (non-ascension values). The amalgam's death re-telegraphs
    an in-progress Burn Bright as Enrage on the spot (see on_amalgam_died); the
    branch already routes every later move past Burn Bright."""

    min_hp = 400
    max_hp = 400

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())
        hooks.register(_AmalgamDeathListener(self))

    def on_amalgam_died(self) -> None:
        """Queen.cs:226-232 — HasAmalgamDied/Amalgam are derived state in the
        sim (`_amalgam_died` reads the combat), so all that is left is the
        immediate re-telegraph: a pending Burn Bright becomes Enrage via
        SetMoveImmediate(EnragedState), i.e. NextMove = state PLUS
        MoveStateMachine.ForceCurrentState(state) (MonsterModel.cs:420-432).
        ForceCurrentState does not append to the state log."""
        enraged = self.machine.states["ENRAGE_MOVE"]
        if self._current_move.id == "BURN_BRIGHT_FOR_ME_MOVE":
            self._current_move = enraged
            self.machine.force_current_state(enraged)

    def _amalgam(self) -> Monster | None:
        combat = self._hooks.combat
        if combat is None:
            return None
        for enemy in combat.enemies:
            if isinstance(enemy, TorchHeadAmalgam):
                return enemy
        return None

    def _amalgam_died(self) -> bool:
        amalgam = self._amalgam()
        return amalgam is None or amalgam.is_gone

    def build_machine(self) -> MonsterMoveStateMachine:
        puppet = MoveState(
            "PUPPET_STRINGS_MOVE", self._puppet_strings, Intent(MoveType.CARD_DEBUFF)
        )
        youre_mine = MoveState(
            "YOU_ARE_MINE_MOVE", self._youre_mine, Intent(MoveType.DEBUFF)
        )
        burn_bright = MoveState(
            "BURN_BRIGHT_FOR_ME_MOVE", self._burn_bright,
            Intent(MoveType.BUFF, also=(MoveType.DEFEND,)),
        )
        off_with_head = MoveState(
            "OFF_WITH_YOUR_HEAD_MOVE", self._off_with_head,
            Intent(MoveType.ATTACK, damage=_OFF_WITH_HEAD_DMG, hits=_OFF_WITH_HEAD_HITS),
        )
        execution = MoveState(
            "EXECUTION_MOVE", self._execution,
            Intent(MoveType.ATTACK, damage=_EXECUTION_DMG),
        )
        enrage = MoveState("ENRAGE_MOVE", self._enrage, Intent(MoveType.BUFF))
        mine_branch = ConditionalBranchState("YOURE_MINE_NOW_BRANCH")
        burn_branch = ConditionalBranchState("BURN_BRIGHT_FOR_ME_BRANCH")

        puppet.follow_up = youre_mine
        youre_mine.follow_up = mine_branch
        mine_branch.add_state(burn_bright, lambda: not self._amalgam_died())
        mine_branch.add_state(off_with_head, self._amalgam_died)
        burn_bright.follow_up = burn_branch
        burn_branch.add_state(burn_bright, lambda: not self._amalgam_died())
        burn_branch.add_state(off_with_head, self._amalgam_died)
        off_with_head.follow_up = execution
        execution.follow_up = enrage
        enrage.follow_up = off_with_head
        return MonsterMoveStateMachine(
            [puppet, youre_mine, burn_bright, burn_branch, mine_branch,
             off_with_head, execution, enrage],
            puppet,
        )

    def _puppet_strings(self, ctx: CombatCtx) -> None:
        from ...cmds import PowerCmd
        from ...powers import ChainsOfBindingPower
        PowerCmd.apply(ctx.hooks, ctx.player, ChainsOfBindingPower, _PUPPET_CHAINS, applier=self)

    def _youre_mine(self, ctx: CombatCtx) -> None:
        from ...cmds import PowerCmd
        from ...powers import FrailPower, VulnerablePower, WeakPower
        PowerCmd.apply(ctx.hooks, ctx.player, FrailPower, _MINE_DEBUFF)
        PowerCmd.apply(ctx.hooks, ctx.player, WeakPower, _MINE_DEBUFF)
        PowerCmd.apply(ctx.hooks, ctx.player, VulnerablePower, _MINE_DEBUFF)

    def _burn_bright(self, ctx: CombatCtx) -> None:
        from ...cmds import BlockCmd, PowerCmd
        from ...powers import StrengthPower
        from ...valueprops import ValueProp
        combat = ctx.hooks.combat
        for enemy in combat.enemies:
            if enemy is not self and not enemy.is_gone:
                PowerCmd.apply(ctx.hooks, enemy, StrengthPower, _BURN_BRIGHT_ALLY_STR)
        BlockCmd.apply(ctx.hooks, self, _BURN_BRIGHT_BLOCK, props=ValueProp.MOVE)

    def _off_with_head(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _OFF_WITH_HEAD_DMG, _OFF_WITH_HEAD_HITS)

    def _execution(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _EXECUTION_DMG, 1)

    def _enrage(self, ctx: CombatCtx) -> None:
        from ...cmds import PowerCmd
        from ...powers import StrengthPower
        PowerCmd.apply(ctx.hooks, self, StrengthPower, _ENRAGE_STR)


QUEEN_BOSS = Encounter(
    id="queen_boss",
    monster_classes=[TorchHeadAmalgam, Queen],
)
