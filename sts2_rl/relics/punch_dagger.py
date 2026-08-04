from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class PunchDagger(Relic):
    """PunchDagger.cs — upon pickup, enchant one chosen deck Attack with
    Momentum 5 (`DynamicVar("Momentum", 5m)`, PunchDagger.cs:15-19).

    `AfterObtained` (:24-33) is one screen and one enchant:
    `CardSelectCmd.FromDeckForEnchantment(owner, canonicalMomentum, 5, prefs)`
    under `CardSelectorPrefs(EnchantSelectionPrompt, 1)` — the one-argument
    count ctor sets MinSelect == MaxSelect == 1 (CardSelectorPrefs.cs:62-66),
    so the pick is mandatory, not skippable — then
    `CardCmd.Enchant(momentum, card, 5)` on the result. There is no shuffle
    here, unlike Royal Stamp's: the screen is built over the deck in deck
    order.

    `CardCmd.Preview(item)` on the tail is presentation only.
    """

    id = "punch_dagger"
    name = "Punch Dagger"
    rarity = RelicRarity.SHOP
    has_upon_pickup_effect = True  # RelicModel.HasUponPickupEffect
    CARDS = 1     # CardSelectorPrefs(prompt, 1)
    MOMENTUM = 5  # DynamicVar("Momentum", 5m)

    def after_obtained(self, run) -> None:
        from ..enchantments import MomentumEnchantment, make_enchantment

        # `FromDeckForEnchantment` builds its list from the cards the
        # enchantment can take (EnchantmentModel.CanEnchant + Momentum's
        # Attack-only CanEnchantCardType).
        candidates = [c for c in run.deck if MomentumEnchantment.can_enchant(c)]
        if not candidates:
            return
        for card in run.select_cards("enchant", candidates, self.CARDS):
            enchantment = make_enchantment("momentum")
            enchantment.amount = self.MOMENTUM
            enchantment.attach(card)
