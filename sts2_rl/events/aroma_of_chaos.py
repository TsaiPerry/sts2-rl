from __future__ import annotations

from .base import Event, EventOption, register_event


@register_event
class AromaOfChaos(Event):
    """Aroma of Chaos — transform a card, or upgrade a card.

    Source: AromaOfChaos.cs
      LET_GO:           choose 1 deck card to transform into a random card
      MAINTAIN_CONTROL: choose 1 deck card to upgrade
    """

    id = "aroma_of_chaos"
    name = "Aroma of Chaos"

    def initial_options(self) -> list[EventOption]:
        return [
            EventOption("LET_GO", self._let_go),
            EventOption("MAINTAIN_CONTROL", self._maintain_control),
        ]

    def _let_go(self) -> None:
        chosen = self.run.select_cards("transform", self.run.transformable_cards(), 1)
        if chosen:
            self.run.transform_card(chosen[0])
        self._finish("LET_GO")

    def _maintain_control(self) -> None:
        chosen = self.run.select_cards("upgrade", self.run.upgradable_cards(), 1)
        if chosen:
            chosen[0].upgrade()
        self._finish("MAINTAIN_CONTROL")
