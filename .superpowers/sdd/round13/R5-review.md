# R5 review — the Play pile (`creature_card_cmds` N9 + step82 + G8, step99, step51, step56, `power/smoggy`)

Reviewer pass over `.superpowers/sdd/round13/R5-report.md` and `R5-diff.txt`.
Everything below was re-derived from the C# at `c:\Users\Perry\Desktop\Slay the
Spire 2` and, where it is a behavioural claim, **executed** — against the live
tree, against a `git archive HEAD` export, and against a third isolation tree I
built for the observation question. R1's work (the derived listener registry,
`hook_contains`, `combat_removal_committed`, the potions/powers predicates) is
attributed out and is not reviewed here; so are the other lanes' changes that
share the diff (`cards/breakthrough.py`, `powers.py`'s DarkEmbrace/RetainHand,
`monsters/**`, `events/**`, `rewards.py`, `run.py`, `driver.py`, `selectors.py`).

## Verdict: **NEEDS-FIXES**

The engine work is the best-derived change I have reviewed this round. The C#
is ported literally at every load-bearing point I checked; the two "hard
blockers" were correctly re-derived and the brief was correctly overruled on
both; the ADDENDUM's slot list was correctly overruled; the tests are real pins
and are RED on a clean HEAD. **I found no functional regression, and the fixes
are behaviour-preserving where they claim to be — I executed that, I did not
infer it.**

What forces NEEDS-FIXES is not code, it is a claim. **CONCERN 3's root cause is
wrong, and its measurement could not have established it.** §4/F8/the queue
annotation all attribute two trajectory-changing run-env divergences to R5's own
change through a named mechanism. I isolated them: they are 100% another lane's
`events/the_future_of_potions.py`, the shared run RNG is byte-identical up to
the differing step, and the named mechanism is impossible in that env. Since the
reviewer's/implementer's text is applied nearly verbatim to `GAP-QUEUE.md`, a
wrong root cause about the RL observation is exactly the residue this campaign
keeps paying for. The correct finding — which I established and which is
*stronger* than R5's — is in §5 RV-1.

Three smaller in-footprint items (RV-2, RV-3, RV-4) come with it.

---

## 1. Per-item verdicts

### 1. The pile itself — **CONFIRMED**

`PlayerCombatState.cs:60-68` declares five `CardPile`s; `:70-80` `AllPiles` is
`new CardPile[5] { Hand, DrawPile, DiscardPile, ExhaustPile, PlayPile }` —
**Play LAST**, verbatim; `:82` `AllCards => AllPiles.SelectMany(p => p.Cards)`.
`PileType.cs`: `None=0, Draw=1, Hand=2, Discard=3, Exhaust=4, Play=5, Deck=6`,
with Play's own doc comment ("a temporary pile that a card lives in while it's
mid-play, so that it isn't counted towards your hand or your discard pile").
`PileTypeExtensions.cs:35-42` `(uint)(pileType - 1) <= 4u` — Play IS a combat
pile.

Sim: `player.play_pile` (`player.py`), `all_cards` = the five piles with Play
last, `pile_type_of` a straight membership test with the `_playing_card`
short-circuit removed, `remove_from_current_pile` as the pile-agnostic verb.
`combat_card_db.ordered_piles` is five piles, Play last.

The listener walk enumerates it in C#'s position: `hooks._derive` splices
`hand, reversed(draw), discard, exhaust, play` on the `_riders == 0` fast path
and walks the same five in the per-card path, and the inactive-player `excluded`
leg covers `play_pile` too. R1's `_playing_card` stand-in is gone from
`hooks.py`. Pinned by `test_the_listener_walk_reads_the_real_play_pile` and by
R1's re-staged `test_a_card_mid_onplay_walks_in_the_play_slot_last`; both RED on
HEAD.

Two prose inaccuracies, not behaviour — see RV-7 (`all_cards`' draw-pile
orientation) in §5.

### 2. `_resolve_card_play` == `OnPlayWrapper`'s statement order — **CONFIRMED**

`CardModel.cs:1867-2005`, re-read in full. The sim's order is now:

| C# | sim |
|---|---|
| `:1875` `AddDuringManualCardPlay` / `:1879` `Add(this, Play, Bottom, null, …)` | `_add_to_play_pile(card)` — first statement |
| `:1890` `Hook.ModifyCardPlayResultPileTypeAndPosition(…, GetResultPileTypeForCardPlay(), …)` | `hooks.modify_card_play_result_pile(card, self._result_pile_type_for_card_play(card))` |
| `:1895` `GeneratePlayCount` | `hooks.modify_card_play_count(...)` |
| `:1896` `if (Owner.Creature.IsDead) return;` | `if self.player.is_dead: return` |
| `:1901-1970` `BeginCardOrPotionEffect` + loop + `finally` | `_play_count_loop` inside `with self._card_or_potion_effect()` |
| `:1976-1990` the Play-gated exit switch | `_move_to_result_pile_after_play` |
| `:1992` `CheckForEmptyHand` | `_check_for_empty_hand()` |

Entry-into-Play-before-OnPlay: **confirmed** (`:1875`/`:1879` are the wrapper's
first statements; `play_card` no longer pops the hand, `auto_play_card` no longer
pre-removes). This also fixes a real ordering bug I verified separately:
`PlayCardAction.cs:92` calls `_card.SpendResources()` — which fires
`Hook.AfterEnergySpent` at `CardModel.cs:1842` — **before** `OnPlayWrapper` at
`:102`, i.e. with the card still in Hand. The sim now matches.

The exit gate: `:1976-1977` `CardPile? pile = Pile; if (pile != null &&
pile.Type == PileType.Play)`. Sim: `if card not in self.player.play_pile:
return`. Same gate, exactly. Pinned by
`test_the_exit_is_a_no_op_when_an_effect_already_moved_the_card`, and that pin
is strong: with the gate removed the sim raises `ValueError` on
`play_pile.remove`, it cannot silently pass.

`GetResultPileTypeForCardPlay` (`:2070-2082`): `IsDupe || Type == Power ->
None`; `ExhaustOnNextPlay || Keywords.Contains(Exhaust) -> Exhaust`, **clearing
`ExhaustOnNextPlay` at `:2078`**; else Discard. The sim's
`_result_pile_type_for_card_play` is that, and because Python evaluates the
argument before the call, the consumption happens before the chain runs —
exactly C#'s argument-evaluation position. Pinned by
`test_exhaust_on_next_play_is_consumed_before_the_hook_chain` (RED on HEAD).

**Stranding.** I tried to construct one, by execution
(`scratchpad/strand.py`, six cases):

| case | sim result | C# |
|---|---|---|
| effect moves the card out of Play mid-OnPlay | exit no-ops, card where the effect put it | same (`:1977`) |
| entry refused (`is_over_or_ending`) | card stays in **hand**, exit no-ops | same (`:649-652` / `:312-319` + `:398-401`, both before any mutation) |
| lethal self-damage during OnPlay | card left in **play** | same (the `return` at `:1934` skips `:1976-1990`) |
| nested play (Cascade shape) | inner enters and leaves Play inside the outer's Play; `_playing_card` restored | same |
| exhaust / transform / return-to-hand from inside OnPlay | card leaves Play, exit no-ops | same |
| **combat ends during the play** | card moved to discard/exhaust | **C# leaves it in Play** — see RV-2 |

So: **a played card can never strand in Play through any path R5 introduced**,
and the brief's two HARD BLOCKERS are genuinely closed. The one *reverse*
divergence (the sim moves where C# strands) is RV-2. R5's §2 claim "with one
exception that is C#'s own" understates it by two: RV-2, and R5's own F6
(`_process_turn_end_cards`' death path, which I reproduced — CASE 5 leaves the
card in `play`).

### 3. The two hard-blocker rewrites — **CONFIRMED, and R5 is right that the brief was wrong**

`CorruptionPower.cs:27-38` is, in full: owner test → `(pileType, position)`;
`card.Type != Skill` → `(pileType, position)`; else `return (PileType.Exhaust,
position)`. **No pile-membership test and no `pileType != Discard` guard.** The
brief was wrong; R5 is right. `ReboundPower.cs:19-30`: owner test, then
`if (pileType != PileType.Discard) return (pileType, position);` — **one**
guard, not three. R5 is right again.

Both sim rewrites are literal. The removal of Rebound's `card.exhausts or
card.exhaust_on_next_play` re-test is correct *because* the chain is now seeded
with the real `GetResultPileTypeForCardPlay` answer, so an exhausting play
arrives as `"exhaust"` and C#'s single guard covers the abstention. Removal of
`card not in player.discard_pile` from both is correct: it is false for every
card once a resolving card lives in `play_pile`, i.e. both powers would have
silently stopped firing. That is the blocker, and it is closed.

**Consistency with the sibling lane: CONFIRMED, no conflict.** `R3-review.md`
§2 independently derived the same two facts and the same consequence — the
*pile* outcome is order-independent (Corruption always wins), the *stack* is
order-dependent, because `Hook.cs:1391-1406` adds a listener to `modifiers`
only `if (pileType3 != pileType2 || cardPilePosition2 != cardPilePosition)`, and
`ReboundPower.AfterModifyingCardPlayResultPileOrPosition` (`:32-39`) decrements
unconditionally once it is in that list. R5's fold of the tick into the modifier
call, gated on `pile == "discard"`, reproduces that exactly. Executed both
orders on the live tree:

```
corruption first -> exhaust=True draw=False discard=False rebound_amount=2   <- abstains, keeps its stack
rebound first    -> exhaust=True draw=False discard=False rebound_amount=1   <- credited, ticks
```

That is `Hook.cs:1401-1404` reproduced without the notification machinery. It
also **closes R3's residues 1–3**, which R3's review left LIVE /
BLOCKED-ON-FOOTPRINT on `power/corruption` and NEEDS-FIX on `power/rebound` —
see RV-5.

### 4. G8's manual-play dispatch — **CONFIRMED**; **CONCERN 1 is CORRECT and the deferral is protocol-correct**

`CardPileCmd.AddDuringManualCardPlay` (`:647-684`), statement for statement:
`IsOverOrEnding -> return` `:649-652`; `oldPile = card.Pile` captured at `:659`
**before** the move; `RemoveFromCurrentPile()` `:669`; `PileType.Play.GetPile(
…).AddInternal(card)` `:670` (raw insert, no per-card hook); one
`Hook.AfterCardChangedPiles(runState, combatState, card, oldPile?.Type ??
PileType.None, null)` at `:683`, **after** the move. `Add`'s own dispatch is
`:635`, same `oldPile?.Type ?? PileType.None`, same literal `clonedBy`.

`_add_to_play_pile` is that, and the argument pin is honest:
`test_the_manual_play_entry_fires_after_card_changed_piles` asserts both
`("round13_probe", "hand", None)` **and** that `pile_type_of(card) == "play"`
inside the listener — so it fails if the dispatch moves before the move, or
carries the wrong old pile, or is the exit dispatch instead. Verified RED on
HEAD (`IndexError`, no dispatch existed).

I also confirmed R5's claim that the manual and auto guards coincide, by reading
the code rather than the summary: `Add` returns at `:312-319` (`IsCombatPile &&
IsEnding`) and `:398-401` (`IsCombatPile && !IsInProgress`) — **both strictly
before** `RemoveFromCurrentPile` at `:496` and `AddInternal` at `:510`, so a
refused add leaves the card exactly where it was. That is what makes the shared
`_add_to_play_pile` legitimate.

**CONCERN 1 (F1) — RULING: the finding is CORRECT, and deferring was the right
call, but the stated reason is wrong.**

`CardCmd.Exhaust` (`CardCmd.cs:237-246`) is `await CardPileCmd.Add(card,
PileType.Exhaust, CardPilePosition.Bottom, null, skipVisuals)` at `:242`, and
`Add`'s tail dispatches `Hook.AfterCardChangedPiles` at `CardPileCmd.cs:635`,
before `History.CardExhausted` (`:243`) and `Hook.AfterCardExhausted` (`:244`).
So yes: **every exhaust in the game is an AfterCardChangedPiles site**, and the
sim's `ExhaustCmd.exhaust` dispatches none of them (14 direct `ExhaustCmd.
exhaust(` call sites inside `sts2_rl/`, more through the exit switch and the
Ethereal arm). It is step81's residue — `Add` is one C# method with many sim
entry points, and step81 wired three generated-card helpers and the per-card
draw, not `Add`. R5's enumeration and its exact-diff hand-off are both right.

The deferral is protocol-correct: PROTOCOL.md §Method says "when any site of a
mechanism remains unhandled, propose NARROWING instead of closing", and that is
what R5 did, with the diff spelled out. **But the reason given — "would add a
dispatch at ~30 sites in a tree three other lanes are live in" — is
overstated.** I grepped: `sts2_rl/` contains **zero** implementers of
`after_card_changed_piles` (the four ported C# listeners are Deck-filtered and
reach the sim through `Relic.after_card_added_to_deck`, a different shim). The
presence gate therefore returns False and the dispatch is a no-op everywhere.
The real reason to defer is the honest one: wiring `Add` faithfully means
`ExhaustCmd.exhaust` **and** `discard_and_draw`'s `:192` **and**
`discard_hand` **and** `add_to_hand`/`add_to_draw`, and landing two of those is
worse than landing none. Please put that reason in the queue instead.

### 5. step51 (Sly / `DiscardAndDraw`) — **CONFIRMED**

`CardCmd.DiscardAndDraw` (`:172-205`), statement for statement: `IsOverOrEnding
-> return` `:174-177`; `discardCards.Count == 0 -> return` `:179-182`; per card
collect `IsSlyThisTurn` `:188-191`, `CardPileCmd.Add(card, discardPile)` `:192`,
`History.CardDiscarded` `:193`, `Hook.AfterCardDiscarded` `:194` — **append
first, hook second**; the draw once for the batch `:197-200`; then
`AutoPlay(…, AutoPlayType.SlyDiscard)` per collected card `:201-204`. The sim's
`CardCmd.discard_and_draw` is that, and `hooks.before_card_auto_played` now
carries the `AutoPlayType` (`CardCmd.cs:122`).

The asymmetry is real and is fixed. HEAD's `potions.py` fired
`on_card_discarded` **before** the append; HEAD's `relics/gambling_chip.py`
appended first. C# appends first. `GamblersBrew.cs:27` and `GamblingChip.cs:21`
are both a single `CardCmd.DiscardAndDraw(picked, picked.Count)` call, so
neither should have open-coded it at all.

Pin quality: `test_gamblers_brew_routes_through_discard_and_draw` is a genuine
RED-to-GREEN pin (it asserts `card in discard_pile` inside the hook; HEAD
answered False). `test_gambling_chip_routes_through_discard_and_draw` **passes
on HEAD** — HEAD's gambling chip already appended-then-hooked and drew
afterwards, so `["discard", "draw"]` was already the answer. It is a legitimate
no-regression pin but the report lists it among step51's six pins without
saying so; nothing in it would fail if the reroute were reverted.

### 6. step56 (`PileIndexSort`) — **CONFIRMED, NARROWED is the right verdict**

`CardCmd.cs:353-360` compares `value1.Item2.Type.CompareTo(value2.Item2.Type)`
then `Item3` — raw `PileType` compare, so Draw(1) before Hand(2), which is *not*
`AllPiles` order. `Item3` is `pile.Cards.IndexOf(item.Original)` captured at
**`:396`**, before `RemoveFromCurrentPile()` at `:402`; the sort is applied at
`:405`. (The brief said `:391`, which is the `pile` capture, not the index —
R5's code and report both cite `:396` correctly but do not flag the brief's
slip.) `CardCmd._PILE_TYPE_ORDER` is the enum verbatim and the pin asserts
`d0, d1, h0, x0, e2, p0, k0`. No caller exists, so NARROWED is right. One nit:
RV-8.

### 7. step99 (`AutoPlayFromDrawPile`) — **CONFIRMED STALE; the parking claim needs a precision correction**

Verified against the committed tree, not the prose: the two-phase verb exists
and is a statement-for-statement port of `CardPileCmd.cs:931-966`. Phase 1 now
parks each pick in `play_pile` with a `"draw" -> Play` dispatch, which is
`:954`'s `await Add(cardModel, PileType.Play)`. The two new callers are real:
`Cascade.cs:24` and `DistilledChaos.cs:27` are each a single
`AutoPlayFromDrawPile(choiceContext, Owner, n, CardPilePosition.Top,
forceExhaust: false)` and were both open-coding it; `Havoc.cs:21` is the same
call with `forceExhaust: true`. Both open-coded loops also broke on
`combat.is_over` where `:958` breaks on `item.Owner.Creature.IsDead` alone.

**Precision correction, which the review brief also asks for.** The two-phase
split is what buys reshuffle immunity, and it bought it *already*: `Shuffle`
reads only `PileType.Draw` (`:870`) and `PileType.Discard` (`:871`), and HEAD's
phase-1 picks sat in a local list — in **no** pile — so they were immune too.
What the park in Play changes is not immunity but **visibility**: the parked
picks are now in `AllCards`, in `pile_type_of`, in the listener walk, and in
`combat_card_db.ordered_piles`. R5's §6 close note says exactly this ("it
matched the reshuffle immunity but not `AllCards`") and is right; the pin
(`test_auto_play_from_draw_pile_parks_every_pick_in_the_play_pile`, asserting
the first pick to resolve sees all three parked) tests the right thing. I flag
it only because the review question was phrased the other way round, and the
answer is "immunity was never the residue".

### 8. The ADDENDUM's IsDead early returns — **CONFIRMED; R5's correction of the brief is right**

`CardModel.cs` has exactly **five** `if (Owner.Creature.IsDead) return;` inside
`OnPlayWrapper`, at `:1896`, `:1932`, `:1940`, `:1950`, `:1960` — and all five
are `return`, so they skip the exit switch (`:1976-1990`) *and*
`CheckForEmptyHand` (`:1992`). The brief's "before `BeforeCardPlayed`" is wrong
(the pre-loop gate is `:1896`, after `GeneratePlayCount`, before
`BeginCardOrPotionEffect`), and the brief omits `:1960`. **R5 is right; R4's
review was right that a gate was missing and wrong about which.**

Sim: `:1896` between the play-count hook and the loop ✔; `:1932` immediately
after the card's `on_play` (and after the sim's `after_attack`, which models the
`AttackCommand` completing *inside* OnPlay — correct placement) ✔; `:1940` after
the enchantment leg ✔; `:1960` inside the `if not self.is_over:` block right
after `on_card_played` ✔; `:1950` has no sim counterpart (no ported affliction
has an `OnPlay`) and is named in a comment ✔. The "past the exit switch" half is
reproduced by the post-loop `if self.player.is_dead: return` in
`_resolve_card_play`. Pins are genuine: with the `:1932` gate removed
`on_card_played` fires (nothing else suppresses it — `is_over` is
`phase == COMBAT_OVER`, still false), and `test_the_play_count_gate_runs_before
_the_loop` fails without `:1896`.

### 9. The de-hacks — **CONFIRMED behaviour-preserving, against the C#, not the tests**

| removed | C# proof it was a workaround |
|---|---|
| `cascade.py`'s remove-self-from-discard + inline verb | `Cascade.cs:24` is one `AutoPlayFromDrawPile` statement; the self-exclusion is `Shuffle` reading only Draw+Discard (`:870-871`) while the card is in Play |
| `headbutt.py`'s `predicate=lambda c: c is not self` | `Headbutt.cs:29` is `CardSelectCmd.FromCombatPile(pile: PileType.Discard.GetPile(Owner), prefs: new CardSelectorPrefs(prompt, 1))` — **no predicate**; exclusion is structural |
| `trash_heap_cards.py` `StackCard`'s `sum(1 for c in … if c is not self)` | `Stack.cs:24` is `PileType.Discard.GetPile(card.Owner).Cards.Count()` — a raw count |
| `colorless_attacks.py`'s three-pile scan | `Bolas.cs`/`ThrummingHatchet.cs` test `pile == null \|\| pile.Type != Hand` then `Add(this, Hand)` from wherever; `remove_from_current_pile` is that verb over five piles, and the Hand guard is retained |
| `CorruptionPower` / `ReboundPower` | §1.3 above |
| both reshuffle hold-backs | `Shuffle` reads Draw + Discard only (`:870-871`); a card in Play is in neither |
| `ExhaustCmd.exhaust`'s "no fourth Play limbo case" docstring | premise dead; the fifth pile is now scanned, and the pin shows the double-membership bug it prevents |

Crucially, the four content de-hacks are pinned by tests that are **green on
both trees** (`test_headbutt_cannot_pick_itself_by_construction`,
`test_stack_counts_the_discard_pile_without_itself`,
`test_cascade_does_not_replay_itself`,
`test_corruption_sends_the_played_skill_to_the_exhaust_pile`,
`test_rebound_still_redirects_a_played_card_to_the_draw_top` — I ran the file on
the HEAD export and they pass there). That is the correct shape of evidence for
"behaviour-preserving", and it is what I was asked to confirm. One de-hack of
the same class was **missed** — RV-4.

### 10. CONCERN 3 (the RL observation) — **PARTLY OVERTURNED.** See RV-1; this is the headline finding of this review.

### 11. CONCERN 2 (`power/smoggy`, `power/ringing`) — **RULING: smoggy CONFIRMED; ringing CONFIRMED as "must re-derive", and I derived it**

`SmoggyPower.cs` re-read in full: `AfterCardPlayed` (`:22-37`) sweeps
`Owner.Player.PlayerCombatState.AllCards` and afflicts every unafflicted
**Skill**; `AfterCardEnteredCombat` (`:39-45`) afflicts ONE arriving card and
does not sweep; `AfterSideTurnEnd` (`:47-62`) sweeps `AllCards` to clear;
`ShouldPlay` (`:64-71`) blocks a Smog-afflicted card.

* **The entry is mis-filed.** Its issue text describes the `AfterCardPlayed`
  sweep and is keyed to `AfterCardEnteredCombat`, whose C# does not sweep at
  all. R5 is right.
* **The entry's stated exposure is factually wrong about the tree it was written
  against, not merely stale.** HEAD's `_resolve_card_play` appended every
  non-Power card to `discard_pile` *before* the play loop, so the resolving
  Skill **was** inside `all_cards` when `on_card_played` swept, and it **was**
  afflicted. I confirmed this by running the new pin against the HEAD export:
  `test_smoggy_afflicts_the_skill_that_is_mid_play` **passes on HEAD**. The
  record's consequence ("so it can be replayed by an effect that returns it to
  hand, where the game would block it") never held. R5's F2 is correct, and it
  is the more valuable half of this lane's findings after RV-1.

**`power/ringing` — re-derived, do not close by analogy, and it is NOT simply
false.** `RingingPower.__init__` (the sim's `AfterApplied` port) walks
`getattr(owner, "all_cards", ())` and afflicts **every** unafflicted card
regardless of type. On HEAD a *Power* card mid-play was in **no** pile (HEAD's
`_resolve_card_play` appended only `card_type != POWER`), so a Ringing applied
while a Power card resolved genuinely missed it, where C# has it in Play and
afflicts it. So:

* for non-Power cards the entry is wrong in the same way smoggy's is (they were
  in the discard, hence in `all_cards`);
* for a Power card mid-play the entry's exposure was **real** — narrow, and
  dormant for the recorded reason (Ringing is applied by an enemy on the enemy's
  turn), but real;
* either way it is now structurally closed by `all_cards` including `play_pile`;
* and it is mis-filed the same way — the issue describes `__init__`/AfterApplied
  while keyed to `AfterCardEnteredCombat`.

That is the derivation the record should carry instead of "same shape as
smoggy".

### 12. Tests — **CONFIRMED**, with two numeric corrections

Executed by me:

```
py -m pytest test/test_round13_play_pile.py -q
    -> 42 passed

py -m pytest <R5's 8 touched files + auto_play/powers/potions/combat_card_db/is_dead> -q
    -> 540 passed

py -m pytest test/test_conformance_*.py (the 10 replay-parity files) -q
    -> 95 passed, 6 xfailed

py -m pytest test/ -q --ignore=test/test_conformance_floor_state.py
    -> 3927 passed, 6 xfailed        (0 failed; R5 reported 3910 mid-wave)
```

**RED, re-measured against a clean `git archive HEAD` export** (I copied the pin
file into the export and ran it there): **31 failed, 11 passed**, not R5's
"33 failed / 9 passed". R5's baseline was the mid-work live tree, which already
carried other lanes' changes; the report does not say so. The RED evidence is
sound either way — 31 of 42 pins are genuinely RED on the committed tree — but
the number in the report is not reproducible from HEAD and should say what it
was measured against.

Spot-checks of the load-bearing pins (each: does it still pass with its
mechanism removed?):

* **stranding / exit no-op** — `test_the_exit_is_a_no_op_when_an_effect_already
  _moved_the_card`: cannot false-pass; without the gate the sim raises
  `ValueError`. Strong.
* **exit switch** — `test_the_exit_add_fires_after_card_changed_piles_from_play`
  asserts the exact two-element dispatch sequence `[("…","hand",None),
  ("…","play",None)]`; RED on HEAD (empty).
* **G8 dispatch args** — pins pile, `clonedBy is None`, *and* after-the-move
  ordering via `pile_type_of` inside the listener. Strong.
* **Sly ordering** — `…_appends_before_it_fires_the_hook` (RED on HEAD),
  `…_draws_before_it_auto_plays_the_sly_cards` (RED), `…_passes_the_auto_play
  _type` (RED). `test_gambling_chip_routes_through_discard_and_draw` is a
  no-regression pin, see §1.5.
* **IsDead slots** — `…stops_before_after_card_played` fails without `:1932`;
  `…play_count_gate_runs_before_the_loop` fails without `:1896`;
  `…still_dispatches` is the negative control. The one weakness is that the
  lethal case sets `player.hp = 0` directly rather than through `DamageCmd`, so
  it pins the gate mechanically rather than end-to-end. Acceptable.
* Weak-but-honest: `test_all_cards_puts_the_play_pile_last` also passes on HEAD
  (HEAD's discard parking produced the same order); `test_corruption_beats_a
  _draw_top_redirect` pins only one of the two orders — RV-10.

**The six re-staged legacy tests kept their intent and three of them are
strictly stronger.** `test_hook_order`'s reshuffle pin now also asserts
`discard_pile == []`; `test_tier1_residue`'s renamed pin adds `card not in
discard_pile`; `test_take_random_streams`'s transform pin now asserts the
replacement lands **in `play_pile`**, where the old form's stated conclusion
("there was no Play-pile gap here") really was an artefact of the stand-in.
Nothing was weakened to fit. `test_tiny_dispatchers`' spy now asserts the
`auto_play_type` value rather than just accepting the parameter. One caveat:
RV-9 (`test_pen_nib_tenth_attack_doubled`).

### 13. Protocol — **CONFIRMED**

* No `audit/records/**` or `audit/GAP-QUEUE.md` file appears in `R5-diff.txt`;
  the record modifications in the worktree belong to the controller and other
  lanes.
* No git index mutation is evidenced anywhere in the report or diff.
* Footprint: every engine file R5 claims is in the declared footprint.
  `cards/breakthrough.py`, `powers.py`'s DarkEmbrace/RetainHand, `monsters/**`,
  `events/**`, `rewards.py`, `run.py`, `driver.py`, `selectors.py`,
  `enchantments.py`, `relics/base.py`, `relics/vambrace.py`,
  `afflictions.py` in the same diff are other lanes'.
* **`relics/pen_nib.py` is untouched and is the only remaining `_playing_card`
  consumer** — I grepped the whole package; the two hits are both in
  `pen_nib.py`. The declared one-line debt is real: `PenNib.cs:120-128` is
  `if ((pile == null || pile.Type != PileType.Play) && AttacksPlayed == 9)
  return 2m;`, so `card not in player.play_pile` is the faithful predicate and
  `_playing_card` is now narrower. **That is the only debt R5 owes outside its
  footprint** — with one addition I found, RV-4.

---

## 2. Rulings on the three concerns, stated for the record

* **CONCERN 1 (G8 cannot fully close; `CardCmd.Exhaust` is an `Add` site).**
  **UPHELD.** `CardCmd.cs:242` → `CardPileCmd.cs:635`. G8 must be NARROWED, not
  closed. Deferral was correct; the *reason* in the report and the proposed
  queue line should be replaced (the hook has **zero** sim listeners, so the
  blast radius is not the issue — completeness across `Add`'s other sim entry
  points is).
* **CONCERN 2 (`power/smoggy`'s issue text is wrong, not stale; re-derive
  `power/ringing`).** **UPHELD on both counts**, and I supplied ringing's
  derivation in §1.11: it is wrong for non-Power cards and was *right* for a
  Power card mid-play.
* **CONCERN 3 (the RL observation is no longer byte-identical).**
  **UPHELD on the observation change; OVERTURNED on the root cause of the two
  trajectory-changing seeds, and the method could not have supported it.** See
  RV-1. The finding that replaces it is stronger, not weaker.

---

## 3. Record-close verdicts

Apply these; where I differ from R5 I have marked it.

**`creature_card_cmds` guard `N9` → `faithful`. APPROVE R5's close note as
written.** Its two replaced claims are accurately quoted from the record
("the limbo exclusion is parity-only"; "the remaining exposure … is not
demonstrated"), and both are now dead — the first because both hold-backs are
deleted and `Shuffle` reads Draw+Discard only (`CardPileCmd.cs:870-871`), the
second because `StackCard` now reads `len(ctx.player.discard_pile)` with no
filter and gets the game's number (`Stack.cs:24`).

**`creature_card_cmds` step 82 → `faithful`. APPROVE R5's close note**, with one
sentence added: *"The exit switch is ported with C#'s Play gate
(CardModel.cs:1976-1977) but WITHOUT `CardPileCmd.Add`'s IsEnding/!IsInProgress
refusals (:312-319, :398-401) or `CardCmd.Exhaust`'s `!IsOverOrEnding` wrapper
(CardCmd.cs:239), so a card that lands the killing blow leaves Play in the sim
where C# leaves it there. Dormant — every downstream command re-gates — but
recorded (R5-review RV-2)."*

**`creature_card_cmds` step 99 → `faithful` (stale close CONFIRMED).**
APPROVE R5's close note, **amend one clause**: replace "it matched the reshuffle
immunity but not `AllCards`" — which is right — but strike any implication that
the park *creates* the immunity. Suggested wording for the amended half:
*"Parking the picks in no pile already gave them reshuffle immunity, because
`CardPileCmd.Shuffle` reads only Draw and Discard (:870-871); what it did not
give them was membership of `AllCards`, `pile_type_of`, the listener walk and
`combat_card_db.ordered_piles`. Parking them in `PileType.Play` (:954) supplies
all four."* Keep the four-callers correction verbatim — `Cascade.cs:24` and
`DistilledChaos.cs:27` are each a single `AutoPlayFromDrawPile` statement and
were open-coding it.

**`creature_card_cmds` step 51 → `faithful` (machinery), DORMANT on content.**
APPROVE. Add: *"Pinned by five RED-to-GREEN tests plus one no-regression pin
(`test_gambling_chip_routes_through_discard_and_draw`, which HEAD already
satisfied)."*

**`creature_card_cmds` step 50 → `faithful` (upgrade from
`deliberate-divergence`).** R5 folds this into step51's note; give it its own
verdict. Close note: *"Closed 2026-08-01 (round 13, R5). The entry's premise —
`DiscardAndDraw`'s deferred draw 'has no sim counterpart because no ported card
uses the combined verb; the sim's discard-then-draw callers issue the two
separately, which is the ordering C# explicitly warns against for Sly' — is
retired: `CardCmd.discard_and_draw` is the combined verb (CardCmd.cs:172-205),
the draw is issued once for the batch after every `AfterCardDiscarded`
(:197-200), and both open-coded callers (Gambler's Brew, Gambling Chip) now
route through it."*

**`creature_card_cmds` step 56 → NARROWED, do not close.** APPROVE R5's note as
written. Add: *"The index is captured at :396 (the brief's :391 is the pile
capture); the sort runs at :405 over tuples whose removals happened at :402."*

**`creature_card_cmds` guard `G8` → NARROWED, do NOT close.** APPROVE the
verdict and the substance. **Replace the last sentence** of R5's note. Suggested:
*"Not landed here because a faithful `Add` wiring is not two lines at one site:
it is `ExhaustCmd.exhaust`, `CardCmd.discard_and_draw`'s :192,
`PlayerCombatState.discard_hand`, and the hand/draw add helpers, and wiring some
of them is worse than wiring none. Blast radius is not the constraint —
`sts2_rl/` has ZERO `after_card_changed_piles` implementers (the four ported
Deck-filtering listeners reach the sim through `Relic.after_card_added_to_deck`,
a different shim), so the dispatch is a presence-gate no-op today."*

**`power/smoggy` `AfterCardEnteredCombat` → `faithful`.** APPROVE R5's close
note. **Add the mis-filing correction as a first-class instruction**, not an
aside: *"The issue text describes SmoggyPower.cs:22-37 (`AfterCardPlayed`,
which sweeps `AllCards`) but is keyed to `AfterCardEnteredCombat`
(:39-45, which afflicts one arriving card and does not sweep). Re-key or
re-word."* And record the F2 lesson verbatim — the entry reasoned from "the sim
has no Play pile" to "therefore the resolving card is invisible" without
checking where the sim actually put it (the discard, i.e. inside `all_cards`);
`test_smoggy_afflicts_the_skill_that_is_mid_play` passes on HEAD.

**`power/ringing` `AfterCardEnteredCombat` → NARROWED / re-derived, not closed
by analogy.** Use §1.11's derivation: structurally closed by `all_cards`, but
the record's exposure was false for non-Power cards and **true** for a Power
card mid-play on the pre-round-13 tree, and the entry is mis-filed the same way
(it describes `__init__`/AfterApplied).

**New entries the controller should open** (from §5): RV-2 (the exit switch's
missing IsOverOrEnding refusals) and RV-4 (`cards/neows_fury.py`'s dead
`is not self` predicate). R5's own F3–F7 are all correct and should be queued as
written; I re-verified F3 (`CardModel.cs:1890` strictly precedes `:1895`) and F7
(`CardCmd.cs:114-116` fires only for `card.Pile == null`, and is reached *after*
the Unplayable/ShouldPlay/target checks at `:58-97`, so the refused-play path
never uses it — R5's "currently unreachable" is right).

---

## 4. Spec compliance and code quality

**Spec compliance: excellent.** Twelve C# methods re-derived, and every line
citation I checked resolved to the statement claimed. The two places the brief
and the R4 hand-off were wrong (Corruption/Rebound's guards; the IsDead slot
list) were both caught by reading the source rather than the prose, which is the
behaviour this campaign is trying to buy. `_add_to_play_pile`,
`_result_pile_type_for_card_play`, `_move_to_result_pile_after_play`,
`remove_card_from_combat` and `_move_to_result_pile_without_playing` are each a
transcription of one C# method with the citation in the docstring, and
`_resolve_card_play` is now readable side-by-side with `:1867-2005`.

**Code quality: good, with three prose defects.** Splitting the loop out into
`_play_count_loop` is what makes the four `return`s expressible without a flag,
and the `try/finally` around `_playing_card` is the right shape (F5 is a real
latent bug that nothing in the suite noticed — I reproduced the nesting case and
the mark is now restored correctly). The de-hack deletions leave the C# citation
behind in a comment in every case, which is the house style.

The defects are all documentation, and in this campaign that is not a free pass:
RV-3 (`modify_card_play_result_pile`'s dispatcher docstring now states the exact
opposite of what the change made true), RV-7 (`all_cards`' docstring overstates
the `AllPiles.SelectMany` equivalence), and the RED-count baseline in §5 of the
report. Round 12's recorded lesson is that records are wrong about their
*reasoning* more often than their verdicts; the same applies to docstrings that
outlive the code they describe.

---

## 5. My findings (these outrank the task's)

### RV-1 — CONCERN 3's root cause is wrong, and HEAD-vs-live could not have established it. **MUST FIX (report + queue text).**

R5's §4/F8 say: 7 of 30 run-env episodes diverge; 5 are the intended mid-play
observation; "**the other 2 (seeds 1 and 16) … Root cause: a shared-RNG
draw-count cascade, and it is the faithful direction.** `CombatState.select_cards`'
selectorless fallback draws from the RNG in proportion to the candidate list,
and Headbutt's and Neow's Fury's candidate lists are the DISCARD PILE, which no
longer contains the resolving card."

**The method cannot support that attribution.** `git diff --stat HEAD --
sts2_rl/` shows **29 changed engine files** from at least six lanes, including
`events/the_future_of_potions.py` (+119), `events/base.py` (+87),
`rewards.py` (+159), `run.py`, `driver.py`, `selectors.py`. A HEAD-vs-live
comparison measures the wave, not the lane.

**I isolated it.** Third tree: `git archive HEAD` export **plus only**
`sts2_rl/events/the_future_of_potions.py` and `sts2_rl/events/base.py` copied in
from live. Same scripted driver, same seeded uniform-over-legal policy, per-step
SHA-1 of the float32 observation, the action, a state snapshot, and a digest of
`run.rng.getstate()`.

```
seed 16, 107 steps:
  LIVE   vs HEAD    -> first divergence t=59 (REWARD_POTION vs MAP)
  TREE_C vs HEAD    -> first divergence t=59 (REWARD_POTION vs MAP)   <- identical divergence
  LIVE   vs TREE_C  -> IDENTICAL over all 107 steps, including run.rng state
```

30-seed sweep, same probe:

| comparison | identical episodes | what the rest are |
|---|---|---|
| LIVE vs HEAD | 23/30 (1,653 steps) | 7 seeds: 9, 11, 14, 16, 17, 18, 27 |
| TREE_C vs HEAD (**event lane alone**) | 28/30 | seeds **16 and 17** — the only two that change episode length and reward |
| LIVE vs TREE_C (**everything else, incl. R5**) | 25/30 (1,714 steps) | seeds 9, 11, 14, 18, 27 |

So the two trajectory-changing, reward-changing seeds (seed 16: reward 7.0 → 5.0)
are **entirely the event lane's**, and the shared run RNG is byte-identical up
to the step where the two trees are already on different screens.

**The named mechanism is also impossible here, on three independent counts:**

1. `cards/headbutt.py` and `cards/neows_fury.py` both passed
   `predicate=lambda c: c is not self`, and `CardSelectCmd.from_pile` applies the
   predicate before `select_cards` — so the candidate **list size** is `N-1` on
   both trees (HEAD: discard contained self, filtered out; live: self is in Play).
   Nothing about the RNG draw count changes.
2. `cards/neows_fury.py` is **unchanged in this diff** and still carries its
   predicate (RV-4).
3. The selectorless fallback is only reached when `combat.card_selector is None`.
   In the run env a selector is installed — the divergences I traced are at
   `DecisionKind.SELECT_CARDS`, i.e. the driver suspending on the screen — so
   `select_cards` never reaches `rng.sample` at all.

**The correct finding, which I verified and which is stronger than R5's.** R5's
change alters the observation **only at mid-play decision points and never
changes a trajectory.** All five remaining divergences (seeds 9, 11, 14, 18, 27)
have identical episode length, identical total reward, identical action
sequence, and differ in exactly two obs slots: the combat block's
`discard_pile_size` (`full_env.py:698`, Δ = 0.025 = exactly one card) and one
discard-composition slot (0.1 → 0.0). Combat env: **5/5 byte-identical**.
Ground truth at seed 27, step 5 — an Armaments upgrade screen suspended inside
`OnPlay`:

```
HEAD  hand ['defend','strike','strike']  discard ['strike','armaments']  play []
LIVE  hand ['defend','strike','strike']  discard ['strike']              play ['armaments']
```

That is `PileType.Play` (`PileType.cs:26-30`: "so that it isn't counted towards
your hand or your discard pile") and it is the game's own UI semantics. The
decision not to add Play to the observation vector is right; no schema bump, no
checkpoint migration, conformance parity green (95 passed / 6 xfailed, re-run by
me).

**Required:** rewrite §4's last bullet, F8, and the F8 queue annotation to say
this. The queue line should read something like: *"R5's Play pile changes the RL
observation ONLY at a decision point suspended inside `OnPlay` (a card-selection
screen): the resolving card is counted in `play` instead of `discard`, so the
combat block's discard-size and one discard-composition slot differ by one card.
Measured against a HEAD export with the concurrent event lane isolated out:
combat env 5/5 byte-identical; run env 25/30 episodes byte-identical and the
other 5 identical in length, reward and action sequence. No trajectory changes.
No schema change. Conformance parity green."*

### RV-2 — the exit switch omits C#'s combat-ending refusals. **SHOULD FIX (two lines, in footprint).**

`CardModel.cs:1979-1989`'s three arms are not unconditional moves in C#:

* `default: CardPileCmd.Add(this, resultPileType, resultPilePosition)` — `Add`
  returns at `:312-319` (`IsCombatPile && IsEnding`) and at `:398-401`
  (`IsCombatPile && !IsInProgress`), both **before** `RemoveFromCurrentPile`
  (`:496`) and `AddInternal` (`:510`);
* `case Exhaust: CardCmd.Exhaust(...)` — the whole body is inside
  `if (!CombatManager.Instance.IsOverOrEnding)` (`CardCmd.cs:239`);
* `case None: CardPileCmd.RemoveFromCombat(...)` — **no** gate (`:102-191`),
  which the sim matches.

`CombatManager.IsEnding` (`CombatManager.cs:180-201`) is true as soon as no
primary enemy is alive with nothing vetoing, i.e. **immediately after the
killing blow**, well before `CheckWinCondition`. So in C# the card that ends the
fight, and any card played while a loss is pending, **stays in the Play pile**
and fires neither `AfterCardChangedPiles` nor `AfterCardExhausted`.

Executed against the live tree (`scratchpad/strand.py`):

```
CASE 1 killing blow    -> pile_type_of: discard    (C#: play)
CASE 2 pending loss    -> pile_type_of: discard    (C#: play)
CASE 3 exhaust + kill  -> pile_type_of: exhaust    (C#: play)   + on_card_exhausted fired
```

**Not a regression** — HEAD parked the card in the discard at entry and its
exhaust leg was ungated too, so the end state is unchanged. And it is **dormant
in effect**: I checked the exhaust arm end-to-end with `FeelNoPainPower`
applied, and the block gain is 0 either way because `BlockCmd`/`DrawCmd`/
`DamageCmd` are each themselves `IsOverOrEnding`-gated (`player._draw`'s gate is
`CardPileCmd.cs:800-803`) — which is exactly why C# can afford to put the gate
one level up. What remains observable is the card's final pile at combat end and
two dispatches C# does not make. Worth fixing because R5's own
`_add_to_play_pile` already models this predicate for the entry, and because
`_move_to_result_pile_after_play` is presented as a literal transcription.

Fix (in `combat.py`, R5's footprint):

```python
        if result_pile == "exhaust":
            # `CardCmd.Exhaust`'s whole body is inside
            # `if (!CombatManager.Instance.IsOverOrEnding)` (CardCmd.cs:239),
            # so a card exhausting at the play's exit while the combat is
            # ending stays in Play.
            if self.is_over_or_ending:
                return
            ...
        # `CardPileCmd.Add` refuses a combat pile while IsEnding (:312-319) or
        # !IsInProgress (:398-401), both before the move — so does this.
        if self.is_over_or_ending:
            return
        self.player.play_pile.remove(card)
```

If it is not landed, it must be recorded on step 82 (wording in §3).

### RV-3 — the dispatcher docstring for the hook whose seeding changed is now false. **SHOULD FIX (one docstring, in footprint).**

`hooks.py:1126-1131`, unchanged by this lane:

> *"pile is `"discard"` by default; a listener may return `"draw_top"` … **Consulted only for cards that would land in the discard pile (exhausted cards and Powers never reach it).**"*

That is precisely the statement R5's change inverted: the chain is now seeded
with `"none"` for a Power and `"exhaust"` for an Exhaust-keyword card
(`CardModel.cs:1890`'s `GetResultPileTypeForCardPlay()` argument), and R5's own
`test_rebound_abstains_on_an_exhausting_play` depends on that. Corruption also
returns `"exhaust"` from a listener, which the docstring's "may return
`draw_top`" does not admit. Rewrite it to `CardModel.cs:1890` + `:2070-2082`.

### RV-4 — a ninth de-hack of the same class survives, and it is the one the report names. **RECORD as BLOCKED-ON-FOOTPRINT.**

`cards/neows_fury.py:66` still passes `predicate=lambda c: c is not self` into
`CardSelectCmd.from_pile(ctx.hooks, ctx.player.discard_pile, "from_discard", …)`.
`NeowsFury.cs:39` has no such filter; the exclusion is `PileType.Play`. The
predicate is now a permanent no-op, so this is **behaviour-neutral and not a
bug** — but it is one of the compensations R5's headline says it removed, it is
outside R5's footprint (`NOT yours: … other relics/cards`), and it is **not** in
§7's BLOCKED-ON-FOOTPRINT list, which claims `pen_nib.py` is the only debt. It
also sits oddly with the report naming Neow's Fury as a cause of the observation
cascade in a file it never touched. One-line removal, plus the same
`headbutt.py`-style docstring note.

### RV-5 — R5 closed a sibling lane's BLOCKED item and did not say so. **CONTROLLER ACTION.**

`R3-review.md` left `power/corruption/ModifyCardPlayResultPileTypeAndPosition`
**LIVE / BLOCKED-ON-FOOTPRINT** (powers.py was R5's this wave) with three named
residues, and prescribed the fix shape verbatim: *"teach
`modify_card_play_result_pile` an `"exhaust"` destination; branch on it in
`combat.py`'s post-loop move; delete `CorruptionPower.on_card_played`"*. R5
landed exactly that. R3 also marked
`power/rebound/ModifyCardPlayResultPileTypeAndPosition` **NEEDS-FIX** on the
guard and `…/AfterModifyingCardPlayResultPileOrPosition` **NEEDS-FIX** on the
tick's gate; R5's real chain seed removes both at the root, and R3's suggested
workaround (`card.exhausts or card.exhaust_on_next_play` re-test) is correctly
deleted rather than kept. Executed both power orders (§1.3): the sim now
reproduces C#'s order-independent pile and order-dependent stack. **All three
R3 entries can now close.** R5's report should cross-reference R3 the way it
cross-references R4.

### RV-6 — the RED baseline is not reproducible from HEAD. **FIX the number.**

Report: "33 failed, 9 passed (BEFORE)". Clean `git archive HEAD` export:
**31 failed, 11 passed**. The report should state that its RED run was against
the mid-work live tree (which is legitimate under the protocol's
no-revert rule) rather than against HEAD, and name the 11 no-regression pins
rather than 9.

### RV-7 — `all_cards`' new docstring overstates the equivalence.

`PlayerCombatState.all_cards` returns `hand + draw_pile + …` with the draw pile
in the sim's **bottom-first** order, while `AllCards` is
`AllPiles.SelectMany(p => p.Cards)` over a **top-first** `CardPile`
(`CardPile.cs`'s `MoveToTopInternal` = `Insert(0, …)`; `CardPileCmd.cs:843`
draws `FirstOrDefault()`). `hooks._derive` flips the draw pile for exactly this
reason; `all_cards` does not. Pre-existing, unobservable today (Smoggy and
Ringing afflict unconditionally, and `CardCmd.afflict` draws no RNG), but the
new docstring now asserts `all_cards` **is** `AllPiles.SelectMany(...)` "in
their declared order", which is not true of the draw leg. Either flip it or
qualify the docstring.

### RV-8 — `pile_index_sort_key` swallows an unknown pile name.

`CardCmd._PILE_TYPE_ORDER.get(pile_name, 0)` maps anything unrecognised to
`PileType.None`. `CardCmd.cs:392-395` **throws** on a null pile
(`"Can't transform … because it has no pile"`). The whole point of landing the
key with no caller is that a future batch transform inherits the right
semantics; a silent 0 is the wrong default for that. Prefer `[pile_name]` and
let it `KeyError`, per note N4's loud-failure idiom.

### RV-9 — the pen-nib pin can no longer detect the footprint debt.

`test_relics.py::test_pen_nib_tenth_attack_doubled` now sets **both**
`play_pile` and `_playing_card`, so it passes whichever predicate `pen_nib.py`
reads. R5 documents this in the test comment, which is honest, but it means the
pin will stay green whether the §7 one-liner is landed, mis-landed, or never
landed. Whoever pays that debt must drop the `_playing_card` half in the same
change — worth stating in the queue line for §7.

### RV-10 — the Corruption/Rebound order pin covers the wrong order.

`test_corruption_beats_a_draw_top_redirect` applies Rebound then Corruption,
which pins the *pile*. The order that pins the **stack** — Corruption first, so
Rebound sees `"exhaust"`, abstains, and is not in `Hook.cs:1401-1404`'s
`modifiers` list — is unpinned, and it is the half R3's review called out as the
live residue. I executed it and the sim is correct (`rebound_amount=2` when
Corruption is applied first, `1` when Rebound is). Four-line pin; please add it.

---

## 6. What I ran

```
py -m pytest test/test_round13_play_pile.py -q                      -> 42 passed
py -m pytest <8 touched files + 5 blast-radius files> -q            -> 540 passed
py -m pytest test/test_conformance_{combat,determinism,player_state,
    rooms,runner,save,recording,map,pools,relic_bag}.py -q          -> 95 passed, 6 xfailed
py -m pytest test/ -q --ignore=test/test_conformance_floor_state.py -> 3927 passed, 6 xfailed
# RED check, clean HEAD export (git archive HEAD | tar -x)
py -m pytest test/test_round13_play_pile.py -q  [in the export]     -> 31 failed, 11 passed
```

Scripts written to the scratchpad (not to the repo): `obs_probe.py`,
`obs_probe2.py`, `rngtrace.py`, `cmp.py`, `cmp2.py`, `trace.py`, `midplay.py`
(the RL observation isolation), `strand.py` (the six stranding constructions),
`corr.py` (both Corruption/Rebound orders), `fnp.py` (RV-2's liveness). Trees
built under the scratchpad: `head_export` (`git archive HEAD`) and `treeC`
(HEAD + the event lane's two files). Nothing was reverted in the live tree and
no git index command was run.

---

# Re-review (2026-08-01) — after the R5 fix pass

Everything below was re-derived and re-executed against the **final** tree. My
engine verdicts in §1 and the CONCERN-3 isolation in RV-1 stand unchanged; one
of my own ratings does not.

## Verdict: **APPROVED**, with one required text amendment (item 4) and one recommendation (item 8).

---

### 1. RV-2 dormancy — **REFUTED. I withdraw the rating; the lane is right.**

**The C#.** `JossPaper.CardsExhausted` is a `[SavedProperty]`
(`JossPaper.cs:60-76`), incremented from `AfterCardExhausted` (`:105-112`).
`AfterCombatEnd` (`:143-147`) clears **`EtherealCount` only**. The single place
`CardsExhausted` ever decreases is `%= ExhaustAmount` inside
`DrawIfThresholdMet` (`:132`) — so it is run-scoped, save-persisted, and an
over-count is not merely wrong once: because it is reduced modulo 5 rather than
reset, it permanently shifts the phase of every future fifth-exhaust draw for
the rest of the run.

**Executed A/B** (`scratchpad/joss.py` — an exhausting card whose OnPlay lands
the killing blow, Joss Paper equipped):

```
LIVE   joss.cards_exhausted 0 -> 0   card pile=play
HEAD   joss.cards_exhausted 0 -> 1   card pile=exhaust
C#     CardCmd.Exhaust body skipped at :239 -> no AfterCardExhausted,
       CardsExhausted unchanged, card stays in Play
```

**And it is worse than one relic.** I ran the enumeration my rating should have
had — all nine `on_card_exhausted` definitions in `sts2_rl/`:

| listener | pre-fix behaviour on an ending combat | observable? |
|---|---|---|
| `relics/joss_paper.py` | `cards_exhausted += 1` | **YES — run-scoped, permanent, phase-shifting** |
| `relics/forgotten_soul.py` | `combat_rng.targets.choice(living)` + `DamageCmd.deal` | **YES** — on the pending-loss path (enemies alive) it dealt real damage **and** burned an RNG draw |
| `history.py` | appends `CardExhaustedEntry` | **YES** — a history entry C# never records |
| `relics/burning_sticks.py` | sets `_used_this_combat = True` before the gated add | yes, combat-scoped |
| `powers.py` FeelNoPain / DarkEmbrace, `relics/charons_ashes.py` | re-gate downstream | no |
| `cards/drum_of_battle.py` | `card is not self` guard | no |

Executed, pending-loss path (`scratchpad/fsoul.py`):

```
LIVE  pile=play      enemy hp [56] -> [56]   history CardExhausted entries=0
HEAD  pile=exhaust   enemy hp [56] -> [55]   history CardExhausted entries=1
```

So my claim was wrong twice over. It was wrong about counters — the lane's
"commands re-gate; counters do not" is exactly right — and it was wrong about
*commands* too, because `DamageCmd`'s gate is `is_over` (`phase ==
COMBAT_OVER`), not `is_over_or_ending`, so Forgotten Soul's damage went through
as well. **My error, named:** I generalised from two probes (FeelNoPain via
`BlockCmd`, DarkEmbrace via `DrawCmd`) to "every downstream command re-gates".
That is a sample, not an enumeration — precisely what PROTOCOL.md's Method
section forbids for a dormancy verdict ("ask *what else reads this*, not *does
the recorded consumer still hold*"). A reviewer's dormancy rating is as unsafe
as an implementer's, and this one was reached the same way round 12's
overturned verdicts were.

**Consequence for the record.** Step 82's close note must carry LIVE wording,
not the dormant sentence I proposed in §3 above. Replace it with:

> *The exit switch is ported with C#'s Play gate (CardModel.cs:1976-1977) AND
> with the combat-ending refusals its arms carry: `CardPileCmd.Add`'s
> `IsCombatPile && IsEnding` (:312-319) and `!IsInProgress` (:398-401), and
> `CardCmd.Exhaust`'s `!IsOverOrEnding` wrapper (CardCmd.cs:239), the latter
> placed in `ExhaustCmd.exhaust` where C# puts it. This was a LIVE divergence,
> not a cosmetic one: `JossPaper.CardsExhausted` is a `[SavedProperty]`
> (JossPaper.cs:60-76) that `AfterCombatEnd` (:143-147) does not clear, so
> every fight ending on an exhaust over-credited a RUN-scoped counter by one
> and, because `DrawIfThresholdMet` reduces it `%= 5` (:132), permanently
> shifted the phase of every later draw; `ForgottenSoul` additionally dealt
> real damage and burned a `CombatTargets` RNG draw on the pending-loss path,
> and `CombatHistory` recorded a `CardExhaustedEntry` the game never records.
> A legacy test was asserting the divergence — `test_ironclad_cards.py::
> TestFeed::test_fatal_grants_max_hp_and_heals` pinned Feed landing in the
> exhaust pile on the killing blow — and has been re-staged onto the C# truth.*

### 2. The legacy test that was asserting the divergence — **CONFIRMED, no coverage lost**

`Feed.cs:26` declares `CardKeyword.Exhaust`; its `OnPlay` (`:35-44`) lands the
kill and grants the max HP *inside* OnPlay, before the exit; `IsEnding`
(`CombatManager.cs:180-201`) is therefore true when the wrapper reaches
`:1984`, and `CardCmd.cs:239` skips the whole body. The game leaves Feed in
Play.

The re-staged assertion is **strictly stronger**, not weaker: the old single
`assert card in cs.player.exhaust_pile` is replaced by a *pair* —
`assert card in cs.player.play_pile` **and** `assert card not in
cs.player.exhaust_pile` — so the test now fails if the card is in the exhaust
pile, in the discard, or nowhere. The `max_hp == 83` / `hp == 73` /
`enemy.is_dead` assertions are untouched, so Fatal's own coverage is intact.
This is the cleanest instance this round of the campaign's recorded failure
mode: a green suite that was green *because* a test pinned the bug.

### 3. The single-choke-point argument — **CONFIRMED by exhaustive grep**

`grep -rn "PileType\.Exhaust" src/ --include=*.cs` returns 24 hits. Exactly one
is an add: `CardCmd.cs:242`. The rest are reads or plumbing —
`AshenStrike.cs:22` and `KnifeTrap.cs:25,36` count `GetPile(...).Cards`,
`PlayerCombatState.cs:66` declares the pile and `:76` lists it in `AllPiles`,
`CardPile.cs:51` is `CardPile.Get`'s switch, `CombatManager.cs:931` is
`HandlePlayerDeath`'s five-pile `RemoveFromCombat` sweep, the remainder is
UI/net/serialisation. There is no `ExhaustPile.AddInternal` anywhere.

So `CardCmd.Exhaust` really is the sole gateway, the gate belongs in
`ExhaustCmd.exhaust`, and one statement covers all **14** sim call sites. The
placement is doubly correct: even if a caller bypassed it, `CardPileCmd.Add`
would refuse on its own (`:312-319`, `:398-401`).

### 4. CONCERN 3 as rewritten — **correct on the run env; ONE SENTENCE IS NOW STALE and must be amended**

I re-measured from scratch with my own probe on all three trees against the
final tree (see the probe-collision note below):

```
run env, 30 seeds, same probe both sides
  FINAL vs HEAD    : 23/30 identical   (9, 11, 14, 16, 17, 18, 27 differ)
  FINAL vs TREE_C  : 25/30 identical   (9, 11, 14, 18, 27 - each identical in
                                        length, reward AND action sequence)
  FINAL vs the pre-fix-pass live tree : 30/30 identical, 1,853 steps
combat env, 5 seeds
  FINAL vs HEAD    : 2/5 identical     (seeds 0, 2, 3 differ)
```

The run-env half is **exactly right** — my numbers reproduce the lane's seed for
seed, the two trajectory-changing seeds are 100% the event lane, and the
residual five never change a trajectory. The three impossibility arguments hold
(I had derived the candidate-list one analytically; the lane executed it, and
`driver.py:320`'s selector installation confirms the third).

**But "combat env ... 5/5 byte-identical, all three" is now false — the lane's
own RV-2 fix made it false.** It was true when I measured it before the fix
pass; it is 2/5 after. The three differences are confined to the **terminal
observation** of an episode and have the identical two-slot shape:

```
seed 0, terminal row   HEAD  discard [bloodletting, strike, strike, whirlwind]  play []
                       FINAL discard [bloodletting, strike, strike]             play [whirlwind]
seed 2, terminal row   HEAD  discard [..., defend, strike]                      play []
                       FINAL discard [..., defend]                              play [strike]
seed 3, terminal row   HEAD  discard [strike, bloodletting, whirlwind]          play []
                       FINAL discard [strike, bloodletting]                     play [whirlwind]
```

That is the `default:` arm's new `IsEnding` refusal (`CardPileCmd.cs:312-319`)
doing exactly what C# does — the card that ends the fight stays in Play — so
this is the fix being *correct*, not a defect. Episode lengths, rewards and
action sequences are identical in all five seeds; every pre-terminal row is
byte-identical (verified separately with a full-vector dump: 12/14/16
pre-terminal rows, zero differing slots).

**Required amendment**, one sentence, replacing "combat env 5/5":

> *Combat env: every pre-terminal observation is byte-identical on all three
> trees; the TERMINAL observation of a combat that ends on a card play now
> differs on 3 of 5 seeds, in the same two slots and by the same one card,
> because `CardPileCmd.Add`'s IsEnding refusal (:312-319) leaves the winning
> card in Play where the sim used to discard it. Rewards, episode lengths and
> action sequences are unchanged. Practically invisible to training: it is the
> observation of a `terminated=True` step, which PPO/GAE never bootstraps from;
> it would matter only to an algorithm that consumes final observations (a
> replay buffer storing `next_obs`, or a truncation-bootstrap path).*

Two further results worth folding, both mine:

* **The entire fix pass is observation-neutral in the run env** — FINAL vs the
  pre-fix-pass live tree is 30/30 identical over 1,853 compared steps. The only
  observation RV-2 moves is the combat env's terminal row.
* **Probe-collision caution for the controller.** The lane's scratchpad
  `cmp.py` and its `*_run.json` outputs overwrote mine (same filenames,
  different terminal-row convention), which briefly produced a spurious uniform
  "+1 step per episode". I regenerated every tree's data with a single probe
  before drawing any conclusion. The two probes agree step-for-step once the
  terminal row is treated consistently — but their JSON is **not**
  interchangeable, and nobody should compare one lane's dump against another's.

### 5. CONCERN 1's corrected reason — **CONFIRMED on both counts**

`grep -rn "ExhaustCmd\.exhaust(" sts2_rl/ --include=*.py` gives **14**, across
12 files (`brand`, `burning_pact`, `cinder`, `colorless_skills`, `fiend_fire`,
`second_wind`, `stoke`, `thrash`, `true_grit`, `relics/paels_eye` one each;
`combat.py` twice; `potions.py` twice). My "~30" in the first review repeated
the report's figure without checking it — 14 is right. And
`grep -rn "def after_card_changed_piles" sts2_rl/` returns only the dispatcher:
**zero implementers**, so the presence gate makes the missing dispatches a
no-op today. G8 stays NARROWED for the completeness reason, which is the
correct one.

### 6. RV-3, RV-4, RV-7, RV-8, RV-9, RV-10 — **all landed and verified**

* **RV-3** — `modify_card_play_result_pile`'s docstring now states the three
  seeds, cites `:1890` / `:2070-2082`, and explicitly retracts the old sentence.
* **RV-4** — `neows_fury.py`'s predicate is deleted and pinned
  (`test_neows_fury_cannot_pick_itself_by_construction`, an invariance pin).
* **RV-7** — not flipped, but corrected with a real enumeration of every
  `all_cards` consumer and the condition under which flipping becomes
  necessary. Better than flipping blind; I agree with the call.
* **RV-8** — `_PILE_TYPE_ORDER[pile_name]`; `.get` and the `None` key are gone,
  with the right C# justification (`CardCmd.cs:392-394` throws before `:396`).
* **RV-9** — the pen-nib debt is **paid**, not re-declared: `pen_nib.py` now
  reads `card not in play_pile`, which is `PenNib.cs:120-128`'s
  `pile == null || pile.Type != PileType.Play` in full, and the pin no longer
  sets `_playing_card` so it can discriminate. R5 now owes no
  BLOCKED-ON-FOOTPRINT item.
* **RV-10** — both orders pinned; I re-executed both and the sim matches
  `Hook.cs:1401-1404`.

### 7. The three sibling-lane (R3) entries — **true as written; closing them here is CORRECT, not presumptuous**

I re-read all three C# methods and re-executed both application orders. The
close text is accurate in every particular, including the residue-by-residue
accounting for Corruption and the "verdict unchanged, mechanism replaced"
framing for the two Rebound entries.

Record-state check, so the controller applies it the right way: the live
records currently read `power/corruption/ModifyCardPlayResultPileTypeAndPosition
= gap` and both `power/rebound` entries `= faithful`. That matches the text
exactly — (a) is a verdict change gap to faithful, (b) and (c) are close-note
replacements with the verdict untouched.

Not presumptuous, for three reasons: R3's lane is complete and its review
predates these fixes; R3 itself marked the Corruption entry
BLOCKED-ON-FOOTPRINT precisely because `powers.py` belonged to another lane
this wave; and R5 proposes text rather than editing records, which is what the
protocol asks for. The one thing the controller should confirm is that no R3
follow-up is concurrently rewriting those entries.

### 8. F12 — is deleting `_playing_card` safe? **Yes, with one condition.**

Verified by grep over `sts2_rl/` and `test/`: the only non-comment occurrences
are `player.py:170`'s declaration and `combat.py:1060-1066`'s save/set/restore.
`pen_nib.py` now reads `play_pile`; `pile_type_of` no longer tests it;
`hooks._derive` no longer uses it; `test_relics.py:806` deliberately no longer
sets it. **Zero functional readers**, so removing it cannot change behaviour and
the tests would not notice either way — which is the reason to be careful about
*how* it is removed, not whether.

**Condition.** It is the sim's only handle on a fact `play_pile` genuinely
cannot express — "the card whose `OnPlayWrapper` is on the stack" — whose C#
counterpart is `choiceContext.PushModel(this)` / `PopModel(this)`
(`CardModel.cs:1869` / `:2004`), a *stack*, not a slot; `play_pile` cannot
express it because `AutoPlayFromDrawPile` parks several picks at once and a
nested play leaves two cards in Play. Deleting the field is fine; deleting F5's
lesson with it is not. Whichever way the lane goes, the queue must carry:
*"`_playing_card` was a single slot cleared at the tail, so a nested play
(Cascade, Havoc, Mayhem, Distilled Chaos, Beat Down, Catastrophe, Hellraiser,
Stampede, Whispering Earring, the Imbued enchantment) wiped the outer card's
mark for the rest of its own play, and nothing in the suite noticed. If a later
port needs 'the card whose wrapper is on the stack' — C#'s PushModel/PopModel
stack, CardModel.cs:1869/:2004 — it must be re-derived as a save/restore stack,
never as a single slot, and never as `play_pile` membership."*
My preference is delete-and-record; keeping it costs one attribute and is
equally defensible.

### 9. Tests — **CONFIRMED by execution**

```
py -m pytest test/test_round13_play_pile.py -q                      -> 54 passed
[clean git-archive HEAD export, same file]                          -> 41 failed, 13 passed
py -m pytest test/test_conformance_*.py (10 replay-parity files) -q -> 95 passed, 6 xfailed
py -m pytest test/ -q --ignore=test/test_conformance_floor_state.py -> 3939 passed, 6 xfailed, 0 failed
```

54 pins and 41/13 both reproduce exactly. The 13 that pass on HEAD are named
correctly in the report and none is a defect: twelve are de-hack *invariance*
pins, which is the required shape of evidence for "behaviour-preserving" — a
pin that must be green on both trees is doing its job.

The thirteenth is the one item 9's rule is aimed at, and the lane found it
before I did and said so plainly:
`test_corruption_first_makes_rebound_abstain_and_keep_its_stack` passes on HEAD
**by accident of listener order**, not because HEAD reproduced
`Hook.cs:1401-1404` — on HEAD both powers were `on_card_played` handlers,
Corruption moved the card out of the discard first, and Rebound then failed its
own `card in discard_pile` test. It does not discriminate on its own. Its
mirror, `test_rebound_first_is_credited_and_ticks_even_though_corruption_wins`,
is genuinely RED, and the pair brackets the behaviour, so the coverage is
sound. Self-reporting a non-discriminating pin is the right handling; I would
only add a one-line note in the test itself so a future reader does not mistake
it for a discriminating pin.

### 10. Standing items from the first review

Section 1's engine verdicts (the pile, the wrapper's statement order, the two
hard blockers, G8's dispatch, step 51/56/99, the IsDead slots, the de-hacks) and
RV-1's isolation all stand unchanged and re-verified against the final tree.
Nothing in the fix pass weakened them.
