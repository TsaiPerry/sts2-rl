"""Bowlbug workers (Hive).

Sources: BowlbugRock.cs, BowlbugEgg.cs, BowlbugSilk.cs, BowlbugNectar.cs,
BowlbugsWeak.cs, BowlbugsNormal.cs.
"""
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

_HEADBUTT_DMG = 15         # BowlbugRock.cs:36 base
_HEADBUTT_DMG_ASC = 16     # BowlbugRock.cs:36 DeadlyEnemies (asc 9+)
_EGG_BITE_DMG = 7          # BowlbugEgg.cs:23 base
_EGG_BITE_DMG_ASC = 8      # BowlbugEgg.cs:23 DeadlyEnemies (asc 9+)
_EGG_BLOCK = 7             # BowlbugEgg.cs:25 base
_EGG_BLOCK_ASC = 8         # BowlbugEgg.cs:25 DeadlyEnemies (asc 9+)
_SILK_THRASH_DMG = 4       # BowlbugSilk.cs:32 base
_SILK_THRASH_DMG_ASC = 5   # BowlbugSilk.cs:32 DeadlyEnemies (asc 9+)
_SILK_THRASH_HITS = 2
_SILK_WEAK = 1
_NECTAR_THRASH_DMG = 3     # BowlbugNectar.cs:29 -- plain `=> 3`, not ascension-gated (no-op)
_NECTAR_STR = 15           # BowlbugNectar.cs:31 base
_NECTAR_STR_ASC = 16       # BowlbugNectar.cs:31 DeadlyEnemies (asc 9+)


class BowlbugRock(MachineMonster):
    """HEADBUTT (15) every turn — but Imbalanced: a fully blocked headbutt
    throws it off balance and it spends the next turn dizzy."""

    name = "Bowlbug (Rock)"
    min_hp = 45          # BowlbugRock.cs:32 base
    max_hp = 48          # BowlbugRock.cs:34 base
    min_hp_asc = 46      # BowlbugRock.cs:32 ToughEnemies (asc 8+)
    max_hp_asc = 49      # BowlbugRock.cs:34 ToughEnemies (asc 8+)

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        self.is_off_balance = False
        super().__init__(hooks, rng or random.Random())
        from ...cmds import PowerCmd
        from ...powers import ImbalancedPower
        PowerCmd.apply(hooks, self, ImbalancedPower, 1)

    def _headbutt_dmg(self) -> int:
        """BowlbugRock.cs:36 `HeadbuttDamage` -- a C# PROPERTY re-read at both
        the telegraphed Intent (:72) and the executed attack (:86), so both
        sites call this rather than a value cached at construction."""
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _HEADBUTT_DMG_ASC, _HEADBUTT_DMG)

    def build_machine(self) -> MonsterMoveStateMachine:
        headbutt = MoveState(
            "HEADBUTT_MOVE", self._headbutt,
            lambda: Intent(MoveType.ATTACK, damage=self._headbutt_dmg()),
        )
        dizzy = MoveState("DIZZY_MOVE", self._dizzy, Intent(MoveType.STUN))
        post = ConditionalBranchState("POST_HEADBUTT")
        post.add_state(dizzy, lambda: self.is_off_balance)
        post.add_state(headbutt, lambda: not self.is_off_balance)
        headbutt.follow_up = post
        dizzy.follow_up = headbutt
        return MonsterMoveStateMachine([dizzy, post, headbutt], headbutt)

    def _headbutt(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._headbutt_dmg(), 1)

    def _dizzy(self, ctx: CombatCtx) -> None:
        self.is_off_balance = False


class BowlbugEgg(MachineMonster):
    """BITE (7) then gain 7 block, every turn."""

    name = "Bowlbug (Egg)"
    min_hp = 21          # BowlbugEgg.cs:19 base
    max_hp = 22          # BowlbugEgg.cs:21 base
    min_hp_asc = 23      # BowlbugEgg.cs:19 ToughEnemies (asc 8+)
    max_hp_asc = 24      # BowlbugEgg.cs:21 ToughEnemies (asc 8+)

    def _bite_dmg(self) -> int:
        """BowlbugEgg.cs:23 `BiteDamage` -- re-read at both the Intent (:59)
        and the executed attack (:67)."""
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _EGG_BITE_DMG_ASC, _EGG_BITE_DMG)

    def _protect_block(self) -> int:
        """BowlbugEgg.cs:25 `ProtectBlock`, read only at the executed move
        (:71) -- the Intent (:59) is a plain DefendIntent with no amount."""
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _EGG_BLOCK_ASC, _EGG_BLOCK)

    def build_machine(self) -> MonsterMoveStateMachine:
        bite = MoveState(
            "BITE_MOVE", self._bite,
            lambda: Intent(MoveType.ATTACK, damage=self._bite_dmg(), also=(MoveType.DEFEND,)),
        )
        bite.follow_up = bite
        return MonsterMoveStateMachine([bite], bite)

    def _bite(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._bite_dmg(), 1)
        from ...cmds import BlockCmd
        BlockCmd.apply(ctx.hooks, self, self._protect_block())


class BowlbugSilk(MachineMonster):
    """Opens with TOXIC_SPIT (Weak 1), then alternates THRASH (4x2) and SPIT."""

    name = "Bowlbug (Silk)"
    min_hp = 40          # BowlbugSilk.cs:28 base
    max_hp = 43          # BowlbugSilk.cs:30 base
    min_hp_asc = 41      # BowlbugSilk.cs:28 ToughEnemies (asc 8+)
    max_hp_asc = 44      # BowlbugSilk.cs:30 ToughEnemies (asc 8+)

    def _thrash_dmg(self) -> int:
        """BowlbugSilk.cs:32 `ThrashDamage` -- re-read at both the Intent
        (:45) and the executed attack (:55)."""
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _SILK_THRASH_DMG_ASC, _SILK_THRASH_DMG)

    def build_machine(self) -> MonsterMoveStateMachine:
        thrash = MoveState(
            "THRASH_MOVE", self._thrash,
            lambda: Intent(MoveType.ATTACK, damage=self._thrash_dmg(), hits=_SILK_THRASH_HITS),
        )
        spit = MoveState("TOXIC_SPIT_MOVE", self._spit, Intent(MoveType.DEBUFF))
        thrash.follow_up = spit
        spit.follow_up = thrash
        return MonsterMoveStateMachine([thrash, spit], spit)

    def _thrash(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._thrash_dmg(), _SILK_THRASH_HITS)

    def _spit(self, ctx: CombatCtx) -> None:
        from ...cmds import PowerCmd
        from ...powers import WeakPower
        PowerCmd.apply(ctx.hooks, ctx.player, WeakPower, _SILK_WEAK, applier=self)


class BowlbugNectar(MachineMonster):
    """THRASH (3), BUFF (+15 Strength), then THRASH forever."""

    name = "Bowlbug (Nectar)"
    min_hp = 35          # BowlbugNectar.cs:25 base
    max_hp = 38          # BowlbugNectar.cs:27 base
    min_hp_asc = 36      # BowlbugNectar.cs:25 ToughEnemies (asc 8+)
    max_hp_asc = 39      # BowlbugNectar.cs:27 ToughEnemies (asc 8+)

    def _buff_str(self) -> int:
        """BowlbugNectar.cs:31 `BuffStrengthGain`, read only at the executed
        move (:69) -- the Intent (:47) is a plain BuffIntent with no amount."""
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _NECTAR_STR_ASC, _NECTAR_STR)

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
        PowerCmd.apply(ctx.hooks, self, StrengthPower, self._buff_str())


@dataclass
class BowlbugsWeakEncounter(Encounter):
    """A Bowlbug Rock plus one random worker from Egg / Nectar."""

    monster_classes: list = field(default_factory=list)

    def create_monsters(self, hooks: HookSystem, rng: random.Random, selection_rng=None) -> list[Monster]:
        # Parity (BowlbugsWeak.GenerateMonsters): the second slot's worker is
        # `base.Rng.NextItem(Bugs)` on the per-encounter Rng, Bugs in declaration
        # order [Egg, Nectar]. Legacy keeps the shared-rng choice.
        bugs = [BowlbugEgg, BowlbugNectar]
        if selection_rng is not None:
            worker_cls = selection_rng.next_item(bugs)
        else:
            worker_cls = rng.choice(bugs)
        return [BowlbugRock(hooks, rng), worker_cls(hooks, rng)]


@dataclass
class BowlbugsNormalEncounter(Encounter):
    """A Bowlbug Rock plus two distinct workers picked sequentially from
    Egg / Silk / Nectar (each type at most once — mirrors the per-type caps
    in BowlbugsNormal.GenerateMonsters)."""

    monster_classes: list = field(default_factory=list)

    def create_monsters(self, hooks: HookSystem, rng: random.Random, selection_rng=None) -> list[Monster]:
        # Parity (BowlbugsNormal.GenerateMonsters): two workers picked in turn
        # via `base.Rng.NextItem(items)` where items = the valid-count keys
        # (declaration order [Egg, Silk, Nectar]) minus any type already at its
        # cap of 1. Legacy keeps the shared-rng choice.
        candidates = [BowlbugEgg, BowlbugSilk, BowlbugNectar]
        monsters: list[Monster] = [BowlbugRock(hooks, rng)]
        for _ in range(2):
            if selection_rng is not None:
                worker_cls = selection_rng.next_item(candidates)
            else:
                worker_cls = rng.choice(candidates)
            candidates.remove(worker_cls)
            monsters.append(worker_cls(hooks, rng))
        return monsters


BOWLBUGS_WEAK = BowlbugsWeakEncounter(id="bowlbugs_weak")
BOWLBUGS_NORMAL = BowlbugsNormalEncounter(id="bowlbugs_normal")
