"""CombatHistory — the combat event log, mirroring CombatManager.History.

Records typed entries (card plays, card exhausts, damage received) tagged with
the turn they happened on. Registered as the first hook listener so entries
already exist when powers and cards react to the same event, and queried by
cards/powers for "did X happen this turn / this combat" conditionals (Evil Eye,
Spite, Tear Asunder, Stomp, ...).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Iterator, TypeVar

from .hooks import CAT_HISTORY
from .valueprops import ValueProp

if TYPE_CHECKING:
    from .cards import Card
    from .combat import CombatState
    from .creatures import Creature


@dataclass
class HistoryEntry:
    """Base class for combat-history entries (mirrors CombatHistory entries).

    turn is `CombatState.RoundNumber`, which is what every C# entry is
    stamped with (CombatHistory.cs:40-120). A player turn and the enemy turns
    that follow it share it, so events from the previous enemy phase do not
    count as "this turn" on the player's next turn -- and so does an EXTRA
    player turn, because SwitchSides' extra-turn branch bumps TurnNumber
    without bumping RoundNumber (CombatManager.cs:1406-1418).
    """

    turn: int


@dataclass
class CardPlayStartedEntry(HistoryEntry):
    """`CardPlayStartedEntry` — `History.CardPlaysStarted` (CombatHistory.cs:26).

    A SEPARATE list from CardPlaysFinished, and the two are pushed at different
    points inside the replay loop: started at CardModel.cs:1930, immediately
    after Hook.BeforeCardPlayed and BEFORE `await OnPlay` (:1931); finished at
    :1956, after the enchantment and affliction have resolved. The sim used to
    have only the finished row, so a card auto-played from inside another card's
    OnPlay could not see the outer play — which is exactly what Normality
    (Normality.cs:33) and NostalgiaPower (NostalgiaPower.cs:31-42) read.

    Nine C# sites read CardPlaysStarted and eleven read CardPlaysFinished, so
    the distinction is load-bearing well beyond those two; the rest of the sim's
    readers stay on `CardPlayedEntry` until their own entries are worked.
    """

    card: Card
    is_auto_play: bool = False


@dataclass
class CardPlayedEntry(HistoryEntry):
    """`CardPlayFinishedEntry` — `History.CardPlaysFinished` (CombatHistory.cs:28),
    pushed at CardModel.cs:1956. One entry per replay ITERATION (the push is
    inside the loop), so a Hidden-Gem'd card records two."""

    card: Card
    # CardPlay.IsAutoPlay. Pael's Eye filters on it (PaelsEye.cs:155's
    # `&& !e.CardPlay.IsAutoPlay`) and Brilliant Scarf early-returns on it
    # (BrilliantScarf.cs:84-87), while Rainbow Ring and Razor Tooth
    # deliberately DO count auto-plays.
    is_auto_play: bool = False


@dataclass
class CardExhaustedEntry(HistoryEntry):
    """A card was moved to the exhaust pile (mirrors CardExhaustedEntry)."""

    card: Card


@dataclass
class DamageReceivedEntry(HistoryEntry):
    """A creature went through the damage pipeline (mirrors
    DamageReceivedEntry). amount is the HP actually lost (UnblockedDamage);
    fully blocked hits record amount 0."""

    target: Creature
    amount: int
    dealer: Creature | None
    card: Card | None


_E = TypeVar("_E", bound=HistoryEntry)


class CombatHistory:
    """Combat event log, mirroring the game's CombatManager.History.

    Registered on the HookSystem before any power or card listener, so
    entries are already recorded when other listeners react to the same
    event. Cards and powers query it for "did X happen this turn / this
    combat" conditionals (Evil Eye, Spite, Tear Asunder, Stomp, ...).
    """

    # Sim-only listener with no C# counterpart (hook_dispatch note N3): it
    # sits ahead of the creature walk so an entry already exists when
    # anything reacts to the event that produced it.
    hook_category = CAT_HISTORY

    def __init__(self, combat: CombatState) -> None:
        self.combat = combat
        self.entries: list[HistoryEntry] = []

    # ── Recorders (hook listeners) ───────────────────────────────────────

    def card_play_started(self, card: Card, is_auto_play: bool = False) -> None:
        """`History.CardPlayStarted` (CombatHistory.cs:38), pushed from
        CardModel.cs:1930. NOT a hook — the game calls it directly, between
        Hook.BeforeCardPlayed and OnPlay, which is why an inner auto-play sees
        the outer play. Combat._resolve_card_play calls it at that position."""
        self.entries.append(
            CardPlayStartedEntry(self.combat.round_number, card, is_auto_play))

    def on_card_played(self, card: Card, is_auto_play: bool = False) -> None:
        self.entries.append(
            CardPlayedEntry(self.combat.round_number, card, is_auto_play))

    def on_card_exhausted(self, card: Card,
                          caused_by_ethereal: bool = False) -> None:
        self.entries.append(CardExhaustedEntry(self.combat.round_number, card))

    def on_damage_received(
        self,
        target: Creature,
        amount: int,
        dealer: Creature | None,
        card: Card | None,
        props: ValueProp = ValueProp.NONE,
    ) -> None:
        self.entries.append(
            DamageReceivedEntry(self.combat.round_number, target, amount, dealer, card)
        )

    # ── Queries ──────────────────────────────────────────────────────────

    def of_type(self, entry_type: type[_E], this_turn: bool = False) -> Iterator[_E]:
        """Entries of the given type, optionally only from the current turn."""
        for entry in self.entries:
            if isinstance(entry, entry_type):
                if not this_turn or entry.turn == self.combat.round_number:
                    yield entry

    def card_exhausted_this_turn(self) -> bool:
        """Any card exhausted this turn (Evil Eye / Forgotten Ritual)."""
        return any(True for _ in self.of_type(CardExhaustedEntry, this_turn=True))

    def lost_hp_this_turn(self, creature: Creature) -> bool:
        """Did the creature lose HP (unblocked damage > 0) this turn (Spite)."""
        return any(
            e.target is creature and e.amount > 0
            for e in self.of_type(DamageReceivedEntry, this_turn=True)
        )

    def times_damaged(self, creature: Creature) -> int:
        """How many times the creature lost HP this combat (Tear Asunder)."""
        return sum(
            1
            for e in self.of_type(DamageReceivedEntry)
            if e.target is creature and e.amount > 0
        )

    def attack_plays_this_turn(self) -> int:
        """Attack card plays this turn (Stomp / Juggling seed)."""
        from .cards import CardType
        return sum(
            1
            for e in self.of_type(CardPlayedEntry, this_turn=True)
            if e.card.card_type == CardType.ATTACK
        )
