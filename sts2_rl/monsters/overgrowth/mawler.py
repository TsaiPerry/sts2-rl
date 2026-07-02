from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ..base import Encounter, Intent, Monster, MoveType

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem

_CLAW_DMG = 4
_CLAW_HITS = 2
_RIP_DMG = 14
_VULNERABLE_AMT = 3


class Mawler(Monster):
    """Starts with CLAW, then picks randomly each turn among RIP_AND_TEAR
    (no consecutive repeats), ROAR (usable once per combat), and CLAW
    (no consecutive repeats), all with equal weight."""
    min_hp = 72
    max_hp = 72

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())
        self._rng = rng or random.Random()
        self._move_key = "CLAW"
        self._roar_used = False

    @property
    def current_intent(self) -> Intent:
        if self._move_key == "CLAW":
            return Intent(MoveType.ATTACK, damage=_CLAW_DMG, hits=_CLAW_HITS)
        if self._move_key == "ROAR":
            from ...powers import VulnerablePower
            return Intent(MoveType.BUFF, buffs=[(VulnerablePower, _VULNERABLE_AMT)])
        return Intent(MoveType.ATTACK, damage=_RIP_DMG)

    def take_turn(self, ctx: CombatCtx) -> None:
        from ...cmds import PowerCmd
        if self._move_key == "CLAW":
            self._execute_attack(ctx, _CLAW_DMG, _CLAW_HITS)
        elif self._move_key == "RIP_AND_TEAR":
            self._execute_attack(ctx, _RIP_DMG, 1)
        else:  # ROAR
            from ...powers import VulnerablePower
            PowerCmd.apply(ctx.hooks, ctx.player, VulnerablePower, _VULNERABLE_AMT)
            self._roar_used = True
        candidates = [
            m for m in ("RIP_AND_TEAR", "ROAR", "CLAW")
            if m != self._move_key and (m != "ROAR" or not self._roar_used)
        ]
        self._move_key = self._rng.choice(candidates)


MAWLER_NORMAL = Encounter(
    id="mawler_normal",
    monster_classes=[Mawler],
)
