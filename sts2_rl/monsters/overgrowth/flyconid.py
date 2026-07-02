from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ..base import Encounter, Intent, Monster, MoveType
from .slimes import LeafSlimeM, TwigSlimeM

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem

_V_SPORES_VULN = 2
_FRAIL_SPORES_DMG = 8
_FRAIL_SPORES_FRAIL = 2
_SMASH_DMG = 11

_MOVES = ["V_SPORES", "FRAIL_SPORES", "SMASH"]
_WEIGHTS = [3, 2, 1]


class Flyconid(Monster):
    """Weighted random among 3 moves; no move can repeat consecutively.
    First move is FRAIL_SPORES (weight 2) or SMASH (weight 1)."""
    min_hp = 47
    max_hp = 49

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())
        self._rng = rng or random.Random()
        self._move_key = self._rng.choices(["FRAIL_SPORES", "SMASH"], weights=[2, 1])[0]

    @property
    def current_intent(self) -> Intent:
        if self._move_key == "V_SPORES":
            from ...powers import VulnerablePower
            return Intent(MoveType.DEBUFF, buffs=[(VulnerablePower, _V_SPORES_VULN)])
        if self._move_key == "FRAIL_SPORES":
            return Intent(
                MoveType.ATTACK, damage=_FRAIL_SPORES_DMG, also=(MoveType.DEBUFF,)
            )
        return Intent(MoveType.ATTACK, damage=_SMASH_DMG)

    def take_turn(self, ctx: CombatCtx) -> None:
        from ...cmds import PowerCmd
        if self._move_key == "V_SPORES":
            from ...powers import VulnerablePower
            PowerCmd.apply(ctx.hooks, ctx.player, VulnerablePower, _V_SPORES_VULN)
        elif self._move_key == "FRAIL_SPORES":
            self._execute_attack(ctx, _FRAIL_SPORES_DMG, 1)
            from ...powers import FrailPower
            PowerCmd.apply(ctx.hooks, ctx.player, FrailPower, _FRAIL_SPORES_FRAIL)
        else:
            self._execute_attack(ctx, _SMASH_DMG, 1)
        last = self._move_key
        candidates = [m for m in _MOVES if m != last]
        weights = [_WEIGHTS[_MOVES.index(m)] for m in candidates]
        self._move_key = self._rng.choices(candidates, weights=weights)[0]


@dataclass
class FlyconidEncounter(Encounter):
    """Randomly picks LeafSlimeM or TwigSlimeM alongside a Flyconid."""
    monster_classes: list = field(default_factory=list)

    def create_monsters(self, hooks: HookSystem, rng: random.Random) -> list[Monster]:
        slime_cls = rng.choice([LeafSlimeM, TwigSlimeM])
        return [slime_cls(hooks, rng), Flyconid(hooks, rng)]


FLYCONID_NORMAL = FlyconidEncounter(id="flyconid_normal")
