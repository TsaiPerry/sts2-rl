from __future__ import annotations

import random
from dataclasses import dataclass, field
from functools import partial
from typing import TYPE_CHECKING

from ...actmap import AscensionLevel
from ..base import Encounter, Intent, Monster, MoveType, asc_value

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem

# KinFollower.cs:67 QuickSlashDamage / :69 BoomerangDamage are DeadlyEnemies
# GetValueIfAscension(..., 5, 5) / (..., 2, 2) -- degenerate, asc == base, so
# ported as a no-op comment per the wave brief (no code change).
_SLASH_DMG = 5
_BOOMERANG_DMG = 2
_BOOMERANG_HITS = 2
_DANCE_STR = 2               # KinFollower.cs:71 base
_DANCE_STR_ASC = 3           # DeadlyEnemies (asc 9+)

_ORB_FRAILTY_DMG = 8         # KinPriest.cs:58 base
_ORB_FRAILTY_DMG_ASC = 9     # DeadlyEnemies (asc 9+)
_ORB_WEAKNESS_DMG = 8        # KinPriest.cs:60 base
_ORB_WEAKNESS_DMG_ASC = 9    # DeadlyEnemies (asc 9+)
# KinPriest.cs:62 BeamDamage is GetValueIfAscension(DeadlyEnemies, 3, 3) --
# degenerate, asc == base, so ported as a no-op comment.
_BEAM_DMG = 3
_BEAM_HITS = 3
_RITUAL_STR = 2              # KinPriest.cs:64 base
_RITUAL_STR_ASC = 3          # DeadlyEnemies (asc 9+)


class KinFollower(Monster):
    """QUICK_SLASH → BOOMERANG → POWER_DANCE → cycle. StartsWithDance shifts start to POWER_DANCE."""
    name = "Kin Follower"
    min_hp = 58
    max_hp = 59
    min_hp_asc = 62      # KinFollower.cs:63 ToughEnemies (asc 8+)
    max_hp_asc = 63      # KinFollower.cs:65 ToughEnemies (asc 8+)

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

    def _dance_str(self) -> int:
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _DANCE_STR_ASC, _DANCE_STR)

    @property
    def current_intent(self) -> Intent:
        if self._move_key == "QUICK_SLASH":
            return Intent(MoveType.ATTACK, damage=_SLASH_DMG)
        if self._move_key == "BOOMERANG":
            return Intent(MoveType.ATTACK, damage=_BOOMERANG_DMG, hits=_BOOMERANG_HITS)
        from ...powers import StrengthPower
        return Intent(MoveType.BUFF, buffs=[(StrengthPower, self._dance_str())])

    def take_turn(self, ctx: CombatCtx) -> None:
        from ...cmds import PowerCmd
        _transitions = {"QUICK_SLASH": "BOOMERANG", "BOOMERANG": "POWER_DANCE", "POWER_DANCE": "QUICK_SLASH"}
        if self._move_key == "QUICK_SLASH":
            self._execute_attack(ctx, _SLASH_DMG, 1)
        elif self._move_key == "BOOMERANG":
            self._execute_attack(ctx, _BOOMERANG_DMG, _BOOMERANG_HITS)
        else:
            from ...powers import StrengthPower
            PowerCmd.apply(ctx.hooks, self, StrengthPower, self._dance_str())
        self._move_key = _transitions[self._move_key]


class KinPriest(Monster):
    """ORB_OF_FRAILTY → ORB_OF_WEAKNESS → BEAM → RITUAL → cycle."""
    name = "Kin Priest"
    min_hp = 190
    max_hp = 190
    min_hp_asc = 199     # KinPriest.cs:54 ToughEnemies (asc 8+)
    max_hp_asc = 199     # KinPriest.cs:56 `MaxInitialHp => MinInitialHp`

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())
        self._move_key = "ORB_FRAILTY"

    _TRANSITIONS = {
        "ORB_FRAILTY": "ORB_WEAKNESS",
        "ORB_WEAKNESS": "BEAM",
        "BEAM": "RITUAL",
        "RITUAL": "ORB_FRAILTY",
    }

    def _orb_frailty_dmg(self) -> int:
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _ORB_FRAILTY_DMG_ASC, _ORB_FRAILTY_DMG)

    def _orb_weakness_dmg(self) -> int:
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _ORB_WEAKNESS_DMG_ASC, _ORB_WEAKNESS_DMG)

    def _ritual_str(self) -> int:
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _RITUAL_STR_ASC, _RITUAL_STR)

    @property
    def current_intent(self) -> Intent:
        if self._move_key == "ORB_FRAILTY":
            return Intent(MoveType.ATTACK, damage=self._orb_frailty_dmg(), also=(MoveType.DEBUFF,))
        if self._move_key == "ORB_WEAKNESS":
            return Intent(MoveType.ATTACK, damage=self._orb_weakness_dmg(), also=(MoveType.DEBUFF,))
        if self._move_key == "BEAM":
            return Intent(MoveType.ATTACK, damage=_BEAM_DMG, hits=_BEAM_HITS)
        from ...powers import StrengthPower
        return Intent(MoveType.BUFF, buffs=[(StrengthPower, self._ritual_str())])

    def take_turn(self, ctx: CombatCtx) -> None:
        from ...cmds import PowerCmd
        if self._move_key == "ORB_FRAILTY":
            self._execute_attack(ctx, self._orb_frailty_dmg(), 1)
            from ...powers import FrailPower
            PowerCmd.apply(ctx.hooks, ctx.player, FrailPower, 1)
        elif self._move_key == "ORB_WEAKNESS":
            self._execute_attack(ctx, self._orb_weakness_dmg(), 1)
            from ...powers import WeakPower
            PowerCmd.apply(ctx.hooks, ctx.player, WeakPower, 1)
        elif self._move_key == "BEAM":
            self._execute_attack(ctx, _BEAM_DMG, _BEAM_HITS)
        else:
            from ...powers import StrengthPower
            PowerCmd.apply(ctx.hooks, self, StrengthPower, self._ritual_str())
        self._move_key = self._TRANSITIONS[self._move_key]


@dataclass
class TheKinEncounter(Encounter):
    """KinFollower (dance start) + KinFollower + KinPriest."""
    # Declared for metadata consumers (the run obs' boss identity);
    # create_monsters below overrides instantiation for the dance start.
    monster_classes: list = field(
        default_factory=lambda: [KinFollower, KinFollower, KinPriest])

    def create_monsters(self, hooks: HookSystem, rng: random.Random, selection_rng=None) -> list[Monster]:
        return [
            KinFollower(hooks, rng, starts_with_dance=True),
            KinFollower(hooks, rng),
            KinPriest(hooks, rng),
        ]


THE_KIN_BOSS = TheKinEncounter(id="the_kin_boss")
