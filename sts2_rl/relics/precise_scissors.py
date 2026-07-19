from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class PreciseScissors(Relic):
    """PreciseScissors.cs — remove a chosen card from the deck."""

    id = "precise_scissors"
    name = "Precise Scissors"
    rarity = RelicRarity.ANCIENT
    has_upon_pickup_effect = True  # RelicModel.HasUponPickupEffect

    def after_obtained(self, run) -> None:
        chosen = run.select_cards("remove", run.removable_cards(), 1)
        run.remove_cards(chosen)
