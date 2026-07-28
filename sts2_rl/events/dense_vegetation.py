from __future__ import annotations

import random
from typing import TYPE_CHECKING

from ..monsters import Encounter, Monster
from ..monsters.overgrowth import Wriggler
from .base import Event, EventOption, register_event

if TYPE_CHECKING:
    from ..hooks import HookSystem
    from ..rewards import CombatRewards

_HP_LOSS = 8  # HpLossVar(8)


class _WrigglerNestEncounter(Encounter):
    """DenseVegetationEventEncounter.cs: four Wrigglers (not start-stunned) in
    slots wriggler1..4 — odd slots open with Nasty Bite, even with Wriggle."""

    def create_monsters(self, hooks: HookSystem, rng: random.Random, selection_rng=None) -> list[Monster]:
        return [
            Wriggler(hooks, rng, start_stunned=False, slot=slot)
            for slot in range(1, 5)
        ]


DENSE_VEGETATION_EVENT_ENCOUNTER = _WrigglerNestEncounter(
    id="dense_vegetation_event",
    monster_classes=[Wriggler] * 4,
)


@register_event
class DenseVegetation(Event):
    """Dense Vegetation — hack through for gold, or rest and get ambushed.

    Source: DenseVegetation.cs
      CalculateVars: Gold = NextInt(61, 100); Heal = rest-site heal amount
      TRUDGE_ON: lose 8 HP (unblockable, unpowered), gain the gold
      REST:      rest-site heal (30% max HP), then the only option is
      FIGHT:     enter combat vs 4 Wrigglers (no event resume afterwards)
    """

    id = "dense_vegetation"
    name = "Dense Vegetation"

    def __init__(self, run) -> None:
        super().__init__(run)
        self.gold = 0
        # The rest-site heal's reward screen (HealRestSiteOption.
        # ExecuteRestSiteHeal's RewardsCmd.OfferCustom — Dream Catcher's
        # 3-card choice). Set by REST; the driver offers it.
        self.pending_rewards: "CombatRewards | None" = None

    def calculate_vars(self) -> None:
        self.gold = self.rng.randint(61, 99)  # Rng.NextInt(61, 100)

    def initial_options(self) -> list[EventOption]:
        return [
            EventOption("TRUDGE_ON", self._trudge_on),
            EventOption("REST", self._rest),
        ]

    def _trudge_on(self) -> None:
        self.run.lose_hp(_HP_LOSS)
        self.run.gain_gold(self.gold)
        self._finish("TRUDGE_ON")

    def _rest(self) -> None:
        # PlayerCmd.MimicRestSiteHeal → HealRestSiteOption.ExecuteRestSiteHeal:
        # heal, fire Hook.AfterRestSiteHeal (Stone Humidifier's +5 Max HP),
        # then Hook.ModifyRestSiteHealRewards and offer what it built
        # (Dream Catcher's 3-card choice) — the same pair a real rest takes.
        self.run.rest_heal()
        self.pending_rewards = self.run.rest_heal_rewards()
        self._set_state("REST", [EventOption("FIGHT", self._fight)])

    def _fight(self) -> None:
        # EnterCombatWithoutExitingEvent(shouldResumeAfterCombat: false):
        # the event is over once the fight starts.
        self.pending_encounter = DENSE_VEGETATION_EVENT_ENCOUNTER
        self._finish("REST")
