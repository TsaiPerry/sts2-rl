"""Bowlbug workers (Hive).

Sources: BowlbugRock.cs, BowlbugEgg.cs, BowlbugSilk.cs, BowlbugNectar.cs,
BowlbugsWeak.cs, BowlbugsNormal.cs.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ..base import Encounter, Intent, Monster, MoveType
from ..state_machine import (
    ConditionalBranchState,
    MachineMonster,
    MonsterMoveStateMachine,
    MoveState,
)

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem

_HEADBUTT_DMG = 15
_EGG_BITE_DMG = 7
_EGG_BLOCK = 7
_SILK_THRASH_DMG = 4
_SILK_THRASH_HITS = 2
_SILK_WEAK = 1
_NECTAR_THRASH_DMG = 3
_NECTAR_STR = 15


class BowlbugRock(MachineMonster):
    """HEADBUTT (15) every turn — but Imbalanced: a fully blocked headbutt
    throws it off balance and it spends the next turn dizzy."""

    min_hp = 45
    max_hp = 48

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        self.is_off_balance = False
        super().__init__(hooks, rng or random.Random())
        from ...cmds import PowerCmd
        from ...powers import ImbalancedPower
        PowerCmd.apply(hooks, self, ImbalancedPower, 1)

    def build_machine(self) -> MonsterMoveStateMachine:
        headbutt = MoveState(
            "HEADBUTT_MOVE", self._headbutt,
            Intent(MoveType.ATTACK, damage=_HEADBUTT_DMG),
        )
        dizzy = MoveState("DIZZY_MOVE", self._dizzy, Intent(MoveType.STUN))
        post = ConditionalBranchState("POST_HEADBUTT")
        post.add_state(dizzy, lambda: self.is_off_balance)
        post.add_state(headbutt, lambda: not self.is_off_balance)
        headbutt.follow_up = post
        dizzy.follow_up = headbutt
        return MonsterMoveStateMachine([dizzy, post, headbutt], headbutt)

    def _headbutt(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _HEADBUTT_DMG, 1)

    def _dizzy(self, ctx: CombatCtx) -> None:
        self.is_off_balance = False


class BowlbugEgg(MachineMonster):
    """BITE (7) then gain 7 block, every turn."""

    min_hp = 21
    max_hp = 22

    def build_machine(self) -> MonsterMoveStateMachine:
        bite = MoveState(
            "BITE_MOVE", self._bite,
            Intent(MoveType.ATTACK, damage=_EGG_BITE_DMG, also=(MoveType.DEFEND,)),
        )
        bite.follow_up = bite
        return MonsterMoveStateMachine([bite], bite)

    def _bite(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _EGG_BITE_DMG, 1)
        from ...cmds import BlockCmd
        BlockCmd.apply(ctx.hooks, self, _EGG_BLOCK)


class BowlbugSilk(MachineMonster):
    """Opens with TOXIC_SPIT (Weak 1), then alternates THRASH (4x2) and SPIT."""

    min_hp = 40
    max_hp = 43

    def build_machine(self) -> MonsterMoveStateMachine:
        thrash = MoveState(
            "THRASH_MOVE", self._thrash,
            Intent(MoveType.ATTACK, damage=_SILK_THRASH_DMG, hits=_SILK_THRASH_HITS),
        )
        spit = MoveState("TOXIC_SPIT_MOVE", self._spit, Intent(MoveType.DEBUFF))
        thrash.follow_up = spit
        spit.follow_up = thrash
        return MonsterMoveStateMachine([thrash, spit], spit)

    def _thrash(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _SILK_THRASH_DMG, _SILK_THRASH_HITS)

    def _spit(self, ctx: CombatCtx) -> None:
        from ...cmds import PowerCmd
        from ...powers import WeakPower
        PowerCmd.apply(ctx.hooks, ctx.player, WeakPower, _SILK_WEAK, applier=self)


class BowlbugNectar(MachineMonster):
    """THRASH (3), BUFF (+15 Strength), then THRASH forever."""

    min_hp = 35
    max_hp = 38

    def build_machine(self) -> MonsterMoveStateMachine:
        thrash = MoveState(
            "THRASH_MOVE", self._thrash,
            Intent(MoveType.ATTACK, damage=_NECTAR_THRASH_DMG),
        )
        buff = MoveState("BUFF_MOVE", self._buff, Intent(MoveType.BUFF))
        thrash2 = MoveState(
            "THRASH2_MOVE", self._thrash,
            Intent(MoveType.ATTACK, damage=_NECTAR_THRASH_DMG),
        )
        thrash.follow_up = buff
        buff.follow_up = thrash2
        thrash2.follow_up = thrash2
        return MonsterMoveStateMachine([buff, thrash2, thrash], thrash)

    def _thrash(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _NECTAR_THRASH_DMG, 1)

    def _buff(self, ctx: CombatCtx) -> None:
        from ...cmds import PowerCmd
        from ...powers import StrengthPower
        PowerCmd.apply(ctx.hooks, self, StrengthPower, _NECTAR_STR)


@dataclass
class BowlbugsWeakEncounter(Encounter):
    """A Bowlbug Rock plus one random worker from Egg / Nectar."""

    monster_classes: list = field(default_factory=list)

    def create_monsters(self, hooks: HookSystem, rng: random.Random) -> list[Monster]:
        worker_cls = rng.choice([BowlbugEgg, BowlbugNectar])
        return [BowlbugRock(hooks, rng), worker_cls(hooks, rng)]


@dataclass
class BowlbugsNormalEncounter(Encounter):
    """A Bowlbug Rock plus two distinct workers picked sequentially from
    Egg / Silk / Nectar (each type at most once — mirrors the per-type caps
    in BowlbugsNormal.GenerateMonsters)."""

    monster_classes: list = field(default_factory=list)

    def create_monsters(self, hooks: HookSystem, rng: random.Random) -> list[Monster]:
        candidates = [BowlbugEgg, BowlbugSilk, BowlbugNectar]
        monsters: list[Monster] = [BowlbugRock(hooks, rng)]
        for _ in range(2):
            worker_cls = rng.choice(candidates)
            candidates.remove(worker_cls)
            monsters.append(worker_cls(hooks, rng))
        return monsters


BOWLBUGS_WEAK = BowlbugsWeakEncounter(id="bowlbugs_weak")
BOWLBUGS_NORMAL = BowlbugsNormalEncounter(id="bowlbugs_normal")
