"""SP3 Task 7: ReplayCombatDriver — replay a recording's combat commands
against a live, parity-mode `CombatState`, asserting each command's pre-state
annotation (Hand / Enemies) against the recording before dispatching it.

Card resolution uses the `CombatCardDb` (Task 5) oracle: `PlayCard`'s first
argument is the per-combat card id (`NetCombatCardDb`), not a hand index —
`card_db.get(id)` returns the card, whose hand index is then looked up live.
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
_COMBAT_TAIL_CMDS = _DRIVER_CMDS | {"SelectGridCard"}


def card_display_name(card) -> str:
    """Recording spelling: base name + one '+' per upgrade level (Card.__repr__:
    f"{name}{'+'*upgrade_level}"). e.g. "Strike", "Defend+", "Bash+", "Slimed"."""
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
        """Resolve a synchronous in-combat card selection.

        Mirrors CardSelectCmd.FromCombatPile: when the choice isn't a genuine
        over-count one (``num <= MinSelect``), the game auto-resolves — takes all
        candidates in pile order with no screen, so the recording holds no
        SelectGridCard. Only a real over-count choice shows a screen, which the
        recording captures as a SelectGridCard whose arg is the picked index."""
        if len(candidates) <= count:
            return list(candidates)
        chosen = []
        for _ in range(count):
            cmd = self.cursor.peek()
            if cmd is None or cmd.name != "SelectGridCard":
                break
            self.cursor.advance()
            arg = cmd.args[0] if cmd.args else None
            if arg is not None and arg.lstrip("-").isdigit():
                idx = int(arg)
                if 0 <= idx < len(candidates):
                    chosen.append(candidates[idx])
        return chosen

    def enemy_by_target_id(self, tid: int):
        """1-based recording target id -> the `combat.enemies` slot it names."""
        return self.combat.enemies[tid - 1]

    def _assert(self, cmd) -> None:
        ann = cmd.annotation
        if ann is None:
            return
        if ann.hand is not None:
            live = [card_display_name(c) for c in self.combat.player.hand]
            if live != ann.hand:
                self.divergences.append(Divergence("hand", cmd.lineno, ann.hand, live))
        if ann.enemies is not None:
            live = [(enemy_display_name(e), e.hp, e.max_hp)
                    for e in self.combat.enemies if not e.is_gone]
            exp = [(e.name, e.hp, e.max_hp) for e in ann.enemies]  # EnemyState
            if live != exp:
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
            target_idx = int(cmd.args[1]) - 1 if len(cmd.args) > 1 else None
            self.combat.play_card(hand_idx, target_idx=target_idx)
        elif cmd.name == "UsePotion":
            slot = int(cmd.args[0])
            target_idx = int(cmd.args[1]) - 1 if len(cmd.args) > 1 else None
            self.combat.use_potion(slot, target_idx=target_idx)
        elif cmd.name == "SelectCardFromScreen":
            # Resolve a mid-combat choose-a-card screen. The arg is the 0-based
            # index into the offered cards, or a non-numeric "skip".
            arg = cmd.args[0] if cmd.args else "skip"
            idx = int(arg) if arg.lstrip("-").isdigit() else None
            self.combat.resolve_screen_selection(idx)
