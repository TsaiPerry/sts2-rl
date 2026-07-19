from __future__ import annotations

from typing import TYPE_CHECKING

from ..cards import make_card
from ..potions import random_potion
from .base import Event, EventOption, register_event

if TYPE_CHECKING:
    from ..run import RunState

_HP_LOSS = 8         # DamageVar(8, Unblockable | Unpowered)


@register_event
class TheLegendsWereTrue(Event):
    """The Legends Were True — the Spoils Map, or the slow way out.

    Shared event (ModelDb.AllSharedEvents). Source: TheLegendsWereTrue.cs
      IsAllowed: act 1 only, deck non-empty, current HP >= 10
      NAB_THE_MAP:         add a Spoils Map card to the deck
      SLOWLY_FIND_AN_EXIT: take 8 damage, offered 1 random potion (the
                           source rolls PlayerRng.Rewards over the unlocked
                           pools; the sim's single stream + reward pool)
    """

    id = "the_legends_were_true"
    name = "The Legends Were True"

    @classmethod
    def is_allowed(cls, run: RunState) -> bool:
        return run.act_index == 0 and len(run.deck) > 0 and run.hp >= 10

    def initial_options(self) -> list[EventOption]:
        return [
            EventOption("NAB_THE_MAP", self._nab_the_map),
            EventOption("SLOWLY_FIND_AN_EXIT", self._slowly_find_an_exit),
        ]

    def _nab_the_map(self) -> None:
        self.run.add_card(make_card("spoils_map"))
        self._finish("NAB_THE_MAP")

    def _slowly_find_an_exit(self) -> None:
        self.run.lose_hp(_HP_LOSS)
        # Potion offers auto-keep when a slot is free (sim convention).
        self.run.add_potion(random_potion(self.rng))
        self._finish("SLOWLY_FIND_AN_EXIT")
