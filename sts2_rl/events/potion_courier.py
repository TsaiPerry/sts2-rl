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
        # One RewardsCmd.OfferCustom screen carrying three independent
        # PotionRewards (PotionCourier.cs:36-44) — each is take-or-skip.
        for _ in range(_FOUL_POTIONS):
            self.offer_potion(make_potion("foul_potion"))
        self._finish("GRAB_POTIONS")

    def _ransack(self) -> None:
        # The pick is rolled first, then offered take-or-skip
        # (RewardsCmd.OfferCustom — PotionCourier.cs:48-60).
        if self.run.rng_set is not None:
            from ..potion_pools import _make
            options = [
                pid for pid, r in self.run.potion_pool if r == "uncommon"
            ]
            pid = self.run.rewards_rng.next_item(options)
            if pid is not None:
                self.offer_potion(_make(pid, "uncommon"))
        else:
            uncommon = sorted(
                (
                    cls for cls in ALL_POTIONS.values()
                    if cls.rarity == "uncommon" and self.run.owns_potion(cls)
                ),
                key=lambda cls: cls.id,
            )
            if uncommon:
                self.offer_potion(self.rng.choice(uncommon)())
        self._finish("RANSACK")
