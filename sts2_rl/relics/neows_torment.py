from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class NeowsTorment(Relic):
    """NeowsTorment.cs — add a Neow's Fury to the deck."""

    id = "neows_torment"
    name = "Neow's Torment"
    rarity = RelicRarity.ANCIENT
    has_upon_pickup_effect = True  # RelicModel.HasUponPickupEffect

    def after_obtained(self, run) -> None:
        from ..cards import make_card

        run.add_card(make_card("neows_fury"))
