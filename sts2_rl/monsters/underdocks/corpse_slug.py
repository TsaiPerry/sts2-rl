from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ..base import Encounter, Intent, Monster, MoveType
from ..state_machine import MachineMonster, MonsterMoveStateMachine, MoveState

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem

_WHIP_SLAP_DMG = 3
_WHIP_SLAP_HITS = 2
_GLOMP_DMG = 8
_GOOP_FRAIL = 2
_RAVENOUS_STR = 4


class CorpseSlug(MachineMonster):
    """WHIP_SLAP → GLOMP → GOOP → loop; the encounter staggers each slug's
    starting move (starter_move_idx, mirroring StarterMoveIdx). Ravenous:
    when a fellow slug dies, this one devours it — stunned for a turn and
    +4 Strength."""

    min_hp = 25
    max_hp = 27

    def __init__(
        self,
        hooks: HookSystem,
        rng: random.Random | None = None,
        *,
        starter_move_idx: int = 0,
    ) -> None:
        self._starter_move_idx = starter_move_idx  # read by build_machine
        super().__init__(hooks, rng or random.Random())
        from ...cmds import PowerCmd
        from ...powers import RavenousPower
        PowerCmd.apply(hooks, self, RavenousPower, _RAVENOUS_STR)

    def build_machine(self) -> MonsterMoveStateMachine:
        whip_slap = MoveState(
            "WHIP_SLAP_MOVE", self._whip_slap,
            Intent(MoveType.ATTACK, damage=_WHIP_SLAP_DMG, hits=_WHIP_SLAP_HITS),
        )
        glomp = MoveState(
            "GLOMP_MOVE", self._glomp, Intent(MoveType.ATTACK, damage=_GLOMP_DMG)
        )
        goop = MoveState("GOOP_MOVE", self._goop, Intent(MoveType.DEBUFF))
        whip_slap.follow_up = glomp
        glomp.follow_up = goop
        goop.follow_up = whip_slap
        initial = (whip_slap, glomp, goop)[self._starter_move_idx % 3]
        return MonsterMoveStateMachine([whip_slap, glomp, goop], initial)

    def _whip_slap(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _WHIP_SLAP_DMG, _WHIP_SLAP_HITS)

    def _glomp(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _GLOMP_DMG, 1)

    def _goop(self, ctx: CombatCtx) -> None:
        from ...cmds import PowerCmd
        from ...powers import FrailPower
        PowerCmd.apply(ctx.hooks, ctx.player, FrailPower, _GOOP_FRAIL)


@dataclass
class CorpseSlugsEncounter(Encounter):
    """N Corpse Slugs starting on consecutive moves of the loop (mirrors
    EnsureCorpseSlugsStartWithDifferentMoves)."""

    monster_classes: list = field(default_factory=list)
    count: int = 3

    def create_monsters(self, hooks: HookSystem, rng: random.Random) -> list[Monster]:
        start = rng.randrange(3)
        return [
            CorpseSlug(hooks, rng, starter_move_idx=(start + i) % 3)
            for i in range(self.count)
        ]


CORPSE_SLUGS_NORMAL = CorpseSlugsEncounter(id="corpse_slugs_normal", count=3)
CORPSE_SLUGS_WEAK = CorpseSlugsEncounter(id="corpse_slugs_weak", count=2)
