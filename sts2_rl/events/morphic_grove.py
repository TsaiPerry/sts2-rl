from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Event, EventOption, register_event

if TYPE_CHECKING:
    from ..run import RunState

_MAX_HP_GAIN = 5   # MaxHpVar(5)
_MIN_GOLD = 100    # IsAllowed gate
_TRANSFORMS = 2    # _transformCount


@register_event
class MorphicGrove(Event):
    """Morphic Grove — give all your gold to transform 2 cards, or gain max HP.

    Source: MorphicGrove.cs
      IsAllowed: gold >= 100 and at least 2 transformable deck cards
      GROUP: lose ALL gold, choose 2 cards to transform
      LONER: gain 5 max HP
    """

    id = "morphic_grove"
    name = "Morphic Grove"

    @classmethod
    def is_allowed(cls, run: RunState) -> bool:
        return run.gold >= _MIN_GOLD and len(run.transformable_cards()) >= _TRANSFORMS

    def initial_options(self) -> list[EventOption]:
        return [
            EventOption("GROUP", self._group),
            EventOption("LONER", self._loner),
        ]

    def _group(self) -> None:
        self.run.lose_gold(self.run.gold)
        chosen = self.run.select_cards(
            "transform", self.run.transformable_cards(), _TRANSFORMS
        )
        for card in chosen:
            self.run.transform_card(card)
        self._finish("GROUP")

    def _loner(self) -> None:
        self.run.gain_max_hp(_MAX_HP_GAIN)
        self._finish("LONER")
