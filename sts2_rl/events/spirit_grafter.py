from __future__ import annotations

from ..cards import make_card
from .base import Event, EventOption, register_event

_REJECTION_HP_LOSS = 10   # HpLossVar("RejectionHpLoss", 10)
_LET_IT_IN_HEAL = 25      # HealVar("LetItInHealAmount", 25)


@register_event
class SpiritGrafter(Event):
    """Spirit Grafter — let it in (heal + a Metamorphosis card), or reject it
    (upgrade a card but take damage).

    Source: SpiritGrafter.cs
      LET_IT_IN: heal 25 and add a Metamorphosis card
      REJECTION: upgrade 1 chosen card, then take 10 damage
    """

    id = "spirit_grafter"
    name = "Spirit Grafter"

    def initial_options(self) -> list[EventOption]:
        return [
            EventOption("LET_IT_IN", self._let_it_in),
            EventOption("REJECTION", self._rejection),
        ]

    def _let_it_in(self) -> None:
        self.run.heal(_LET_IT_IN_HEAL)
        self.run.add_card(make_card("metamorphosis"))
        self._finish("LET_IT_IN")

    def _rejection(self) -> None:
        for card in self.run.select_cards("upgrade", self.run.upgradable_cards(), 1):
            card.upgrade()
        self.run.lose_hp(_REJECTION_HP_LOSS)
        self._finish("REJECTION")
