"""The Fake Merchant — the monster the Fake Merchant shared event turns into
when you throw a Foul Potion at him.

Source: src/Core/Models/Monsters/FakeMerchantMonster.cs and
src/Core/Models/Encounters/FakeMerchantEventEncounter.cs (non-ascension
values). Lives at the top level rather than in an act package because its
event is a SHARED one — reachable from any act after the first — unlike the
Mysterious Knight, which belongs to Hive's Lantern Key.
"""
from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ..actmap import AscensionLevel
from .base import Encounter, Intent, MoveType, asc_value
from .state_machine import (
    MachineMonster,
    MonsterMoveStateMachine,
    MoveRepeatType,
    MoveState,
    RandomBranchState,
)

if TYPE_CHECKING:
    from ..combat import CombatCtx
    from ..hooks import HookSystem

_SWIPE_DMG = 13          # FakeMerchantMonster.cs:37 base
_SWIPE_DMG_ASC = 15      # DeadlyEnemies
_SPEW_DMG = 2
_SPEW_HITS = 8
_THROW_DMG = 9           # FakeMerchantMonster.cs:39 base
_THROW_DMG_ASC = 10      # DeadlyEnemies
_THROW_FRAIL = 1
_ENRAGE_STRENGTH = 2
_GOLD_REWARD = 300


class FakeMerchantMonster(MachineMonster):
    """Opens with SWIPE (13), then each turn picks among SWIPE, SPEW_COINS
    (2x8), THROW_RELIC (9 + 1 Frail) and ENRAGE (+2 Strength, cooldown 3) —
    all weight 1, all cannot-repeat. After THROW_RELIC he picks from the
    attacks only (RAND_ATTACK_MOVE has no Enrage branch).

    Source: FakeMerchantMonster.cs (non-ascension values)."""
    name = "The Merchant???"

    min_hp = 165            # FakeMerchantMonster.cs:33
    max_hp = 165              # FakeMerchantMonster.cs:35
    min_hp_asc = 175          # FakeMerchantMonster.cs:33 -- ToughEnemies
    max_hp_asc = 175          # FakeMerchantMonster.cs:35 -- ToughEnemies

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())

    def _swipe_dmg(self) -> int:
        hooks = getattr(self, "_hooks", None)
        if hooks is None:
            return _SWIPE_DMG
        return asc_value(hooks, AscensionLevel.DEADLY_ENEMIES,
                          _SWIPE_DMG_ASC, _SWIPE_DMG)

    def _throw_dmg(self) -> int:
        hooks = getattr(self, "_hooks", None)
        if hooks is None:
            return _THROW_DMG
        return asc_value(hooks, AscensionLevel.DEADLY_ENEMIES,
                          _THROW_DMG_ASC, _THROW_DMG)

    def build_machine(self) -> MonsterMoveStateMachine:
        swipe = MoveState(
            "SWIPE_MOVE", self._swipe,
            Intent(MoveType.ATTACK, damage=self._swipe_dmg()),
        )
        spew = MoveState(
            "SPEW_COINS_MOVE", self._spew_coins,
            Intent(MoveType.ATTACK, damage=_SPEW_DMG, hits=_SPEW_HITS),
        )
        throw = MoveState(
            "THROW_RELIC_MOVE", self._throw_relic,
            Intent(MoveType.ATTACK, damage=self._throw_dmg(), also=(MoveType.DEBUFF,)),
        )
        enrage = MoveState("ENRAGE_MOVE", self._enrage, self._enrage_intent)

        rand_move = RandomBranchState("RAND_MOVE")
        rand_move.add_branch(swipe, repeat_type=MoveRepeatType.CANNOT_REPEAT)
        rand_move.add_branch(spew, repeat_type=MoveRepeatType.CANNOT_REPEAT)
        rand_move.add_branch(throw, repeat_type=MoveRepeatType.CANNOT_REPEAT)
        # FakeMerchantMonster.cs:58 AddBranch(state, 3, CannotRepeat) is the
        # (state, int cooldown, MoveRepeatType) overload — a cooldown, not a
        # weight.
        rand_move.add_branch(
            enrage, repeat_type=MoveRepeatType.CANNOT_REPEAT, cooldown=3,
        )

        rand_attack = RandomBranchState("RAND_ATTACK_MOVE")
        rand_attack.add_branch(swipe, repeat_type=MoveRepeatType.CANNOT_REPEAT)
        rand_attack.add_branch(spew, repeat_type=MoveRepeatType.CANNOT_REPEAT)
        rand_attack.add_branch(throw, repeat_type=MoveRepeatType.CANNOT_REPEAT)

        swipe.follow_up = rand_move
        spew.follow_up = rand_move
        enrage.follow_up = rand_move
        throw.follow_up = rand_attack
        return MonsterMoveStateMachine(
            [swipe, spew, throw, enrage, rand_move, rand_attack], swipe,
        )

    @staticmethod
    def _enrage_intent() -> Intent:
        from ..powers import StrengthPower

        return Intent(MoveType.BUFF, buffs=[(StrengthPower, _ENRAGE_STRENGTH)])

    def _swipe(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._swipe_dmg(), 1)

    def _spew_coins(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _SPEW_DMG, _SPEW_HITS)

    def _throw_relic(self, ctx: CombatCtx) -> None:
        from ..cmds import PowerCmd
        from ..powers import FrailPower

        self._execute_attack(ctx, self._throw_dmg(), 1)
        PowerCmd.apply(ctx.hooks, ctx.player, FrailPower, _THROW_FRAIL,
                       applier=self)

    def _enrage(self, ctx: CombatCtx) -> None:
        from ..cmds import PowerCmd
        from ..powers import StrengthPower

        PowerCmd.apply(ctx.hooks, self, StrengthPower, _ENRAGE_STRENGTH)


# FakeMerchantEventEncounter.cs: RoomType.Monster, gold reward pinned at 300.
FAKE_MERCHANT_EVENT_ENCOUNTER = Encounter(
    id="fake_merchant_event",
    monster_classes=[FakeMerchantMonster],
    min_gold=_GOLD_REWARD,
    max_gold=_GOLD_REWARD,
    # C# class FakeMerchantEventEncounter — the sim id drops the suffix.
    entry_slug="FAKE_MERCHANT_EVENT_ENCOUNTER",
    # FakeMerchantEventEncounter.cs:17,25-28 — a one-name row.
    slots=("merchant",),
    monster_slots=("merchant",),
)
