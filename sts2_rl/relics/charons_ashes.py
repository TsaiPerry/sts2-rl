from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic
from ..valueprops import DamageProps

if TYPE_CHECKING:
    from ..cards import Card

@register_relic
class CharonsAshes(Relic):
    """Whenever you exhaust a card, deal 3 damage to ALL enemies."""

    id = "charons_ashes"
    name = "Charon's Ashes"
    rarity = RelicRarity.RARE

    DAMAGE = 3

    def on_card_exhausted(self, card: Card) -> None:
        from ..cmds import DamageCmd
        for enemy in self.living_enemies():
            DamageCmd.deal(
                self.hooks, enemy, self.DAMAGE,
                dealer=self.player, props=DamageProps.NON_CARD_UNPOWERED,
            )
        self._check_win()
