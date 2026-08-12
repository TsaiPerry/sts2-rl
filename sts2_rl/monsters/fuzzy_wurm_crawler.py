from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ..actmap import AscensionLevel
from .base import Encounter, Intent, Monster, MoveType, asc_value

if TYPE_CHECKING:
    from ..combat import CombatCtx
    from ..hooks import HookSystem

_ACID_GOOP_DMG = 4       # FuzzyWurmCrawler.cs:33 base
_ACID_GOOP_DMG_ASC = 6   # DeadlyEnemies (asc 9+)


class FuzzyWurmCrawler(Monster):
    min_hp = 55
    max_hp = 57
    min_hp_asc = 58      # FuzzyWurmCrawler.cs:29 ToughEnemies (asc 8+)
    max_hp_asc = 59      # FuzzyWurmCrawler.cs:31

    # (move_type, hits, strength_gain) -- ATTACK damage is resolved
    # dynamically via _acid_goop_dmg(), not stored here (DeadlyEnemies is
    # read live at both the telegraphed intent and the executed attack).
    _MOVES: dict[str, tuple[MoveType, int, int]] = {
        "FIRST_ACID_GOOP": (MoveType.ATTACK, 1, 0),
        "INHALE":          (MoveType.BUFF,   0, 7),
        "ACID_GOOP":       (MoveType.ATTACK, 1, 0),
    }

    _TRANSITIONS: dict[str, str] = {
        "FIRST_ACID_GOOP": "INHALE",
        "INHALE":          "ACID_GOOP",
        "ACID_GOOP":       "FIRST_ACID_GOOP",
    }

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())
        self._move_key = "FIRST_ACID_GOOP"

    def _acid_goop_dmg(self) -> int:
        """FuzzyWurmCrawler.cs:33 `AcidGoopDamage` -- read at both the
        telegraphed Intent (:51/:52) and the executed attack (:77)."""
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _ACID_GOOP_DMG_ASC, _ACID_GOOP_DMG)

    @property
    def current_intent(self) -> Intent:
        move_type, hits, strength_gain = self._MOVES[self._move_key]
        if move_type == MoveType.ATTACK:
            return Intent(move_type=MoveType.ATTACK, damage=self._acid_goop_dmg(), hits=hits)
        from ..powers import StrengthPower
        return Intent(move_type=MoveType.BUFF, buffs=[(StrengthPower, strength_gain)])

    def take_turn(self, ctx: CombatCtx) -> None:
        from ..cmds import PowerCmd
        intent = self.current_intent
        if intent.move_type == MoveType.ATTACK:
            self._execute_attack(ctx, intent.damage, intent.hits)
        else:
            for power_cls, amount in intent.buffs:
                PowerCmd.apply(ctx.hooks, self, power_cls, amount)
        self._advance_move()

    def _advance_move(self) -> None:
        self._move_key = self._TRANSITIONS[self._move_key]


FUZZY_WURM_ENCOUNTER = Encounter(
    id="fuzzy_wurm_crawler",
    monster_classes=[FuzzyWurmCrawler],
    # C# class FuzzyWurmCrawlerWeak — the sim id drops the tier.
    entry_slug="FUZZY_WURM_CRAWLER_WEAK",
)
