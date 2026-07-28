from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class Whetstone(Relic):
    """Whetstone.cs — upon pickup, upgrade 2 random upgradable Attacks in your
    deck (AfterObtained, dispatched by RunState.add_relic)."""

    id = "whetstone"
    name = "Whetstone"
    rarity = RelicRarity.COMMON
    has_upon_pickup_effect = True  # RelicModel.HasUponPickupEffect

    CARDS = 2  # CardsVar(2)

    def after_obtained(self, run) -> None:
        from ..cards import CardType

        upgradable = [
            c for c in run.deck
            if c.card_type == CardType.ATTACK and c.is_upgradable
        ]
        count = min(self.CARDS, len(upgradable))
        # Whetstone.cs: Deck Attack+IsUpgradable cards,
        # StableShuffle(Rng.Niche).Take(count). StableShuffle sorts by ModelId
        # (CardModel.CompareTo — the game's UPPERCASE entry compared ordinally,
        # then the upgrade level) before the game UnstableShuffle.
        if run.rng_set is not None:
            from ..actmap import stable_shuffle
            from ..player import _compare_to_key
            chosen = stable_shuffle(
                list(upgradable), run.rng_set.niche, key=_compare_to_key,
            )[:count]
        else:
            chosen = run.rng.sample(upgradable, count)
        for card in chosen:
            card.upgrade()
