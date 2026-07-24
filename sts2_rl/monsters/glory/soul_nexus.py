from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ..base import Encounter, Intent, MoveType
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

_SOUL_BURN_DMG = 29
_MAELSTROM_DMG = 6
_MAELSTROM_HITS = 4
_DRAIN_DMG = 18
_DRAIN_VULN = 2
_DRAIN_WEAK = 2


class SoulNexus(MachineMonster):
    """Opens with Soul Burn (29), then each turn randomly picks one of Soul Burn
    (29), Maelstrom (6×4) or Drain Life (18 + Vulnerable 2 + Weak 2) that it did
    not just use.

    Source: SoulNexus.cs (non-ascension values)."""
    name = "Soul Nexus"

    min_hp = 234
    max_hp = 234

    def build_machine(self) -> MonsterMoveStateMachine:
        soul_burn = MoveState(
            "SOUL_BURN_MOVE", self._soul_burn,
            Intent(MoveType.ATTACK, damage=_SOUL_BURN_DMG),
        )
        maelstrom = MoveState(
            "MAELSTROM_MOVE", self._maelstrom,
            Intent(MoveType.ATTACK, damage=_MAELSTROM_DMG, hits=_MAELSTROM_HITS),
        )
        drain = MoveState(
            "DRAIN_LIFE_MOVE", self._drain,
            Intent(MoveType.ATTACK, damage=_DRAIN_DMG, also=(MoveType.DEBUFF_STRONG,)),
        )
        branch = RandomBranchState("RAND")
        for move in (soul_burn, maelstrom, drain):
            move.follow_up = branch
            branch.add_branch(move, weight=1.0, repeat_type=MoveRepeatType.CANNOT_REPEAT)
        return MonsterMoveStateMachine([soul_burn, maelstrom, drain, branch], soul_burn)

    def _soul_burn(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _SOUL_BURN_DMG, 1)

    def _maelstrom(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _MAELSTROM_DMG, _MAELSTROM_HITS)

    def _drain(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _DRAIN_DMG, 1)
        from ...cmds import PowerCmd
        from ...powers import VulnerablePower, WeakPower
        PowerCmd.apply(ctx.hooks, ctx.player, VulnerablePower, _DRAIN_VULN)
        PowerCmd.apply(ctx.hooks, ctx.player, WeakPower, _DRAIN_WEAK)


SOUL_NEXUS_ELITE = Encounter(
    id="soul_nexus_elite",
    monster_classes=[SoulNexus],
)
