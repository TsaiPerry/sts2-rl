from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Event, EventOption, register_event

if TYPE_CHECKING:
    from ..run import RunState

_MIN_HP = 12       # IsAllowed: current HP >= 12
_DAMAGE = 11       # DamageVar(11, Unblockable | Unpowered)


@register_event
class RoundTeaParty(Event):
    """Round Tea Party — take the Royal Poison relic and heal, or pick a fight
    for a relic.

    Source: RoundTeaParty.cs
      IsAllowed: current HP >= 12
      ENJOY_TEA:  obtain Royal Poison, then heal to full
      PICK_FIGHT → CONTINUE_FIGHT: take 11 unblockable damage, obtain a relic
                   from the front of the grab bag
    """

    id = "round_tea_party"
    name = "Round Tea Party"

    @classmethod
    def is_allowed(cls, run: RunState) -> bool:
        return run.hp >= _MIN_HP

    def initial_options(self) -> list[EventOption]:
        return [
            EventOption("ENJOY_TEA", self._enjoy_tea),
            EventOption("PICK_FIGHT", self._pick_fight),
        ]

    def _enjoy_tea(self) -> None:
        self.run.add_relic("royal_poison")
        self.run.heal(self.run.max_hp - self.run.hp)
        self._finish("ENJOY_TEA")

    def _pick_fight(self) -> None:
        self._set_state("PICK_FIGHT", [EventOption("CONTINUE_FIGHT", self._continue_fight)])

    def _continue_fight(self) -> None:
        self.run.lose_hp(_DAMAGE)
        self.run.obtain_relic_from_grab_bag()
        self._finish("CONTINUE_FIGHT")
