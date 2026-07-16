from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class StoneHumidifier(Relic):
    """StoneHumidifier.cs — whenever you Heal at a rest site, gain 5 Max HP."""

    id = "stone_humidifier"
    name = "Stone Humidifier"
    rarity = RelicRarity.ANCIENT
    MAX_HP = 5

    def after_rest_site_heal(self, run) -> None:
        run.gain_max_hp(self.MAX_HP)
