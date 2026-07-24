from __future__ import annotations

from typing import TYPE_CHECKING

from ..potions import ALL_POTIONS, make_potion
from .base import Event, EventOption, register_event

if TYPE_CHECKING:
    from ..run import RunState

_FOUL_POTIONS = 3   # FoulPotions


@register_event
class PotionCourier(Event):
    """Potion Courier — grab a crate of Foul Potions, or ransack it.

    Shared event (ModelDb.AllSharedEvents). Source: PotionCourier.cs
      IsAllowed: acts 2-3 (CurrentActIndex > 0)
      GRAB_POTIONS: offered 3 Foul Potions
      RANSACK:      offered 1 random UNCOMMON potion

    RANSACK is `PlayerRng.Rewards.NextItem(<character pool + SharedPotionPool>
    .Where(Rarity == Uncommon))` — ONE draw on the per-player Rewards stream
    over the GAME's whole uncommon pool in pool order. The parity path uses
    exactly that (unimplemented uncommons come back as pool placeholders, as
    everywhere else the full pool is modelled); the legacy RL path keeps the
    old shared-rng pick over the *implemented* uncommons so a training run
    never puts an inert placeholder on the belt.
    """

    id = "potion_courier"
    name = "Potion Courier"

    @classmethod
    def is_allowed(cls, run: RunState) -> bool:
        return run.act_index > 0

    def initial_options(self) -> list[EventOption]:
        return [
            EventOption("GRAB_POTIONS", self._grab_potions),
            EventOption("RANSACK", self._ransack),
        ]

    def _grab_potions(self) -> None:
        # Potion offers auto-keep while a belt slot is free (sim convention).
        for _ in range(_FOUL_POTIONS):
            self.run.add_potion(make_potion("foul_potion"))
        self._finish("GRAB_POTIONS")

    def _ransack(self) -> None:
        if self.run.rng_set is not None:
            from ..potion_pools import POTION_POOL, _make
            options = [pid for pid, r in POTION_POOL if r == "uncommon"]
            pid = self.run.rewards_rng.next_item(options)
            if pid is not None:
                self.run.add_potion(_make(pid, "uncommon"))
        else:
            uncommon = sorted(
                (cls for cls in ALL_POTIONS.values() if cls.rarity == "uncommon"),
                key=lambda cls: cls.id,
            )
            if uncommon:
                self.run.add_potion(self.rng.choice(uncommon)())
        self._finish("RANSACK")
