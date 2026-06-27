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

    @property
    def strength(self) -> int:
        """Convenience read of the StrengthPower amount; 0 if not present."""
        p = self.powers.get("strength")
        return p.amount if p is not None else 0

    @property
    def is_dead(self) -> bool:
        return self.hp <= 0
