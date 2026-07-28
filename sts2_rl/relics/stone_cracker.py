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
            # sorts by ModelId (CardModel.CompareTo — the game's UPPERCASE
            # entry compared ordinally, then the upgrade level) before the game
            # UnstableShuffle. The game stores a pile top-at-index-0 and the sim
            # draws off the END (player.py:264), so feed the pile in the GAME's
            # orientation: equal-comparing cards (5 Strikes, 4 Defends) keep
            # their incoming order under both List.Sort and Python's sort.
            from ..actmap import stable_shuffle
            from ..player import _compare_to_key
            chosen = stable_shuffle(
                list(reversed(upgradable)), crng.card_selection,
                key=_compare_to_key,
            )[:count]
        else:
            chosen = self.combat._rng.sample(upgradable, count)
        for card in chosen:
            card.upgrade()
