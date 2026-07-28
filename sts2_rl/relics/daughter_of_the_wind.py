from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..cards import Card


@register_relic
class DaughterOfTheWind(Relic):
    """DaughterOfTheWind.cs — whenever you play an Attack, gain 1 Block
    (BlockVar(1, Unpowered): unaffected by Dexterity/Frail). One of the three
    dolls in the Doll Room event."""

    id = "daughter_of_the_wind"
    name = "Daughter of the Wind"
    rarity = RelicRarity.EVENT

    BLOCK = 1

    def on_card_played(self, card: Card,
                       is_auto_play: bool = False) -> None:
        from ..cards import CardType
        from ..cmds import BlockCmd
        from ..valueprops import DamageProps

        if card.card_type != CardType.ATTACK:
            return
        BlockCmd.apply(
            self.hooks, self.combat.player, self.BLOCK,
            props=DamageProps.NON_CARD_UNPOWERED,
        )
