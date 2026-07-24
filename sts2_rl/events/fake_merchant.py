from __future__ import annotations

from typing import TYPE_CHECKING

from ..rewards import RewardExtra
from .base import Event, EventOption, register_event

if TYPE_CHECKING:
    from ..relics import Relic
    from ..run import RunState

_RELIC_COST = 50      # FakeMerchant.relicCost
_STOCK = 6            # Take(6) of the nine knock-offs
_GOLD_GATE = 100

# FakeMerchant._inventoryRelics — the nine knock-offs (the Rug is deliberately
# NOT in this list: it is a combat reward, not stock).
_INVENTORY = (
    "fake_anchor", "fake_blood_vial", "fake_happy_flower", "fake_lees_waffle",
    "fake_mango", "fake_orichalcum", "fake_snecko_eye", "fake_strike_dummy",
    "fake_venerable_tea_set",
)


@register_event
class FakeMerchant(Event):
    """Fake Merchant — a shady stall of knock-off relics, 50 gold each.

    Shared event (ModelDb.AllSharedEvents). Source: FakeMerchant.cs
      IsAllowed: acts 2-3, single-player, and either >= 100 gold OR a Foul
                 Potion in the belt
      BeforeEventStarted stocks 6 of the 9 knock-offs (UnstableShuffle, Take 6)
      <relic id>:    buy that knock-off for 50 gold (locked when broke)
      THROW_POTION:  spend a Foul Potion to expose him — starts the Fake
                     Merchant fight, whose rewards are his Rug plus every
                     relic still on the shelf (FoulPotionThrown)
      LEAVE:         walk away

    Documented approximation: the source drives this through a bespoke
    merchant UI (EventLayoutType.Custom, so GenerateInitialOptions is empty
    and buying happens on the shop screen). The sim has no custom screens, so
    the stall's stock is surfaced as ordinary event options — the same
    treatment the merchant room gets. Buying does not end the event; the
    source lets you clear the whole shelf.
    """

    id = "fake_merchant"
    name = "Fake Merchant"

    @classmethod
    def is_allowed(cls, run: RunState) -> bool:
        if run.act_index < 1:
            return False
        return run.gold >= _GOLD_GATE or cls._has_foul_potion(run)

    @staticmethod
    def _has_foul_potion(run: RunState) -> bool:
        return any(p.id == "foul_potion" for p in run.held_potions)

    def calculate_vars(self) -> None:
        from ..relics import make_relic

        stock = list(_INVENTORY)
        self.rng.shuffle(stock)                      # UnstableShuffle
        self.stock: list[Relic] = [make_relic(r) for r in stock[:_STOCK]]

    def _page_options(self) -> list[EventOption]:
        options: list[EventOption] = []
        for relic in self.stock:
            if self.run.gold >= _RELIC_COST:
                options.append(EventOption(
                    relic.id, lambda r=relic: self._buy(r)))
            else:
                options.append(EventOption(f"{relic.id}_LOCKED", None))
        if self._has_foul_potion(self.run):
            options.append(EventOption("THROW_POTION", self._throw_potion))
        options.append(EventOption("LEAVE", self._leave))
        return options

    def initial_options(self) -> list[EventOption]:
        return self._page_options()

    def _buy(self, relic: Relic) -> None:
        self.run.lose_gold(_RELIC_COST)
        self.run.add_relic(relic)
        self.stock.remove(relic)
        # The stall stays open until you leave or blow it up.
        self._set_state("INITIAL", self._page_options())

    def _throw_potion(self) -> None:
        from ..monsters.fake_merchant import FAKE_MERCHANT_EVENT_ENCOUNTER
        from ..relics import make_relic

        potion = next(p for p in self.run.held_potions if p.id == "foul_potion")
        self.run.discard_potion(potion)
        self.pending_encounter = FAKE_MERCHANT_EVENT_ENCOUNTER
        # FoulPotionThrown: the Rug, plus every relic still unsold.
        self.pending_reward_extras = [
            RewardExtra.of_relic(make_relic("fake_merchants_rug"))
        ] + [RewardExtra.of_relic(r) for r in self.stock]
        self._finish("THROW_POTION")

    def _leave(self) -> None:
        self._finish("LEAVE")
