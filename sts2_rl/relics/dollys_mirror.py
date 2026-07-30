from __future__ import annotations

from .base import Relic, RelicRarity, register_relic

@register_relic
class DollysMirror(Relic):
    """DollysMirror.cs — upon pickup, duplicate one card in your deck."""

    id = "dollys_mirror"
    name = "Dolly's Mirror"
    rarity = RelicRarity.SHOP
    has_upon_pickup_effect = True  # RelicModel.HasUponPickupEffect

    def after_obtained(self, run) -> None:
        """DollysMirror.cs:16-24 — one pick from a screen of count 1, then
        `RunState.CloneCard` and `CardPileCmd.Add(card, PileType.Deck)`.

        The filter is `c.Type != CardType.Quest` (:26-29) and NOTHING ELSE, so
        Curses, Statuses and ETERNAL cards are all duplicable -- which is why
        `run.removable_cards()` and `run.transformable_cards()` are both the
        wrong candidate list here (the first would offer a Quest card, the
        second would refuse an Eternal one).

        `.FirstOrDefault()` plus the `!= null` check at :19 make a cancelled
        selection a clean no-op, which `select_cards`' empty-list return
        already models. The copy is `CloneCard`, i.e.
        `ClonePreservingMutability` (CombatState.cs:188-193) -- `create_clone`,
        not a rebuild from the id, because a deck card out of combat carries
        the enchantments Beautiful Bracelet and Silken Tress put on it.
        """
        from ..cards import CardType
        from ..cards.base import create_clone

        candidates = [c for c in run.deck if c.card_type != CardType.QUEST]
        for card in run.select_cards("duplicate", candidates, 1):
            run.add_card(create_clone(card))
