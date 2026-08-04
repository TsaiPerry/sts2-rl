"""SP3 Task 7: ReplayCombatDriver — replay a recording's combat commands
against a live, parity-mode `CombatState`, asserting each command's pre-state
annotation (Hand / Enemies) against the recording before dispatching it.

Card resolution uses the `CombatCardDb` (Task 5) oracle: `PlayCard`'s first
argument is the per-combat card id (`NetCombatCardDb`), not a hand index —
`card_db.get(id)` returns the card, whose hand index is then looked up live.
The db is the COMBAT's own (`CombatState.card_db`, started at the game's
`SetUpCombat` instant and stamping each later card as it is added), not one the
driver builds after the fact; passing a different db here would reintroduce the
post-draw reconstruction this driver used to be wrong about.
Enemy targeting is the recording's 1-based, stable absolute slot into
`combat.enemies` (dead enemies stay in place as `is_gone`), so `target_idx =
tid - 1` needs no re-indexing over living enemies.
"""
from __future__ import annotations

from .comparators import Divergence

_COMBAT_CMDS = {"PlayCard", "EndTurn", "UsePotion"}
# Commands the driver consumes while a combat is live but which never *start* a
# fight (so they stay out of _COMBAT_CMDS, which the runner uses to detect an
# annotated fight). SelectCardFromScreen resolves a mid-combat choose-a-card
# screen (Skill Potion, Discovery, …). SelectGridCard is NOT a top-level driver
# command: it resolves a card-selection screen a card effect opens *during* a
# PlayCard (Headbutt's discard->draw pick, Armaments, …), so it is consumed by
# the driver's card_selector mid-dispatch, not iterated here.
_DRIVER_CMDS = _COMBAT_CMDS | {"SelectCardFromScreen"}
# Every command that belongs to a live fight (used to drop a stopped fight's
# unreplayed tail — including any pending in-combat selection screens — so the
# cursor realigns on the post-combat reward/room boundary).
_COMBAT_TAIL_CMDS = _DRIVER_CMDS | {"SelectGridCard", "SelectHandCards"}


def card_display_name(card) -> str:
    """Recording spelling — the game's `CardModel.Title`.

    Normally that is the base name plus one '+' per upgrade level
    (Card.__repr__: f"{name}{'+'*upgrade_level}"): "Strike", "Defend+",
    "Bash+", "Slimed".

    `Wither` overrides `Title` (Wither.cs:16-27) to append `+{FakeUpgradeLevel}`
    instead — a SEPARATE counter from `CurrentUpgradeLevel`, which for Wither
    can never be non-zero (`MaxUpgradeLevel => 0`, Wither.cs:41) because the
    card grows through `FakeUpgrade()` (:60-64, +3 damage a step) rather than
    the ordinary upgrade path. Reading `upgrade_level` alone therefore CANNOT
    reproduce the recording's "Wither+1", and reported it as a hand divergence
    on every turn one was held: 14 of them across 89U21BV1TZ's act-2 Aeonglass
    fights, which were the seed's last per-command mismatches. The engine was
    right the whole time — the sim's Withers carry the matching
    `fake_upgrade_level`, which is why the run's HP, counters, deck, relics and
    gold all matched exactly while these 14 "divergences" stood. Teaching the
    comparator the field takes them to zero and changes nothing else.
    """
    fake = getattr(card, "fake_upgrade_level", 0)
    if fake:
        return f"{card.name}+{fake}"
    suffix = "+" * card.upgrade_level if card.upgrade_level > 0 else ""
    return f"{card.name}{suffix}"


def enemy_display_name(monster) -> str:
    """The monster's game display name (Monster.name class attr, Part C).

    A monster whose roster entry hasn't been given a `name` yet (un-ported for
    parity, a Task 9 item) falls back to its class name so the driver reports an
    Enemies divergence instead of crashing — a conformance driver reports, it
    does not raise."""
    return getattr(monster, "name", None) or type(monster).__name__


class ReplayCombatDriver:
    """Drives a live `CombatState` through a recording's combat commands,
    reading strictly in order from a `_CommandCursor` positioned at the
    recording's current spot. Stops (without consuming) at the first
    non-combat command — combat ends at the recording's next `ClaimReward` /
    `MoveToMapCoord`, which belongs to the caller (map-walk driver)."""

    def __init__(self, combat, cursor, card_db) -> None:
        self.combat = combat
        self.cursor = cursor
        self.db = card_db
        self.divergences: list[Divergence] = []
        # Recorded CombatCardDb ids that never resolved to a live card (the
        # card was mid-resolution or the pile ordering diverged). Task 8's
        # runner surfaces this so `unresolved_play_card_ids == []` is a
        # first-class acceptance signal.
        self.unresolved_play_card_ids: list[int] = []
        # Set by _dispatch when a recorded card fails to resolve (stops the fight).
        self._stopped = False
        # Route in-combat player card-selection screens (Headbutt's discard->draw
        # pick, Armaments, …) to the recording's SelectGridCard command(s). The
        # sim resolves these synchronously inside play_card, so the selector reads
        # the choice straight off the cursor, which play() has already advanced
        # past the current PlayCard.
        combat.card_selector = self._grid_selector

    def _grid_selector(self, purpose, candidates, count):
        """Resolve a synchronous in-combat card selection from the recording.

        When the choice isn't a genuine over-count one (``cards.Count <=
        MinSelect``), the game auto-resolves — takes all candidates with no
        screen (CardSelectCmd.cs:287/343), so the recording holds no selection
        command. Otherwise the recording captures the picks in one of two forms:

          - FromCombatPile (Headbutt discard→draw, random autoplay, …) → one
            ``SelectGridCard N`` command per pick, N indexing the candidate grid.
          - FromHand (Armaments upgrade, Burning Pact discard, …) → a single
            ``SelectHandCards i j …`` command whose indices are positions in the
            FULL hand (RunReplays SelectHandCardsCommand indexes
            ``PlayerCombatState.Hand.Cards[idx]``), which we map to their
            filtered candidates.

        A recorded ``SelectHandCards`` sitting right here is checked FIRST,
        before the auto-resolve shortcut: a screen with MinSelect 0 (Gambler's
        Brew — "discard any number") is always shown even though every
        candidate is selectable, so `candidates <= count` does not imply the
        game auto-resolved. When the game *did* auto-resolve it emitted no
        command at all, so this peek cannot steal a later screen's pick."""
        cmd = self.cursor.peek()
        # `CardSelectCmd.FromChooseACardScreen` — the OTHER screen kind, and
        # the recording writes it as `SelectCardFromScreen N` (an index into
        # the offered cards), not as a grid pick. The sim resolves most of
        # those asynchronously through `_pending_screen_cards`, but the ones
        # the game blocks on mid-move (Knowledge Demon's Curse of Knowledge,
        # KnowledgeDemon.cs:183) come through here instead, and used to fall
        # off the end of this function as "no choice made" — the recorded
        # command was then dispatched into an empty `_pending_screen_cards`
        # and did nothing at all. Taking it here is safe precisely BECAUSE the
        # deferred kind parks its cards first: if a screen is already pending,
        # the command belongs to that one.
        if (cmd is not None and cmd.name == "SelectCardFromScreen"
                and self.combat._pending_screen_cards is None):
            self.cursor.advance()
            arg = cmd.args[0] if cmd.args else "skip"
            if not arg.lstrip("-").isdigit():
                return []                      # a `skip` on a canSkip screen
            idx = int(arg)
            return [candidates[idx]] if 0 <= idx < len(candidates) else []
        if cmd is None or cmd.name != "SelectHandCards":
            if len(candidates) <= count:
                return list(candidates)
        if cmd is not None and cmd.name == "SelectHandCards":
            # One command carries every picked hand index; map each into the
            # full hand, then keep those that are selectable (in `candidates`).
            self.cursor.advance()
            hand = self.combat.player.hand
            chosen = []
            for arg in cmd.args:
                if arg.lstrip("-").isdigit():
                    idx = int(arg)
                    if 0 <= idx < len(hand) and hand[idx] in candidates:
                        chosen.append(hand[idx])
            return chosen[:count]
        # One `SelectGridCard` command == one screen, carrying EVERY picked
        # index (RunReplays DeckCardSelectRecordPatch: "Collect all selected
        # indices into a single command so that multi-card selections … are
        # recorded atomically"), each index a position in the candidate grid as
        # shown. Taking one command per pick would swallow the next screen's.
        cmd = self.cursor.peek()
        if cmd is None or cmd.name != "SelectGridCard":
            return []
        self.cursor.advance()
        chosen = []
        for arg in cmd.args:
            if arg.lstrip("-").isdigit():
                idx = int(arg)
                if 0 <= idx < len(candidates):
                    chosen.append(candidates[idx])
        return chosen[:count]

    def _target_idx(self, tid: int) -> int:
        """Recorded target CombatId -> its CURRENT index in `combat.enemies`.

        The recording targets by CombatId (creation/attach order, enemies 1..N),
        which is stable across enemy-list reordering (Ovicopter egg slots), so a
        positional `tid - 1` breaks once spawns are inserted out of order. Match
        by the stored `net_id`; fall back to `tid - 1` for combats that never
        assigned ids (creation order == position there anyway)."""
        for i, e in enumerate(self.combat.enemies):
            if getattr(e, "net_id", None) == tid:
                return i
        return tid - 1

    def enemy_by_target_id(self, tid: int):
        """Recorded target CombatId -> the `combat.enemies` slot it names."""
        return self.combat.enemies[self._target_idx(tid)]

    def _live_enemy_states(self) -> list[tuple[str, int, int]]:
        """The recording's `Enemies:` list — `CombatState.Enemies`, which drops
        a creature once it dies UNLESS a power kept it (a withered
        Decimillipede segment stays, showing 0 HP)."""
        return [(enemy_display_name(e), e.hp, e.max_hp)
                for e in self.combat.enemies
                if not e.is_gone or e.retained_after_death]

    @staticmethod
    def _name_matches(recorded: str, live: str) -> bool:
        """A recorded enemy name is the creature's localized Title, and one of
        them carries a counter no run seed can reproduce: TestSubject.cs:72
        appends `Count = SaveManager.Instance.Progress.TestSubjectKills + 8` — a
        PROFILE-lifetime kill count, so the same act-3 boss reads
        "Test Subject #C71" / "#C106" / "#C114" across the three recordings that
        fight it (all three saves carry the same per-run `test_subject_kills`).
        Accept the sim's un-numbered name for exactly that " #…" shape; every
        other difference stays a real divergence."""
        return recorded == live or recorded.startswith(live + " #")

    @staticmethod
    def _recorded_potion_id(cmd) -> str | None:
        """`UsePotion 0 # POTION.SWIFT_POTION || …` -> "swift_potion" (the sim's
        potion id, snake_case of the source class name). None when the recording
        carries no identity comment."""
        import re
        m = re.search(r"POTION\.([A-Z0-9_]+)", cmd.comment or "")
        return m.group(1).lower() if m else None

    def _assert(self, cmd) -> None:
        ann = cmd.annotation
        if ann is None:
            return
        if ann.hand is not None:
            live = [card_display_name(c) for c in self.combat.player.hand]
            if live != ann.hand:
                self.divergences.append(Divergence("hand", cmd.lineno, ann.hand, live))
        if ann.enemies is not None:
            live = self._live_enemy_states()
            exp = [(e.name, e.hp, e.max_hp) for e in ann.enemies]  # EnemyState
            same = len(live) == len(exp) and all(
                self._name_matches(e[0], l[0]) and e[1:] == l[1:]
                for e, l in zip(exp, live)
            )
            if not same:
                self.divergences.append(Divergence("enemies", cmd.lineno, exp, live))

    def play(self) -> list[Divergence]:
        while not self.combat.is_over:
            cmd = self.cursor.peek()
            if cmd is None or cmd.name not in _DRIVER_CMDS:
                break
            self._assert(cmd)
            # Consume the command BEFORE dispatching: a card effect can open a
            # selection screen mid-play (Headbutt) whose SelectGridCard the
            # card_selector reads from the cursor, which must already sit past
            # this PlayCard.
            self.cursor.advance()
            try:
                self._dispatch(cmd)
            except NotImplementedError as exc:
                # Un-ported content reached during replay (a placeholder potion
                # or card effect). Report and stop this fight rather than
                # crashing the whole run -- a conformance driver reports, it
                # does not raise. The runner then force-wins so later fights
                # still replay (surfacing every gap, not just the first).
                self.divergences.append(Divergence(
                    "combat_effect", cmd.lineno,
                    f"{cmd.name} {' '.join(cmd.args)}", str(exc),
                    "un-ported combat effect",
                ))
                break
            if self._stopped:
                break
            self.db.refresh(self.combat)
        return self.divergences

    def _dispatch(self, cmd) -> None:
        """Apply one combat command to the live combat, or set `self._stopped`
        + append a Divergence when the recorded card can't be resolved."""
        self._stopped = False
        if cmd.name == "EndTurn":
            self.combat.end_turn()
        elif cmd.name == "PlayCard":
            card_id = int(cmd.args[0])
            live_hand = [card_display_name(c) for c in self.combat.player.hand]
            try:
                card = self.db.get(card_id)
            except KeyError:
                # The recorded CombatCardDb id was never registered in the
                # sim's db -- an upstream divergence (e.g. an un-ported
                # card-generation effect, or a mis-ordered pile at db start).
                # Report and stop rather than raising: a conformance driver
                # reports, it does not crash.
                self.unresolved_play_card_ids.append(card_id)
                self.divergences.append(Divergence(
                    "play_card", cmd.lineno,
                    f"play db id {card_id}", live_hand,
                    "recorded card id absent from sim combat card db",
                ))
                self._stopped = True
                return
            if card not in self.combat.player.hand:
                # The recorded card resolved but is not in the live hand --
                # the draw/shuffle order has diverged. Report it (localized
                # to this command) and stop: the annotation mismatch above
                # already flags the first divergent draw.
                self.divergences.append(Divergence(
                    "play_card", cmd.lineno,
                    f"play {card_display_name(card)} (db id {card_id})",
                    live_hand, "recorded card absent from live hand",
                ))
                self._stopped = True
                return
            hand_idx = self.combat.player.hand.index(card)
            target_idx = self._target_idx(int(cmd.args[1])) if len(cmd.args) > 1 else None
            self.combat.play_card(hand_idx, target_idx=target_idx)
        elif cmd.name == "UsePotion":
            slot = int(cmd.args[0])
            # `UsePotion N` names a real BELT SLOT: the sim's belt is now a
            # fixed-length list[Potion | None] like Player.cs's
            # `_potionSlots` (using a potion nulls its slot rather than
            # compacting; a new one backfills the first null slot —
            # AddPotionInternal: `_potionSlots.IndexOf(null)`). Still resolve
            # by the recorded IDENTITY (`# POTION.SWIFT_POTION`) rather than
            # trusting `slot` outright — that's robustness against the
            # OUT-OF-SCOPE potion-retention divergence (the sim holding a
            # different potion than the game in that slot), not a belt-model
            # workaround. Only report when the potion genuinely isn't held.
            live = {i: p.id for i, p in enumerate(self.combat.player.potions)
                    if p is not None}
            want = self._recorded_potion_id(cmd)
            if want is not None:
                if want not in live.values():
                    self.divergences.append(Divergence(
                        "potion", cmd.lineno, want, list(live.values()),
                        f"recorded potion (belt slot {slot}) not held",
                    ))
                    self._stopped = True
                    return
                if live.get(slot) != want:
                    slot = next(i for i, pid in live.items() if pid == want)
            target_idx = self._target_idx(int(cmd.args[1])) if len(cmd.args) > 1 else None
            self.combat.use_potion(slot, target_idx=target_idx)
        elif cmd.name == "SelectCardFromScreen":
            # Resolve a mid-combat choose-a-card screen. The arg is the 0-based
            # index into the offered cards, or a non-numeric "skip".
            arg = cmd.args[0] if cmd.args else "skip"
            idx = int(arg) if arg.lstrip("-").isdigit() else None
            self.combat.resolve_screen_selection(idx)
