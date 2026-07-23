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
        crng = self.combat.combat_rng
        if crng.is_parity:
            # StoneCracker.cs: Draw-pile IsUpgradable cards,
            # StableShuffle(Rng.CombatCardSelection).Take(count). StableShuffle
            # sorts by ModelId (card id, then upgrade level) before the game
            # UnstableShuffle, so the result is independent of pile order.
            from ..actmap import stable_shuffle
            chosen = stable_shuffle(
                list(upgradable), crng.card_selection,
                key=lambda c: (c.id, c.upgrade_level),
            )[:count]
        else:
            chosen = self.combat._rng.sample(upgradable, count)
        for card in chosen:
            card.upgrade()
