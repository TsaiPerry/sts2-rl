from __future__ import annotations

import random
from dataclasses import dataclass, field
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
    from ...hooks import HookSystem

_SPIKE_SPIT_DMG = 3       # Toadpole.cs:49 base
_SPIKE_SPIT_DMG_ASC = 4   # DeadlyEnemies
_SPIKE_SPIT_HITS = 3
_WHIRL_DMG = 7            # Toadpole.cs:53 base
_WHIRL_DMG_ASC = 8        # DeadlyEnemies
_SPIKEN_THORNS = 2


class Toadpole(MachineMonster):
    """Cycle WHIRL (7) → SPIKEN (+2 Thorns) → SPIKE_SPIT (spend the Thorns,
    then 3×3). The front toad starts at SPIKEN, the back toad at WHIRL
    (is_front, mirroring Toadpole.IsFront)."""

    min_hp = 21
    max_hp = 25
    min_hp_asc = 22   # Toadpole.cs:32 -- ToughEnemies
    max_hp_asc = 26   # Toadpole.cs:34 -- ToughEnemies

    def _spike_spit_dmg(self) -> int:
        """Toadpole.cs:49 `SpikeSpitDamage` -- read at both the telegraphed
        Intent and the executed attack."""
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _SPIKE_SPIT_DMG_ASC, _SPIKE_SPIT_DMG)

    def _whirl_dmg(self) -> int:
        """Toadpole.cs:53 `WhirlDamage`."""
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _WHIRL_DMG_ASC, _WHIRL_DMG)

    def __init__(
        self,
        hooks: HookSystem,
        rng: random.Random | None = None,
        *,
        is_front: bool = False,
    ) -> None:
        self.is_front = is_front  # read by build_machine
        super().__init__(hooks, rng or random.Random())

    def build_machine(self) -> MonsterMoveStateMachine:
        spike_spit = MoveState(
            "SPIKE_SPIT_MOVE", self._spike_spit,
            lambda: Intent(MoveType.ATTACK, damage=self._spike_spit_dmg(),
                            hits=_SPIKE_SPIT_HITS),
        )
        whirl = MoveState(
            "WHIRL_MOVE", self._whirl, lambda: Intent(MoveType.ATTACK, damage=self._whirl_dmg())
        )
        spiken = MoveState("SPIKEN_MOVE", self._spiken, Intent(MoveType.BUFF))
        init = ConditionalBranchState("INIT_MOVE")
        whirl.follow_up = spiken
        spiken.follow_up = spike_spit
        spike_spit.follow_up = whirl
        init.add_state(whirl, lambda: not self.is_front)
        init.add_state(spiken, lambda: self.is_front)
        return MonsterMoveStateMachine([init, spiken, spike_spit, whirl], init)

    def _spike_spit(self, ctx: CombatCtx) -> None:
        # The toad spits its spikes: Thorns -2 (removing the Spiken stacks)
        # before the hits land.
        from ...cmds import PowerCmd
        from ...powers import ThornsPower
        PowerCmd.apply(ctx.hooks, self, ThornsPower, -_SPIKEN_THORNS)
        self._execute_attack(ctx, self._spike_spit_dmg(), _SPIKE_SPIT_HITS)

    def _whirl(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._whirl_dmg(), 1)

    def _spiken(self, ctx: CombatCtx) -> None:
        from ...cmds import PowerCmd
        from ...powers import ThornsPower
        PowerCmd.apply(ctx.hooks, self, ThornsPower, _SPIKEN_THORNS)


@dataclass
class ToadpolesEncounter(Encounter):
    """Two Toadpoles offset by one move: the front one opens with SPIKEN, the
    back one with WHIRL (mirrors ToadpolesWeak.GenerateMonsters)."""

    monster_classes: list = field(default_factory=list)

    def create_monsters(self, hooks: HookSystem, rng: random.Random, selection_rng=None) -> list[Monster]:
        return [
            Toadpole(hooks, rng, is_front=True),
            Toadpole(hooks, rng, is_front=False),
        ]


TOADPOLES_WEAK = ToadpolesEncounter(id="toadpoles_weak")
