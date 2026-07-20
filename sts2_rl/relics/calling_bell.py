from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class CallingBell(Relic):
    """CallingBell.cs — upon pickup, gain a Curse of the Bell and three
    specific relics: Anchor, Gremlin Horn and Mummified Hand. Offered by the
    Darv shrine.

    The source offers them via RewardsCmd.OfferCustom (a take-or-skip
    screen); the sim grants all three, matching how it auto-keeps other
    non-choice relic offers."""

    id = "calling_bell"
    name = "Calling Bell"
    rarity = RelicRarity.ANCIENT
    has_upon_pickup_effect = True

    RELICS = ("anchor", "gremlin_horn", "mummified_hand")

    def after_obtained(self, run) -> None:
        from ..cards import make_card

        run.add_card(make_card("curse_of_the_bell"))
        for relic_id in self.RELICS:
            run.add_relic(relic_id)
