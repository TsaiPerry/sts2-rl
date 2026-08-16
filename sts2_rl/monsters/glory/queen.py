from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ...actmap import AscensionLevel
from ..base import Encounter, Intent, Monster, MoveType, asc_value
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
_TACKLE_DMG = 18            # TorchHeadAmalgam.cs:32 base
_TACKLE_DMG_ASC = 19        # DeadlyEnemies
_WEAK_TACKLE_DMG = 14        # TorchHeadAmalgam.cs:34 base
_WEAK_TACKLE_DMG_ASC = 15    # DeadlyEnemies
_BEAM_DMG = 8
_BEAM_HITS = 3
# TorchHeadAmalgam.cs:36 SoulBeamDamage: DeadlyEnemies value (8) == base (8), a no-op.

# Queen
_PUPPET_CHAINS = 3
_MINE_DEBUFF = 99
_BURN_BRIGHT_ALLY_STR = 1
_BURN_BRIGHT_BLOCK = 20
_OFF_WITH_HEAD_DMG = 3        # Queen.cs:56 base
_OFF_WITH_HEAD_DMG_ASC = 4    # DeadlyEnemies
_OFF_WITH_HEAD_HITS = 5
_EXECUTION_DMG = 15           # Queen.cs:58 base
_EXECUTION_DMG_ASC = 18       # DeadlyEnemies
_ENRAGE_STR = 2
# Queen.cs:186 BurnBrightForMeMove strengthAmount: DeadlyEnemies value (1) ==
# base (1), a no-op; _BURN_BRIGHT_ALLY_STR above stays a plain constant.


class TorchHeadAmalgam(MachineMonster):
    """The Queen's minion: Tackle (18) → Tackle (18) → Soul Beam (8×3) → two
    Weak Tackles (14) → Soul Beam → loop. Marked a minion (its survival does
    not keep combat going once the Queen falls).

    Source: TorchHeadAmalgam.cs (non-ascension values)."""
    name = "Torch Head Amalgam"

    min_hp = 199
    max_hp = 199
    min_hp_asc = 211   # TorchHeadAmalgam.cs:28 -- ToughEnemies (MaxInitialHp == MinInitialHp)
    max_hp_asc = 211

    def _tackle_dmg(self) -> int:
        """TorchHeadAmalgam.cs:32 `TackleDamage` -- read at both the
        telegraphed Intent and the executed attack."""
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _TACKLE_DMG_ASC, _TACKLE_DMG)

    def _weak_tackle_dmg(self) -> int:
        """TorchHeadAmalgam.cs:34 `WeakTackleDamage`."""
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _WEAK_TACKLE_DMG_ASC, _WEAK_TACKLE_DMG)

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())
        from ...cmds import PowerCmd
        from ...powers import MinionPower
        PowerCmd.apply(hooks, self, MinionPower, 1)

    def build_machine(self) -> MonsterMoveStateMachine:
        tackle1 = MoveState(
            "TACKLE_MOVE", self._tackle, lambda: Intent(MoveType.ATTACK, damage=self._tackle_dmg())
        )
        tackle2 = MoveState(
            "TACKLE_2_MOVE", self._tackle, lambda: Intent(MoveType.ATTACK, damage=self._tackle_dmg())
        )
        beam = MoveState(
            "BEAM_MOVE", self._beam,
            Intent(MoveType.ATTACK, damage=_BEAM_DMG, hits=_BEAM_HITS),
        )
        weak1 = MoveState(
            "TACKLE_3_MOVE", self._weak_tackle,
            lambda: Intent(MoveType.ATTACK, damage=self._weak_tackle_dmg()),
        )
        weak2 = MoveState(
            "TACKLE_4_MOVE", self._weak_tackle,
            lambda: Intent(MoveType.ATTACK, damage=self._weak_tackle_dmg()),
        )
        tackle1.follow_up = tackle2
        tackle2.follow_up = beam
        beam.follow_up = weak1
        weak1.follow_up = weak2
        weak2.follow_up = beam
        return MonsterMoveStateMachine([tackle1, tackle2, beam, weak1, weak2], tackle1)

    def _tackle(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._tackle_dmg(), 1)

    def _weak_tackle(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._weak_tackle_dmg(), 1)

    def _beam(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _BEAM_DMG, _BEAM_HITS)


class Queen(MachineMonster):
    """Puppet Strings (Chains of Binding 3) → You Are Mine (Frail/Weak/
    Vulnerable 99) → while the Torch Head Amalgam lives, Burn Bright For Me
    (buff the amalgam + gain 20 block) loops; once the amalgam dies she switches
    to Off With Your Head (3×5) → Execution (15) → Enrage (+2 Strength) → loop.

    Source: Queen.cs (non-ascension values). The amalgam's death re-telegraphs
    an in-progress Burn Bright as Enrage on the spot (see on_amalgam_died); the
    branch already routes every later move past Burn Bright."""

    min_hp = 400            # Queen.cs:50 base
    max_hp = 400
    min_hp_asc = 419        # Queen.cs:50 -- ToughEnemies (MaxInitialHp == MinInitialHp)
    max_hp_asc = 419

    def _off_with_head_dmg(self) -> int:
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _OFF_WITH_HEAD_DMG_ASC, _OFF_WITH_HEAD_DMG)

    def _execution_dmg(self) -> int:
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _EXECUTION_DMG_ASC, _EXECUTION_DMG)

    def on_death(self, creature: Creature,
                 was_removal_prevented: bool = False) -> None:
        """`Queen.AfterDeath` (Queen.cs:221-234).

        Lived on a private `_AmalgamDeathListener` registered in a hand-made
        Powers+1 slot until hook_dispatch/G5 gave the sim a real MonsterModel
        listener category (CombatState.cs:417-421); the body is unchanged.
        """
        if isinstance(creature, TorchHeadAmalgam) and not self.is_dead:
            self.on_amalgam_died()

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
            Intent(MoveType.ATTACK, damage=self._off_with_head_dmg(), hits=_OFF_WITH_HEAD_HITS),
        )
        execution = MoveState(
            "EXECUTION_MOVE", self._execution,
            Intent(MoveType.ATTACK, damage=self._execution_dmg()),
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
        # Queen.cs:187-188 -- membership test is the enemy side minus self,
        # which still holds a death-vetoed retained corpse; use
        # `is_removed_from_combat` (not `is_gone`) as in Guardbot._guard.
        for enemy in combat.enemies:
            if enemy is not self and not enemy.is_removed_from_combat:
                PowerCmd.apply(ctx.hooks, enemy, StrengthPower, _BURN_BRIGHT_ALLY_STR)
        BlockCmd.apply(ctx.hooks, self, _BURN_BRIGHT_BLOCK, props=ValueProp.MOVE)

    def _off_with_head(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._off_with_head_dmg(), _OFF_WITH_HEAD_HITS)

    def _execution(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._execution_dmg(), 1)

    def _enrage(self, ctx: CombatCtx) -> None:
        from ...cmds import PowerCmd
        from ...powers import StrengthPower
        PowerCmd.apply(ctx.hooks, self, StrengthPower, _ENRAGE_STR)


QUEEN_BOSS = Encounter(
    id="queen_boss",
    monster_classes=[TorchHeadAmalgam, Queen],
    # QueenBoss.cs:17,43-50 — the row and the roster agree, so the sort is a
    # no-op today; declared so a future summon lands where the game puts it.
    slots=("amalgam", "queen"),
    monster_slots=("amalgam", "queen"),
)
