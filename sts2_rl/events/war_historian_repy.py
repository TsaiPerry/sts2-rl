"""War Historian Repy (Models/Events/WarHistorianRepy.cs).

``IsAllowed => false`` in the source: the room is reached only by carrying a
Lantern Key card into it via ``LanternKeyCard.modify_next_event``
(``sts2_rl/cards/event_cards.py``), which bypasses ``is_allowed`` entirely
(``RunState.enter_point``'s EVENT arm calls ``make_event`` directly on
whatever id a ``modify_next_event`` listener produced — it never re-checks
that event's own gate). Registered here so it occupies its slot in
``ModelDb.AllSharedEvents`` — the game shuffles the full 18-event shared pool
onto every act's queue, so the sim must carry the same 18 ids for the
UpFront event-shuffle draw count/order to match (SP2). See [crystal_sphere],
the other deferred-then-ported shared event.

INITIAL page — two options (WarHistorianRepy.cs:35-42):
  UNLOCK_CAGE -> UnlockCage: grants the HistoryCourse relic
                 (RelicCmd.Obtain<HistoryCourse>, :96-100).
  UNLOCK_CHEST -> UnlockChest: offers 2 PotionReward + 2 RelicReward via one
                 RewardsCmd.OfferCustom screen (:86-94).
Both options first consume a Lantern Key from the deck
(RemoveLanternKeysForInitialChoice, :102-112, PlayerCmd.CompleteQuest +
CardPileCmd.RemoveFromDeck), then check ``ShouldGetSecondReward`` — true iff
the deck STILL holds a Lantern Key after that removal (i.e. the player kept
more than one across separate visits to The Lantern Key event) AND there is
only one player (:18-28). If so, a second page offers the OTHER option
(SecondUnlockCage / SecondUnlockChest, :72-84), consuming every remaining
Lantern Key at once (RemoveLanternKeysForSecondChoice, :124-132) rather than
just one.

``PlayerCmd.CompleteQuest`` (PlayerCmd.cs:291-294) — INVESTIGATED, not
ported: its body is
``questCard.Owner.RunState.CurrentMapPointHistoryEntry?.GetEntry(...)
.CompletedQuests.Add(questCard.Id)``, a list read only by the Run History
screen's quest icon and its hover tip (NMapPointHistoryEntry.cs:186,
NMapPointHistoryHoverTip.cs:304) and the save serializer
(PlayerMapPointHistoryEntry.cs:214,273,311). Grepped the whole decompiled
tree for every other reader of ``CompletedQuests``: none. Presentation/save
bookkeeping with no gameplay-observable effect this event (or any other
CompleteQuest caller, e.g. SpoilsMap.cs:121) could ever surface headlessly —
out of scope per this lane's brief ("do not build a general quest system").
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Event, EventOption, register_event

if TYPE_CHECKING:
    from ..run import RunState


@register_event
class WarHistorianRepy(Event):
    id = "war_historian_repy"
    name = "War Historian Repy"

    @classmethod
    def is_allowed(cls, run: "RunState") -> bool:
        # WarHistorianRepy.IsAllowed => false (:30-33). Reached only via the
        # Lantern Key's modify_next_event redirect, which bypasses this gate.
        return False

    # ── INITIAL page ─────────────────────────────────────────────────────

    def initial_options(self) -> list[EventOption]:
        return [
            EventOption("UNLOCK_CAGE", self._initial_unlock_cage),
            EventOption("UNLOCK_CHEST", self._initial_unlock_chest),
        ]

    def _should_get_second_reward(self) -> bool:
        # ShouldGetSecondReward (:18-28). The sim is single-player only, so
        # `Players.Count <= 1` is always true; only the deck check matters.
        from ..cards.event_cards import LanternKeyCard
        return any(isinstance(c, LanternKeyCard) for c in self.run.deck)

    def _initial_unlock_cage(self) -> None:
        self._remove_lantern_keys_for_initial_choice()
        self._unlock_cage()
        if self._should_get_second_reward():
            self._set_state(
                "UNLOCK_CAGE",
                [EventOption("UNLOCK_CHEST", self._second_unlock_chest)],
            )
        else:
            self._finish("UNLOCK_CAGE")

    def _initial_unlock_chest(self) -> None:
        self._remove_lantern_keys_for_initial_choice()
        self._unlock_chest()
        if self._should_get_second_reward():
            self._set_state(
                "UNLOCK_CHEST",
                [EventOption("UNLOCK_CAGE", self._second_unlock_cage)],
            )
        else:
            self._finish("UNLOCK_CHEST")

    # ── EXTRA page (the second, other-option reward) ────────────────────

    def _second_unlock_cage(self) -> None:
        # Source order (:72-77): SetEventFinished, THEN remove keys, THEN
        # grant the relic -- all still land before `choose()` returns.
        self._finish("EXTRA_UNLOCK_CAGE")
        self._remove_lantern_keys_for_second_choice()
        self._unlock_cage()

    def _second_unlock_chest(self) -> None:
        self._finish("EXTRA_UNLOCK_CHEST")
        self._remove_lantern_keys_for_second_choice()
        self._unlock_chest()

    # ── Payouts ──────────────────────────────────────────────────────────

    def _unlock_chest(self) -> None:
        # UnlockChest (:86-94): 2 PotionReward + 2 RelicReward on one
        # OfferCustom screen. The sim has no combined multi-kind OfferCustom
        # primitive; `offer_potion`/`offer_relic` are the same take-or-skip
        # screen per item (their own docstrings), so each of the 4 rewards is
        # offered separately in source order.
        # Note: all 4 rewards are drawn eagerly in C# before any accept/decline
        # step (`RewardsSet.GenerateWithoutOffering`), matching the potion-
        # potion-relic-relic draw order. This interleaves each draw with its
        # own offer step, but no RNG is consumed between draw and offer, so the
        # net draw sequence remains correct.
        for _ in range(2):
            self.offer_potion(self.run.random_potion())
        for _ in range(2):
            relic = self.run.pull_relic_from_front()
            if relic is not None:
                self.run.offer_relic(relic)

    def _unlock_cage(self) -> None:
        # UnlockCage (:96-100): ExtraFields.FreedRepy's only other reader
        # (grepped the whole tree) is NQueenRepyBgVfx.cs:20, a background
        # VFX toggle -- presentation only, no gameplay effect -- so it is
        # not ported, same reasoning as PlayerCmd.CompleteQuest above.
        self.run.add_relic("history_course")

    # ── Lantern Key consumption ─────────────────────────────────────────

    def _remove_lantern_keys_for_initial_choice(self) -> None:
        # RemoveLanternKeysForInitialChoice (:102-112): `Players.Count > 1`
        # branches to the second-choice (remove-all) helper; the sim is
        # single-player only, so this is always RemoveFirstLanternKey.
        self._remove_first_lantern_key()

    def _remove_first_lantern_key(self) -> None:
        # RemoveFirstLanternKey (:114-122). PlayerCmd.CompleteQuest is
        # deliberately not ported -- see module docstring.
        from ..cards.event_cards import LanternKeyCard
        for card in self.run.deck:
            if isinstance(card, LanternKeyCard):
                self.run.remove_cards([card])
                return

    def _remove_lantern_keys_for_second_choice(self) -> None:
        # RemoveLanternKeysForSecondChoice (:124-132): every Lantern Key at
        # once, not just one.
        from ..cards.event_cards import LanternKeyCard
        keys = [c for c in self.run.deck if isinstance(c, LanternKeyCard)]
        if keys:
            self.run.remove_cards(keys)
