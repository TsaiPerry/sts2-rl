from __future__ import annotations

from ..cards import make_card
from .base import Event, EventOption, register_event


@register_event
class Bugslayer(Event):
    """Bugslayer — take Exterminate, or take Squash.

    Source: Bugslayer.cs
      EXTERMINATION: add an Exterminate card
      SQUASH:        add a Squash card
    """

    id = "bugslayer"
    name = "Bugslayer"

    def initial_options(self) -> list[EventOption]:
        return [
            EventOption("EXTERMINATION", self._extermination),
            EventOption("SQUASH", self._squash),
        ]

    def _extermination(self) -> None:
        self.run.add_card(make_card("exterminate"))
        self._finish("EXTERMINATION")

    def _squash(self) -> None:
        self.run.add_card(make_card("squash"))
        self._finish("SQUASH")
