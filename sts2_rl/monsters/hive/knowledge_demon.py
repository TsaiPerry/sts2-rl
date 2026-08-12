"""Knowledge Demon (Hive boss). Sources: KnowledgeDemon.cs,
KnowledgeDemonBoss.cs."""
from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ...actmap import AscensionLevel
from ..base import Encounter, Intent, MoveType, asc_value
from ..state_machine import (
    ConditionalBranchState,
    MachineMonster,
    MonsterMoveStateMachine,
    MoveState,
)

if TYPE_CHECKING:
    from ...combat import CombatCtx

_SLAP_DMG = 17               # KnowledgeDemon.cs:101 base
_SLAP_DMG_ASC = 18           # DeadlyEnemies (asc 9+)
_OVERWHELM_DMG = 8           # KnowledgeDemon.cs:105 base
_OVERWHELM_DMG_ASC = 9       # DeadlyEnemies (asc 9+)
_OVERWHELM_HITS = 3
_PONDER_DMG = 11             # KnowledgeDemon.cs:103 base
_PONDER_DMG_ASC = 13         # DeadlyEnemies (asc 9+)
_PONDER_HEAL = 30
_PONDER_STR = 2              # KnowledgeDemon.cs:107 base
_PONDER_STR_ASC = 3          # DeadlyEnemies (asc 9+)
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
    name = "Knowledge Demon"

    min_hp = 379
    max_hp = 379
    min_hp_asc = 399     # KnowledgeDemon.cs:97 ToughEnemies (asc 8+)
    max_hp_asc = 399     # KnowledgeDemon.cs:99 `MaxInitialHp => MinInitialHp`

    def __init__(self, hooks, rng: random.Random | None = None) -> None:
        self.curse_counter = 0
        super().__init__(hooks, rng or random.Random())

    def _slap_dmg(self) -> int:
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _SLAP_DMG_ASC, _SLAP_DMG)

    def _overwhelm_dmg(self) -> int:
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _OVERWHELM_DMG_ASC, _OVERWHELM_DMG)

    def _ponder_dmg(self) -> int:
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _PONDER_DMG_ASC, _PONDER_DMG)

    def _ponder_str(self) -> int:
        return asc_value(self._hooks, AscensionLevel.DEADLY_ENEMIES,
                          _PONDER_STR_ASC, _PONDER_STR)

    def build_machine(self) -> MonsterMoveStateMachine:
        curse = MoveState(
            "CURSE_OF_KNOWLEDGE_MOVE", self._curse, Intent(MoveType.DEBUFF)
        )
        slap = MoveState(
            "SLAP_MOVE", self._slap,
            lambda: Intent(MoveType.ATTACK, damage=self._slap_dmg()),
        )
        overwhelm = MoveState(
            "KNOWLEDGE_OVERWHELMING_MOVE", self._overwhelm,
            lambda: Intent(MoveType.ATTACK, damage=self._overwhelm_dmg(),
                            hits=_OVERWHELM_HITS),
        )
        ponder = MoveState(
            "PONDER_MOVE", self._ponder,
            lambda: Intent(MoveType.ATTACK, damage=self._ponder_dmg(),
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
        # KnowledgeDemon.cs:183 -- `FromChooseACardScreen(new
        # BlockingPlayerChoiceContext(), cards, target.Player)`; no
        # auto-select shortcut (CardSelectCmd.cs:216-261) -- has_shortcut=False.
        # Always 2 candidates today so this is currently unobservable, but the
        # architecture must not depend on that.
        chosen = ctx.combat.select_cards(
            "curse_of_knowledge", choices, 1, has_shortcut=False)
        if chosen:
            card = chosen[0]
            # Disintegration.cs:27 / MindRot.cs:27 / Sloth.cs:27 /
            # WasteAway.cs:30 all read `PowerCmd.Apply<XPower>(...,
            # base.Owner.Creature, amount, base.Owner.Creature, this)` -- the
            # CARD applies its own power with the PLAYER (base.Owner.Creature)
            # as BOTH target and applier, and itself (`this`) as the card
            # source. The port previously applied with the demon (`self`) as
            # applier; PowerCmd.apply has no card-source parameter at all
            # (architecture-wide -- see the report), so only the applier half
            # is fixable here. monster/knowledge_demon/g1.
            PowerCmd.apply(
                ctx.hooks, ctx.player, card.power_cls, card.power_amount,
                applier=ctx.player,
            )
        self.curse_counter += 1

    def _slap(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._slap_dmg(), 1)

    def _overwhelm(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._overwhelm_dmg(), _OVERWHELM_HITS)

    def _ponder(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, self._ponder_dmg(), 1)
        from ...cmds import CreatureCmd, PowerCmd
        from ...powers import StrengthPower
        CreatureCmd.heal(ctx.hooks, self, _PONDER_HEAL)
        PowerCmd.apply(ctx.hooks, self, StrengthPower, self._ponder_str())


KNOWLEDGE_DEMON_BOSS = Encounter(
    id="knowledge_demon_boss",
    monster_classes=[KnowledgeDemon],
)
