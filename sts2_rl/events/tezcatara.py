"""Tezcatara — one of the three Act-2 (Hive) Ancients.

Port of Tezcatara.cs GenerateInitialOptions: three relic options —

  1. one of OptionPool1 (Very Hot Cocoa / Yummy Cookie) + [Nutritious Soup if
     the deck holds a Basic Strike-tagged card];
  2. one of OptionPool2 (Biiig Hug / Storybook / Toasty Mittens);
  3. one of OptionPool3 (Golden Compass / Pumpkin Candle / Toy Box /
     Seal of Gold).
"""
from __future__ import annotations

from .ancient import AncientEvent
from .base import EventOption, register_event

OPTION_POOL_1: tuple[str, ...] = ("very_hot_cocoa", "yummy_cookie")
OPTION_POOL_2: tuple[str, ...] = ("biiig_hug", "storybook", "toasty_mittens")
OPTION_POOL_3: tuple[str, ...] = (
    "golden_compass", "pumpkin_candle", "toy_box", "seal_of_gold",
)


@register_event
class TezcataraEvent(AncientEvent):
    id = "tezcatara"
    name = "Tezcatara"

    def initial_options(self) -> list[EventOption]:
        from ..cards import CardRarity

        run = self.run
        # Tezcatara.cs: three base.Rng.NextItem picks on the per-event Rng.
        # Legacy keeps the shared run rng (.choice).
        er = self.event_rng

        def pick(opts):
            return er.next_item(opts) if er is not None else self.rng.choice(opts)

        pool1 = list(OPTION_POOL_1)
        if any(
            c.rarity == CardRarity.BASIC and "strike" in c.tags
            for c in run.deck
        ):
            pool1.append("nutritious_soup")
        first = pick(pool1)
        second = pick(list(OPTION_POOL_2))
        third = pick(list(OPTION_POOL_3))
        return [self._relic_option(rid) for rid in (first, second, third)]
