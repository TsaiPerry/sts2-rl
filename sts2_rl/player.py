"""PlayerCombatState — the player side of a combat, mirroring STS2's
PlayerCombatState.

Extends Creature with energy, the four card piles (hand / draw / discard /
exhaust), and potions. Owns the card-flow verbs: `start_turn` (clear block →
reset energy → turn-start hooks → draw, with innate-card handling on turn 1),
`discard_hand` (respecting Retain), `reshuffle_discard_into_draw`, and the
low-level `_draw`. Constants (ENERGY_PER_TURN, DRAW_PER_TURN, MAX_HAND_SIZE,
MAX_POTIONS) live here as class attributes.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from .cmds import is_over_or_ending as _is_over_or_ending
from .creatures import Creature
from .dotnet_sort import dotnet_list_sort
from .hooks import HookSystem
from .turn_phase import PlayerTurnPhase

if TYPE_CHECKING:
    from .cards import Card
    from .potions import Potion


def _compare_to_key(card: "Card") -> "tuple[str, int]":
    """CardModel.CompareTo's sort key (CardModel.cs:2242): the ModelId first —
    `string.Compare(Entry, other.Entry, StringComparison.Ordinal)`
    (ModelId.cs:49) over the game's UPPERCASE entry — then CurrentUpgradeLevel.

    Case matters: an ordinal compare puts `_` (0x5F) *after* the uppercase
    letters but *before* the lowercase ones, so sorting the sim's lowercase
    slugs orders `blood_wall`/`bloodletting` and
    `jack_of_all_trades`/`jackpot` the opposite way round from the game.
    Cards that compare equal are ordered by `dotnet_list_sort`'s introsort, not
    by their incoming positions (`List<T>.Sort()` is NOT stable — see
    `sts2_rl/dotnet_sort.py`), but the incoming order is still what that
    algorithm runs on, so the caller must pass the pile in the GAME's
    orientation."""
    return (card.id.upper(), card.upgrade_level)


def stable_shuffled_cards(cards: "list[Card]", combat_rng,
                          stream=None) -> "list[Card]":
    """`cards.ToList().StableShuffle(rng)` — a shuffled COPY, in the
    game's own orientation (index 0 is the game's `First()`).

    Content that picks a card at random by shuffling a pile and taking the
    front (Catastrophe) must burn the shuffle's N-1 draws, not one. The
    stabilizing sort is the same CardModel.CompareTo key `_shuffle_cards`
    uses, and is parity-only for the same reason: legacy stays byte-for-byte.

    `stream` names the Rng the call site's C# passes to StableShuffle, because
    it is NOT always Rng.Shuffle: Catastrophe and Beat Down use Shuffle,
    Seeker Strike uses CombatCardSelection (SeekerStrike.cs:36). Defaults to
    Shuffle, which is what every earlier caller means.
    """
    out = list(cards)
    if combat_rng.is_parity:
        dotnet_list_sort(out, key=_compare_to_key)
    (stream if stream is not None else combat_rng.shuffle).shuffle(out)
    return out


class PlayerCombatState(Creature):
    ENERGY_PER_TURN = 3
    DRAW_PER_TURN = 5
    MAX_HAND_SIZE = 10
    MAX_POTIONS = 3

    def __init__(
        self,
        max_hp: int,
        deck: list[Card],
        combat_rng,
        hooks: HookSystem,
        potions: list[Potion] | None = None,
        max_potions: int | None = None,
    ) -> None:
        super().__init__(max_hp)
        self.side = "player"
        # `Player.IsActiveForHooks` (Player.cs:112). "Almost equivalent to
        # Creature.IsAlive, except for a brief period between the player's HP
        # reaching zero and DieInternal" (Player.cs:103-111) — it is what lets
        # death-prevention hooks run before the player counts as dead, and it
        # exists on Player rather than Creature because a dead player STAYS in
        # the combat where a dead monster is removed from it.
        #
        # `CombatState.IterateHookListeners` reads it twice: structurally at
        # :424-427, where a false value skips that player's relics, potions,
        # orbs and cards (but not the powers already added at :416), and lazily
        # in `Contains` (:589-597) as the owner leg of every card/relic/potion/
        # affliction/enchantment arm. Initialised true (`= Creature.IsAlive`,
        # Player.cs:272/:438) and cleared by `DeactivateHooks` (:857-860) from
        # CreatureCmd.cs:553 — after AfterDeath, i.e. only once the death is
        # real and unprevented.
        #
        # RE-SET by `ActivateHooks` (:868-871), and single-player DOES reach it
        # — do not delete the two lines that do. C#'s own doc comment there
        # guesses "likely only called in multiplayer scenarios", but the caller
        # is `Creature.HealInternal` (Creature.cs:477-485, `if (isDead &&
        # !IsDead) Player?.ActivateHooks()`), and `CombatManager.
        # EndCombatInternal` runs EVERY player's `ReviveBeforeCombatEnd`
        # (CombatManager.cs:986) — which heals a dead player to 1 — immediately
        # before `Hook.AfterCombatEnd` (:988). Player.cs:813-819 says in as many
        # words why the order matters: a still-dead player's relics "will not be
        # subscribed to the HookBus, and relics which rely on AfterCombatEnd to
        # reset state will not be reset for the next combat". The sim mirrors
        # both callers (`CreatureCmd.heal`, `CombatState._end_combat_internal`)
        # and the window is genuinely open: `_check_win_condition` tests
        # `_has_pending_loss` first, but seven other call sites reach
        # `_end_combat(player_won=True)` without that test. Verified by
        # execution: without the reactivation, Chosen Cheese silently loses its
        # AfterCombatEnd max-HP gain (80 -> 80 instead of 80 -> 81) and no other
        # test in the suite notices. Pinned by
        # `test_the_victory_path_revives_before_dispatching_after_combat_end`.
        self.is_active_for_hooks = True
        self.energy = 0
        self.hand: list[Card] = []
        self.draw_pile: list[Card] = deck.copy()
        self.discard_pile: list[Card] = []
        self.exhaust_pile: list[Card] = []
        # `PlayerCombatState.PlayPile` (PlayerCombatState.cs:68) — the FIFTH
        # combat pile (PileTypeExtensions.cs:35-42) and the LAST entry of
        # `AllPiles` (:76). A card sits here for the whole of its own
        # `OnPlayWrapper` (CardModel.cs:1875/:1879), and `CardPileCmd.Shuffle`
        # reads only Draw and Discard (CardPileCmd.cs:870-871) — which is the
        # entire mechanism behind "a reshuffle a card's own effect triggers
        # cannot pick that card up". The sim used to fake it by parking the
        # card in the DISCARD pile and marking it `_playing_card`, then
        # subtracting it back out at every reader (see the de-hack list in
        # `Combat._resolve_card_play`). creature_card_cmds N9 + step82.
        self.play_pile: list[Card] = []
        # Belt size defaults to the base 3; runs pass their own (Phial
        # Holster grows RunState.max_potions). Fixed-length list[Potion |
        # None] mirroring Player.cs's `_potionSlots` — see RunState.potions
        # for the full citation. A caller's plain (gap-free) list is placed
        # left-to-right from slot 0; a list that already carries `None` gaps
        # (RunState.potions handed in by create_combat) keeps them in place.
        self.max_potions = max_potions if max_potions is not None else self.MAX_POTIONS
        self.potions: list[Potion | None] = [None] * self.max_potions
        for i, p in enumerate(list(potions or [])[: self.max_potions]):
            self.potions[i] = p
        self._combat_rng = combat_rng
        self._hooks = hooks
        self._first_turn = True
        # PlayerCombatState.Phase. `None` until StartTurn runs; content reads
        # it (UnceasingTop.cs:18). See sts2_rl/turn_phase.py.
        self.turn_phase = PlayerTurnPhase.NONE
        # The card whose `OnPlayWrapper` is currently executing, if any.
        #
        # This is NO LONGER the sim's PileType.Play stand-in — `play_pile`
        # above is the real pile. What survives here is the strictly narrower
        # fact "this card's OnPlay is on the stack right now", which the Play
        # pile cannot express: `CardPileCmd.AutoPlayFromDrawPile` parks EVERY
        # pick in Play (CardPileCmd.cs:954) before playing any of them, and a
        # card whose OnPlay auto-plays another card (Cascade) leaves both in
        # Play at once. Maintained by `Combat._resolve_card_play`, which saves
        # and restores it so a nested play does not clear the outer card's
        # mark.
        #
        # Currently unread: `relics/pen_nib.py` used to be its consumer but now
        # tests `card not in player.play_pile` instead (PenNib.cs:120-128 wants
        # `cardSource.Pile?.Type != PileType.Play`); the two predicates differ
        # whenever `AutoPlayFromDrawPile` has more than one pick parked in Play.
        # Kept because the fact it names ("this card's OnPlay is on the stack
        # right now") has no other expression in the sim — C#'s own
        # `CardPlay`/`BeginCardOrPotionEffect` bracket is what a future port
        # would attach here. A reader added later should check whether the
        # Play pile answers the question instead.
        self._playing_card: Card | None = None
        # Combat-start draw-pile randomization is CardPile.RandomizeOrderInternal
        # -> UnstableShuffle (Fisher-Yates, NO stabilizing sort), unlike the
        # mid-combat reshuffle which is a StableShuffle. Hence stable=False here.
        # Pass self.draw_pile itself (not a copy): RandomizeOrderInternal
        # shuffles the pile's own `_cards` in place before dispatching, so the
        # aliasing is the correct replication here -- see _shuffle_cards.
        self.draw_pile = self._shuffle_cards(self.draw_pile, stable=False)

    @property
    def all_cards(self) -> list[Card]:
        """`PlayerCombatState.AllCards` (PlayerCombatState.cs:82) —
        `AllPiles.SelectMany(p => p.Cards)` over the five piles in their
        declared PILE order, Play LAST (:76).

        The Play leg is what makes a card sweep reach the card that is being
        played right now: SmoggyPower's AfterCardPlayed sweep
        (SmoggyPower.cs:24-34) afflicts the very Skill that triggered it,
        because in C# that Skill is sitting in Play.

        WITHIN a pile the equivalence is not exact, and only for one leg:
        `CardPile` is TOP-FIRST (`MoveToTopInternal` is `Insert(0, …)` and
        `CardPileCmd.cs:843` draws `FirstOrDefault()`), while the sim's
        `draw_pile` is BOTTOM-first — end of list = top of pile. So the draw
        leg is emitted in the reverse of `AllPiles.SelectMany`'s order; the
        other four are stored in C#'s order. `HookSystem._derive` flips the
        draw pile for exactly this reason and this method does not, because
        nothing that reads it is order-sensitive: every consumer is an
        unconditional sweep (`apotheosis`, `maul`, `ghost_seed`,
        `end_of_turn_cleanup`, the Smoggy/Ringing/Tainted/Galvanized affliction
        sweeps, `combat.py`'s listener REGISTRATION — whose dispatch order
        `_derive` recomputes anyway) or a count (`perfected_strike`), and
        `CardCmd.afflict` draws no RNG. Flipping it is a one-line change if a
        first-match or RNG-proportional consumer is ever ported; do not assume
        the equivalence holds before then. R5-review RV-7."""
        return (self.hand + self.draw_pile + self.discard_pile
                + self.exhaust_pile + self.play_pile)

    def pile_type_of(self, card: Card) -> str | None:
        """`CardModel.Pile?.Type` — which pile holds this card RIGHT NOW, or
        None for a card that is in no combat pile (a played Power, which
        `CardPileCmd.RemoveFromCombat` takes out of the combat entirely, or a
        run-deck card that was never dealt in).

        A straight membership test over `AllPiles`, in `AllPiles` order: with
        a real `play_pile` there is no marker to consult and no card in two
        piles at once. (It used to test `_playing_card` FIRST, because the
        sim parked a resolving card in the discard pile and would otherwise
        have answered Discard for a card the game holds in Play.)

        Several C# models guard on the pile — `FreeAttackPower.cs:26-39` and
        `:48-59` want `Hand` or `Play` — and the sim had no way to ask."""
        if card in self.hand:
            return "hand"
        if card in self.draw_pile:
            return "draw"
        if card in self.discard_pile:
            return "discard"
        if card in self.exhaust_pile:
            return "exhaust"
        if card in self.play_pile:
            return "play"
        return None

    def remove_from_current_pile(self, card: Card) -> str | None:
        """`CardModel.RemoveFromCurrentPile` (CardPileCmd.cs:496 ->
        CardModel.cs) — take the card out of whatever combat pile holds it and
        return that pile's name, or None if it was in none.

        Pile-agnostic by construction, which is the property every ad-hoc
        four-pile scan in the sim was approximating; the fifth pile is why
        they are centralised here."""
        for name, pile in (("hand", self.hand), ("draw", self.draw_pile),
                           ("discard", self.discard_pile),
                           ("exhaust", self.exhaust_pile),
                           ("play", self.play_pile)):
            if card in pile:
                pile.remove(card)
                return name
        return None

    # ── Potions ──────────────────────────────────────────────────────────

    def add_potion(self, potion: Potion) -> bool:
        """Fill the first open belt slot. Returns whether it was kept.

        Mirrors Player.cs AddPotionInternal: `slotIndex =
        _potionSlots.IndexOf(null)` — fails if no slot is null (belt full).
        Combat-side procurement (Alchemize, Delicate Frond, Petrified Toad)
        does not run the Hook.ShouldProcurePotion gate today (see
        RunState.add_potion for the out-of-combat Sozu gate) — unchanged by
        this fix, out of scope."""
        if None not in self.potions:
            return False
        self.potions[self.potions.index(None)] = potion
        potion.combat = self._hooks.combat
        self._hooks.register(potion)
        return True

    def discard_potion(self, potion: Potion) -> None:
        """Null the potion's belt slot (Player.cs DiscardPotionInternal) — the
        other slots keep their positions; the belt is never compacted."""
        self.potions[self.potions.index(potion)] = None
        self.detach_potion(potion)

    def detach_potion(self, potion: Potion) -> None:
        """Stop dispatching hooks to a potion that has left the belt (it is no
        longer in CombatState.IterateHookListeners' PotionSlots walk — that is
        what stops a used Fairy in a Bottle from preventing death again)."""
        try:
            self._hooks.unregister(potion)
        except ValueError:
            pass

    @property
    def held_potions(self) -> list[Potion]:
        """The potions actually held, in slot order, with empty slots
        filtered out (Player.cs `Potions => _potionSlots.Where(p => p !=
        null)`)."""
        return [p for p in self.potions if p is not None]

    @property
    def has_open_potion_slot(self) -> bool:
        """Mirrors Player.cs `HasOpenPotionSlots => _potionSlots.Any(p => p
        == null)`."""
        return None in self.potions

    def start_turn(self) -> None:
        """Reset block/energy, fire turn-start hooks, then draw."""
        # CombatManager.cs:429 — StartTurn opens by putting EVERY player back
        # to PlayerTurnPhase.None, on both sides, before any hook fires.
        self.turn_phase = PlayerTurnPhase.NONE
        # No card reset here. "This turn" card state expires at the END of the
        # turn, in PlayerCombatState.EndOfTurnCleanup, which C# runs at two
        # sites and neither is a turn START (turn_structure G7). Resetting here
        # instead kept every modifier alive through the whole enemy turn.

        # Hook.BeforeSideTurnStart (CombatManager.cs:458) — the side's first
        # hook, after each participant's Creature.BeforeTurnStart (the loop
        # above) and BEFORE the enemies' next-move roll and the block clear.
        self._hooks.before_side_turn_start(self)
        # CombatManager.cs:464 — Start is entered on the player-side branch,
        # strictly AFTER Hook.BeforeSideTurnStart.
        self.turn_phase = PlayerTurnPhase.START

        # Creature.AfterTurnStart (Creature.cs:681-692) returns BEFORE
        # ClearBlock for a player whose TurnNumber == 1 — that is what lets
        # Hook.BeforeCombatStart grant block that survives into the first enemy
        # turn, and why Anchor's real hook is BeforeCombatStart rather than the
        # on_block_cleared the sim had to rewire it onto.
        if not self._first_turn:
            preventer: list = []
            if self._hooks.should_clear_block(self, preventer):
                self.block = 0
            else:
                # Creature.cs:726 — the else-arm names the vetoing listener.
                self._hooks.after_preventing_block_clear(preventer, self)
        # CombatManager.cs:492-507 runs the block clear and its event in TWO
        # loops: `foreach AfterTurnStart` then `foreach Hook.AfterBlockCleared`.
        # So the event fires for every participant — one with no block, one
        # whose clear a ShouldClearBlock listener prevented, and a turn-1 player
        # whose AfterTurnStart returned early. Fusing it into the `if` arm meant
        # a Barricaded player never re-armed Anchor or Fake Anchor.
        self._hooks.on_block_cleared(self)

        # SetupPlayerTurn (CombatManager.cs:629-676) opens on
        # `if (player.Creature.IsDead) return;` (:631-634), so a dead player
        # gets no energy, no draw and no Hook.AfterPlayerTurnStart. The SIDE
        # hooks around it still run: the block clear above is StartTurn's own
        # loop (:492-507) and Hook.AfterSideTurnStart below is :522.
        if not self.is_dead:
            self._setup_player_turn()
        # Hook.AfterSideTurnStart (CombatManager.cs:522) — once for the side,
        # after every SetupPlayerTurn has returned. A separate, later hook that
        # this slot used to be fused with; see HookSystem.after_side_turn_start.
        self._hooks.after_side_turn_start(self)
        # PlayerTurnPhase.AutoPrePlay (CombatManager.cs:556-572): entered
        # strictly AFTER Hook.AfterSideTurnStart and the orb queue.
        # RunAutoPrePlayPhase (:613-619) brackets the hook and nothing else:
        # AutoPrePlay at :616, the hook at :617, Play at :618. :566 skips the
        # whole phase for a dead player.
        if not self.is_dead:
            self.turn_phase = PlayerTurnPhase.AUTO_PRE_PLAY
            self._hooks.after_auto_pre_play_phase_entered(self)
            self.turn_phase = PlayerTurnPhase.PLAY

    def _setup_player_turn(self) -> None:
        """SetupPlayerTurn's body (CombatManager.cs:640-675): energy reset,
        Hook.BeforeHandDraw, the hand draw with its turn-1 pile moves, and
        Hook.AfterPlayerTurnStart."""
        # Energy reset — or add-to-current when a listener vetoes the reset
        # (mirrors ShouldPlayerResetEnergy → ResetEnergy / AddMaxEnergyToCurrent).
        # CombatManager.cs:641-649 — ShouldPlayerResetEnergy is evaluated
        # FIRST; MaxEnergy (== Hook.ModifyMaxEnergy(..., player.MaxEnergy),
        # PlayerCombatState.cs:101) is read INSIDE the chosen branch, exactly
        # once either way. The sim used to call modify_max_energy first
        # (tier-2 Task 11, item E; turn_structure/step17, dormant).
        should_reset = self._hooks.should_reset_energy(self)
        gained = self._hooks.modify_max_energy(self, self.ENERGY_PER_TURN)
        if should_reset:
            self.energy = gained
        else:
            self.energy += gained
        self._hooks.on_energy_reset(self)
        self._hooks.on_player_turn_start(self)

        hand_draw_modifiers: list = []
        draw_count = self._hooks.modify_hand_draw(
            self, self.DRAW_PER_TURN, hand_draw_modifiers)
        # CombatManager.cs:655 — Hook.AfterModifyingHandDraw, immediately
        # after ModifyHandDraw returns and before the turn-1 pile moves and
        # the draw itself (tier-2 Task 11, item C; turn_structure/step20,
        # dormant).
        self._hooks.after_modifying_hand_draw(hand_draw_modifiers)
        if self._first_turn:
            self._first_turn = False
            # Innate cards move to the top of the draw pile and the first-turn
            # draw is raised to include all of them (mirrors CombatManager's
            # combat-start innate handling: MoveToTop + handDraw = max(...)).
            # CombatManager.cs:657-672 runs TWO pile moves before the turn-1
            # draw, in this order: first every card whose enchantment sets
            # ShouldStartAtBottomOfDrawPile goes to the BOTTOM, then every
            # Innate card `.Except(list)` goes to the top. The sim ported only
            # the Innate half, so an Imbued card (Imbued.cs:11 is the hook's
            # only implementer in the whole game, granted by Electric Shrymp)
            # kept occupying an opening-hand slot the game never gives it.
            sinking = [c for c in self.draw_pile
                       if c.enchantment is not None
                       and getattr(c.enchantment,
                                   "should_start_at_bottom_of_draw_pile", False)]
            for card in sinking:
                self.draw_pile.remove(card)
            # index 0 = bottom of the pile (the end of the list is the top).
            self.draw_pile[:0] = sinking
            innates = [c for c in self.draw_pile
                       if c.innate and c not in sinking]
            if innates:
                for card in innates:
                    self.draw_pile.remove(card)
                self.draw_pile.extend(innates)  # end of list = top of pile
                draw_count = max(draw_count, len(innates))
        self._draw(draw_count, from_hand_draw=True)
        # Hook.AfterPlayerTurnStart (CombatManager.cs:675) — SetupPlayerTurn's
        # last line, so per player and immediately after that player's draw.
        self._hooks.on_player_turn_started(self)

    def discard_hand(self, flush: bool = True) -> None:
        """FlushPlayerHand (CombatManager.cs:1313-1347).

        Retain cards stay in hand (ShouldRetainThisTurn). `flush=False` is
        Hook.ShouldFlush returning false, which C# treats as "every card is
        retained": `cardsToFlush` is empty and the batched Add is skipped, but
        the TAIL — Hook.AfterFlush and PlayerCombatState.EndOfTurnCleanup —
        still runs. The sim used to skip the whole call.

        No `on_card_discarded`/`Hook.AfterCardDiscarded` here, and this is not
        a "fire after the move" ordering fix -- FlushPlayerHand never fires it
        at all. `await CardPileCmd.Add(cardsToFlush, PileType.Discard)` is the
        ONLY pile-change call this method makes, and a repo-wide
        `grep -rn AfterCardDiscarded src/` over the decompiled game returns
        exactly four hits: the AbstractModel/Hook.cs declarations, the two
        relic overrides (Tingsha.cs:18, ToughBandages.cs:20), and its ONE
        call site, `CardCmd.cs:194`, inside `DiscardAndDraw` -- the explicit
        "discard these specific cards" command (Concentrate, Sly, Gambler's
        Brew/Gambling Chip's `CardCmd.DiscardAndDraw`), which this method is
        not and does not call. `discard_hand`'s only caller is the turn-end
        flush (`combat.py`'s `should_flush_hand`/`discard_hand` pair) --
        confirmed by grep, no other site calls it -- so it is FlushPlayerHand
        and nothing else. (creature_card_cmds guard G11 / step49 previously
        cited CardCmd.cs:186-195 for this method; that citation names the
        wrong method — the correct fix is removing the call, not reordering it.)

        No `on_hand_emptied` here either. CombatManager.cs:880-883 excludes
        the flush from CheckForEmptyHand in as many words ("besides ending
        turn, which should not trigger an empty hand check"), and the flush is
        the one site the sim used to fire it from (turn_structure G16).
        """
        # CardCmd.cs:174-177 -- Discard/DiscardAndDraw open on
        # `IsOverOrEnding -> return`, so the end-of-turn flush of a combat that
        # has just been won leaves the hand alone.
        if _is_over_or_ending(self._hooks):
            return
        # CombatManager.cs:1330 partitions on `!flag || card.ShouldRetainThisTurn`
        # — the Retain KEYWORD or a single-turn grant (CardModel.cs:590-600).
        flushed = [c for c in self.hand if not c.should_retain_this_turn] if flush else []
        self.discard_pile.extend(flushed)
        if flush:
            self.hand = [c for c in self.hand if c.should_retain_this_turn]
        # CombatManager.cs:1346 — FlushPlayerHand's last line, after
        # Hook.AfterFlush. One of EndOfTurnCleanup's two sites.
        self.end_of_turn_cleanup()

    def end_of_turn_cleanup(self) -> None:
        """PlayerCombatState.EndOfTurnCleanup (PlayerCombatState.cs:268-274) —
        `foreach (CardModel allCard in AllCards) allCard.EndOfTurnCleanup()`.
        Every pile, not just the hand."""
        for card in self.all_cards:
            card.end_of_turn_cleanup()

    def shuffle_if_necessary(self) -> None:
        """`CardPileCmd.ShuffleIfNecessary` (CardPileCmd.cs:972-981) in full —
        `if (!draw.Cards.Any() && discard.Cards.Any()) await Shuffle(...)`. The
        guard is the whole method: an empty discard or a non-empty draw pile is a
        no-op, and the reshuffle it delegates to is the STABLE one. Callers that
        inlined `if not draw and discard: reshuffle` were right; callers that
        inlined their own unstable shuffle (Havoc did) were not."""
        if not self.draw_pile and self.discard_pile:
            self.reshuffle_discard_into_draw()

    def reshuffle_discard_into_draw(self) -> None:
        """Shuffle the discard pile into the empty draw pile (mirrors
        CardPileCmd.ShuffleIfNecessary's reshuffle step)."""
        if _is_over_or_ending(self._hooks):
            return          # CardPileCmd.cs:866-869
        # `CardPileCmd.Shuffle` reads exactly two piles — `PileType.Draw` and
        # `PileType.Discard` (CardPileCmd.cs:870-871). A card mid-OnPlay is in
        # NEITHER: it sits in `PileType.Play` for the whole of its wrapper
        # (CardModel.cs:1875/:1879). So the exclusion this method used to
        # implement by hand — hold `_playing_card` back out of the discard,
        # then put it back afterwards — is now structural and the hold-back
        # code is gone (round 13, R5; creature_card_cmds N9/step82).
        cards = list(self.discard_pile)   # COPY -- see _shuffle_cards
        new_discard: list[Card] = []
        # A mid-combat reshuffle is CardPileCmd.Shuffle -> StableShuffle. Shuffle
        # and dispatch BEFORE touching self.draw_pile/self.discard_pile -- see
        # _shuffle_cards (creature_card_cmds/G10, RE-VERIFIED 2026-07-30,
        # tier-2 Task 5).
        cards = self._shuffle_cards(cards, stable=True)
        self.draw_pile = cards
        self.discard_pile = new_discard
        # CardPileCmd.cs:892-912: every card in the shuffled order gets a
        # full `Add()` -> `AfterCardChangedPiles` UNLESS it was already
        # sitting in the draw pile (those are re-seated silently,
        # `AddInternal(item2, -1, silent: true)`, no hook at all). This
        # method only ever runs with an EMPTY draw pile -- every one of its
        # five callers gates on `not self.draw_pile` first
        # (`shuffle_if_necessary` above, plus DistilledChaos/Cascade/Toasty
        # Mittens' own `if not draw_pile` guards) -- so every card here
        # originated in the discard and the silent branch never applies at
        # this call site; contrast `shuffle_draw_and_discard`, where it can.
        # seam/creature_card_cmds guard G8, step96.
        for card in cards:
            self._hooks.after_card_changed_piles(card, "discard", None)
        self._hooks.on_shuffle(self)

    def shuffle_draw_and_discard(self) -> None:
        """CardPileCmd.Shuffle: shuffle the discard pile AND the whole current
        draw pile into a new draw pile (Bottled Potential).

        `reshuffle_discard_into_draw` is the ShuffleIfNecessary path, which only
        ever runs with an empty draw pile; the explicit command shuffles both
        piles together (`list = discard.ToList(); list.AddRange(drawPileCards);
        list.StableShuffle(Rng.Shuffle)`), so the draw pile's contents survive
        into the new order. Same two piles, so the same PileType.Play rule: a
        card mid-OnPlay is in neither and needs no hold-back."""
        if _is_over_or_ending(self._hooks):
            return          # CardPileCmd.cs:866-869
        discard = self.discard_pile
        new_discard: list[Card] = []
        # CardPileCmd.cs:874 `drawPileCards = drawPile.Cards.ToHashSet()` --
        # captured BEFORE the shuffle, so it names each card's ORIGIN pile,
        # not its post-shuffle position. Only non-origin (discard-sourced)
        # cards get a full `Add()` -> `AfterCardChangedPiles` dispatch below;
        # already-in-draw cards are re-seated silently (CardPileCmd.cs:911),
        # the asymmetry step96 describes -- and unlike
        # `reshuffle_discard_into_draw`, this method (Bottled Potential,
        # Reboot) can genuinely run with cards already in the draw pile, so
        # the asymmetry has a real surface here. seam/creature_card_cmds
        # guard G8, step96.
        already_in_draw = {id(c) for c in self.draw_pile}
        cards = discard + self.draw_pile   # `+` always copies -- see _shuffle_cards
        # See reshuffle_discard_into_draw: shuffle and dispatch BEFORE touching
        # the real piles (creature_card_cmds/G10, tier-2 Task 5).
        cards = self._shuffle_cards(cards, stable=True)
        self.draw_pile = cards
        self.discard_pile = new_discard
        for card in cards:
            if id(card) not in already_in_draw:
                self._hooks.after_card_changed_piles(card, "discard", None)
        self._hooks.on_shuffle(self)

    def _shuffle_cards(self, cards: list[Card], stable: bool) -> list[Card]:
        """Shuffle `cards` via the Shuffle stream and dispatch
        Hook.ModifyShuffleOrder on it, in place.

        The game has two draw-pile shuffles that both draw from the same
        Shuffle stream but differ in one step:

          - combat start: CardPile.RandomizeOrderInternal -> UnstableShuffle
            (Fisher-Yates only), `stable=False`.
          - reshuffle:    CardPileCmd.Shuffle -> StableShuffle, `stable=True`,
            which SORTS the pile into a canonical order first so the result is
            INDEPENDENT of the pile's incoming (play) order, THEN Fisher-Yates.

        "Independent of the incoming order" is the verb's INTENT and holds for
        any two cards that compare unequal. It does NOT hold for a tie: C#'s
        `List<T>.Sort()` is an introsort and is not stable, so two identical
        cards (same ModelId, same upgrade level — `CardModel.CompareTo` returns
        0, CardModel.cs:2242-2263) come out in an order the ALGORITHM decides
        from where they happened to sit. That is why the sort below is
        `dotnet_list_sort` and not `cards.sort`; see `sts2_rl/dotnet_sort.py`
        for the divergence that paid for it.

        In parity mode we reproduce both. The stabilizing sort mirrors the
        game's CardModel.CompareTo: first ModelId ordinal (Category.Entry) — the
        sim card `id` is a lowercase slug whose ordinal order matches the game
        Entry ordinal for the cards seen so far (bash < defend < strike, etc.)
        — then, for cards of the same id, CurrentUpgradeLevel (CardModel.cs
        CompareTo). The upgrade tiebreak matters whenever a pile holds both a
        base and an upgraded copy of one card (e.g. Defend + Defend+): the game
        sorts the upgraded copy AFTER the base regardless of their incoming
        discard order, so which variant lands on top after the Fisher-Yates is
        decided by upgrade level, not by play order. (A game-id override map can
        be added later if a card whose slug diverges from its game Entry order
        turns up.) Finally, the game stores the pile top-at-index-0 but the sim
        draws off the END of the list (its top), so reverse to reproduce the
        game's front-to-back draw order under the sim's top=end convention.

        Legacy is byte-for-byte unchanged: the shared random.Random shuffles in
        place with no sort and no reorientation.

        WHO CAN CALL THIS WITH WHAT (creature_card_cmds/G10, RE-VERIFIED
        2026-07-30, tier-2 Task 5): Hook.ModifyShuffleOrder fires HERE — after
        the Fisher-Yates and before the pile is repopulated (CardPileCmd.cs:877
        for the mid-combat shuffle, CardPile.cs:73 for RandomizeOrderInternal).
        `HookSystem.modify_shuffle_order`'s per-dispatch listener order is keyed
        on each listener's card's position in `player.all_cards` (Hand, Draw,
        Discard, Exhaust), re-derived fresh every call to mirror
        CombatState.IterateHookListeners (CombatState.cs:449-467) doing the same
        from the real piles. C# gets this for free because `CardPileCmd.Shuffle`
        builds a DETACHED local `list` (CardPileCmd.cs:871-876) and only removes
        cards from the real Draw/Discard piles AFTER the hook has run
        (CardPileCmd.cs:878-913) -- so at dispatch time the real piles are still
        in their PRE-shuffle state. `CardPile.RandomizeOrderInternal` is the one
        exception: it shuffles the pile's OWN `_cards` list in place
        (CardPile.cs:69-73), so there the "pre-shuffle" and "post-shuffle" pile
        both mean the same object, and combat start's caller below passes
        `self.draw_pile` itself (aliased, correctly). For the two mid-combat
        callers, `cards` MUST be a list this method can mutate freely WITHOUT
        that mutation being visible through `self.draw_pile`/`self.discard_pile`
        -- callers build a fresh list (never `self.discard_pile`/`self.draw_pile`
        by reference) and must not reassign either attribute until this method
        returns. Getting this wrong once already cost a `Perfect Fit` + clone
        collision its determinism: reassigning `self.draw_pile =
        self.discard_pile` and shuffling THAT before dispatch made the "later in
        the discard wins" tie-break depend on the Fisher-Yates outcome instead
        of the pre-shuffle discard order — an RNG coin flip that only looked
        fixed because the regression tests pinned a single seed where the
        2-card shuffle happened not to swap."""
        if stable and self._combat_rng.is_parity:
            dotnet_list_sort(cards, key=_compare_to_key)
        self._combat_rng.shuffle.shuffle(cards)
        if self._combat_rng.is_parity:
            cards.reverse()
        self._hooks.modify_shuffle_order(self, cards, is_initial_shuffle=not stable)
        return cards

    def _draw(self, n: int, from_hand_draw: bool = False) -> None:
        # CardPileCmd.cs:800-803 -- `IsOverOrEnding -> empty`, before
        # Hook.ShouldDraw is even consulted.
        if _is_over_or_ending(self._hooks):
            return
        # CardPileCmd.cs:804-808 -- Hook.ShouldDraw is evaluated EXACTLY ONCE
        # per Draw call, strictly before `drawsRequested`/`num` (the hand-space
        # count) are even computed -- i.e. before the per-card loop below, not
        # inside it. A refusal fires Hook.AfterPreventingDraw(modifier),
        # targeted at the ONE listener that vetoed (mirrors ShouldDie/
        # ShouldClearBlock's `out preventer` pattern), then the WHOLE draw
        # returns empty: unlike a `break` reached mid-loop, no card is drawn at
        # all, not even the ones that would have come before a hypothetical
        # per-card refusal. seam/creature_card_cmds guard G9, step84.
        preventer: list = []
        if not self._hooks.should_draw(self, from_hand_draw, preventer):
            self._hooks.after_preventing_draw(preventer)
            return
        for _ in range(n):
            if len(self.hand) >= self.MAX_HAND_SIZE:
                break
            if not self.draw_pile:
                if not self.discard_pile:
                    break
                self.reshuffle_discard_into_draw()
                # AfterShuffle hooks (e.g. Stratagem) can drain the pile;
                # the game re-checks after ShuffleIfNecessary and stops.
                if not self.draw_pile:
                    break
            card = self.draw_pile.pop()  # end of list = top of pile
            self.hand.append(card)
            # `await Add(card, hand)` (CardPileCmd.cs:849) is the FULL Add
            # pipeline, whose own end-of-batch dispatch
            # (CardPileCmd.cs:635) fires before Draw's own hooks below --
            # oldPile was Draw, so `pile="draw"`. seam/creature_card_cmds
            # guard G8, step89.
            self._hooks.after_card_changed_piles(card, "draw", None)
            self._hooks.on_card_drawn(card, from_hand_draw)
