from __future__ import annotations

from typing import TYPE_CHECKING

from ..potions import ALL_POTIONS, make_potion
from .base import Event, EventOption, register_event

if TYPE_CHECKING:
    from ..run import RunState

_FOUL_POTIONS = 3   # FoulPotions


@register_event
class PotionCourier(Event):
    """Potion Courier — grab a crate of Foul Potions, or ransack it.

    Shared event (ModelDb.AllSharedEvents). Source: PotionCourier.cs
      IsAllowed: acts 2-3 (CurrentActIndex > 0)
      GRAB_POTIONS: offered 3 Foul Potions
      RANSACK:      offered 1 random UNCOMMON potion

    RANSACK is a faithful port of a filter that currently matches nothing:
    every potion ported so far is Common/Event/Token rarity (see potions.py),
    and the source's `NextItem` over an empty sequence returns null and
    offers nothing. It starts paying out as soon as Uncommon potions land.
    """

    id = "potion_courier"
    name = "Potion Courier"

    @classmethod
    def is_allowed(cls, run: RunState) -> bool:
        return run.act_index > 0

    def initial_options(self) -> list[EventOption]:
        return [
            EventOption("GRAB_POTIONS", self._grab_potions),
            EventOption("RANSACK", self._ransack),
        ]

    def _grab_potions(self) -> None:
        # Potion offers auto-keep while a belt slot is free (sim convention).
        for _ in range(_FOUL_POTIONS):
            self.run.add_potion(make_potion("foul_potion"))
        self._finish("GRAB_POTIONS")

    def _ransack(self) -> None:
        uncommon = sorted(
            (cls for cls in ALL_POTIONS.values() if cls.rarity == "uncommon"),
            key=lambda cls: cls.id,
        )
        if uncommon:
            self.run.add_potion(self.rng.choice(uncommon)())
        self._finish("RANSACK")
