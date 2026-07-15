from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ..base import Encounter, Intent, MoveType
from ..state_machine import MachineMonster, MonsterMoveStateMachine, MoveState

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem

_EBB_DMG = 26
_EBB_BLOCK = 33
_EYE_LASERS_DMG = 11
_EYE_LASERS_HITS = 2
_INTENSITY_BASE_STR = 3
_WITHER_AMOUNT = 1
_WITHERING_PRESENCE = 6
_ARTIFACT = 3


class Aeonglass(MachineMonster):
    """Ebb (26 + 33 block) → Eye Lasers (11×2) → Increasing Intensity (add a
    Wither and fake-upgrade every existing Wither, then gain escalating
    Strength) → loop. Starts with Withering Presence 6 (every 6 cards the player
    plays adds a Wither) and Artifact 3.

    Source: Aeonglass.cs / Wither.cs (non-ascension values)."""

    min_hp = 512
    max_hp = 512

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())
        self.wither_upgrade_count = 0
        self._additional_strength = 0
        from ...cmds import PowerCmd
        from ...powers import ArtifactPower, WitheringPresencePower
        PowerCmd.apply(hooks, self, WitheringPresencePower, _WITHERING_PRESENCE)
        PowerCmd.apply(hooks, self, ArtifactPower, _ARTIFACT)

    def build_machine(self) -> MonsterMoveStateMachine:
        ebb = MoveState(
            "EBB_MOVE", self._ebb,
            Intent(MoveType.ATTACK, damage=_EBB_DMG, also=(MoveType.DEFEND,)),
        )
        lasers = MoveState(
            "EYE_LASERS_MOVE", self._lasers,
            Intent(MoveType.ATTACK, damage=_EYE_LASERS_DMG, hits=_EYE_LASERS_HITS),
        )
        intensity = MoveState(
            "INCREASING_INTENSITY_MOVE", self._intensity,
            Intent(MoveType.STATUS_CARD, also=(MoveType.BUFF,)),
        )
        ebb.follow_up = lasers
        lasers.follow_up = intensity
        intensity.follow_up = ebb
        return MonsterMoveStateMachine([ebb, lasers, intensity], ebb)

    def _ebb(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _EBB_DMG, 1)
        from ...cmds import BlockCmd
        from ...valueprops import ValueProp
        BlockCmd.apply(ctx.hooks, self, _EBB_BLOCK, props=ValueProp.MOVE)

    def _lasers(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, _EYE_LASERS_DMG, _EYE_LASERS_HITS)

    def _intensity(self, ctx: CombatCtx) -> None:
        from ...cards import WitherCard
        from ...cmds import CardPileCmd, PowerCmd
        from ...powers import StrengthPower
        for card in ctx.player.all_cards:
            if isinstance(card, WitherCard):
                card.fake_upgrade()
        self.wither_upgrade_count += 1
        for _ in range(_WITHER_AMOUNT):
            wither = WitherCard()
            for _ in range(self.wither_upgrade_count):
                wither.fake_upgrade()
            CardPileCmd.add_to_discard(ctx.hooks, ctx.player, wither)
        PowerCmd.apply(
            ctx.hooks, self, StrengthPower,
            _INTENSITY_BASE_STR + self._additional_strength,
        )
        self._additional_strength += 1


AEONGLASS_BOSS = Encounter(
    id="aeonglass_boss",
    monster_classes=[Aeonglass],
)
