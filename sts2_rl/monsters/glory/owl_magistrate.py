from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ..base import Encounter, Intent, MoveType
from ..state_machine import MachineMonster, MonsterMoveStateMachine, MoveState

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem

_SCRUTINY_DMG = 16
_PECK_DMG = 4
_PECK_HITS = 6
_VERDICT_DMG = 33
_VERDICT_VULN = 4


class OwlMagistrate(MachineMonster):
    """Magistrate Scrutiny (16) → Peck Assault (4×6) → Judicial Flight (gain
    Soar: take half damage) → Verdict (33 + Vulnerable 4, ends the flight) →
    loop.

    Source: OwlMagistrate.cs (non-ascension values)."""

    min_hp = 231
    max_hp = 231

    def build_machine(self) -> MonsterMoveStateMachine:
        scrutiny = MoveState(
            "MAGISTRATE_SCRUTINY", self._scrutiny,
            Intent(MoveType.ATTACK, damage=_SCRUTINY_DMG),
        )
        peck = MoveState(
            "PECK_ASSAULT", self._peck,
            Intent(MoveType.ATTACK, damage=_PECK_DMG, hits=_PECK_HITS),
        )
        flight = MoveState("JUDICIAL_FLIGHT", self._flight, Intent(MoveType.BUFF))
        verdict = MoveState(
            "VERDICT", self._verdict,
            Intent(MoveType.ATTACK, damage=_VERDICT_DMG, also=(MoveType.DEBUFF,)),
        )
        scrutiny.follow_up = peck
        peck.follow_up = flight
        flight.follow_up = verdict
        verdict.follow_up = scrutiny
        return MonsterMoveStateMachine([scrutiny, peck, flight, verdict], scrutiny)

    def _scrutiny(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _SCRUTINY_DMG, 1)

    def _peck(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _PECK_DMG, _PECK_HITS)

    def _flight(self, ctx: CombatCtx) -> None:
        from ...cmds import PowerCmd
        from ...powers import SoarPower
        PowerCmd.apply(ctx.hooks, self, SoarPower, 1)

    def _verdict(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _VERDICT_DMG, 1)
        from ...cmds import PowerCmd
        from ...powers import VulnerablePower
        PowerCmd.apply(ctx.hooks, ctx.player, VulnerablePower, _VERDICT_VULN)
        PowerCmd.remove(ctx.hooks, self, "soar")


OWL_MAGISTRATE_NORMAL = Encounter(
    id="owl_magistrate_normal",
    monster_classes=[OwlMagistrate],
)
