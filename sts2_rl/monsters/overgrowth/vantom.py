from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ...actmap import AscensionLevel
from ..base import Encounter, Intent, Monster, MoveType, asc_value

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem

_INK_BLOT_DMG = 7          # Vantom.cs:68 base
_INK_BLOT_DMG_ASC = 8      # DeadlyEnemies (asc 9+)
_INKY_LANCE_DMG = 6        # Vantom.cs:70 base
_INKY_LANCE_DMG_ASC = 7    # DeadlyEnemies (asc 9+)
_INKY_LANCE_HITS = 2
_DISMEMBER_DMG = 26        # Vantom.cs:72 base
_DISMEMBER_DMG_ASC = 30    # DeadlyEnemies (asc 9+)
_DISMEMBER_WOUNDS = 3     # Vantom.cs:34 _dismemberWounds; also StatusIntent(3) at :119
_PREPARE_STR = 2
_SLIPPERY_START = 8        # Vantom.cs:64 base
_SLIPPERY_START_ASC = 9    # ToughEnemies (asc 8+)

_TRANSITIONS = {
    "INK_BLOT": "INKY_LANCE",
    "INKY_LANCE": "DISMEMBER",
    "DISMEMBER": "PREPARE",
    "PREPARE": "INK_BLOT",
}


class Vantom(Monster):
    min_hp = 173         # Vantom.cs:62 base (MaxInitialHp == MinInitialHp)
    max_hp = 173
    min_hp_asc = 183     # Vantom.cs:62 ToughEnemies (asc 8+)
    max_hp_asc = 183

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())
        from ...cmds import PowerCmd
        from ...powers import SlipperyPower
        slippery = asc_value(hooks, AscensionLevel.TOUGH_ENEMIES,
                              _SLIPPERY_START_ASC, _SLIPPERY_START)
        PowerCmd.apply(hooks, self, SlipperyPower, slippery)
        self._move_key = "INK_BLOT"

    def _ink_blot_dmg(self) -> int:
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _INK_BLOT_DMG_ASC, _INK_BLOT_DMG)

    def _inky_lance_dmg(self) -> int:
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _INKY_LANCE_DMG_ASC, _INKY_LANCE_DMG)

    def _dismember_dmg(self) -> int:
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _DISMEMBER_DMG_ASC, _DISMEMBER_DMG)

    @property
    def current_intent(self) -> Intent:
        if self._move_key == "INK_BLOT":
            return Intent(MoveType.ATTACK, damage=self._ink_blot_dmg())
        if self._move_key == "INKY_LANCE":
            return Intent(MoveType.ATTACK, damage=self._inky_lance_dmg(), hits=_INKY_LANCE_HITS)
        if self._move_key == "DISMEMBER":
            # Vantom.cs:119 — SingleAttackIntent(26) AND StatusIntent(3). The
            # intent must carry the C# StatusIntent's CardCount, not just the
            # STATUS_CARD flag bit. monster/_intent_count_lost is NOT closed:
            # the spec has 18 `new StatusIntent(N)` sites and only 5 are
            # ported (round 13 R11 fix pass corrected the earlier "4 known
            # sites, all done" claim). See test_monster_tier_families.py's
            # census ledger for the 13 that remain.
            return Intent(MoveType.ATTACK, damage=self._dismember_dmg(),
                          also=(MoveType.STATUS_CARD,),
                          status_count=_DISMEMBER_WOUNDS)
        from ...powers import StrengthPower
        return Intent(MoveType.BUFF, buffs=[(StrengthPower, _PREPARE_STR)])

    def take_turn(self, ctx: CombatCtx) -> None:
        from ...cmds import PowerCmd
        if self._move_key == "INK_BLOT":
            self._execute_attack(ctx, self._ink_blot_dmg(), 1)
        elif self._move_key == "INKY_LANCE":
            self._execute_attack(ctx, self._inky_lance_dmg(), _INKY_LANCE_HITS)
        elif self._move_key == "DISMEMBER":
            self._execute_attack(ctx, self._dismember_dmg(), 1)
            from ...cards import WoundCard
            from ...cmds import CardPileCmd
            for _ in range(_DISMEMBER_WOUNDS):
                CardPileCmd.add_to_discard(ctx.hooks, ctx.player, WoundCard())
        else:
            from ...powers import StrengthPower
            PowerCmd.apply(ctx.hooks, self, StrengthPower, _PREPARE_STR)
        self._move_key = _TRANSITIONS[self._move_key]


VANTOM_BOSS = Encounter(
    id="vantom_boss",
    monster_classes=[Vantom],
)
