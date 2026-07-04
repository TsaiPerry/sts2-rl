"""Knowledge Demon (Hive boss). Sources: KnowledgeDemon.cs,
KnowledgeDemonBoss.cs."""
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

_SLAP_DMG = 17
_OVERWHELM_DMG = 8
_OVERWHELM_HITS = 3
_PONDER_DMG = 11
_PONDER_HEAL = 30
_PONDER_STR = 2
_DISINTEGRATION_DMG = (6, 7, 8)


class KnowledgeDemon(MachineMonster):
    """CURSE_OF_KNOWLEDGE (choose one of two permanent curses; three times
    total, with escalating Disintegration damage) → SLAP (17) →
    KNOWLEDGE_OVERWHELMING (8x3) → PONDER (11 + heal 30 + 2 Strength) →
    back to the curse until all three are given.

    The curse choice goes through CombatState.select_cards with purpose
    "curse_of_knowledge" (random unless a card_selector is installed); the
    chosen card's power is applied to the player immediately, mirroring
    KnowledgeDemon.IChoosable.OnChosen."""

    min_hp = 379
    max_hp = 379

    def __init__(self, hooks, rng: random.Random | None = None) -> None:
        self.curse_counter = 0
        super().__init__(hooks, rng or random.Random())

    def build_machine(self) -> MonsterMoveStateMachine:
        curse = MoveState(
            "CURSE_OF_KNOWLEDGE_MOVE", self._curse, Intent(MoveType.DEBUFF)
        )
        slap = MoveState(
            "SLAP_MOVE", self._slap, Intent(MoveType.ATTACK, damage=_SLAP_DMG)
        )
        overwhelm = MoveState(
            "KNOWLEDGE_OVERWHELMING_MOVE", self._overwhelm,
            Intent(MoveType.ATTACK, damage=_OVERWHELM_DMG, hits=_OVERWHELM_HITS),
        )
        ponder = MoveState(
            "PONDER_MOVE", self._ponder,
            Intent(MoveType.ATTACK, damage=_PONDER_DMG,
                   also=(MoveType.HEAL, MoveType.BUFF)),
        )
        branch = ConditionalBranchState("CurseOfKnowledgeBranch")
        curse.follow_up = slap
        slap.follow_up = overwhelm
        overwhelm.follow_up = ponder
        ponder.follow_up = branch
        branch.add_state(curse, lambda: self.curse_counter < 3)
        branch.add_state(slap, lambda: self.curse_counter >= 3)
        return MonsterMoveStateMachine(
            [branch, curse, slap, ponder, overwhelm], curse
        )

    def _curse(self, ctx: CombatCtx) -> None:
        from ...cards import DisintegrationCard, MindRotCard, SlothCard, WasteAwayCard
        from ...cmds import PowerCmd
        other_cls = (MindRotCard, SlothCard, WasteAwayCard)[self.curse_counter]
        disintegration = DisintegrationCard()
        disintegration.power_amount = _DISINTEGRATION_DMG[self.curse_counter]
        choices = [disintegration, other_cls()]
        chosen = ctx.combat.select_cards("curse_of_knowledge", choices, 1)
        if chosen:
            card = chosen[0]
            PowerCmd.apply(
                ctx.hooks, ctx.player, card.power_cls, card.power_amount, applier=self
            )
        self.curse_counter += 1

    def _slap(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _SLAP_DMG, 1)

    def _overwhelm(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _OVERWHELM_DMG, _OVERWHELM_HITS)

    def _ponder(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _PONDER_DMG, 1)
        from ...cmds import CreatureCmd, PowerCmd
        from ...powers import StrengthPower
        CreatureCmd.heal(ctx.hooks, self, _PONDER_HEAL)
        PowerCmd.apply(ctx.hooks, self, StrengthPower, _PONDER_STR)


KNOWLEDGE_DEMON_BOSS = Encounter(
    id="knowledge_demon_boss",
    monster_classes=[KnowledgeDemon],
)
