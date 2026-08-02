from __future__ import annotations

from .base import Relic, RelicRarity, register_relic

@register_relic
class GnarledHammer(Relic):
    """GnarledHammer.cs — upon pickup, enchant up to 3 deck cards with Sharp 3."""

    id = "gnarled_hammer"
    name = "Gnarled Hammer"
    rarity = RelicRarity.SHOP
    has_upon_pickup_effect = True  # RelicModel.HasUponPickupEffect

    CARDS = 3          # CanonicalVars: CardsVar(3)
    SHARP_AMOUNT = 3   # CanonicalVars: DynamicVar("SharpAmount", 3)

    def after_obtained(self, run) -> None:
        """GnarledHammer.cs:30-34 — `new CardSelectorPrefs(EnchantSelectionPrompt,
        0, Cards.IntValue) { Cancelable = false, RequireManualConfirmation =
        true }`, the CHARACTER-FOR-CHARACTER Kifuda shape (MinSelect 0,
        MaxSelect 3): the player may confirm having enchanted 0, 1, 2 or 3
        eligible cards. purpose="enchant_optional" (relics/kifuda.py's own
        purpose — the identical prefs shape, driver.SKIPPABLE_PURPOSES) plus
        min_select=0 is what lets `RunDriver._card_selector` offer a "stop
        here" action instead of the `count >= len(remaining)` fast path
        force-filling all 3 (tier-2 round-13/14 gap
        relic/gnarled_hammer/g3 -- see this round's report). Six other
        "enchant"-purpose relics/events keep the plain "enchant" purpose:
        their own CardSelectorPrefs constructors are the exact-count overload
        (MinSelect == MaxSelect), a genuinely different shape.
        `CardSelectCmd.FromDeckForEnchantment` filters by the enchantment's
        own CanEnchant, which for Sharp is Attacks only."""
        from ..enchantments import SharpEnchantment, make_enchantment

        candidates = [c for c in run.deck if SharpEnchantment.can_enchant(c)]
        for card in run.select_cards(
                "enchant_optional", candidates, self.CARDS, min_select=0):
            enchantment = make_enchantment("sharp")
            enchantment.amount = self.SHARP_AMOUNT
            enchantment.attach(card)
