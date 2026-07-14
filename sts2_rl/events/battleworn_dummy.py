from __future__ import annotations

from ..monsters.glory import (
    BATTLEWORN_DUMMY_SETTING_1,
    BATTLEWORN_DUMMY_SETTING_2,
    BATTLEWORN_DUMMY_SETTING_3,
)
from .base import Event, EventOption, register_event


@register_event
class BattlewornDummy(Event):
    """Battleworn Dummy — pick a difficulty and race to destroy a training
    dummy in 3 turns.

    Source: BattlewornDummy.cs (a shared event)
      SETTING_1: fight a 75 HP dummy → potion reward on victory
      SETTING_2: fight a 150 HP dummy → 2 card upgrades on victory
      SETTING_3: fight a 300 HP dummy → relic reward on victory
    The dummies never attack but flee after 3 turns; the reward (only on a timely
    victory) is granted post-combat and is not modelled — like the other
    combat-entering events, this sets `pending_encounter` and finishes."""

    id = "battleworn_dummy"
    name = "Battleworn Dummy"

    def initial_options(self) -> list[EventOption]:
        return [
            EventOption("SETTING_1", self._setting_1),
            EventOption("SETTING_2", self._setting_2),
            EventOption("SETTING_3", self._setting_3),
        ]

    def _setting_1(self) -> None:
        self.pending_encounter = BATTLEWORN_DUMMY_SETTING_1
        self._finish("SETTING_1")

    def _setting_2(self) -> None:
        self.pending_encounter = BATTLEWORN_DUMMY_SETTING_2
        self._finish("SETTING_2")

    def _setting_3(self) -> None:
        self.pending_encounter = BATTLEWORN_DUMMY_SETTING_3
        self._finish("SETTING_3")
