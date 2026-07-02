from __future__ import annotations

import random
from dataclasses import dataclass, field
from functools import partial
from typing import TYPE_CHECKING

from ..base import Encounter, Intent, Monster, MoveType

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem

_SLASH_DMG = 5
_BOOMERANG_DMG = 2
_BOOMERANG_HITS = 2
_DANCE_STR = 2

_ORB_FRAILTY_DMG = 8
_ORB_WEAKNESS_DMG = 8
_BEAM_DMG = 3
_BEAM_HITS = 3
_RITUAL_STR = 2


class KinFollower(Monster):
    """QUICK_SLASH → BOOMERANG → POWER_DANCE → cycle. StartsWithDance shifts start to POWER_DANCE."""
    min_hp = 58
    max_hp = 59

    def __init__(
        self,
        hooks: HookSystem,
        rng: random.Random | None = None,
        *,
        starts_with_dance: bool = False,
    ) -> None:
        super().__init__(hooks, rng or random.Random())
        from ...cmds import PowerCmd
        from ...powers import MinionPower
        PowerCmd.apply(hooks, self, MinionPower, 1)
        self._move_key = "POWER_DANCE" if starts_with_dance else "QUICK_SLASH"

    @property
    def current_intent(self) -> Intent:
        if self._move_key == "QUICK_SLASH":
            return Intent(MoveType.ATTACK, damage=_SLASH_DMG)
        if self._move_key == "BOOMERANG":
            return Intent(MoveType.ATTACK, damage=_BOOMERANG_DMG, hits=_BOOMERANG_HITS)
        from ...powers import StrengthPower
        return Intent(MoveType.BUFF, buffs=[(StrengthPower, _DANCE_STR)])

    def take_turn(self, ctx: CombatCtx) -> None:
        from ...cmds import PowerCmd
        _transitions = {"QUICK_SLASH": "BOOMERANG", "BOOMERANG": "POWER_DANCE", "POWER_DANCE": "QUICK_SLASH"}
        if self._move_key == "QUICK_SLASH":
            self._execute_attack(ctx, _SLASH_DMG, 1)
        elif self._move_key == "BOOMERANG":
            self._execute_attack(ctx, _BOOMERANG_DMG, _BOOMERANG_HITS)
        else:
            from ...powers import StrengthPower
            PowerCmd.apply(ctx.hooks, self, StrengthPower, _DANCE_STR)
        self._move_key = _transitions[self._move_key]


class KinPriest(Monster):
    """ORB_OF_FRAILTY → ORB_OF_WEAKNESS → BEAM → RITUAL → cycle."""
    min_hp = 190
    max_hp = 190

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())
        self._move_key = "ORB_FRAILTY"

    _TRANSITIONS = {
        "ORB_FRAILTY": "ORB_WEAKNESS",
        "ORB_WEAKNESS": "BEAM",
        "BEAM": "RITUAL",
        "RITUAL": "ORB_FRAILTY",
    }

    @property
    def current_intent(self) -> Intent:
        if self._move_key == "ORB_FRAILTY":
            return Intent(MoveType.ATTACK, damage=_ORB_FRAILTY_DMG, also=(MoveType.DEBUFF,))
        if self._move_key == "ORB_WEAKNESS":
            return Intent(MoveType.ATTACK, damage=_ORB_WEAKNESS_DMG, also=(MoveType.DEBUFF,))
        if self._move_key == "BEAM":
            return Intent(MoveType.ATTACK, damage=_BEAM_DMG, hits=_BEAM_HITS)
        from ...powers import StrengthPower
        return Intent(MoveType.BUFF, buffs=[(StrengthPower, _RITUAL_STR)])

    def take_turn(self, ctx: CombatCtx) -> None:
        from ...cmds import PowerCmd
        if self._move_key == "ORB_FRAILTY":
            self._execute_attack(ctx, _ORB_FRAILTY_DMG, 1)
            from ...powers import FrailPower
            PowerCmd.apply(ctx.hooks, ctx.player, FrailPower, 1)
        elif self._move_key == "ORB_WEAKNESS":
            self._execute_attack(ctx, _ORB_WEAKNESS_DMG, 1)
            from ...powers import WeakPower
            PowerCmd.apply(ctx.hooks, ctx.player, WeakPower, 1)
        elif self._move_key == "BEAM":
            self._execute_attack(ctx, _BEAM_DMG, _BEAM_HITS)
        else:
            from ...powers import StrengthPower
            PowerCmd.apply(ctx.hooks, self, StrengthPower, _RITUAL_STR)
        self._move_key = self._TRANSITIONS[self._move_key]


@dataclass
class TheKinEncounter(Encounter):
    """KinFollower (dance start) + KinFollower + KinPriest."""
    monster_classes: list = field(default_factory=list)

    def create_monsters(self, hooks: HookSystem, rng: random.Random) -> list[Monster]:
        return [
            KinFollower(hooks, rng, starts_with_dance=True),
            KinFollower(hooks, rng),
            KinPriest(hooks, rng),
        ]


THE_KIN_BOSS = TheKinEncounter(id="the_kin_boss")
