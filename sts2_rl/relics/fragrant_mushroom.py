from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class FragrantMushroom(Relic):
    """On pickup, lose 15 HP and upgrade 2 random upgradable cards.

    Source: FragrantMushroom.cs — AfterObtained deals 15 unblockable, unpowered
    damage then upgrades 2 random upgradable deck cards. Granted by the Hungry
    for Mushrooms event. It has no in-combat effect, so both pickup effects are
    applied by the event (RunState has no run-level AfterObtained dispatch); the
    relic is registered so the reward is constructible."""

    id = "fragrant_mushroom"
    name = "Fragrant Mushroom"
    rarity = RelicRarity.EVENT

    HP_LOSS = 15
    CARDS = 2
