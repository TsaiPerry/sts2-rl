from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..creatures import Creature


@register_relic
class PaperPhrog(Relic):
    """Enemies you hit while Vulnerable take 25% more damage: the ×1.5
    Vulnerable multiplier becomes ×1.75 for your attacks (mirrors
    ModifyVulnerableMultiplier +0.25)."""

    id = "paper_phrog"
    name = "Paper Phrog"
    rarity = RelicRarity.UNCOMMON

    def modify_vulnerable_multiplier(self, dealer: Creature | None, mult: float) -> float:
        if dealer is self.player:
            return mult + 0.25
        return mult
