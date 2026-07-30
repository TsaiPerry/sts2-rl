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
        er = self.event_rng
        if er is not None:
            # Vakuu.cs: UnstableShuffle each pool on the per-event Rng, take [0].
            p1, p2, p3 = list(POOL_1), list(POOL_2), list(POOL_3)
            er.shuffle(p1)
            er.shuffle(p2)
            er.shuffle(p3)
            picks = (p1[0], p2[0], p3[0])
        else:
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
        """`RelicOption<DistinguishedCape>().ThatDecreasesMaxHp(9m)`
        (Vakuu.cs:38) applies NO HP: `ThatDecreasesMaxHp` is
        `ThatWillKillPlayerIf(p => p.MaxHp <= value)` (EventOption.cs:194-197),
        a UI flag that reddens the option when taking it would be lethal. The
        −9 is the relic's own AfterObtained (DistinguishedCape.cs:31), which
        this option used to duplicate here."""
        from ..relics import make_relic

        def on_chosen() -> None:
            self.run.add_relic(make_relic("distinguished_cape"))
            self._finish("DONE")

        return EventOption("distinguished_cape", on_chosen)
