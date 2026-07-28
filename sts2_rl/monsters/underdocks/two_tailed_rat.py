from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ..base import Encounter, Intent, Monster, MoveType
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

_SCRATCH_DMG = 8
_DISEASE_BITE_DMG = 6
_SCREECH_FRAIL = 1
_SUMMON_CHANCE = 0.75
_OTHER_WEIGHT_WHEN_SUMMONABLE = 1.0 / 12.0
_BACKUP_LIMIT = 3
_SLOTS = 5


class TwoTailedRat(MachineMonster):
    """Picks randomly (never twice in a row) among SCRATCH (8), DISEASE_BITE
    (6) and SCREECH (Frail 1, then not again for 3 moves). Once a rat has
    acted twice it may CALL_FOR_BACKUP (75% when eligible, once per rat,
    3 summons per fight, 5 slots) to add another rat. The encounter staggers
    the three starting moves (starter_move_idx; -1 = roll randomly, used for
    summoned rats)."""
    name = "Two-Tailed Rat"

    min_hp = 17
    max_hp = 21

    def __init__(
        self,
        hooks: HookSystem,
        rng: random.Random | None = None,
        *,
        starter_move_idx: int = -1,
    ) -> None:
        self._starter_move_idx = starter_move_idx  # read by build_machine
        self.turns_until_summonable = 2
        self.call_for_backup_count = 0
        super().__init__(hooks, rng or random.Random())

    def build_machine(self) -> MonsterMoveStateMachine:
        scratch = MoveState(
            "SCRATCH_MOVE", self._scratch,
            Intent(MoveType.ATTACK, damage=_SCRATCH_DMG),
        )
        bite = MoveState(
            "DISEASE_BITE_MOVE", self._disease_bite,
            Intent(MoveType.ATTACK, damage=_DISEASE_BITE_DMG),
        )
        screech = MoveState(
            "SCREECH_MOVE", self._screech, Intent(MoveType.DEBUFF)
        )
        backup = MoveState(
            "CALL_FOR_BACKUP_MOVE", self._call_for_backup,
            Intent(MoveType.SUMMON),
        )
        rand = RandomBranchState("RAND")
        scratch.follow_up = rand
        bite.follow_up = rand
        screech.follow_up = rand
        backup.follow_up = rand

        def other_weight() -> float:
            return _OTHER_WEIGHT_WHEN_SUMMONABLE if self._can_summon() else 1.0

        def backup_weight() -> float:
            return _SUMMON_CHANCE if self._can_summon() else 0.0

        rand.add_branch(scratch, other_weight, MoveRepeatType.CANNOT_REPEAT)
        rand.add_branch(bite, other_weight, MoveRepeatType.CANNOT_REPEAT)
        rand.add_branch(
            screech, other_weight, MoveRepeatType.CANNOT_REPEAT, cooldown=3
        )
        rand.add_branch(backup, backup_weight, MoveRepeatType.USE_ONLY_ONCE)

        states = [rand, scratch, bite, screech, backup]
        if self._starter_move_idx == -1:
            return MonsterMoveStateMachine(states, rand)
        initial = (scratch, bite, screech)[self._starter_move_idx % 3]
        return MonsterMoveStateMachine(states, initial)

    def _live_rats(self) -> list[TwoTailedRat]:
        combat = self._hooks.combat
        return [
            e for e in combat.enemies
            if isinstance(e, TwoTailedRat) and not e.is_gone
        ]

    def _can_summon(self) -> bool:
        if self.turns_until_summonable > 0:
            return False
        if self.call_for_backup_count >= _BACKUP_LIMIT:
            return False
        live = self._live_rats()
        if len(live) >= _SLOTS:  # no free slot
            return False
        # Never two rats telegraphing a summon at once.
        for rat in live:
            if rat is not self and rat._current_move.id == "CALL_FOR_BACKUP_MOVE":
                return False
        return True

    def _scratch(self, ctx: CombatCtx) -> None:
        self.turns_until_summonable -= 1
        self._execute_attack(ctx, _SCRATCH_DMG, 1)

    def _disease_bite(self, ctx: CombatCtx) -> None:
        self.turns_until_summonable -= 1
        self._execute_attack(ctx, _DISEASE_BITE_DMG, 1)

    def _screech(self, ctx: CombatCtx) -> None:
        self.turns_until_summonable -= 1
        from ...cmds import PowerCmd
        from ...powers import FrailPower
        PowerCmd.apply(ctx.hooks, ctx.player, FrailPower, _SCREECH_FRAIL)

    def _call_for_backup(self, ctx: CombatCtx) -> None:
        from ...cmds import CreatureCmd
        if len(self._live_rats()) < _SLOTS:
            CreatureCmd.add(ctx.hooks, TwoTailedRat(ctx.hooks, self._rng))
        # All rats (including the newcomer) share the summon count.
        rats = self._live_rats()
        new_count = max(r.call_for_backup_count for r in rats) + 1
        for r in rats:
            r.call_for_backup_count = new_count


@dataclass
class TwoTailedRatsEncounter(Encounter):
    """Three rats starting on consecutive moves of scratch/bite/screech
    (mirrors TwoTailedRatsNormal.GenerateMonsters)."""

    monster_classes: list = field(default_factory=list)

    def create_monsters(self, hooks: HookSystem, rng: random.Random, selection_rng=None) -> list[Monster]:
        # Parity (TwoTailedRatsNormal.cs:33): one `base.Rng.NextInt(3)` on the
        # PER-ENCOUNTER Rng staggers the three rats. Legacy keeps the shared-rng
        # draw.
        if selection_rng is not None:
            start = selection_rng.next_int(3)
        else:
            start = rng.randrange(3)
        return [
            TwoTailedRat(hooks, rng, starter_move_idx=(start + i) % 3)
            for i in range(3)
        ]


TWO_TAILED_RATS_NORMAL = TwoTailedRatsEncounter(id="two_tailed_rats_normal")
