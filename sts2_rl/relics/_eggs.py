"""The three egg relics' shared behaviour (Helpers/Models/EggRelicHelper.cs).

Each egg upgrades one card TYPE. NOTE the mapping differs from sts1: in sts2
Toxic is Skill, Frozen is Power, Molten is Attack (ToxicEgg.cs / FrozenEgg.cs /
MoltenEgg.cs).

Both of the game's hooks matter for parity:

  * ``TryModifyCardRewardOptionsLate`` -> ``EggRelicHelper.UpgradeValidCards``
    upgrades the matching cards in a reward's OFFER, so the card is already
    upgraded when the player takes it (a recording's ``TakeCard`` annotation
    shows the ``+``).
  * ``TryModifyCardBeingAddedToDeck`` (via ``Hook.ModifyCardBeingAddedToDeck``,
    CardPileCmd.cs:501) catches every other route into the deck — shops,
    events, Neow.

The game swaps in an upgraded *clone*; the sim upgrades in place, which is the
same observable deck state.
"""
from __future__ import annotations

from .base import Relic, RelicRarity, is_before_act3_treasure_chest


class EggRelic(Relic):
    """Base for Toxic / Frozen / Molten Egg. Subclasses set ``CARD_TYPE``."""

    rarity = RelicRarity.RARE
    CARD_TYPE = None                 # sts2_rl.cards.CardType
    # MoltenEgg.cs:56 alone refuses a card that is already upgraded (a
    # multi-upgrade Attack stops at +1 from the egg); Toxic/Frozen do not.
    ONLY_UNUPGRADED = False

    @classmethod
    def is_allowed(cls, run) -> bool:
        """All three eggs override IsAllowed identically (ToxicEgg.cs:16-19,
        FrozenEgg.cs:16-19, MoltenEgg.cs:16-19): IsBeforeAct3TreasureChest, so
        they leave the pools from floor 41."""
        return is_before_act3_treasure_chest(run)

    def _applies(self, card) -> bool:
        if card.card_type != self.CARD_TYPE or not card.is_upgradable:
            return False
        return not (self.ONLY_UNUPGRADED and card.upgrade_level >= 1)

    def modify_card_reward_options_late(self, run, cards, options=None):
        # The C# overrides return a bool (`ToxicEgg.cs` and siblings return
        # true after the owner check); the dispatcher hands the true-returners
        # to Hook.AfterModifyingCardRewardOptions.
        for card in cards:
            if self._applies(card):
                card.upgrade()
        return True

    def modify_merchant_card_results(self, run, cards) -> None:
        self.modify_card_reward_options_late(run, cards)

    def modify_card_being_added_to_deck(self, run, card):
        if not self._applies(card):
            return None
        card.upgrade()
        return card
