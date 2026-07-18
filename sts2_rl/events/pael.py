"""Pael — one of the three Act-2 (Hive) Ancients.

Port of Pael.cs GenerateInitialOptions: three relic options —

  1. one of OptionPool1 (Pael's Flesh / Horn / Tears);
  2. from a weighted list: [Wing] + [Claw if ≥3 Goopy-eligible deck cards] +
     [Tooth if ≥5 removable deck cards], the whole list DOUBLED
     (list.AddRange(list)), then + [Growth] — so Growth rolls at half the
     weight of the others;
  3. one of OptionPool3 (Pael's Eye / Blood) + [Legion if the player has no
     event pet].
"""
from __future__ import annotations

from .ancient import AncientEvent
from .base import EventOption, register_event

OPTION_POOL_1: tuple[str, ...] = ("paels_flesh", "paels_horn", "paels_tears")


@register_event
class PaelEvent(AncientEvent):
    id = "pael"
    name = "Pael"

    def initial_options(self) -> list[EventOption]:
        rng = self.rng
        run = self.run

        first = rng.choice(list(OPTION_POOL_1))

        from ..enchantments import GoopyEnchantment
        from ..relics.paels_claw import PaelsClaw
        from ..relics.paels_tooth import PaelsTooth

        pool2 = ["paels_wing"]
        goopy_eligible = sum(
            1 for c in run.deck if GoopyEnchantment.can_enchant(c)
        )
        if goopy_eligible >= PaelsClaw.MIN_ELIGIBLE:
            pool2.append("paels_claw")
        if len(run.removable_cards()) >= PaelsTooth.MIN_REMOVABLE:
            pool2.append("paels_tooth")
        pool2 = pool2 + pool2          # list.AddRange(list): double the weights
        pool2.append("paels_growth")
        second = rng.choice(pool2)

        pool3 = ["paels_eye", "paels_blood"]
        if not run.has_event_pet:
            pool3.append("paels_legion")
        third = rng.choice(pool3)

        return [self._relic_option(rid) for rid in (first, second, third)]
