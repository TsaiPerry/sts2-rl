from __future__ import annotations

from typing import TYPE_CHECKING

from ..monsters.glory import (
    BATTLEWORN_DUMMY_SETTING_1,
    BATTLEWORN_DUMMY_SETTING_2,
    BATTLEWORN_DUMMY_SETTING_3,
)
from .base import Event, EventOption, register_event

if TYPE_CHECKING:
    from ..combat import CombatState
    from ..potions import Potion
    from ..run import RunState


@register_event
class BattlewornDummy(Event):
    """Battleworn Dummy — pick a difficulty and race to destroy a training
    dummy in 3 turns.

    Source: BattlewornDummy.cs (a shared event)
      SETTING_1: fight a 75 HP dummy → a take-or-skip potion offer on victory
      SETTING_2: fight a 150 HP dummy → 2 random card upgrades on victory
      SETTING_3: fight a 300 HP dummy → a grab-bag relic on victory
    The dummies never attack but flee after 3 turns; the fight has no normal
    reward screen (BattlewornDummyEventEncounter.cs ShouldGiveRewards=false).
    Resume(): a fled dummy (RanOutOfTime) grants nothing; otherwise the
    chosen setting's reward is granted — the potion is offered take-or-skip
    (RewardsCmd.OfferCustom), the upgrades and relic are applied directly."""

    id = "battleworn_dummy"
    name = "Battleworn Dummy"

    def __init__(self, run: RunState) -> None:
        super().__init__(run)
        self._setting: int | None = None

    def initial_options(self) -> list[EventOption]:
        return [
            EventOption("SETTING_1", self._setting_1),
            EventOption("SETTING_2", self._setting_2),
            EventOption("SETTING_3", self._setting_3),
        ]

    def _setting_1(self) -> None:
        self._setting = 1
        self.pending_encounter = BATTLEWORN_DUMMY_SETTING_1
        self._finish("SETTING_1")

    def _setting_2(self) -> None:
        self._setting = 2
        self.pending_encounter = BATTLEWORN_DUMMY_SETTING_2
        self._finish("SETTING_2")

    def _setting_3(self) -> None:
        self._setting = 3
        self.pending_encounter = BATTLEWORN_DUMMY_SETTING_3
        self._finish("SETTING_3")

    def resume_after_combat(self, combat: CombatState) -> list[Potion]:
        """BattlewornDummy.cs Resume: RanOutOfTime (the dummy fled) grants
        nothing; otherwise Setting1 offers a random potion, Setting2 upgrades
        2 random upgradable deck cards (StableShuffle(Rng).Take(2)), Setting3
        obtains the grab bag's next relic (RelicFactory.PullNextRelicFromFront
        → RelicCmd.Obtain)."""
        dummy = combat.enemies[0]
        if dummy.escaped:  # RanOutOfTime — DEFEAT page
            return []
        if self._setting == 1:
            return [self.run.random_potion()]
        if self._setting == 2:
            upgradable = self.run.upgradable_cards()
            self.rng.shuffle(upgradable)
            for card in upgradable[:2]:
                card.upgrade()
            return []
        if self._setting == 3:
            self.run.obtain_relic_from_grab_bag()
            return []
        raise ValueError("Setting must be set!")
