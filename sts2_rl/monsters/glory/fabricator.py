from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ..base import Encounter, Intent, MoveType
from ..state_machine import (
    ConditionalBranchState,
    MachineMonster,
    MonsterMoveStateMachine,
    MoveState,
    RandomBranchState,
)

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem

_STRIKE_DMG = 18
_DISINTEGRATE_DMG = 11
_GUARD_BLOCK = 15
_NOISE_DAZED = 2
_STAB_DMG = 11
_STAB_FRAIL = 1
_ZAP_DMG = 14
_HIGH_VOLTAGE = 2
_MAX_ALIVE = 4  # Fabricator stops summoning once this many enemies are alive


class Guardbot(MachineMonster):
    """Guards: gives 15 block to the Fabricator every turn. Source: Guardbot.cs."""

    min_hp = 16
    max_hp = 20

    def build_machine(self) -> MonsterMoveStateMachine:
        guard = MoveState("GUARD_MOVE", self._guard, Intent(MoveType.DEFEND))
        guard.follow_up = guard
        return MonsterMoveStateMachine([guard], guard)

    def _guard(self, ctx: CombatCtx) -> None:
        from ...cmds import BlockCmd
        from ...valueprops import ValueProp
        combat = ctx.hooks.combat
        if combat is None:
            return
        # Guardbot.cs:51 `Enemies.Where(c => c.Monster is Fabricator)` -- the
        # ONLY test is membership of CombatState.Enemies, which C# still
        # holds a death-vetoed retained corpse in. `is_removed_from_combat`
        # (not `is_gone`) is the sim's mirror of that membership test: it is
        # False for a retained corpse (still "in Enemies") and True only for
        # a creature C# has actually dropped from Enemies (an ordinary kill,
        # or an escape -- both real removals).
        for enemy in combat.enemies:
            if isinstance(enemy, Fabricator) and not enemy.is_removed_from_combat:
                BlockCmd.apply(ctx.hooks, enemy, _GUARD_BLOCK, props=ValueProp.UNPOWERED)


class Noisebot(MachineMonster):
    """Adds 2 Dazed (one to draw, one to discard) every turn. Source: Noisebot.cs."""

    min_hp = 18
    max_hp = 23

    def build_machine(self) -> MonsterMoveStateMachine:
        noise = MoveState("NOISE_MOVE", self._noise, Intent(MoveType.STATUS_CARD))
        noise.follow_up = noise
        return MonsterMoveStateMachine([noise], noise)

    def _noise(self, ctx: CombatCtx) -> None:
        from ...cards import DazedCard
        from ...cmds import CardPileCmd
        CardPileCmd.add_to_discard(ctx.hooks, ctx.player, DazedCard())
        CardPileCmd.add_to_draw(ctx.hooks, ctx.player, DazedCard())


class Stabbot(MachineMonster):
    """Stabs for 11 and applies Frail 1 every turn. Source: Stabbot.cs."""

    min_hp = 18
    max_hp = 23

    def build_machine(self) -> MonsterMoveStateMachine:
        stab = MoveState(
            "STAB_MOVE", self._stab,
            Intent(MoveType.ATTACK, damage=_STAB_DMG, also=(MoveType.DEBUFF,)),
        )
        stab.follow_up = stab
        return MonsterMoveStateMachine([stab], stab)

    def _stab(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _STAB_DMG, 1)
        from ...cmds import PowerCmd
        from ...powers import FrailPower
        PowerCmd.apply(ctx.hooks, ctx.player, FrailPower, _STAB_FRAIL)


class Zapbot(MachineMonster):
    """Zaps for 14 every turn. Starts with High Voltage 2 (gains 2 Strength at
    the end of each of its turns). Source: Zapbot.cs."""

    min_hp = 18
    max_hp = 23

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())
        from ...cmds import PowerCmd
        from ...powers import HighVoltagePower
        PowerCmd.apply(hooks, self, HighVoltagePower, _HIGH_VOLTAGE)

    def build_machine(self) -> MonsterMoveStateMachine:
        zap = MoveState(
            "ZAP", self._zap, Intent(MoveType.ATTACK, damage=_ZAP_DMG)
        )
        zap.follow_up = zap
        return MonsterMoveStateMachine([zap], zap)

    def _zap(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _ZAP_DMG, 1)


_DEFENSE_SPAWNS: list[type[MachineMonster]] = [Guardbot, Noisebot]
_AGGRO_SPAWNS: list[type[MachineMonster]] = [Zapbot, Stabbot]


class Fabricator(MachineMonster):
    """Fabricates bots until four enemies are on the field, alternating Fabricate
    (summon one defensive + one aggressive bot) and Fabricating Strike (18 +
    summon one aggressive bot); once the field is full it Disintegrates (11).
    Summoned bots are minions.

    Source: Fabricator.cs (non-ascension values). The game rolls the two
    fabricate moves from a dedicated MonsterAi RNG; the sim uses the shared
    combat RNG."""

    min_hp = 150
    max_hp = 150

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())
        self._last_spawned: type[MachineMonster] | None = None

    def _alive_count(self) -> int:
        combat = self._hooks.combat
        # combat.enemies is not assigned until every monster is built, so the
        # opening roll (during __init__) counts just this Fabricator.
        enemies = getattr(combat, "enemies", None) if combat is not None else None
        if not enemies:
            return 1
        return sum(1 for c in enemies if not c.is_gone)

    def _can_fabricate(self) -> bool:
        return self._alive_count() < _MAX_ALIVE

    def build_machine(self) -> MonsterMoveStateMachine:
        fabricate = MoveState("FABRICATE_MOVE", self._fabricate, Intent(MoveType.SUMMON))
        strike = MoveState(
            "FABRICATING_STRIKE_MOVE", self._strike,
            Intent(MoveType.ATTACK, damage=_STRIKE_DMG, also=(MoveType.SUMMON,)),
        )
        disintegrate = MoveState(
            "DISINTEGRATE_MOVE", self._disintegrate,
            Intent(MoveType.ATTACK, damage=_DISINTEGRATE_DMG),
        )
        rand = RandomBranchState("RAND")
        rand.add_branch(fabricate, weight=1.0)
        rand.add_branch(strike, weight=1.0)
        branch = ConditionalBranchState("fabricateBranch")
        branch.add_state(rand, self._can_fabricate)
        branch.add_state(disintegrate, lambda: not self._can_fabricate())
        fabricate.follow_up = branch
        strike.follow_up = branch
        disintegrate.follow_up = branch
        return MonsterMoveStateMachine(
            [fabricate, strike, disintegrate, branch, rand], branch
        )

    def _spawn_bot(self, ctx: CombatCtx, options: list[type[MachineMonster]]) -> None:
        combat = ctx.hooks.combat
        if combat is None:
            return
        choices = [m for m in options if m is not self._last_spawned]
        # Fabricator.cs:115 — base.RunRng.MonsterAi.NextItem(items), the same
        # dedicated stream MonsterModel.RollMove draws from, not the shared rng.
        cls = combat.combat_rng.monster_ai.choice(choices)
        self._last_spawned = cls
        bot = cls(ctx.hooks, combat._rng)
        from ...cmds import CreatureCmd, PowerCmd
        from ...powers import MinionPower
        # Fabricator.cs:115 passes `CombatState.Encounter.GetNextSlot(
        # CombatState)` to CreatureCmd.Add — the FIRST unoccupied entry of
        # [bot1, bot2, fabricator, bot3, bot4]. Since the Fabricator itself holds
        # the middle entry, the first two bots seat IN FRONT of it: the game's
        # Enemies after the opening FABRICATE are [bot, bot, Fabricator]. The sim
        # appended, so the Fabricator came out FIRST — the same reversal
        # monster/living_fog is verdicted live for, and it also arms the
        # turn_structure block-clearing gap, because Guardbot's GUARD grants
        # block to a creature LATER in the list.
        slot = None
        if combat.encounter is not None and combat.encounter.slots:
            slot = combat.encounter.get_next_slot(combat)
        CreatureCmd.add(ctx.hooks, bot, slot_name=slot)
        PowerCmd.apply(ctx.hooks, bot, MinionPower, 1, applier=self)

    def _fabricate(self, ctx: CombatCtx) -> None:
        self._spawn_bot(ctx, _DEFENSE_SPAWNS)
        self._spawn_bot(ctx, _AGGRO_SPAWNS)

    def _strike(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _STRIKE_DMG, 1)
        self._spawn_bot(ctx, _AGGRO_SPAWNS)

    def _disintegrate(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _DISINTEGRATE_DMG, 1)


FABRICATOR_NORMAL = Encounter(
    id="fabricator_normal",
    monster_classes=[Fabricator],
    # FabricatorNormal.cs:19 — the Fabricator sits in the MIDDLE of the row, so
    # the first two bots seat in FRONT of it and the last two behind it.
    slots=("bot1", "bot2", "fabricator", "bot3", "bot4"),
    # FabricatorNormal.cs:46-49 — `GenerateMonsters` seats it in "fabricator".
    monster_slots=("fabricator",),
)
