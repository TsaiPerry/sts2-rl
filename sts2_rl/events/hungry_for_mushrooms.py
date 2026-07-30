from __future__ import annotations

from ..relics import make_relic
from .base import Event, EventOption, register_event

_BIG_MUSHROOM_MAX_HP = 20    # BigMushroom MaxHpVar(20)
_FRAGRANT_HP_LOSS = 15       # FragrantMushroom HpLossVar(15)
_FRAGRANT_CARDS = 2          # FragrantMushroom CardsVar(2)


@register_event
class HungryForMushrooms(Event):
    """Hungry for Mushrooms — pick one of two mushroom relics.

    Source: HungryForMushrooms.cs
      BIG_MUSHROOM:      obtain Big Mushroom (gain 20 Max HP; draws 2 fewer on
                         the first turn of combat)
      FRAGRANT_MUSHROOM: obtain Fragrant Mushroom (lose 15 HP, upgrade 2 random
                         cards)
    The relics' upon-pickup effects are applied here (RunState has no run-level
    AfterObtained dispatch)."""

    id = "hungry_for_mushrooms"
    name = "Hungry for Mushrooms"

    def initial_options(self) -> list[EventOption]:
        return [
            EventOption("BIG_MUSHROOM", self._big_mushroom),
            EventOption("FRAGRANT_MUSHROOM", self._fragrant_mushroom),
        ]

    def _big_mushroom(self) -> None:
        # The +20 Max HP is the RELIC's own pickup effect
        # (BigMushroom.cs:24-28, fired via add_relic), like Fragrant
        # Mushroom's below. The event used to apply it here instead.
        self.run.add_relic(make_relic("big_mushroom"))
        self._finish("BIG_MUSHROOM")

    def _fragrant_mushroom(self) -> None:
        # The HP loss + 2 upgrades are the relic's own pickup effect
        # (FragrantMushroom.cs AfterObtained, fired via add_relic).
        self.run.add_relic(make_relic("fragrant_mushroom"))
        self._finish("FRAGRANT_MUSHROOM")
