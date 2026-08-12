from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ...actmap import AscensionLevel
from ..base import Encounter, Intent, MoveType, asc_value
from ..state_machine import MachineMonster, MonsterMoveStateMachine, MoveState

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem


class _Cultist(MachineMonster):
    """Shared cultist pattern: INCANTATION (gain Ritual) once, then DARK_STRIKE
    forever."""

    dark_strike_dmg: int
    incantation_amt: int

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())

    def _dark_strike_dmg(self) -> int:
        """Per-subclass DeadlyEnemies damage read; default no-op (base ==
        asc value) unless overridden. Called at both the telegraphed Intent
        (build_machine) and the executed attack (_dark_strike)."""
        return self.dark_strike_dmg

    def build_machine(self) -> MonsterMoveStateMachine:
        incantation = MoveState(
            "INCANTATION_MOVE", self._incantation, Intent(MoveType.BUFF)
        )
        dark_strike = MoveState(
            "DARK_STRIKE_MOVE", self._dark_strike,
            lambda: Intent(MoveType.ATTACK, damage=self._dark_strike_dmg()),
        )
        incantation.follow_up = dark_strike
        dark_strike.follow_up = dark_strike
        return MonsterMoveStateMachine([incantation, dark_strike], incantation)

    def _incantation_amt(self) -> int:
        """Per-subclass DeadlyEnemies Ritual-gain read; default no-op unless
        overridden."""
        return self.incantation_amt

    def _incantation(self, ctx: CombatCtx) -> None:
        from ...cmds import PowerCmd
        from ...powers import RitualPower
        PowerCmd.apply(ctx.hooks, self, RitualPower, self._incantation_amt(), applier=self)

    def _dark_strike(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._dark_strike_dmg(), 1)


class CalcifiedCultist(_Cultist):
    """Hits harder, smaller Ritual."""
    name = "Calcified Cultist"

    min_hp = 38
    max_hp = 41
    # CalcifiedCultist.cs:28-30 -- MinInitialHp/MaxInitialHp read
    # GetValueIfAscension(ToughEnemies, 39/42, 38/41).
    min_hp_asc = 39
    max_hp_asc = 42
    dark_strike_dmg = 9    # CalcifiedCultist.cs:32 base
    _dark_strike_dmg_asc = 11  # DeadlyEnemies (asc 9+)
    # CalcifiedCultist.cs:34 `IncantationAmount` is a fixed `2`, not asc-gated.
    incantation_amt = 2

    def _dark_strike_dmg(self) -> int:
        """CalcifiedCultist.cs:32 `DarkStrikeDamage` -- re-read at both the
        telegraphed Intent and the executed attack."""
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          self._dark_strike_dmg_asc, self.dark_strike_dmg)


class DampCultist(_Cultist):
    """Hits for almost nothing, but Ritual 5 snowballs fast."""
    name = "Damp Cultist"

    min_hp = 51              # DampCultist.cs:28
    max_hp = 53               # DampCultist.cs:30
    min_hp_asc = 52           # DampCultist.cs:28 -- ToughEnemies
    max_hp_asc = 54           # DampCultist.cs:30 -- ToughEnemies
    dark_strike_dmg = 1       # DampCultist.cs:32 base
    _dark_strike_dmg_asc = 3  # DeadlyEnemies
    incantation_amt = 5       # DampCultist.cs:34 base
    _incantation_amt_asc = 6  # DeadlyEnemies

    def _dark_strike_dmg(self) -> int:
        """DampCultist.cs:32 `DarkStrikeDamage` -- re-read at both the
        telegraphed Intent and the executed attack."""
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          self._dark_strike_dmg_asc, self.dark_strike_dmg)

    def _incantation_amt(self) -> int:
        """DampCultist.cs:34 `IncantationAmount`."""
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          self._incantation_amt_asc, self.incantation_amt)


CULTISTS_NORMAL = Encounter(
    id="cultists_normal",
    monster_classes=[CalcifiedCultist, DampCultist],
)
