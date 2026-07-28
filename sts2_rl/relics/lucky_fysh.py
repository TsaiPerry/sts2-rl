from __future__ import annotations

from .base import Relic, RelicRarity, is_before_act3_treasure_chest, register_relic


@register_relic
class LuckyFysh(Relic):
    """LuckyFysh.cs — whenever a card enters your deck, gain 15 gold
    (AfterCardChangedPiles filtered to PileType.Deck -> GoldVar(15))."""

    id = "lucky_fysh"
    name = "Lucky Fysh"
    rarity = RelicRarity.UNCOMMON
    is_allowed_in_shops = False  # LuckyFysh.IsAllowedInShops

    GOLD = 15

    def after_card_added_to_deck(self, run, card) -> None:
        run.gain_gold(self.GOLD)

    @classmethod
    def is_allowed(cls, run) -> bool:
        """LuckyFysh.cs:19-22: IsBeforeAct3TreasureChest — the relic leaves the
        pools from floor 41."""
        return is_before_act3_treasure_chest(run)
