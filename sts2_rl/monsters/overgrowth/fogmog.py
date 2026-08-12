from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ...actmap import AscensionLevel
from ..base import Encounter, Intent, Monster, MoveType, asc_value
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

_SWIPE_DMG = 8            # Fogmog.cs:32 SwipeDamage base
_SWIPE_DMG_ASC = 9        # DeadlyEnemies (asc 9+)
_SWIPE_STR = 1
_HEADBUTT_DMG = 14        # Fogmog.cs:34 HeadbuttDamage base
_HEADBUTT_DMG_ASC = 16    # DeadlyEnemies (asc 9+)


class EyeWithTeeth(Monster):
    """Summoned illusion; adds 3 Dazed cards each turn. Cannot truly die —
    IllusionPower revives it to full HP on its next turn."""
    name = "Eye with Teeth"
    min_hp = 6
    max_hp = 6

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())
        from ...cmds import PowerCmd
        from ...powers import IllusionPower
        PowerCmd.apply(hooks, self, IllusionPower, 1)

    @property
    def _illusion(self):
        return self.powers.get("illusion")

    @property
    def current_intent(self) -> Intent:
        illusion = self._illusion
        if illusion is not None and illusion.is_reviving:
            return Intent(MoveType.HEAL)  # revive turn
        return Intent(MoveType.STATUS_CARD, status_count=3)  # DISTRACT: 3 Dazed cards

    def take_turn(self, ctx: CombatCtx) -> None:
        illusion = self._illusion
        if illusion is not None and illusion.is_reviving:
            illusion.revive()
            return
        from ...cards import DazedCard
        from ...cmds import CardPileCmd
        for _ in range(3):
            CardPileCmd.add_to_discard(ctx.hooks, ctx.player, DazedCard())


class Fogmog(MachineMonster):
    """ILLUSION (summon Eye With Teeth) → SWIPE → branch: 40% SWIPE_RANDOM /
    60% HEADBUTT (each weight-zeroed if it was the previous move); the random
    SWIPE is always followed by HEADBUTT, and HEADBUTT returns to SWIPE, which
    branches again. A faithful port of the source's move state machine."""
    min_hp = 74           # Fogmog.cs:28-30
    max_hp = 74
    min_hp_asc = 78        # ToughEnemies (asc 8+); MaxInitialHp = MinInitialHp
    max_hp_asc = 78

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())

    def _swipe_dmg(self) -> int:
        """Fogmog.cs:32 `SwipeDamage` -- a C# PROPERTY re-read at both the
        telegraphed Intent (:42-43) and the executed attack (:72), so both
        sites call this rather than a value cached at construction."""
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _SWIPE_DMG_ASC, _SWIPE_DMG)

    def _headbutt_dmg(self) -> int:
        """Fogmog.cs:34 `HeadbuttDamage` -- same re-read pattern (:44, :81)."""
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _HEADBUTT_DMG_ASC, _HEADBUTT_DMG)

    def build_machine(self) -> MonsterMoveStateMachine:
        swipe_intent = lambda: Intent(
            MoveType.ATTACK, damage=self._swipe_dmg(), also=(MoveType.BUFF,)
        )
        illusion = MoveState("ILLUSION_MOVE", self._illusion_move, Intent(MoveType.SUMMON))
        swipe = MoveState("SWIPE_MOVE", self._swipe_move, swipe_intent)
        swipe_random = MoveState("SWIPE_RANDOM_MOVE", self._swipe_move, swipe_intent)
        headbutt = MoveState(
            "HEADBUTT_MOVE", self._headbutt_move,
            lambda: Intent(MoveType.ATTACK, damage=self._headbutt_dmg()),
        )
        branch = RandomBranchState("BRANCH")
        branch.add_branch(swipe_random, weight=0.4, repeat_type=MoveRepeatType.CANNOT_REPEAT)
        branch.add_branch(headbutt, weight=0.6, repeat_type=MoveRepeatType.CANNOT_REPEAT)

        illusion.follow_up = swipe
        swipe.follow_up = branch
        swipe_random.follow_up = headbutt
        headbutt.follow_up = swipe
        return MonsterMoveStateMachine(
            [illusion, swipe, swipe_random, branch, headbutt], illusion
        )

    def _illusion_move(self, ctx: CombatCtx) -> None:
        from ...cmds import CreatureCmd
        # Fogmog.cs:66 — `CreatureCmd.Add<EyeWithTeeth>(CombatState,
        # "illusion")`: the slot is hard-coded, and its index (0) puts the
        # summon ahead of the Fogmog when `add` re-sorts the enemy list.
        CreatureCmd.add(
            ctx.hooks, EyeWithTeeth(ctx.hooks, self._rng), slot_name="illusion",
        )

    def _swipe_move(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._swipe_dmg(), 1)
        from ...cmds import PowerCmd
        from ...powers import StrengthPower
        PowerCmd.apply(ctx.hooks, self, StrengthPower, _SWIPE_STR)

    def _headbutt_move(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._headbutt_dmg(), 1)


FOGMOG_NORMAL = Encounter(
    id="fogmog_normal",
    monster_classes=[Fogmog],
    # FogmogNormal.cs:15,25-28 — the Fogmog is seated in "fogmog" (index 1)
    # and ILLUSION_MOVE's EyeWithTeeth takes "illusion" (index 0), so the
    # turn-1 summon re-sorts AHEAD of the Fogmog.
    slots=("illusion", "fogmog"),
    monster_slots=("fogmog",),
)
