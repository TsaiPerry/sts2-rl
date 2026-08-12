from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ...actmap import AscensionLevel
from ..base import Encounter, Intent, MoveType, asc_value
from ..state_machine import MachineMonster, MonsterMoveStateMachine, MoveState

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem

_BOOT_UP_BLOCK = 10
_BOOT_UP_BLOCK_ASC = 15     # Axebot.cs:36 DeadlyEnemies
_BOOT_UP_STR_PER_STOCK = 3
_BOOT_UP_STR_PER_STOCK_ASC = 4  # Axebot.cs:40 DeadlyEnemies
_ONE_TWO_DMG = 9
_ONE_TWO_DMG_ASC = 10       # Axebot.cs:38 DeadlyEnemies
_ONE_TWO_HITS = 2
_HAMMER_DMG = 12
_HAMMER_DMG_ASC = 14        # Axebot.cs:42 DeadlyEnemies
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
    min_hp_asc = 76      # Axebot.cs:44 ToughEnemies
    max_hp_asc = 86      # Axebot.cs:46 ToughEnemies

    def _boot_up_block(self) -> int:
        """Axebot.cs:36 `BootUpBlock`."""
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _BOOT_UP_BLOCK_ASC, _BOOT_UP_BLOCK)

    def _boot_up_str_per_stock(self) -> int:
        """Axebot.cs:40 `BootUpStrGain`."""
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _BOOT_UP_STR_PER_STOCK_ASC, _BOOT_UP_STR_PER_STOCK)

    def _one_two_dmg(self) -> int:
        """Axebot.cs:38 `OneTwoDamage`, re-read at Intent (:88) and
        execution (:113)."""
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _ONE_TWO_DMG_ASC, _ONE_TWO_DMG)

    def _hammer_dmg(self) -> int:
        """Axebot.cs:42 `HammerUppercutDamage`, re-read at Intent (:89) and
        execution (:123)."""
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _HAMMER_DMG_ASC, _HAMMER_DMG)

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
            lambda: Intent(MoveType.ATTACK, damage=self._one_two_dmg(), hits=_ONE_TWO_HITS),
        )
        hammer = MoveState(
            "HAMMER_UPPERCUT_MOVE", self._hammer,
            lambda: Intent(MoveType.ATTACK, damage=self._hammer_dmg(), also=(MoveType.DEBUFF,)),
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
        BlockCmd.apply(ctx.hooks, self, self._boot_up_block(), props=ValueProp.MOVE)
        gain = self._boot_up_str_per_stock() * (_DEFAULT_STOCK - self._stock)
        if gain:
            PowerCmd.apply(ctx.hooks, self, StrengthPower, gain)

    def _one_two(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._one_two_dmg(), _ONE_TWO_HITS)

    def _hammer(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._hammer_dmg(), 1)
        from ...cmds import PowerCmd
        from ...powers import FrailPower, WeakPower
        PowerCmd.apply(ctx.hooks, ctx.player, WeakPower, _HAMMER_WEAK)
        PowerCmd.apply(ctx.hooks, ctx.player, FrailPower, _HAMMER_FRAIL)


AXEBOTS_NORMAL = Encounter(
    id="axebots_normal",
    monster_classes=[Axebot],
    # AxebotsNormal.cs:11,19-22 — a one-name row, and GenerateMonsters seats
    # the starting Axebot in it. Nothing summons in this encounter, so the
    # row orders nothing today; declared because the sort reads it.
    slots=("front",),
    monster_slots=("front",),
)
