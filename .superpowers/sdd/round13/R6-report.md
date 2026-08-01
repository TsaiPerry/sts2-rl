# R6 report — wire `run.reward_offer_selector`

Footprint touched: `sts2_rl/events/base.py` (`_accept_offer`, `:204-258` after
the edit — `offer_potion`/`offer_card_reward` bodies unchanged) and
`test/test_event_offer_screens.py` (4 new tests). **`sts2_rl/driver.py`,
`sts2_rl/run.py` and `sts2_rl/conformance/runner.py` were read and verified
but not edited** — §1 explains why none of the three needed a change.

## 0. Re-verifying the brief's map against the current tree

Read `R10-report.md` first, per instructions, then re-read every citation
against the live files rather than trusting either document:

- `events/base.py`: `_accept_offer` is at `:204-222`, `offer_potion` at
  `:224-229`, `offer_card_reward` at `:231-240` — **exactly as the brief
  cites**, unaffected by R10 (R10 never touched this file).
- `run.py`: `card_selector` param at `:134`, assignment at `:199` (brief said
  `:133`/`:196-198` — off by one line, immaterial). `offer_relic`
  (`:563-584`, selector read `:581-583`) and `offer_potion` (`:586-594`,
  selector read `:591-593`) both route through `self.reward_selector` —
  confirmed, and their line numbers moved from the brief's `:545-576` to
  `:563-594` (R10 inserted the `offer_rewards` backstop docstring above them,
  `run.py:530-561`) — **flagging this as a stale-but-harmless brief citation**,
  since the brief's own text already said "re-verify line numbers."
- `driver.py`: `run.card_selector = self._card_selector` / `option_selector`
  / `reward_selector` / `rewards_offerer` wiring is at `:301-307` (brief said
  `:296-302` — shifted by R10's docstring expansion, same non-issue).
  `_reward_selector` (`:365-383`) is unchanged in shape: `kind == "relic"` →
  REWARD_RELIC; everything else (including a bare `"potion"`) → builds
  `CombatRewards(room_type=RoomType.MONSTER, potion=item)` and asks
  REWARD_POTION. This is the **exact call shape** `RunState.offer_potion`
  already uses (`run.py:592`, `selector("potion", potion)`).
- `conformance/runner.py`: `_ForceWinDriver` at `:187`, `_ask_decision`'s
  dispatch table at `:247-282` (brief said `:247-268` — the table grew by a
  few lines from prior rounds' work, non-issue). **`DecisionKind.REWARD_POTION`
  has no explicit branch and falls to the default `return legal[0]`**
  (`:282`) — i.e. take when a belt slot is open, skip when it isn't. This is
  the SAME default every other already-existing `REWARD_POTION` ask in the
  sim goes through (Lost Coffer, Small Capsule, Toy Box potions via
  `_reward_selector`), so no runner change was needed to "answer the new
  decisions" — they answer through machinery that already exists and is
  already exercised by the conformance suite.
- C#: `RewardsSet.cs:153-196` (`Offer`), `Reward.cs:92/111-134`,
  `PotionReward.cs:76/95`, `CardReward.cs:183/313` — read in full, confirm the
  brief's framing: `RewardsCmd.OfferCustom` reward screens are cancelable
  take-or-skip screens in real (non-TestMode) play.

## 1. The fix — re-derived, not the brief's literal suggestion

The brief offered two shapes ("wire a new adapter in `driver.py`" OR "unify
`_accept_offer` onto the already-wired `reward_selector`, retire the second
name") and asked me to derive the actual shape from the C# and today's
conventions. Before building either, I probed the ACTUAL current behavior of
both consumers with a driver attached (a `RunDriver` whose `ask` always tries
to decline), against the **pre-fix** code:

```
drowning_beacon (offer_potion):    decisions_seen = [EVENT]        held_potions = ['glowwater']
the_future_of_potions (offer_card_reward): decisions_seen = [EVENT, SELECT_CARDS]  deck unchanged
```

This is the RED evidence (a driver-driven policy that tries to decline gets
the potion anyway, and no `REWARD_POTION`-shaped decision is ever raised) —
and it also revealed the brief's framing is **only half right**:

- **`offer_potion`'s six callers really do auto-accept in real play.**
  `Event.offer_potion` calls `self.run.add_potion(potion)` directly with
  nothing downstream to decline with — `_accept_offer`'s gate was the ONLY
  decline surface, and it never asked anything (no `reward_offer_selector`
  is defined anywhere outside the test helper). **This is the real, fixed
  gap.**
- **`offer_card_reward`'s one caller (`the_future_of_potions.py:95`) does
  NOT actually auto-accept in real play, and the brief's framing is wrong
  here.** `Event.offer_card_reward` calls
  `self.run.select_cards("card_reward", cards, 1)` downstream, and
  `"card_reward"` is already a member of `driver.py`'s `SKIPPABLE_PURPOSES`
  (`:98-101`) — so `RunDriver._card_selector` (`:334-355`) already asks a
  **skippable** `SELECT_CARDS` decision for it, and a driver-attached policy
  can already decline through that skip slot, independent of
  `_accept_offer`/`reward_offer_selector` entirely. The probe above proves
  this against the **unmodified, pre-fix** code (`decisions_seen` includes
  `SELECT_CARDS`, and the deck stayed at its pre-offer size when the policy
  tried to decline there).

Given that, wiring `_accept_offer` to ask a SECOND, real decision for
`"card_reward"` (either brief option, applied uniformly) would not fix
anything — it would **regress** the shape, asking a driver-attached policy
twice for what C#'s single `CardReward` screen (`OnSelect`/`OnSkipped`,
`CardReward.cs:183/313`) shows once, since `offer_card_reward`'s own two-call
structure (`_accept_offer` then `select_cards`) is outside my footprint
(`:231-240` is explicitly R2's territory) and can't be collapsed into one
call here.

**What I built** — a purpose-aware resolution order in `_accept_offer`
(`events/base.py:204-258`), not a driver.py adapter and not a blanket
retirement of `reward_offer_selector`:

1. `run.reward_offer_selector`, if explicitly installed (unchanged — this is
   what `test/test_event_offer_screens.py`'s `decline()` helper sets, and it
   still wins for either purpose, so every existing test in that file needed
   zero changes).
2. Else, for `purpose == "potion"` only: fall back onto `run.reward_selector`
   — the seam every `RunDriver` already wires unconditionally
   (`driver.py:303`), calling it exactly the way `RunState.offer_potion`
   already does (`selector("potion", payload)`). This is the actual fix:
   real play and the conformance `_ForceWinDriver` now ask a real
   `REWARD_POTION` decision instead of nothing.
3. `purpose == "card_reward"` and any other purpose: pass straight to the
   step-4 default (auto-accept) — deliberately NOT routed onto
   `reward_selector`, for the regression reason above.
4. No selector anywhere: `True` (auto-accept) — byte-identical to the
   pre-R6 default, preserving the brief's "watch item" (hundreds of
   selectorless unit tests must not change meaning).

**Why no changes to `driver.py` / `run.py` / `conformance/runner.py`:**
`run.reward_selector` and its `_reward_selector` potion branch already do
exactly what's needed with zero modification (§0); `conformance/runner.py`'s
existing default (`legal[0]`) already answers the new `REWARD_POTION` asks
correctly (§0, confirmed by the conformance suite staying green, §4). Adding
an unnecessary adapter would have been a second, redundant path onto the
same seam.

## 2. Verdict on the brief's own two footprint questions

- **RL action space** ("both decision kinds already exist... verify, state
  it"): confirmed. `REWARD_POTION` and `SELECT_CARDS` (skippable, purpose
  `"card_reward"`) are both fully wired in `run_env.py` — action decode
  (`:527-539`), action mask (`:558-563`), and observation (`:733-765`,
  including `PURPOSE_IDS`/`vocab.json:843` already containing
  `"card_reward"`). `test/test_run_env.py` (12/12) passed unmodified. No
  `run_env.py` change was needed, confirmed rather than assumed.
- **Conformance replay traversal**: confirmed — see §0's dispatch-table
  finding and §4's suite results. No recorded command names a per-offer
  potion take/skip (`grep`'d recording/runner code for `Potion` — only
  `BuyPotion`/`UsePotion` exist), consistent with the runner's own documented
  policy ("which reward is taken is choice-independent for the parity
  streams... a default that always progresses suffices," `runner.py:21-24`)
  — my new asks flow through that same pre-existing, already-tested default.

## 3. Tests

**New** (`test/test_event_offer_screens.py`, appended after the existing
"default" section — file went from 13 to 17 tests):

- `test_drowning_beacon_declines_through_a_real_driver_with_no_explicit_
  selector` — **RED-first** (proven via an ad-hoc probe against the
  unmodified code before writing the fix, §1's transcript: a driver whose
  policy always tries to skip `REWARD_POTION` never got asked and got the
  potion anyway). GREEN after the fix: `REWARD_POTION` is now in the
  decisions seen and the potion is declined.
- `test_drowning_beacon_still_defaults_to_take_through_a_real_driver` —
  regression guard: a driver that always answers the first legal action
  still ends up with the potion (the fix changes whether the player is
  asked, not what a take answer does).
- `test_explicit_reward_offer_selector_still_overrides_the_driver_seam` —
  the finer-grained explicit override still wins over the new
  `reward_selector` fallback with a real driver attached (the two seams
  don't fight).
- `test_the_future_of_potions_card_offer_already_declines_through_
  select_cards` — pins §1's surprising finding: a driver-attached policy can
  already decline this screen via `SELECT_CARDS`'s skip slot, unaffected by
  (and not requiring) the potion-purpose fix above.

**Commands run and counts:**

```
py -m pytest test/test_event_offer_screens.py -v
  → 17 passed

py -m pytest test/test_event_offer_screens.py test/test_driver.py test/test_rng_tripwire.py -q
  → 63 passed

py -m pytest test/ -k "event" -q
  → 430 passed, 3413 deselected

py -m pytest test/test_conformance_runner.py -v
  → 11 passed   (baseline maintained — see below)

py -m pytest test/test_conformance_map.py test/test_conformance_player_state.py \
  test/test_conformance_floor_state.py test/test_conformance_combat.py \
  test/test_conformance_pools.py test/test_conformance_relic_bag.py \
  test/test_conformance_rooms.py -q
  → 2 failed, 69 passed, 6 xfailed
  (the 2 failures are test_conformance_floor_state.py's known missing-fixture
  gap named in PROTOCOL.md — 933T39V18D/floor_49/actions.sts2replay does not
  exist on disk — confirmed by FileNotFoundError trace, not a regression, not
  counted, not touched)

py -m pytest test/test_conformance_recording.py test/test_conformance_save.py \
  test/test_conformance_determinism.py -q
  → 18 passed

py -m pytest test/test_run_env.py -q
  → 12 passed
```

`test_rng_tripwire.py`'s watch item (brief: "pins driver.py line numbers")
was already stale before I started — R10 found and fixed this (the allowlist
is function-keyed, not line-keyed) — and I didn't touch `driver.py` at all,
so it's doubly moot here; re-confirmed passing regardless (63-test batch
above).

`git status` confirms my only unstaged changes are `sts2_rl/events/base.py`
and `test/test_event_offer_screens.py`; every other modified file in the
worktree (driver.py, run.py, hooks.py, powers.py, combat.py, the audit
records, etc.) is either already staged by the controller or another lane's
in-flight work I did not touch.

## 4. Findings not in the brief

1. **The brief's central claim ("every take-or-skip EVENT screen
   auto-accepts in real play") is only half true, and the half that's false
   is provable, not speculative.** `offer_card_reward`'s decline path
   already worked with a driver attached, before any R6 change, via
   `SELECT_CARDS`'s pre-existing `SKIPPABLE_PURPOSES` membership for
   `"card_reward"`. This is the single most load-bearing finding in this
   report — it's why the fix is purpose-asymmetric instead of uniform, and
   it changes what `event/the_future_of_potions/g15`'s "separate, larger
   concern" note should say (see §5).
2. **`run.py`'s `offer_relic`/`offer_potion` line numbers drifted from the
   brief's citation** (`:545-576` → `:563-594`) — R10's `offer_rewards`
   docstring expansion pushed them down; harmless, noted for the next lane
   that cites this file.
3. Confirmed (not new, but worth stating since I was asked to re-derive
   rather than trust the brief): the brief's suggested driver.py adapter
   shape was never actually necessary — `run.reward_selector`'s existing
   `else`-branch (assume-potion) already IS that adapter, built for
   `RunState.offer_potion` and reusable verbatim.

## 5. Record-close proposals

I did not edit `audit/records/**` or `audit/GAP-QUEUE.md`.

### `audit/records/event/the_future_of_potions.json` — last guard ("G-new",
informally `g15`)

**Verdict: unchanged (`gap`, `live: true`).** The reroll-surface half of this
guard (`Event.offer_card_reward` skips `Hook.ModifyRewards`, so Driftwood
can't reroll this screen) is untouched by R6 and stays open — it needs new
capability (R2's territory), not wiring.

**Propose replacing the guard's trailing paragraph** — currently:

> "SEPARATE, LARGER CONCERN recorded here for want of a better home:
> run.reward_offer_selector is never wired by driver.py (set only in test
> files, verified by repo-wide grep), so take-or-skip screens AUTO-ACCEPT in
> real play. That is pre-existing and out of Task 32's scope, but it is a
> bigger divergence than the reroll flag and needs its own task."

with:

> "**R6 update (2026-08-01, round 13):** the wiring concern above is now
> RESOLVED for the potion half and CORRECTED for the card half.
> `Event._accept_offer` (events/base.py) now falls back onto
> `run.reward_selector` — the seam every RunDriver already wires
> unconditionally (driver.py:303) for RunState.offer_relic/offer_potion —
> for `purpose == "potion"` when no `reward_offer_selector` is explicitly
> installed, so drowning_beacon / endless_conveyor / potion_courier (x3) /
> the_legends_were_true / wellspring / whispering_hollow's potion offers are
> now real REWARD_POTION decisions in real play and in the conformance
> `_ForceWinDriver`, not permanent auto-accepts. For `purpose ==
> "card_reward"` (THIS event's own screen), the 'auto-accept in real play'
> characterization was WRONG once a driver is attached: `Event.
> offer_card_reward`'s downstream `run.select_cards('card_reward', ...)` was
> ALREADY skippable (driver.py's SKIPPABLE_PURPOSES, wired unconditionally
> via `run.card_selector`, driver.py:301) independently of
> `reward_offer_selector` — proven against the pre-R6 code by an ad-hoc
> probe (a driver-attached policy that always tries to decline the card
> already left the deck untouched) and pinned by
> `test_the_future_of_potions_card_offer_already_declines_through_
> select_cards` (test/test_event_offer_screens.py). `_accept_offer`
> deliberately leaves `purpose == 'card_reward'` a pass-through rather than
> adding a second, redundant ask on top of the one that already worked.
> `run.reward_offer_selector` itself remains a **test-only** override with
> zero production writers by design (`driver.py` never assigns it; only
> `test/test_event_offer_screens.py:37` does) — it is no longer
> load-bearing, because `_accept_offer` now reaches the driver through
> `run.reward_selector` for potion offers instead. A repo-wide grep finding
> `reward_offer_selector` unwired by `driver.py` is therefore expected, not
> a re-opened gap. The reroll-surface gap above is UNCHANGED, remains open,
> and belongs on the **REWARD_CARD** decision, not on `SELECT_CARDS`: C#
> puts Skip and REROLL as alternatives on the card-selection screen itself
> (`CardRewardAlternative.cs:53-74`, reached from `CardReward.cs:189`),
> which the sim already models at `driver.py:207-214` / `_offer_card_group`
> (`driver.py:519-542`). Closing G-new therefore most likely means routing
> `Event.offer_card_reward` through `run.offer_rewards` (picking up
> `apply_reward_modifiers` via R10's offer-time backstop, `run.py:530-561`)
> and retiring `_accept_offer`'s `card_reward` pass-through, not extending
> `RunState.select_cards`."

**What reasoning this replaces:** the claim that the wiring gap was
"pre-existing... needs its own task" undifferentiated across both purposes.
It wasn't undifferentiated — one purpose (`"potion"`) had a real, fixable
gap; the other (`"card_reward"`) never had the gap the note implied, because
a different, already-existing mechanism already covered it.

### `audit/records/event/{drowning_beacon,endless_conveyor,potion_courier,
the_legends_were_true,wellspring,whispering_hollow}.json` — EV-4 guards

**No change proposed.** Each guard's `maps_to` text already describes the
mechanism accurately as written ("`_accept_offer`... consults the run's
`reward_offer_selector`... and only grants the reward when the screen is
taken") — it never claimed a selector was reachable in real play, so R6
doesn't make these six records more or less true. Their `verdict: faithful`
stands. (Optional, not proposed: the controller could append a one-line note
to each pointing at the g15 amendment above for context; I judged six
near-identical edits for a narrative cross-reference not worth the review
overhead versus one shared pointer in g15 itself.)

## 6. Queue-annotation proposals (`GAP-QUEUE.md`, terse style)

**Location 1 — "Still open, found this round, owned by nobody" (Round 12
section, lines 79-83).** Replace:

> "- `run.reward_offer_selector` is **never wired by `driver.py`** (set only
> in test files), so take-or-skip reward screens auto-accept in real play.
> Pre-existing and larger than the flag it was found beside."

with:

> "- ~~`run.reward_offer_selector` is never wired by `driver.py`...~~
> **CLOSED for potion offers, CORRECTED for card offers, 2026-08-01 (round
> 13, R6):** `Event._accept_offer` (events/base.py) now falls back onto
> `run.reward_selector` — the seam every RunDriver already wires
> unconditionally (driver.py:303) for RunState.offer_relic/offer_potion —
> for `purpose=="potion"` when no `reward_offer_selector` is explicitly
> installed, so the six events offering a bare PotionReward ask a real
> REWARD_POTION decision in real play and in the conformance
> `_ForceWinDriver` instead of permanently auto-accepting.
> `purpose=="card_reward"` (the_future_of_potions' sole screen) turned out
> to be a WRONG premise, not a gap: its decline path already runs through
> `RunState.select_cards`'s SKIPPABLE_PURPOSES ('card_reward', driver.py),
> wired unconditionally via `run.card_selector` (driver.py:301) — a
> driver-attached policy could already decline it before R6 too.
> `run.reward_offer_selector` itself stays deliberately unwired by
> `driver.py` — it is a test-only override now, with zero production
> writers by design, because `_accept_offer` reaches the driver through
> `run.reward_selector` instead; a future grep finding it unwired is
> expected, not a re-opened gap. See `event/the_future_of_potions/g15`'s
> updated note."

**Location 2 — section "3C. `event`" (lines 2708-2712).** Replace:

> "**Separate and larger, found in the same pass:** `run.reward_offer_
> selector` is never wired by `driver.py` (set only in test files, confirmed
> by repo-wide grep), so take-or-skip reward screens AUTO-ACCEPT in real
> play. Pre-existing, out of Task 32's scope, recorded on
> `event/the_future_of_potions/g15` for want of a better home, and worth
> more than the reroll flag it was found beside."

with:

> "**Separate and larger, found in the same pass — closed/corrected
> 2026-08-01 (round 13, R6):** the 'auto-accept in real play' claim was
> right for the six events wrapping a bare `Event.offer_potion` and wrong
> for this event's own `Event.offer_card_reward` screen. `_accept_offer`
> now falls back onto the already-wired `run.reward_selector` for
> `purpose=='potion'` (fixing the six); `purpose=='card_reward'` was found
> to already decline correctly through `RunState.select_cards`'s existing
> SKIPPABLE_PURPOSES machinery whenever a real driver is attached, so
> nothing there needed a fix — `_accept_offer` stays a deliberate
> pass-through for it, to avoid asking a driver-attached policy twice for
> the one screen C# shows. `run.reward_offer_selector` itself remains a
> test-only override with zero production writers by design (no longer
> load-bearing since the potion half now goes through `run.reward_selector`
> instead); a repo-wide grep finding it unwired by `driver.py` is expected,
> not a gap. The reroll-surface gap above (G-new) is UNCHANGED, stays open,
> and belongs on the **REWARD_CARD** decision — not `SELECT_CARDS` — per
> C#'s single `{cards…, Skip, REROLL}` screen (`CardRewardAlternative.cs:
> 53-74`, `CardReward.cs:189`; sim shape at `driver.py:207-214` /
> `driver.py:519-542`); closing it most likely means routing
> `Event.offer_card_reward` through `run.offer_rewards` and retiring
> `_accept_offer`'s `card_reward` pass-through, not extending
> `RunState.select_cards`."

No change proposed to line 35's "7 remaining live mechanisms... 
`event/the_future_of_potions/g15` (new this round)" listing — that mechanism
is still correctly counted live (the reroll-surface half stays open).

## Status

DONE. Both halves of the brief's target gap are settled: the real one
(potion offers) is fixed and pinned; the other (card offers) is proven to
have never needed this fix, which is itself the more important finding for
whoever picks up R2's reroll-surface work next.

**Correction (2026-08-01, fix pass):** this section originally closed by
telling R2 to build the reroll surface "straight onto
`RunState.select_cards`'s existing skip mechanism." That advice is wrong
against the C#, and the reviewer overturned it with a citation I have now
verified directly against the source: `CardRewardAlternative.Generate`
(`CardRewardAlternative.cs:53-74`) puts **both** Skip (`:56-59`, gated on
`CardReward.CanSkip`, which defaults `true`, `CardReward.cs:95`) **and**
REROLL (`:60-67`, Driftwood, `PostAlternateCardRewardAction.DoNothing` =
re-show the same screen) as alternatives on the card-selection screen
itself, generated from inside `CardReward.OnSelect` (`CardReward.cs:183`,
the `Generate` call at `:189`). C# therefore shows **one screen** — `{card0,
card1, card2, Skip, REROLL}` — never a prior accept/decline gate followed
by a separate reroll ask. The sim already models exactly that shape on the
**REWARD_CARD** decision, not on SELECT_CARDS: `DecisionRequest.own_actions`
reserves slot `n+1` for Driftwood's reroll and `n+2` for Pael's Wing's
sacrifice (`driver.py:207-214`), and `RunDriver._offer_card_group`
(`driver.py:519-542`) already implements the reroll-and-re-ask loop. R2's
correct move is therefore almost certainly to migrate
`Event.offer_card_reward` off `select_cards`/SELECT_CARDS and onto
`run.offer_rewards`/REWARD_CARD instead — which also picks up
`apply_reward_modifiers` (R10's offer-time backstop, `run.py:530-561`), the
actual G-new gap, for free — and to retire `_accept_offer`'s
`"card_reward"` pass-through once that migration lands. Bolting a reroll
onto SELECT_CARDS would duplicate machinery that already exists on
REWARD_CARD and would diverge from C#'s single-screen shape. None of this
migration is R6's work; it is corrected here only so it does not misdirect
R2.

## Fix pass (2026-08-01)

Applied per `R6-review.md` (verdict NEEDS-FIXES, narrow). `events/base.py`
was **not touched** — the reviewer approved the engine change as written,
and every required fix was prose (F1/F2) or test-only (F4).

- **F1 — wrong parting advice to R2, corrected.** Verified the reviewer's
  citation myself against the decompiled source
  (`CardRewardAlternative.cs:1-75`, `CardReward.cs:170-269`):
  `CardRewardAlternative.Generate` (`:53-74`) really does add both `"Skip"`
  (`:56-59`, `CardReward.CanSkip` gate, default `true` at `CardReward.cs:95`,
  not overridden by `TheFutureOfPotions.cs`) and `"REROLL"` (`:60-67`,
  Driftwood, `PostAlternateCardRewardAction.DoNothing`) as alternatives
  returned into the *same* card-reward screen, which `CardReward.OnSelect`
  (`:183`) opens by calling `Generate(this)` at `:189` and then dispatches
  through one loop (`:194-269`) that reads a single index across
  `{cards…, alternatives…}`. There is no second, prior accept/decline
  screen in the source. Confirmed against the sim side too:
  `driver.py:207-214` (`DecisionRequest.own_actions` for REWARD_CARD
  reserves `n+1`=reroll, `n+2`=Pael's Wing sacrifice) and
  `RunDriver._offer_card_group` (`driver.py:519-542`, the reroll-and-re-ask
  loop) already implement exactly that one-screen shape today — on
  REWARD_CARD, not SELECT_CARDS. Rewrote: the report's closing "Status"
  section (previously told R2 to build onto `RunState.select_cards`'s skip
  mechanism — now says the reroll surface belongs on REWARD_CARD, and that
  R2's move is most likely migrating `Event.offer_card_reward` onto
  `run.offer_rewards`/REWARD_CARD, which also closes the actual G-new gap
  via R10's `apply_reward_modifiers` backstop, and retiring `_accept_offer`'s
  `card_reward` pass-through at that point); the `g15` record-note proposal
  in §5; and the Queue Location 2 proposal in §6. Queue Location 1 does not
  mention the reroll surface at all, so F1 did not apply there.

- **F2 — `run.reward_offer_selector` is still unwired, now stated
  explicitly.** Re-confirmed by grep (`sts2_rl/`, `test/`,
  `.superpowers/sdd/`): `driver.py` never assigns `reward_offer_selector`
  anywhere; its only production reader is the `getattr(self.run,
  "reward_offer_selector", None)` this fix pass's engine change added
  (`events/base.py:251`); its only writer anywhere in the tree is
  `test/test_event_offer_screens.py:37`. That is expected, not a leftover
  gap: `_accept_offer` now reaches a real driver for potion offers through
  `run.reward_selector` (the seam `driver.py:303` already wires
  unconditionally), so `reward_offer_selector` only still exists as a
  finer-grained, opt-in **test override** that wins when a test explicitly
  installs it (pinned by
  `test_explicit_reward_offer_selector_still_overrides_the_driver_seam`).
  Added a clause saying exactly this — flag name, unwired status, and why
  that is now correct rather than a hole — to all three prose sites: the
  `g15` record-note proposal (§5), Queue Location 1 (§6), and Queue Location
  2 (§6). A future repo-wide grep for `reward_offer_selector` will still
  find it unwired by `driver.py`; that grep result is now explained inline
  wherever the mechanism is documented, so it should not be re-opened as a
  gap on sight.

- **F4 — redundant `.begin()` removed from all four new tests.**
  `test/test_event_offer_screens.py`: the four tests that call
  `driver._run_event(ev)` (`test_drowning_beacon_declines_through_a_real_
  driver_with_no_explicit_selector`, `test_drowning_beacon_still_defaults_
  to_take_through_a_real_driver`, `test_explicit_reward_offer_selector_
  still_overrides_the_driver_seam`, `test_the_future_of_potions_card_offer_
  already_declines_through_select_cards`) previously built the event with
  `make_event(...).begin()` and then handed it to `driver._run_event(ev)`,
  which itself calls `event.begin()` at `driver.py:557` — a double
  `begin()`, i.e. `calculate_vars` running twice and double-spending the
  event RNG (harmless for these three events, but the wrong pattern to
  demonstrate). Changed all four call sites from `make_event(id, run)
  .begin()` to `make_event(id, run)`, letting `driver._run_event` be the
  sole caller of `begin()`, matching how every other driver-driven call site
  in the codebase (`driver.py:394,429,634,649`) uses `make_event`.

- **Reviewer's evidence adopted verbatim (not re-derived), because it
  corrects what "green" means for this change:** the conformance suite this
  report cited in §3/§0 (`test_conformance_*.py`, 77 passed/6 xfailed) only
  proves the wave-13 default: `ReplayRunner.run(stop_after_act=0)`
  (`runner.py:767`) never walks far enough to reach `Event._accept_offer` on
  any of the 15 recordings (reviewer instrumented `accept_offer_calls=[]`
  for every seed/floor at act 0) — so that suite passing was **not
  evidence** about this change, contrary to how §3 originally presented it.
  The reviewer re-drove all 15 recordings through `stop_after_act=2`, which
  *does* reach the relevant events (`the_future_of_potions` on
  TZEKRYTSNT/floor_34 and /floor_49, `drowning_beacon` on QRWCVDPZN5,
  `the_legends_were_true` on DJDCSAQZNR), and found the pre-fix and post-fix
  walks **identical** on every recording (rooms walked, `reached_act_end`,
  divergence count, stop reason unchanged) — e.g. TZEKRYTSNT/floor_49:
  `(45, True, 4, 'reached act 2 boss')` both before and after. The
  mechanism is safe by construction, not by luck: `_ForceWinDriver.
  _ask_decision` has no REWARD_POTION branch and falls to `return legal[0]`
  (`runner.py:282`), and `DecisionRequest.own_actions` for REWARD_POTION
  (`driver.py:215-220`) yields `[0, 1]` with an open belt slot and `[1]`
  without — i.e. take-when-possible, skip-when-not, which is bit-for-bit
  the pre-fix outcome (pre-fix auto-accepted, then `add_potion` silently
  refused a full belt). **This act-2 walk, not the act-0 conformance suite,
  is the real evidence that R6 changed nothing about conformance replay.**
  Recording it here so the next reader of this report does not repeat §3's
  overstatement of what the act-0 suite proves.

**Commands run this pass:**

```
py -m pytest test/test_event_offer_screens.py -q
  -> 17 passed

py -m pytest test/test_event_offer_screens.py test/test_driver.py test/test_rng_tripwire.py -q
  -> 63 passed

py -m pytest test/ -k "event" -q
  -> 431 passed, 3441 deselected
```

No regressions. No production file was edited (`git status` confirms this
pass's only changes are `test/test_event_offer_screens.py` and this report;
`sts2_rl/driver.py` / `sts2_rl/run.py` show as modified in the worktree but
that is other lanes'/the controller's in-flight state, not this pass, and
`sts2_rl/events/base.py`'s prior modification is the already-approved
engine change from before this fix pass, untouched here).
