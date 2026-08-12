from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ...actmap import AscensionLevel
from ..base import Encounter, Intent, MoveType, asc_value
from ..state_machine import MachineMonster, MonsterMoveStateMachine, MoveState

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem

_PRESSURIZE_AMT = 15        # WaterfallGiant.cs:74 base
_PRESSURIZE_AMT_ASC = 20    # DeadlyEnemies
_MOVE_STEAM_GAIN = 3
_STOMP_DMG = 15              # WaterfallGiant.cs:76 base
_STOMP_DMG_ASC = 16          # DeadlyEnemies
_STOMP_WEAK = 1
_RAM_DMG = 10                # WaterfallGiant.cs:78 base
_RAM_DMG_ASC = 11            # DeadlyEnemies
_SIPHON_HEAL = 10            # WaterfallGiant.cs:72 base
_SIPHON_HEAL_ASC = 15        # ToughEnemies
_BASE_PRESSURE_GUN_DMG = 20  # WaterfallGiant.cs:82 base
_BASE_PRESSURE_GUN_DMG_ASC = 23  # DeadlyEnemies
_PRESSURE_GUN_INCREASE = 5
_PRESSURE_UP_DMG = 13        # WaterfallGiant.cs:80 base
_PRESSURE_UP_DMG_ASC = 14    # DeadlyEnemies


class WaterfallGiant(MachineMonster):
    """Underdocks boss. Opens with PRESSURIZE (Steam Eruption 15), then loops
    STOMP (15 + Weak 1) → RAM (10) → SIPHON (heal 10) → PRESSURE_GUN (20,
    +5 per use) → PRESSURE_UP (13) → STOMP…, every move adding 3 Steam
    Eruption. Killing it flips it into ABOUT_TO_BLOW (a lost turn) and then
    EXPLODE: all banked Steam Eruption as one attack, and it dies in the
    blast."""
    name = "Waterfall Giant"

    min_hp = 240
    max_hp = 240
    # WaterfallGiant.cs:68-70 -- MinInitialHp is ToughEnemies-gated (250 vs
    # 240); MaxInitialHp `=> MinInitialHp` always mirrors it, so both bounds
    # move together (degenerate no-op range, not a separate site).
    min_hp_asc = 250
    max_hp_asc = 250

    def _pressurize_amt(self) -> int:
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _PRESSURIZE_AMT_ASC, _PRESSURIZE_AMT)

    def _stomp_dmg(self) -> int:
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _STOMP_DMG_ASC, _STOMP_DMG)

    def _ram_dmg(self) -> int:
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _RAM_DMG_ASC, _RAM_DMG)

    def _siphon_heal(self) -> int:
        return asc_value(self._hooks, AscensionLevel.TOUGH_ENEMIES,
                          _SIPHON_HEAL_ASC, _SIPHON_HEAL)

    def _pressure_up_dmg(self) -> int:
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _PRESSURE_UP_DMG_ASC, _PRESSURE_UP_DMG)

    def _base_pressure_gun_dmg(self) -> int:
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _BASE_PRESSURE_GUN_DMG_ASC, _BASE_PRESSURE_GUN_DMG)

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        self.is_about_to_blow = False
        self._steam_eruption_dmg = 0
        super().__init__(hooks, rng or random.Random())
        # WaterfallGiant.cs:162 `CurrentPressureGunDamage = BasePressureGunDamage`
        # -- set once at AfterAddedToRoom, so only the STARTING value is
        # asc-gated; the sim mirrors that by reading the helper post-super()
        # (self._hooks is set there) rather than caching the module constant.
        self._pressure_gun_dmg = self._base_pressure_gun_dmg()

    def build_machine(self) -> MonsterMoveStateMachine:
        pressurize = MoveState(
            "PRESSURIZE_MOVE", self._pressurize, Intent(MoveType.BUFF)
        )
        stomp = MoveState(
            "STOMP_MOVE", self._stomp,
            lambda: Intent(MoveType.ATTACK, damage=self._stomp_dmg(),
                            also=(MoveType.DEBUFF, MoveType.BUFF)),
        )
        ram = MoveState(
            "RAM_MOVE", self._ram,
            lambda: Intent(MoveType.ATTACK, damage=self._ram_dmg(), also=(MoveType.BUFF,)),
        )
        siphon = MoveState(
            "SIPHON_MOVE", self._siphon,
            Intent(MoveType.HEAL, also=(MoveType.BUFF,)),
        )
        pressure_gun = MoveState(
            "PRESSURE_GUN_MOVE", self._pressure_gun,
            lambda: Intent(MoveType.ATTACK, damage=self._pressure_gun_dmg,
                           also=(MoveType.BUFF,)),
        )
        pressure_up = MoveState(
            "PRESSURE_UP_MOVE", self._pressure_up,
            lambda: Intent(MoveType.ATTACK, damage=self._pressure_up_dmg(),
                            also=(MoveType.BUFF,)),
        )
        about_to_blow = MoveState(
            "ABOUT_TO_BLOW_MOVE", self._about_to_blow, Intent(MoveType.STUN),
            must_perform_once_before_transitioning=True,
        )
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
            lambda: Intent(MoveType.DEATH_BLOW,
                           damage=self._steam_eruption_dmg,
                           also=(MoveType.ATTACK,)),
        )
        pressurize.follow_up = stomp
        stomp.follow_up = ram
        ram.follow_up = siphon
        siphon.follow_up = pressure_gun
        pressure_gun.follow_up = pressure_up
        pressure_up.follow_up = stomp
        about_to_blow.follow_up = explode
        explode.follow_up = explode
        return MonsterMoveStateMachine(
            [pressurize, stomp, ram, siphon, pressure_gun, pressure_up,
             explode, about_to_blow],
            pressurize,
        )

    def trigger_about_to_blow(self) -> None:
        """Called by SteamEruptionPower when a killing blow lands (mirrors
        TriggerAboutToBlowState): the giant becomes unkillable and spends its
        next turn ABOUT_TO_BLOW before EXPLODE."""
        if self.is_about_to_blow:
            return
        self.is_about_to_blow = True
        about_to_blow = self.machine.states["ABOUT_TO_BLOW_MOVE"]
        self.machine.force_current_state(about_to_blow)
        self._current_move = about_to_blow

    def _gain_steam(self, ctx: CombatCtx, amount: int) -> None:
        from ...cmds import PowerCmd
        from ...powers import SteamEruptionPower
        PowerCmd.apply(ctx.hooks, self, SteamEruptionPower, amount)

    def _pressurize(self, ctx: CombatCtx) -> None:
        self._gain_steam(ctx, self._pressurize_amt())

    def _stomp(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._stomp_dmg(), 1)
        from ...cmds import PowerCmd
        from ...powers import WeakPower
        PowerCmd.apply(ctx.hooks, ctx.player, WeakPower, _STOMP_WEAK)
        self._gain_steam(ctx, _MOVE_STEAM_GAIN)

    def _ram(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._ram_dmg(), 1)
        self._gain_steam(ctx, _MOVE_STEAM_GAIN)

    def _siphon(self, ctx: CombatCtx) -> None:
        from ...cmds import CreatureCmd
        CreatureCmd.heal(ctx.hooks, self, self._siphon_heal())
        self._gain_steam(ctx, _MOVE_STEAM_GAIN)

    def _pressure_gun(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._pressure_gun_dmg, 1)
        self._pressure_gun_dmg += _PRESSURE_GUN_INCREASE
        self._gain_steam(ctx, _MOVE_STEAM_GAIN)

    def _pressure_up(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._pressure_up_dmg(), 1)
        self._gain_steam(ctx, _MOVE_STEAM_GAIN)

    def _about_to_blow(self, ctx: CombatCtx) -> None:
        from ...cmds import PowerCmd
        steam = self.powers.get("steam_eruption")
        self._steam_eruption_dmg = steam.amount if steam is not None else 0
        PowerCmd.remove(ctx.hooks, self, "steam_eruption")

    def _explode(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._steam_eruption_dmg, 1)
        from ...cmds import CreatureCmd
        CreatureCmd.kill(ctx.hooks, self)


WATERFALL_GIANT_BOSS = Encounter(
    id="waterfall_giant_boss",
    monster_classes=[WaterfallGiant],
)
