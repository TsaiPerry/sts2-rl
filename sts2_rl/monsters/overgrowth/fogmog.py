from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ..base import Encounter, Intent, Monster, MoveType

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem

_SWIPE_DMG = 8
_SWIPE_STR = 1
_HEADBUTT_DMG = 14


class EyeWithTeeth(Monster):
    """Summoned illusion; adds 3 Dazed cards each turn. Cannot truly die —
    IllusionPower revives it to full HP on its next turn."""
    min_hp = 6
    max_hp = 6

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())
        from ...cmds import PowerCmd
        from ...powers import IllusionPower
        PowerCmd.apply(hooks, self, IllusionPower, 1)

    @property
    def _illusion(self):
        return self.powers.get("illusion")

    @property
    def current_intent(self) -> Intent:
        # Both the revive turn and DISTRACT (3 Dazed cards) render as non-attacks.
        return Intent(MoveType.BUFF, buffs=[])

    def take_turn(self, ctx: CombatCtx) -> None:
        illusion = self._illusion
        if illusion is not None and illusion.is_reviving:
            illusion.revive()
            return
        from ...cards import DazedCard
        from ...cmds import CardPileCmd
        for _ in range(3):
            CardPileCmd.add_to_discard(ctx.hooks, ctx.player, DazedCard())


class Fogmog(Monster):
    """ILLUSION (summon Eye With Teeth) → SWIPE → 40% SWIPE / 60% HEADBUTT;
    the random SWIPE is always followed by HEADBUTT, and HEADBUTT always
    returns to SWIPE (which branches again)."""
    min_hp = 74
    max_hp = 74

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())
        self._rng = rng or random.Random()
        self._move_key = "ILLUSION"

    @property
    def current_intent(self) -> Intent:
        if self._move_key == "ILLUSION":
            return Intent(MoveType.BUFF, buffs=[])  # summon EyeWithTeeth
        if self._move_key in ("SWIPE", "SWIPE_RANDOM"):
            return Intent(MoveType.ATTACK, damage=_SWIPE_DMG)
        return Intent(MoveType.ATTACK, damage=_HEADBUTT_DMG)

    def take_turn(self, ctx: CombatCtx) -> None:
        from ...cmds import PowerCmd
        if self._move_key == "ILLUSION":
            ctx.enemies.append(EyeWithTeeth(ctx.hooks, self._rng))
            self._move_key = "SWIPE"
        elif self._move_key in ("SWIPE", "SWIPE_RANDOM"):
            self._execute_attack(ctx, _SWIPE_DMG, 1)
            from ...powers import StrengthPower
            PowerCmd.apply(ctx.hooks, self, StrengthPower, _SWIPE_STR)
            if self._move_key == "SWIPE":
                self._move_key = "SWIPE_RANDOM" if self._rng.random() < 0.4 else "HEADBUTT"
            else:
                self._move_key = "HEADBUTT"
        else:  # HEADBUTT
            self._execute_attack(ctx, _HEADBUTT_DMG, 1)
            self._move_key = "SWIPE"


FOGMOG_NORMAL = Encounter(
    id="fogmog_normal",
    monster_classes=[Fogmog],
)
