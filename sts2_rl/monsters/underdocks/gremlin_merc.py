from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ..base import Encounter, Intent, MoveType
from ..state_machine import MachineMonster, MonsterMoveStateMachine, MoveState

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem

_GIMME_DMG = 7
_GIMME_HITS = 2
_DOUBLE_SMASH_DMG = 6
_DOUBLE_SMASH_HITS = 2
_DOUBLE_SMASH_WEAK = 2
_HEHE_DMG = 8
_HEHE_STR = 2
_THIEVERY_GOLD = 20  # ThieveryPower applied at 20 (GremlinMerc.AfterAddedToRoom)
_SNEAKY_TACKLE_DMG = 9


class GremlinMerc(MachineMonster):
    """GIMME → DOUBLE_SMASH → HEHE → loop, each move stealing up to 20 gold
    after its attack (ThieveryPower.Steal — GremlinMerc.cs). Surprise: on
    death, a Sneaky Gremlin and a Fat Gremlin jump out of the crate
    (SurprisePower), the fat one carrying the stolen gold (HeistPower)."""

    min_hp = 47
    max_hp = 49

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())
        from ...cmds import PowerCmd
        from ...powers import SurprisePower, ThieveryPower
        PowerCmd.apply(hooks, self, SurprisePower, 1)
        PowerCmd.apply(hooks, self, ThieveryPower, _THIEVERY_GOLD)

    def _steal(self) -> None:
        thievery = self.powers.get("thievery")
        if thievery is not None:
            thievery.steal()

    def build_machine(self) -> MonsterMoveStateMachine:
        gimme = MoveState(
            "GIMME_MOVE", self._gimme,
            Intent(MoveType.ATTACK, damage=_GIMME_DMG, hits=_GIMME_HITS),
        )
        double_smash = MoveState(
            "DOUBLE_SMASH_MOVE", self._double_smash,
            Intent(
                MoveType.ATTACK, damage=_DOUBLE_SMASH_DMG, hits=_DOUBLE_SMASH_HITS,
                also=(MoveType.DEBUFF,),
            ),
        )
        hehe = MoveState(
            "HEHE_MOVE", self._hehe,
            Intent(MoveType.ATTACK, damage=_HEHE_DMG, also=(MoveType.BUFF,)),
        )
        gimme.follow_up = double_smash
        double_smash.follow_up = hehe
        hehe.follow_up = gimme
        return MonsterMoveStateMachine([gimme, double_smash, hehe], gimme)

    def _gimme(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _GIMME_DMG, _GIMME_HITS)
        self._steal()

    def _double_smash(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _DOUBLE_SMASH_DMG, _DOUBLE_SMASH_HITS)
        self._steal()
        from ...cmds import PowerCmd
        from ...powers import WeakPower
        PowerCmd.apply(ctx.hooks, ctx.player, WeakPower, _DOUBLE_SMASH_WEAK)

    def _hehe(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _HEHE_DMG, 1)
        self._steal()
        from ...cmds import PowerCmd
        from ...powers import StrengthPower
        PowerCmd.apply(ctx.hooks, self, StrengthPower, _HEHE_STR)


class SneakyGremlin(MachineMonster):
    """Spends its spawn turn waking up (STUN intent, no-op), then TACKLEs
    every turn."""

    min_hp = 10
    max_hp = 14

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())

    def build_machine(self) -> MonsterMoveStateMachine:
        spawned = MoveState("SPAWNED_MOVE", self._spawned, Intent(MoveType.STUN))
        tackle = MoveState(
            "TACKLE_MOVE", self._tackle,
            Intent(MoveType.ATTACK, damage=_SNEAKY_TACKLE_DMG),
        )
        spawned.follow_up = tackle
        tackle.follow_up = tackle
        return MonsterMoveStateMachine([spawned, tackle], spawned)

    def _spawned(self, ctx: CombatCtx) -> None:
        pass  # wake-up animation only

    def _tackle(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _SNEAKY_TACKLE_DMG, 1)


class FatGremlin(MachineMonster):
    """Spends its spawn turn waking up, then flees the fight (escapes,
    counting as gone for the win condition)."""

    min_hp = 13
    max_hp = 17

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())

    def build_machine(self) -> MonsterMoveStateMachine:
        spawned = MoveState("SPAWNED_MOVE", self._spawned, Intent(MoveType.STUN))
        flee = MoveState("FLEE_MOVE", self._flee, Intent(MoveType.ESCAPE))
        spawned.follow_up = flee
        flee.follow_up = flee
        return MonsterMoveStateMachine([spawned, flee], spawned)

    def _spawned(self, ctx: CombatCtx) -> None:
        pass  # wake-up animation only

    def _flee(self, ctx: CombatCtx) -> None:
        from ...cmds import CreatureCmd
        CreatureCmd.escape(ctx.hooks, self)


GREMLIN_MERC_NORMAL = Encounter(
    id="gremlin_merc_normal",
    monster_classes=[GremlinMerc],
)
