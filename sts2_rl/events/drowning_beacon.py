from __future__ import annotations

from ..potions import make_potion
from .base import Event, EventOption, register_event

_HP_LOSS = 13  # HpLossVar(13)


@register_event
class DrowningBeacon(Event):
    """Drowning Beacon — bottle the water, or climb for a relic.

    Source: DrowningBeacon.cs
      BOTTLE: gain a Glowwater Potion.
      CLIMB:  lose 13 Max HP and obtain the Fresnel Lens relic.
    """

    id = "drowning_beacon"
    name = "Drowning Beacon"

    def initial_options(self) -> list[EventOption]:
        return [
            EventOption("BOTTLE", self._bottle),
            EventOption("CLIMB", self._climb),
        ]

    def _bottle(self) -> None:
        # RewardsCmd.OfferCustom(PotionReward) — a take-or-skip screen, not a
        # grant (DrowningBeacon.cs:39-46).
        self.offer_potion(make_potion("glowwater"))
        self._finish("BOTTLE")

    def _climb(self) -> None:
        self.run.lose_max_hp(_HP_LOSS)
        self.run.add_relic("fresnel_lens")
        self._finish("CLIMB")
