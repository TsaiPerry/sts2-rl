from __future__ import annotations

from typing import TYPE_CHECKING

from ..cards import make_card
from .base import Event, EventOption, register_event

if TYPE_CHECKING:
    from ..run import RunState

_HP_LOSS = 6         # HpLossVar(6)
_GOLD_MIN = 41       # CalculateVars: NextInt(41, 69)
_GOLD_MAX = 68


@register_event
class ThisOrThat(Event):
    """This or That — a plain box of gold, or an ornate one with a catch.

    Shared event (ModelDb.AllSharedEvents). Source: ThisOrThat.cs
      PLAIN:  take 6 damage (unblockable, unpowered), gain 41-68 gold
      ORNATE: obtain the next grab-bag relic, gain a Clumsy curse
    """

    id = "this_or_that"
    name = "This or That"

    def calculate_vars(self) -> None:
        self._gold = self.rng.randint(_GOLD_MIN, _GOLD_MAX)

    def initial_options(self) -> list[EventOption]:
        return [
            EventOption("PLAIN", self._plain),
            EventOption("ORNATE", self._ornate),
        ]

    def _plain(self) -> None:
        self.run.lose_hp(_HP_LOSS)
        self.run.gain_gold(self._gold)
        self._finish("PLAIN")

    def _ornate(self) -> None:
        relic = self.run.pull_relic_from_front()
        if relic is not None:
            self.run.add_relic(relic)
        self.run.add_card(make_card("clumsy"))
        self._finish("ORNATE")
