from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ...actmap import AscensionLevel
from ..base import Encounter, Intent, MoveType, asc_value
from ..state_machine import MachineMonster, MonsterMoveStateMachine, MoveState

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem

_SCRUTINY_DMG = 16       # OwlMagistrate.cs:41 base
_SCRUTINY_DMG_ASC = 17   # DeadlyEnemies
# PeckAssaultDamage (OwlMagistrate.cs:43) reads
# GetValueIfAscension(DeadlyEnemies, 4, 4) -- both branches are 4, a no-op;
# ported as a comment only, no code change.
_PECK_DMG = 4
_PECK_HITS = 6
_VERDICT_DMG = 33        # OwlMagistrate.cs:39 base
_VERDICT_DMG_ASC = 36    # DeadlyEnemies
_VERDICT_VULN = 4


class OwlMagistrate(MachineMonster):
    """Magistrate Scrutiny (16) → Peck Assault (4×6) → Judicial Flight (gain
    Soar: take half damage) → Verdict (33 + Vulnerable 4, ends the flight) →
    loop.

    Source: OwlMagistrate.cs (non-ascension values)."""
    name = "Owl Magistrate"

    min_hp = 231
    max_hp = 231
    min_hp_asc = 247   # OwlMagistrate.cs:35 -- ToughEnemies (MaxInitialHp == MinInitialHp)
    max_hp_asc = 247

    def _scrutiny_dmg(self) -> int:
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _SCRUTINY_DMG_ASC, _SCRUTINY_DMG)

    def _verdict_dmg(self) -> int:
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _VERDICT_DMG_ASC, _VERDICT_DMG)

    def build_machine(self) -> MonsterMoveStateMachine:
        scrutiny = MoveState(
            "MAGISTRATE_SCRUTINY", self._scrutiny,
            lambda: Intent(MoveType.ATTACK, damage=self._scrutiny_dmg()),
        )
        peck = MoveState(
            "PECK_ASSAULT", self._peck,
            Intent(MoveType.ATTACK, damage=_PECK_DMG, hits=_PECK_HITS),
        )
        flight = MoveState("JUDICIAL_FLIGHT", self._flight, Intent(MoveType.BUFF))
        verdict = MoveState(
            "VERDICT", self._verdict,
            lambda: Intent(MoveType.ATTACK, damage=self._verdict_dmg(), also=(MoveType.DEBUFF,)),
        )
        scrutiny.follow_up = peck
        peck.follow_up = flight
        flight.follow_up = verdict
        verdict.follow_up = scrutiny
        return MonsterMoveStateMachine([scrutiny, peck, flight, verdict], scrutiny)

    def _scrutiny(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._scrutiny_dmg(), 1)

    def _peck(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _PECK_DMG, _PECK_HITS)

    def _flight(self, ctx: CombatCtx) -> None:
        from ...cmds import PowerCmd
        from ...powers import SoarPower
        PowerCmd.apply(ctx.hooks, self, SoarPower, 1)

    def _verdict(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._verdict_dmg(), 1)
        from ...cmds import PowerCmd
        from ...powers import VulnerablePower
        PowerCmd.apply(ctx.hooks, ctx.player, VulnerablePower, _VERDICT_VULN)
        PowerCmd.remove(ctx.hooks, self, "soar")


OWL_MAGISTRATE_NORMAL = Encounter(
    id="owl_magistrate_normal",
    monster_classes=[OwlMagistrate],
)
