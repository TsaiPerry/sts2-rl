from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class NewLeaf(Relic):
    """NewLeaf.cs — transform a chosen card."""

    id = "new_leaf"
    name = "New Leaf"
    rarity = RelicRarity.ANCIENT
    has_upon_pickup_effect = True  # RelicModel.HasUponPickupEffect

    def after_obtained(self, run) -> None:
        # NewLeaf.cs:27 is CardCmd.TransformToRandom(item, RunState.Rng.Niche),
        # which reaches CreateRandomCardForTransform and really draws on Niche
        # (the CardTransformation carries no explicit Replacement). Legacy runs
        # keep the shared rng.
        niche = run.rng_set.niche if run.rng_set is not None else None
        for card in run.select_cards("transform", run.transformable_cards(), 1):
            run.transform_card(card, pick_rng=niche)
