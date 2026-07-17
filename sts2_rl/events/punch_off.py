from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ..cards import make_card
from ..monsters import Encounter, Monster
from ..monsters.underdocks.punch_construct import PunchConstruct
from .base import Event, EventOption, register_event

if TYPE_CHECKING:
    from ..hooks import HookSystem
    from ..run import RunState

_MIN_FLOOR = 6  # IsAllowed: TotalFloor >= 6


class _PunchOffEncounter(Encounter):
    """PunchOffEventEncounter.cs: two Punch Constructs — the left one opens with
    Fast Punch — each with its starting HP cut by NextInt(2, 10) (2..9)."""

    def create_monsters(self, hooks: HookSystem, rng: random.Random) -> list[Monster]:
        monsters = []
        for i in range(2):
            m = PunchConstruct(hooks, rng, starts_with_fast_punch=(i == 0))
            reduction = rng.randint(2, 9)  # NextInt(2, 10)
            m.max_hp = max(1, m.max_hp - reduction)
            m.hp = min(m.hp, m.max_hp)
            monsters.append(m)
        return monsters


PUNCH_OFF_EVENT_ENCOUNTER = _PunchOffEncounter(
    id="punch_off_event",
    monster_classes=[PunchConstruct, PunchConstruct],
)


@register_event
class PunchOff(Event):
    """Punch-Off — nab a relic (and an Injury), or fight the constructs.

    Source: PunchOff.cs
      IsAllowed: TotalFloor >= 6
      NAB:        add an Injury curse, obtain a relic
      I_CAN_TAKE_THEM → FIGHT: fight two Punch Constructs; the fight's reward
                        screen carries a RelicReward + PotionReward on top of
                        the normal Monster rewards (Fight()'s extraRewards →
                        EnterCombatWithoutExitingEvent; not resumed afterwards)
    """

    id = "punch_off"
    name = "Punch-Off"

    @classmethod
    def is_allowed(cls, run: RunState) -> bool:
        return run.total_floor >= _MIN_FLOOR

    def calculate_vars(self) -> None:
        # GoldVar rolled for fidelity but never granted by either option.
        self.rng.randint(91, 98)  # NextInt(91, 99)

    def initial_options(self) -> list[EventOption]:
        return [
            EventOption("NAB", self._nab),
            EventOption("I_CAN_TAKE_THEM", self._take_them),
        ]

    def _nab(self) -> None:
        self.run.add_card(make_card("injury"))
        self.run.obtain_relic_from_grab_bag()
        self._finish("NAB")

    def _take_them(self) -> None:
        self._set_state("I_CAN_TAKE_THEM", [EventOption("FIGHT", self._fight)])

    def _fight(self) -> None:
        from ..rewards import RewardExtra
        self.pending_encounter = PUNCH_OFF_EVENT_ENCOUNTER
        # PunchOff.cs Fight(): RelicReward + PotionReward ride the fight's
        # reward screen (both rolled at screen time).
        self.pending_reward_extras = [RewardExtra.of_relic(), RewardExtra.of_potion()]
        self._finish("I_CAN_TAKE_THEM")
