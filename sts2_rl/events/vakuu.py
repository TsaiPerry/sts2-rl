"""Vakuu — one of the three Act-3 (Glory) Ancients.

Port of Vakuu.cs GenerateInitialOptions: one option from each of three
shuffled pools —

  1. Blood-Soaked Rose / Whispering Earring / Fiddle;
  2. Preserved Fog / Sere Talon / Distinguished Cape (the Cape option also
     costs 9 Max HP — RelicOption<DistinguishedCape>().ThatDecreasesMaxHp(9));
  3. Choice's Paradox / Music Box / Lord's Parasol / Jeweled Mask.
"""
from __future__ import annotations

from .ancient import AncientEvent
from .base import EventOption, register_event

POOL_1: tuple[str, ...] = ("blood_soaked_rose", "whispering_earring", "fiddle")
POOL_2: tuple[str, ...] = ("preserved_fog", "sere_talon", "distinguished_cape")
POOL_3: tuple[str, ...] = (
    "choices_paradox", "music_box", "lords_parasol", "jeweled_mask",
)


@register_event
class VakuuEvent(AncientEvent):
    id = "vakuu"
    name = "Vakuu"

    def initial_options(self) -> list[EventOption]:
        rng = self.rng
        picks = (
            rng.choice(list(POOL_1)),
            rng.choice(list(POOL_2)),
            rng.choice(list(POOL_3)),
        )
        options = []
        for rid in picks:
            if rid == "distinguished_cape":
                options.append(self._cape_option())
            else:
                options.append(self._relic_option(rid))
        return options

    def _cape_option(self) -> EventOption:
        """RelicOption<DistinguishedCape>().ThatDecreasesMaxHp(9): the OPTION
        costs 9 Max HP on top of the relic's own pickup effect."""
        from ..relics import make_relic
        from ..relics.distinguished_cape import DistinguishedCape

        def on_chosen() -> None:
            self.run.lose_max_hp(DistinguishedCape.MAX_HP_LOSS)
            self.run.add_relic(make_relic("distinguished_cape"))
            self._finish("DONE")

        return EventOption("distinguished_cape", on_chosen)
