from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class Astrolabe(Relic):
    """Astrolabe.cs — upon pickup, transform 3 chosen cards; each replacement
    is UPGRADED (CreateRandomCardForTransform then CardCmd.Upgrade). Offered
    by the Darv shrine."""

    id = "astrolabe"
    name = "Astrolabe"
    rarity = RelicRarity.ANCIENT
    has_upon_pickup_effect = True

    CARDS = 3

    def after_obtained(self, run) -> None:
        chosen = run.select_cards(
            "transform", run.transformable_cards(), self.CARDS)
        # Astrolabe.cs:25 rolls each replacement on the Niche stream
        # (CreateRandomCardForTransform(item, isInCombat: false,
        # RunState.Rng.Niche)), one NextItem per transformed card. Legacy runs
        # keep the shared rng.
        niche = run.rng_set.niche if run.rng_set is not None else None
        for card in chosen:
            run.transform_card(card, pick_rng=niche).upgrade()
