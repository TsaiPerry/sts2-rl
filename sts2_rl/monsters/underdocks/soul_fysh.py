from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ...actmap import AscensionLevel
from ..base import Encounter, Intent, MoveType, asc_value
from ..state_machine import MachineMonster, MonsterMoveStateMachine, MoveState

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem

_DE_GAS_DMG = 16          # SoulFysh.cs:54 base
_DE_GAS_DMG_ASC = 17      # DeadlyEnemies (asc 9+)
_GAZE_DMG = 7             # SoulFysh.cs:58 base
_GAZE_DMG_ASC = 8         # DeadlyEnemies
_SCREAM_DMG = 13          # SoulFysh.cs:56 base
_SCREAM_DMG_ASC = 15      # DeadlyEnemies
_SCREAM_VULN = 3
_FADE_INTANGIBLE = 2
_BECKON_COUNT = 2
_GAZE_BECKON_COUNT = 1


class SoulFysh(MachineMonster):
    """Underdocks boss. Fixed loop: BECKON (a Beckon status into the draw
    pile and one into the discard) → DE_GAS (16) → GAZE (7 + a Beckon into
    the discard) → FADE (Intangible 2) → SCREAM (13 + Vulnerable 3)."""
    name = "Soul Fysh"

    min_hp = 211          # SoulFysh.cs:50 base (MaxInitialHp == MinInitialHp)
    max_hp = 211
    min_hp_asc = 221       # ToughEnemies (asc 8+) -- SoulFysh.cs:50
    max_hp_asc = 221

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())

    def _de_gas_dmg(self) -> int:
        """SoulFysh.cs:54 `DeGasDamage`."""
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _DE_GAS_DMG_ASC, _DE_GAS_DMG)

    def _gaze_dmg(self) -> int:
        """SoulFysh.cs:58 `GazeDamage`."""
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _GAZE_DMG_ASC, _GAZE_DMG)

    def _scream_dmg(self) -> int:
        """SoulFysh.cs:56 `ScreamDamage`."""
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _SCREAM_DMG_ASC, _SCREAM_DMG)

    def build_machine(self) -> MonsterMoveStateMachine:
        beckon = MoveState(
            "BECKON_MOVE", self._beckon,
            Intent(MoveType.STATUS_CARD, status_count=_BECKON_COUNT),
        )
        de_gas = MoveState(
            "DE_GAS_MOVE", self._de_gas,
            lambda: Intent(MoveType.ATTACK, damage=self._de_gas_dmg()),
        )
        gaze = MoveState(
            "GAZE_MOVE", self._gaze,
            lambda: Intent(MoveType.ATTACK, damage=self._gaze_dmg(),
                            also=(MoveType.STATUS_CARD,), status_count=_GAZE_BECKON_COUNT),
        )
        fade = MoveState("FADE_MOVE", self._fade, Intent(MoveType.BUFF))
        scream = MoveState(
            "SCREAM_MOVE", self._scream,
            lambda: Intent(MoveType.ATTACK, damage=self._scream_dmg(),
                            also=(MoveType.DEBUFF,)),
        )
        beckon.follow_up = de_gas
        de_gas.follow_up = gaze
        gaze.follow_up = fade
        fade.follow_up = scream
        scream.follow_up = beckon
        return MonsterMoveStateMachine(
            [beckon, de_gas, gaze, scream, fade], beckon
        )

    def _beckon(self, ctx: CombatCtx) -> None:
        from ...cards import make_card
        from ...cmds import CardPileCmd
        CardPileCmd.add_to_draw(ctx.hooks, ctx.player, make_card("beckon"))
        CardPileCmd.add_to_discard(ctx.hooks, ctx.player, make_card("beckon"))

    def _de_gas(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._de_gas_dmg(), 1)

    def _gaze(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._gaze_dmg(), 1)
        from ...cards import make_card
        from ...cmds import CardPileCmd
        CardPileCmd.add_to_discard(ctx.hooks, ctx.player, make_card("beckon"))

    def _fade(self, ctx: CombatCtx) -> None:
        from ...cmds import PowerCmd
        from ...powers import IntangiblePower
        PowerCmd.apply(ctx.hooks, self, IntangiblePower, _FADE_INTANGIBLE)

    def _scream(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._scream_dmg(), 1)
        from ...cmds import PowerCmd
        from ...powers import VulnerablePower
        PowerCmd.apply(ctx.hooks, ctx.player, VulnerablePower, _SCREAM_VULN)


SOUL_FYSH_BOSS = Encounter(
    id="soul_fysh_boss",
    monster_classes=[SoulFysh],
)
