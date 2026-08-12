from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ...actmap import AscensionLevel
from ..base import Encounter, Intent, MoveType, asc_value
from ..state_machine import MachineMonster, MonsterMoveStateMachine, MoveState

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem

_THUNDER_DMG = 6           # GlobeHead.cs:33 base
_THUNDER_DMG_ASC = 7       # DeadlyEnemies (asc 9+)
_THUNDER_HITS = 3
_SLAP_DMG = 13              # GlobeHead.cs:35 base
_SLAP_DMG_ASC = 14          # DeadlyEnemies (asc 9+)
_SLAP_FRAIL = 2
_BURST_DMG = 16             # GlobeHead.cs:37 base
_BURST_DMG_ASC = 17         # DeadlyEnemies (asc 9+)
_BURST_STR = 2
_GALVANIC = 6


class GlobeHead(MachineMonster):
    """Shocking Slap (13 + Frail 2) → Thunder Strike (6×3) → Galvanic Burst (16
    + gain 2 Strength) → loop. Starts with Galvanic 6, which afflicts the
    player's Power cards with Galvanized (they zap the player for 6 when played).

    Source: GlobeHead.cs (non-ascension values)."""
    name = "Globe Head"

    min_hp = 148          # GlobeHead.cs:29 base (MaxInitialHp == MinInitialHp)
    max_hp = 148
    min_hp_asc = 158       # ToughEnemies (asc 8+)
    max_hp_asc = 158

    def _thunder_dmg(self) -> int:
        """GlobeHead.cs:33 `ThunderStrikeDamage` -- re-read at both the
        telegraphed Intent and the executed attack."""
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _THUNDER_DMG_ASC, _THUNDER_DMG)

    def _slap_dmg(self) -> int:
        """GlobeHead.cs:35 `ShockingSlapDamage`."""
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _SLAP_DMG_ASC, _SLAP_DMG)

    def _burst_dmg(self) -> int:
        """GlobeHead.cs:37 `GalvanicBurstDamage`."""
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _BURST_DMG_ASC, _BURST_DMG)

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())
        from ...cmds import PowerCmd
        from ...powers import GalvanicPower
        PowerCmd.apply(hooks, self, GalvanicPower, _GALVANIC)

    def build_machine(self) -> MonsterMoveStateMachine:
        thunder = MoveState(
            "THUNDER_STRIKE", self._thunder,
            lambda: Intent(MoveType.ATTACK, damage=self._thunder_dmg(), hits=_THUNDER_HITS),
        )
        slap = MoveState(
            "SHOCKING_SLAP", self._slap,
            lambda: Intent(MoveType.ATTACK, damage=self._slap_dmg(), also=(MoveType.DEBUFF,)),
        )
        burst = MoveState(
            "GALVANIC_BURST", self._burst,
            lambda: Intent(MoveType.ATTACK, damage=self._burst_dmg(), also=(MoveType.BUFF,)),
        )
        slap.follow_up = thunder
        thunder.follow_up = burst
        burst.follow_up = slap
        return MonsterMoveStateMachine([slap, thunder, burst], slap)

    def _thunder(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._thunder_dmg(), _THUNDER_HITS)

    def _slap(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._slap_dmg(), 1)
        from ...cmds import PowerCmd
        from ...powers import FrailPower
        PowerCmd.apply(ctx.hooks, ctx.player, FrailPower, _SLAP_FRAIL)

    def _burst(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._burst_dmg(), 1)
        from ...cmds import PowerCmd
        from ...powers import StrengthPower
        PowerCmd.apply(ctx.hooks, self, StrengthPower, _BURST_STR)


GLOBE_HEAD_NORMAL = Encounter(
    id="globe_head_normal",
    monster_classes=[GlobeHead],
)
