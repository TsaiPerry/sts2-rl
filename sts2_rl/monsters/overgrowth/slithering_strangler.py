from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ..base import Encounter, Intent, Monster, MoveType
from ..state_machine import weighted_branch_pick

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem

_THWACK_DMG = 7
_THWACK_BLOCK = 5
_LASH_DMG = 12
_CONSTRICT_AMT = 3


class SlitheringStrangler(Monster):
    name = "Slithering Strangler"
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
            return Intent(MoveType.DEBUFF, buffs=[(ConstrictPower, _CONSTRICT_AMT)])
        if self._move_key == "THWACK":
            return Intent(MoveType.ATTACK, damage=_THWACK_DMG, also=(MoveType.DEFEND,))
        return Intent(MoveType.ATTACK, damage=_LASH_DMG)

    def take_turn(self, ctx: CombatCtx) -> None:
        from ...cmds import PowerCmd, BlockCmd
        if self._move_key == "CONSTRICT":
            from ...powers import ConstrictPower
            PowerCmd.apply(ctx.hooks, ctx.player, ConstrictPower, _CONSTRICT_AMT, applier=self)
        elif self._move_key == "THWACK":
            self._execute_attack(ctx, _THWACK_DMG, 1)
            BlockCmd.apply(ctx.hooks, self, _THWACK_BLOCK)
        else:
            self._execute_attack(ctx, _LASH_DMG, 1)

    def telegraph_next_move(self) -> None:
        if self._move_key == "CONSTRICT":
            self._move_key = weighted_branch_pick(
                self._hooks.combat.combat_rng.monster_ai, ["THWACK", "LASH"], [1, 1]
            )
        else:
            self._move_key = "CONSTRICT"


@dataclass
class SlitheringStranglerEncounter(Encounter):
    """A random secondary group — a Snapping Jaxfruit, one medium slime, or two
    small slimes (independently picked, duplicates allowed) — then the Strangler."""
    monster_classes: list = field(default_factory=list)

    def create_monsters(self, hooks: HookSystem, rng: random.Random, selection_rng=None) -> list[Monster]:
        from .slimes import LeafSlimeM, LeafSlimeS, TwigSlimeM, TwigSlimeS
        from .snapping_jaxfruit import SnappingJaxfruit
        # Parity (SlitheringStranglerNormal.cs:57,77,88,90): every pick is a
        # `base.Rng.NextItem` on the PER-ENCOUNTER Rng — one over the
        # SecondaryEnemyType enum in declaration order, then 0/1/2 more over
        # _mediumSlimes / _smallSlimes ([Leaf, Twig] in both). The small-slime
        # pair is drawn WITH replacement. Legacy keeps the shared-rng picks.
        def pick(items):
            if selection_rng is not None:
                return selection_rng.next_item(items)
            return rng.choice(items)

        kind = pick(["jaxfruit", "medium_slime", "small_slimes"])
        if kind == "jaxfruit":
            secondary = [SnappingJaxfruit(hooks, rng)]
        elif kind == "medium_slime":
            secondary = [pick([LeafSlimeM, TwigSlimeM])(hooks, rng)]
        else:
            smalls = [LeafSlimeS, TwigSlimeS]
            secondary = [pick(smalls)(hooks, rng), pick(smalls)(hooks, rng)]
        return secondary + [SlitheringStrangler(hooks, rng)]


SLITHERING_STRANGLER_NORMAL = SlitheringStranglerEncounter(id="slithering_strangler_normal")
