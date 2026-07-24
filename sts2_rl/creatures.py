"""Creature base class — the common ground between the player and monsters.

A Creature owns the state every combatant shares: HP, block, the `powers`
dict, side ("player"/"enemy"), and the `stunned`/`escaped` flags that the
combat loop reads. `PlayerCombatState` (player.py) and `Monster`
(monsters/base.py) both subclass it. Mirrors STS2's CreatureModel.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .powers import Power


class Creature:
    def __init__(self, max_hp: int) -> None:
        self.max_hp = max_hp
        self.hp = max_hp
        self.block = 0
        self.side: str = "enemy"
        self.powers: dict[str, Power] = {}
        # Set by CreatureCmd.stun; the creature skips its next turn.
        self.stunned = False
        # Set by CreatureCmd.escape; the creature has left combat alive.
        self.escaped = False
        # Set on death when Hook.ShouldCreatureBeRemovedFromCombatAfterDeath
        # says no (CreatureCmd.cs:508): the corpse stays in CombatState.Enemies
        # — it still shows in the UI/recording and still takes turns, which is
        # how a withered Decimillipede segment reaches its REATTACH move.
        self.retained_after_death = False

    @property
    def strength(self) -> int:
        """Convenience read of the StrengthPower amount; 0 if not present."""
        p = self.powers.get("strength")
        return p.amount if p is not None else 0

    @property
    def is_dead(self) -> bool:
        return self.hp <= 0

    @property
    def is_gone(self) -> bool:
        """Dead or escaped — no longer participating in combat."""
        return self.is_dead or self.escaped
