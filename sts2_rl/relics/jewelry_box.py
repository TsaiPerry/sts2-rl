from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class JewelryBox(Relic):
    """JewelryBox.cs — upon pickup, add an Apotheosis to the deck."""

    id = "jewelry_box"
    name = "Jewelry Box"
    rarity = RelicRarity.ANCIENT
    has_upon_pickup_effect = True  # RelicModel.HasUponPickupEffect

    def after_obtained(self, run) -> None:
        from ..cards import make_card

        run.add_card(make_card("apotheosis"))
