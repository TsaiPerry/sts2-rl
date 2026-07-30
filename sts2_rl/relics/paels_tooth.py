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
        # PaelsTooth.cs:82 passes `filter: (CardModel c) => c.IsUpgradable`
        # and CardSelectCmd.FromDeckForRemoval ANDs `IsRemovable` onto it, so
        # the offered set is the INTERSECTION. `run.removable_cards()` is the
        # IsRemovable half alone; without the IsUpgradable half a Curse, a
        # Status or an already-smithed card could be stored, and a stored
        # non-upgradable card comes back un-upgraded (the guard below), i.e.
        # the relic silently did nothing for it.
        candidates = [c for c in run.removable_cards() if c.is_upgradable]
        # PaelsTooth.cs:83 ends the selection in
        # `.OrderBy(c => c.Id.Entry, StringComparer.Ordinal)` and stores in that
        # order — and AfterCombatEnd's PlayerRng.Rewards.NextItem indexes into
        # the store, so the order is load-bearing. Ordinal is byte order over
        # the game's UPPERCASE entry, so sort the uppercased id.
        chosen = sorted(run.select_cards("remove", candidates, self.CARDS),
                        key=lambda c: c.id.upper())
        for card in chosen:
            run.remove_cards([card])   # CardPileCmd.RemoveFromDeck (:88)
            self.stored_cards.append(card)

    def after_combat_end(self, run, room_type) -> None:
        # AfterCombatEnd: survivor + cards left → return one, upgraded.
        if run.is_dead or not self.stored_cards:
            return
        # PaelsTooth.cs: PlayerRng.Rewards.NextItem(SerializableCards).
        if run.rng_set is not None:
            card = run.player_rng.rewards.next_item(self.stored_cards)
        else:
            card = run.rng.choice(self.stored_cards)
        self.stored_cards.remove(card)
        if card.is_upgradable:
            card.upgrade()
        run.add_card(card)
