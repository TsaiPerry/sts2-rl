# R10 report — consolidate the reward-modifier dispatch onto one choke point

Footprint touched: `sts2_rl/rewards.py`, `sts2_rl/driver.py`, `sts2_rl/run.py`,
plus a new test file `test/test_reward_dispatch_choke_point.py`.
`sts2_rl/relics/glass_eye.py`, `sts2_rl/events/brain_leech.py`,
`sts2_rl/events/trial.py`, `sts2_rl/conformance/runner.py` were read and
verified but **not edited** — see "Why the three per-site call sites did not
need to change" below.

## 0. The brief's map, re-verified against the C#

Before building, I re-read `RewardsSet.cs` and `RewardsCmd.cs` in full and
walked their real callers (`CombatRoom.cs`, `TreasureRoom.cs`,
`NTreasureRoom.cs`) rather than trusting the brief's citations. Findings:

- `RewardsSet.cs:125-147` (`GenerateWithoutOffering`), the `_isGenerated`
  guard (`:127-130`, set `:146`), and `Offer()`'s repeat call to it
  (`RewardsSet.cs:153-196`, call at `:159`) — **all confirmed exactly as
  cited.**
- The 6 real construction sites and their line numbers
  (`rewards.py:698,761`; `run.py:1419`; `glass_eye.py:78`;
  `brain_leech.py:89`; `trial.py:118`) and the "must NOT dispatch" wrapper
  sites (`driver.py:374,467-471,493-495,517`; `rewards.py:597-598`) —
  **all confirmed exactly as cited**, by reading each file, not by grep alone.
- The consumer list (`driver.py:448,543,655`; `conformance/runner.py:242`;
  `run.py:537` via `rewards_offerer`) — **confirmed**, with one correction:
  `run.py:523-543` is `RunState.offer_rewards`, not line 537 specifically;
  the method spans that range and its selectorless fallback loop is at
  `:546-550` (post-edit; `:539-543` pre-edit, matching the brief).
- **One brief citation is stale and I flag it per protocol:** the brief's
  "Watch items" section says `test/test_rng_tripwire.py:15` pins `driver.py`
  line numbers and warns that adding lines above `driver.py:306` trips it.
  Reading `test_rng_tripwire.py:9-32` shows this was true in the PAST but was
  already fixed: the allowlist is now keyed by `(file, FUNCTION)`, not
  `(file, line)` (`_ALLOWLIST = {("sts2_rl/driver.py", "_ask"), ...}`), with
  a comment explaining exactly this failure mode and why it was changed. I
  added 12 lines above `_ask` (an import expansion plus the new
  `_offer_treasure_extra_rewards` method) and re-ran
  `test/test_rng_tripwire.py` (21 passed) to confirm the watch item no
  longer applies.
- **The treasure-room citation needed correction, not just verification** —
  see §3.

## 1. The fix — which shape, and why

The brief offered two candidate shapes and asked me to re-derive the choice
from the C#, not defer to its recommendation. I did:

`RewardsCmd.OfferForRoomEnd` (the method the brief's framing centers on) is
**not actually called anywhere** in the decompiled game outside its own file
— `grep -rn "RewardsCmd\.(OfferForRoomEnd|GenerateForRoomEnd|OfferCustom|GenerateCustom)"`
across the whole tree shows only `HealRestSiteOption.cs:112` (`OfferCustom`),
every relic/event's own `OfferCustom` calls, and `TreasureRoom.cs:82` /
`CombatRoom.cs:267`, both of which call `GenerateForRoomEnd` — **not**
`OfferForRoomEnd`. The real shape every reward screen in this game actually
takes is:

1. **Generate immediately** at the moment the reward needs to exist —
   `CombatRoom.OfferRoomEndRewards` / `TreasureRoom.DoExtraRewardsIfNeeded`
   call `RewardsCmd.GenerateForRoomEnd`, which builds the `RewardsSet` AND
   calls `GenerateWithoutOffering()` right there (`RewardsCmd.cs:55-60`).
   This is where `Hook.ModifyRewards` actually fires and RNG is actually
   drawn.
2. **Offer** the already-generated set — a second, separate step
   (`await item.Offer()`) that calls `GenerateWithoutOffering()` again, but
   the `_isGenerated` guard makes that a no-op.

This is a **generate-then-idempotently-reoffer** shape, not a single
offer-time choke point — so shape (a) (idempotent flag + backstop at BOTH
ends) is the one that actually reproduces C#'s structure, not merely a safer
compromise. Shape (b) (delete the construction-time calls, dispatch only at
offer time) would have been unfaithful to the real C# control flow, not just
riskier for RNG order.

**What I built:**

- `CombatRewards.generated: bool = False` (`rewards.py`, in the dataclass) —
  mirrors `RewardsSet._isGenerated`.
- `apply_reward_modifiers` now returns immediately if `rewards.generated`,
  and sets `rewards.generated = True` as the LAST step (after both hook
  passes and the populate sweep) — mirroring `GenerateWithoutOffering`'s own
  ordering (`RewardsSet.cs:127-130` guard first, `:146` set last).
- The 6 real construction sites are **unchanged** — they still call
  `apply_reward_modifiers` explicitly, preserving their exact RNG draw
  order, exactly like C#'s real generate-time call.
- **New backstop calls**, mirroring `Offer()`'s repeat call
  (`RewardsSet.cs:159`):
  - `driver.py`'s `_offer_rewards` (top of the method, `driver.py:484`).
  - `run.py`'s `RunState.offer_rewards` (top of the method, before
    delegating to `rewards_offerer` or falling into the selectorless
    fallback loop, `run.py:552`).

Because both are idempotent no-ops on an already-generated set, every
existing site's behavior is unchanged, and a future site that forgets the
explicit call now gets dispatched exactly once anyway, at offer time.

## 2. Verdict per item in the brief

### Item 1 — the choke-point consolidation

**FIXED.** `CombatRewards.generated` + the guard in `apply_reward_modifiers`
(`rewards.py`) + backstop calls in `driver._offer_rewards` (`driver.py:484`)
and `RunState.offer_rewards` (`run.py:552`). Diff summary:

- `sts2_rl/rewards.py`: +1 dataclass field (`generated`), the early-return
  guard + trailing flag-set in `apply_reward_modifiers`, docstring rewrite
  explaining both halves of the shape, module-docstring addendum.
- `sts2_rl/driver.py`: `apply_reward_modifiers` added to the `.rewards`
  import; one new call at the top of `_offer_rewards`.
- `sts2_rl/run.py`: `apply_reward_modifiers` added to the `.rewards` import
  (module level, replacing the old local import inside `rest_heal_rewards`);
  one new call at the top of `offer_rewards`.
- `sts2_rl/relics/glass_eye.py`, `sts2_rl/events/brain_leech.py`,
  `sts2_rl/events/trial.py`, `sts2_rl/conformance/runner.py`: **no changes**
  — see below.

**Why the three per-site files and the conformance runner did not need
changes:** Glass Eye / Brain Leech / Trial already call
`apply_reward_modifiers` explicitly at their construction sites (the correct,
faithful shape — see §1). The new backstop calls are no-ops on top of that,
which is exactly the point: I added tests
(`test_glass_eye_construction_call_plus_offer_backstop_still_fires_once`,
`test_site_brain_leech_rip_fires_once`,
`test_site_trial_nondescript_guilty_fires_once`) proving each site's relic
hooks still fire exactly once through the real pipeline post-fix.
`conformance/runner.py`'s `ReplayRunner` subclasses `RunDriver` and does not
override `_offer_rewards`, so it inherits the backstop automatically.

Tests: `test/test_reward_dispatch_choke_point.py` (new, 15 tests, all
written and confirmed RED for the right reason before the fix — see §4).

### Item 2 — the treasure-room hole

**FIXED**, and the brief's own reading of the C# needed a correction along
the way (see §3). `run.py`'s `enter_point` TREASURE branch now also builds
an empty, `Room=Treasure` `CombatRewards` and dispatches
`apply_reward_modifiers` over it, mirroring
`TreasureRoom.DoExtraRewardsIfNeeded`; `driver.py` gained
`_offer_treasure_extra_rewards` to surface it when non-empty. **Dormant with
today's relic roster** (enumerated below) — this closes a structural gap
pre-emptively rather than fixing an observable divergence.

## 3. The treasure-room investigation — corrected reading, then fixed

The brief's citation of `RewardsCmd.OfferForRoomEnd` as the treasure-room's
dispatch path is **wrong** — as established in §1, that method is never
called anywhere in the decompiled tree. I traced the real path instead:

- `NTreasureRoom.cs:190-204` (`OpenChest`) calls, in order:
  1. `_room.DoNormalRewards()` → `OneOffSynchronizer.DoLocalTreasureRoomRewards`
     → `DoTreasureRoomRewards` (`OneOffSynchronizer.cs:108-143`): a **direct**
     `PlayerCmd.GainGold` call gated by `Hook.ShouldGenerateTreasure`, plus
     the Spoils Map payout. **No `RewardsSet` at all** — this never dispatches
     `Hook.ModifyRewards`. The chest relic pick goes through
     `TreasureRoomRelicSynchronizer`, also not a `RewardsSet`.
  2. `_room.DoExtraRewardsIfNeeded()` (`TreasureRoom.cs:75-97`) — called
     **unconditionally**, even when step 1 was suppressed. This builds
     `RewardsCmd.GenerateForRoomEnd(player, this)` →
     `RewardsSet.WithRewardsFromRoom(treasureRoom)` →
     `GenerateWithoutOffering`, which **does** fire `Hook.ModifyRewards`
     (`RewardsSet.cs:136`) — over a base `Rewards` list that
     `GenerateRewardsFor` (`RewardsSet.cs:206-246`) leaves **empty** for a
     `TreasureRoom` (it only adds anything for `CombatRoom`; for
     `TreasureRoom` it falls through with no throw, confirming the brief's
     `RewardsSet.cs:206-219` reading on that narrower point). `Room` is set
     to the `TreasureRoom` instance (not null), so room-gated relics see a
     real, non-null, non-combat room.

So the observable claim in the brief ("a C# `TryModifyRewards` implementer
can see treasure rooms; a sim one cannot") is **correct**, but the mechanism
named to support it was wrong — it is `DoExtraRewardsIfNeeded`, not
`OfferForRoomEnd`. I flag this per the protocol rather than silently fixing
it.

**Enumeration of every PORTED `modify_combat_rewards` / `_late` implementer**
(complete: `grep -rl "def modify_combat_rewards" sts2_rl/relics` — 8 files)
against `Room == Treasure`:

| relic | C# gate | fires on Treasure? |
|---|---|---|
| `amethyst_aubergine` | `room not in {Monster,Elite,Boss}` | no |
| `black_star` | `room != Elite` | no |
| `lava_rock` | `room != Boss` (+ act 0 only) | no |
| `prayer_wheel` | `room != Monster` | no |
| `white_star` | `room != Elite` | no |
| `wongos_mystery_ticket` | `room not in {Monster,Elite,Boss}` | no |
| `driftwood` | none — iterates `rewards.card_rewards` | **no gate, but the base list is always empty here, so 0 iterations — no-op** |
| `paels_wing` | none — iterates `rewards.card_rewards` | same as Driftwood — no-op |

I also confirmed, on the C# side, that these 8 (7 `TryModifyRewards[Late]`
implementers + Pael's Wing's `TryModifyCardRewardAlternatives`) are the
**complete** set of relic-side reward-screen listeners
(`grep -n "TryModifyRewards\b|TryModifyRewardsLate\b" src/Core/Models/Relics/*.cs`
→ exactly 7 files, matching the 7 sim relics 1:1). The only OTHER
unconditional (no room-gate) `TryModifyRewards[Late]` implementer in the
whole decompiled source is `Midas.cs`, which is a **run Modifier**
(`src/Core/Models/Modifiers/Midas.cs`), not a relic — Modifiers are the
existing, already-recorded out-of-scope waiver (note N4/N1 in
`seam/hook_dispatch.json`), so it does not change this enumeration.

**Conclusion: dormant with today's roster, real as a structural gap.** I
fixed it anyway rather than leaving it recorded-only, because the fix is
small and fully contained in my footprint (`run.py` + `driver.py`, no new
`DecisionKind`, reusing the existing `_offer_rewards`/`REWARD_CARD` machinery)
and it is the exact same choke-point mechanism as item 1 — leaving it
unfixed would have meant R10 built the idempotent choke point everywhere
except the one room type C# itself dispatches over.

**Implementation**: `RunState.enter_point`'s `TREASURE` branch, after the
existing gold+relic grant (now placed **unconditionally**, matching
`DoExtraRewardsIfNeeded`'s unconditional call — even a Silver-Crucible-
suppressed chest still dispatches), builds
`CombatRewards(room_type=RoomType.MONSTER, room=RoomType.TREASURE)` (the
`room_type`/`room` split mirrors the existing convention in
`driver._reward_selector`/`_offer_potion`: `room_type` is only the neutral
card-odds label, `room` is the real `RewardsSet.Room` mirror used for
gating), dispatches `apply_reward_modifiers`, and stashes the result on a new
`RunState.pending_treasure_extra_rewards` attribute only if non-empty.
`RunDriver._resolve_room` gained a `TREASURE` branch calling the new
`_offer_treasure_extra_rewards()`, which drains that attribute through the
existing `_offer_rewards`.

**BLOCKED-ON-FOOTPRINT note:** I deliberately did NOT add a field to
`RoomResolution` (`sts2_rl/rooms.py`) to carry this — `rooms.py` is not in my
footprint. I routed it through a new `RunState` attribute instead
(`pending_treasure_extra_rewards`, the same "stash on RunState, drain in the
driver" shape `pending_reward_extras` already uses), which stays entirely
inside `run.py` + `driver.py`. If a future task wants this surfaced on
`RoomResolution` instead (e.g. for the conformance runner to inspect without
reaching into `run.` private state), that edit is outside my footprint.

## 4. Tests

New file: `test/test_reward_dispatch_choke_point.py` (15 tests, 4 sections):

- **A (4 tests, RED-first, the core pin)**: `apply_reward_modifiers` called
  twice on the same `CombatRewards` must not double-fire. Confirmed RED
  before the `generated` flag existed — AmethystAubergine's gold doubled to
  30, Black Star pulled 2 relics, Prayer Wheel added 2 extra card groups, and
  a direct call-counting stub relic saw 3 calls for 3 dispatches. All GREEN
  after the fix.
- **B (3 tests, RED-first for 2 of them)**: the offer-time backstop
  dispatches a screen nobody explicitly generated —
  `driver._offer_rewards` and `RunState.offer_rewards`'s selectorless
  fallback loop, both confirmed RED (gold stayed 0) before the backstop
  calls existed. The third (`test_glass_eye_construction_call_plus_offer_
  backstop_still_fires_once`) was already green pre-fix (Glass Eye's own
  explicit call was already correct) and stays green — a regression guard,
  not a RED-first pin; I labelled it honestly as such rather than
  implying it was RED.
- **C (6 tests, regression proof, NOT RED-first)**: each of the 6 real
  construction sites, driven through the real pipeline
  (`run.generate_combat_rewards`, `run.rest_heal_rewards`,
  `glass_eye.after_obtained`, Brain Leech's RIP, Trial's Nondescript Guilty,
  and the final-act-boss early-return branch), still dispatches a
  call-counting stub relic's hook exactly once after the backstop is wired.
  These were already green before the backstop existed (nothing to
  double-fire yet) and stay green after — proving the new wiring didn't
  introduce a NEW double-dispatch. I call this out explicitly per the
  protocol's "prove idempotency with a RED-first test... and prove each of
  the 6 sites still dispatches exactly once end-to-end" — the brief asks for
  both, and only the first half is RED-first by nature.
- **D (2 tests)**: the treasure-room fix. D1 is the dormancy enumeration
  executed (all 8 relics attached, walk to a treasure node, assert
  `pending_treasure_extra_rewards is None` and the chest's own direct gold
  grant still ran) — RED before the attribute existed (`AttributeError`).
  D2 proves the wiring works for a hypothetical future Room==Treasure-gated
  relic (test-local stub, not registered globally): its `CardRewardGroup`
  reaches `pending_treasure_extra_rewards`, and
  `driver._offer_treasure_extra_rewards()` offers it through a real
  `REWARD_CARD` decision and clears the attribute. RED before (same
  `AttributeError`).

Commands run and counts (current, see note on flakiness below):

```
py -m pytest test/test_reward_dispatch_choke_point.py -v
  → 15 passed

py -m pytest test/test_rewards.py test/test_relic_tier1_gaps.py \
  test/test_rng_tripwire.py test/test_event_offer_screens.py \
  test/test_reward_dispatch_and_relic_stubs.py \
  test/test_event_reward_modifiers.py test/test_glass_eye_reward_set.py \
  test/test_driver.py test/test_darv.py test/test_shared_events.py \
  test/test_tier1_last_five.py test/test_reward_dispatch_choke_point.py -q
  → 322 passed

py -m pytest test/test_map.py test/test_neow.py \
  test/test_shop_and_map_mods.py test/test_false_premise_stubs.py -q
  → 560 passed   (map/event/treasure tests — covers the enter_point change)
```

Every one of these files is either brief-mandated
(`test_rewards*.py`/`test_relic_tier1_gaps.py`/`test_rng_tripwire.py`/
`test_event_offer_screens.py`), touched by the T31/T32 predecessor tasks I'm
building on (`test_reward_dispatch_and_relic_stubs.py`,
`test_event_reward_modifiers.py`), exercises `CombatRewards`/`RunDriver`
directly (`test_glass_eye_reward_set.py`, `test_driver.py`, `test_darv.py`,
`test_shared_events.py`, `test_tier1_last_five.py`), or exercises the
`enter_point`/map machinery I touched for the treasure-room fix
(`test_map.py`, `test_neow.py`, `test_shop_and_map_mods.py`,
`test_false_premise_stubs.py`).

**Note on flakiness / concurrent-agent noise:** while verifying, one isolated
run of `test/test_driver.py` showed 1 failure that did not reproduce on a
second run, and broader sweeps (`test_ancients.py`,
`test_combat_over_hook_gate.py`, all of `test_conformance_*.py`) are
currently failing with `AttributeError`s (`'HookSystem' object has no
attribute '_order_key'`, `'PlayerCombatState' object has no attribute
'is_active_for_hooks'`) and, once, a collection-time `NameError: name
'CAT_MONSTER' is not defined`. `git status` shows `sts2_rl/hooks.py` (+306/
-worth of diff) and `sts2_rl/powers.py` (+95/-worth) as **modified,
uncommitted, and not mine** — both are explicitly listed as NOT my
footprint in the brief. This is another agent's in-progress work landing
live in the shared worktree mid-session (the `NameError` on a transient
missing name is conclusive: that is not a stable state, it is a snapshot
mid-edit). None of the failing tests touch `rewards.py`/`driver.py`/`run.py`
in their tracebacks — every failure bottoms out inside `hooks.py` or
`monsters/base.py`'s import chain. I did not touch, and this task does not
require touching, any of those files. Re-running my full footprint-relevant
set (above) after observing this came back 322/322 and 560/560 clean, so I
treat this as environmental noise from concurrent work, not a regression
from R10 — but the controller should know the wider suite is unstable right
now for reasons unrelated to this task.

## 5. Record-close proposals

I did not edit `audit/records/**` or `audit/GAP-QUEUE.md`. Proposed changes:

### `event/brain_leech.json` — guard "G-new" (the RIP mid-event reward)

Verdict stays `faithful` (unchanged — Task 32's fix was already correct).
**Propose amending the `issue` text**, replacing the closing sentence "That
leaves the sim structurally unlike C#'s single choke point, which is a real
(recorded) tension: the next event ported this way can reintroduce the same
bug." with something like: "R10 (2026-08-01) closed this tension:
`CombatRewards.generated` (rewards.py) plus a backstop
`apply_reward_modifiers` call in `driver._offer_rewards` and
`RunState.offer_rewards` mirror the two dispatch entry points C# actually
has — generate-time for room-end sets (`RewardsCmd.cs:55-60`,
`GenerateForRoomEnd`) and offer-time for every `RewardsCmd.OfferCustom` set
(`RewardsCmd.cs:47-50`, which has NO generate-time call — `Offer()`'s repeat
call at `RewardsSet.cs:159` is that set's first and only dispatch), both
funnelled through the `_isGenerated`-guarded `GenerateWithoutOffering`
(`RewardsSet.cs:127-130/146`, re-called at `:159`) — so a future event built
this same way is now automatically dispatched exactly once even if it
forgets the explicit call — see `event/3C`'s updated note and
`test/test_reward_dispatch_choke_point.py`." **What reasoning this
replaces:** the old text asserted the per-site fix was structurally fragile
going forward; that is no longer true — the fragility is closed, not just
patched at two more sites. (**Correction from R10-review.md §1a/§7:** an
earlier draft of this amendment cited "mirroring `RewardsSet.Offer`'s own
repeat call" as if every C# caller generates before offering — false for the
`OfferCustom` majority, corrected above to the two-entry-point framing.)

### `event/trial.json` — guard "G-new" (Nondescript Guilty)

Same proposed amendment, same replaced reasoning, same citation.

### `event/the_future_of_potions.json` — `g15` (Event.offer_card_reward)

**No change proposed — confirmed correctly left open.** I re-verified this
gap is a missing reroll SURFACE in `events/base.py::Event.offer_card_reward`
(a boolean take-or-skip protocol with nowhere for a reroll flag to attach),
not a missing dispatch call — R10 does not touch `events/base.py` (out of
footprint per the brief) and would not have closed this even if it did; it
needs new capability, not wiring. Verdict stays `gap`, unchanged.

### New finding: the treasure-room dispatch gap (previously touched, but not closed, by another record)

**Correction (R10-review.md §7):** my original claim that
`grep -rn "TreasureRoom\|DoExtraRewardsIfNeeded"` over `audit/records/**` and
`GAP-QUEUE.md` found nothing was wrong — that grep DOES hit
`audit/records/relic/wongos_mystery_ticket.json:264` (guard N7), which
already knew C#'s `TreasureRoom` reaches `RewardsSet`
(`RewardsSet.cs:206-219`) and closes with: "C#'s TreasureRoom also reaches
RewardsSet (RewardsSet.cs:206-219) and its `room is CombatRoom` test
correctly rejects it; **the sim rejects it earlier**." That sentence is now
STALE: R10 makes the sim build the treasure `CombatRewards` and reach the
same rejection point C# does (6 of the 7 `TryModifyRewards[Late]` relics are
room-gated and reject on their own room tuple, e.g.
`wongos_mystery_ticket.py:40-43`; Driftwood is ungated and is a no-op on a
treasure set only because `card_rewards` is empty), so the sim no longer
"rejects it earlier" — it rejects it the same way, at the same point, as C#.
**Propose amending `relic/wongos_mystery_ticket.json` guard N7's `rationale`**
to replace that sentence with something like: "R10 (2026-08-01) made this
stale: the sim now builds an empty `Room=Treasure` `CombatRewards` in
`RunState.enter_point`'s TREASURE branch and dispatches
`apply_reward_modifiers` over it (`run.py:1355-1359`), mirroring
`TreasureRoom.DoExtraRewardsIfNeeded` (`TreasureRoom.cs:75-97`) — so Wongo's
Ticket now rejects a treasure room on its own room-tuple gate
(`wongos_mystery_ticket.py:40-43`), exactly as C# does, rather than never
reaching a treasure `RewardsSet` at all. Cross-reference the new
`seam/hook_dispatch` guard below." **What reasoning this replaces:** the old
sentence described the sim as structurally short of C#'s dispatch (harmless
because it never got there); after R10 the sim gets there and is rejected by
the same gate C# uses, which is a stronger, not merely different, form of
fidelity and should be recorded as such rather than left describing a
pre-R10 shape.

**Propose a new guard** for the treasure-room-hole finding itself, most
naturally under `seam/hook_dispatch.json` (it's a dispatch-completeness
question, same family as that record's step-32/34/38 material) or as a
standalone note wherever the controller judges fits best. Proposed text:

> **G-new (found AND fixed 2026-08-01, R10):** `RunState.enter_point`'s
> `TREASURE` branch never dispatched `Hook.ModifyRewards`, where C#'s
> `TreasureRoom.DoExtraRewardsIfNeeded` (`TreasureRoom.cs:75-97`) does, over
> an empty `Room=Treasure` `RewardsSet` (`GenerateRewardsFor` returns `[]`
> for `TreasureRoom`, `RewardsSet.cs:206-246`), called unconditionally even
> when `Hook.ShouldGenerateTreasure` suppressed the chest's own direct
> gold+relic grant. **DORMANT at the time it was found**: enumerated all 8
> ported `modify_combat_rewards`/`_late`/`TryModifyCardRewardAlternatives`
> implementers (the complete set — `grep -rl "def modify_combat_rewards"
> sts2_rl/relics`) and confirmed each is gated to Monster/Elite/Boss or only
> touches pre-existing `card_rewards` groups (always empty here), so no
> ported relic produced anything observable. Fixed anyway (contained,
> in-footprint, same mechanism as the main R10 task):
> `RunState.pending_treasure_extra_rewards` + `RunDriver.
> _offer_treasure_extra_rewards`. Pinned by
> `test/test_reward_dispatch_choke_point.py`'s section D (2 tests).

## 6. Queue-annotation proposals (GAP-QUEUE.md, terse style)

**Replace** the "Still open, found this round, owned by nobody" bullet
(currently: "The sim dispatches reward modifiers at several construction
sites where C# has exactly one choke point... Task 32 fixed per-site
because consolidating was out of footprint; the next event ported this way
can reintroduce the same bug.") with:

> - ~~The sim dispatches reward modifiers at several construction sites...~~
>   **CLOSED 2026-08-01 (R10):** `CombatRewards.generated` + an idempotent
>   offer-time backstop in `driver._offer_rewards`/`RunState.offer_rewards`
>   now mirror C#'s real shape — not one choke point called from one place,
>   but ONE choke point (`RewardsSet.cs`'s `_isGenerated`-guarded
>   `GenerateWithoutOffering`) reached from TWO entry points: generate-time
>   for room-end sets (`RewardsCmd.GenerateForRoomEnd`, `RewardsCmd.cs:55-60`)
>   and offer-time, for the FIRST and ONLY time, for every
>   `RewardsCmd.OfferCustom` set (`RewardsCmd.cs:47-50` — no generate-time
>   call precedes it, so `Offer()`'s call at `RewardsSet.cs:159` is that
>   set's sole dispatch, not a harmless repeat). Construction sites are
>   unchanged, but a future one that forgets the explicit call is now caught
>   automatically by the offer-time entry point. Also closed the same way:
>   the treasure-room reward-modifier hole (`run.py`'s TREASURE branch never
>   dispatched at all) — dormant with today's roster, fixed pre-emptively.
>   (**Correction, R10-review.md §1a/§7:** an earlier draft of this bullet
>   said the repeat call was "harmless" as if every C# caller generates
>   before offering — true only for room-end sets, false for the
>   `OfferCustom` majority; corrected above.)

**Update** the "3C. `event`" section's paragraph (the one beginning "The fix
is per-site because `driver.py`'s `_offer_rewards` has three other
callers...") to note the consolidation, per the record-close proposal above.

## 7. Findings not in the brief

1. **`RewardsCmd.OfferForRoomEnd` is dead code** — never called anywhere in
   the decompiled source outside its own file. The brief's framing leaned on
   it as the treasure-room's dispatch path; the real path is
   `TreasureRoom.DoExtraRewardsIfNeeded` → `RewardsCmd.GenerateForRoomEnd`.
   Worth knowing for any future task that cites `OfferForRoomEnd`.
2. **The `test_rng_tripwire.py:15` line-number watch item is stale** — the
   allowlist has been function-name-keyed for a while (its own comment
   explains why), so the warning in the brief no longer applies. Confirmed
   by adding 12 lines above `_ask` and re-running (21/21 passed).
3. **The wider test suite is currently unstable from concurrent,
   uncommitted work on `sts2_rl/hooks.py` and `sts2_rl/powers.py`** (neither
   in my footprint) — see §4's flakiness note. Not caused by, and not fixed
   by, this task.
4. Confirmed (not a new finding, but worth stating plainly since the brief
   asked me to re-derive rather than trust it): shape (a) is not just
   "materially safer" as the brief's scout framed it — it is the shape that
   actually matches C#'s real control flow, once `OfferForRoomEnd`'s
   non-existence is accounted for. Shape (b) was never really on the table.

## Fix pass (2026-08-01)

Applied all four `R10-review.md` §9 required fixes. Reviewer verdict was
NEEDS-FIXES on documentation/record text only — the review found the shipped
code correct, faithful and well pinned; no behavior changed in this pass.

Before making any edit I independently re-verified the review's central
claim against the decompiled C#: `RewardsCmd.OfferCustom`
(`RewardsCmd.cs:47-50`) reads `await new RewardsSet(player).WithCustomRewards
(rewards).Offer()` — there is no `GenerateWithoutOffering` call before
`Offer()`, so for every `OfferCustom` caller the repeat call inside `Offer()`
at `RewardsSet.cs:159` is the FIRST and ONLY dispatch, not a harmless
no-op repeat. `grep -rn "RewardsCmd\.OfferCustom" --include=*.cs .` over the
decompiled tree returns 24 files (23 callers + the definition), matching the
review's enumeration (`HealRestSiteOption.cs`, 12 events, 8 relics,
`OneOffSynchronizer.cs`). This is a materially stronger justification for the
landed shape (shape (a): idempotent flag + backstop) than the sentence it
replaces, because it shows C# itself has two dispatch entry points funneled
through one idempotency-guarded choke point — not one entry point whose
repeat call happens to be harmless.

1. **`sts2_rl/rewards.py:672-675`** (docstring of `apply_reward_modifiers`):
   replaced "the repeat is always a no-op in practice, since every real
   caller generates before offering" with the two-entry-point statement —
   room-end sets dispatch at generate time (`RewardsCmd.GenerateForRoomEnd`,
   `RewardsCmd.cs:55-60`), every `OfferCustom` set dispatches for the first
   and only time at offer time (`RewardsCmd.cs:47-50` → `Offer()` →
   `RewardsSet.cs:159`), both funnelled through the same `_isGenerated`-
   guarded `GenerateWithoutOffering` (`RewardsSet.cs:127-130/146`). Zero
   behavior change — docstring only.
2. **`sts2_rl/rewards.py:680-681`**: refreshed the stale construction-site
   line numbers from `rewards.py:698,761; run.py:1419` to the current
   `rewards.py:735,798; run.py:1456` (verified against the current file: the
   final-act-boss early return is at `:735`, the normal-combat dispatch at
   `:798`, the rest-heal dispatch at `run.py:1456`).
3. **Proposed queue/record text**: applied the same two-entry-point
   correction in two places in this report — the `event/brain_leech.json`
   and `event/trial.json` `issue`-amendment proposal (§5) and the
   GAP-QUEUE.md replacement bullet (§6) — both previously said the repeat
   call was "harmless"/mirrored "`RewardsSet.Offer`'s own repeat call" as if
   every C# caller generates before offering, which is false for the
   `OfferCustom` majority. Each edited passage keeps a visible
   "**Correction, R10-review.md §1a/§7**" note naming what it replaces, per
   protocol ("state which reasoning you replaced, not only which verdict").
4. **`relic/wongos_mystery_ticket.json` amendment added, false-novelty claim
   dropped** (§5): my original claim that no record anywhere mentioned
   `TreasureRoom`/`DoExtraRewardsIfNeeded` was wrong — I re-ran
   `grep -rn "TreasureRoom\|DoExtraRewardsIfNeeded" audit/records
   audit/GAP-QUEUE.md` myself and confirmed it hits
   `relic/wongos_mystery_ticket.json:264` (guard N7), whose `rationale` ends
   "the sim rejects it earlier" — true pre-R10 (the sim never built a
   treasure `RewardsSet`), now STALE (R10 makes the sim build one and get
   rejected by the same room-gate C# uses). Added a proposed amendment to
   that guard's `rationale` alongside the new `seam/hook_dispatch` guard
   proposal, and reworded the section header and lead-in so it no longer
   claims novelty it doesn't have.

**Not applied — the review's optional item:** "one test pinning that a
Silver-Crucible-suppressed treasure room still dispatches" (`R10-review.md`,
end of §9) is explicitly marked optional/not-blocking by the reviewer, and
this fix pass's footprint is docstrings/comments only (zero behavior, no new
test). Left as a follow-up for whoever next touches
`test_reward_dispatch_choke_point.py`'s section D.

**Verification:** `py -m pytest test/test_reward_dispatch_choke_point.py -q`
→ **15 passed** (same count as before this pass — expected, since nothing
executable changed). `py -c "import sts2_rl.rewards"` → imports cleanly.

**Footprint actually touched by this pass:** `sts2_rl/rewards.py` (one
docstring block, `apply_reward_modifiers`, lines ~667-702 — comments only)
and this report (`R10-report.md`, §5/§6 text). No other file edited; no
`audit/**` edits; no git index mutation.

## Status

DONE_WITH_CONCERNS — see the flakiness note in §4 (environmental, not mine)
and the record/queue text I could not write myself (protocol-forbidden).
The fix pass above resolves all four `R10-review.md` §9 required items;
status otherwise unchanged from the original report (record/queue text still
requires the controller to apply it to `audit/**`, which remains
protocol-forbidden for this lane).
