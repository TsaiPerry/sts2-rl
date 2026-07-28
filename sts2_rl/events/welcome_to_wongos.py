from __future__ import annotations

from typing import TYPE_CHECKING

from ..relics import RelicRarity
from .base import Event, EventOption, register_event

if TYPE_CHECKING:
    from ..run import RunState

_BARGAIN_BIN_COST = 100
_FEATURED_ITEM_COST = 200
_MYSTERY_BOX_COST = 300

# Wongo points earned per purchase (CheckObtainWongoBadge call sites).
_POINTS = {"BARGAIN_BIN": 32, "FEATURED_ITEM": 16, "MYSTERY_BOX": 8}


@register_event
class WelcomeToWongos(Event):
    """Welcome to Wongo's — a discount relic emporium.

    Shared event (ModelDb.AllSharedEvents). Source: WelcomeToWongos.cs
      IsAllowed: act 2 only, and every player has >= 100 gold
      BARGAIN_BIN:   100 gold -> a Common shop-legal grab-bag relic
      FEATURED_ITEM: 200 gold -> the pre-rolled Rare shop-legal relic
      MYSTERY_BOX:   300 gold -> Wongo's Mystery Ticket
      LEAVE:         free, but a random UPGRADED deck card is downgraded
    Each paid option locks when unaffordable.

    Wongo points are cross-run save progression (SaveManager.Progress); the
    sim tracks the points a run earns on `run.wongo_points` but never awards
    the 2000-point badge, which no single run can reach (see
    relics/wongo_customer_appreciation_badge.py).
    """

    id = "welcome_to_wongos"
    name = "Welcome to Wongo's"

    @classmethod
    def is_allowed(cls, run: RunState) -> bool:
        return run.act_index == 1 and run.gold >= _BARGAIN_BIN_COST

    def initial_options(self) -> list[EventOption]:
        # GenerateInitialOptions pre-rolls the featured Rare relic first.
        self._featured = self.run.pull_relic_from_front(
            RelicRarity.RARE, shop_legal=True)
        options = []
        for key, cost, handler in (
            ("BARGAIN_BIN", _BARGAIN_BIN_COST, self._buy_bargain_bin),
            ("FEATURED_ITEM", _FEATURED_ITEM_COST, self._buy_featured_item),
            ("MYSTERY_BOX", _MYSTERY_BOX_COST, self._buy_mystery_box),
        ):
            if self.run.gold >= cost:
                options.append(EventOption(key, handler))
            else:
                options.append(EventOption(f"{key}_LOCKED", None))
        options.append(EventOption("LEAVE", self._leave))
        return options

    def _award_points(self, key: str) -> None:
        run = self.run
        run.wongo_points = getattr(run, "wongo_points", 0) + _POINTS[key]

    def _buy_bargain_bin(self) -> None:
        self.run.lose_gold(_BARGAIN_BIN_COST)
        relic = self.run.pull_relic_from_front(
            RelicRarity.COMMON, shop_legal=True)
        if relic is not None:
            self.run.add_relic(relic)
        self._award_points("BARGAIN_BIN")
        self._finish("AFTER_BUY")

    def _buy_featured_item(self) -> None:
        self.run.lose_gold(_FEATURED_ITEM_COST)
        if self._featured is not None:
            self.run.add_relic(self._featured)
        self._award_points("FEATURED_ITEM")
        self._finish("AFTER_BUY")

    def _buy_mystery_box(self) -> None:
        self.run.lose_gold(_MYSTERY_BOX_COST)
        self.run.add_relic("wongos_mystery_ticket")
        self._award_points("MYSTERY_BOX")
        self._finish("AFTER_BUY")

    def _leave(self) -> None:
        upgraded = [c for c in self.run.deck if c.upgrade_level > 0]
        # `base.Rng.NextItem(upgraded)` — the event's own Rng
        # (WelcomeToWongos.cs:158).
        er = self.event_rng
        if er is not None:
            card = er.next_item(upgraded)
            if card is not None:
                card.downgrade()
        elif upgraded:
            self.rng.choice(upgraded).downgrade()
        self._finish("LEAVE")
