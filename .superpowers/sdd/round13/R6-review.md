# R6 review — wire `run.reward_offer_selector`

Reviewer verdict: **NEEDS-FIXES** — narrowly, and **not in `events/base.py`**.
The engine change is correct, minimal and better-derived than the brief's own
suggestion; I am approving it as written. The fixes are to two pieces of
**prose the controller applies nearly verbatim** (the record note's forward
advice to R2 is wrong against the C#; the queue/record text omits a fact that
will cause this gap to be re-found by grep), plus one 4-line test cleanup.

Everything below was established by execution unless marked "read".

---

## 0. THE CENTRAL RULING — premise correction: **CONFIRM**

The implementer claims the brief's premise ("every take-or-skip EVENT screen
auto-accepts in real play") is half wrong: `Event.offer_card_reward` never
auto-accepted with a driver attached, because its decline already ran through
`RunState.select_cards` → `RunDriver._card_selector` → `SKIPPABLE_PURPOSES`.

**Confirmed, by executing the pre-fix code.** I reinstated HEAD's
`_accept_offer` body in memory (monkeypatch — never on disk, per PROTOCOL's ban
on temporary reverts in a live tree) and drove both consumers through a real
`RunDriver`:

```
A.  PRE-FIX `offer_card_reward` (the_future_of_potions) through a REAL driver
      DECLINE policy   decisions=['event','select_cards']   deck 10 -> 10  (delta 0)
      TAKE    policy   decisions=['event','select_cards']   deck 10 -> 11  (delta +1)

A2. PRE-FIX `offer_potion`, all 8 call sites, decline-everything policy
      drowning_beacon       BOTTLE                decisions=['event']  potions=['glowwater']
      wellspring            BOTTLE                decisions=['event']  potions=['ship_in_a_bottle']
      the_legends_were_true SLOWLY_FIND_AN_EXIT   decisions=['event']  potions=['ship_in_a_bottle']
      potion_courier        GRAB_POTIONS          decisions=['event']  potions=[x3 foul_potion]
      potion_courier        RANSACK               decisions=['event']  potions=['radiant_tincture']
      whispering_hollow     GOLD                  decisions=['event']  potions=[dexterity, shackling]
```

A decline-everything policy against the **pre-R6 code** already left the deck
untouched on the card screen (delta 0) and could not stop a single one of the
eight potion grants. That is the premise correction, proven in both directions:
the card half never had the gap; the potion half had it at every site.

The C# then makes the correction *stronger* than the implementer argued — see
§3. Ruling: **CONFIRM.**

---

## 1. Item (a) — did `offer_card_reward` really surface a decline pre-fix?

**PROVEN — yes.** Trace, then execution.

Read trace: `Event.offer_card_reward` (`events/base.py:271-273`) calls
`self.run.select_cards("card_reward", cards, 1)`; `RunState.select_cards`
(`run.py:511-512`) delegates to `self.card_selector`, which **every**
`RunDriver` installs unconditionally at construction (`driver.py:301`);
`_card_selector` (`driver.py:334-355`) computes `skippable = purpose in
SKIPPABLE_PURPOSES` and `"card_reward"` is a member (`driver.py:98-101`), so it
raises a SELECT_CARDS whose `own_actions` include the skip slot
(`driver.py:226-230`) and honours it at `:352-353`.

Execution beat reading, as instructed: probe A above, run against the
**unmodified pre-fix body**, shows `select_cards` in the decision list and a
deck delta of 0 under a declining policy versus +1 under a taking one. The
brief's "every take-or-skip EVENT screen auto-accepts" is therefore **false for
`offer_card_reward` with any real driver attached**, and the round-12 record
that said so is wrong on this half.

Bare `RunState` (no driver): `select_cards` falls to `self.rng.sample`
(`run.py:514`) and always takes a card — unchanged by R6, and correct as the
unit-test convention.

## 2. Item (b) — the six `offer_potion` callers

**Caller list verified independently of the brief** (`grep` over `sts2_rl/`,
`events/base.py` excluded): 8 call sites in 6 event files —
`drowning_beacon.py:30`, `endless_conveyor.py:130`, `potion_courier.py:49`,
`:62`, `:79`, `the_legends_were_true.py:49`, `wellspring.py:32`,
`whispering_hollow.py:68`. The brief's list is **correct**. `_accept_offer` has
exactly two callers and therefore exactly two purposes ever reach it
(`events/base.py:263`, `:271`).

**They auto-accepted:** probe A2 above — only an `event` decision was ever
raised; every potion landed despite a policy that declines everything.

**They ask now:** probe B, post-fix, decline-everything policy —

```
OK drowning_beacon       BOTTLE               reward_potion asks=1 (expect 1)  potions=[]
OK wellspring            BOTTLE               reward_potion asks=1 (expect 1)  potions=[]
OK the_legends_were_true SLOWLY_FIND_AN_EXIT  reward_potion asks=1 (expect 1)  potions=[]
OK potion_courier        GRAB_POTIONS         reward_potion asks=3 (expect 3)  potions=[]
OK potion_courier        RANSACK              reward_potion asks=1 (expect 1)  potions=[]
OK whispering_hollow     GOLD                 reward_potion asks=2 (expect 2)  potions=[]
```

**The ask COUNTS match the C# reward-set shapes**, which I checked rather than
assumed: `PotionCourier.cs:41-43` builds a list in a loop and hands it to ONE
`OfferCustom` (→ 3 independent `PotionReward`s, 3 take/skip buttons, 3 sim
asks); `PotionCourier.cs:55-57` is the separate RANSACK branch with one;
`WhisperingHollow.cs:53-56` is one `OfferCustom` with **two** `PotionReward`s.
`DrowningBeacon.cs:41-43`, `EndlessConveyor.cs:156-158`,
`TheLegendsWereTrue.cs:56-58`, `Wellspring.cs:36-38` are one each. **None of
the seven calls `WithSkippingDisallowed`** (`RewardsSet.cs:115-119`, whose only
caller in the whole source is Neow's Bones), so every one of these screens is
genuinely declinable — the fix is warranted at all 8 sites.

## 3. Item (c) — the double-ask argument, ruled against the C#

**The implementer is right, and the C# supports them more strongly than their
own argument did.** Their case was "OnSelect/OnSkipped is one screen, not two".
The actual C# is better than that:

`CardReward.OnSelect` (`CardReward.cs:183`) opens the card screen with
`CardRewardAlternative.Generate(this)` (`CardReward.cs:189`), and
`CardRewardAlternative.Generate` (`CardRewardAlternative.cs:53-74`) puts

- **"Skip"** — `CardRewardAlternative.cs:56-59`, gated on `CardReward.CanSkip`,
  which defaults to `true` (`CardReward.cs:95`) and is not overridden by
  `TheFutureOfPotions.cs:128-130`'s plain `new CardReward(options, 3, Owner)`;
- **"REROLL"** — `CardRewardAlternative.cs:60-67` (Driftwood), with
  `PostAlternateCardRewardAction.DoNothing`, i.e. re-show the same screen;

as options **on the card-selection screen itself**, dispatched at
`CardReward.cs:244-256`. So C#'s take-or-skip for a `CardReward` is literally
**one screen offering `{card0, card1, card2, Skip, REROLL}`** — a second,
prior accept/decline decision does not exist in the source. Wiring
`_accept_offer("card_reward", …)` onto a real selector would have invented a
decision the game does not have. **The pass-through is correct.**

The outer `NRewardsScreen` button (`NRewardsScreen.cs:194-196`, `RewardClaimed`
/ `RewardSkipped`) is the reward *list*, not a second decision about this
reward's contents, and the two decline routes converge on identical state:
in-screen Skip → `OnSelect` returns `false` → `SelectUnsynchronized`
(`Reward.cs:120-134`) leaves `SuccessfullySelected` false → the reward stays in
the set → set completion runs `CardReward.OnSkipped` (`CardReward.cs:313-320`)
via `RewardsSetSynchronizer.cs:344-353`, exactly as the outer skip does. Same
history entries, same hooks (`Hook.AfterRewardTaken` fires only on success,
`Reward.cs:125`).

**Does the sim now ask exactly once?** Yes, measured (probe B3, post-fix):

```
the_future_of_potions  DECLINE policy  decisions=['event','select_cards']  deck 10
the_future_of_potions  TAKE    policy  decisions=['event','select_cards']  deck 11
```

One card decision, either way. And one potion decision per `PotionReward`
(probe B). **No double-ask anywhere.**

---

## 4. The other verification items

### Default with NO driver still auto-accepts — **PASS, and pinned**

Probe C, bare `RunState`: all six events keep their potions,
`the_future_of_potions` still adds its card (`deck delta=+1`), and
`hasattr(run, 'reward_selector') == False` — so the new fallback is
unreachable without a driver. The guard is structural (`getattr(..., None)`,
`events/base.py:255-257`) *and* pinned by the pre-existing parametrized test
(`test_event_offer_screens.py:160-170`). Independently: **all 13 pre-existing
tests in that file pass unchanged against both the pre-fix and post-fix
bodies** (§6), which is the real evidence that the hundreds of selectorless
event tests keep their meaning.

### No event's GRANTS changed — **PASS**

Probe D ran every affected event under a take-everything policy against the
pre-fix and post-fix bodies and compared held potions, deck contents, HP and
gold:

```
SAME drowning_beacon / wellspring / the_legends_were_true / potion_courier x2
SAME whispering_hollow (gold 166 both) / the_future_of_potions (deck 11 both)
```

Only *whether the player is asked* changed. The brief's third watch item holds.

### Conformance replay path — **PASS, and I went past what the suite proves**

The suite is green with the change: `test_conformance_{runner,map,player_state,
combat,pools,relic_bag,rooms}.py` → **77 passed, 6 xfailed** (the 2 known
`test_conformance_floor_state.py` failures are the missing 933T floor_49
fixture; excluded, not counted, not touched).

But green here is nearly vacuous, and the implementer did not notice why: the
conformance tests call `ReplayRunner.run(stop_after_act=0)`
(`runner.py:767`), and **on all 15 recordings the act-0 walk never reaches
`Event._accept_offer` at all** (instrumented: `accept_offer_calls=[]` for every
seed/floor). So the suite passing is not evidence about R6.

I therefore drove all 15 recordings through `stop_after_act=2`. That walk
*does* reach the relevant events — `the_future_of_potions` (TZEKRYTSNT/floor_34
and /floor_49, one `('the_future_of_potions','card_reward')` call),
`drowning_beacon` (QRWCVDPZN5), `the_legends_were_true` (DJDCSAQZNR) — and
**pre-fix vs post-fix walks are identical on every recording** (rooms walked,
`reached_act_end`, divergence count, stop reason), e.g.

```
TZEKRYTSNT floor_49  PRE (45, True, 4, 'reached act 2 boss')  POST (45, True, 4, ...)  IDENTICAL
QRWCVDPZN5 floor_34  PRE (31, False, 2, 'no more MoveToMapCoord') POST (31, False, 2, ...) IDENTICAL
DJDCSAQZNR floor_49  PRE (45, True, 0, 'reached act 2 boss')  POST (45, True, 0, ...)  IDENTICAL
```

And the mechanism is safe by construction, not by luck: `_ForceWinDriver.
_ask_decision` has no REWARD_POTION branch and falls to `return legal[0]`
(`runner.py:282`); `DecisionRequest.own_actions` for REWARD_POTION
(`driver.py:215-220`) yields `[0, 1]` with a free belt slot and `[1]` without —
so the runner takes when it can and skips when the belt is full, which is
**bit-for-bit the pre-fix outcome** (pre-fix auto-accepted, then `add_potion`
refused a full belt). That default is already live 2–5 times per recording from
post-combat potion rewards. **"conformance/runner.py needed no change" is TRUE
and now demonstrated, not merely untested.** Verdict on the implementer's claim:
correct; on their evidence for it: insufficient (suite-green only), which I have
now supplied.

### RL action space — **PASS (read + test)**

`REWARD_POTION` decode (`run_env.py:540-543` generic choice-slot path), mask
(`:566-570`), observation (`:748-753`, reading `rewards.potion` — which
`_reward_selector` populates at `driver.py:379`); `"card_reward"` is in
`vocab.json:843`. `test_run_env.py` green unmodified. No `run_env.py` change
needed; the implementer confirmed rather than assumed, as asked.

### `test_rng_tripwire.py` watch item — **moot, correctly reported**

The allowlist is keyed by (file, **function**), not line (`test_rng_tripwire.py:
9-17` documents exactly why), and R6 does not touch `driver.py`. Green.

---

## 5. Spec-compliance and code-quality verdicts

**Spec compliance: PASS.** The chosen shape — resolution order in
`_accept_offer` with `purpose == "potion"` falling back onto the already-wired
`reward_selector` — is derived from the C# rather than from the brief, which is
what the brief asked for. It reuses the seam `RunState.offer_potion`
(`run.py:591-593`) already calls with the identical `("potion", potion)`
signature, so the sim now surfaces relic-sourced and event-sourced
`PotionReward`s through one decision kind, matching C#, where both are just
`RewardsCmd.OfferCustom` (`RewardsCmd.cs:47-50`). Footprint respected: the
brief reserved `:231-240` for R2 and `offer_card_reward`'s body is byte-
unchanged. No `driver.py` / `run.py` / `conformance/runner.py` edit was needed
and none was made — correct restraint; a `driver.py` adapter would have been a
second path onto a seam that already exists.

**Code quality: PASS with nits.**
- The 8-line body is right: explicit-override first, purpose-scoped fallback,
  default `True` last. Reads cleanly and the `getattr` guards keep bare
  `RunState` safe.
- Nit: the docstring hard-codes `driver.py:301` / `:303` / `run.py:592`. All
  three are accurate today (verified), but this repo has already been bitten
  by exactly this — `test_rng_tripwire.py:12-17` records a gate re-opening
  because six added comment lines moved `_ask`. Prefer naming
  `RunDriver.__init__`'s wiring block by function.
- Nit: 47 lines of docstring for an 8-line function is at the top of the house
  style, but it is the house style. Not a finding.

**PROTOCOL compliance: PASS.** `git diff --name-only` for this lane is exactly
`sts2_rl/events/base.py` + `test/test_event_offer_screens.py`. No
`audit/records/**` or `audit/GAP-QUEUE.md` edit (both are staged by the
controller, untouched in the worktree). No index-mutating git command is
evidenced. Record/queue changes were proposed, not applied. Full suite not run
by the implementer, as required.

---

## 6. Tests

**RED-first: verified by execution, and the report's characterisation is
honest.** I ran the lane's whole test file against HEAD's pre-fix
`_accept_offer` (scratch copy + conftest monkeypatch; nothing on disk touched):

```
1 failed, 16 passed
FAILED test_drowning_beacon_declines_through_a_real_driver_with_no_explicit_selector
  assert <DecisionKind.REWARD_POTION> in [<DecisionKind.EVENT>]
```

Exactly the one test the report labels RED-first fails; the other three are
characterisation/regression guards that are *supposed* to pass both sides
(`..._still_defaults_to_take...`, `..._explicit_..._still_overrides...`, and
`..._card_offer_already_declines_through_select_cards`, whose entire point is
that it was already green). The 13 pre-existing tests also pass under the
pre-fix body, which is the meaning-preservation evidence for §4's default item.

**No test asserts only a value it assigned.** The two tests that inspect a
list they populate (`kinds`, `seen`) populate it with values produced by
production code — `request.kind` off the `DecisionRequest` the driver built,
and the `purpose` string that `events/base.py:263` passes. Legitimate.

**Defect (minor, F4 below):** all four new tests call
`make_event(...).begin()` and then hand the event to `driver._run_event(ev)`,
which calls `event.begin()` again (`driver.py:556-557`). `calculate_vars` runs
twice, double-spending the event RNG; harmless for these three events but it
would double-roll `generate_internal_combat_state` for a Combat-layout event
and it teaches the wrong pattern. Drop the `.begin()` at these four call sites.

**Commands I ran (reviewer's own, not the implementer's):**

```
py -m pytest test/test_event_offer_screens.py test/test_driver.py \
  test/test_rng_tripwire.py test/test_ancients.py test/test_any_time_potion_action.py \
  test/test_darv.py test/test_reward_dispatch_choke_point.py test/test_run_env.py -q
    -> 219 passed

py -m pytest test/ -k "event" -q
    -> 431 passed, 3432 deselected

py -m pytest test/test_conformance_{runner,map,player_state,combat,pools,relic_bag,rooms}.py -q
    -> 77 passed, 6 xfailed

<scratch> pytest on a copy of test_event_offer_screens.py with the pre-fix body
    -> 1 failed, 16 passed   (RED-first check)
```

Plus three bespoke probes (pre/post `_accept_offer` behaviour at all 8 sites;
15-recording conformance walk to act 2 pre vs post; full-belt behaviour).

**Heads-up for the controller, not a defect:** `play_random_run`
(`driver.py:713-715`) passes the *same* `random.Random` to both `RunState` and
`random_asker`, so an added decision consumes a shared-rng draw. Any smoke-run
seed whose trajectory touches one of these six events now walks differently.
Verified benign — `test_driver.py`'s assertions are property-based
(determinism, inequality, termination) and the 219-test batch is green — but
if a downstream seed-pinned baseline exists outside these files, R6 moves it.

---

## 7. Findings that outrank the task

### F1 — the report's advice to R2 is wrong against the C# (**must fix**)

The report's closing line, and the tone of the proposed record note, tell R2
that "R2 can build straight onto `RunState.select_cards`'s existing skip
mechanism." **The C# says otherwise.** Driftwood's reroll is a
`CardRewardAlternative` living on the *same* screen as the card pick and the
Skip (`CardRewardAlternative.cs:60-67`), with
`PostAlternateCardRewardAction.DoNothing` = re-show the same screen. The sim
already models precisely that shape — on the **REWARD_CARD** decision, not on
SELECT_CARDS: `DecisionRequest.own_actions` reserves `n+1` for reroll and `n+2`
for Pael's Wing (`driver.py:207-214`) and `RunDriver._offer_card_group`
(`driver.py:519-542`) implements the reroll-and-re-ask loop. Pael's Wing is
`Hook.ModifyCardRewardAlternatives` (`CardRewardAlternative.cs:68`) — the same
screen again.

So R2's correct move is almost certainly to migrate `Event.offer_card_reward`
off `select_cards`/SELECT_CARDS and onto `run.offer_rewards` / REWARD_CARD —
which *also* gets it `apply_reward_modifiers`, i.e. **the actual G-new gap**,
for free through R10's offer-time backstop (`run.py:530-561`) — and to retire
`_accept_offer("card_reward", …)` entirely at that point. Steering R2 toward
bolting a reroll onto SELECT_CARDS would duplicate correct machinery and
diverge from C#'s single `{cards…, Skip, REROLL}` screen.

None of this is R6's work (`the_future_of_potions.py` and the reroll surface
are explicitly R2's), and the *current* SELECT_CARDS shape is fine today
because its outcome space is identical. But the record must not misdirect the
next lane.

**Required edit** to the proposed `g15` note and to queue Location 2: replace
the "R2 can build straight onto select_cards" framing with, in substance:

> The reroll surface belongs on the REWARD_CARD decision, not on SELECT_CARDS:
> C# puts Skip and REROLL as alternatives on the card-selection screen itself
> (`CardRewardAlternative.cs:53-74`, reached from `CardReward.cs:189`), which
> the sim already models at `driver.py:207-214` / `_offer_card_group`
> (`driver.py:519-542`). Closing G-new therefore most likely means routing
> `Event.offer_card_reward` through `run.offer_rewards` (picking up
> `apply_reward_modifiers` via R10's offer-time backstop) and retiring
> `_accept_offer`'s `card_reward` pass-through, not extending
> `RunState.select_cards`.

### F2 — the proposed notes omit that `reward_offer_selector` is still unwired (**must fix**)

After R6, `run.reward_offer_selector` is **still defined nowhere in
production**: `driver.py` does not wire it, `RunState.__init__` does not
declare it, and its only writer remains `test_event_offer_screens.py:37`. The
mechanism was fixed through a *different* seam. The proposed record and queue
text describe the fallback correctly but never say this — so the next auditor
running the same repo-wide grep that produced the round-12 finding will re-find
"`reward_offer_selector` is never wired by driver.py, set only in test files"
and reasonably re-open it.

**Required edit**: add one clause to both proposed notes, e.g. "`run.
reward_offer_selector` itself remains a **test-only** override with zero
production writers by design — it is no longer load-bearing, because
`_accept_offer` reaches the driver through `run.reward_selector` instead. A
repo-wide grep finding it unwired is expected, not a gap."

### F3 — negative finding worth recording: this gap class does NOT extend to event relics

The obvious next question — "do event *relic* payouts auto-accept too?" —
is answered **no** by the C#, and the sim is already right. Events grant relics
with `RelicCmd.Obtain` (an unconditional grant), not `RewardsCmd.OfferCustom`:
`DrowningBeacon.cs:41` (potion, `OfferCustom`) versus `DrowningBeacon.cs:54`
(relic, `RelicCmd.Obtain`) **in the same file** is the clean contrast; likewise
`TeaMaster.cs:69/76/82`, `SunkenStatue.cs:44`, `TrashHeap.cs:66`,
`ColossalFlower.cs:103`. The ~25 direct `self.run.add_relic(...)` calls across
`sts2_rl/events/*` are therefore faithful, and no sibling task is needed.
Recommend one line in the queue so nobody re-audits it. (I also confirmed no
event bypasses the potion seam: `grep` finds **zero** `run.add_potion` calls in
`sts2_rl/events/` outside `base.py`.)

### F4 — redundant `.begin()` in all four new tests (**should fix**)

See §6. Four one-line deletions in `test/test_event_offer_screens.py`.

### F5 — behavioural nuance R6 introduces, benign but unstated

With a **full belt**, R6 adds a decision where there was none, and its only
legal answer is skip (`driver.py:215-220` gates "take" on
`has_open_potion_slot`). Measured (probe E): pre-fix `decisions=['event']`,
post-fix `decisions=['event','reward_potion']`, belt unchanged in both. In C#
the take button *is* clickable and fails inside `PotionCmd.TryToProcure`
(`PotionReward.cs:78-89`); the sim masks it instead. That masking is a
pre-existing convention shared with every other REWARD_POTION offer, so R6
introduces **no new divergence** — but it does add a forced decision to RL
episodes and to the replay decision stream. Worth a sentence somewhere; not a
defect.

### F6 — observation, no action

`Event.offer_potion` and `RunState.offer_potion` are now behaviourally
identical (both: `reward_selector` gate → `add_potion`). The brief's "two names
for one concept" complaint survives as thin duplication. Not worth churn now —
it collapses naturally when F1's migration retires `_accept_offer`.

### F7 — brief citation drift, re-verified

The implementer's §0 corrections are all correct: `run.py` `offer_relic`
`:563-584` / `offer_potion` `:586-594` (brief said `:545-576`), driver wiring
`:301-307` (brief said `:296-302`), runner dispatch `:247-282` (brief said
`:247-268`), `card_selector` assignment `run.py:199` (brief said `:196-198`).

---

## 8. Verdicts on the report's record / queue proposals

| Proposal | Verdict |
|---|---|
| `event/the_future_of_potions` guard 15 (`G-new`/`g15`) stays `gap`, `live: true` | **CORRECT.** The reroll-surface half is untouched by R6 and needs new capability. Do not close it. |
| Replace g15's trailing "SEPARATE, LARGER CONCERN" paragraph | **CORRECT IN SUBSTANCE, TWO EDITS REQUIRED** — apply F1 and F2. The rest is accurate: I independently verified every factual claim in the replacement text (the six events, `driver.py:303`, `driver.py:301`, `SKIPPABLE_PURPOSES`, the pre-R6 probe result, the pinning test name). |
| It states which reasoning it replaces | **YES, and correctly** — "the claim that the wiring gap was 'pre-existing… needs its own task' undifferentiated across both purposes… one purpose had a real, fixable gap; the other never had the gap the note implied." That is exactly the right framing and it is the true correction. |
| The six EV-4 event records unchanged | **CORRECT.** I read the `maps_to` shape on `the_future_of_potions`'s EV-4 guard; it describes `_accept_offer` consulting the selector and granting only when taken — still true. No edit needed, and declining the six near-identical cross-reference edits is the right call. |
| Queue Location 1 (round-12 "owned by nobody", lines 81-83) | **CORRECT** in verdict and location — I confirmed the quoted text is verbatim at `audit/GAP-QUEUE.md:81-83`. Apply F2's clause. Style matches the neighbouring R10 strikethrough bullet. |
| Queue Location 2 (§3C `event`, lines 2708-2712) | **CORRECT** in verdict and location — quoted text verbatim at `:2708-2712`. Apply F1 and F2. |
| No change to line 35's "7 remaining live mechanisms" listing | **CORRECT.** `event/the_future_of_potions/g15` stays live on its reroll half; the live count does not move. Verified against `audit/GAP-QUEUE.md:32-37`. |

**How `g15` should now read**, in summary: verdict unchanged (`gap`, `live:
true`, reroll surface open); the trailing wiring paragraph replaced by a note
that (i) the potion half is FIXED via `run.reward_selector`, (ii) the card half
was a WRONG PREMISE — `select_cards`'s `SKIPPABLE_PURPOSES` already carried the
decline, proven against pre-R6 code — (iii) `reward_offer_selector` itself
remains deliberately test-only [F2], and (iv) the still-open reroll surface
belongs on REWARD_CARD, not SELECT_CARDS [F1].

**What remains for R2** (do NOT do here): `Event.offer_card_reward` still skips
`Hook.ModifyRewards`, so Driftwood cannot reroll this screen and the late
card-reward modify hooks do not run on it. Per F1, the likely shape is routing
it through `run.offer_rewards` / REWARD_CARD.

---

## 9. Summary

| Item | Verdict |
|---|---|
| Premise correction (card half never auto-accepted) | **CONFIRM** — proven by executing the pre-fix code |
| Six `offer_potion` callers auto-accepted, now ask | **CONFIRM** — 8/8 sites, ask counts match the C# reward sets |
| Double-ask argument | **CONFIRM**, on stronger C# grounds than argued; sim asks exactly once |
| Bare-RunState default preserved and pinned | PASS |
| No event's grants changed | PASS |
| Conformance traversal | PASS — and demonstrated past act 0, where the suite stops |
| RL action space unchanged | PASS |
| RED-first | PASS (1 of 4 genuinely RED, honestly reported) |
| Spec compliance / code quality | PASS with nits |
| PROTOCOL compliance | PASS |
| Record / queue proposals | Correct except **F1** and **F2**, both required |

`events/base.py` needs **no change**. Required before merge: F1 and F2 (edits
to the proposed record/queue prose the controller applies) and F4 (four
`.begin()` deletions in the test file). F3 and F5 are recommended additions.

---

## Re-review (2026-08-01) — F1 / F2 / F4 fix pass

Scope: only the three items I raised. The premise-correction **CONFIRM** and
the approval of `events/base.py` stand and are not re-opened. I first
re-verified that the engine really was untouched: `_accept_offer`'s body
(`events/base.py:251-258`) is byte-identical to what I approved, and
`git diff --stat -- sts2_rl/events/base.py` is unchanged at 44/8.

**Verdict: APPROVED.** All three items are fixed. Two trivial nits below, both
confined to the report's own narrative and neither present in any text the
controller applies to a record or the queue — no further pass needed.

### F1 — reroll surface belongs on REWARD_CARD: **FIXED, correct and precise**

Applied at all three sites that needed it — the report's Status section
(`R6-report.md:387-413`), the `g15` record-note proposal (`:280-289`) and Queue
Location 2 (`:367-374`). Queue Location 1 correctly excluded; it never
mentioned the reroll surface.

Every citation in the new text re-verified against the source:
`CardRewardAlternative.Generate` at `CardRewardAlternative.cs:53-74`, Skip at
`:56-59` gated on `CardReward.CanSkip`, which defaults `true` at
`CardReward.cs:95` and is not overridden by `TheFutureOfPotions.cs:128`'s plain
`new CardReward(options, 3, base.Owner)`; REROLL at `:60-67` with
`PostAlternateCardRewardAction.DoNothing`; `Generate(this)` reached from
`CardReward.OnSelect` (`CardReward.cs:183`) at `:189`. Sim side:
`driver.py:207-214` (`n+1` reroll, `n+2` sacrifice) and
`RunDriver._offer_card_group` (`driver.py:519-542`, the reroll-and-re-ask
loop); `run.py:530-561` for the `apply_reward_modifiers` backstop. All correct.

Precise enough to apply verbatim and to steer the follow-up task: the text
names the target decision kind (REWARD_CARD), the two sim functions that
already implement it, the likely migration (`Event.offer_card_reward` →
`run.offer_rewards`), the bonus it collects (`apply_reward_modifiers`, i.e. the
actual G-new gap), the cleanup it enables (retiring `_accept_offer`'s
`card_reward` pass-through), and the thing to avoid (extending
`RunState.select_cards`). It hedges with "most likely", which is right — it
does not over-constrain the follow-up task's design. It does not contradict the
amended brief.

*Nit (narrative only, does not propagate):* the fix-pass bullet at
`R6-report.md:430-432` cites `CardReward.cs:194-269` for "one loop that reads a
single index across `{cards…, alternatives…}`". The structural claim is right,
but the loop actually spans `:194-292` and the index dispatch is `:232-256`;
`:269` is a mid-loop `continue`. Short range, correct conclusion.

### F2 — `reward_offer_selector` still unwired, stated explicitly: **FIXED, accurate as written**

Re-verified the three factual claims rather than reading them:
`grep -c reward_offer_selector sts2_rl/driver.py` → **0** (driver.py never
mentions, let alone assigns, the flag); the only writer anywhere in
`sts2_rl/` + `test/` is `test/test_event_offer_screens.py:37`; the only
production reader is `events/base.py:251`. The clause is present at all three
prose sites — `g15` (`R6-report.md:274-280`), Queue Location 1 (`:335-340`),
Queue Location 2 (`:363-367`) — and each states the flag name, the unwired
status, that only the one test file sets it, that `_accept_offer` reaches the
driver via `run.reward_selector` instead, and that a future grep finding it
unwired is expected rather than a re-opened gap. That is exactly what F2 asked
for, and it is true.

*Nit (narrative only, does not propagate):* the fix-pass bullet at
`R6-report.md:450-452` describes the `getattr(self.run,
"reward_offer_selector", None)` as something "this fix pass's engine change
added". It was not added by R6 or by the fix pass — it is in
`git show HEAD:sts2_rl/events/base.py` verbatim, and the fix pass touched no
production file at all. The record/queue clauses do not repeat this, so nothing
inaccurate reaches the audit.

### F4 — redundant `.begin()` removed: **FIXED, and the tests still pin what they claim**

All four driver-driven tests now build the event with `make_event(id, run)` and
let `driver._run_event` call `begin()` (`test_event_offer_screens.py:199, 217,
235, 266`). The 11 surviving `.begin()` calls in the file are all in the
bare-`RunState` tests that drive `event.choose(...)` directly with no driver —
those need it, correctly kept.

`driver.py:557` is confirmed the **sole** production caller of `event.begin()`
(`grep '\.begin()' sts2_rl/` returns only it, `events/ancient.py:32`'s
`super().begin()` inside an override, and a docstring line). So there is no
pre-existing double-begin on the `driver.py:429` room path either.

Tests still pin what they claim, verified rather than assumed: I re-ran the
**amended** file against HEAD's pre-fix `_accept_offer` (scratch copy +
conftest monkeypatch) and got the identical result to the pre-fix-pass run —
`1 failed, 16 passed`, failing on exactly
`test_drowning_beacon_declines_through_a_real_driver_with_no_explicit_selector`
with `assert REWARD_POTION in [EVENT]`. The RED-first property survived the
edit, and the three characterisation guards still pass on both sides as
intended. Post-fix: `py -m pytest test/test_event_offer_screens.py -q` → **17
passed**.

*Nit (narrative only):* the bullet's supporting parenthetical cites
`driver.py:394,429,634,649` as sites that "use `make_event`". `:429` is
`self._run_event(resolution.event)` — a driver-driven `_run_event` call site,
but not a `make_event` one. The point it supports is still right.

### Fix-pass conformance section: **ACCURATE**

`R6-report.md:484-508` records the evidence correctly and explicitly supersedes
§3's overstatement. It gets the load-bearing point right — the conformance
suite's greenness was **not** evidence about R6, because
`ReplayRunner.run(stop_after_act=0)` (`runner.py:767`) never reaches
`Event._accept_offer` on any of the 15 recordings — names the correct seeds and
events reached only at `stop_after_act=2` (`the_future_of_potions` on
TZEKRYTSNT/floor_34 and /floor_49, `drowning_beacon` on QRWCVDPZN5,
`the_legends_were_true` on DJDCSAQZNR), quotes TZEKRYTSNT/floor_49's
`(45, True, 4, 'reached act 2 boss')` identically pre and post, and reproduces
the safety-by-construction argument with the right citations
(`runner.py:282`'s `legal[0]`; `driver.py:215-220` yielding `[0, 1]` with an
open belt slot and `[1]` without, i.e. bit-for-bit the pre-fix outcome). It is
correctly attributed to the review rather than re-claimed as the lane's own
work.

### Re-review summary

| Item | Verdict |
|---|---|
| F1 — reroll surface on REWARD_CARD, at all three sites | **FIXED** — citations verified, precise enough to apply verbatim |
| F2 — `reward_offer_selector` unwired-by-design, at all three sites | **FIXED** — accurate; 0 mentions in `driver.py`, one writer tree-wide |
| F4 — four redundant `.begin()` calls | **FIXED** — sole caller is `driver.py:557`; RED-first property re-verified (1 failed / 16 passed pre-fix, 17 passed post-fix) |
| Fix-pass conformance section | **ACCURATE** — supersedes §3's overstatement correctly |
| Engine change untouched | Confirmed byte-identical |

**APPROVED.** Nothing blocking remains. The two nits are optional word fixes in
the report's own narrative; neither appears in the `g15` note or either queue
annotation, so the text the controller applies is correct as it stands.
