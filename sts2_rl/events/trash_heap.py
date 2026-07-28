from __future__ import annotations

from typing import TYPE_CHECKING

from ..cards import make_card
from .base import Event, EventOption, register_event

if TYPE_CHECKING:
    from ..run import RunState

_HP_LOSS = 8   # HpLossVar(8)
_GOLD = 100    # GoldVar(100)

# TrashHeap.cs Relics / Cards (fixed pools, not the run's grab bag).
_RELICS = ("darkstone_periapt", "dream_catcher", "hand_drill", "maw_bank", "the_boot")
_CARDS = (
    "caltrops", "clash", "distraction", "dual_wield", "entrench",
    "hello_world", "outmaneuver", "rebound", "rip_and_tear", "stack",
)


@register_event
class TrashHeap(Event):
    """Trash Heap — dive in for a relic (taking damage), or grab gold and a card.

    Source: TrashHeap.cs
      IsAllowed: current HP > 5
      DIVE_IN: take 8 damage (unblockable, unpowered), obtain a random relic
               from the fixed pool
      GRAB:    gain 100 gold and add a random card from the fixed pool
    """

    id = "trash_heap"
    name = "Trash Heap"

    @classmethod
    def is_allowed(cls, run: RunState) -> bool:
        return run.hp > 5

    def initial_options(self) -> list[EventOption]:
        return [
            EventOption("DIVE_IN", self._dive_in),
            EventOption("GRAB", self._grab),
        ]

    def _dive_in(self) -> None:
        self.run.lose_hp(_HP_LOSS)
        # `base.Rng.NextItem(Relics)` — the event's own Rng (TrashHeap.cs:65).
        er = self.event_rng
        relic = (er.next_item(_RELICS) if er is not None
                 else self.rng.choice(_RELICS))
        self.run.add_relic(relic)
        self._finish("DIVE_IN")

    def _grab(self) -> None:
        self.run.gain_gold(_GOLD)
        # `base.Rng.NextItem(Cards)` — the event's own Rng (TrashHeap.cs:73).
        er = self.event_rng
        card_id = (er.next_item(_CARDS) if er is not None
                   else self.rng.choice(_CARDS))
        self.run.add_card(make_card(card_id))
        self._finish("GRAB")
