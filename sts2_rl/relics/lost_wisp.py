from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic
from ..cards import CardType

if TYPE_CHECKING:
    from ..cards import Card


@register_relic
class LostWisp(Relic):
    """Whenever you play a Power card, deal 8 damage to all enemies.

    Source: LostWisp.cs — AfterCardPlayed: if the played card is a Power, deal
    Damage 8 (Unpowered, blockable) to all HittableEnemies. Granted by the
    Lost Wisp event (Claim)."""

    id = "lost_wisp"
    name = "Lost Wisp"
    rarity = RelicRarity.EVENT

    DAMAGE = 8

    def on_card_played(self, card: Card) -> None:
        if card.card_type != CardType.POWER or self.combat is None or self.combat.is_over:
            return
        from ..cmds import DamageCmd
        from ..valueprops import DamageProps
        for enemy in self.living_enemies():
            DamageCmd.deal(
                self.hooks, enemy, self.DAMAGE,
                dealer=self.player, props=DamageProps.NON_CARD_UNPOWERED,
            )
        self._check_win()
