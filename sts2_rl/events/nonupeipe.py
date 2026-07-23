"""Nonupeipe — one of the three Act-3 (Glory) Ancients.

Port of Nonupeipe.cs GenerateInitialOptions: one 9-relic pool (+ Beautiful
Bracelet when the deck has ≥4 Swift-eligible cards); shuffle and take 3.
"""
from __future__ import annotations

from .ancient import AncientEvent
from .base import EventOption, register_event

OPTION_POOL: tuple[str, ...] = (
    "blessed_antler", "brilliant_scarf", "delicate_frond", "diamond_diadem",
    "fur_coat", "glitter", "jewelry_box", "looming_fruit", "signet_ring",
)


@register_event
class NonupeipeEvent(AncientEvent):
    id = "nonupeipe"
    name = "Nonupeipe"

    def initial_options(self) -> list[EventOption]:
        from ..enchantments import SwiftEnchantment
        from ..relics.beautiful_bracelet import BeautifulBracelet

        pool = list(OPTION_POOL)
        eligible = sum(
            1 for c in self.run.deck if SwiftEnchantment.can_enchant(c)
        )
        if eligible >= BeautifulBracelet.MIN_ELIGIBLE:
            pool.append("beautiful_bracelet")
        # Nonupeipe.cs: list.UnstableShuffle(base.Rng).Take(3) on the per-event
        # Rng. Legacy keeps the shared run rng.
        (self.event_rng if self.event_rng is not None else self.rng).shuffle(pool)
        return [self._relic_option(rid) for rid in pool[:3]]
