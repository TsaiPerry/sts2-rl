from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ...actmap import AscensionLevel
from ..base import Encounter, Intent, MoveType, asc_value
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

_SOUL_BURN_DMG = 29        # SoulNexus.cs:26 base
_SOUL_BURN_DMG_ASC = 31    # DeadlyEnemies (asc 9+)
_MAELSTROM_DMG = 6         # SoulNexus.cs:28 base
_MAELSTROM_DMG_ASC = 7     # DeadlyEnemies
# SoulNexus.cs:30 MaelstromRepeat: GetValueIfAscension(DeadlyEnemies, 4, 4) --
# both bounds are 4, a no-op; not ported (no behaviour changes at any
# ascension), left as the plain constant below.
_MAELSTROM_HITS = 4
_DRAIN_DMG = 18            # SoulNexus.cs:32 base
_DRAIN_DMG_ASC = 19        # DeadlyEnemies
_DRAIN_VULN = 2
_DRAIN_WEAK = 2


class SoulNexus(MachineMonster):
    """Opens with Soul Burn (29), then each turn randomly picks one of Soul Burn
    (29), Maelstrom (6×4) or Drain Life (18 + Vulnerable 2 + Weak 2) that it did
    not just use.

    Source: SoulNexus.cs (non-ascension values)."""
    name = "Soul Nexus"

    min_hp = 234          # SoulNexus.cs:22 base (MaxInitialHp == MinInitialHp)
    max_hp = 234
    min_hp_asc = 254       # ToughEnemies (asc 8+) -- SoulNexus.cs:22
    max_hp_asc = 254

    def _soul_burn_dmg(self) -> int:
        """SoulNexus.cs:26 `SoulBurnDamage`."""
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _SOUL_BURN_DMG_ASC, _SOUL_BURN_DMG)

    def _maelstrom_dmg(self) -> int:
        """SoulNexus.cs:28 `MaelstromDamage`."""
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _MAELSTROM_DMG_ASC, _MAELSTROM_DMG)

    def _drain_dmg(self) -> int:
        """SoulNexus.cs:32 `DrainLifeDamage`."""
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _DRAIN_DMG_ASC, _DRAIN_DMG)

    def build_machine(self) -> MonsterMoveStateMachine:
        soul_burn = MoveState(
            "SOUL_BURN_MOVE", self._soul_burn,
            lambda: Intent(MoveType.ATTACK, damage=self._soul_burn_dmg()),
        )
        maelstrom = MoveState(
            "MAELSTROM_MOVE", self._maelstrom,
            lambda: Intent(MoveType.ATTACK, damage=self._maelstrom_dmg(), hits=_MAELSTROM_HITS),
        )
        drain = MoveState(
            "DRAIN_LIFE_MOVE", self._drain,
            lambda: Intent(MoveType.ATTACK, damage=self._drain_dmg(), also=(MoveType.DEBUFF_STRONG,)),
        )
        branch = RandomBranchState("RAND")
        for move in (soul_burn, maelstrom, drain):
            move.follow_up = branch
            branch.add_branch(move, weight=1.0, repeat_type=MoveRepeatType.CANNOT_REPEAT)
        return MonsterMoveStateMachine([soul_burn, maelstrom, drain, branch], soul_burn)

    def _soul_burn(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._soul_burn_dmg(), 1)

    def _maelstrom(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._maelstrom_dmg(), _MAELSTROM_HITS)

    def _drain(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._drain_dmg(), 1)
        from ...cmds import PowerCmd
        from ...powers import VulnerablePower, WeakPower
        PowerCmd.apply(ctx.hooks, ctx.player, VulnerablePower, _DRAIN_VULN)
        PowerCmd.apply(ctx.hooks, ctx.player, WeakPower, _DRAIN_WEAK)


SOUL_NEXUS_ELITE = Encounter(
    id="soul_nexus_elite",
    monster_classes=[SoulNexus],
)
