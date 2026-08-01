# R10 review — consolidate the reward-modifier dispatch onto one choke point

Reviewer: independent re-derivation from the decompiled C# and the current
worktree. I did not revert or edit any production file. Everything below was
re-derived; where I agree with the report I say so, and where the report's
*reasoning* is wrong I say that even when its *verdict* is right.

**Verdict: NEEDS-FIXES.** The shipped code is correct, faithful and well
pinned — I found no behavioral defect. The fixes are documentation/record
text: one materially wrong sentence about the C# is baked into the engine
docstring that justifies this whole change, and it is echoed in the proposed
queue text the controller will paste nearly verbatim. Three citations are
stale, and one "no existing record" claim is false in a way that leaves
another record's rationale silently wrong. All four are surgical.

---

## 1. THE DEAD-CODE CLAIM — CONFIRMED

`grep -rn "OfferForRoomEnd" --include=*.cs .` over the whole decompiled tree
returns exactly one hit: the definition itself,
`src/Core/Commands/RewardsCmd.cs:20`. **Zero call sites.** The report is
right and the brief's framing was built on dead code.

The path the game actually executes, re-derived end to end:

- `CombatRoom.OfferRoomEndRewards` (`CombatRoom.cs:261-273`) and
  `TreasureRoom.DoExtraRewardsIfNeeded` (`TreasureRoom.cs:75-97`) both call
  `RewardsCmd.GenerateForRoomEnd` (`CombatRoom.cs:267`, `TreasureRoom.cs:82`).
- `GenerateForRoomEnd` (`RewardsCmd.cs:55-60`) = `WithRewardsFromRoom(room)`
  then `await set.GenerateWithoutOffering()` — **this** is where
  `Hook.ModifyRewards` fires (`RewardsSet.cs:136`) and where the RNG is drawn.
- Both then call `item.Offer()` (`CombatRoom.cs:271`, `TreasureRoom.cs:86`),
  and `Offer()` calls `GenerateWithoutOffering()` again at `RewardsSet.cs:159`.
- The repeat is a no-op because of `_isGenerated`: declared
  `RewardsSet.cs:41`, guard `:127-130`, set LAST at `:146` after both hook
  passes, the re-populate sweep (`:137-143`), `AfterModifyingRewards` (`:144`)
  and the `RewardsSetIndex` sort (`:145`).

So the implementer's corrected trace is right, and shape (a) — an idempotency
flag plus a backstop at offer time — is the shape that reproduces C#'s real
control flow. Shape (b) was never on the table, for a reason the report gets
right (RNG order) *and* a reason it misses (see §1a).

### 1a. FINDING THAT OUTRANKS THE TASK: the report's justification for the
### backstop is factually wrong about the C#, and the wrong sentence shipped

`sts2_rl/rewards.py:673-675` now says, in the docstring that justifies this
entire change:

> `Offer()` ... call it AGAIN unconditionally at :159 — **the repeat is
> always a no-op in practice, since every real caller generates before
> offering**, but the guard is what makes that safe to do from two places.

That is false, and it is false for the *majority* of C# reward screens.
`RewardsCmd.OfferCustom` (`RewardsCmd.cs:47-50`) is
`new RewardsSet(player).WithCustomRewards(rewards).Offer()` — **no
`GenerateWithoutOffering` beforehand**. For every `OfferCustom` caller the
call at `RewardsSet.cs:159` is the FIRST and ONLY dispatch. I enumerated them
(`grep -rn "RewardsCmd\.OfferCustom"`): `HealRestSiteOption.cs:112` (the
rest-site heal), 12 events (`BattlewornDummy:88`, `BrainLeech:58`,
`ColorfulPhilosophers:59`, `DrowningBeacon:41`, `EndlessConveyor:156`,
`PotionCourier:43,55`, `PunchOff:112`, `TheFutureOfPotions:130`,
`TheLegendsWereTrue:56`, `Trial:185`, `WarHistorianRepy:93`, `Wellspring:36`,
`WhisperingHollow:53`), 8 relics (`CallingBell:31`, `Cauldron:33`,
`GlassEye:32`, `Kaleidoscope:49`, `LostCoffer:22`, `Orrery:27`,
`SmallCapsule:15`, `ToyBox:96`) and `OneOffSynchronizer.cs:209`.

The correct statement — which is *stronger* support for what was built — is:
**C# has two dispatch entry points, not one.** Room-end sets dispatch at
generate time (`GenerateForRoomEnd`); every `OfferCustom` set dispatches at
offer time (`Offer` → `:159`). `_isGenerated` exists precisely so that both
entry points are safe. Shape (a) is the only sim shape that mirrors both.

This matters beyond pedantry: four of the seven sim paths this task touches
(glass_eye, brain_leech, trial, rest-heal/dense_vegetation) are exactly the
`OfferCustom` family, i.e. the ones the report's sentence claims "generate
before offering" — they do not, in C#. The sim's choice to dispatch at those
construction sites is still right (it puts the dispatch at the same code
point the `await OfferCustom` sits at, which matters for brain_leech / trial /
dense_vegetation where the sim defers the *offer* to the driver but C# awaits
it inline), but that is a different argument from the one written down.

**Required fix 1:** rewrite `rewards.py:672-675` to state the two-entry-point
shape, with `RewardsCmd.cs:47-50` and `:55-60` cited. **Required fix 2:** the
same correction in the proposed GAP-QUEUE bullet (§4 below).

---

## 2. THE CONSOLIDATION SHAPE — CORRECT, VERIFIED THREE WAYS

Shape landed: `CombatRewards.generated` (`rewards.py:602`), early return
(`rewards.py:692-693`), flag set last (`rewards.py:707`), backstops at
`driver.py:484` and `run.py:552`. Construction sites untouched.

### (a) Exactly once, end to end, for all seven paths

I traced each one in the current tree, not from the brief's map:

| # | path | construction dispatch | offer path | net |
|---|---|---|---|---|
| 1 | final-act-boss early return | `rewards.py:735` | `driver._offer_rewards` :484 (no-op) | 1 |
| 2 | normal combat | `rewards.py:798` | `driver._offer_rewards` :484 (no-op) | 1 |
| 3 | rest heal | `run.py:1456` | `driver.py:686` → :484 (no-op) | 1 |
| 4 | glass_eye | `glass_eye.py:78` | `run.offer_rewards` :552 (no-op) → `rewards_offerer` = `driver._offer_rewards` :484 (no-op) | 1 |
| 5 | brain_leech RIP | `brain_leech.py:89` | `driver.py:574` → :484 (no-op) | 1 |
| 6 | trial Nondescript Guilty | `trial.py:118` | `driver.py:574` → :484 (no-op) | 1 |
| 7 | dense_vegetation rest | rides #3 (`dense_vegetation.py:75`) | `driver.py:574` → :484 (no-op) | 1 |
| 8 | **new** treasure | `run.py:1357` | `driver._offer_treasure_extra_rewards` :453 → :484 (no-op) | 1 |

Path 4 passes through **two** backstops and is still exactly one — pinned by
`test_glass_eye_construction_call_plus_offer_backstop_still_fires_once`.

### (b) No new dispatch anywhere it did not previously happen

This is the risk the brief called "double-fires 100% of the time", and it is
the thing that could silently change real play. I enumerated **every**
`CombatRewards(` construction in the package (`grep -n "CombatRewards("`),
not just the brief's list: `driver.py:379,498,524,548` (all four are
display-only re-wraps handed to `DecisionRequest`, never to `_offer_rewards`
or `offer_rewards` — verified by reading each), `brain_leech.py:81`,
`trial.py:111`, `glass_eye.py:54`, `run.py:1447` (rest heal), `run.py:1355`
(new treasure), `rewards.py:725`. Every set that reaches an offer entry point
was already dispatched at construction. **No existing screen changes.**

Listener side: `grep -n "def modify_combat_rewards(_late)?" sts2_rl/` returns
exactly 9 hits — `relics/base.py:270,275` (both empty no-op bodies) and the 8
relics. `apply_reward_modifiers` iterates `run.relics` only, so relics are the
complete listener set. All 8 checked for a pre-gate side effect: every one's
room gate (or empty-list loop) is its first statement.

### (c) Construction-time RNG order unchanged — verified, not assumed

`rewards.py` diff touches only the module docstring, the dataclass field and
`apply_reward_modifiers`' body/docstring. `apply_reward_modifiers` still sits
at `rewards.py:798`, i.e. **after** the elite `run.offer_relic` (`:777`/`:795`)
and **before** the `pending_reward_extras` drain (`:810-829`) — byte-identical
positioning. I re-ran the RNG gate: `test/test_rng_tripwire.py` 21/21.

Independent execution (reviewer probe, scratchpad, monkeypatch-only — no
working-tree edits):

- Re-ran the **pre-R10 body by hand** twice on one set: Amethyst Aubergine
  gold 30 (not 15), Black Star 2 relics, Prayer Wheel 2 groups. So section A
  **would be RED** against the old arrangement. Confirmed, not taken on trust.
- Monkeypatched `driver.apply_reward_modifiers` / `run.apply_reward_modifiers`
  to no-ops (= "the backstop call is not there") and re-ran section B's
  bodies: the set comes back `gold == 0`, run gold unchanged. So section B
  **would be RED**. Confirmed.

---

## 3. THE TREASURE-ROOM CHANGE — CORRECT, AND THE C# CLAIM HOLDS

This got the hardest scrutiny, as asked. Re-derived rather than checked:

- `NTreasureRoom.OpenChest` (`NTreasureRoom.cs:190-228`) calls
  `_room.DoNormalRewards()` (`:198`) then `_room.DoExtraRewardsIfNeeded()`
  (`:204`) — **unconditionally**, no gate between them.
- `DoNormalRewards` → `OneOffSynchronizer.DoTreasureRoomRewards`
  (`OneOffSynchronizer.cs:128-143`): `Hook.ShouldGenerateTreasure` gate at
  `:130-132`, then a direct `PlayerCmd.GainGold` at `:139` and the Spoils Map
  payout. **No `RewardsSet` anywhere** — this path never dispatches
  `Hook.ModifyRewards`. The chest relic is rolled earlier still, in
  `TreasureRoomRelicSynchronizer.BeginRelicPicking` (`:91-113`, rarity roll at
  `:109`), called from `TreasureRoom.EnterInternal:47`.
- `DoExtraRewardsIfNeeded` (`TreasureRoom.cs:75-97`) →
  `RewardsCmd.GenerateForRoomEnd` → `WithRewardsFromRoom(treasureRoom)` (sets
  `Room`, `RewardsSet.cs:87`) → `GenerateWithoutOffering` → **`Hook.ModifyRewards`
  fires at `RewardsSet.cs:136` with a non-null, non-combat `Room`**, over a base
  list that `GenerateRewardsFor` leaves empty for a `TreasureRoom` (`:206-246`;
  the throw at `:217` is only for a room that is neither `CombatRoom` nor
  `TreasureRoom` — `:213-219`).

So the brief's *observable* claim was right and its *mechanism* was wrong; the
report's correction is correct and correctly flagged. The sim comment at
`run.py:1339-1354` cites `TreasureRoom.cs:75-97` and `RewardsSet.cs:213-219`
accurately.

**Ordering fidelity (the part nobody asked about and it checks out):** C# order
is relic-rarity roll (room entry) → chest gold → `ModifyRewards` dispatch →
relic pick UI. The sim's order is relic (`run.py:1324`) → gold (`:1333-1337`)
→ quests (`:1338`) → dispatch (`:1357`). Same relative order, dispatch last of
the three grants, matching `OpenChest`.

**Grants identical — executed, not reasoned.** Reviewer probe: walk seed-30 to
a treasure node with all 8 reward-hook relics attached, once with the new
dispatch live and once with `run.apply_reward_modifiers` monkeypatched to a
no-op, then compare `(resolution.gold, run.gold, len(run.relics), relic ids,
run.rng.getstate(), pending_treasure_extra_rewards)`. **Tuples identical**,
including the full shared-RNG state — so the new dispatch consumes zero draws
and changes zero grants on today's roster. The `rewards_rng` (parity) stream
is untouched because the dispatch sits outside the `should_generate_treasure`
block that owns the only Rewards-stream draw.

**Room-sensitivity enumeration — re-derived, and the report's table is right
despite reading backwards.** The table's "C# gate" column lists each relic's
*bail* condition, so "`room not in {Monster,Elite,Boss}`" against a Treasure
room reads as "fires" on a first pass; it does not. Verified by reading all 8
implementations: `amethyst_aubergine.py:24-27`, `black_star.py:19-20`,
`lava_rock.py:23-29`, `prayer_wheel.py:29-30`, `white_star.py:29-30`,
`wongos_mystery_ticket.py:40-43` all early-return on `room == TREASURE`;
`driftwood.py:22-23` and `paels_wing.py:26-27` are room-ungated but iterate
`rewards.card_rewards`, which is `[]` here and stays `[]` (nothing populates
it). C# side confirmed 1:1: `grep -rln "TryModifyRewards"` over
`src/Core/Models/Relics/` gives exactly the same 7 files (+ `PaelsWing`'s
`TryModifyCardRewardAlternatives:73`).

One correction to the report's C# enumeration: it names `Midas.cs` as "the
only OTHER unconditional implementer". There is a second Modifier,
`src/Core/Models/Modifiers/Vintage.cs:10-30` (`TryModifyRewardsLate`) — but it
is gated `room is CombatRoom` **and** `RoomType.Monster`, so it does not reach
a treasure room and the conclusion is unaffected. Modifiers remain the
recorded out-of-scope waiver (`seam/hook_dispatch.json`: "Modifiers are
custom/daily-run mutators loaded from save.Modifiers (RunState.cs:296, 344)
and a standard run has none").

**Empty-screen suppression matches, with one benign asymmetry.** C#'s `Offer()`
returns before showing anything when `Rewards.Count <= 0 && !(Room is
CombatRoom) && !_allowEmptyRewards` (`RewardsSet.cs:160-165`) — a treasure set
satisfies all three, so nothing is shown. The sim's `if not
treasure_rewards.is_empty` (`run.py:1358`) is the analogue. They are not the
same predicate: a hook adding only a `GoldReward` gives `Rewards.Count == 1`
(C# shows a screen) and `is_empty == False` (sim stashes it, but
`_offer_rewards` has no gold decision, so nothing is presented). Unreachable
today; noted, not blocking.

**Verdict on item 3: FIXED, correctly, and the change is behavior-neutral on
every treasure floor with today's roster — proven by execution.**

---

## 4. `conformance/runner.py` — NO DELTA, REPLAY SEMANTICS UNCHANGED

The file is not in the diff and `git status` does not list it as modified.
Its only exposure is inherited: `runner.py:851` calls
`driver._resolve_room(resolution)`, which now has a `TREASURE` branch
(`driver.py:434-435`) calling `_offer_treasure_extra_rewards()` — an early
return when `pending_treasure_extra_rewards is None`, which it always is
today. No command is consumed, no decision is asked, no RNG is drawn.

Confirmed by execution: `py -m pytest test/ -q -k conformance` →
**98 passed, 6 xfailed, 2 failed**, and the 2 are exactly the protocol's known
environment gap (`FileNotFoundError: .../933T39V18D/floor_49/actions.sts2replay`).

One report inaccuracy the controller should not copy: the report says
"`conformance/runner.py`'s `ReplayRunner` subclasses `RunDriver`". It does not
— `ReplayRunner` is a plain class (`runner.py:423`); the RunDriver subclass is
`_ForceWinDriver` (`runner.py:187`), and `runner.py:242` is inside *its*
`_run_combat` override. Neither class overrides `_offer_rewards` or
`_resolve_room`, so the substance (the backstop is inherited) holds.

---

## 5. TEST-QUALITY VERDICT — GOOD, with the RED claims independently confirmed

15 tests, all passing (`py -m pytest test/test_reward_dispatch_choke_point.py
-q` → **15 passed in 1.10s**).

- **Do they pin C#, not sim-vs-sim?** Yes for the load-bearing ones. Section A
  pins "one `Hook.ModifyRewards` dispatch per screen", which is the property
  `_isGenerated` exists to guarantee (`RewardsSet.cs:127-130/146`), and it
  pins it through *state* (gold, relic pulls, group count) plus a call
  counter, not through an internal flag. `_CountingRelic` is a legitimate
  probe, not a tautology: it is the sim's stand-in for a room-ungated
  `TryModifyRewards` implementer, which C# genuinely has
  (`Driftwood`, `PaelsWing`, `Midas`).
- **Was RED shown, and would the double-dispatch pin really fail against the
  old arrangement?** Yes — and I did not take the report's word for it.
  Reviewer probe (monkeypatch/re-run-the-old-body only, no working-tree
  reverts): old body double-fires on all three state-mutating relics; backstop
  removal leaves an ungenerated set undispatched. Section A and section B are
  genuine RED-first pins.
- **Honesty of labeling:** the report explicitly marks section C (6 site
  regressions) and one section-B test as *not* RED-first. That is the correct
  call and correctly disclosed — before the backstop existed there was nothing
  to double-fire, so those tests can only ever have been GREEN. Section D's
  RED was an `AttributeError` (the attribute did not exist), which is a weak
  but legitimate RED for new machinery.
- **D1 is a real executed enumeration, and stronger than it looks:** it
  attaches all 8 relics and asserts `pending_treasure_extra_rewards is None`.
  Any of the state-mutating relics firing (amethyst's gold, black_star's /
  lava_rock's / wongos' relic append) would make the set non-empty and trip
  the assertion, so the test genuinely catches the failure mode, not just the
  symptom.
- **Gaps (minor, not blocking):** nothing pins that the treasure dispatch is
  *unconditional* — i.e. that a Silver-Crucible-suppressed chest still
  dispatches, which is the specific thing `TreasureRoom.cs:75` +
  `NTreasureRoom.cs:198-204` mandate and which the code does implement
  correctly (the block sits outside the `should_generate_treasure` gate at
  `run.py:1320`). One test with `silver_crucible` attached on the first
  treasure room would close that. Also nothing pins the dense_vegetation path
  (#7) separately, though it is the same object as #3.

Regression sweep I ran myself:
`py -m pytest test/test_rewards.py test/test_relic_tier1_gaps.py
test/test_rng_tripwire.py test/test_event_offer_screens.py
test/test_reward_dispatch_and_relic_stubs.py test/test_event_reward_modifiers.py
test/test_glass_eye_reward_set.py test/test_driver.py test/test_map.py
test/test_shop_and_map_mods.py -q` → **693 passed**.

**Environmental caveat — attribution verified and now stale.** The report's §4
describes `test_ancients` / `test_combat_over_hook_gate` / `test_conformance_*`
failing with `HookSystem._order_key` / `PlayerCombatState.is_active_for_hooks`
`AttributeError`s from the concurrent hooks.py/powers.py lane. I re-ran them:
`test_combat_over_hook_gate.py` + `test_ancients.py` → **102 passed**, and
conformance is green but for the 2 known fixture failures. The other lane has
since settled. The attribution was right regardless: this lane's diff is
confined to `rewards.py` / `run.py` / `driver.py` and cannot produce an
`AttributeError` inside `hooks.py`.

---

## 6. SPEC-COMPLIANCE VERDICT — did the brief, no more, no less

- **Shape choice re-derived, not deferred to.** Required by the brief and
  actually done: the implementer overturned the brief's `OfferForRoomEnd`
  framing from the source. Correct outcome, flawed supporting sentence (§1a).
- **Footprint respected.** `git status` shows this lane's edits confined to
  `sts2_rl/rewards.py`, `sts2_rl/run.py`, `sts2_rl/driver.py` plus the
  untracked `test/test_reward_dispatch_choke_point.py`. `glass_eye.py`,
  `brain_leech.py`, `trial.py`, `conformance/runner.py` are genuinely
  unmodified — and the report's reason (they already dispatch; the backstop
  is a no-op on top) is correct, not an excuse. Everything else modified in
  the tree (`hooks.py`, `powers.py`, `combat.py`, `player.py`, `cmds.py`,
  `afflictions.py`, `enchantments.py`, `cards/base.py`, `relics/base.py`,
  `monsters/**`, three test files, other `test_r13_*` files) belongs to other
  lanes and is not claimed by this report.
- **No `audit/**` edits.** `audit/records/**` and `audit/GAP-QUEUE.md` are
  untouched; the only staged audit path is `audit/tools/unlabelled_batches.py`,
  which predates this wave and is not claimed by R10.
- **No git index mutation by this lane.** Its three production files are
  unstaged (` M`) and its test file untracked (`??`) — i.e. no `git add`. The
  single `stash@{0}` entry is `WIP on main: 0c0178c`, an older commit than
  `HEAD` (`c9bc337`); it predates this wave.
- **Watch items honored.** `test_rng_tripwire.py`'s allowlist is indeed
  function-keyed now (`_ALLOWLIST = {("sts2_rl\\driver.py", "_ask"), ...}`,
  with a comment naming this exact failure mode) — the brief's line-number
  warning was stale and the report is right to say so. (Small correction: the
  report says it "added 12 lines above `_ask`". Only the 4-line import
  expansion is above `_ask` at `driver.py:313`; `_offer_treasure_extra_rewards`
  is at `:439`, below it. Immaterial to the conclusion.)
- **Scope.** The treasure fix was conditionally in scope ("either fix it inside
  your footprint if the fix is contained, or write the complete gap analysis")
  and the fix is genuinely contained — `run.py` + `driver.py`, no new
  `DecisionKind`, no `rooms.py` field (correctly declined as out of footprint,
  with the alternative recorded). Not gold-plating.
- **The `the_future_of_potions/g15` and `reward_offer_selector` items were
  correctly left alone**, as the brief instructed.

---

## 7. THE PROPOSED RECORD / QUEUE TEXT — accurate except in two places

Verified against the actual files (read-only):

- `audit/records/event/brain_leech.json` guard `G-new`: `verdict` is already
  `"faithful"` (confirmed), and the sentence the report proposes to replace —
  *"That leaves the sim structurally unlike C#'s single choke point, which is
  a real (recorded) tension: the next event ported this way can reintroduce
  the same bug."* — is **verbatim** present at `brain_leech.json:79`. Same for
  `trial.json:235`. **The amendment is accurate as written, except that its
  citation "mirroring `RewardsSet.Offer`'s own repeat call" repeats the §1a
  error.** Fix: say *"mirroring the two dispatch entry points C# actually has
  — generate-time for room-end sets (`RewardsCmd.cs:55-60`) and offer-time for
  every `RewardsCmd.OfferCustom` set (`RewardsCmd.cs:47-50`), both funnelled
  through the `_isGenerated`-guarded `GenerateWithoutOffering`
  (`RewardsSet.cs:127-130/146`, re-called at `:159`)"*.
- `audit/GAP-QUEUE.md` — the bullet to replace is at lines **85-88** under
  "Still open, found this round, owned by nobody" and matches the report's
  quotation. The 3C paragraph to update is at lines **2690-2711**. Both
  locations are right. The replacement bullet's phrase *"called once at
  generation and again, harmlessly, from `Offer()`"* is the §1a error again
  and needs the same correction — as written it tells the next reader that
  `OfferCustom` screens generate before offering, which is what this whole
  round was supposed to stop believing.
- The proposed new `seam/hook_dispatch.json` guard text for the treasure hole
  is otherwise accurate: I independently confirmed every citation in it
  (`TreasureRoom.cs:75-97`, `RewardsSet.cs:206-246`, the unconditional call,
  the 8-relic enumeration, the `ShouldGenerateTreasure` independence).

**But its claim of novelty is false, and that has a consequence.** The report
says it *"did not find an existing entry for it anywhere in `audit/records/**`
or `GAP-QUEUE.md` (`grep -rn "TreasureRoom\|DoExtraRewardsIfNeeded"` over
both)"*. That grep does return hits. The material one is
`audit/records/relic/wongos_mystery_ticket.json:264`:

> "C#'s TreasureRoom also reaches RewardsSet (RewardsSet.cs:206-219) and its
> `room is CombatRoom` test correctly rejects it; **the sim rejects it
> earlier**."

That record already knew the sim never built a treasure `RewardsSet` and
treated it as harmless. **R10 makes that sentence stale**: the sim no longer
"rejects it earlier" — it now builds the treasure set and Wongo's Ticket
rejects it on its own room tuple (`wongos_mystery_ticket.py:40-43`), i.e.
exactly as C# does. **Proposed additional record action:** amend
`relic/wongos_mystery_ticket.json`'s G-rationale to note that the sim now
reaches the same rejection point C# does (R10, `run.py:1355-1359`), and
cross-reference the new `seam/hook_dispatch` guard. `relic/silver_crucible.json`
also hits that grep but is unaffected (its G3 concerns the map-quest payout
outside the `ShouldGenerateTreasure` gate; R10 changed nothing there).

---

## 8. MY OWN FINDINGS (outrank the task's)

1. **`RewardsCmd.OfferCustom` dispatches at OFFER time, not generate time** —
   §1a. Wrong in the shipped `rewards.py` docstring and in the proposed queue
   text. This is the highest-value finding here: the fix is right for reasons
   the record would have misstated, which is precisely the round-12 lesson
   ("records are wrong about their reasoning more than their verdicts").

2. **Pre-existing, NOT closed by R10, and now worth its own queue line:
   `CombatRoom.ExtraRewards` are folded into the reward list BEFORE the hook
   dispatch in C# and AFTER it in the sim.** `RewardsSet.WithRewardsFromRoom`
   adds them at `RewardsSet.cs:96-99`, so `GenerateWithoutOffering` populates
   them and `Hook.ModifyRewards` sees them at `:136`. The sim drains
   `run.pending_reward_extras` at `rewards.py:810-829`, i.e. **after**
   `apply_reward_modifiers` at `:798`. A `TryModifyRewards` implementer that
   reads the reward list therefore cannot see Thieving Hopper's returned card,
   Punch-Off's relic/potion, or returned stolen gold. Dormant today (no ported
   listener inspects `special_cards` / `special_potions` / `relics`); the C#
   listener that would notice is `Midas.TryModifyRewardsLate`
   (`Midas.cs:12-29`), which doubles every `GoldReward` and is a Modifier
   (waived). Note that shape (b) would have *closed* this by accident, and
   shape (a) preserves it — so the shape choice, though correct, has a cost
   that should be written down rather than discovered later. Also unmodelled:
   C# sorts the reward list by `RewardsSetIndex` after the hooks
   (`RewardsSet.cs:145`).

3. **Stale line citations shipped inside the new docstring.**
   `rewards.py:680-681` claims the construction sites are at
   "rewards.py:698,761; run.py:1419". Post-edit they are `rewards.py:735,798`
   and `run.py:1456` (`glass_eye.py:78`, `brain_leech.py:89`, `trial.py:118`
   are still correct). Given this campaign grades citations, a comment whose
   self-references are wrong on the day it lands should be fixed.

4. **Report citation errors the controller should not propagate:**
   `run.offer_rewards`'s selectorless fallback loop is at `run.py:557-561`,
   not `:546-550`; `ReplayRunner` does not subclass `RunDriver` (§4); "12
   lines above `_ask`" is 4 (§6).

5. **Follow-up worth a queue line (not R10's job):** `pending_treasure_extra_rewards`
   is drained only by `RunDriver._resolve_room`. Both `enter_point` callers in
   the package go through it (`driver.py:401`, `conformance/runner.py:851`), so
   there is no leak today, but any future non-driver consumer of `enter_point`
   would silently drop the screen. The report already flags the
   `RoomResolution` alternative as out of footprint; that is the right home.

---

## 9. REQUIRED FIXES (all documentation; no behavior change)

1. `sts2_rl/rewards.py:672-675` — replace "the repeat is always a no-op in
   practice, since every real caller generates before offering" with the
   two-entry-point statement, citing `RewardsCmd.cs:47-50` (OfferCustom →
   offer-time dispatch) and `:55-60` (GenerateForRoomEnd → generate-time).
2. `sts2_rl/rewards.py:680-681` — refresh the construction-site line numbers
   to `rewards.py:735,798; run.py:1456`.
3. Proposed queue/record text — apply the same correction as (1) in both the
   GAP-QUEUE bullet and the two `event/*.json` `issue` amendments.
4. Add the `relic/wongos_mystery_ticket.json` amendment (§7) to the
   record-close proposals, and drop the "no existing entry anywhere" claim.

Optional (recommended, not blocking): one test pinning that a
Silver-Crucible-suppressed treasure room still dispatches, since
unconditionality is the specific thing `NTreasureRoom.cs:198-204` mandates and
nothing currently pins it.

---

## Re-review (2026-08-01) — text-only fix pass

Scope: only §9's four items. Code verdicts from §§1-6 stand and were not
re-opened.

### Item 1 — `rewards.py` docstring: CORRECT IN SUBSTANCE, TWO CITATION DEFECTS

The two-entry-point framing is now right and every structural citation checks
out against the source: `GenerateWithoutOffering` `RewardsSet.cs:125-147`;
generate-time entry `RewardsCmd.cs:55-60` reached from `CombatRoom.cs:267` /
`TreasureRoom.cs:82`; offer-time entry `RewardsCmd.cs:47-50`, whose body is
literally `new RewardsSet(player).WithCustomRewards(rewards).Offer()` with no
preceding generate call, making `Offer()`'s call at `RewardsSet.cs:159` that
set's first and only dispatch; `_isGenerated` `:127-130`/`:146`;
`HealRestSiteOption.cs:112`, `BrainLeech.cs:58`, `Trial.cs:185`,
`GlassEye.cs:32`. The sentence I flagged in §1a is gone and its replacement
is the stronger argument. Good.

Two defects remain, both in the same docstring:

1. **The refreshed construction-site line numbers are stale again — the fix
   re-staled itself.** `rewards.py:680-681` (now `:692-693`) cites
   "rewards.py:735,798", but adding ~35 docstring lines pushed those calls to
   **`rewards.py:751` and `:814`** (`grep -n "apply_reward_modifiers("`
   confirms). This is the exact failure mode §9 fix 2 existed to correct, and
   the numbers were evidently read before the edit that moved them.
   `run.py:1456`, `glass_eye.py:78`, `brain_leech.py:89`, `trial.py:118` are
   still correct. (Minor, optional: the list enumerates the six pre-existing
   sites and omits the new treasure site at `run.py:1357`.)
2. **"12 events" should be 13 (14 call sites).** `grep -rl
   "RewardsCmd.OfferCustom" src/Core/Models/Events/` → 13 files
   (`BattlewornDummy`, `BrainLeech`, `ColorfulPhilosophers`, `DrowningBeacon`,
   `EndlessConveyor`, `PotionCourier` ×2, `PunchOff`, `TheFutureOfPotions`,
   `TheLegendsWereTrue`, `Trial`, `WarHistorianRepy`, `Wellspring`,
   `WhisperingHollow`); relics = 8, confirmed. **This error is mine** — my
   §1a listed 13 names and wrote "12"; the fix pass faithfully copied it. The
   report's own arithmetic exposes it: it says the tree-wide grep returns "24
   files (23 callers + the definition)", and 1 def + `HealRestSiteOption` +
   `OneOffSynchronizer` + 12 events + 8 relics is 23, not 24. With 13 events
   it closes exactly.

### Item 2 — report §5/§6 record and queue text: ACCURATE, ONE COUNT TO FIX

Verified against the actual files, not the report's description:

- `event/brain_leech.json` / `event/trial.json` `G-new`: `verdict` is
  `"faithful"` in both, and the sentence being replaced is verbatim present
  (`brain_leech.json:79`, `trial.json:235`). The amendment now carries the
  two-entry-point framing with correct citations and an explicit
  "which reasoning this replaces" clause plus a visible correction note.
  **Applicable nearly verbatim.**
- `relic/wongos_mystery_ticket.json`: the guard is indeed **N7**
  (`what: "N7: the room gate -- C# is !(room is CombatRoom) -> return
  false"`, `verdict: faithful`) and its rationale does end with "the sim
  rejects it earlier" at line 264. The staleness claim is correct and the
  proposed replacement is accurate. **One count to fix:** the parenthetical
  "each of the 7 room-gated relics rejects on its own room tuple" — only
  **6** of the 7 C# `TryModifyRewards[Late]` relics are room-gated
  (`AmethystAubergine`, `BlackStar`, `LavaRock`, `PrayerWheel`, `WhiteStar`,
  `WongosMysteryTicket`); `Driftwood` is ungated and is a no-op here only
  because `card_rewards` is empty, as is `PaelsWing`.
- The false-novelty claim is dropped and the section header/lead-in reworded
  honestly; the new `seam/hook_dispatch` guard text is unchanged and I
  re-confirmed each of its citations.
- §6 GAP-QUEUE bullet: the target bullet is still at `GAP-QUEUE.md:85-88` and
  the 3C paragraph at `:2690-2711`. The replacement now states the
  two-entry-point shape correctly, including "no generate-time call precedes
  it, so `Offer()`'s call at `RewardsSet.cs:159` is that set's sole dispatch,
  not a harmless repeat". **Applicable nearly verbatim.**
- The "Fix pass (2026-08-01)" section is an honest, checkable account: it
  states the reviewer verdict, re-derives the central C# claim independently
  before editing, names what each edit replaced, and explicitly lists the
  optional test it did not add. Its only error is the "12 events" breakdown
  carried over from my §1a.

### Item 3 — behavior-free: CONFIRMED

`git diff -- sts2_rl/rewards.py` contains exactly three executable additions,
all three previously reviewed and unchanged by this pass: the
`generated: bool = False` dataclass field, `if rewards.generated: return`, and
`rewards.generated = True`. Every other added line is a `#` comment or
docstring prose (verified by filtering the `+` lines). `run.py` and
`driver.py` were not touched — their dispatch/backstop call sites are still at
`run.py:552`, `run.py:1357`, `run.py:1456` and `driver.py:484`, the identical
line numbers I read during the first review. Re-ran
`test/test_reward_dispatch_choke_point.py test/test_rewards.py
test/test_rng_tripwire.py` → **61 passed**.

### Re-review verdict: NEEDS-FIXES (three one-line text edits)

1. `rewards.py` docstring: `rewards.py:735,798` → `rewards.py:751,814`.
2. Same docstring (and the report's Fix-pass §): "12 events" → "13 events
   (14 call sites)" — my error, propagated.
3. Report §5's wongos amendment: "each of the 7 room-gated relics" → "each of
   the 6 room-gated relics (Driftwood and Pael's Wing are ungated but iterate
   an empty `card_rewards` list here)".

Nothing else outstanding. The code, the tests and the record/queue reasoning
are all approved.
