from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Event, EventOption, register_event

if TYPE_CHECKING:
    from ..run import RunState

_GOLD_COST = 100     # GoldVar(100)


@register_event
class RanwidTheElder(Event):
    """Ranwid the Elder — trade a potion, gold, or a relic for relics.

    Shared event (ModelDb.AllSharedEvents). Source: RanwidTheElder.cs
      IsAllowed: acts 2-3, and the player has a tradable relic AND >= 100
                 gold AND at least one potion
      POTION: give the shown random potion -> 1 grab-bag relic
      GOLD:   pay 100 gold             -> 1 grab-bag relic
      RELIC:  give the shown random tradable relic -> 2 grab-bag relics
      (POTION/RELIC lock when their roll finds nothing.)

    The source's CanRemovePotions=false guard is UI-only and not modeled.
    """

    id = "ranwid_the_elder"
    name = "Ranwid the Elder"

    @classmethod
    def is_allowed(cls, run: RunState) -> bool:
        return (
            run.act_index != 0
            and any(r.is_tradable for r in run.relics)
            and run.gold >= _GOLD_COST
            and len(run.held_potions) > 0
        )

    def initial_options(self) -> list[EventOption]:
        options: list[EventOption] = []
        # Same roll order as GenerateInitialOptions: potion, then relic.
        held = self.run.held_potions
        potion = self.rng.choice(held) if held else None
        if potion is not None:
            options.append(EventOption(
                "POTION", lambda p=potion: self._give_potion(p)))
        else:
            options.append(EventOption("POTION_LOCKED", None))
        options.append(EventOption("GOLD", self._give_gold))
        tradable = [r for r in self.run.relics if r.is_tradable]
        relic = self.rng.choice(tradable) if tradable else None
        if relic is not None:
            options.append(EventOption(
                "RELIC", lambda r=relic: self._give_relic(r)))
        else:
            options.append(EventOption("RELIC_LOCKED", None))
        return options

    def _obtain_grab_bag(self, count: int) -> None:
        for _ in range(count):
            relic = self.run.pull_relic_from_front()
            if relic is not None:
                self.run.add_relic(relic)

    def _give_potion(self, potion) -> None:
        self.run.discard_potion(potion)
        self._obtain_grab_bag(1)
        self._finish("POTION")

    def _give_gold(self) -> None:
        self.run.lose_gold(_GOLD_COST)
        self._obtain_grab_bag(1)
        self._finish("GOLD")

    def _give_relic(self, relic) -> None:
        self.run.relics.remove(relic)
        self._obtain_grab_bag(2)
        self._finish("RELIC")
