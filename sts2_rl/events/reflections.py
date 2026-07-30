from __future__ import annotations

import copy

from ..cards import make_card
from .base import Event, EventOption, register_event

_DOWNGRADES = 2   # TouchAMirror: downgrade up to 2 upgraded cards
_UPGRADES = 4     # TouchAMirror: then upgrade up to 4 upgradable cards


@register_event
class Reflections(Event):
    """Reflections — touch a mirror to reshuffle upgrades, or shatter it to
    duplicate your whole deck.

    Source: Reflections.cs
      TOUCH_A_MIRROR: downgrade up to 2 random upgraded cards, then upgrade up
                      to 4 random upgradable cards (recomputed afterwards)
      SHATTER:        add a copy of every card currently in the deck, then add a
                      Bad Luck curse
    """

    id = "reflections"
    name = "Reflections"

    def initial_options(self) -> list[EventOption]:
        return [
            EventOption("TOUCH_A_MIRROR", self._touch_a_mirror),
            EventOption("SHATTER", self._shatter),
        ]

    def _touch_a_mirror(self) -> None:
        # Both picks are `base.Rng.NextItem` on the event's own Rng
        # (Reflections.cs:41/54).
        er = self.event_rng
        upgraded = [c for c in self.run.deck if c.upgrade_level > 0]
        for _ in range(_DOWNGRADES):
            if not upgraded:
                break
            card = (er.next_item(upgraded) if er is not None
                    else self.rng.choice(upgraded))
            upgraded.remove(card)
            # Reflections.cs:43 -- CardCmd.Downgrade. Out of combat, so its
            # IsEnding guard is vacuously false.
            from ..cmds import CardCmd
            CardCmd.downgrade(None, card)
        upgradable = [c for c in self.run.deck if c.is_upgradable]
        for _ in range(_UPGRADES):
            if not upgradable:
                break
            card = (er.next_item(upgradable) if er is not None
                    else self.rng.choice(upgradable))
            upgradable.remove(card)
            card.upgrade()
        self._finish("TOUCH_A_MIRROR")

    def _shatter(self) -> None:
        for card in list(self.run.deck):
            self.run.add_card(copy.deepcopy(card))
        self.run.add_card(make_card("bad_luck"))
        self._finish("SHATTER")
