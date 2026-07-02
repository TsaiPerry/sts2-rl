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
