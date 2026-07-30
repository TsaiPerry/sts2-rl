from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class FresnelLens(Relic):
    """FresnelLens.cs — every Nimble-eligible card the owner is offered or adds
    to the deck is enchanted with Nimble 2 (`NimbleAmount`, :19).

    All three C# hooks are ported: `TryModifyCardRewardOptionsLate` (:23-31 —
    enchant every eligible option in the LATE pass, so a card another relic
    ADDED in the plain pass is caught too), `ModifyMerchantCardCreationResults`
    (:32-38) and `TryModifyCardBeingAddedToDeck` (:40-53). All three funnel
    through `EnchantValidCards` / `EnchantCard` (:55-74), so the eligibility
    test is one `Nimble.CanEnchant` in every case.

    C# enchants a CLONE (`RunState.CloneCard`, :71) and the sim enchants in
    place; that is relic/glitter's N1, recorded once for the whole family, and
    it is inert for a freshly created reward option with no per-instance state
    to lose.
    """

    id = "fresnel_lens"
    name = "Fresnel Lens"
    rarity = RelicRarity.EVENT
    NIMBLE_AMOUNT = 2              # CanonicalVars "NimbleAmount" 2m

    def _enchant(self, card):
        from ..enchantments import make_enchantment

        enchantment = make_enchantment("nimble")
        enchantment.amount = self.NIMBLE_AMOUNT
        enchantment.attach(card)
        return card

    def modify_card_reward_options_late(self, run, cards, options=None):
        from ..enchantments import NimbleEnchantment

        for card in cards:
            if NimbleEnchantment.can_enchant(card):
                self._enchant(card)
        return True                     # FresnelLens.cs:29

    def modify_merchant_card_results(self, run, cards) -> None:
        # FresnelLens.cs:32-38 — the same EnchantValidCards over the shop's
        # stock, so the shelf shows Nimble cards and the price is computed
        # from the enchanted card.
        self.modify_card_reward_options_late(run, cards)

    def modify_card_being_added_to_deck(self, run, card):
        from ..enchantments import NimbleEnchantment

        if not NimbleEnchantment.can_enchant(card):
            return None
        return self._enchant(card)
