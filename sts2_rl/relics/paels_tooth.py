from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class PaelsTooth(Relic):
    """PaelsTooth.cs — upon pickup, choose 5 removable deck cards to store in
    the tooth (removed from the deck). After each combat you survive, one
    random stored card returns to the deck UPGRADED. Only offered by Pael when
    the deck has at least 5 removable cards."""

    id = "paels_tooth"
    name = "Pael's Tooth"
    rarity = RelicRarity.ANCIENT
    has_upon_pickup_effect = True  # RelicModel.HasUponPickupEffect

    CARDS = 5
    # Pael.cs GenerateInitialOptions' offer gate.
    MIN_REMOVABLE = 5

    def __init__(self) -> None:
        super().__init__()
        self.stored_cards: list = []

    def after_obtained(self, run) -> None:
        candidates = run.removable_cards()
        for card in run.select_cards("remove", candidates, self.CARDS):
            run.deck.remove(card)
            self.stored_cards.append(card)

    def after_combat_end(self, run, room_type) -> None:
        # AfterCombatEnd: survivor + cards left → return one, upgraded.
        if run.is_dead or not self.stored_cards:
            return
        card = run.rng.choice(self.stored_cards)
        self.stored_cards.remove(card)
        if card.is_upgradable:
            card.upgrade()
        run.add_card(card)
