# R5 report — the Play pile (`creature_card_cmds` N9 + step82 + G8's last site, step99, step51, step56, `power/smoggy`)

Lane: R5, round 13. Worktree `c:\Users\Perry\Desktop\sts2-rl-tier2`.
Spec: decompiled C# at `c:\Users\Perry\Desktop\Slay the Spire 2`, non-ascension.

## Headline

`PlayerCombatState` has a fifth pile. `player.play_pile` is a real list, it is
the LAST entry of `all_cards`, and a card being played physically sits in it
for the whole of `OnPlayWrapper` — `CardModel.cs:1867-2005`. Everything the sim
used to do to fake that (park the card in the DISCARD pile, mark it
`_playing_card`, then subtract it back out at each reader) is gone, along with
all five of the card-level de-hacks that compensated for it.

Verdicts:

| entry | verdict |
|---|---|
| `creature_card_cmds/N9` (the guard) | **FIXED** |
| `creature_card_cmds/step82` (AddDuringManualCardPlay) | **FIXED** |
| `creature_card_cmds/G8` (AfterCardChangedPiles) | **NARROWED, not closed** — the manual-play site is wired; a site the record's own enumeration missed is not (§8, F1) |
| `creature_card_cmds/step99` (AutoPlayFromDrawPile) | **STALE-ALREADY-FIXED, confirmed**, and its one residue is now closed too |
| `creature_card_cmds/step51` (Sly / DiscardAndDraw) | **FIXED (machinery)**, dormant on content |
| `creature_card_cmds/step56` (PileIndexSort) | **NARROWED** — the key is ported and pinned; there is still no multi-card transform to apply it to |
| `power/smoggy` `AfterCardEnteredCombat` | **FIXED structurally**, and the entry's stated exposure **never reproduced** (§8, F2) |

Two findings outrank the fixes and are in §8: **F1**, `G8` cannot close fully
because `CardPileCmd.Add` is an AfterCardChangedPiles site that the sim reaches
from ~30 places that do not dispatch it; and **F2**, `power/smoggy`'s issue text
is factually wrong about the tree it was written against.

---

## 1. Per-entry verdicts

### N9 + step82 — the Play pile — **FIXED**

**C#, re-derived (not taken from the brief).**

* `PileType.cs`: `None=0, Draw=1, Hand=2, Discard=3, Exhaust=4, Play=5,
  Deck=6`. `PileTypeExtensions.IsCombatPile` is `(uint)(pileType - 1) <= 4u`
  (`PileTypeExtensions.cs:35-42`) — so Play IS a combat pile.
* `PlayerCombatState.cs:68` `public CardPile PlayPile { get; } = new
  CardPile(PileType.Play);`; `:70-80` `AllPiles` is
  `new CardPile[5] { Hand, DrawPile, DiscardPile, ExhaustPile, PlayPile }`
  (Play LAST); `:82` `AllCards => AllPiles.SelectMany(p => p.Cards)`.
* ENTRY, manual: `CardPileCmd.AddDuringManualCardPlay`
  (`CardPileCmd.cs:647-684`) — `IsOverOrEnding -> return` (`:649-652`),
  `oldPile = card.Pile` captured at `:659` BEFORE the move,
  `card.RemoveFromCurrentPile()` `:669`, `PileType.Play.GetPile(...).
  AddInternal(card)` `:670` (a raw insert, no per-card hook), then the ONE
  dispatch at `:683`: `Hook.AfterCardChangedPiles(runState, combatState, card,
  oldPile?.Type ?? PileType.None, clonedBy: null)` — AFTER the move.
  Called from `CardModel.cs:1875`, the FIRST statement of `OnPlayWrapper`.
* ENTRY, auto: `CardModel.cs:1879` `CardPileCmd.Add(this, PileType.Play,
  CardPilePosition.Bottom, null, skipCardPileVisuals)`. `Add`'s dispatch is
  `CardPileCmd.cs:635`, same `oldPile?.Type ?? PileType.None`, same literal
  null `clonedBy`. Its refusals are `IsCombatPile && IsEnding -> success:false`
  (`:312-319`) and `IsCombatPile && !IsInProgress -> return` (`:398-401`) —
  **together exactly `IsOverOrEnding`**, i.e. the same guard the manual entry
  states in one line. That is why the sim has one `_add_to_play_pile` for both.
* ENTRY, refused play: `CardCmd.MoveToResultPileWithoutPlaying`
  (`CardCmd.cs:133-137`) is `CardPileCmd.Add(card, PileType.Play)` then
  `card.MoveToResultPileWithoutPlaying(...)`.
* ENTRY, turn-end-in-hand: `CardModel.OnTurnEndInHandWrapper`
  (`CardModel.cs:1682-1698`) opens with `CardPileCmd.Add(this, PileType.Play)`
  (`:1684`); its own doc comment says so at `:1673` ("While this method is
  being run, this card will be in the Play pile"), then Ethereal ->
  `CardCmd.Exhaust(causedByEthereal: true)` (`:1692`) else
  `CardPileCmd.Add(this, PileType.Discard)` (`:1696`).
* EXIT: `CardModel.cs:1976-1991`, gated —
  `CardPile? pile = Pile; if (pile != null && pile.Type == PileType.Play)`
  then `switch (resultPileType)`: `None -> CardPileCmd.RemoveFromCombat`,
  `Exhaust -> CardCmd.Exhaust`, `default -> CardPileCmd.Add(this,
  resultPileType, resultPilePosition)`.
* `GetResultPileTypeForCardPlay` (`CardModel.cs:2070-2082`):
  `IsDupe || Type == Power -> None`; `ExhaustOnNextPlay ||
  Keywords.Contains(Exhaust) -> Exhaust`, **consuming `ExhaustOnNextPlay` on
  the spot at `:2078`**; else `Discard`. It is evaluated as the
  `defaultPileType` ARGUMENT of `Hook.ModifyCardPlayResultPileTypeAndPosition`
  at `:1890`.
* `CardPileCmd.Shuffle` (`CardPileCmd.cs:864-919`) reads `PileType.Draw`
  (`:870`) and `PileType.Discard` (`:871`) and nothing else. That is the whole
  of "a card mid-play is not reshuffled".
* `MoveToResultPileWithoutPlaying` (`CardModel.cs:2089-2107`) is gated the same
  way (`:2092`), and its None arm is `IsDupe` ALONE — which is what its doc
  comment at `:2086-2087` means by "Power cards do not get sent to Limbo, and
  instead get sent to the discard".

**Sim diff.**

* `player.py`: `play_pile` added; `all_cards` is now the five piles with Play
  last; `pile_type_of` is a straight five-pile membership test (it used to test
  `_playing_card` FIRST, because a resolving card was genuinely in two piles at
  once); new `remove_from_current_pile(card) -> old pile name | None`, the
  `CardModel.RemoveFromCurrentPile` verb every ad-hoc four-pile scan was
  approximating; BOTH reshuffle hold-backs deleted from
  `reshuffle_discard_into_draw` and `shuffle_draw_and_discard`.
* `combat.py`: new `_result_pile_type_for_card_play`, `_add_to_play_pile`,
  `_play_count_loop`, `_move_to_result_pile_after_play`,
  `remove_card_from_combat`. `_resolve_card_play` is now the wrapper's
  statement order: entry -> result-pile hook -> play-count hook -> IsDead gate
  -> loop -> exit switch -> `CheckForEmptyHand`.
  `play_card` no longer pops the hand and `auto_play_card` no longer
  pre-removes the card from its pile — the entry move does it, which is what
  makes `oldPile` available to the G8 dispatch at all.
  `_move_to_result_pile_without_playing` gained the Play add, the Play gate and
  the `IsDupe` arm. `_process_turn_end_cards` parks the card in Play.
* `cmds.py`: `ExhaustCmd.exhaust`, `CardCmd.afflict` and
  `CardCmd.transform_to_random` all see the fifth pile;
  `CardPileCmd.auto_play_from_draw_pile` parks its phase-1 picks in it.
* `hooks.py`: `_derive`'s Play leg walks `player.play_pile` instead of
  `player._playing_card` (both the `_riders == 0` fast path and the per-card
  path), and the `excluded` leg for an inactive player covers it too.
* `combat_card_db.py`: `ordered_piles` is five piles, Play last.

**`_playing_card` was kept, deliberately, and narrowed.** It is no longer a
Play-pile stand-in; it names "the card whose `OnPlayWrapper` is on the stack",
which the pile genuinely cannot express (`AutoPlayFromDrawPile` parks EVERY
pick in Play before playing any of them, `CardPileCmd.cs:954`, and a card whose
OnPlay auto-plays another card leaves both in Play). It is now SAVED AND
RESTORED around the play loop; the old code cleared it to `None` at the tail,
so a nested play (Cascade) wiped the outer card's mark for the rest of its own
play. Its ONE consumer is `relics/pen_nib.py`, outside this lane's footprint —
see §7.

**Tests:** `test/test_round13_play_pile.py`, 42 pins. RED evidence in §5.

### G8 — the manual-play dispatch — **NARROWED (not closed)**

Wired: `CombatState._add_to_play_pile` dispatches
`after_card_changed_piles(card, old_pile, None)` after the move — `"hand"` for
a manual play, `None` for a pile-less card, `"draw"`/`"exhaust"`/... for an
auto-play from elsewhere. The play's EXIT dispatches again with `pile="play"`
(`CardModel.cs:1988 -> CardPileCmd.cs:635`), as does
`remove_card_from_combat` (`CardPileCmd.cs:188`), the turn-end-in-hand discard
(`CardModel.cs:1696`), `MoveToResultPileWithoutPlaying`'s discard arm
(`:2104`) and `auto_play_from_draw_pile`'s park (`CardPileCmd.cs:954`).

**Why not a full close:** see §8 F1. `CardCmd.Exhaust` is
`CardPileCmd.Add(card, PileType.Exhaust, ...)` (`CardCmd.cs:242`), so every
exhaust in the game is an AfterCardChangedPiles dispatch; the sim's
`ExhaustCmd.exhaust` does not dispatch it at any of its ~30 call sites. That is
a residue of **step81 (the Add site)**, which the record considers closed, not
of step 82. Closing G8 while it stands would be closing a guard on an
enumeration that is one site short.

### step99 — AutoPlayFromDrawPile — **STALE-ALREADY-FIXED (confirmed), residue closed**

Verified against the tree, not the prose: `CardPileCmd.auto_play_from_draw_pile`
(`sts2_rl/cmds.py`) is the two-phase port, and `grep -rn
auto_play_from_draw_pile sts2_rl/` shows the definition plus its callers. The
entry's own premise ("the sim has no AutoPlayFromDrawPile verb") is false.

Its ONE Play-pile defect is now fixed: phase 1 parked its picks NOWHERE
(removed from the draw pile into a local list) where `CardPileCmd.cs:954` parks
them in `PileType.Play`. They are now appended to `play_pile` with the
`"draw" -> Play` dispatch.

**And the entry's "both ported callers now route through it" is itself stale.**
Two more callers are literally `CardPileCmd.AutoPlayFromDrawPile` in C# and
were still open-coding the verb:

* `Cascade.cs:23` — the whole of `OnPlay` is
  `await CardPileCmd.AutoPlayFromDrawPile(choiceContext, Owner, num,
  CardPilePosition.Top, forceExhaust: false)`;
* `DistilledChaos.cs` — same one-statement `OnUse`.

Both now call the verb. Besides parking nowhere, both open-coded loops broke on
`combat.is_over or player.is_dead` where `CardPileCmd.cs:958` breaks on
`item.Owner.Creature.IsDead` alone.

Pin: `test_auto_play_from_draw_pile_parks_every_pick_in_the_play_pile`.

### step51 — Sly / `CardCmd.DiscardAndDraw` — **FIXED (machinery)**

C# (`CardCmd.cs:172-205`), statement for statement:
`IsOverOrEnding -> return` (`:174-177`); empty -> return (`:179-182`); per card
collect `IsSlyThisTurn` (`:188-191`), `CardPileCmd.Add(card, discardPile)`
(`:192`), `History.CardDiscarded` (`:193`), `Hook.AfterCardDiscarded` (`:194`)
— **append first, hook second**; THEN the draw, once (`:197-200`); THEN
auto-play every collected Sly card with `AutoPlayType.SlyDiscard` (`:201-204`).
Its own warning at `:139-143` is the reason it exists as one verb.

Sim: new `CardCmd.discard_and_draw`. `hooks.before_card_auto_played` gained the
`auto_play_type` argument (`CardCmd.cs:122`) and `CombatState.auto_play_card`
threads it.

**The asymmetry the brief flagged is real and is fixed.** The two open-coded
copies disagreed with each other: `potions.py`'s Gambler's Brew fired
`on_card_discarded` BEFORE the append, `relics/gambling_chip.py` appended
first. C# appends first. Both now route through the verb (`GamblersBrew.cs:27`
and `GamblingChip.cs:21` are the same one-line call).

Still DORMANT on content: no sim card carries the Sly keyword (`cards/base.py`
has the fields, nothing sets them), and `AutoPlayType`'s only C# reader is
`SkillSilent1Achievement.cs`, unported (step46).

Pins: `test_discard_and_draw_appends_before_it_fires_the_hook`,
`..._draws_before_it_auto_plays_the_sly_cards`, `..._passes_the_auto_play_type`,
`..._is_refused_once_the_combat_is_over_or_ending`,
`test_gamblers_brew_routes_through_discard_and_draw`,
`test_gambling_chip_routes_through_discard_and_draw`.

### step56 — PileIndexSort — **NARROWED**

C# (`CardCmd.cs:353-360`, applied at `:405`): sort by `CardPile.Type.CompareTo`
— the RAW `PileType` enum value — then by the index captured pre-removal
(`pile.Cards.IndexOf(...)` at `:396`, `RemoveFromCurrentPile()` at `:402`).
**That is deliberately NOT `AllPiles` order**: Draw(1) sorts before Hand(2),
where `AllPiles` puts Hand first. Full order Draw -> Hand -> Discard ->
Exhaust -> Play -> Deck.

Sim: `CardCmd.pile_index_sort_key(pile_name, index)` plus the
`CardCmd._PILE_TYPE_ORDER` map. NARROWED rather than FIXED because there is
still nothing to sort — both sim transform verbs (`CardCmd.transform_to_random`,
`RunState.transform_card`) are single-card. The key exists and is pinned so
that when a batch transform is ported the ordering is not re-derived from
`AllPiles` by mistake, which is the specific error this entry predicts.

Pin: `test_pile_index_sort_orders_by_raw_pile_enum_then_index`.

### `power/smoggy` — `AfterCardEnteredCombat` — **FIXED structurally; the entry's evidence never held**

C# re-read in full (`SmoggyPower.cs`): `AfterCardPlayed` (`:22-36`) sweeps
`Owner.Player.PlayerCombatState.AllCards` and afflicts every unafflicted Skill;
`AfterCardEnteredCombat` (`:38-45`) afflicts ONE new card and does not sweep;
`AfterSideTurnEnd` (`:47-61`) sweeps `AllCards` to clear.

Since `all_cards` is now literally `AllPiles`, all three sweeps see the Play
pile and the entry's structural complaint is answered. But its stated exposure
— "in the sim it is in neither all_cards nor the discard pile yet and is
skipped" — was **false against the tree it was written for**: `_resolve_card_play`
appended every non-Power card to `discard_pile` BEFORE the play loop, so the
resolving Skill was already inside `all_cards` when `on_card_played` swept.
Detail in §8, F2. `test_smoggy_afflicts_the_skill_that_is_mid_play` is
therefore an honest no-regression pin, not a RED-to-GREEN one.

---

## 2. The two HARD BLOCKERS

Both were real and both are fixed by porting the C# literally rather than by
translating the guard.

**CorruptionPower.** C# (`CorruptionPower.cs:27-38`) is a
`ModifyCardPlayResultPileTypeAndPosition` implementer whose entire body is the
owner test, the Skill test, and `return (PileType.Exhaust, position)`. There is
no pile-membership test and no `pileType != Discard` guard — Corruption
OVERRIDES whatever the chain handed it. The sim had it as an `on_card_played`
handler that moved the card out of the discard pile BY HAND, once per play
iteration. `card in player.discard_pile` is FALSE for every card once a
resolving card lives in `play_pile`, so Corruption would have silently stopped
working. Rewritten as `modify_card_play_result_pile` returning `"exhaust"`,
which also fixes the timing (C# exhausts at the play's EXIT, `CardModel.cs:1985`,
through `CardCmd.Exhaust`, not inside the loop).
Pins: `test_corruption_sends_the_played_skill_to_the_exhaust_pile`,
`test_corruption_beats_a_draw_top_redirect`.

**ReboundPower.** C# (`ReboundPower.cs:19-29`) tests the owner and
`pileType != PileType.Discard`. Nothing else. TWO sim workarounds died:
`card not in player.discard_pile` (a Play-limbo artefact, now false for every
card), and the explicit `card.exhausts or card.exhaust_on_next_play` re-test,
which existed only because `_resolve_card_play` passed the literal `"discard"`
for every card. The chain is now seeded with
`GetResultPileTypeForCardPlay`'s real answer, so an exhausting play arrives as
`"exhaust"` and C#'s one guard covers the abstention that
`ReboundPower.cs:25-28` describes.
Pins: `test_rebound_still_redirects_a_played_card_to_the_draw_top`,
`test_rebound_abstains_on_an_exhausting_play`.

**"A played card must never strand in the Play pile."** It does not, with one
exception that is C#'s own: the four `if (Owner.Creature.IsDead) return;`
statements return out of the whole wrapper, past the exit switch, and the card
stays in Play. The sim does the same, deliberately (§3). Every other path goes
through `_move_to_result_pile_after_play`, whose gate is `card not in
play_pile -> return` — the same gate C# spells as `pile.Type == PileType.Play`,
which is what makes an effect that moved the card out mid-play the owner of it.

### The de-hacks

| site | what it was | now |
|---|---|---|
| `cards/cascade.py` | removed itself from the discard for the duration and restored it in a `finally`; open-coded AutoPlayFromDrawPile | one `CardPileCmd.auto_play_from_draw_pile` call (`Cascade.cs:23`) |
| `cards/headbutt.py` | `predicate=lambda c: c is not self` + a "deviation guard" docstring | no predicate; the card is in Play, so it is not a candidate |
| `cards/trash_heap_cards.py` | `sum(1 for c in discard if c is not self)` | `len(ctx.player.discard_pile)` |
| `cards/colorless_attacks.py` | a three-pile scan for the return-to-hand | `player.remove_from_current_pile(card)` (all five) |
| `powers.py` CorruptionPower | see above | see above |
| `powers.py` ReboundPower | see above | see above |
| `player.py` ×2 reshuffles | `_playing_card` hold-back + restore | deleted; the exclusion is structural |
| `cmds.py` `ExhaustCmd.exhaust` docstring | asserted "no fourth Play limbo case exists to scan for" | that premise is named as dead, and the fifth pile is scanned |

---

## 3. ADDENDUM — the `Owner.Creature.IsDead` early returns

Re-derived from `CardModel.cs` rather than taken from the brief. There are
**four** of them inside `OnPlayWrapper`, and the brief's list is close but not
exact:

```
:1895  playCount = await GeneratePlayCount(...)
:1896  if (Owner.Creature.IsDead) return;      <- BEFORE BeginCardOrPotionEffect
:1901  BeginCardOrPotionEffect
:1929  await Hook.BeforeCardPlayed(...)         <- NO IsDead gate before this
:1931  await OnPlay(...)
:1932  if (Owner.Creature.IsDead) return;       <- after OnPlay, before the enchantment
:1937      await Enchantment.OnPlay(...)
:1940      if (Owner.Creature.IsDead) return;
:1946      await Affliction.OnPlay(...)
:1950      if (Owner.Creature.IsDead) return;
:1957  if (IsInProgress) { await Hook.AfterCardPlayed(...);
:1960                      if (Owner.Creature.IsDead) return; }
```

So the brief's "before BeforeCardPlayed" is wrong — the gate is at `:1896`,
before the LOOP, not inside it — and it omits `:1960`. All four are `return`,
not `break`: they skip the exit switch (`:1976-1991`) AND `CheckForEmptyHand`
(`:1992`). The sim's single break-on-dead at the loop tail was in none of those
slots and never skipped the exit.

Landed: `:1896` in `_resolve_card_play` between the play-count hook and the
loop; `:1932` and `:1940` in `_play_count_loop`; `:1960` right after
`on_card_played`. `:1950` has no sim counterpart (no ported affliction has an
`OnPlay`) and is named in a comment. The post-loop `if self.player.is_dead:
return` reproduces the "past the exit switch" half.

Pins: `test_a_lethal_self_damaging_play_stops_before_after_card_played`
(asserts `AfterCardPlayed` is NOT dispatched and that the card is left in
Play), `test_a_play_that_only_hurts_the_player_still_dispatches` (the vetoed /
survivable case still dispatches), `test_the_play_count_gate_runs_before_the_loop`.

Cited as requested: `R4-review.md` §findings — the reviewer's identification of
the missing early return is correct; its slot list is not, and the correction is
above.

---

## 4. Observation impact — measured, HEAD vs live

This is the item the brief asked to "decide + document". **Decision: the Play
pile is NOT added to the observation vector.** No new slots, no schema bump,
every checkpoint stays loadable. A card mid-play is simply in none of the three
observed piles, which is what the game's own UI shows — the discard-pile
counter is `DiscardPile.Cards.Count` and a resolving card is in the play area,
not in it.

Method: `git archive HEAD | tar -x` into the scratchpad (no revert — another
lane is live in this tree), identical scripted-episode driver on both trees,
same action RNG, comparing the full float32 observation vector, the reward, and
a full pile/enemy/HP snapshot per step.

* `STS2FullCombatEnv`, 5 seeds: **byte-identical, all 5.**
* `STS2RunEnv`, 5 seeds (obs+reward hash over the whole episode):
  4 identical, 1 differing.
* `STS2RunEnv`, 30-seed first-divergence sweep, 1,944 compared steps:
  **7 seeds diverge, 23 do not.** Of the 7 first divergences, **5 are exactly
  the intended mid-play observation** — the resolving card
  (`burning_pact`, `headbutt`, `neows_fury`) appears in `play` instead of
  `discard`, with every other field equal. Example (seed 0, step 33):

  ```
  HEAD  discard ["burning_pact"]  play []
  LIVE  discard []                play ["burning_pact"]
  ```

  These are observable at all only because a card-selection decision suspends
  the driver INSIDE `OnPlay`; every post-play observation is unchanged.

* The other 2 (seeds 1 and 16) diverge at an out-of-combat decision with
  identical run HP / gold / deck / relics, and the differing obs segments are
  `phase`, `run.potion0/1`, `reward.potion`, `map0/1/2` — i.e. the two trees
  are on different screens. **Root cause: a shared-RNG draw-count cascade, and
  it is the faithful direction.** `CombatState.select_cards`' selectorless
  fallback draws from the RNG in proportion to the candidate list, and
  Headbutt's and Neow's Fury's candidate lists are the DISCARD PILE, which no
  longer contains the resolving card. C# has exactly that list. This is the
  known "out-of-combat draws on the unseeded shared rng" class; the parity
  gate that matters — the conformance replays against recorded game runs — is
  green (§5).

---

## 5. Tests

New: `test/test_round13_play_pile.py` — **42 pins**, organised by entry
(N9/step82, G8, the exit switch, the ADDENDUM, MoveToResultPileWithoutPlaying,
the five-pile scans, the listener walk, OnTurnEndInHandWrapper, the two hard
blockers, the de-hacks, smoggy, step99, step51, step56).

**RED evidence.** Written before the implementation and run against the live
tree in that state (reverting is forbidden and another lane is live):

```
py -m pytest test/test_round13_play_pile.py -q
    -> 33 failed, 9 passed        (BEFORE)
    -> 42 passed                  (AFTER)
```

The 9 that passed at RED are the no-regression pins — including
`test_smoggy_afflicts_the_skill_that_is_mid_play`, which is how F2 was found.

Re-staged, not deleted (all six manually staged `_playing_card`-in-discard; each
keeps its intent and now sets the state the game is really in, with a
`RE-STAGED 2026-08-01` note saying which claim it replaced):

* `test/test_hook_order.py::test_card_mid_play_is_excluded_from_a_reshuffle_it_triggers`
* `test/test_task8_pile_move_and_generated_hooks.py::test_reshuffle_discard_into_draw_excludes_the_held_card`
* `test/test_tier1_residue.py::test_pile_type_of_reports_play_limbo_not_discard`
  -> renamed `test_pile_type_of_reports_play_for_a_card_mid_play` (its old
  assertion was that the ORDER of the membership tests mattered, which was only
  true because a card was genuinely in two piles)
* `test/test_take_random_streams.py::test_transform_finds_a_card_that_is_mid_play`
  (its stated conclusion — "there was no Play-pile gap here" — was an artefact
  of the stand-in; with a real pile the four-pile scan WOULD have returned None)
* `test/test_relics.py::test_pen_nib_tenth_attack_doubled`
* `test/test_round13_listener_derivation.py::test_a_card_mid_onplay_walks_in_the_play_slot_last`
  (R1's; not in the brief's list of five)

Also changed: `test/test_tiny_dispatchers.py` — the `before_card_auto_played`
spy gained the `auto_play_type` parameter and now asserts the value.

Commands and counts:

```
py -m pytest test/test_round13_play_pile.py -q
    -> 42 passed

py -m pytest test/test_round13_play_pile.py test/test_hook_order.py \
    test/test_task8_pile_move_and_generated_hooks.py test/test_tier1_residue.py \
    test/test_take_random_streams.py test/test_relics.py \
    test/test_round13_listener_derivation.py test/test_tiny_dispatchers.py -q
    -> 336 passed

py -m pytest test/test_auto_play_from_draw_pile.py test/test_powers.py \
    test/test_ironclad_powers.py test/test_colorless.py test/test_curses.py \
    test/test_potions.py test/test_engine_features.py \
    test/test_card_residue_gaps.py test/test_card_residue_gaps2.py \
    test/test_combat_card_db.py test/test_is_dead_early_returns.py \
    test/test_turn_structure_gaps.py test/test_turn_structure_residues.py \
    test/test_discard_draw_order.py test/test_combat_over_hook_gate.py \
    test/test_exhaust_escape_removal.py test/test_live_false_gaps.py \
    test/test_ironclad_final_cards.py -q
    -> 622 passed          (card / power / pile-move blast radius)

py -m pytest test/test_conformance_combat.py test/test_conformance_determinism.py \
    test/test_conformance_player_state.py test/test_conformance_rooms.py \
    test/test_conformance_runner.py test/test_conformance_save.py \
    test/test_conformance_recording.py test/test_conformance_map.py \
    test/test_conformance_pools.py test/test_conformance_relic_bag.py -q
    -> 95 passed, 6 xfailed    (the replay-parity gate against recorded runs —
                                the evidence that matters for §4's RNG cascade)

py -m pytest test/ -q --ignore=test/test_conformance_floor_state.py
    -> 3910 passed, 6 xfailed          (run once mid-work to find blast radius;
                                        the controller gates the full suite)

py -m pytest test/test_conformance_floor_state.py -q
    -> 2 failed, 3 passed              (the known missing 933T floor_49 fixture,
                                        FileNotFoundError on actions.sts2replay —
                                        unchanged, never counted)
```

---

## 6. Record-close proposals

Record file: `audit/records/seam/creature_card_cmds.json` (and
`audit/records/power/smoggy.json`). For each: the verdict and **which
reasoning it replaces**.

**guard `N9` -> `faithful`.**
Close note: *Closed 2026-08-01 (round 13, R5). `PlayerCombatState.play_pile`
is a real list — the fifth entry of `AllPiles` (PlayerCombatState.cs:70-80),
last in `all_cards`, a combat pile for `pile_type_of` and for
`CardCmd.afflict`'s IsEnding guard (PileTypeExtensions.cs:35-42). A card
occupies it for the whole of `OnPlayWrapper` (CardModel.cs:1875/:1879) and
leaves through the Play-gated exit switch (:1976-1991).*
Reasoning replaced: two claims, both now dead. (a) "the limbo exclusion is
parity-only" — already corrected by step82's 2026-07-29 re-verify, and now moot:
there is no exclusion code left in either reshuffle helper, because
`CardPileCmd.Shuffle` reads Draw and Discard (CardPileCmd.cs:870-871) and a
resolving card is in neither. (b) "the remaining exposure … is not
demonstrated, as no ported card reads the discard-pile size mid-play" —
superseded by step82's own finding (Stack), and now structurally impossible:
`trash_heap_cards.py` reads `len(ctx.player.discard_pile)` with no `is not self`
filter and gets the game's number.

**step 82 -> `faithful`.**
Close note: *Closed 2026-08-01 (round 13, R5). `AddDuringManualCardPlay`
(CardPileCmd.cs:647-684) is ported as `CombatState._add_to_play_pile`:
the IsOverOrEnding guard (:649-652), `oldPile` captured before the move (:659),
`RemoveFromCurrentPile` (:669), the raw insert into Play (:670), and the single
`Hook.AfterCardChangedPiles(..., oldPile?.Type ?? None, clonedBy: null)` at
:683, AFTER the move. `play_card` no longer pops the hand — that removal IS the
command, which is why `oldPile` was previously unavailable. The same method
serves the auto entry (CardModel.cs:1879 `CardPileCmd.Add(this,
PileType.Play)`), whose two refusals (:312-319 IsEnding, :398-401 !IsInProgress)
are together the manual entry's one IsOverOrEnding.*
Reasoning replaced: "the architectural gap is unchanged — the sim still has no
Play pile: `_resolve_card_play` still appends the played card straight to
DISCARD and sets `player._playing_card` as a limbo marker". Also: the entry's
DORMANT verdict rested on "no ported card is left with a wrong observable;
Stack's `is not self` filter is the tell". Stack's filter is now deleted and
so are Headbutt's and Cascade's; the compensation moved from four card authors
into the engine.

**step 99 -> `faithful` (stale close CONFIRMED), with a correction.**
Close note: *Re-verified 2026-08-01 (round 13, R5) against the tree, not the
prose: `CardPileCmd.auto_play_from_draw_pile` is the two-phase port and its
stated premise is false. Its ONE remaining Play-pile defect is fixed — phase 1
now parks each pick in `play_pile` with the `"draw" -> Play` dispatch
(CardPileCmd.cs:954), where it used to remove the picks into a local list and
park them in no pile at all. CORRECTION to this entry's own close note: "BOTH
ported callers now route through it" was wrong — `Cascade.cs:23` and
`DistilledChaos.cs` are also single-statement `AutoPlayFromDrawPile` calls and
were still open-coding the verb (parking nowhere, and breaking on
`combat.is_over` where CardPileCmd.cs:958 breaks on the owner's death alone).
Both now route through it; there are four callers, not two.*
Reasoning replaced: the two-caller enumeration, and the claim that parking the
picks in no pile "match[ed] C#'s Play-pile-limbo immunity by a different
mechanism" — it matched the reshuffle immunity but not `AllCards`, not the
listener walk, and not `pile_type_of`.

**step 51 -> `faithful` (machinery), DORMANT on content.**
Close note: *Closed 2026-08-01 (round 13, R5). `CardCmd.discard_and_draw` ports
CardCmd.cs:172-205 statement for statement, including the collect-then-defer
shape its own warning at :139-143 exists for: append to the discard (:192) THEN
`Hook.AfterCardDiscarded` (:194), the draw once for the whole batch
(:197-200), then `AutoPlay(..., AutoPlayType.SlyDiscard)` per collected Sly card
(:201-204). `hooks.before_card_auto_played` carries the `AutoPlayType`
(CardCmd.cs:122). Both open-coded copies are rerouted — `potions.py`'s
Gambler's Brew (GamblersBrew.cs:27) and `relics/gambling_chip.py`
(GamblingChip.cs:21) — which also closes an asymmetry neither record mentioned:
the two fired `AfterCardDiscarded` on OPPOSITE sides of the append. Still
dormant on content: no sim card carries the Sly keyword.*
Reasoning replaced: "The Sly keyword is UNPORTED … so CardCmd.Discard's
collect-then-auto-play tail has no sim counterpart and neither does the
AutoPlayType.SlyDiscard path". Both now exist; what is unported is the KEYWORD's
content, not the machinery. Note this also settles step 50's ordering, which the
entry said "becomes live at the same moment".

**step 56 -> NARROWED, not closed.**
Close note: *Narrowed 2026-08-01 (round 13, R5). `CardCmd.pile_index_sort_key`
ports CardCmd.cs:353-360 exactly — the RAW `PileType` enum compare
(None=0, Draw=1, Hand=2, Discard=3, Exhaust=4, Play=5, Deck=6), then the
pre-removal index captured at :396 — and is pinned, specifically so that a
future batch transform does not re-derive the order from `AllPiles` (which
would put Hand before Draw). NOT closed: both sim transform verbs are still
single-card, so nothing applies the key yet. The trigger this entry names —
porting any multi-card transform — is unchanged.*
Reasoning replaced: nothing in the entry is wrong; only "has no sim
counterpart" becomes "has a sim counterpart with no caller".

**guard `G8` -> NARROWED (do NOT close).**
Close note: *Narrowed 2026-08-01 (round 13, R5). The manual-play site
(CardPileCmd.cs:683) — the last of the four this guard enumerates — is WIRED:
`CombatState._add_to_play_pile` dispatches with the pile the card left and a
literal null `clonedBy`, AFTER the move, and the play's exit dispatches again
from `pile="play"` (CardModel.cs:1988 -> CardPileCmd.cs:635). Four further
`Add`-site dispatches landed with it (the exit, RemoveFromCombat via the played
Power card, OnTurnEndInHandWrapper's discard, AutoPlayFromDrawPile's park).
STILL OPEN, and it is a residue of step81's Add site rather than of this one:
`CardCmd.Exhaust` is `CardPileCmd.Add(card, PileType.Exhaust)` (CardCmd.cs:242),
so EVERY exhaust in the game is an AfterCardChangedPiles dispatch, and the sim's
`ExhaustCmd.exhaust` dispatches nothing at any of its call sites. Dormancy
unchanged: all four ported listeners filter to Deck.*
Reasoning replaced: "the ONLY site still unwired is the manual play … a faithful
dispatch there needs the Play-pile modelling first (creature_card_cmds/N9)".
The Play-pile prerequisite is met and that site is wired; the enumeration of
"four C# dispatch sites" is what turns out to be short, because `Add` is one
C# METHOD with many sim entry points and step81 closed only some of them.

**`power/smoggy` hooks entry `AfterCardEnteredCombat` -> `faithful`.**
Close note: *Closed 2026-08-01 (round 13, R5). `PlayerCombatState.all_cards`
is now literally `AllPiles.SelectMany(...)` with the Play pile last
(PlayerCombatState.cs:70-82), so all three of SmoggyPower's `AllCards` walks
(AfterCardPlayed :22-36, AfterSideTurnEnd :47-61) see a card mid-play.*
Reasoning replaced — and this is the part worth recording: the entry's stated
exposure was **wrong about the sim it was written against**. It claimed
"in C# that Skill is in the Play pile and IS afflicted with Smog, in the sim it
is in neither all_cards nor the discard pile yet and is skipped — so it can be
replayed by an effect that returns it to hand". `_resolve_card_play` appended
every non-Power card to `discard_pile` BEFORE the play loop, so the resolving
Skill WAS in `all_cards` when `AfterCardPlayed` swept, and it WAS afflicted.
The divergence was structural (the pile list was wrong) but had no behavioural
consequence for this power. Also worth fixing while the record is open: this
issue text describes the `AfterCardPlayed` sweep (`:22-36`) but is filed under
the `AfterCardEnteredCombat` key, whose C# (`:38-45`) does not sweep at all.
`power/ringing`'s "matching entry", which this one cross-references, should be
re-derived on the same basis before it is closed by analogy.

---

## 7. BLOCKED-ON-FOOTPRINT

**`sts2_rl/relics/pen_nib.py`** — one line. `PenNib.cs:120-128`'s no-latch arm
doubles a `cardSource` whose `Pile?.Type != PileType.Play`. The sim reads
`player._playing_card`, which is now the narrower "card whose wrapper is on the
stack". The faithful predicate is now available:

```python
            # PenNib.cs:120-128 — `cardSource.Pile?.Type != PileType.Play`.
            if card not in self.player.play_pile and self._attacks_played == self.ATTACKS - 1:
                return 2.0
```

(replacing the `playing = getattr(self.player, "_playing_card", None)` lookup
and `card is not playing`). The two predicates differ only while
`AutoPlayFromDrawPile` has more than one pick parked — Havoc, Mayhem, Cascade,
Distilled Chaos — where `_playing_card` names one card and `play_pile` holds
several. `player.py`'s `_playing_card` docstring points here.

---

## 8. Findings NOT in the brief

**F1 — `G8`'s enumeration of "four C# dispatch sites" is one site short, and
the missing one is the most-travelled path in the sim.** `Hook.
AfterCardChangedPiles` has one C# ADD site (`CardPileCmd.cs:635`) reached from
every `CardPileCmd.Add` overload — and `CardCmd.Exhaust` (`CardCmd.cs:237-246`)
is `Add(card, PileType.Exhaust, ...)` at `:242`. So every exhaust in the game
dispatches it, before `History.CardExhausted` and `Hook.AfterCardExhausted`.
The sim's `ExhaustCmd.exhaust` dispatches only `on_card_exhausted`, at all ~30
call sites. step81 closed "the Add site" by wiring three generated-card helpers
and the per-card draw; that is not the same as wiring `Add`. I did NOT land the
two-line fix — it is outside the brief's enumerated scope and would add a
dispatch at ~30 sites in a tree three other lanes are live in. Exact diff, for
whoever picks it up: in `ExhaustCmd.exhaust`, replace
`player.remove_from_current_pile(card)` with
`old = player.remove_from_current_pile(card)` and insert
`hooks.after_card_changed_piles(card, old, None)` immediately after
`player.exhaust_pile.append(card)` and before `hooks.on_card_exhausted(card)`
(that is C#'s order: Add's dispatch at `:635`, then `:243`, then `:244`).
Dormant today — all four ported listeners filter to Deck. Same shape applies to
`CardCmd.discard_and_draw`'s `:192` and to `PlayerCombatState.discard_hand`.

**F2 — `power/smoggy`'s issue text is wrong about the sim, not just stale.**
Detailed in §6. The general lesson is round 12's, in a new place: the entry
reasoned from "the sim has no Play pile" straight to "therefore the resolving
card is invisible", without checking where the sim actually put it. It put it
in the discard, which is in `all_cards`. A dormancy verdict was right for the
wrong reason, and the mechanism it named would have been the one to fix.

**F3 — the sim asked for the play COUNT before the RESULT PILE; C# is the
other way round.** `CardModel.cs:1890` `Hook.ModifyCardPlayResultPileTypeAnd
Position` is strictly before `:1895` `GeneratePlayCount`. The sim did
`modify_card_play_count` first. Fixed as part of the rewrite and pinned
(`test_the_result_pile_hook_runs_before_the_play_count_hook`). No sim listener
observes the difference today (Duplication/Hidden Gem ticks vs Nostalgia's
history count are independent), but it is a real hook-order divergence and it
was not in any record I read.

**F4 — `Hook.AfterModifyingCardPlayResultPileOrPosition` (`CardModel.cs:1891-1894`)
and `Hook.AfterModifyingCardPlayCount` (`:2019`) are both "notify only the
listeners whose own call changed the value" hooks the sim has no machinery
for** (`seam/power_cmd` G4). Rebound folds its `PowerCmd.Decrement` into the
modifier call, which the power's docstring already explains; Nostalgia's
`AfterModifyingCardPlayResultPileOrPosition` is a `Flash()` with no game
effect. Recorded because the rewrite put both hooks in their exact C# slots and
the missing after-hooks are now the only thing between this function and a
literal transcription of `:1867-2005`.

**F5 — `_playing_card` was silently lossy under nesting.** The old code set it
at the start of `_resolve_card_play` and cleared it to `None` at the tail, so a
card whose OnPlay auto-plays another card (Cascade, Havoc, Mayhem, Distilled
Chaos, Beat Down, Catastrophe, Hellraiser, Stampede, Whispering Earring, the
Imbued enchantment) had its mark wiped by the inner play and spent the rest of
its own play unmarked. That fed `pen_nib.py` and `pile_type_of`. Now saved and
restored. Nothing in the suite noticed either state.

**F6 — `_process_turn_end_cards`' death path leaves the card in Play.** The sim
has an `if self.player.is_dead: lose_combat(); return` between
`on_turn_end_in_hand` and the Ethereal/Discard branch;
`OnTurnEndInHandWrapper` (`CardModel.cs:1682-1698`) has NO such early return
and always reaches `:1690`. Pre-existing (the card used to end up in no pile,
now it ends up in Play), out of this brief's scope, and unobservable because the
combat is over — but it is a real divergence in a method I touched, so it is
recorded rather than quietly normalised.

**F7 — `CardCmd.AutoPlay`'s pre-emptive add (`CardCmd.cs:114-116`) is not
modelled.** For a card with `Pile == null`, C# adds it to Play there (firing
`AfterCardChangedPiles` with `PileType.None` AND `Hook.AfterCardEnteredCombat`
via `CardPileCmd.cs:517-519`) and then `OnPlayWrapper` adds it AGAIN at `:1879`
(firing a second dispatch with `oldPile = Play`). The sim fires only the
`:1879` one. After this lane's changes, no sim caller of `auto_play_card`
passes a pile-less card — the two that did (`cascade.py`, `potions.py`'s
Distilled Chaos) now park in Play first — so the arm is currently unreachable.
Recorded so it is not rediscovered as a regression.

**F8 — the observation is no longer byte-identical at mid-play decision
points, and the reason is a correct candidate list.** Full numbers in §4. Worth
a queue line because it is the first time a Play-pile change reaches the RL
obs: `select_cards`' selectorless fallback draws in proportion to the candidate
list, and Headbutt's / Neow's Fury's candidate list is the discard pile, which
correctly no longer contains the resolving card. 7 of 30 scripted run-env
episodes diverge; 23 do not; all 5 combat-env episodes are byte-identical; the
conformance replays are green.

---

## 9. Queue annotations (GAP-QUEUE.md style)

**creature_card_cmds N9 + step82** — CLOSED 2026-08-01 (round 13 R5).
`PlayerCombatState.play_pile` is a real fifth pile: last in `AllPiles`
(PlayerCombatState.cs:70-80), a combat pile (PileTypeExtensions.cs:35-42), held
for the whole of `OnPlayWrapper` (CardModel.cs:1875/:1879) and left through the
Play-gated exit switch (:1976-1991). Both reshuffle hold-backs deleted — the
exclusion is structural (CardPileCmd.cs:870-871). Eight compensating de-hacks
removed (cascade, headbutt, Stack, the colorless return-to-hand, Corruption,
Rebound, and the two reshuffles). `_playing_card` survives, narrowed to "the
card whose wrapper is on the stack", with `relics/pen_nib.py` as its one
consumer and a one-line follow-up in R5-report §7.

**creature_card_cmds step99** — CONFIRMED STALE 2026-08-01 (round 13 R5), and
its residue closed: phase 1 parks its picks in `play_pile` (CardPileCmd.cs:954)
instead of in no pile. The entry's own close note undercounted its callers —
`Cascade.cs:23` and `DistilledChaos.cs` are also one-statement
`AutoPlayFromDrawPile` calls and were still open-coding it; four callers, not
two.

**creature_card_cmds step51 (+ step50)** — CLOSED 2026-08-01 (round 13 R5),
machinery only. `CardCmd.discard_and_draw` ports CardCmd.cs:172-205 including
the append-then-hook order (:192-194), the once-for-the-batch draw (:197-200)
and the `AutoPlayType.SlyDiscard` tail (:201-204); `before_card_auto_played`
carries the AutoPlayType. Gambler's Brew and Gambling Chip both reroute, which
also fixes an asymmetry no record listed: the two open-coded copies fired
`AfterCardDiscarded` on opposite sides of the append. Dormant on content — no
sim card has the Sly keyword.

**creature_card_cmds step56** — NARROWED 2026-08-01 (round 13 R5).
`CardCmd.pile_index_sort_key` is CardCmd.cs:353-360 exactly (RAW PileType enum,
then the pre-removal index — Draw before Hand, NOT AllPiles order) and is
pinned. Still no multi-card transform to apply it to, so the entry's trigger is
unchanged.

**creature_card_cmds G8** — NARROWED 2026-08-01 (round 13 R5), NOT closed. The
manual-play site (CardPileCmd.cs:683) is wired, plus four more Add-site
dispatches. But the guard's "four C# dispatch sites" enumeration is short: `Add`
is one C# method with many sim entry points, and `CardCmd.Exhaust` is
`Add(card, PileType.Exhaust)` (CardCmd.cs:242) — so every exhaust dispatches it
in C# and none does in the sim. That is step81's residue, exact diff in
R5-report §8 F1. Dormancy unchanged (all four ported listeners filter to Deck).

**power/smoggy AfterCardEnteredCombat** — CLOSED 2026-08-01 (round 13 R5).
`all_cards` is now literally `AllPiles` with Play last, so all three of
SmoggyPower's sweeps see a card mid-play. The entry's STATED exposure never
reproduced: `_resolve_card_play` used to append the resolving card to the
DISCARD before the loop, so it was already inside `all_cards`. The issue text
also describes `AfterCardPlayed` (SmoggyPower.cs:22-36) while filed under
`AfterCardEnteredCombat` (:38-45, which does not sweep). Re-derive
`power/ringing`'s matching entry rather than closing it by analogy.

**creature_card_cmds (new) — the play loop's IsDead early returns.**
`CardModel.OnPlayWrapper` returns out of the WHOLE method at :1896 (before the
loop), :1932 (after OnPlay), :1940 (after the enchantment), :1950 (after the
affliction) and :1960 (after AfterCardPlayed) — skipping the exit switch
(:1976-1991) and CheckForEmptyHand (:1992). The sim had one break-on-dead at
the loop tail. Landed by R5 with pins; :1950 has no sim counterpart (no ported
affliction has an OnPlay).

**creature_card_cmds (new) — result-pile hook before play-count hook.**
CardModel.cs:1890 precedes :1895; the sim asked for the play count first.
Fixed and pinned by R5. No listener observes it today.

**seam/power_cmd G4 cross-reference.**
`Hook.AfterModifyingCardPlayResultPileOrPosition` (CardModel.cs:1891-1894) and
`Hook.AfterModifyingCardPlayCount` (:2019) are the only two statements of
`OnPlayWrapper` with no sim counterpart after R5. Rebound folds its Decrement
into the modifier call; Nostalgia's is a Flash.

---

## 10. Footprint touched

Engine, all inside the declared footprint: `sts2_rl/player.py`,
`sts2_rl/combat.py`, `sts2_rl/cmds.py`, `sts2_rl/hooks.py`,
`sts2_rl/powers.py` (CorruptionPower + ReboundPower only),
`sts2_rl/potions.py` (Gambler's Brew + Distilled Chaos),
`sts2_rl/combat_card_db.py`, `sts2_rl/cards/cascade.py`,
`sts2_rl/cards/headbutt.py`, `sts2_rl/cards/trash_heap_cards.py`,
`sts2_rl/cards/colorless_attacks.py`, `sts2_rl/relics/gambling_chip.py`.

`sts2_rl/cards/base.py` needed no change: the Sly fields
(`sly`, `_has_single_turn_sly`, `is_sly_this_turn`, `give_single_turn_sly`)
already existed. `sts2_rl/env.py` and `sts2_rl/full_env.py` were verified and
NOT changed — see §4 for the decision and the measurements.

Tests: `test/test_round13_play_pile.py` (new), plus the six re-staged files and
`test/test_tiny_dispatchers.py`.

No `audit/records/**` or `audit/GAP-QUEUE.md` file was edited. No git index
command was run.

---

# Fix pass (2026-08-01)

Response to `R5-review.md` (verdict NEEDS-FIXES). The engine work the reviewer
verified is untouched. This pass fixes one wrong claim, lands two real
omissions, pays the one declared debt, and corrects five pieces of prose.

**The one thing that changed materially in the diagnosis: RV-2 is NOT dormant.**
The reviewer rated the exit switch's missing combat-ending refusals dormant
because every downstream command re-gates. That is true of the *commands* and
false of the *counters*: `JossPaper.CardsExhausted` is a `[SavedProperty]`
(`JossPaper.cs:60-76`) incremented from `AfterCardExhausted` (`:102-114`) and
cleared by nothing at combat end (`AfterCombatEnd` `:144-148` clears
`EtherealCount` only). Every fight that ended on an exhausting card
over-credited a RUN-scoped counter by one. Executed, §2 below.

| review item | action |
|---|---|
| **RV-1 / CONCERN 3** | **REWRITTEN.** Re-measured independently with my own isolation tree; the reviewer is right and its numbers reproduce exactly. Corrected text in §1. |
| **RV-2** | **FIXED**, and the dormancy rating **REFUTED by execution**. The gate landed in `ExhaustCmd.exhaust` (where C# puts it) + the exit's `default:` arm. 6 new pins. |
| **RV-3** | **FIXED** — `modify_card_play_result_pile`'s docstring rewritten (and a second instance of the same defect found in `ReboundPower`). |
| **RV-4** | **FIXED** — the ninth de-hack removed from `cards/neows_fury.py` (now in footprint), with a pin. |
| **CONCERN 1's reason** | **CORRECTED** — zero sim listeners; the constraint is completeness across `Add`'s sim entry points. Also corrects "~30 sites" to the true 14. |
| **CONCERN 2 / ringing** | **DERIVED and PINNED**, not closed by analogy. §6. |
| **RV-5 (bonus)** | Three sibling-lane (R3) entries identified precisely; apply-verbatim close text in §7. |
| **RV-6** | **FIXED** — RED re-measured on a clean `git archive HEAD` export: **41 failed / 13 passed** for the now-54-pin file, and the 13 are named. |
| **RV-7** | `all_cards`' docstring corrected + consumer enumeration; NOT flipped, with the reason. |
| **RV-8** | **FIXED** — `pile_index_sort_key` raises `KeyError`; pinned. |
| **RV-9** | **FIXED** — the pen-nib debt is PAID (`pen_nib.py` is now in footprint) and the pin's `_playing_card` half dropped so it can detect the predicate. |
| **RV-10** | **FIXED** — both Corruption/Rebound orders pinned. |

---

## 1. CONCERN 3 — REWRITTEN. §4 and F8 above are superseded by this section.

### What was wrong

§4's last bullet and F8 attributed two trajectory-changing run-env seeds to
R5's own change through a named mechanism: *"a shared-RNG draw-count cascade …
`CombatState.select_cards`' selectorless fallback draws from the RNG in
proportion to the candidate list, and Headbutt's and Neow's Fury's candidate
lists are the DISCARD PILE, which no longer contains the resolving card."*

That is **false, and the method could not have established it.** The
measurement was HEAD-vs-live in a worktree carrying 29 changed engine files
from six lanes, so nothing in it could be attributed to the Play pile.

### What I did

Built a **third tree** as the reviewer describes and re-measured from scratch
with my own probe (`scratchpad/obsprobe.py`, `obsdump.py`, `cmp.py`):

* `head_export` = `git archive HEAD | tar -x` (no revert; another lane is live).
* `treeC` = that export **plus only** `sts2_rl/events/the_future_of_potions.py`
  and `sts2_rl/events/base.py` copied in from live — the concurrent event
  lane's two files, nothing else.
* Identical scripted driver on all three: `env.reset(seed=s)`, then a uniform
  choice over `action_masks()` from a policy-local `random.Random(1000+s)`, so
  the only way two trees can act differently is if their masks or step counts
  differ. Per step I record a SHA-1 of the float32 observation, the mask hash,
  the action, the reward, a full pile/HP/gold/deck snapshot **and a digest of
  `run.rng.getstate()`.**

Measured against the FINAL tree, i.e. after every fix in this pass:

```
===== run env, 30 seeds =====
LIVE   vs HEAD    : 23/30 identical   (seeds 9, 11, 14, 16, 17, 18, 27 differ)
TREE_C vs HEAD    : 28/30 identical   (seeds 16 and 17 - and ONLY those two
                                       change episode length, reward, actions)
LIVE   vs TREE_C  : 25/30 identical   (seeds 9, 11, 14, 18, 27 - every one of
                                       them identical in length, reward AND
                                       action sequence)
===== combat env, 5 seeds =====
LIVE vs HEAD, TREE_C vs HEAD, LIVE vs TREE_C : 5/5 byte-identical, all three
```

Seeds 16 and 17 in detail:

```
seed 16   LIVE n=107 reward=5.0 | TREE_C n=107 reward=5.0 | HEAD n=105 reward=7.0
  LIVE   vs HEAD  first divergence t=59: REWARD_POTION vs MAP, run.rng af7d8ac8f1b3 vs 8d84edab9623
  TREE_C vs HEAD  first divergence t=59: REWARD_POTION vs MAP, run.rng af7d8ac8f1b3 vs 8d84edab9623
  LIVE   vs TREE_C: IDENTICAL over all 107 steps (obs, action, reward, state, run.rng digest)
seed 17   LIVE n=75 | TREE_C n=75 | HEAD n=87
  LIVE and TREE_C diverge from HEAD at the same t=62, on the same screen, with
  the SAME run.rng digest on both sides; LIVE vs TREE_C: IDENTICAL, all 75 steps.
```

So the two trajectory-changing, reward-changing seeds are **100% the event
lane's**, reproduced byte-for-byte by a tree containing none of R5's work.

**The named mechanism is impossible here, on three independent counts, and I
executed the first one rather than arguing it:**

1. *The candidate list is the same size on both trees.*
   `scratchpad/candlist.py` plays each card with three other cards in the
   discard and records what `select_cards` is handed:
   ```
   head_export   headbutt    -> candidate list sizes [3]
   head_export   neows_fury  -> candidate list sizes [3]
   sts2-rl-tier2 headbutt    -> candidate list sizes [3]
   sts2-rl-tier2 neows_fury  -> candidate list sizes [3]
   ```
   On HEAD the resolving card was in the discard and the `is not self`
   predicate removed it; on LIVE it is structurally absent. `N-1` either way —
   nothing about an RNG draw count can change.
2. *`cards/neows_fury.py` never carried a divergence to begin with.* Its
   predicate was a no-op on both trees and this pass deletes it (RV-4). The
   report named a file R5 had not touched as a cause.
3. *The selectorless fallback is unreachable in the run env.* `RunDriver`
   installs `run.card_selector = self._card_selector` (`driver.py:320`) and it
   becomes every combat's `card_selector` via `create_combat`, so
   `CombatState.select_cards` never reaches `rng.sample`. Every divergent step
   I found is a `DecisionKind.SELECT_CARDS` request — the driver suspended on
   the screen — which is the positive form of the same fact.

### The correct finding — this is the record

**R5's Play pile changes the RL observation ONLY at a decision point suspended
inside `OnPlay`, and it NEVER changes a trajectory.**

All five residual seeds have identical episode length, identical total reward
and an identical action sequence, and every differing step differs in
**exactly two slots**, both of them one card's worth:

* `combat[12]` = `player.pile_sizes[2]` = `_clip01(len(p.discard_pile)/40.0)`
  (`full_env.py:698`) — Δ = 0.025, exactly one card;
* one slot of the `discard_pile` composition block (`full_env.py:751`) —
  0.1 → 0.0, exactly one card.

Ground truth at seed 27, step 5 — an Armaments upgrade screen suspended inside
`OnPlay`:

```
HEAD/TREE_C  hand ['defend','strike','strike']  discard ['strike','armaments']  play []
LIVE         hand ['defend','strike','strike']  discard ['strike']              play ['armaments']
```

That is `PileType.cs:26-30` verbatim — Play is *"a temporary pile that a card
lives in while it's mid-play, so that it isn't counted towards your hand or
your discard pile"* — i.e. the game's own UI semantics. Every differing step in
all five seeds has that shape; the cards involved are `armaments`, `headbutt`
and `neows_fury`, all of them mid-`OnPlay` card-selection screens.

The decision stands and is now positively supported: **the Play pile is NOT
added to the observation vector.** No new slots, no schema bump, every
checkpoint stays loadable, and the replay-parity gate is green (95 passed /
6 xfailed, re-run below).

---

## 2. RV-2 — the exit switch's combat-ending refusals: FIXED, and DORMANCY REFUTED

### Re-derived from the C#

`CardModel.cs:1979-1989`'s three arms, each re-read in full:

* **`default:`** is `CardPileCmd.Add(this, resultPileType, resultPilePosition)`.
  `Add` refuses a combat pile at `CardPileCmd.cs:312-319`
  (`newPile.IsCombatPile && CombatManager.Instance.IsEnding` -> every result
  `success:false`, immediate `return`) and at `:398-401`
  (`newPile.IsCombatPile && !CombatManager.Instance.IsInProgress` -> early
  `return results`). **Both are strictly before** `card.RemoveFromCurrentPile()`
  at `:496` and `targetPile.AddInternal(...)` at `:510`, so a refused add
  leaves the card exactly where it was — in Play.
* **`case Exhaust:`** is `CardCmd.Exhaust`, whose entire body is inside
  `if (!CombatManager.Instance.IsOverOrEnding)` (`CardCmd.cs:239-245`) — the
  `Add` at `:242`, `History.CardExhausted` at `:243` and
  `Hook.AfterCardExhausted` at `:244` are refused *together*.
* **`case None:`** is `CardPileCmd.RemoveFromCombat` (`:102-191`), which I read
  end to end: **no liveness gate of any kind.** A Power played as the killing
  blow still leaves the state.

`IsOverOrEnding` is `IsEnding || !IsInProgress` (`CombatManager.cs:210-219`),
which is exactly the disjunction of `Add`'s two guards — the same identity
`_add_to_play_pile` already relies on for the entry. `IsEnding` (`:180-201`) is
true the instant no primary enemy is alive with nothing vetoing, i.e. from
inside the killing blow's own wrapper.

### Where the gate went, and why not where the review put it

The review proposed both gates inline in `_move_to_result_pile_after_play`. I
landed the `default:` one there and the exhaust one **in
`ExhaustCmd.exhaust`**, because that is where C# puts it and because putting it
at the call site would have repeated exactly the partial-landing mistake this
review criticises in G8:

> `grep -rn "PileType.Exhaust" src/` — the ONLY
> `CardPileCmd.Add(..., PileType.Exhaust, ...)` in the entire source is
> `CardCmd.cs:242`.

So **every exhaust in the game passes through `CardCmd.Exhaust` and is gated by
`:239`**, and `ExhaustCmd.exhaust` is that method's port. Gating it there covers
the exit arm and the other **13** direct sim call sites (`potions.py` x2,
`combat.py` x2, `relics/paels_eye.py`, `cards/{true_grit, thrash, stoke,
second_wind, fiend_fire, colorless_skills, cinder, burning_pact, brand}.py`)
with one statement. `combat.py`'s exhaust arm now carries only the citation.

```python
# sts2_rl/cmds.py, ExhaustCmd.exhaust
if is_over_or_ending(hooks):
    return
player.remove_from_current_pile(card)
...

# sts2_rl/combat.py, _move_to_result_pile_after_play, `default:` arm
if self.is_over_or_ending:
    return
self.player.play_pile.remove(card)
```

### DORMANCY: REFUTED, by execution

The review rates this dormant because `BlockCmd` / `DrawCmd` / `DamageCmd` and
the draw are each separately `IsOverOrEnding`-gated. I enumerated **every**
`on_card_exhausted` implementer in `sts2_rl/` rather than checking the recorded
ones — `grep -rn "def on_card_exhausted" sts2_rl/` gives nine:

| implementer | effect in the ending window | gated? |
|---|---|---|
| `powers.FeelNoPainPower` | `BlockCmd.apply` | yes, downstream |
| `powers.DarkEmbracePower` | `DrawCmd.draw` | yes, downstream |
| `relics/charons_ashes` | `DamageCmd.deal` | yes, downstream |
| `relics/forgotten_soul` | `DamageCmd.deal` + a `combat_rng.targets` draw | yes — its own `combat.is_over` test passes but `living_enemies()` is empty, so it returns before the RNG draw |
| `relics/burning_sticks` | one-shot clone into hand | per-combat flag, reset next combat |
| `cards/drum_of_battle` | auto-plays itself | downstream-gated |
| `history` | appends a `CardExhaustedEntry` | ungated, but the combat is terminal |
| **`relics/joss_paper`** | **`self.cards_exhausted += 1`** | **NOT gated, and NOT per-combat** |

`JossPaper.CardsExhausted` is a `[SavedProperty]` (`JossPaper.cs:60-76`), fed
by `AfterCardExhausted` (`:102-114`), and `JossPaper.AfterCombatEnd`
(`:144-148`) clears `EtherealCount` **only**. It is a RUN-scoped counter that
draws a card every 5. Executed, both directions:

```
OLD (ungated exit):  joss_paper.cards_exhausted = 1 | pile = exhaust
NEW (CardCmd.cs:239): joss_paper.cards_exhausted = 0 | pile = play
```

So every fight that ended on an exhausting card — Feed, Impervious, Fiend
Fire, Second Wind, Brand, Cinder, Stoke, Burning Pact, Thrash, True Grit and
the rest of the 36 exhausting cards, plus any exhaust a card fired from its
own OnPlay after the kill — advanced a persistent counter the game does not
advance, and shifted when Joss Paper draws for the rest of the run. **This is
live, ordinary play, and it is a divergence R5's original pass would have
shipped.** The review's dormancy rating is refuted; the *commands* re-gate, the
*counters* do not.

### A legacy test the C# contradicts

`test/test_ironclad_cards.py::TestFeed::test_fatal_grants_max_hp_and_heals`
asserted `card in cs.player.exhaust_pile`. Feed's own OnPlay lands the killing
blow, so `IsEnding` is already true at the exit and `CardCmd.cs:239` refuses:
the game leaves Feed in `PileType.Play` and fires no `AfterCardExhausted`. The
assertion is a sim-legacy artefact, not game behaviour. **Re-staged** to assert
`card in cs.player.play_pile` and `card not in cs.player.exhaust_pile`, with the
citation in the test. The Fatal max-HP grant is untouched (it happens inside
OnPlay, before the exit) and is still asserted.

### Pins (all RED first)

| pin | RED evidence |
|---|---|
| `test_the_killing_blow_stays_in_the_play_pile` | pre-fix live tree: `assert [] == [Round 13 Probe]` |
| `test_a_pending_loss_leaves_the_played_card_in_play` | same, `assert [] == [Round 13 Probe]` |
| `test_an_exhausting_killing_blow_stays_in_play_and_fires_no_exhaust_hook` | same, `assert [] == [Round 13 Probe]` |
| `test_the_refused_exhaust_does_not_credit_joss_paper` | HEAD export: `assert 1 == 0  where 1 = Joss Paper.cards_exhausted` — the liveness itself |
| `test_a_direct_exhaust_is_refused_once_the_combat_is_ending` | HEAD export: `assert [] == [Strike]` (the card had already left the hand) |
| `test_a_power_card_is_still_removed_from_combat_on_the_killing_blow` | negative control for the ungated `None` arm; not meaningfully RED on HEAD (no `play_pile` attribute) |

---

## 3. RV-3 — `modify_card_play_result_pile`'s docstring: FIXED

`hooks.py`'s dispatcher said the hook is *"Consulted only for cards that would
land in the discard pile (exhausted cards and Powers never reach it)"* — the
exact statement R5's change inverted. Rewritten to `CardModel.cs:1890` +
`:2070-2082`: it is consulted ONCE per play for EVERY card, seeded with
`GetResultPileTypeForCardPlay()`'s real answer (`"none"` for a Power or dupe,
`"exhaust"` for the Exhaust keyword or a consumed `ExhaustOnNextPlay`, else
`"discard"`), and listeners may return any of them — `CorruptionPower` returns
`"exhaust"` unconditionally for Skills, which the old text did not admit
either. The docstring names the claim it replaces.

**A second instance of the same defect, found while fixing it and not in the
review:** `ReboundPower`'s CLASS docstring still argued *"combat.py's
`_resolve_card_play` always passes this hook the literal 'discard' for every
card … so that check has to be made here too"* — describing R3's deleted
workaround, and directly contradicting the method comment three lines below it.
Rewritten to the real chain seed, and it now also records the
order-independent-pile / order-dependent-stack pair that RV-10 pins.

---

## 4. RV-4 — the ninth de-hack: REMOVED

`cards/neows_fury.py:66` still passed `predicate=lambda c: c is not self`.
`NeowsFury.cs:39` is
`CardSelectCmd.FromCombatPile(choiceContext, PileType.Discard.GetPile(Owner),
Owner, new CardSelectorPrefs(prompt, 0, num))` — **no filter of any kind**; the
exclusion is `PileType.Play`. Removed, with the same `headbutt.py`-style
docstring note. `pen_nib.py` is paid too (§8, RV-9), so **R5 now owes no
BLOCKED-ON-FOOTPRINT debt at all** and §7 above is closed.

Pinned by `test_neows_fury_cannot_pick_itself_by_construction`, which asserts
the candidate list the selector is shown, and which **passes on HEAD** — the
correct shape of evidence for a behaviour-preserving de-hack, matching the four
the review checked.

---

## 5. CONCERN 1 — the finding stands, the REASON was wrong

Verified myself rather than accepting either text:

* `grep -rn "def after_card_changed_piles" sts2_rl/` returns **one** line —
  the dispatcher at `hooks.py:1440`. There are **ZERO implementers** in the
  whole package. `hooks.py:589` already says so in passing.
* The four ported C# listeners that would care (`BingBong`,
  `BookOfFiveRings`, `DarkstonePeriapt`, `LuckyFysh`) all filter to
  `PileType.Deck` in C# and reach the sim through
  `Relic.after_card_added_to_deck` (`relics/base.py:358`, called from
  `run.py:452` and `:716`) — a different shim entirely.

So the dispatch is a presence-gate no-op everywhere today and **blast radius is
not the constraint**. The report's "would add a dispatch at ~30 sites in a tree
three other lanes are live in" is wrong twice: the count is **14** direct
`ExhaustCmd.exhaust(` call sites, and their listener set is empty.

The honest reason to defer, which is what the queue should carry: a faithful
`Add` wiring is not two lines at one site. It is `ExhaustCmd.exhaust`,
`CardCmd.discard_and_draw`'s `:192`, `PlayerCombatState.discard_hand`, and the
hand/draw add helpers — and landing two of five is worse than landing none.
G8 stays NARROWED.

---

## 6. CONCERN 2 — `power/ringing`, derived and pinned rather than closed by analogy

`RingingPower.cs` re-read in full. `AfterApplied` (`:23-31`) sweeps
`Owner.Player.PlayerCombatState.AllCards` and afflicts **every** unafflicted
card *of any type* — unlike `SmoggyPower`, which filters to Skills.
`AfterCardEnteredCombat` (`:33-39`) afflicts ONE arriving card and does not
sweep. The sim's port of `AfterApplied` is `RingingPower.__init__`.

Checked against the committed tree, not memory —
`git show HEAD:sts2_rl/combat.py`:

```python
if card.card_type != CardType.POWER:
    self.player.discard_pile.append(card)
    self.player._playing_card = card
```

So on the tree the entry was written against:

* for a **non-Power** card mid-play the entry's exposure was **FALSE** — the
  card was parked in the discard, hence inside `all_cards`, hence afflicted.
  Same error as smoggy's (F2);
* for a **POWER** card mid-play it was **TRUE** — HEAD put it in *no* pile at
  all, so `all_cards` missed it where C#'s `AllCards` has it in Play. Narrow,
  and dormant for the recorded reason (Ringing is applied by an enemy on the
  enemy's turn), but real;
* the entry is **mis-filed the same way smoggy's is**: the issue text describes
  `__init__`/`AfterApplied` while keyed to `AfterCardEnteredCombat`;
* both halves are now structurally closed, because `all_cards` is the five
  piles with Play last.

Pinned by `test_ringing_afflicts_the_power_card_that_is_mid_play`, which applies
Ringing from inside a Power card's own play and asserts the resolving Power was
afflicted. RED on the HEAD export.

---

## 7. RV-5 — the three sibling-lane (R3) entries this closes

Identified precisely, and confirmed by execution on the live tree
(`test_corruption_first_makes_rebound_abstain_and_keep_its_stack` /
`test_rebound_first_is_credited_and_ticks_even_though_corruption_wins`):

```
corruption applied first -> exhaust_pile=[card] draw_pile=[] rebound.amount=2   <- abstains, keeps its stack
rebound   applied first  -> exhaust_pile=[card] draw_pile=[] rebound.amount=1   <- credited, ticks
```

Order-INDEPENDENT pile, order-DEPENDENT stack — `Hook.cs:1391-1406` adds a
listener to `modifiers` only `if (pileType3 != pileType2 || cardPilePosition2
!= cardPilePosition)` and
`ReboundPower.AfterModifyingCardPlayResultPileOrPosition`
(`ReboundPower.cs:32-39`) decrements unconditionally once it is in that list.
Reproduced without the notification machinery.

**The three entries.** All three currently carry reasoning that describes code
that no longer exists; two of them were already flipped to `faithful` by R3's
own fix pass and their close notes are now stale in the same way a docstring
can be. Text below is apply-verbatim.

### (a) `power/corruption` -> hook `ModifyCardPlayResultPileTypeAndPosition` -> `faithful` (was `gap`)

> Closed 2026-08-01 (round 13, R5 fix pass). All three of this entry's named
> residues are gone, because `CorruptionPower` is now a
> `modify_card_play_result_pile` listener returning `"exhaust"` —
> `CorruptionPower.cs:27-38` verbatim (owner test, `card.Type != Skill` test,
> `return (PileType.Exhaust, position)`; no pile-membership test and no
> `pileType != Discard` guard of any kind). (1) Rebound's stack is no longer
> unconditionally consumed: the chain is seeded with
> `GetResultPileTypeForCardPlay` (CardModel.cs:2070-2082 -> :1890's
> `defaultPileType` argument), so with Corruption applied first Rebound is
> handed `"exhaust"`, abstains at ReboundPower.cs:25-28, and is never credited
> — executed both orders, `rebound.amount` 2 vs 1, which is `Hook.cs:1401-1404`
> reproduced. (2) The exhaust timing is fixed: the move happens ONCE at the
> play's exit switch (CardModel.cs:1985 -> `CardCmd.Exhaust`), not once per
> play-count iteration from `on_card_played`; a replayed Skill stays in
> `PileType.Play` for every iteration and fires exactly one
> `Hook.AfterCardExhausted`. (3) Corruption is on the chain, so the `modifiers`
> notification set matches. The BLOCKED-ON-FOOTPRINT hand-off R3 wrote —
> "teach `modify_card_play_result_pile` an `exhaust` destination; branch on it
> in `combat.py`'s post-loop move; delete `CorruptionPower.on_card_played`" —
> was followed exactly. Reasoning replaced: R3's review had already replaced
> the original order-dependence framing (correctly: C# is order-independent on
> the pile too, and Corruption wins there as well); what this close replaces is
> the remaining "the REAL open work is architectural and BLOCKED-ON-FOOTPRINT"
> — it is landed. Pins: `test/test_round13_play_pile.py::test_corruption_sends_the_played_skill_to_the_exhaust_pile`,
> `::test_corruption_beats_a_draw_top_redirect`,
> `::test_corruption_first_makes_rebound_abstain_and_keep_its_stack`,
> `::test_rebound_first_is_credited_and_ticks_even_though_corruption_wins`,
> `::test_corruption_exhausts_once_after_the_whole_play_count_loop`.

### (b) `power/rebound` -> hook `ModifyCardPlayResultPileTypeAndPosition` -> stays `faithful`, close note REPLACED

> Re-closed 2026-08-01 (round 13, R5 fix pass) — verdict unchanged, mechanism
> replaced. The abstention on an Exhaust-keyword card is no longer a
> sim-specific second test: round 13's Play pile made `_resolve_card_play` pass
> this hook `GetResultPileTypeForCardPlay`'s REAL answer
> (CardModel.cs:2070-2082, evaluated as :1890's `defaultPileType` argument), so
> an exhausting play arrives already seeded `"exhaust"` and C#'s ONE guard —
> `if (pileType != PileType.Discard) return (pileType, position);`,
> ReboundPower.cs:25-28 — covers it. The explicit `card.exhausts or
> card.exhaust_on_next_play` re-test the previous close describes is DELETED,
> and so is the older `card not in player.discard_pile` Play-limbo test, which
> the real `play_pile` made false for every card at hook time and which would
> have silently retired this power. Reasoning replaced: that the sim's hook
> "always receives the literal 'discard' … so the test has to be made here". It
> no longer does.

### (c) `power/rebound` -> hook `AfterModifyingCardPlayResultPileOrPosition` -> stays `faithful`, close note REPLACED

> Re-closed 2026-08-01 (round 13, R5 fix pass) — verdict unchanged, gate
> replaced. The tick is still folded into `modify_card_play_result_pile` (the
> sim has no notification-list machinery — seam/power_cmd G4), but its gate is
> now the real "did I change it": the chain carries all three `PileType` seeds,
> so `pile == "discard"` on entry means exactly what `Hook.cs:1391-1406`'s
> `pileType3 != pileType2` comparison means, instead of being the sim's
> flattening of Discard/Exhaust/None into one string. Verified by executing
> BOTH application orders: Corruption first -> Rebound abstains and keeps
> `amount == 2`; Rebound first -> Rebound is credited and ticks to
> `amount == 1`; the final pile is Exhaust either way. That is C#'s
> order-independent pile with C#'s order-dependent stack. Reasoning replaced:
> the previous note's claim that `pile == "discard"` on entry is the same
> condition — it was not then, and it is now, for a different reason than the
> note gives.

---

## 8. Remaining review items

**RV-6 (RED baseline).** Re-measured on a clean `git archive HEAD` export with
the current 54-pin file: **41 failed, 13 passed.** The report's "33 failed, 9
passed" was measured against the mid-work live tree (legitimate under the
no-revert rule, but not reproducible from HEAD, and the report did not say so).
The 13 no-regression pins are: `test_all_cards_puts_the_play_pile_last`,
`test_an_exhaust_keyword_card_exits_through_cardcmd_exhaust`,
`test_a_play_that_only_hurts_the_player_still_dispatches`,
`test_a_refused_power_card_goes_to_the_discard_not_limbo`,
`test_corruption_sends_the_played_skill_to_the_exhaust_pile`,
`test_rebound_still_redirects_a_played_card_to_the_draw_top`,
`test_headbutt_cannot_pick_itself_by_construction`,
`test_neows_fury_cannot_pick_itself_by_construction`,
`test_stack_counts_the_discard_pile_without_itself`,
`test_cascade_does_not_replay_itself`,
`test_smoggy_afflicts_the_skill_that_is_mid_play`,
`test_gambling_chip_routes_through_discard_and_draw`,
`test_corruption_first_makes_rebound_abstain_and_keep_its_stack`.

That last one deserves a note the review did not have: it passes on HEAD **by
accident of listener order**, not because HEAD reproduced `Hook.cs:1401-1404`.
On HEAD both powers were `on_card_played` handlers; Corruption ran first, moved
the card out of the discard, and Rebound then failed its own `card in
discard_pile` test and did not tick. Its mirror,
`test_rebound_first_is_credited_and_ticks_even_though_corruption_wins`, is the
half that is genuinely RED (`assert [] == [Round 13 Probe]` — HEAD sent the card
to the draw top and never exhausted it, exactly the bug R3 described).

**RV-7 (`all_cards`' docstring).** Corrected rather than flipped, and the
docstring now says which leg is wrong and why: `CardPile` is TOP-first
(`MoveToTopInternal` is `Insert(0, …)`; `CardPileCmd.cs:843` draws
`FirstOrDefault()`) while the sim's `draw_pile` is BOTTOM-first, so the draw leg
is emitted reversed. Not flipped because I enumerated every consumer
(`grep -rn "all_cards" sts2_rl/`) and none is order-sensitive: `apotheosis`,
`maul`, `ghost_seed`, `end_of_turn_cleanup`, the Smoggy / Ringing / Tainted /
Galvanized affliction sweeps and `aeonglass` are unconditional sweeps;
`perfected_strike` is a count; `combat.py:197` is listener REGISTRATION, whose
dispatch order `HookSystem._derive` recomputes independently (and `_derive`
already flips the draw pile). `CardCmd.afflict` draws no RNG. The docstring
says flipping is a one-line change and that the equivalence must not be assumed
before a first-match or RNG-proportional consumer is ported.

**RV-8 (`pile_index_sort_key`).** Fixed: `_PILE_TYPE_ORDER[pile_name]`, no
`.get`, and the `None` key removed. `CardCmd.cs:392-394` THROWS on a null pile
("Can't transform … because it has no pile") **before** the index is captured at
`:396`, so `PileIndexSort` can never see one and a silent `PileType.None`
default would be the wrong thing to hand a future batch transform. Pinned by
`test_pile_index_sort_refuses_a_pile_it_does_not_know` (RED on HEAD, where the
method does not exist).

**RV-9 (the pen-nib debt).** `relics/pen_nib.py` is in this pass's footprint, so
the debt is PAID rather than re-declared:

```python
if (card not in getattr(self.player, "play_pile", ())
        and self._attacks_played == self.ATTACKS - 1):
    return 2.0
```

`PenNib.cs:120-128` is `if ((pile == null || pile.Type != PileType.Play) &&
AttacksPlayed == 9) return 2m;` — `card not in play_pile` is true both for a
card in no pile and for a card in any of the other four, so it is the whole
predicate. The pin's `_playing_card` half is dropped so it can detect the
change, and I demonstrated the sensitivity without touching the tree
(`scratchpad/pennib_red.py` runs the pin's exact sequence against a
monkeypatched copy of the old body):

```
OLD predicate (_playing_card): first nine multipliers = [1,1,1,1,1,1,1,1,2.0]   <- the pin asserts all 1.0
NEW predicate (play_pile):     first nine multipliers = [1,1,1,1,1,1,1,1,1.0]
```

**RV-10 (the unpinned order).** Both orders are now pinned — see §7.

---

## 9. Findings from this pass (not in the review)

**F9 — RV-2 is LIVE, not dormant, and the vector is a `[SavedProperty]`.**
Detailed in §2. The general lesson is round 12's, in a new place: "every
downstream command re-gates" is a statement about *commands*, and a hook's
listener set also contains *counters*. A dormancy verdict that enumerates
commands has not enumerated the hook.

**F10 — `CardCmd.cs:242` is the source's ONLY add to `PileType.Exhaust`.**
That single fact settles where the `!IsOverOrEnding` gate belongs
(`ExhaustCmd.exhaust`, covering all 14 sim sites) and it is also the strongest
argument for F1/G8's shape: `CardCmd.Exhaust` is a one-line wrapper around
`Add`, so wiring `Add`'s `AfterCardChangedPiles` dispatch and wiring
`Exhaust`'s liveness gate are the same porting job at the same seam, and this
pass did the second half of it.

**F11 — a legacy test asserted a divergence as if it were the spec.**
`test_ironclad_cards.py::TestFeed::test_fatal_grants_max_hp_and_heals` asserted
that Feed lands in the exhaust pile when it is the killing blow. The game
leaves it in Play. Re-staged with the citation. Worth recording because it is
the only test in the suite that was *asserting* the RV-2 divergence, and it is
why the suite was green over it.

**F12 — `_playing_card` now has ZERO readers.** With the pen-nib debt paid,
`grep -rn "_playing_card" sts2_rl/` finds only the declaration
(`player.py:164`) and the save/restore in `_resolve_card_play`. It is kept and
maintained (the fact it names — "this card's OnPlayWrapper is on the stack" —
is genuinely distinct from the pile, and `AutoPlayFromDrawPile` parking several
picks in Play is the case that separates them), but its docstring now says it
is unread state and that any future reader must first check whether the Play
pile answers the question. A controller may reasonably choose to delete it.

---

## 10. Tests

New in this pass: **12 pins** added to `test/test_round13_play_pile.py`
(42 -> 54), plus one re-staged legacy test.

```
py -m pytest test/test_round13_play_pile.py -q
    -> 54 passed
# RED baseline, clean `git archive HEAD` export (test file copied in, no revert)
py -m pytest test/test_round13_play_pile.py -q   [in the export]
    -> 41 failed, 13 passed

py -m pytest test/test_round13_play_pile.py test/test_hook_order.py \
    test/test_task8_pile_move_and_generated_hooks.py test/test_tier1_residue.py \
    test/test_take_random_streams.py test/test_relics.py \
    test/test_round13_listener_derivation.py test/test_tiny_dispatchers.py \
    test/test_ironclad_cards.py -q
    -> 414 passed

py -m pytest test/test_auto_play_from_draw_pile.py test/test_powers.py \
    test/test_ironclad_powers.py test/test_colorless.py test/test_curses.py \
    test/test_potions.py test/test_engine_features.py \
    test/test_card_residue_gaps.py test/test_card_residue_gaps2.py \
    test/test_combat_card_db.py test/test_is_dead_early_returns.py \
    test/test_turn_structure_gaps.py test/test_turn_structure_residues.py \
    test/test_discard_draw_order.py test/test_combat_over_hook_gate.py \
    test/test_exhaust_escape_removal.py test/test_live_false_gaps.py \
    test/test_ironclad_final_cards.py test/test_combat_ending_command_guards.py -q
    -> 637 passed

py -m pytest test/test_conformance_{combat,determinism,player_state,rooms,
    runner,save,recording,map,pools,relic_bag}.py -q
    -> 95 passed, 6 xfailed        (the replay-parity gate against recorded runs)

py -m pytest test/ -q --ignore=test/test_conformance_floor_state.py
    -> 3939 passed, 6 xfailed, 0 failed
py -m pytest test/test_conformance_floor_state.py -q
    -> 2 failed, 3 passed          (the known missing 933T floor_49 fixture,
                                    unchanged, never counted)
```

Scratchpad scripts (not written to the repo): `obsprobe.py`, `obsdump.py`,
`cmp.py` (the RL-observation isolation), `candlist.py` (the candidate-list-size
execution check), `pennib_red.py` (RV-9's sensitivity demonstration). Trees
built under the scratchpad: `head_export` (`git archive HEAD`) and `treeC`
(HEAD + the event lane's two files). Nothing was reverted in the live tree, no
git index command was run, and no `audit/records/**` or `audit/GAP-QUEUE.md`
file was touched.

Files changed in this pass: `sts2_rl/combat.py`, `sts2_rl/cmds.py`,
`sts2_rl/hooks.py`, `sts2_rl/player.py`, `sts2_rl/powers.py`,
`sts2_rl/cards/neows_fury.py`, `sts2_rl/relics/pen_nib.py`,
`test/test_round13_play_pile.py`, `test/test_relics.py`,
`test/test_ironclad_cards.py` — all inside the fix pass's declared footprint.

---

## 11. FINAL record-close text (supersedes §6 above; apply verbatim)

Records: `audit/records/seam/creature_card_cmds.json`,
`audit/records/power/smoggy.json`, `audit/records/power/ringing.json`,
`audit/records/power/corruption.json`, `audit/records/power/rebound.json`.

**`creature_card_cmds` guard `N9` -> `faithful`.** §6's note above, unchanged.

**`creature_card_cmds` step 82 -> `faithful`.** §6's note above, **plus**:

> The exit switch is ported with C#'s Play gate (CardModel.cs:1976-1977) AND
> with the two combat-ending refusals its arms carry: `CardPileCmd.Add`'s
> IsEnding / !IsInProgress (:312-319, :398-401 — both before the move at :496 /
> :510) on the `default:` arm, and `CardCmd.Exhaust`'s `!IsOverOrEnding`
> wrapper (CardCmd.cs:239) on the Exhaust arm. `case None:`
> (`CardPileCmd.RemoveFromCombat`, :102-191) has no gate and does not get one.
> So a card that lands the killing blow stays in the Play pile, as it does in
> the game. The exhaust gate lives in `ExhaustCmd.exhaust`, not at the call
> site, because CardCmd.cs:242 is the ONLY
> `CardPileCmd.Add(..., PileType.Exhaust, ...)` in the source — every exhaust
> in the game runs inside that wrapper — so one statement covers the exit arm
> and 13 other sim sites. NOT dormant, contrary to R5-review RV-2's rating:
> `JossPaper.CardsExhausted` is a `[SavedProperty]` (JossPaper.cs:60-76) fed by
> AfterCardExhausted (:102-114) and cleared by nothing at combat end (:144-148
> clears EtherealCount only), so every fight that ended on an exhausting card
> over-credited a RUN-scoped counter by one. The commands re-gate; the counters
> do not.

**`creature_card_cmds` step 99 -> `faithful` (stale close CONFIRMED).** §6's
note above with the review's amendment:

> Parking the picks in no pile already gave them reshuffle immunity, because
> `CardPileCmd.Shuffle` reads only Draw and Discard (:870-871); what it did not
> give them was membership of `AllCards`, `pile_type_of`, the listener walk and
> `combat_card_db.ordered_piles`. Parking them in `PileType.Play` (:954)
> supplies all four.

Keep the four-callers correction verbatim.

**`creature_card_cmds` step 51 -> `faithful` (machinery), DORMANT on content.**
§6's note above, plus: *"Pinned by five RED-to-GREEN tests plus one
no-regression pin (`test_gambling_chip_routes_through_discard_and_draw`, which
HEAD already satisfied)."*

**`creature_card_cmds` step 50 -> `faithful` (upgrade from
`deliberate-divergence`).** Own verdict, per the review:

> Closed 2026-08-01 (round 13, R5). The entry's premise — `DiscardAndDraw`'s
> deferred draw "has no sim counterpart because no ported card uses the
> combined verb; the sim's discard-then-draw callers issue the two separately,
> which is the ordering C# explicitly warns against for Sly" — is retired:
> `CardCmd.discard_and_draw` is the combined verb (CardCmd.cs:172-205), the
> draw is issued once for the batch after every `AfterCardDiscarded`
> (:197-200), and both open-coded callers (Gambler's Brew, Gambling Chip) now
> route through it.

**`creature_card_cmds` step 56 -> NARROWED, do not close.** §6's note above,
plus: *"The index is captured at :396 (the brief's :391 is the pile capture);
the sort runs at :405 over tuples whose removals happened at :402. The key
raises KeyError on an unknown pile name rather than defaulting to
`PileType.None`, because :392-394 throws on a null pile before the index is
taken (R5-review RV-8)."*

**`creature_card_cmds` guard `G8` -> NARROWED, do NOT close.** §6's note above
with its LAST SENTENCE REPLACED by:

> Not landed here because a faithful `Add` wiring is not two lines at one site:
> it is `ExhaustCmd.exhaust`, `CardCmd.discard_and_draw`'s :192,
> `PlayerCombatState.discard_hand`, and the hand/draw add helpers, and wiring
> some of them is worse than wiring none. Blast radius is NOT the constraint —
> `sts2_rl/` has ZERO `after_card_changed_piles` implementers (the four ported
> Deck-filtering listeners, BingBong / BookOfFiveRings / DarkstonePeriapt /
> LuckyFysh, reach the sim through `Relic.after_card_added_to_deck`,
> relics/base.py:358, a different shim), so the dispatch is a presence-gate
> no-op today. The site count is 14 direct `ExhaustCmd.exhaust` call sites, not
> the ~30 the first pass claimed.

**`power/smoggy` `AfterCardEnteredCombat` -> `faithful`.** §6's note above, with
the mis-filing correction promoted to a first-class instruction:

> The issue text describes SmoggyPower.cs:22-37 (`AfterCardPlayed`, which
> sweeps `AllCards`) but is keyed to `AfterCardEnteredCombat` (:39-45, which
> afflicts one arriving card and does not sweep). Re-key or re-word.

and the F2 lesson recorded verbatim: the entry reasoned from "the sim has no
Play pile" to "therefore the resolving card is invisible" without checking
where the sim actually put it (the discard, i.e. inside `all_cards`);
`test_smoggy_afflicts_the_skill_that_is_mid_play` passes on HEAD.

**`power/ringing` `AfterCardEnteredCombat` -> `faithful`.** New; do not close by
analogy — this is the derivation:

> Closed 2026-08-01 (round 13, R5 fix pass), re-derived rather than closed by
> analogy with power/smoggy. `PlayerCombatState.all_cards` is now literally
> `AllPiles.SelectMany(...)` with the Play pile last
> (PlayerCombatState.cs:70-82), so every `AllCards` walk sees a card mid-play.
> The entry's stated exposure was HALF wrong about the tree it was written
> against: HEAD's `_resolve_card_play` appended `if card.card_type !=
> CardType.POWER` to the DISCARD before the play loop, so an ordinary card
> mid-play WAS inside `all_cards` and WAS afflicted — the same error
> power/smoggy's entry makes. It was RIGHT for a POWER card mid-play, which
> HEAD put in no pile at all: `RingingPower.AfterApplied`
> (RingingPower.cs:23-31) sweeps `AllCards` and afflicts every unafflicted card
> of ANY type (unlike Smoggy, which filters to Skills), so a Ringing applied
> while a Power card resolved genuinely missed it. Narrow, and dormant for the
> recorded reason (Ringing is applied by an enemy on the enemy's turn), but
> real. Also mis-filed the same way: the issue text describes
> `__init__`/`AfterApplied` (:23-31) while keyed to `AfterCardEnteredCombat`
> (:33-39, which afflicts one arriving card and does not sweep) — re-key or
> re-word. Pin: `test/test_round13_play_pile.py::test_ringing_afflicts_the_power_card_that_is_mid_play`
> (RED on HEAD).

**`power/corruption` `ModifyCardPlayResultPileTypeAndPosition` -> `faithful`**
(was `gap`) — text in §7(a).

**`power/rebound` `ModifyCardPlayResultPileTypeAndPosition`** — verdict
unchanged, close note replaced; text in §7(b).

**`power/rebound` `AfterModifyingCardPlayResultPileOrPosition`** — verdict
unchanged, close note replaced; text in §7(c).

**New entries the controller should open:** F9 (the `on_card_exhausted`
enumeration and the `JossPaper` counter class — a hook's listener set contains
counters, not only commands), F10 (`CardCmd.cs:242` is the source's only
exhaust add), F12 (`_playing_card` is unread state). R5's own F3-F7 are
unchanged and should be queued as written. RV-4 is CLOSED, not opened — the
predicate is deleted. §7's `pen_nib.py` debt is CLOSED, not carried.

---

## 12. FINAL queue text (supersedes §9 above; apply verbatim)

**creature_card_cmds N9 + step82** — CLOSED 2026-08-01 (round 13 R5).
`PlayerCombatState.play_pile` is a real fifth pile: last in `AllPiles`
(PlayerCombatState.cs:70-80), a combat pile (PileTypeExtensions.cs:35-42), held
for the whole of `OnPlayWrapper` (CardModel.cs:1875/:1879) and left through the
Play-gated exit switch (:1976-1991) — including that switch's two combat-ending
refusals (`Add`'s IsEnding/!IsInProgress at CardPileCmd.cs:312-319/:398-401 on
the `default:` arm; `CardCmd.Exhaust`'s `!IsOverOrEnding` at CardCmd.cs:239 on
the Exhaust arm, landed in `ExhaustCmd.exhaust` where C# puts it and so
covering all 14 sim exhaust sites; `RemoveFromCombat` :102-191 has no gate and
gets none), so the killing blow's card stays in Play as it does in the game.
That refusal is LIVE, not cosmetic: `JossPaper.CardsExhausted` is a
`[SavedProperty]` (JossPaper.cs:60-76) that no combat-end hook clears, and
every fight ending on an exhausting card over-credited it by one. Both
reshuffle hold-backs deleted — the exclusion is structural
(CardPileCmd.cs:870-871). NINE compensating de-hacks removed (cascade,
headbutt, Neow's Fury, Stack, the colorless return-to-hand, Corruption,
Rebound, and the two reshuffles). `relics/pen_nib.py` now reads
`card not in player.play_pile`, PenNib.cs:120-128 verbatim; `_playing_card`
survives with ZERO readers, documented as such.

**creature_card_cmds step99** — CONFIRMED STALE 2026-08-01 (round 13 R5), and
its residue closed: phase 1 parks its picks in `play_pile` (CardPileCmd.cs:954)
instead of in no pile. Parking in no pile already matched the reshuffle
immunity (Shuffle reads Draw+Discard only, :870-871); what it missed was
`AllCards`, `pile_type_of`, the listener walk and
`combat_card_db.ordered_piles`. The entry's own close note also undercounted
its callers — `Cascade.cs:24` and `DistilledChaos.cs:27` are also
one-statement `AutoPlayFromDrawPile` calls and were still open-coding it; four
callers, not two.

**creature_card_cmds step51 (+ step50)** — CLOSED 2026-08-01 (round 13 R5),
machinery only. `CardCmd.discard_and_draw` ports CardCmd.cs:172-205 including
the append-then-hook order (:192-194), the once-for-the-batch draw (:197-200)
and the `AutoPlayType.SlyDiscard` tail (:201-204); `before_card_auto_played`
carries the AutoPlayType. Gambler's Brew and Gambling Chip both reroute, which
also fixes an asymmetry no record listed: the two open-coded copies fired
`AfterCardDiscarded` on opposite sides of the append. Dormant on content — no
sim card has the Sly keyword.

**creature_card_cmds step56** — NARROWED 2026-08-01 (round 13 R5).
`CardCmd.pile_index_sort_key` is CardCmd.cs:353-360 exactly (RAW PileType enum,
then the pre-removal index captured at :396 — Draw before Hand, NOT AllPiles
order) and is pinned. It raises KeyError on an unknown pile name rather than
defaulting to PileType.None, because :392-394 throws on a null pile before the
index is taken. Still no multi-card transform to apply it to, so the entry's
trigger is unchanged.

**creature_card_cmds G8** — NARROWED 2026-08-01 (round 13 R5), NOT closed. The
manual-play site (CardPileCmd.cs:683) is wired, plus four more Add-site
dispatches. But the guard's "four C# dispatch sites" enumeration is short:
`Add` is one C# method with many sim entry points, and `CardCmd.Exhaust` is
`Add(card, PileType.Exhaust)` (CardCmd.cs:242) — the source's ONLY add to that
pile — so every exhaust dispatches it in C# and none does in the sim. That is
step81's residue, exact diff in R5-report §8 F1. Blast radius is NOT the reason
it was deferred: `sts2_rl/` has ZERO `after_card_changed_piles` implementers
(the four ported Deck-filtering relics reach the sim through
`Relic.after_card_added_to_deck`, a different shim), so the dispatch is a
presence-gate no-op today. The reason is completeness: a faithful `Add` wiring
means `ExhaustCmd.exhaust` AND `discard_and_draw`'s :192 AND `discard_hand` AND
the hand/draw add helpers, and landing some is worse than landing none. 14
direct exhaust call sites, not ~30.

**creature_card_cmds (new) — the exit switch's combat-ending refusals are
LIVE.** Recorded as a lesson, not only a fix. The review rated them dormant
because `BlockCmd`/`DrawCmd`/`DamageCmd` and the draw each re-gate on
`IsOverOrEnding`. That enumerated the COMMANDS a hook reaches and not the hook:
`Hook.AfterCardExhausted` also reaches `JossPaper.CardsExhausted`, a
`[SavedProperty]` run-scoped counter no combat-end hook clears. Enumerate every
implementer, not every command.

**power/smoggy AfterCardEnteredCombat** — CLOSED 2026-08-01 (round 13 R5).
`all_cards` is now literally `AllPiles` with Play last, so all three of
SmoggyPower's sweeps see a card mid-play. The entry's STATED exposure never
reproduced: `_resolve_card_play` used to append the resolving card to the
DISCARD before the loop, so it was already inside `all_cards`. The issue text
also describes `AfterCardPlayed` (SmoggyPower.cs:22-37) while filed under
`AfterCardEnteredCombat` (:39-45, which does not sweep).

**power/ringing AfterCardEnteredCombat** — CLOSED 2026-08-01 (round 13 R5),
DERIVED not analogised. Structurally closed by `all_cards`, but the entry's
exposure was FALSE for ordinary cards (HEAD parked them in the discard, inside
`all_cards`) and TRUE for a POWER card mid-play, which HEAD put in no pile at
all — `RingingPower.AfterApplied` (RingingPower.cs:23-31) afflicts every
unafflicted card of ANY type, unlike Smoggy's Skill filter. Narrow, dormant for
the recorded reason (enemy-applied on the enemy's turn), real. Mis-filed the
same way smoggy's is (describes `AfterApplied`, keyed to
`AfterCardEnteredCombat`).

**power/corruption + power/rebound (R3's lane)** — CLOSED 2026-08-01 by R5's
chain seed. Executing both application orders shows the sim reproducing C#'s
order-INDEPENDENT pile and order-DEPENDENT stack (Hook.cs:1391-1406 credits
only the listener whose own call changed the value; ReboundPower.cs:32-39 then
decrements unconditionally): Corruption first -> Rebound abstains, amount stays
2; Rebound first -> Rebound ticks to 1; Exhaust either way. That closes
power/corruption's three named residues (Rebound's unconditional tick; the
exhaust happening inside the play-count loop instead of once at
CardModel.cs:1985; Corruption absent from the chain) and retires the
workarounds both power/rebound entries' close notes describe (`card.exhausts or
card.exhaust_on_next_play`, `card not in player.discard_pile`). Full text in
R5-report §7 of the fix pass.

**creature_card_cmds (new) — the play loop's IsDead early returns.**
`CardModel.OnPlayWrapper` returns out of the WHOLE method at :1896 (before the
loop), :1932 (after OnPlay), :1940 (after the enchantment), :1950 (after the
affliction) and :1960 (after AfterCardPlayed) — skipping the exit switch
(:1976-1991) and CheckForEmptyHand (:1992). The sim had one break-on-dead at
the loop tail. Landed by R5 with pins; :1950 has no sim counterpart (no ported
affliction has an OnPlay).

**creature_card_cmds (new) — result-pile hook before play-count hook.**
CardModel.cs:1890 precedes :1895; the sim asked for the play count first.
Fixed and pinned by R5. No listener observes it today.

**seam/power_cmd G4 cross-reference.**
`Hook.AfterModifyingCardPlayResultPileOrPosition` (CardModel.cs:1891-1894) and
`Hook.AfterModifyingCardPlayCount` (:2019) are the only two statements of
`OnPlayWrapper` with no sim counterpart after R5. Rebound folds its Decrement
into the modifier call, correctly gated now that the chain carries all three
PileType seeds; Nostalgia's is a Flash.

**RL observation (REPLACES the old F8 queue line).** R5's Play pile changes the
RL observation ONLY at a decision point suspended inside `OnPlay` (a
card-selection screen): the resolving card is counted in `play` instead of
`discard`, so the combat block's discard-size slot (`full_env.py:698`,
delta = 0.025 = one card) and one discard-composition slot (0.1 -> 0.0) differ.
Measured against a `git archive HEAD` export with the concurrent event lane
isolated into a third tree: combat env 5/5 byte-identical; run env 25/30
episodes byte-identical and the other 5 identical in length, reward AND action
sequence. NO trajectory changes. The two seeds that DO change trajectory and
reward (16, 17; seed 16 reward 7.0 -> 5.0) are 100%
`events/the_future_of_potions.py` — the isolation tree reproduces them
byte-for-byte including the `run.rng` state, and is identical to LIVE over every
step. No schema change, no checkpoint migration, conformance parity green. The
earlier "select_cards RNG draw-count cascade via Headbutt/Neow's Fury" root
cause was WRONG and is retired: the candidate list is N-1 on both trees
(executed), and the run env installs a card selector so the selectorless
fallback is never reached.
