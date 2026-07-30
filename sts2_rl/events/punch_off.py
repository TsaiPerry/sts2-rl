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
    Fast Punch — each with its starting HP cut by NextInt(2, 10) (2..9).

    PunchConstruct.AfterAddedToRoom (PunchConstruct.cs:75-78) spends the
    reduction as SetCurrentHpInternal(Max(1, CurrentHp - reduction)): only
    CURRENT HP drops, MaxHp stays at the model's 55."""

    def create_monsters(self, hooks: HookSystem, rng: random.Random, selection_rng=None) -> list[Monster]:
        monsters = []
        for i in range(2):
            m = PunchConstruct(hooks, rng, starts_with_fast_punch=(i == 0))
            # PunchOffEventEncounter.cs:17,:19 roll `base.Rng.NextInt(2, 10)`
            # on the per-encounter EncounterModel Rng (EncounterModel.cs:259-270),
            # not on the shared combat stream. `selection_rng` IS that stream
            # and was being accepted and ignored; five sibling encounters
            # already thread it (scroll_of_biting, corpse_slug,
            # slithering_strangler, decimillipede, slimes).
            m.starting_hp_reduction = (
                selection_rng.next_int_range(2, 10) if selection_rng is not None
                else rng.randint(2, 9))
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

    # PunchOff.cs:33-35 — a Combat-layout event, so the two constructs (and
    # their HP rolls) are generated when the room is entered, not when FIGHT is
    # chosen.
    is_combat_layout = True
    canonical_encounter = PUNCH_OFF_EVENT_ENCOUNTER

    @classmethod
    def is_allowed(cls, run: RunState) -> bool:
        return run.total_floor >= _MIN_FLOOR

    def calculate_vars(self) -> None:
        # GoldVar rolled for fidelity but never granted by either option.
        # `base.Rng.NextInt(91, 99)` (PunchOff.cs:103) — the event's own Rng
        # (event/EV-3); the draw exists only to advance that stream.
        er = self.event_rng
        if er is not None:
            er.next_int_range(91, 99)
        else:
            self.rng.randint(91, 98)

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
        # EnterCombatWithoutExitingEvent reuses the state built at room entry
        # (ShouldCreateCombat = LayoutType != Combat, EventModel.cs:624-628).
        self.pending_encounter = self.internal_combat_encounter()
        # PunchOff.cs Fight(): RelicReward + PotionReward ride the fight's
        # reward screen (both rolled at screen time).
        self.pending_reward_extras = [RewardExtra.of_relic(), RewardExtra.of_potion()]
        self._finish("I_CAN_TAKE_THEM")
