"""Chomper (Hive). Sources: Chomper.cs, ChompersNormal.cs."""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ..base import Encounter, Intent, Monster, MoveType
from ..state_machine import MachineMonster, MonsterMoveStateMachine, MoveState

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem

_CLAMP_DMG = 8
_CLAMP_HITS = 2
_SCREECH_DAZED = 3
_ARTIFACT = 2


class Chomper(MachineMonster):
    """Alternates CLAMP (8x2) and SCREECH (3 Dazed into the discard pile);
    spawns with Artifact 2. The second Chomper in the pair screams first."""

    min_hp = 60
    max_hp = 64

    def __init__(
        self,
        hooks: HookSystem,
        rng: random.Random | None = None,
        scream_first: bool = False,
    ) -> None:
        self.scream_first = scream_first
        super().__init__(hooks, rng or random.Random())
        from ...cmds import PowerCmd
        from ...powers import ArtifactPower
        PowerCmd.apply(hooks, self, ArtifactPower, _ARTIFACT)

    def build_machine(self) -> MonsterMoveStateMachine:
        clamp = MoveState(
            "CLAMP_MOVE", self._clamp,
            Intent(MoveType.ATTACK, damage=_CLAMP_DMG, hits=_CLAMP_HITS),
        )
        screech = MoveState(
            "SCREECH_MOVE", self._screech, Intent(MoveType.STATUS_CARD)
        )
        clamp.follow_up = screech
        screech.follow_up = clamp
        initial = screech if self.scream_first else clamp
        return MonsterMoveStateMachine([clamp, screech], initial)

    def _clamp(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _CLAMP_DMG, _CLAMP_HITS)

    def _screech(self, ctx: CombatCtx) -> None:
        from ...cards import DazedCard
        from ...cmds import CardPileCmd
        for _ in range(_SCREECH_DAZED):
            CardPileCmd.add_to_discard(ctx.hooks, ctx.player, DazedCard())


@dataclass
class ChompersEncounter(Encounter):
    """Two Chompers; the second one opens with SCREECH (ScreamFirst)."""

    monster_classes: list = field(default_factory=list)

    def create_monsters(self, hooks: HookSystem, rng: random.Random) -> list[Monster]:
        return [Chomper(hooks, rng), Chomper(hooks, rng, scream_first=True)]


CHOMPERS_NORMAL = ChompersEncounter(id="chompers_normal")
