from __future__ import annotations

from typing import TYPE_CHECKING

from ..enchantments import VigorousEnchantment, make_enchantment
from .base import Event, EventOption, register_event

if TYPE_CHECKING:
    from ..run import RunState

_MAX_HP_GAIN = 10      # DrinkMaxHpGain
_PUSH_HP_LOSS = 6      # PushHpLoss
_VIGOROUS_AMOUNT = 8   # PushVigorousAmount


@register_event
class StoneOfAllTime(Event):
    """Stone of All Time — drink a potion to lift it, or push it for Vigor.

    Shared event (ModelDb.AllSharedEvents). Source: StoneOfAllTime.cs
      IsAllowed: act 2 only, and every player holds at least one potion
      LIFT: discard the shown random potion, gain 10 Max HP
      PUSH: take 6 damage, enchant a chosen card with Vigorous 8
    Each option locks when its precondition fails (no potion / no card the
    Vigorous enchantment can take).

    Both branches burn one Rng.NextInt(100) after resolving (the source rolls
    an unused value for its dialogue variant); the sim keeps the draw so its
    single RNG stream stays aligned with the source's call order.

    The source's CanRemovePotions=false guard is UI-only and not modeled.
    """

    id = "stone_of_all_time"
    name = "Stone of All Time"

    @classmethod
    def is_allowed(cls, run: RunState) -> bool:
        return run.act_index == 1 and len(run.potions) > 0

    def initial_options(self) -> list[EventOption]:
        # GenerateInitialOptions rolls the potion first, then checks the deck.
        potion = self.rng.choice(self.run.potions) if self.run.potions else None
        lift = (
            EventOption("LIFT", lambda p=potion: self._lift(p))
            if potion is not None
            else EventOption("LIFT_LOCKED", None)
        )
        push = (
            EventOption("PUSH", self._push)
            if self._vigorous_candidates()
            else EventOption("PUSH_LOCKED", None)
        )
        return [lift, push]

    def _vigorous_candidates(self) -> list:
        return [c for c in self.run.deck if VigorousEnchantment.can_enchant(c)]

    def _lift(self, potion) -> None:
        self.run.potions.remove(potion)
        self.run.gain_max_hp(_MAX_HP_GAIN)
        self.rng.randrange(100)          # Rng.NextInt(100), value unused
        self._finish("LIFT")

    def _push(self) -> None:
        self.run.lose_hp(_PUSH_HP_LOSS)
        for card in self.run.select_cards("enchant", self._vigorous_candidates(), 1):
            enchantment = make_enchantment("vigorous")
            enchantment.amount = _VIGOROUS_AMOUNT
            enchantment.attach(card)
        self.rng.randrange(100)          # Rng.NextInt(100), value unused
        self._finish("PUSH")
