from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ...actmap import AscensionLevel
from ..base import Encounter, Intent, MoveType, asc_value
from ..state_machine import MachineMonster, MonsterMoveStateMachine, MoveState

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem

_ADVANCED_GAS_DMG = 8         # LivingFog.cs:36 base
_ADVANCED_GAS_DMG_ASC = 9     # DeadlyEnemies (asc 9+)
_BLOAT_DMG = 5                # LivingFog.cs:38 base
_BLOAT_DMG_ASC = 6            # DeadlyEnemies (asc 9+)
_BLOAT_SPAWNS = 1
_SUPER_GAS_BLAST_DMG = 8      # LivingFog.cs:40 base
_SUPER_GAS_BLAST_DMG_ASC = 9  # DeadlyEnemies (asc 9+)
_EXPLODE_DMG = 8         # GasBomb.cs:32 base
_EXPLODE_DMG_ASC = 9     # DeadlyEnemies (asc 9+)


class GasBomb(MachineMonster):
    """Minion spawned by Living Fog; every turn it EXPLODEs — 8 damage to the
    player and it dies in the blast."""
    name = "Gas Bomb"

    min_hp = 7
    max_hp = 7
    min_hp_asc = 8       # GasBomb.cs:28 ToughEnemies (asc 8+)
    max_hp_asc = 8       # GasBomb.cs:30 `MaxInitialHp => MinInitialHp`

    def _explode_dmg(self) -> int:
        """GasBomb.cs:32 `ExplodeDamage` -- read at both the telegraphed
        Intent (:62, via the `() => ExplodeDamage` DeathBlowIntent closure)
        and the executed attack (:70)."""
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _EXPLODE_DMG_ASC, _EXPLODE_DMG)

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())
        from ...cmds import PowerCmd
        from ...powers import MinionPower
        PowerCmd.apply(hooks, self, MinionPower, 1)

    def build_machine(self) -> MonsterMoveStateMachine:
        explode = MoveState(
            "EXPLODE_MOVE", self._explode,
            # DeathBlowIntent : SingleAttackIntent : AttackIntent
            # (src/Core/MonsterMoves/Intents/DeathBlowIntent.cs:10) -- it IS
            # an AttackIntent, so NIntent.cs:135's `intent is AttackIntent`
            # check renders its damage number, and MonsterModel.IntendsToAttack
            # (MonsterModel.cs:241-245) explicitly treats DeathBlow as an
            # attack for gameplay purposes. `also=(MoveType.ATTACK,)` mirrors
            # that: it lights up `Intent.has(MoveType.ATTACK)` for the
            # observation's attack flag and damage preview without changing
            # the primary DEATH_BLOW type (still distinct for anything that
            # cares which icon/animation the game shows).
            lambda: Intent(MoveType.DEATH_BLOW, damage=self._explode_dmg(),
                            also=(MoveType.ATTACK,)),
        )
        explode.follow_up = explode
        return MonsterMoveStateMachine([explode], explode)

    def _explode(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._explode_dmg(), 1)
        from ...cmds import CreatureCmd
        CreatureCmd.kill(ctx.hooks, self)


class LivingFog(MachineMonster):
    """Opens with ADVANCED_GAS (8 damage + Smoggy: playing a Skill smogs your
    other Skills for the turn), then alternates BLOAT (spawn a Gas Bomb if a
    slot is free, then 5 damage) and SUPER_GAS_BLAST (8 damage)."""
    name = "Living Fog"

    min_hp = 80
    max_hp = 80
    min_hp_asc = 82      # LivingFog.cs:32 ToughEnemies (asc 8+)
    max_hp_asc = 82      # LivingFog.cs:34 `MaxInitialHp => MinInitialHp`

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())

    def _advanced_gas_dmg(self) -> int:
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _ADVANCED_GAS_DMG_ASC, _ADVANCED_GAS_DMG)

    def _bloat_dmg(self) -> int:
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _BLOAT_DMG_ASC, _BLOAT_DMG)

    def _super_gas_blast_dmg(self) -> int:
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _SUPER_GAS_BLAST_DMG_ASC, _SUPER_GAS_BLAST_DMG)

    def build_machine(self) -> MonsterMoveStateMachine:
        advanced_gas = MoveState(
            "ADVANCED_GAS_MOVE", self._advanced_gas,
            lambda: Intent(MoveType.ATTACK, damage=self._advanced_gas_dmg(),
                            also=(MoveType.CARD_DEBUFF,)),
        )
        bloat = MoveState(
            "BLOAT_MOVE", self._bloat,
            lambda: Intent(MoveType.ATTACK, damage=self._bloat_dmg(),
                            also=(MoveType.SUMMON,)),
        )
        super_gas = MoveState(
            "SUPER_GAS_BLAST_MOVE", self._super_gas_blast,
            lambda: Intent(MoveType.ATTACK, damage=self._super_gas_blast_dmg()),
        )
        advanced_gas.follow_up = bloat
        bloat.follow_up = super_gas
        super_gas.follow_up = bloat
        return MonsterMoveStateMachine([advanced_gas, super_gas, bloat], advanced_gas)

    def _advanced_gas(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._advanced_gas_dmg(), 1)
        from ...cmds import PowerCmd
        from ...powers import SmoggyPower
        PowerCmd.apply(ctx.hooks, ctx.player, SmoggyPower, 1)

    def _bloat(self, ctx: CombatCtx) -> None:
        """LivingFog.cs:85-97 (`BloatMove`).

        `string text = CombatState.Encounter?.GetNextSlot(CombatState);` then
        `if (!string.IsNullOrEmpty(text)) await CreatureCmd.Add<GasBomb>(
        CombatState, text);` — the NAMED slot row, exactly the mechanism
        `Encounter.slots`/`get_next_slot`/`CreatureCmd.add(slot_name=...)`
        already ports for the Fabricator and the Ovicopter.

        This used to hand-roll the same idea with a private `GasBomb.slot` int
        and a computed insertion index, from before the slot row existed. It
        placed live bombs correctly, but nothing ever evicted a dead one, so
        `combat.enemies` grew by one per exploded bomb — and since the
        observation and the action mask both index that list positionally
        against `MAX_ENEMIES`=6, a long fight pushed the LIVING enemies out of
        both (measured: `living_fog` seed 11, a 7-entry list with live enemies
        at indices 5 and 6). Going through the real slot row fixes that at the
        source: `_occupied` already treats a corpse's slot as free (C# removed
        it from `Enemies` at death) and `CreatureCmd.add` now evicts it.
        """
        from ...cmds import CreatureCmd
        combat = ctx.hooks.combat
        encounter = combat.encounter if combat is not None else None
        for _ in range(_BLOAT_SPAWNS):
            # GetNextSlot's default is `string.Empty`, NOT null, and the
            # caller's guard is `!string.IsNullOrEmpty` — so a full row spawns
            # nothing rather than adding a slotless bomb at the front.
            slot = encounter.get_next_slot(combat) if encounter is not None else ""
            if not slot:
                continue
            CreatureCmd.add(ctx.hooks, GasBomb(ctx.hooks, self._rng),
                            slot_name=slot)
        self._execute_attack(ctx, self._bloat_dmg(), 1)

    def _super_gas_blast(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._super_gas_blast_dmg(), 1)


LIVING_FOG_NORMAL = Encounter(
    id="living_fog_normal",
    monster_classes=[LivingFog],
    # LivingFogNormal.cs — `Slots` is the five bomb seats then the Fog, and
    # `GenerateMonsters` seats the Fog itself in "livingFog". The names are the
    # C# literals (camelCase `livingFog`), since they are what the slot row is
    # keyed by.
    slots=("bomb1", "bomb2", "bomb3", "bomb4", "bomb5", "livingFog"),
    monster_slots=("livingFog",),
)
