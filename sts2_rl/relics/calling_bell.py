from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class CallingBell(Relic):
    """CallingBell.cs — upon pickup, gain a Curse of the Bell and be offered
    one Common, one Uncommon and one Rare relic. Offered by the Darv shrine.

    CallingBell.cs:31 hands three RelicRewards to RewardsCmd.OfferCustom, a
    take-or-skip screen with three independent declines (the curse is added
    first, by CardPileCmd.AddCurseToDeck, and is not part of it), so each goes
    through run.offer_relic.

    The rewards come from GenerateRewards' SHIPPING arm (CallingBell.cs:53-63)
    — `new RelicReward(Common/Uncommon/Rare, Owner)`, each Populated by
    `RelicFactory.PullNextRelicFromFront(Player, rarity)` (RelicReward.cs:
    92-95). The fixed Anchor / Gremlin Horn / Mummified Hand list at
    CallingBell.cs:39-52 is the `TestMode.IsOn` branch and is NOT what a run
    sees. The pinned-rarity overload does no RollRarity (RelicFactory.cs:31-33),
    so the three pulls cost bag slots but no Rewards-stream draw."""

    id = "calling_bell"
    name = "Calling Bell"
    rarity = RelicRarity.ANCIENT
    has_upon_pickup_effect = True

    RARITIES = (RelicRarity.COMMON, RelicRarity.UNCOMMON, RelicRarity.RARE)

    def after_obtained(self, run) -> None:
        from ..cards import make_card

        run.add_card(make_card("curse_of_the_bell"))
        # RewardsSet.GenerateWithoutOffering populates EVERY reward before
        # Offer walks them (RewardsSet.cs:125-147, 153-159), so all three bag
        # pulls happen before the first take-or-skip is asked.
        pulled = [run.pull_relic_from_front(rarity=r) for r in self.RARITIES]
        for relic in pulled:
            if relic is not None:
                run.offer_relic(relic)
