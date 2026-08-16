from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ...actmap import AscensionLevel
from ..base import Encounter, Intent, MoveType, asc_value
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

_POWER_SHIELD_DMG = 6          # MagiKnight.cs:47 base
_POWER_SHIELD_DMG_ASC = 7      # DeadlyEnemies
_POWER_SHIELD_BLOCK = 5        # MagiKnight.cs:49 base
_POWER_SHIELD_BLOCK_ASC = 9    # ToughEnemies
_SPEAR_DMG = 10                # MagiKnight.cs:51 base
_SPEAR_DMG_ASC = 11            # DeadlyEnemies
_BOMB_DMG = 35                 # MagiKnight.cs:53 base
_BOMB_DMG_ASC = 40             # DeadlyEnemies
_HEX_AMOUNT = 2
_SOUL_SLASH_DMG = 15          # SpectralKnight.cs:38 base
_SOUL_SLASH_DMG_ASC = 17      # DeadlyEnemies (asc 9+)
_SOUL_FLAME_DMG = 3           # SpectralKnight.cs:40 base
_SOUL_FLAME_DMG_ASC = 4       # DeadlyEnemies
_SOUL_FLAME_HITS = 3


class MagiKnight(MachineMonster):
    """Power Shield (6 + 5 block) → Dampen (downgrade the player's upgraded
    cards) → Spear (10) → Prep (5 block) → Magic Bomb (35) → Spear → loop. The
    Dampen is restored when the Magi Knight dies.

    Source: MagiKnight.cs (non-ascension values)."""
    name = "Magi Knight"

    min_hp = 82
    max_hp = 82
    min_hp_asc = 89   # MagiKnight.cs:41 -- ToughEnemies (MaxInitialHp == MinInitialHp)
    max_hp_asc = 89

    def _power_shield_dmg(self) -> int:
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _POWER_SHIELD_DMG_ASC, _POWER_SHIELD_DMG)

    def _power_shield_block(self) -> int:
        return asc_value(self._hooks, AscensionLevel.TOUGH_ENEMIES,
                          _POWER_SHIELD_BLOCK_ASC, _POWER_SHIELD_BLOCK)

    def _spear_dmg(self) -> int:
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _SPEAR_DMG_ASC, _SPEAR_DMG)

    def _bomb_dmg(self) -> int:
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _BOMB_DMG_ASC, _BOMB_DMG)

    def build_machine(self) -> MonsterMoveStateMachine:
        power_shield = MoveState(
            "POWER_SHIELD_MOVE", self._power_shield,
            lambda: Intent(MoveType.ATTACK, damage=self._power_shield_dmg(), also=(MoveType.DEFEND,)),
        )
        dampen = MoveState("DAMPEN_MOVE", self._dampen, Intent(MoveType.DEBUFF))
        spear = MoveState(
            "RAM_MOVE", self._spear, lambda: Intent(MoveType.ATTACK, damage=self._spear_dmg())
        )
        prep = MoveState("PREP_MOVE", self._prep, Intent(MoveType.DEFEND))
        bomb = MoveState(
            "MAGIC_BOMB", self._bomb, lambda: Intent(MoveType.ATTACK, damage=self._bomb_dmg())
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
        self._execute_attack(ctx, self._power_shield_dmg(), 1)
        from ...cmds import BlockCmd
        from ...valueprops import ValueProp
        BlockCmd.apply(ctx.hooks, self, self._power_shield_block(), props=ValueProp.MOVE)

    def _dampen(self, ctx: CombatCtx) -> None:
        from ...cmds import PowerCmd
        from ...powers import DampenPower
        # MagiKnight.cs:78-96 -- a second caster joining an existing Dampen
        # must NOT re-trigger the downgrade-everything-upgraded pass, so
        # PowerCmd.apply (Apply) only runs when a new instance is created;
        # AddCaster always runs. Sim adds the caster right after creation
        # instead of before (PowerCmd.apply takes a class, not an instance),
        # which is unobservable since nothing reads the caster set in
        # between. monster/magi_knight/g1.
        target = ctx.player
        existing = target.powers.get(DampenPower.id)
        if existing is None:
            created = PowerCmd.apply(ctx.hooks, target, DampenPower, 1, applier=self)
            if created is not None:
                created.add_caster(self)
        else:
            existing.add_caster(self)

    def _spear(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._spear_dmg(), 1)

    def _prep(self, ctx: CombatCtx) -> None:
        from ...cmds import BlockCmd
        from ...valueprops import ValueProp
        BlockCmd.apply(ctx.hooks, self, self._power_shield_block(), props=ValueProp.MOVE)

    def _bomb(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._bomb_dmg(), 1)


class SpectralKnight(MachineMonster):
    """Hex (make the player's cards Ethereal) → Soul Slash (15) → randomly Soul
    Slash (at most twice in a row) or Soul Flame (3×3, cannot repeat); both
    branches are weight 1. The Hex lifts when the Spectral Knight dies.

    Source: SpectralKnight.cs (non-ascension values)."""
    name = "Spectral Knight"

    min_hp = 93          # SpectralKnight.cs:32 base (MaxInitialHp == MinInitialHp)
    max_hp = 93
    min_hp_asc = 97       # ToughEnemies (asc 8+) -- SpectralKnight.cs:32
    max_hp_asc = 97

    def _soul_slash_dmg(self) -> int:
        """SpectralKnight.cs:38 `SoulSlashDamage`."""
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _SOUL_SLASH_DMG_ASC, _SOUL_SLASH_DMG)

    def _soul_flame_dmg(self) -> int:
        """SpectralKnight.cs:40 `SoulFlameDamage`."""
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _SOUL_FLAME_DMG_ASC, _SOUL_FLAME_DMG)

    def build_machine(self) -> MonsterMoveStateMachine:
        hex_move = MoveState("HEX", self._hex, Intent(MoveType.DEBUFF))
        soul_slash = MoveState(
            "SOUL_SLASH", self._soul_slash,
            lambda: Intent(MoveType.ATTACK, damage=self._soul_slash_dmg()),
        )
        soul_flame = MoveState(
            "SOUL_FLAME", self._soul_flame,
            lambda: Intent(MoveType.ATTACK, damage=self._soul_flame_dmg(), hits=_SOUL_FLAME_HITS),
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
        self._execute_attack(ctx, self._soul_slash_dmg(), 1)

    def _soul_flame(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._soul_flame_dmg(), _SOUL_FLAME_HITS)


KNIGHTS_ELITE = Encounter(
    id="knights_elite",
    monster_classes=[FlailKnight, SpectralKnight, MagiKnight],
    # KnightsElite.cs:37-45 seats the three knights by name but declares NO
    # `Slots` override, so `Slots.IndexOf` is -1 for all three and the sort
    # is a no-op — the names are carried for fidelity, not for ordering.
    monster_slots=("first", "second", "third"),
)
