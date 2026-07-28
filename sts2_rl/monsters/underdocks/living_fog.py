from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ..base import Encounter, Intent, MoveType
from ..state_machine import MachineMonster, MonsterMoveStateMachine, MoveState

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem

_ADVANCED_GAS_DMG = 8
_BLOAT_DMG = 5
_BLOAT_SPAWNS = 1
_SUPER_GAS_BLAST_DMG = 8
_EXPLODE_DMG = 8
_BOMB_SLOTS = 5


class GasBomb(MachineMonster):
    """Minion spawned by Living Fog; every turn it EXPLODEs — 8 damage to the
    player and it dies in the blast."""
    name = "Gas Bomb"

    min_hp = 7
    max_hp = 7

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        # Index into LivingFogNormal.Slots of the "bombN" slot this bomb was
        # spawned into (Creature.SlotName); LivingFog.bloat assigns it.
        self.slot = 0
        super().__init__(hooks, rng or random.Random())
        from ...cmds import PowerCmd
        from ...powers import MinionPower
        PowerCmd.apply(hooks, self, MinionPower, 1)

    def build_machine(self) -> MonsterMoveStateMachine:
        explode = MoveState(
            "EXPLODE_MOVE", self._explode,
            Intent(MoveType.DEATH_BLOW, damage=_EXPLODE_DMG),
        )
        explode.follow_up = explode
        return MonsterMoveStateMachine([explode], explode)

    def _explode(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _EXPLODE_DMG, 1)
        from ...cmds import CreatureCmd
        CreatureCmd.kill(ctx.hooks, self)


def _slot_index(creature) -> int | None:
    """Encounter.Slots.IndexOf(creature.SlotName) for LivingFogNormal.Slots =
    [bomb1..bomb5, livingFog]; None for a creature holding no slot (the game
    removes a dead creature from Enemies, so a corpse occupies nothing)."""
    if isinstance(creature, GasBomb):
        return None if creature.is_gone else creature.slot
    if isinstance(creature, LivingFog):
        return _BOMB_SLOTS
    return None


class LivingFog(MachineMonster):
    """Opens with ADVANCED_GAS (8 damage + Smoggy: playing a Skill smogs your
    other Skills for the turn), then alternates BLOAT (spawn a Gas Bomb if a
    slot is free, then 5 damage) and SUPER_GAS_BLAST (8 damage)."""
    name = "Living Fog"

    min_hp = 80
    max_hp = 80

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())

    def build_machine(self) -> MonsterMoveStateMachine:
        advanced_gas = MoveState(
            "ADVANCED_GAS_MOVE", self._advanced_gas,
            Intent(MoveType.ATTACK, damage=_ADVANCED_GAS_DMG,
                   also=(MoveType.CARD_DEBUFF,)),
        )
        bloat = MoveState(
            "BLOAT_MOVE", self._bloat,
            Intent(MoveType.ATTACK, damage=_BLOAT_DMG, also=(MoveType.SUMMON,)),
        )
        super_gas = MoveState(
            "SUPER_GAS_BLAST_MOVE", self._super_gas_blast,
            Intent(MoveType.ATTACK, damage=_SUPER_GAS_BLAST_DMG),
        )
        advanced_gas.follow_up = bloat
        bloat.follow_up = super_gas
        super_gas.follow_up = bloat
        return MonsterMoveStateMachine([advanced_gas, super_gas, bloat], advanced_gas)

    def _advanced_gas(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _ADVANCED_GAS_DMG, 1)
        from ...cmds import PowerCmd
        from ...powers import SmoggyPower
        PowerCmd.apply(ctx.hooks, ctx.player, SmoggyPower, 1)

    def _bloat(self, ctx: CombatCtx) -> None:
        from ...cmds import CreatureCmd
        for _ in range(_BLOAT_SPAWNS):
            # EncounterModel.GetNextSlot: the FIRST of the encounter's slots
            # (LivingFogNormal.Slots = [bomb1..bomb5, livingFog]) that no enemy
            # occupies; an empty result means no room and nothing spawns.
            occupied = {
                e.slot for e in ctx.enemies
                if isinstance(e, GasBomb) and not e.is_gone
            }
            slot = next(
                (s for s in range(_BOMB_SLOTS) if s not in occupied), None
            )
            if slot is None:
                continue
            bomb = GasBomb(ctx.hooks, self._rng)
            bomb.slot = slot
            # CombatManager.AddCreature re-sorts Enemies by
            # Encounter.Slots.IndexOf(SlotName) whenever the added creature
            # carries a slot (SortEnemiesBySlotName), so the bomb takes its
            # slot's position — ahead of the Living Fog (slot index 5) and of
            # any bomb in a later slot — instead of being appended.
            idx = min(
                (i for i, e in enumerate(ctx.enemies)
                 if _slot_index(e) is not None and _slot_index(e) > slot),
                default=len(ctx.enemies),
            )
            CreatureCmd.add(ctx.hooks, bomb, index=idx)
        self._execute_attack(ctx, _BLOAT_DMG, 1)

    def _super_gas_blast(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _SUPER_GAS_BLAST_DMG, 1)


LIVING_FOG_NORMAL = Encounter(
    id="living_fog_normal",
    monster_classes=[LivingFog],
)
