from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ..base import Encounter, Intent, Monster, MoveType
from ..state_machine import weighted_branch_pick

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem


# ── Small Slimes ─────────────────────────────────────────────────────────

class LeafSlimeS(Monster):
    """Random first move, then alternates TACKLE (damage) / GOOP (Slimed card)."""
    name = "Leaf Slime (S)"
    min_hp = 11
    max_hp = 15

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        rng = rng or random.Random()
        super().__init__(hooks, rng)
        # Combat-start telegraph (mirrors LeafSlimeS's RandomBranchState roll,
        # CannotRepeat on both branches — 50/50 with nothing logged yet).
        self._move_key = weighted_branch_pick(
            hooks.combat.combat_rng.monster_ai, ["TACKLE", "GOOP"], [1, 1]
        )

    @property
    def current_intent(self) -> Intent:
        if self._move_key == "TACKLE":
            return Intent(MoveType.ATTACK, damage=3)
        return Intent(MoveType.STATUS_CARD)  # GOOP: adds a Slimed card

    def take_turn(self, ctx: CombatCtx) -> None:
        if self._move_key == "TACKLE":
            self._execute_attack(ctx, 3, 1)
        else:
            from ...cards import SlimedCard
            from ...cmds import CardPileCmd
            CardPileCmd.add_to_discard(ctx.hooks, ctx.player, SlimedCard())
        self.telegraph_next_move()

    def telegraph_next_move(self) -> None:
        # Both branches are CannotRepeat, so the just-performed move is
        # ineligible (weight 0) and the other is forced — but RandomBranchState.
        # GetNextState still draws ONE NextFloat on every transition (it rolls
        # over the summed weights regardless of how many are non-zero), so roll
        # even though the outcome is forced. Skipping it under-counted MonsterAi.
        weights = [0, 1] if self._move_key == "TACKLE" else [1, 0]
        self._move_key = weighted_branch_pick(
            self._hooks.combat.combat_rng.monster_ai, ["TACKLE", "GOOP"], weights
        )


class TwigSlimeS(Monster):
    """Always tackles."""
    name = "Twig Slime (S)"
    min_hp = 7
    max_hp = 11

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())

    @property
    def current_intent(self) -> Intent:
        return Intent(MoveType.ATTACK, damage=4)

    def take_turn(self, ctx: CombatCtx) -> None:
        self._execute_attack(ctx, 4, 1)


# ── Medium Slimes ─────────────────────────────────────────────────────────

class LeafSlimeM(Monster):
    """STICKY_SHOT → CLUMP_SHOT alternating; starts with STICKY_SHOT."""
    name = "Leaf Slime (M)"
    min_hp = 32
    max_hp = 35

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())
        self._move_key = "STICKY_SHOT"

    @property
    def current_intent(self) -> Intent:
        if self._move_key == "STICKY_SHOT":
            return Intent(MoveType.STATUS_CARD)  # adds 2 Slimed cards
        return Intent(MoveType.ATTACK, damage=8)

    def take_turn(self, ctx: CombatCtx) -> None:
        if self._move_key == "STICKY_SHOT":
            from ...cards import SlimedCard
            from ...cmds import CardPileCmd
            for _ in range(2):
                CardPileCmd.add_to_discard(ctx.hooks, ctx.player, SlimedCard())
            self._move_key = "CLUMP_SHOT"
        else:
            self._execute_attack(ctx, 8, 1)
            self._move_key = "STICKY_SHOT"


class TwigSlimeM(Monster):
    """STICKY_SHOT start, then weighted random between POKEY_POUNCE and STICKY_SHOT (no repeats)."""
    name = "Twig Slime (M)"
    min_hp = 26
    max_hp = 28

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())
        self._rng = rng or random.Random()
        self._move_key = "STICKY_SHOT"

    @property
    def current_intent(self) -> Intent:
        if self._move_key == "STICKY_SHOT":
            return Intent(MoveType.STATUS_CARD)  # adds 1 Slimed card
        return Intent(MoveType.ATTACK, damage=11, hits=1)

    def take_turn(self, ctx: CombatCtx) -> None:
        if self._move_key == "STICKY_SHOT":
            from ...cards import SlimedCard
            from ...cmds import CardPileCmd
            CardPileCmd.add_to_discard(ctx.hooks, ctx.player, SlimedCard())
        else:
            self._execute_attack(ctx, 11, 1)
        self.telegraph_next_move()

    def telegraph_next_move(self) -> None:
        if self._move_key == "STICKY_SHOT":
            # After STICKY_SHOT, CannotRepeat blocks STICKY (weight 0) so
            # POKEY_POUNCE is forced — but RandomBranchState still draws one
            # NextFloat every transition, so roll (over [POKEY, STICKY]) even
            # though only POKEY is eligible, rather than assigning it directly.
            self._move_key = weighted_branch_pick(
                self._hooks.combat.combat_rng.monster_ai,
                ["POKEY_POUNCE", "STICKY_SHOT"], [1, 0],
            )
        else:
            # weight 2 POKEY_POUNCE, weight 1 STICKY_SHOT (no repeat restriction after POKEY_POUNCE)
            self._move_key = weighted_branch_pick(
                self._hooks.combat.combat_rng.monster_ai,
                ["POKEY_POUNCE", "STICKY_SHOT"], [2, 1],
            )


# ── Encounter definitions ─────────────────────────────────────────────────

@dataclass
class SlimesNormalEncounter(Encounter):
    """TwigSlimeM + LeafSlimeM + 2 randomly-ordered small slimes."""
    monster_classes: list = field(default_factory=list)

    def create_monsters(self, hooks: HookSystem, rng: random.Random, selection_rng=None) -> list[Monster]:
        if selection_rng is not None:
            # Parity (SlimesNormal.GenerateMonsters): one NextBool orders the two
            # smalls; the two mediums are fixed at slots 0-1.
            leaf_first = selection_rng.next_bool()
            small0, small1 = (
                (LeafSlimeS, TwigSlimeS) if leaf_first else (TwigSlimeS, LeafSlimeS))
            return [
                TwigSlimeM(hooks, rng),
                LeafSlimeM(hooks, rng),
                small0(hooks, rng),
                small1(hooks, rng),
            ]
        small = rng.sample([LeafSlimeS, TwigSlimeS], 2)
        return [
            TwigSlimeM(hooks, rng),
            LeafSlimeM(hooks, rng),
            small[0](hooks, rng),
            small[1](hooks, rng),
        ]


@dataclass
class SlimesWeakEncounter(Encounter):
    """One small + one medium + another small (randomly selected)."""
    monster_classes: list = field(default_factory=list)

    def create_monsters(self, hooks: HookSystem, rng: random.Random, selection_rng=None) -> list[Monster]:
        if selection_rng is not None:
            # Parity (SlimesWeak.GenerateMonsters): pick small A, remove it and
            # pick small B from the remaining single-element list (a NextItem on
            # a 1-element list still consumes a draw), then pick the medium — a
            # three-draw sequence, returned as [A, medium, B].
            smalls = [LeafSlimeS, TwigSlimeS]
            small_a = selection_rng.next_item(smalls)
            smalls.remove(small_a)
            small_b = selection_rng.next_item(smalls)
            medium_cls = selection_rng.next_item([LeafSlimeM, TwigSlimeM])
            return [small_a(hooks, rng), medium_cls(hooks, rng), small_b(hooks, rng)]
        smalls = rng.sample([LeafSlimeS, TwigSlimeS], 2)
        medium_cls = rng.choice([LeafSlimeM, TwigSlimeM])
        return [smalls[0](hooks, rng), medium_cls(hooks, rng), smalls[1](hooks, rng)]


SLIMES_NORMAL = SlimesNormalEncounter(id="slimes_normal")
SLIMES_WEAK = SlimesWeakEncounter(id="slimes_weak")
