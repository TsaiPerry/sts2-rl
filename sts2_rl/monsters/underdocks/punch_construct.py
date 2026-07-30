from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ..base import Encounter, Intent, MoveType
from ..state_machine import MachineMonster, MonsterMoveStateMachine, MoveState

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem

_READY_BLOCK = 10
_STRONG_PUNCH_DMG = 14
_FAST_PUNCH_DMG = 5
_FAST_PUNCH_HITS = 2
_FAST_PUNCH_FRAIL = 1


class PunchConstruct(MachineMonster):
    """READY (10 block) → FAST_PUNCH (5×2 + Frail 1) → STRONG_PUNCH (14) →
    loop. Starts with Artifact 1. starts_with_fast_punch mirrors
    StartsWithFastPunch (used by the Punch-Off event, not the normal fight)."""
    name = "Punch Construct"

    min_hp = 55
    max_hp = 55

    def __init__(
        self,
        hooks: HookSystem,
        rng: random.Random | None = None,
        *,
        starts_with_fast_punch: bool = False,
    ) -> None:
        self._starts_with_fast_punch = starts_with_fast_punch  # read by build_machine
        # `PunchConstruct.StartingHpReduction` (PunchConstruct.cs:60-69) — a
        # FIELD the encounter sets on the model, spent later by
        # AfterAddedToRoom. Keeping it a field rather than applying it at
        # construction is what makes the lifecycle right: the reduction is
        # taken off the CURRENT HP the Niche roll has already assigned, where
        # applying it in create_monsters put it before that roll, which then
        # overwrote it (`_roll_parity_hp` sets hp = max_hp = rolled).
        self.starting_hp_reduction = 0
        super().__init__(hooks, rng or random.Random())
        from ...cmds import PowerCmd
        from ...powers import ArtifactPower
        PowerCmd.apply(hooks, self, ArtifactPower, 1)

    def adjust_hp_after_added(self, teammates) -> None:
        """`PunchConstruct.AfterAddedToRoom` (PunchConstruct.cs:71-79):

            base.Creature.SetCurrentHpInternal(
                Math.Max(1, base.Creature.CurrentHp - StartingHpReduction))

        CURRENT HP only — MaxHp is untouched and stays at the model's flat 55.
        The Artifact 1 the same override applies is a pool-wide deliberate
        divergence (SHARED-FINDINGS section 2) and stays in __init__.
        """
        if self.starting_hp_reduction > 0:
            self.hp = max(1, self.hp - self.starting_hp_reduction)

    def build_machine(self) -> MonsterMoveStateMachine:
        ready = MoveState("READY_MOVE", self._ready, Intent(MoveType.DEFEND))
        strong_punch = MoveState(
            "STRONG_PUNCH_MOVE", self._strong_punch,
            Intent(MoveType.ATTACK, damage=_STRONG_PUNCH_DMG),
        )
        fast_punch = MoveState(
            "FAST_PUNCH_MOVE", self._fast_punch,
            Intent(MoveType.ATTACK, damage=_FAST_PUNCH_DMG, hits=_FAST_PUNCH_HITS,
                   also=(MoveType.DEBUFF,)),
        )
        ready.follow_up = fast_punch
        fast_punch.follow_up = strong_punch
        strong_punch.follow_up = ready
        initial = fast_punch if self._starts_with_fast_punch else ready
        return MonsterMoveStateMachine([ready, fast_punch, strong_punch], initial)

    def _ready(self, ctx: CombatCtx) -> None:
        from ...cmds import BlockCmd
        BlockCmd.apply(ctx.hooks, self, _READY_BLOCK)

    def _strong_punch(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _STRONG_PUNCH_DMG, 1)

    def _fast_punch(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _FAST_PUNCH_DMG, _FAST_PUNCH_HITS)
        from ...cmds import PowerCmd
        from ...powers import FrailPower
        PowerCmd.apply(ctx.hooks, ctx.player, FrailPower, _FAST_PUNCH_FRAIL)


PUNCH_CONSTRUCT_NORMAL = Encounter(
    id="punch_construct_normal",
    monster_classes=[PunchConstruct],
)
