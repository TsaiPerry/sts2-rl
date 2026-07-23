"""Tanx — one of the three Act-3 (Glory) Ancients.

Port of Tanx.cs GenerateInitialOptions: one 9-relic pool (+ Tri-Boomerang
when the deck has ≥3 Instinct-eligible cards); shuffle and take 3.
"""
from __future__ import annotations

from .ancient import AncientEvent
from .base import EventOption, register_event

OPTION_POOL: tuple[str, ...] = (
    "claws", "crossbow", "iron_club", "meat_cleaver", "sai",
    "spiked_gauntlets", "tanxs_whistle", "throwing_axe", "war_hammer",
)


@register_event
class TanxEvent(AncientEvent):
    id = "tanx"
    name = "Tanx"

    def initial_options(self) -> list[EventOption]:
        from ..enchantments import InstinctEnchantment
        from ..relics.tri_boomerang import TriBoomerang

        pool = list(OPTION_POOL)
        eligible = sum(
            1 for c in self.run.deck if InstinctEnchantment.can_enchant(c)
        )
        if eligible >= TriBoomerang.MIN_ELIGIBLE:
            pool.append("tri_boomerang")
        # Tanx.cs: list.UnstableShuffle(base.Rng).Take(3) on the per-event Rng.
        # Legacy keeps the shared run rng.
        (self.event_rng if self.event_rng is not None else self.rng).shuffle(pool)
        return [self._relic_option(rid) for rid in pool[:3]]
