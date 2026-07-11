from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class StoneCracker(Relic):
    """At the start of combat, Upgrade 2 random cards in your draw pile (for
    the rest of the combat)."""

    id = "stone_cracker"
    name = "Stone Cracker"
    rarity = RelicRarity.UNCOMMON

    CARDS = 2

    def on_combat_start(self) -> None:
        upgradable = [c for c in self.player.draw_pile if c.is_upgradable]
        count = min(self.CARDS, len(upgradable))
        for card in self.combat._rng.sample(upgradable, count):
            card.upgrade()
