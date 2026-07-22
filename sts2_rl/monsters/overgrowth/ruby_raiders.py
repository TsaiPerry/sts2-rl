from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ..base import Encounter, Intent, Monster, MoveType

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem


class AxeRubyRaider(Monster):
    """SWING_1 (attack+block) → SWING_2 (attack+block) → BIG_SWING → cycle."""
    name = "Axe Raider"
    min_hp = 20
    max_hp = 22

    _CYCLE = ["SWING_1", "SWING_2", "BIG_SWING"]

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())
        self._step = 0

    @property
    def current_intent(self) -> Intent:
        move = self._CYCLE[self._step % 3]
        if move == "BIG_SWING":
            return Intent(MoveType.ATTACK, damage=12)
        return Intent(MoveType.ATTACK, damage=5, also=(MoveType.DEFEND,))

    def take_turn(self, ctx: CombatCtx) -> None:
        from ...cmds import BlockCmd
        move = self._CYCLE[self._step % 3]
        if move in ("SWING_1", "SWING_2"):
            self._execute_attack(ctx, 5, 1)
            BlockCmd.apply(ctx.hooks, self, 5)
        else:
            self._execute_attack(ctx, 12, 1)
        self._step += 1


class AssassinRubyRaider(Monster):
    """Always KILLSHOT."""
    name = "Assassin Raider"
    min_hp = 18
    max_hp = 23

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())

    @property
    def current_intent(self) -> Intent:
        return Intent(MoveType.ATTACK, damage=10)

    def take_turn(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, 10, 1)


class BruteRubyRaider(Monster):
    """BEAT → ROAR (3 Strength) → alternating."""
    name = "Brute Raider"
    min_hp = 30
    max_hp = 33

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())
        self._move_key = "BEAT"

    @property
    def current_intent(self) -> Intent:
        if self._move_key == "BEAT":
            return Intent(MoveType.ATTACK, damage=7)
        from ...powers import StrengthPower
        return Intent(MoveType.BUFF, buffs=[(StrengthPower, 3)])

    def take_turn(self, ctx: CombatCtx) -> None:
        from ...cmds import PowerCmd
        if self._move_key == "BEAT":
            self._execute_attack(ctx, 7, 1)
            self._move_key = "ROAR"
        else:
            from ...powers import StrengthPower
            PowerCmd.apply(ctx.hooks, self, StrengthPower, 3)
            self._move_key = "BEAT"


class CrossbowRubyRaider(Monster):
    """RELOAD (block) → FIRE (high damage) → alternating; starts with RELOAD."""
    name = "Crossbow Raider"
    min_hp = 18
    max_hp = 21

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())
        self._move_key = "RELOAD"

    @property
    def current_intent(self) -> Intent:
        if self._move_key == "RELOAD":
            return Intent(MoveType.DEFEND)  # gains block
        return Intent(MoveType.ATTACK, damage=14)

    def take_turn(self, ctx: CombatCtx) -> None:
        from ...cmds import BlockCmd
        if self._move_key == "RELOAD":
            BlockCmd.apply(ctx.hooks, self, 3)
            self._move_key = "FIRE"
        else:
            self._execute_attack(ctx, 14, 1)
            self._move_key = "RELOAD"


class TrackerRubyRaider(Monster):
    """TRACK (2 Frail) once, then HOUNDS (1×8) repeating."""
    name = "Tracker Raider"
    min_hp = 21
    max_hp = 25

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())
        self._move_key = "TRACK"

    @property
    def current_intent(self) -> Intent:
        if self._move_key == "TRACK":
            from ...powers import FrailPower
            return Intent(MoveType.DEBUFF, buffs=[(FrailPower, 2)])
        return Intent(MoveType.ATTACK, damage=1, hits=8)

    def take_turn(self, ctx: CombatCtx) -> None:
        from ...cmds import PowerCmd
        if self._move_key == "TRACK":
            from ...powers import FrailPower
            PowerCmd.apply(ctx.hooks, ctx.player, FrailPower, 2)
            self._move_key = "HOUNDS"
        else:
            self._execute_attack(ctx, 1, 8)


_ALL_RAIDERS = [
    AxeRubyRaider,
    AssassinRubyRaider,
    BruteRubyRaider,
    CrossbowRubyRaider,
    TrackerRubyRaider,
]


@dataclass
class RubyRaidersEncounter(Encounter):
    """Randomly selects 3 unique raiders from the pool of 5."""
    monster_classes: list = field(default_factory=list)

    def create_monsters(self, hooks: HookSystem, rng: random.Random, selection_rng=None) -> list[Monster]:
        if selection_rng is not None:
            # Parity (RubyRaidersNormal.GenerateMonsters): three draws WITHOUT
            # replacement (each raider's valid count is 1). Each draw's candidate
            # list is the pool in declaration order minus the already-chosen, and
            # base.Rng.NextItem picks one; the result order is the pick order.
            # _ALL_RAIDERS matches _raiderValidCounts.Keys insertion order.
            chosen: list = []
            for _ in range(3):
                items = [r for r in _ALL_RAIDERS if r not in chosen]
                chosen.append(selection_rng.next_item(items))
            return [cls(hooks, rng) for cls in chosen]
        chosen = rng.sample(_ALL_RAIDERS, 3)
        return [cls(hooks, rng) for cls in chosen]


RUBY_RAIDERS_NORMAL = RubyRaidersEncounter(id="ruby_raiders_normal")
