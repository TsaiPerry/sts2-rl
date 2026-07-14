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
        self.run.add_relic(make_relic("big_mushroom"))
        self.run.gain_max_hp(_BIG_MUSHROOM_MAX_HP)
        self._finish("BIG_MUSHROOM")

    def _fragrant_mushroom(self) -> None:
        self.run.add_relic(make_relic("fragrant_mushroom"))
        self.run.lose_hp(_FRAGRANT_HP_LOSS)
        upgradable = self.run.upgradable_cards()
        count = min(_FRAGRANT_CARDS, len(upgradable))
        for card in self.rng.sample(upgradable, count):
            card.upgrade()
        self._finish("FRAGRANT_MUSHROOM")
