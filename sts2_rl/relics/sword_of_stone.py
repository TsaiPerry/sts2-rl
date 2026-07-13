from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class SwordOfStone(Relic):
    """Event relic (Sunken Statue): counts elite combats won; after 5 it is
    replaced by Sword of Jade. Elite victories and relic replacement are
    out-of-combat run progression the sim doesn't model, so this is a no-op
    stub.

    Source: SwordOfStone.cs — AfterCombatVictory in an Elite room increments
    a counter; at 5, RelicCmd.Replace(SwordOfJade).
    """

    id = "sword_of_stone"
    name = "Sword of Stone"
    rarity = RelicRarity.EVENT
