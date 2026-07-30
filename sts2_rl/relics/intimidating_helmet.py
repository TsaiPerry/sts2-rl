from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic
from ..valueprops import ValueProp

if TYPE_CHECKING:
    from ..cards import Card

@register_relic
class IntimidatingHelmet(Relic):
    """Whenever you play a card by spending 2 or more energy, gain 4 Block."""

    id = "intimidating_helmet"
    name = "Intimidating Helmet"
    rarity = RelicRarity.RARE

    ENERGY = 2      # EnergyVar(2), IntimidatingHelmet.cs:18
    BLOCK = 4       # BlockVar(4m, ValueProp.Unpowered), :17

    def before_card_played(self, card: Card, target=None) -> None:
        """IntimidatingHelmet.cs:23-31 is `BeforeCardPlayed`, and it reads
        `cardPlay.Resources.EnergyValue` — the card's COST, not the energy spent.

        Two defects in one move. (a) The port listened on `on_energy_spent`,
        which carries the amount SPENT: an auto-played 2-cost card spends 0, so
        the relic could not fire where the game fires (ResourceInfo.cs:9-16 says
        so in as many words, and CardCmd.cs:123-128 is the site). (b)
        `on_energy_spent` is dispatched ONCE per logical play, before the
        play-count loop, while Hook.BeforeCardPlayed is inside it
        (CardModel.cs:1929) — so a Replayed 2-cost card granted the block once
        where the game grants it per iteration. Moving to the hook C# actually
        declares fixes both.
        """
        if card.energy_value >= self.ENERGY:
            from ..cmds import BlockCmd
            BlockCmd.apply(self.hooks, self.player, self.BLOCK,
                           props=ValueProp.UNPOWERED)
