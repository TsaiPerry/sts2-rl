from __future__ import annotations

from typing import TYPE_CHECKING

from ..cards import CardRarity, make_card
from .base import Event, EventOption, register_event

if TYPE_CHECKING:
    from ..run import RunState

_SEARCH_HP_LOSS = 14   # DamageVar(14, Unblockable | Unpowered)


@register_event
class RoomFullOfCheese(Event):
    """Room Full of Cheese — gorge on commons, or dig for the Chosen Cheese.

    Shared event (ModelDb.AllSharedEvents). Source: RoomFullOfCheese.cs
      IsAllowed: acts 1-2 only (CurrentActIndex < 2)
      GORGE:  pick 2 of 8 uniform-odds Common character-pool cards
      SEARCH: take 14 damage, obtain the Chosen Cheese relic
    """

    id = "room_full_of_cheese"
    name = "Room Full of Cheese"

    @classmethod
    def is_allowed(cls, run: RunState) -> bool:
        return run.act_index < 2

    def initial_options(self) -> list[EventOption]:
        return [
            EventOption("GORGE", self._gorge),
            EventOption("SEARCH", self._search),
        ]

    def _gorge(self) -> None:
        from ..cards.pool import IRONCLAD_POOL, _CARD_CLASSES

        # ForNonCombatWithUniformOdds(rarity == Common): uniform distinct
        # picks, no rarity roll.
        commons = [
            cid for cid in IRONCLAD_POOL
            if _CARD_CLASSES[cid].rarity == CardRarity.COMMON
        ]
        picks = self.rng.sample(commons, min(8, len(commons)))
        cards = [make_card(cid) for cid in picks]
        for card in self.run.select_cards("card_reward", cards, 2):
            self.run.add_card(card)
        self._finish("GORGE")

    def _search(self) -> None:
        self.run.lose_hp(_SEARCH_HP_LOSS)
        self.run.add_relic("chosen_cheese")
        self._finish("SEARCH")
