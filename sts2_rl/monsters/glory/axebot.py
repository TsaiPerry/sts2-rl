from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ..base import Encounter, Intent, MoveType
from ..state_machine import MachineMonster, MonsterMoveStateMachine, MoveState

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem

_BOOT_UP_BLOCK = 10
_BOOT_UP_STR_PER_STOCK = 3
_ONE_TWO_DMG = 9
_ONE_TWO_HITS = 2
_HAMMER_DMG = 12
_HAMMER_WEAK = 2
_HAMMER_FRAIL = 2
_DEFAULT_STOCK = 2


class Axebot(MachineMonster):
    """Boots Up (10 block + Strength), then cycles Hammer Uppercut (12 + Weak 2
    + Frail 2) and One-Two (9×2). Starts with Stock N: when it dies a fresh
    Axebot boots up in its place with one fewer Stock. Its Boot Up Strength is
    3×(2 − Stock), so later respawns come back angrier.

    The first bot of a fight (default Stock 2) opens on Hammer Uppercut; a
    respawned bot (explicit Stock) opens on Boot Up.

    Source: Axebot.cs / StockPower.cs (non-ascension values)."""

    min_hp = 70
    max_hp = 78

    def __init__(
        self,
        hooks: HookSystem,
        rng: random.Random | None = None,
        *,
        stock: int = _DEFAULT_STOCK,
        respawn: bool = False,
    ) -> None:
        self._stock = stock
        self._respawn = respawn  # read by build_machine
        super().__init__(hooks, rng or random.Random())
        if stock > 0:
            from ...cmds import PowerCmd
            from ...powers import StockPower
            PowerCmd.apply(hooks, self, StockPower, stock)

    def build_machine(self) -> MonsterMoveStateMachine:
        boot_up = MoveState(
            "BOOT_UP_MOVE", self._boot_up,
            Intent(MoveType.DEFEND, also=(MoveType.BUFF,)),
        )
        one_two = MoveState(
            "ONE_TWO_MOVE", self._one_two,
            Intent(MoveType.ATTACK, damage=_ONE_TWO_DMG, hits=_ONE_TWO_HITS),
        )
        hammer = MoveState(
            "HAMMER_UPPERCUT_MOVE", self._hammer,
            Intent(MoveType.ATTACK, damage=_HAMMER_DMG, also=(MoveType.DEBUFF,)),
        )
        boot_up.follow_up = hammer
        hammer.follow_up = one_two
        one_two.follow_up = hammer
        initial = boot_up if self._respawn else hammer
        return MonsterMoveStateMachine([boot_up, one_two, hammer], initial)

    def _boot_up(self, ctx: CombatCtx) -> None:
        from ...cmds import BlockCmd, PowerCmd
        from ...powers import StrengthPower
        from ...valueprops import ValueProp
        BlockCmd.apply(ctx.hooks, self, _BOOT_UP_BLOCK, props=ValueProp.MOVE)
        gain = _BOOT_UP_STR_PER_STOCK * (_DEFAULT_STOCK - self._stock)
        if gain:
            PowerCmd.apply(ctx.hooks, self, StrengthPower, gain)

    def _one_two(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _ONE_TWO_DMG, _ONE_TWO_HITS)

    def _hammer(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _HAMMER_DMG, 1)
        from ...cmds import PowerCmd
        from ...powers import FrailPower, WeakPower
        PowerCmd.apply(ctx.hooks, ctx.player, WeakPower, _HAMMER_WEAK)
        PowerCmd.apply(ctx.hooks, ctx.player, FrailPower, _HAMMER_FRAIL)


AXEBOTS_NORMAL = Encounter(
    id="axebots_normal",
    monster_classes=[Axebot],
)
