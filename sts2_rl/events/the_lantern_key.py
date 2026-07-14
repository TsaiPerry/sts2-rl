from __future__ import annotations

from ..monsters.hive.flail_knight import MYSTERIOUS_KNIGHT_EVENT_ENCOUNTER
from .base import Event, EventOption, register_event

_GOLD = 100  # GoldVar(100)


@register_event
class TheLanternKey(Event):
    """The Lantern Key — return the key for gold, or keep it and fight.

    Source: TheLanternKey.cs
      RETURN_THE_KEY: gain 100 gold
      KEEP_THE_KEY → FIGHT: fight a Mysterious Knight (a Flail Knight with 6
                     Strength and 6 Plating). The Lantern Key card reward and
                     the map redirection it causes are not modelled.
    """

    id = "the_lantern_key"
    name = "The Lantern Key"

    def initial_options(self) -> list[EventOption]:
        return [
            EventOption("RETURN_THE_KEY", self._return_the_key),
            EventOption("KEEP_THE_KEY", self._keep_the_key),
        ]

    def _return_the_key(self) -> None:
        self.run.gain_gold(_GOLD)
        self._finish("RETURN_THE_KEY")

    def _keep_the_key(self) -> None:
        self._set_state("KEEP_THE_KEY", [EventOption("FIGHT", self._fight)])

    def _fight(self) -> None:
        self.pending_encounter = MYSTERIOUS_KNIGHT_EVENT_ENCOUNTER
        self._finish("KEEP_THE_KEY")
