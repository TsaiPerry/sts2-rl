from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ..base import Encounter, Intent, Monster, MoveType
from ..state_machine import weighted_branch_pick
from .slimes import LeafSlimeM, TwigSlimeM

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem

_V_SPORES_VULN = 2
_FRAIL_SPORES_DMG = 8
_FRAIL_SPORES_FRAIL = 2
_SMASH_DMG = 11

# Source: Flyconid.cs GenerateMoveStateMachine. All three moves have base
# weight 1; the "3/2/1" are COOLDOWNS (StateWeight.cooldown), not weights, and
# every branch is CannotRepeat. A move is ineligible (weight 0) if it appears
# in the last `cooldown` performed moves (SMASH's cooldown 0 → only its
# CannotRepeat "not the immediately-previous move" applies). Branch add-order
# (matters for the single-NextFloat walk): V_SPORES, FRAIL_SPORES, SMASH.
_MOVES = ["V_SPORES", "FRAIL_SPORES", "SMASH"]
_COOLDOWN = {"V_SPORES": 3, "FRAIL_SPORES": 2, "SMASH": 0}


class Flyconid(Monster):
    """Equal-weight random among 3 moves gated by per-move cooldowns (V_SPORES
    3, FRAIL_SPORES 2, SMASH 0) + CannotRepeat. The INITIAL state offers only
    FRAIL_SPORES / SMASH (both weight 1 → 50/50), never V_SPORES."""
    min_hp = 47
    max_hp = 49

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())
        self._rng = rng or random.Random()
        self._log: list[str] = []  # performed moves, newest last (StateLog IsMove)
        # INITIAL RandomBranchState: FRAIL_SPORES / SMASH only, both weight 1.
        self._move_key = weighted_branch_pick(
            hooks.combat.combat_rng.monster_ai, ["FRAIL_SPORES", "SMASH"], [1, 1]
        )

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
        self._log.append(self._move_key)
        self.telegraph_next_move()

    def telegraph_next_move(self) -> None:
        # RAND state: all three moves weight 1, gated by cooldown + CannotRepeat.
        # A move is eligible unless it appears within its cooldown window of the
        # move log (SMASH cooldown 0 → CannotRepeat = not the last move only).
        # One NextFloat(total) is drawn every transition regardless (MonsterAi
        # counter unchanged), so roll over the full [V, FRAIL, SMASH] order.
        weights = []
        for m in _MOVES:
            cd = _COOLDOWN[m]
            window = self._log[-cd:] if cd > 0 else self._log[-1:]
            weights.append(0 if m in window else 1)
        self._move_key = weighted_branch_pick(
            self._hooks.combat.combat_rng.monster_ai, _MOVES, weights
        )


@dataclass
class FlyconidEncounter(Encounter):
    """Randomly picks LeafSlimeM or TwigSlimeM alongside a Flyconid."""
    monster_classes: list = field(default_factory=list)

    def create_monsters(self, hooks: HookSystem, rng: random.Random, selection_rng=None) -> list[Monster]:
        if selection_rng is not None:
            # Parity (FlyconidNormal.GenerateMonsters): one NextItem over
            # _mediumSlimes = [LeafSlimeM, TwigSlimeM] (that order), then a
            # Flyconid in slot 1.
            slime_cls = selection_rng.next_item([LeafSlimeM, TwigSlimeM])
            return [slime_cls(hooks, rng), Flyconid(hooks, rng)]
        slime_cls = rng.choice([LeafSlimeM, TwigSlimeM])
        return [slime_cls(hooks, rng), Flyconid(hooks, rng)]


FLYCONID_NORMAL = FlyconidEncounter(id="flyconid_normal")
