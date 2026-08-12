from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ...actmap import AscensionLevel
from ..base import Encounter, Intent, Monster, MoveType, asc_value

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem


_AXE_SWING_DMG = 5
_AXE_SWING_DMG_ASC = 6          # AxeRubyRaider.cs:24 DeadlyEnemies
_AXE_SWING_BLOCK = 5
_AXE_SWING_BLOCK_ASC = 6        # AxeRubyRaider.cs:26 DeadlyEnemies
_AXE_BIG_SWING_DMG = 12
_AXE_BIG_SWING_DMG_ASC = 13     # AxeRubyRaider.cs:28 DeadlyEnemies

_ASSASSIN_KILLSHOT_DMG = 10
_ASSASSIN_KILLSHOT_DMG_ASC = 11  # AssassinRubyRaider.cs:19 DeadlyEnemies

_BRUTE_BEAT_DMG = 7
_BRUTE_BEAT_DMG_ASC = 8          # BruteRubyRaider.cs:25 DeadlyEnemies


class AxeRubyRaider(Monster):
    """SWING_1 (attack+block) → SWING_2 (attack+block) → BIG_SWING → cycle."""
    name = "Axe Raider"
    min_hp = 20
    max_hp = 22
    min_hp_asc = 21   # AxeRubyRaider.cs:20 ToughEnemies
    max_hp_asc = 23   # AxeRubyRaider.cs:22 ToughEnemies

    _CYCLE = ["SWING_1", "SWING_2", "BIG_SWING"]

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())
        self._step = 0

    def _swing_dmg(self) -> int:
        """AxeRubyRaider.cs:24 `SwingDamage`."""
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _AXE_SWING_DMG_ASC, _AXE_SWING_DMG)

    def _swing_block(self) -> int:
        """AxeRubyRaider.cs:26 `SwingBlock`."""
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _AXE_SWING_BLOCK_ASC, _AXE_SWING_BLOCK)

    def _big_swing_dmg(self) -> int:
        """AxeRubyRaider.cs:28 `BigSwingDamage`."""
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _AXE_BIG_SWING_DMG_ASC, _AXE_BIG_SWING_DMG)

    @property
    def current_intent(self) -> Intent:
        move = self._CYCLE[self._step % 3]
        if move == "BIG_SWING":
            return Intent(MoveType.ATTACK, damage=self._big_swing_dmg())
        return Intent(MoveType.ATTACK, damage=self._swing_dmg(), also=(MoveType.DEFEND,))

    def take_turn(self, ctx: CombatCtx) -> None:
        from ...cmds import BlockCmd
        move = self._CYCLE[self._step % 3]
        if move in ("SWING_1", "SWING_2"):
            self._execute_attack(ctx, self._swing_dmg(), 1)
            BlockCmd.apply(ctx.hooks, self, self._swing_block())
        else:
            self._execute_attack(ctx, self._big_swing_dmg(), 1)
        self._step += 1


class AssassinRubyRaider(Monster):
    """Always KILLSHOT."""
    name = "Assassin Raider"
    min_hp = 18
    max_hp = 23
    min_hp_asc = 19   # AssassinRubyRaider.cs:15 ToughEnemies
    max_hp_asc = 24   # AssassinRubyRaider.cs:17 ToughEnemies

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())

    def _killshot_dmg(self) -> int:
        """AssassinRubyRaider.cs:19 `KillshotDamage`."""
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _ASSASSIN_KILLSHOT_DMG_ASC, _ASSASSIN_KILLSHOT_DMG)

    @property
    def current_intent(self) -> Intent:
        return Intent(MoveType.ATTACK, damage=self._killshot_dmg())

    def take_turn(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._killshot_dmg(), 1)


class BruteRubyRaider(Monster):
    """BEAT → ROAR (3 Strength) → alternating."""
    name = "Brute Raider"
    min_hp = 30
    max_hp = 33
    min_hp_asc = 31   # BruteRubyRaider.cs:21 ToughEnemies
    max_hp_asc = 34   # BruteRubyRaider.cs:23 ToughEnemies

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())
        self._move_key = "BEAT"

    def _beat_dmg(self) -> int:
        """BruteRubyRaider.cs:25 `BeatDamage`."""
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _BRUTE_BEAT_DMG_ASC, _BRUTE_BEAT_DMG)

    @property
    def current_intent(self) -> Intent:
        if self._move_key == "BEAT":
            return Intent(MoveType.ATTACK, damage=self._beat_dmg())
        from ...powers import StrengthPower
        # ROAR's Strength gain (BruteRubyRaider.cs:52) is a plain literal `3m`,
        # not an AscensionHelper call -- no-op, ported as-is.
        return Intent(MoveType.BUFF, buffs=[(StrengthPower, 3)])

    def take_turn(self, ctx: CombatCtx) -> None:
        from ...cmds import PowerCmd
        if self._move_key == "BEAT":
            self._execute_attack(ctx, self._beat_dmg(), 1)
            self._move_key = "ROAR"
        else:
            from ...powers import StrengthPower
            PowerCmd.apply(ctx.hooks, self, StrengthPower, 3)
            self._move_key = "BEAT"


class CrossbowRubyRaider(Monster):
    """RELOAD (block) → FIRE (high damage) → alternating; starts with RELOAD."""
    name = "Crossbow Raider"
    min_hp = 18              # CrossbowRubyRaider.cs:24
    max_hp = 21               # CrossbowRubyRaider.cs:26
    min_hp_asc = 19           # CrossbowRubyRaider.cs:24 -- ToughEnemies
    max_hp_asc = 22           # CrossbowRubyRaider.cs:26 -- ToughEnemies

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())
        self._move_key = "RELOAD"

    def _fire_dmg(self) -> int:
        """CrossbowRubyRaider.cs:28 `FireDamage` -- read at both the Intent
        and the executed attack."""
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES, 16, 14)

    @property
    def current_intent(self) -> Intent:
        if self._move_key == "RELOAD":
            return Intent(MoveType.DEFEND)  # gains block
        return Intent(MoveType.ATTACK, damage=self._fire_dmg())

    def take_turn(self, ctx: CombatCtx) -> None:
        from ...cmds import BlockCmd
        if self._move_key == "RELOAD":
            BlockCmd.apply(ctx.hooks, self, 3)
            self._move_key = "FIRE"
        else:
            self._execute_attack(ctx, self._fire_dmg(), 1)
            self._move_key = "RELOAD"


class TrackerRubyRaider(Monster):
    """TRACK (2 Frail) once, then HOUNDS (1×8) repeating."""
    name = "Tracker Raider"
    min_hp = 21
    max_hp = 25
    min_hp_asc = 22   # TrackerRubyRaider.cs:19 -- ToughEnemies
    max_hp_asc = 26   # TrackerRubyRaider.cs:21 -- ToughEnemies

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())
        self._move_key = "TRACK"

    def _hounds_repeat(self) -> int:
        """TrackerRubyRaider.cs:25 `HoundsRepeat` -- read at both the
        telegraphed Intent and the executed attack. HoundsDamage
        (TrackerRubyRaider.cs:23, GetValueIfAscension(DeadlyEnemies, 1, 1))
        is a no-op (asc value == base value); kept as the plain literal 1."""
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES, 9, 8)

    @property
    def current_intent(self) -> Intent:
        if self._move_key == "TRACK":
            from ...powers import FrailPower
            return Intent(MoveType.DEBUFF, buffs=[(FrailPower, 2)])
        return Intent(MoveType.ATTACK, damage=1, hits=self._hounds_repeat())

    def take_turn(self, ctx: CombatCtx) -> None:
        from ...cmds import PowerCmd
        if self._move_key == "TRACK":
            from ...powers import FrailPower
            PowerCmd.apply(ctx.hooks, ctx.player, FrailPower, 2)
            self._move_key = "HOUNDS"
        else:
            self._execute_attack(ctx, 1, self._hounds_repeat())


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
