from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class RoyalStamp(Relic):
    """RoyalStamp.cs — upon pickup, enchant one chosen deck card with Royally
    Approved 1, the candidate list first `UnstableShuffle`d on
    `RunState.Rng.Niche`.

    STILL A NO-OP, but NOT for the reason this docstring used to give: the sim
    does have enchantments (`sts2_rl/enchantments.py`) and a deck-card
    selection screen. What is missing is the **Royally Approved enchantment
    itself** — the module registers 17 and this is not among them — so there is
    nothing to attach, and the Niche shuffle it would consume stays unmade."""

    id = "royal_stamp"
    name = "Royal Stamp"
    rarity = RelicRarity.SHOP
    has_upon_pickup_effect = True  # RelicModel.HasUponPickupEffect
