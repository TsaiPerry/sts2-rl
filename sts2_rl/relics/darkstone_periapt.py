from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class DarkstonePeriapt(Relic):
    """Whenever you add a Curse to your deck, gain 6 Max HP.

    Source: DarkstonePeriapt.cs — AfterCardChangedPiles: a Curse entering the
    deck pile grants MaxHpVar(6) via CreatureCmd.GainMaxHp (raise max HP,
    then heal the same amount). Granted by the Trash Heap event."""

    id = "darkstone_periapt"
    name = "Darkstone Periapt"
    rarity = RelicRarity.EVENT

    MAX_HP = 6  # MaxHpVar(6)

    def after_card_added_to_deck(self, run, card) -> None:
        from ..cards import CardType
        if card.card_type == CardType.CURSE:
            run.gain_max_hp(self.MAX_HP)
