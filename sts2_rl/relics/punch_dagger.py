from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class PunchDagger(Relic):
    """PunchDagger.cs — upon pickup, enchant one chosen deck card with
    Momentum 1 (`CardSelectCmd.FromDeckForEnchantment`).

    STILL A NO-OP, but NOT for the reason this docstring used to give: the sim
    does have enchantments (`sts2_rl/enchantments.py`) and a deck-card
    selection screen. What is missing is the **Momentum enchantment itself** —
    the module registers 17 and Momentum is not among them, so there is
    nothing to attach."""

    id = "punch_dagger"
    name = "Punch Dagger"
    rarity = RelicRarity.SHOP
    has_upon_pickup_effect = True  # RelicModel.HasUponPickupEffect
