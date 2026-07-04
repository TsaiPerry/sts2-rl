"""Ovicopter and Tough Egg (Hive). Sources: Ovicopter.cs, ToughEgg.cs,
OvicopterNormal.cs."""
from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ..base import Encounter, Intent, MoveType
from ..state_machine import (
    ConditionalBranchState,
    MachineMonster,
    MonsterMoveStateMachine,
    MoveState,
)

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem

_SMASH_DMG = 16
_TENDERIZER_DMG = 7
_TENDERIZER_VULN = 2
_PASTE_STR = 3
_EGGS_PER_LAY = 3
_EGG_SLOTS = 5
_NIBBLE_DMG = 4


class ToughEgg(MachineMonster):
    """Egg laid by the Ovicopter: sits for a turn (Hatch countdown), then
    hatches into a Hatchling (HP rerolled to 19-22) that NIBBLEs for 4."""

    min_hp = 14
    max_hp = 18

    HATCHLING_MIN_HP = 19
    HATCHLING_MAX_HP = 22

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        self.is_hatched = False
        super().__init__(hooks, rng or random.Random())
        from ...cmds import PowerCmd
        from ...powers import HatchPower
        combat = hooks.combat
        # Eggs laid during the enemy turn show a 2-turn countdown (mirrors
        # AfterAddedToRoom's CurrentSide check).
        amount = 2 if combat is not None and combat.current_side == "enemy" else 1
        PowerCmd.apply(hooks, self, HatchPower, amount)

    def build_machine(self) -> MonsterMoveStateMachine:
        hatch = MoveState("HATCH_MOVE", self._hatch, Intent(MoveType.SUMMON))
        nibble = MoveState(
            "NIBBLE_MOVE", self._nibble, Intent(MoveType.ATTACK, damage=_NIBBLE_DMG)
        )
        hatch.follow_up = nibble
        nibble.follow_up = nibble
        return MonsterMoveStateMachine([hatch, nibble], hatch)

    def _hatch(self, ctx: CombatCtx) -> None:
        self.is_hatched = True
        # All powers except Minion fall away with the shell (mirrors HatchMove).
        from ...cmds import PowerCmd
        for power_id in [p for p in self.powers if p != "minion"]:
            PowerCmd.remove(ctx.hooks, self, power_id)
        hp = self._rng.randint(self.HATCHLING_MIN_HP, self.HATCHLING_MAX_HP)
        delta = hp - self.hp
        self.max_hp = hp
        self.hp = hp
        ctx.hooks.on_hp_changed(self, delta)

    def _nibble(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _NIBBLE_DMG, 1)


class Ovicopter(MachineMonster):
    """Opens with LAY_EGGS (up to 3 Tough Egg minions, 5 egg slots), then
    SMASH (16) → TENDERIZER (7 + Vulnerable 2) → lay again while 3 or fewer
    enemies are alive, otherwise NUTRITIONAL_PASTE (+3 Strength)."""

    min_hp = 124
    max_hp = 130

    def _can_lay(self) -> bool:
        combat = self._hooks.combat
        if combat is None:
            return True
        return sum(1 for e in combat.enemies if not e.is_gone) <= 3

    def build_machine(self) -> MonsterMoveStateMachine:
        lay = MoveState("LAY_EGGS_MOVE", self._lay_eggs, Intent(MoveType.SUMMON))
        smash = MoveState(
            "SMASH_MOVE", self._smash, Intent(MoveType.ATTACK, damage=_SMASH_DMG)
        )
        tenderizer = MoveState(
            "TENDERIZER_MOVE", self._tenderizer,
            Intent(MoveType.ATTACK, damage=_TENDERIZER_DMG, also=(MoveType.DEBUFF,)),
        )
        paste = MoveState(
            "NUTRITIONAL_PASTE_MOVE", self._paste, Intent(MoveType.BUFF)
        )
        branch = ConditionalBranchState("SUMMON_BRANCH_STATE")
        lay.follow_up = smash
        paste.follow_up = smash
        smash.follow_up = tenderizer
        tenderizer.follow_up = branch
        branch.add_state(lay, self._can_lay)
        branch.add_state(paste, lambda: not self._can_lay())
        return MonsterMoveStateMachine(
            [paste, lay, smash, tenderizer, branch], lay
        )

    def _lay_eggs(self, ctx: CombatCtx) -> None:
        from ...cmds import CreatureCmd, PowerCmd
        from ...powers import MinionPower
        for _ in range(_EGGS_PER_LAY):
            live_eggs = sum(
                1 for e in ctx.enemies if isinstance(e, ToughEgg) and not e.is_gone
            )
            if live_eggs >= _EGG_SLOTS:
                break
            egg = ToughEgg(ctx.hooks, self._rng)
            CreatureCmd.add(ctx.hooks, egg)
            PowerCmd.apply(ctx.hooks, egg, MinionPower, 1, applier=self)

    def _smash(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _SMASH_DMG, 1)

    def _tenderizer(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _TENDERIZER_DMG, 1)
        from ...cmds import PowerCmd
        from ...powers import VulnerablePower
        PowerCmd.apply(
            ctx.hooks, ctx.player, VulnerablePower, _TENDERIZER_VULN, applier=self
        )

    def _paste(self, ctx: CombatCtx) -> None:
        from ...cmds import PowerCmd
        from ...powers import StrengthPower
        PowerCmd.apply(ctx.hooks, self, StrengthPower, _PASTE_STR)


OVICOPTER_NORMAL = Encounter(
    id="ovicopter_normal",
    monster_classes=[Ovicopter],
)
