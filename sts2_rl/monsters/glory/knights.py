from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ..base import Encounter, Intent, MoveType
from ..hive.flail_knight import FlailKnight
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

_POWER_SHIELD_DMG = 6
_POWER_SHIELD_BLOCK = 5
_SPEAR_DMG = 10
_BOMB_DMG = 35
_HEX_AMOUNT = 2
_SOUL_SLASH_DMG = 15
_SOUL_FLAME_DMG = 3
_SOUL_FLAME_HITS = 3


class MagiKnight(MachineMonster):
    """Power Shield (6 + 5 block) → Dampen (downgrade the player's upgraded
    cards) → Spear (10) → Prep (5 block) → Magic Bomb (35) → Spear → loop. The
    Dampen is restored when the Magi Knight dies.

    Source: MagiKnight.cs (non-ascension values)."""
    name = "Magi Knight"

    min_hp = 82
    max_hp = 82

    def build_machine(self) -> MonsterMoveStateMachine:
        power_shield = MoveState(
            "POWER_SHIELD_MOVE", self._power_shield,
            Intent(MoveType.ATTACK, damage=_POWER_SHIELD_DMG, also=(MoveType.DEFEND,)),
        )
        dampen = MoveState("DAMPEN_MOVE", self._dampen, Intent(MoveType.DEBUFF))
        spear = MoveState(
            "RAM_MOVE", self._spear, Intent(MoveType.ATTACK, damage=_SPEAR_DMG)
        )
        prep = MoveState("PREP_MOVE", self._prep, Intent(MoveType.DEFEND))
        bomb = MoveState(
            "MAGIC_BOMB", self._bomb, Intent(MoveType.ATTACK, damage=_BOMB_DMG)
        )
        power_shield.follow_up = dampen
        dampen.follow_up = spear
        spear.follow_up = prep
        prep.follow_up = bomb
        bomb.follow_up = spear
        return MonsterMoveStateMachine(
            [power_shield, dampen, spear, prep, bomb], power_shield
        )

    def _power_shield(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _POWER_SHIELD_DMG, 1)
        from ...cmds import BlockCmd
        from ...valueprops import ValueProp
        BlockCmd.apply(ctx.hooks, self, _POWER_SHIELD_BLOCK, props=ValueProp.MOVE)

    def _dampen(self, ctx: CombatCtx) -> None:
        from ...cmds import PowerCmd
        from ...powers import DampenPower
        # MagiKnight.cs:78-96 DampenMove: fetch the target's existing
        # DampenPower (if any), AddCaster this Magi Knight either way, and
        # call PowerCmd.Apply ONLY when a new instance had to be created --
        # a second caster joining an existing Dampen does not re-trigger the
        # downgrade-everything-upgraded pass. PowerCmd.apply only takes a
        # power CLASS (no pre-built-instance overload), so the sim cannot
        # add the caster before registration the way C# does; it adds the
        # caster to the freshly created instance immediately after instead,
        # which is unobservable -- AddCaster only mutates the caster set and
        # nothing reads that set between construction and this call.
        # monster/magi_knight/g1.
        target = ctx.player
        existing = target.powers.get(DampenPower.id)
        if existing is None:
            created = PowerCmd.apply(ctx.hooks, target, DampenPower, 1, applier=self)
            if created is not None:
                created.add_caster(self)
        else:
            existing.add_caster(self)

    def _spear(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _SPEAR_DMG, 1)

    def _prep(self, ctx: CombatCtx) -> None:
        from ...cmds import BlockCmd
        from ...valueprops import ValueProp
        BlockCmd.apply(ctx.hooks, self, _POWER_SHIELD_BLOCK, props=ValueProp.MOVE)

    def _bomb(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _BOMB_DMG, 1)


class SpectralKnight(MachineMonster):
    """Hex (make the player's cards Ethereal) → Soul Slash (15) → randomly Soul
    Slash (at most twice in a row) or Soul Flame (3×3, cannot repeat); both
    branches are weight 1. The Hex lifts when the Spectral Knight dies.

    Source: SpectralKnight.cs (non-ascension values)."""
    name = "Spectral Knight"

    min_hp = 93
    max_hp = 93

    def build_machine(self) -> MonsterMoveStateMachine:
        hex_move = MoveState("HEX", self._hex, Intent(MoveType.DEBUFF))
        soul_slash = MoveState(
            "SOUL_SLASH", self._soul_slash,
            Intent(MoveType.ATTACK, damage=_SOUL_SLASH_DMG),
        )
        soul_flame = MoveState(
            "SOUL_FLAME", self._soul_flame,
            Intent(MoveType.ATTACK, damage=_SOUL_FLAME_DMG, hits=_SOUL_FLAME_HITS),
        )
        branch = RandomBranchState("RAND")
        hex_move.follow_up = soul_slash
        soul_slash.follow_up = branch
        soul_flame.follow_up = branch
        # SpectralKnight.cs:52 AddBranch(state, 2) is the (state, int
        # maxRepeats) overload — a repeat limit, not a weight.
        branch.add_branch(
            soul_slash, repeat_type=MoveRepeatType.CAN_REPEAT_X_TIMES, max_times=2
        )
        branch.add_branch(soul_flame, repeat_type=MoveRepeatType.CANNOT_REPEAT)
        return MonsterMoveStateMachine(
            [hex_move, soul_slash, soul_flame, branch], hex_move
        )

    def _hex(self, ctx: CombatCtx) -> None:
        from ...cmds import PowerCmd
        from ...powers import HexPower
        PowerCmd.apply(ctx.hooks, ctx.player, HexPower, _HEX_AMOUNT, applier=self)

    def _soul_slash(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _SOUL_SLASH_DMG, 1)

    def _soul_flame(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _SOUL_FLAME_DMG, _SOUL_FLAME_HITS)


KNIGHTS_ELITE = Encounter(
    id="knights_elite",
    monster_classes=[FlailKnight, SpectralKnight, MagiKnight],
    # KnightsElite.cs:37-45 seats the three knights by name but declares NO
    # `Slots` override, so `Slots.IndexOf` is -1 for all three and the sort
    # is a no-op — the names are carried for fidelity, not for ordering.
    monster_slots=("first", "second", "third"),
)
