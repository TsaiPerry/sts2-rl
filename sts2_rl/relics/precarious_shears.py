from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class PrecariousShears(Relic):
    """PrecariousShears.cs — remove 2 chosen cards; take 16 damage."""

    id = "precarious_shears"
    name = "Precarious Shears"
    rarity = RelicRarity.ANCIENT
    CARDS = 2
    DAMAGE = 16

    def after_obtained(self, run) -> None:
        chosen = run.select_cards("remove", run.removable_cards(), self.CARDS)
        run.remove_cards(chosen)
        run.lose_hp(self.DAMAGE)
