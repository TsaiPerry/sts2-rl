from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ..base import Encounter, Intent, Monster, MoveType

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem

_THWACK_DMG = 7
_THWACK_BLOCK = 5
_LASH_DMG = 12
_CONSTRICT_AMT = 3


class SlitheringStrangler(Monster):
    min_hp = 53
    max_hp = 55

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())
        self._rng = rng or random.Random()
        self._move_key = "CONSTRICT"

    @property
    def current_intent(self) -> Intent:
        if self._move_key == "CONSTRICT":
            from ...powers import ConstrictPower
            return Intent(MoveType.BUFF, buffs=[(ConstrictPower, _CONSTRICT_AMT)])
        if self._move_key == "THWACK":
            return Intent(MoveType.ATTACK, damage=_THWACK_DMG)
        return Intent(MoveType.ATTACK, damage=_LASH_DMG)

    def take_turn(self, ctx: CombatCtx) -> None:
        from ...cmds import PowerCmd, BlockCmd
        if self._move_key == "CONSTRICT":
            from ...powers import ConstrictPower
            PowerCmd.apply(ctx.hooks, ctx.player, ConstrictPower, _CONSTRICT_AMT, applier=self)
            self._move_key = self._rng.choice(["THWACK", "LASH"])
        elif self._move_key == "THWACK":
            self._execute_attack(ctx, _THWACK_DMG, 1)
            BlockCmd.apply(ctx.hooks, self, _THWACK_BLOCK)
            self._move_key = "CONSTRICT"
        else:
            self._execute_attack(ctx, _LASH_DMG, 1)
            self._move_key = "CONSTRICT"


@dataclass
class SlitheringStranglerEncounter(Encounter):
    """A random secondary group — a Snapping Jaxfruit, one medium slime, or two
    small slimes (independently picked, duplicates allowed) — then the Strangler."""
    monster_classes: list = field(default_factory=list)

    def create_monsters(self, hooks: HookSystem, rng: random.Random) -> list[Monster]:
        from .slimes import LeafSlimeM, LeafSlimeS, TwigSlimeM, TwigSlimeS
        from .snapping_jaxfruit import SnappingJaxfruit
        kind = rng.choice(["jaxfruit", "medium_slime", "small_slimes"])
        if kind == "jaxfruit":
            secondary = [SnappingJaxfruit(hooks, rng)]
        elif kind == "medium_slime":
            secondary = [rng.choice([LeafSlimeM, TwigSlimeM])(hooks, rng)]
        else:
            smalls = [LeafSlimeS, TwigSlimeS]
            secondary = [rng.choice(smalls)(hooks, rng), rng.choice(smalls)(hooks, rng)]
        return secondary + [SlitheringStrangler(hooks, rng)]


SLITHERING_STRANGLER_NORMAL = SlitheringStranglerEncounter(id="slithering_strangler_normal")
