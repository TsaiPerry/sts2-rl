from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class SmallCapsule(Relic):
    """SmallCapsule.cs:13-19 — `RewardsCmd.OfferCustom(Owner, [new
    RelicReward(Owner)])`: a take-or-skip screen with one grab-bag relic.
    RelicReward.Populate pulls it before the offer, so a decline still spends
    the bag slot; only the obtain is conditional."""

    id = "small_capsule"
    name = "Small Capsule"
    rarity = RelicRarity.ANCIENT

    def after_obtained(self, run) -> None:
        relic = run.pull_relic_from_front()
        if relic is not None:
            run.offer_relic(relic)
