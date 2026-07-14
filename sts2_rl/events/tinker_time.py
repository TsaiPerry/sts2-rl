from __future__ import annotations

from ..cards import CardType
from ..cards.mad_science import MadScienceCard
from .base import Event, EventOption, register_event

# The two card types the player is offered are 2 random of these three; each
# then offers 2 random of its three riders (TinkerTime.cs). Option keys mirror
# the source loc names (GetRiderLocKey).
_TYPE_KEYS = {
    CardType.ATTACK: "ATTACK",
    CardType.SKILL: "SKILL",
    CardType.POWER: "POWER",
}
_TYPE_RIDERS = {
    CardType.ATTACK: ["sapping", "violence", "choking"],
    CardType.SKILL: ["energized", "wisdom", "chaos"],
    CardType.POWER: ["expertise", "curious", "improvement"],
}


@register_event
class TinkerTime(Event):
    """Tinker Time — build a Mad Science card by choosing its type and a rider.

    Source: TinkerTime.cs
      CHOOSE_CARD_TYPE: offered 2 of {Attack, Skill, Power}
      CHOOSE_RIDER:     offered 2 of the chosen type's 3 riders
      then add a Mad Science card carrying that type + rider to the deck
    """

    id = "tinker_time"
    name = "Tinker Time"

    def __init__(self, run) -> None:
        super().__init__(run)
        self._chosen_type: CardType | None = None

    def initial_options(self) -> list[EventOption]:
        return [EventOption("CHOOSE_CARD_TYPE", self._choose_card_type)]

    def _choose_card_type(self) -> None:
        types = self.rng.sample(list(_TYPE_RIDERS), 2)  # TakeRandom(2)
        options = [
            EventOption(_TYPE_KEYS[t], self._make_type_chooser(t)) for t in types
        ]
        self._set_state("CHOOSE_CARD_TYPE", options)

    def _make_type_chooser(self, card_type: CardType):
        def choose() -> None:
            self._chosen_type = card_type
            self._choose_rider()
        return choose

    def _choose_rider(self) -> None:
        riders = self.rng.sample(_TYPE_RIDERS[self._chosen_type], 2)  # TakeRandom(2)
        options = [
            EventOption(rider.upper(), self._make_rider_chooser(rider)) for rider in riders
        ]
        self._set_state("CHOOSE_RIDER", options)

    def _make_rider_chooser(self, rider: str):
        def choose() -> None:
            card = MadScienceCard().configure(self._chosen_type, rider)
            self.run.add_card(card)
            self._finish("DONE")
        return choose
