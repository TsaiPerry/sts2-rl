from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class SandCastle(Relic):
    """SandCastle.cs — upon pickup, upgrade 6 random upgradable deck cards."""

    id = "sand_castle"
    name = "Sand Castle"
    rarity = RelicRarity.ANCIENT
    has_upon_pickup_effect = True  # RelicModel.HasUponPickupEffect

    CARDS = 6  # CardsVar(6)

    def after_obtained(self, run) -> None:
        upgradable = run.upgradable_cards()
        count = min(self.CARDS, len(upgradable))
        # SandCastle.cs: Deck IsUpgradable cards,
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
