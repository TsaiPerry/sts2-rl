from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ..base import Encounter, Intent, Monster, MoveType

if TYPE_CHECKING:
    from ...combat import CombatCtx
    from ...hooks import HookSystem

_LASH_DMG = 4
_LASH_HITS = 4
_INFECT_CARDS = 3  # would add 3 Infection cards to player discard


class Wriggler(Monster):
    """Spawned by PhrogParasite's Infested power; starts stunned if summoned mid-combat."""
    min_hp = 17
    max_hp = 21

    def __init__(
        self,
        hooks: HookSystem,
        rng: random.Random | None = None,
        *,
        start_stunned: bool = False,
        slot: int = 1,
    ) -> None:
        super().__init__(hooks, rng or random.Random())
        # Spawned mid-combat: stunned for its first turn (the combat loop
        # skips stunned creatures' moves, mirroring CreatureCmd.Stun).
        self.stunned = start_stunned
        # Odd slots start with NASTY_BITE; even slots start with WRIGGLE
        self._move_key = "NASTY_BITE" if slot % 2 == 1 else "WRIGGLE"

    @property
    def current_intent(self) -> Intent:
        if self.stunned:
            return Intent(MoveType.STUN)
        if self._move_key == "NASTY_BITE":
            return Intent(MoveType.ATTACK, damage=6)
        from ...powers import StrengthPower
        # WRIGGLE buffs itself and shuffles an Infection into the discard pile
        return Intent(
            MoveType.BUFF, buffs=[(StrengthPower, 2)], also=(MoveType.STATUS_CARD,)
        )

    def take_turn(self, ctx: CombatCtx) -> None:
        from ...cmds import PowerCmd
        if self._move_key == "NASTY_BITE":
            self._execute_attack(ctx, 6, 1)
            self._move_key = "WRIGGLE"
        else:
            from ...powers import StrengthPower
            PowerCmd.apply(ctx.hooks, self, StrengthPower, 2)
            from ...cards import InfectionCard
            from ...cmds import CardPileCmd
            CardPileCmd.add_to_discard(ctx.hooks, ctx.player, InfectionCard())
            self._move_key = "NASTY_BITE"


class PhrogParasite(Monster):
    """INFECT (adds Infection cards) → LASH (multi-hit) → alternating.
    On death, InfestedPower spawns 4 stunned Wrigglers."""
    min_hp = 61
    max_hp = 64

    def __init__(self, hooks: HookSystem, rng: random.Random | None = None) -> None:
        super().__init__(hooks, rng or random.Random())
        from ...cmds import PowerCmd
        from ...powers import InfestedPower
        PowerCmd.apply(hooks, self, InfestedPower, 4)
        self._move_key = "INFECT"

    @property
    def current_intent(self) -> Intent:
        if self._move_key == "INFECT":
            return Intent(MoveType.STATUS_CARD)  # adds 3 Infection cards
        return Intent(MoveType.ATTACK, damage=_LASH_DMG, hits=_LASH_HITS)

    def take_turn(self, ctx: CombatCtx) -> None:
        if self._move_key == "INFECT":
            from ...cards import InfectionCard
            from ...cmds import CardPileCmd
            for _ in range(_INFECT_CARDS):
                CardPileCmd.add_to_discard(ctx.hooks, ctx.player, InfectionCard())
            self._move_key = "LASH"
        else:
            self._execute_attack(ctx, _LASH_DMG, _LASH_HITS)
            self._move_key = "INFECT"


PHROG_PARASITE_ELITE = Encounter(
    id="phrog_parasite_elite",
    monster_classes=[PhrogParasite],
)
