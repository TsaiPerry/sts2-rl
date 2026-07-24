from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ..base import Encounter, Intent, MoveType
from ..state_machine import MachineMonster, MonsterMoveStateMachine, MoveState

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem

_SMOG_STEAL = 2
_EYE_LASERS_DMG = 4
_EYE_LASERS_HITS = 2
_MIASMA_STEAL = 2
_MIASMA_BLOCK = 8
_DREAD_BASE = 13


class TheLost(MachineMonster):
    """Debilitating Smog (steal 2 Strength from the player) → Eye Lasers (4×2) →
    loop. Starts with Possess Strength: all the Strength it drains is returned
    to the player when it dies.

    Source: TheLost.cs (non-ascension values)."""
    name = "The Lost"

    min_hp = 93
    max_hp = 93

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())
        from ...cmds import PowerCmd
        from ...powers import PossessStrengthPower
        PowerCmd.apply(hooks, self, PossessStrengthPower, 1)

    def build_machine(self) -> MonsterMoveStateMachine:
        smog = MoveState(
            "DEBILITATING_SMOG", self._smog,
            Intent(MoveType.DEBUFF, also=(MoveType.BUFF,)),
        )
        lasers = MoveState(
            "EYE_LASERS", self._lasers,
            Intent(MoveType.ATTACK, damage=_EYE_LASERS_DMG, hits=_EYE_LASERS_HITS),
        )
        smog.follow_up = lasers
        lasers.follow_up = smog
        return MonsterMoveStateMachine([smog, lasers], smog)

    def _smog(self, ctx: CombatCtx) -> None:
        from ...cmds import PowerCmd
        from ...powers import StrengthPower
        PowerCmd.apply(ctx.hooks, ctx.player, StrengthPower, -_SMOG_STEAL, applier=self)
        PowerCmd.apply(ctx.hooks, self, StrengthPower, _SMOG_STEAL)

    def _lasers(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _EYE_LASERS_DMG, _EYE_LASERS_HITS)


class TheForgotten(MachineMonster):
    """Miasma (steal 2 Dexterity, gain 8 block) → Dread (13 + own Dexterity) →
    loop. Starts with Possess Speed: all the Dexterity it drains is returned to
    the player when it dies.

    Source: TheForgotten.cs (non-ascension values)."""
    name = "The Forgotten"

    min_hp = 106
    max_hp = 106

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())
        from ...cmds import PowerCmd
        from ...powers import PossessSpeedPower
        PowerCmd.apply(hooks, self, PossessSpeedPower, 1)

    def _dread_damage(self) -> int:
        dex = self.powers.get("dexterity")
        return _DREAD_BASE + (dex.amount if dex is not None else 0)

    def build_machine(self) -> MonsterMoveStateMachine:
        miasma = MoveState(
            "MIASMA", self._miasma,
            Intent(MoveType.DEBUFF, also=(MoveType.DEFEND, MoveType.BUFF)),
        )
        dread = MoveState(
            "DREAD", self._dread,
            lambda: Intent(MoveType.ATTACK, damage=self._dread_damage()),
        )
        miasma.follow_up = dread
        dread.follow_up = miasma
        return MonsterMoveStateMachine([miasma, dread], miasma)

    def _miasma(self, ctx: CombatCtx) -> None:
        from ...cmds import BlockCmd, PowerCmd
        from ...powers import DexterityPower
        from ...valueprops import ValueProp
        PowerCmd.apply(ctx.hooks, ctx.player, DexterityPower, -_MIASMA_STEAL, applier=self)
        BlockCmd.apply(ctx.hooks, self, _MIASMA_BLOCK, props=ValueProp.MOVE)
        PowerCmd.apply(ctx.hooks, self, DexterityPower, _MIASMA_STEAL)

    def _dread(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._dread_damage(), 1)


THE_LOST_AND_FORGOTTEN_NORMAL = Encounter(
    id="the_lost_and_forgotten_normal",
    monster_classes=[TheLost, TheForgotten],
)
