from __future__ import annotations

from typing import TYPE_CHECKING

from ..enchantments import SteadyEnchantment, make_enchantment
from .base import Event, EventOption, register_event

if TYPE_CHECKING:
    from ..run import RunState

_MAX_HP = 6                 # MaxHpVar(6)
_TENTACLE_QUILL_GOLD = 55   # GoldVar(55)
_PRICKLY_SPONGE_GOLD = 99   # GoldVar("PricklySpongeGold", 99)
_PRICKLY_SPONGE_CARDS = 2   # CardsVar(2)


@register_event
class WaterloggedScriptorium(Event):
    """Waterlogged Scriptorium — gain Max HP for free, or pay to enchant cards
    with Steady (Retain).

    Source: WaterloggedScriptorium.cs
      IsAllowed: gold >= 55
      BLOODY_INK:    gain 6 Max HP
      TENTACLE_QUILL: pay 55 gold, enchant 1 chosen card with Steady
                      (locked if gold < 55)
      PRICKLY_SPONGE: pay 99 gold, enchant 2 chosen cards with Steady
                      (locked if gold < 99)
    """

    id = "waterlogged_scriptorium"
    name = "Waterlogged Scriptorium"

    @classmethod
    def is_allowed(cls, run: RunState) -> bool:
        return run.gold >= _TENTACLE_QUILL_GOLD

    def initial_options(self) -> list[EventOption]:
        options = [EventOption("BLOODY_INK", self._bloody_ink)]
        if self.run.gold >= _TENTACLE_QUILL_GOLD:
            options.append(EventOption("TENTACLE_QUILL", self._tentacle_quill))
        else:
            options.append(EventOption("TENTACLE_QUILL_LOCKED", None))
        if self.run.gold >= _PRICKLY_SPONGE_GOLD:
            options.append(EventOption("PRICKLY_SPONGE", self._prickly_sponge))
        else:
            options.append(EventOption("PRICKLY_SPONGE_LOCKED", None))
        return options

    def _enchant(self, count: int) -> None:
        candidates = [c for c in self.run.deck if SteadyEnchantment.can_enchant(c)]
        for card in self.run.select_cards("enchant", candidates, count):
            make_enchantment("steady").attach(card)

    def _bloody_ink(self) -> None:
        self.run.gain_max_hp(_MAX_HP)
        self._finish("BLOODY_INK")

    def _tentacle_quill(self) -> None:
        self.run.lose_gold(_TENTACLE_QUILL_GOLD)
        self._enchant(1)
        self._finish("TENTACLE_QUILL")

    def _prickly_sponge(self) -> None:
        self.run.lose_gold(_PRICKLY_SPONGE_GOLD)
        self._enchant(_PRICKLY_SPONGE_CARDS)
        self._finish("PRICKLY_SPONGE")
