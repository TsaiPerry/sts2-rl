from __future__ import annotations

import random
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ...actmap import AscensionLevel
from ..base import Encounter, Intent, MoveType, asc_value
from ..state_machine import MachineMonster, MonsterMoveStateMachine, MoveState

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem

_GIMME_DMG = 7              # GremlinMerc.cs:36 base
_GIMME_DMG_ASC = 8          # ToughEnemies (asc 8+) -- note: source gates this
                             # damage site on ToughEnemies, not DeadlyEnemies.
_GIMME_HITS = 2
_DOUBLE_SMASH_DMG = 6        # GremlinMerc.cs:40 base
_DOUBLE_SMASH_DMG_ASC = 7    # ToughEnemies (asc 8+)
_DOUBLE_SMASH_HITS = 2
_DOUBLE_SMASH_WEAK = 2
_HEHE_DMG = 8                # GremlinMerc.cs:44 base
_HEHE_DMG_ASC = 9            # ToughEnemies (asc 8+)
_HEHE_STR = 2
_THIEVERY_GOLD = 20  # ThieveryPower applied at 20 (GremlinMerc.AfterAddedToRoom)
_SNEAKY_TACKLE_DMG = 9        # SneakyGremlin.cs:25 base
_SNEAKY_TACKLE_DMG_ASC = 10   # DeadlyEnemies (asc 9+)


class GremlinMerc(MachineMonster):
    """GIMME → DOUBLE_SMASH → HEHE → loop, each move stealing up to 20 gold
    after its attack (ThieveryPower.Steal — GremlinMerc.cs). Surprise: on
    death, a Sneaky Gremlin and a Fat Gremlin jump out of the crate
    (SurprisePower), the fat one carrying the stolen gold (HeistPower)."""
    name = "Gremlin Merc"

    min_hp = 47          # GremlinMerc.cs:28-30
    max_hp = 49
    min_hp_asc = 51       # ToughEnemies (asc 8+)
    max_hp_asc = 53

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())
        from ...cmds import PowerCmd
        from ...powers import SurprisePower, ThieveryPower
        PowerCmd.apply(hooks, self, SurprisePower, 1)
        PowerCmd.apply(hooks, self, ThieveryPower, _THIEVERY_GOLD)

    def _gimme_dmg(self) -> int:
        """GremlinMerc.cs:36 `GimmeDamage` -- re-read at both the telegraphed
        Intent and the executed attack."""
        return asc_value(self._hooks, AscensionLevel.TOUGH_ENEMIES,
                          _GIMME_DMG_ASC, _GIMME_DMG)

    def _double_smash_dmg(self) -> int:
        """GremlinMerc.cs:40 `DoubleSmashDamage`."""
        return asc_value(self._hooks, AscensionLevel.TOUGH_ENEMIES,
                          _DOUBLE_SMASH_DMG_ASC, _DOUBLE_SMASH_DMG)

    def _hehe_dmg(self) -> int:
        """GremlinMerc.cs:44 `HeheDamage`."""
        return asc_value(self._hooks, AscensionLevel.TOUGH_ENEMIES,
                          _HEHE_DMG_ASC, _HEHE_DMG)

    def _steal(self) -> None:
        thievery = self.powers.get("thievery")
        if thievery is not None:
            thievery.steal()

    def build_machine(self) -> MonsterMoveStateMachine:
        gimme = MoveState(
            "GIMME_MOVE", self._gimme,
            lambda: Intent(MoveType.ATTACK, damage=self._gimme_dmg(), hits=_GIMME_HITS),
        )
        double_smash = MoveState(
            "DOUBLE_SMASH_MOVE", self._double_smash,
            lambda: Intent(
                MoveType.ATTACK, damage=self._double_smash_dmg(), hits=_DOUBLE_SMASH_HITS,
                also=(MoveType.DEBUFF,),
            ),
        )
        hehe = MoveState(
            "HEHE_MOVE", self._hehe,
            lambda: Intent(MoveType.ATTACK, damage=self._hehe_dmg(), also=(MoveType.BUFF,)),
        )
        gimme.follow_up = double_smash
        double_smash.follow_up = hehe
        hehe.follow_up = gimme
        return MonsterMoveStateMachine([gimme, double_smash, hehe], gimme)

    def _gimme(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._gimme_dmg(), _GIMME_HITS)
        self._steal()

    def _double_smash(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._double_smash_dmg(), _DOUBLE_SMASH_HITS)
        self._steal()
        from ...cmds import PowerCmd
        from ...powers import WeakPower
        PowerCmd.apply(ctx.hooks, ctx.player, WeakPower, _DOUBLE_SMASH_WEAK)

    def _hehe(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._hehe_dmg(), 1)
        self._steal()
        from ...cmds import PowerCmd
        from ...powers import StrengthPower
        PowerCmd.apply(ctx.hooks, self, StrengthPower, _HEHE_STR)


class SneakyGremlin(MachineMonster):
    """Spends its spawn turn waking up (STUN intent, no-op), then TACKLEs
    every turn."""
    name = "Sneaky Gremlin"

    min_hp = 10          # SneakyGremlin.cs:21
    max_hp = 14
    min_hp_asc = 11       # ToughEnemies (asc 8+) -- SneakyGremlin.cs:21
    max_hp_asc = 15       # SneakyGremlin.cs:23

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())

    def _tackle_dmg(self) -> int:
        """SneakyGremlin.cs:25 `TackleDamage` -- re-read at both the
        telegraphed Intent and the executed attack."""
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _SNEAKY_TACKLE_DMG_ASC, _SNEAKY_TACKLE_DMG)

    def build_machine(self) -> MonsterMoveStateMachine:
        spawned = MoveState("SPAWNED_MOVE", self._spawned, Intent(MoveType.STUN))
        tackle = MoveState(
            "TACKLE_MOVE", self._tackle,
            lambda: Intent(MoveType.ATTACK, damage=self._tackle_dmg()),
        )
        spawned.follow_up = tackle
        tackle.follow_up = tackle
        return MonsterMoveStateMachine([spawned, tackle], spawned)

    def _spawned(self, ctx: CombatCtx) -> None:
        pass  # wake-up animation only

    def _tackle(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._tackle_dmg(), 1)


class FatGremlin(MachineMonster):
    """Spends its spawn turn waking up, then flees the fight (escapes,
    counting as gone for the win condition)."""
    name = "Fat Gremlin"

    min_hp = 13          # FatGremlin.cs:28-30
    max_hp = 17
    min_hp_asc = 14       # ToughEnemies (asc 8+)
    max_hp_asc = 18

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


@dataclass
class GremlinMercEncounter(Encounter):
    """`GremlinMercNormal` — the one encounter with a bespoke escape/reward
    rule (EncounterModel.cs:371 names it as THE example)."""

    def calculate_gold_proportion(self, combat) -> float:
        """`GremlinMercNormal.CalculateGoldProportion`
        (GremlinMercNormal.cs:58-69), all three arms:

            no Fat Gremlin escaped        -> 1.0  (the base formula is not used)
            it escaped, stole nothing     -> 0.5
            it escaped WITH stolen gold   -> 0.0

        `GoldWasStolen` is a flag `SurprisePower.AfterDeath` raises via
        `MarkGoldStolen` when the dying Merc's ThieveryPower total is > 0
        (SurprisePower.cs:34-38). The flag itself is NOT ported onto the
        `Encounter`: these objects are module-level singletons shared by every
        combat (C# takes a `ToMutable()` copy per run), so state parked on one
        would leak into the next fight. `combat.gold_stolen` — the combat's own
        running total of ThieveryPower steals — carries the same fact here: the
        Merc is this encounter's only thief and it cannot steal after the death
        that raises the flag, so "the dying Merc's Thievery total was > 0" and
        "this combat had any gold stolen" coincide. Neither the Merc's own
        ThieveryPower nor the Fat Gremlin's HeistPower can be read back
        instead — powers are cleared on death AND on escape, both of which have
        happened by the time rewards are generated.
        """
        if not any(isinstance(e, FatGremlin) and e.escaped for e in combat.enemies):
            return 1.0
        return 0.0 if combat.gold_stolen > 0 else 0.5


GREMLIN_MERC_NORMAL = GremlinMercEncounter(
    id="gremlin_merc_normal",
    monster_classes=[GremlinMerc],
)
