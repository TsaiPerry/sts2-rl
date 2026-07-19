from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class DistinguishedCape(Relic):
    """DistinguishedCape.cs — upon pickup, add 3 Apparition cards
    (CardsVar(3)). The −9 Max HP comes from the Vakuu event OPTION
    (RelicOption<DistinguishedCape>().ThatDecreasesMaxHp(9)), not the relic
    itself — vakuu.py applies it when the option is chosen."""

    id = "distinguished_cape"
    name = "Distinguished Cape"
    rarity = RelicRarity.ANCIENT
    has_upon_pickup_effect = True  # RelicModel.HasUponPickupEffect

    CARDS = 3
    MAX_HP_LOSS = 9  # applied by the Vakuu option wrapper

    def after_obtained(self, run) -> None:
        from ..cards import make_card

        for _ in range(self.CARDS):
            run.add_card(make_card("apparition"))
