from __future__ import annotations

from ..enchantments import SownEnchantment
from .base import Event, EventOption, register_event

_HEAL = 9  # HealVar(9)


@register_event
class SapphireSeed(Event):
    """Sapphire Seed — eat it to heal and upgrade, or plant it in a card.

    Source: SapphireSeed.cs
      EAT:   heal 9 HP, then choose 1 card to upgrade
      PLANT: choose 1 eligible card; it gains the Sown enchantment
             (first play each combat grants 1 energy)
    """

    id = "sapphire_seed"
    name = "Sapphire Seed"

    def initial_options(self) -> list[EventOption]:
        return [
            EventOption("EAT", self._eat),
            EventOption("PLANT", self._plant),
        ]

    def _eat(self) -> None:
        self.run.heal(_HEAL)
        chosen = self.run.select_cards("upgrade", self.run.upgradable_cards(), 1)
        if chosen:
            chosen[0].upgrade()
        self._finish("EAT")

    def _plant(self) -> None:
        candidates = [c for c in self.run.deck if SownEnchantment.can_enchant(c)]
        chosen = self.run.select_cards("enchant", candidates, 1)
        if chosen:
            SownEnchantment(amount=1).attach(chosen[0])
        self._finish("PLANT")
