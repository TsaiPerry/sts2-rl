from __future__ import annotations

from .base import Relic, RelicRarity, register_relic

@register_relic
class Kifuda(Relic):
    """Kifuda.cs — upon pickup, enchant up to 3 deck cards with Adroit 3."""

    id = "kifuda"
    name = "Kifuda"
    rarity = RelicRarity.SHOP
    has_upon_pickup_effect = True  # RelicModel.HasUponPickupEffect

    CARDS = 3           # CanonicalVars: CardsVar(3)
    ADROIT_AMOUNT = 3   # Kifuda.cs:36 -- a literal 3m, not a var

    def after_obtained(self, run) -> None:
        """Kifuda.cs:24-37 — the same shape as Gnarled Hammer with a different
        enchantment. Adroit has no CanEnchantCardType override, so the base
        CanEnchant (no Status/Curse/Quest, playable, not already enchanted) is
        the whole filter.

        Kifuda.cs:26-29: `new CardSelectorPrefs(EnchantSelectionPrompt, 0,
        Cards.IntValue) { Cancelable = false, RequireManualConfirmation =
        true }` — MinSelect 0, MaxSelect 3 (mechanism `relic/_auto_keep`,
        `relic/kifuda/g2`). The player may confirm having enchanted 0, 1, 2
        or 3 eligible cards; they may not back out of the screen entirely
        (there is simply no such action in the sim's SELECT_CARDS decision).
        purpose="enchant_optional" (not the plain "enchant" every other
        enchant relic/event uses) is what lets `RunDriver._card_selector`
        offer a "stop here" action once at least 0 have been picked —
        driver.SKIPPABLE_PURPOSES, and `min_select=0` is what lets a
        SELECTORLESS `RunState` (no driver attached) return fewer than 3
        instead of always sampling exactly 3.

        CAVEAT (round-13 review): "confirm 0, 1, 2 or 3" above is the PREFS
        range (MinSelect/MaxSelect), the level `ICardSelector.GetSelectedCards`
        and this driver operate at — it is NOT a literal description of the
        shipped single-player screen. `NDeckEnchantSelectScreen.ConfirmSelection`
        (`:258-264`) refuses to finalize an empty selection
        (`if (_selectedCards.Count != 0)`), and `CloseSelection` (`:186-190`)
        — the only path that DOES resolve with zero cards — is gated behind
        `Cancelable` (false here), so it is unreachable too. The shipped UI's
        actual reachable floor is 1; the sim's 0 is a deliberate, recorded
        modelling choice at the automated-selector altitude
        (`CardSelectCmd.cs:582`), not a UI bug port."""
        from ..enchantments import AdroitEnchantment, make_enchantment

        candidates = [c for c in run.deck if AdroitEnchantment.can_enchant(c)]
        for card in run.select_cards(
                "enchant_optional", candidates, self.CARDS, min_select=0):
            enchantment = make_enchantment("adroit")
            enchantment.amount = self.ADROIT_AMOUNT
            enchantment.attach(card)
