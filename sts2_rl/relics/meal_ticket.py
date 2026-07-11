from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class MealTicket(Relic):
    """Whenever you enter a shop, heal 15 HP — an out-of-combat (MerchantRoom)
    effect, so this is a no-op stub."""

    id = "meal_ticket"
    name = "Meal Ticket"
    rarity = RelicRarity.COMMON
