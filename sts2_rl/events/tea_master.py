from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Event, EventOption, register_event

if TYPE_CHECKING:
    from ..run import RunState

_BONE_TEA_COST = 50
_EMBER_TEA_COST = 150


@register_event
class TeaMaster(Event):
    """Tea Master — buy a tea, or accept the free discourteous one.

    Shared event (ModelDb.AllSharedEvents). Source: TeaMaster.cs
      IsAllowed: acts 1-2 (CurrentActIndex < 2) and every player has >= 150
                 gold
      BONE_TEA:           50 gold  -> Bone Tea
      EMBER_TEA:          150 gold -> Ember Tea
      TEA_OF_DISCOURTESY: free     -> Tea of Discourtesy
    The two paid options lock when their price is unaffordable (reachable
    only if gold drops between the gate and the visit).
    """

    id = "tea_master"
    name = "Tea Master"

    @classmethod
    def is_allowed(cls, run: RunState) -> bool:
        return run.act_index < 2 and run.gold >= _EMBER_TEA_COST

    def initial_options(self) -> list[EventOption]:
        options = []
        if self.run.gold >= _BONE_TEA_COST:
            options.append(EventOption("BONE_TEA", self._bone_tea))
        else:
            options.append(EventOption("BONE_TEA_LOCKED", None))
        if self.run.gold >= _EMBER_TEA_COST:
            options.append(EventOption("EMBER_TEA", self._ember_tea))
        else:
            options.append(EventOption("EMBER_TEA_LOCKED", None))
        options.append(
            EventOption("TEA_OF_DISCOURTESY", self._tea_of_discourtesy))
        return options

    def _bone_tea(self) -> None:
        self.run.lose_gold(_BONE_TEA_COST)
        self.run.add_relic("bone_tea")
        self._finish("DONE")

    def _ember_tea(self) -> None:
        self.run.lose_gold(_EMBER_TEA_COST)
        self.run.add_relic("ember_tea")
        self._finish("DONE")

    def _tea_of_discourtesy(self) -> None:
        self.run.add_relic("tea_of_discourtesy")
        self._finish("TEA_OF_DISCOURTESY")
