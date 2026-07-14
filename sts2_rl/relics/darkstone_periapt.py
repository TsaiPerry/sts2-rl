from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class DarkstonePeriapt(Relic):
    """Whenever you add a Curse to your deck, gain 6 Max HP.

    Source: DarkstonePeriapt.cs — AfterCardChangedPiles: a Curse entering the
    deck grants 6 Max HP. This fires on out-of-combat deck edits, which the sim
    routes through RunState without run-level relic hooks, so it is a
    documented stub. Granted by the Trash Heap event."""

    id = "darkstone_periapt"
    name = "Darkstone Periapt"
    rarity = RelicRarity.EVENT
