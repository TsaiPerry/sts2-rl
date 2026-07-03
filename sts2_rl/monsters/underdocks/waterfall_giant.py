from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ..base import Encounter, Intent, MoveType
from ..state_machine import MachineMonster, MonsterMoveStateMachine, MoveState

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem

_PRESSURIZE_AMT = 15
_MOVE_STEAM_GAIN = 3
_STOMP_DMG = 15
_STOMP_WEAK = 1
_RAM_DMG = 10
_SIPHON_HEAL = 10
_BASE_PRESSURE_GUN_DMG = 20
_PRESSURE_GUN_INCREASE = 5
_PRESSURE_UP_DMG = 13


class WaterfallGiant(MachineMonster):
    """Underdocks boss. Opens with PRESSURIZE (Steam Eruption 15), then loops
    STOMP (15 + Weak 1) → RAM (10) → SIPHON (heal 10) → PRESSURE_GUN (20,
    +5 per use) → PRESSURE_UP (13) → STOMP…, every move adding 3 Steam
    Eruption. Killing it flips it into ABOUT_TO_BLOW (a lost turn) and then
    EXPLODE: all banked Steam Eruption as one attack, and it dies in the
    blast."""

    min_hp = 240
    max_hp = 240

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        self.is_about_to_blow = False
        self._pressure_gun_dmg = _BASE_PRESSURE_GUN_DMG
        self._steam_eruption_dmg = 0
        super().__init__(hooks, rng or random.Random())

    def build_machine(self) -> MonsterMoveStateMachine:
        pressurize = MoveState(
            "PRESSURIZE_MOVE", self._pressurize, Intent(MoveType.BUFF)
        )
        stomp = MoveState(
            "STOMP_MOVE", self._stomp,
            Intent(MoveType.ATTACK, damage=_STOMP_DMG,
                   also=(MoveType.DEBUFF, MoveType.BUFF)),
        )
        ram = MoveState(
            "RAM_MOVE", self._ram,
            Intent(MoveType.ATTACK, damage=_RAM_DMG, also=(MoveType.BUFF,)),
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
            Intent(MoveType.ATTACK, damage=_PRESSURE_UP_DMG,
                   also=(MoveType.BUFF,)),
        )
        about_to_blow = MoveState(
            "ABOUT_TO_BLOW_MOVE", self._about_to_blow, Intent(MoveType.STUN),
            must_perform_once_before_transitioning=True,
        )
        explode = MoveState(
            "EXPLODE_MOVE", self._explode,
            lambda: Intent(MoveType.DEATH_BLOW,
                           damage=self._steam_eruption_dmg),
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
        self._gain_steam(ctx, _PRESSURIZE_AMT)

    def _stomp(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _STOMP_DMG, 1)
        from ...cmds import PowerCmd
        from ...powers import WeakPower
        PowerCmd.apply(ctx.hooks, ctx.player, WeakPower, _STOMP_WEAK)
        self._gain_steam(ctx, _MOVE_STEAM_GAIN)

    def _ram(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _RAM_DMG, 1)
        self._gain_steam(ctx, _MOVE_STEAM_GAIN)

    def _siphon(self, ctx: CombatCtx) -> None:
        from ...cmds import CreatureCmd
        CreatureCmd.heal(ctx.hooks, self, _SIPHON_HEAL)
        self._gain_steam(ctx, _MOVE_STEAM_GAIN)

    def _pressure_gun(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._pressure_gun_dmg, 1)
        self._pressure_gun_dmg += _PRESSURE_GUN_INCREASE
        self._gain_steam(ctx, _MOVE_STEAM_GAIN)

    def _pressure_up(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _PRESSURE_UP_DMG, 1)
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
