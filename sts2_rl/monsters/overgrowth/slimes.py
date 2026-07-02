from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ..base import Encounter, Intent, Monster, MoveType

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem


# ── Small Slimes ─────────────────────────────────────────────────────────

class LeafSlimeS(Monster):
    """Random first move, then alternates TACKLE (damage) / GOOP (Slimed card)."""
    min_hp = 11
    max_hp = 15

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        rng = rng or random.Random()
        super().__init__(hooks, rng)
        self._move_key = rng.choice(["TACKLE", "GOOP"])

    @property
    def current_intent(self) -> Intent:
        if self._move_key == "TACKLE":
            return Intent(MoveType.ATTACK, damage=3)
        return Intent(MoveType.BUFF, buffs=[])  # GOOP: adds Slimed card (not yet implemented)

    def take_turn(self, ctx: CombatCtx) -> None:
        if self._move_key == "TACKLE":
            self._execute_attack(ctx, 3, 1)
            self._move_key = "GOOP"
        else:
            from ...cards import SlimedCard
            from ...cmds import CardPileCmd
            CardPileCmd.add_to_discard(ctx.hooks, ctx.player, SlimedCard())
            self._move_key = "TACKLE"


class TwigSlimeS(Monster):
    """Always tackles."""
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
    min_hp = 32
    max_hp = 35

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())
        self._move_key = "STICKY_SHOT"

    @property
    def current_intent(self) -> Intent:
        if self._move_key == "STICKY_SHOT":
            return Intent(MoveType.BUFF, buffs=[])  # adds 2 Slimed cards
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
    min_hp = 26
    max_hp = 28

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())
        self._rng = rng or random.Random()
        self._move_key = "STICKY_SHOT"

    @property
    def current_intent(self) -> Intent:
        if self._move_key == "STICKY_SHOT":
            return Intent(MoveType.BUFF, buffs=[])  # adds 1 Slimed card
        return Intent(MoveType.ATTACK, damage=11, hits=1)

    def take_turn(self, ctx: CombatCtx) -> None:
        if self._move_key == "STICKY_SHOT":
            from ...cards import SlimedCard
            from ...cmds import CardPileCmd
            CardPileCmd.add_to_discard(ctx.hooks, ctx.player, SlimedCard())
            # After STICKY_SHOT, can't repeat → always POKEY_POUNCE next
            self._move_key = "POKEY_POUNCE"
        else:
            self._execute_attack(ctx, 11, 1)
            # weight 2 POKEY_POUNCE, weight 1 STICKY_SHOT (no repeat restriction after POKEY_POUNCE)
            self._move_key = self._rng.choices(
                ["POKEY_POUNCE", "STICKY_SHOT"], weights=[2, 1]
            )[0]


# ── Encounter definitions ─────────────────────────────────────────────────

@dataclass
class SlimesNormalEncounter(Encounter):
    """TwigSlimeM + LeafSlimeM + 2 randomly-ordered small slimes."""
    monster_classes: list = field(default_factory=list)

    def create_monsters(self, hooks: HookSystem, rng: random.Random) -> list[Monster]:
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

    def create_monsters(self, hooks: HookSystem, rng: random.Random) -> list[Monster]:
        smalls = rng.sample([LeafSlimeS, TwigSlimeS], 2)
        medium_cls = rng.choice([LeafSlimeM, TwigSlimeM])
        return [smalls[0](hooks, rng), medium_cls(hooks, rng), smalls[1](hooks, rng)]


SLIMES_NORMAL = SlimesNormalEncounter(id="slimes_normal")
SLIMES_WEAK = SlimesWeakEncounter(id="slimes_weak")
