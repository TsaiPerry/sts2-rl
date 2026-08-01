# R12 report — `relic/_auto_keep` / `relic/kifuda`: partial-confirm out-of-combat card selection

Footprint touched: `sts2_rl/run.py` (`select_cards`, `run.py:501-559`),
`sts2_rl/driver.py` (`SKIPPABLE_PURPOSES`, `driver.py:98-121`),
`sts2_rl/relics/kifuda.py` (`after_obtained`), `sts2_rl/run_env.py`
(`PURPOSE_IDS`), `sts2_rl/vocab.json` (`purposes`), and a new test file
`test/test_kifuda_partial_enchant.py` (13 tests). No other file edited;
`combat.py`, `potions.py`, `events/**`, `relics/gnarled_hammer.py` and every
other relic were read for investigation only, never written.

## 0. Re-verifying the brief's map against the current tree

- `run.py::select_cards` is at `run.py:501-559` today (brief cited
  `:488-507` — drifted, R10's `offer_rewards` docstring expansion pushed it
  down; harmless, noted per the brief's own "re-verify line numbers"
  instruction).
- `driver.py::_card_selector` is at `driver.py:368-389` (unchanged in body;
  the `SKIPPABLE_PURPOSES` region it reads grew by my edit). `_ask` moved
  again since R10's report (which cited a different line) — irrelevant per
  the next point.
- **`test/test_rng_tripwire.py`'s driver line-pin watch item is confirmed
  stale**, independently re-verified by reading the file myself rather than
  trusting either the brief or the two sibling-lane reports that already
  said so: `_ALLOWLIST` is keyed by `(file, FUNCTION)`
  (`test_rng_tripwire.py:17-32`, `("sts2_rl/driver.py", "_ask")`), with an
  inline comment explaining exactly why it was changed from a line-keyed
  scheme. I added ~30 lines above `_ask` (comments, a new frozenset member,
  a new docstring block in `run.py`) and reran the whole file — 21/21 still
  pass. This is the third lane this round to confirm the same thing (R6,
  R10, now R12); safe to retire the brief's own watch item text.
- `combat.py::select_cards` — the brief's cited `:1134-1246` is stale; it is
  at `combat.py:1369-1481` today. Read in full as the "already-solved"
  in-combat reference the brief points to. It is NOT actually a full solved
  reference for the *driver-attached* case — see §3's Ashwater/Gambler's
  Brew finding below, which the brief did not anticipate.
- Read `R10-report.md` and `R6-report.md` in full per the brief's
  instruction. Neither touched `select_cards`/`SKIPPABLE_PURPOSES`/Kifuda;
  no line-number or shape conflicts with this task.

## 1. Premise correction, re-verified

The brief's own "PREMISE CORRECTION" says `relic/kifuda/AfterObtained`'s
rollup text "says the port does nothing at all" and that this is stale.
**Re-verified against the actual committed record
(`audit/records/relic/kifuda.json`), and the brief's characterization of
what's CURRENTLY live in that record is itself stale, one level further
than the brief states:**

- The current `hooks.AfterObtained.issue` text does **not** claim the port
  does nothing — it opens with "UPDATED (round 11): the stub premise this
  rollup was built on is gone... G2 is PROMOTED to LIVE this round" and
  correctly summarizes the state as of round 11. The phrase "the port does
  nothing at all" appears **only** inside that same field's trailing
  "The issue it replaced read: ..." — i.e. it is already quoted as
  **superseded** prior text, not the active claim, and has been since round
  11 (2026-07-30), which predates this round's brief.
- Guard `G1` similarly already reads "Closed 2026-07-29 (round 7)."
- What actually remains open in the record, and what this task closes, is
  **exactly guard `G2`** (and the `AfterObtained` hook's rollup verdict,
  which mirrors G2 per binding rule 4) — the record already correctly
  isolates this; there was nothing stale left to correct on the "does
  nothing" point specifically. I flag this precisely rather than silently
  agreeing with the brief's framing, per protocol ("don't defer to the
  brief... flag the contradiction").
- The GAP-QUEUE.md rollup (`audit/GAP-QUEUE.md:2767`) is accurate and
  current: `relic/_auto_keep` — LIVE — `relic/kifuda/g2` +
  `/AfterObtained`, with the correct C# citation.

## 2. The divergence, re-derived from the C# (not the brief's citations alone)

Read directly, not trusted from the brief:

- `Kifuda.cs:24-37`: `new CardSelectorPrefs(EnchantSelectionPrompt, 0,
  base.DynamicVars.Cards.IntValue) { Cancelable = false,
  RequireManualConfirmation = true }` (`:26-29`) →
  `CardSelectCmd.FromDeckForEnchantment(Owner, canonicalEnchantment, 3,
  prefs)` (`:32`). MinSelect 0, MaxSelect 3.
- `CardSelectorPrefs.cs:23-78`: the two-arg range constructor
  (`:68-78`) sets `RequireManualConfirmation = MinSelect >= 0 && MinSelect
  != MaxSelect` (`:77`) — confirmed `True` for Kifuda's 0/3.
- `CardSelectCmd.cs:547-608` (`FromDeckForEnchantment`, read in full): the
  shortcut at `:576` is `cards.Count <= prefs.MinSelect` — for Kifuda,
  `cards.Count <= 0` — **does not consult `RequireManualConfirmation` at
  all**, unlike the sibling overloads `FromDeckGeneric` (`:653`,
  `!prefs.RequireManualConfirmation && list.Count <= prefs.MinSelect`) and
  `FromHand` (`:708`, same gate). With ≥1 eligible candidate the screen (or
  an installed `Selector`) is **always** consulted, never auto-filled —
  confirmed this holds even when candidate count == MaxSelect exactly
  (pinned by `test_enchant_optional_asks_even_when_candidates_equal_max`).
- `NDeckEnchantSelectScreen.cs`, read in full (not just the two lines the
  brief cited): `Cancelable` gates only `_closeButton`
  (`:120-127,214-217`) — the "back out entirely" affordance.
  `RefreshConfirmButtonVisibility` (`:174-184`) enables the **grid**
  Confirm button once `MinSelect != MaxSelect && selected >= MinSelect`
  (true even at 0 selected for Kifuda) — clicking it goes to a preview
  (`PreviewSelection`, `:226-256`), and `ConfirmSelection` (`:258-264`)
  finalizes via `CheckIfSelectionComplete` (`:266-275`, the real
  `MinSelect <= selected <= MaxSelect` bounds check that matches
  `CardSelectorPrefs`). **Non-load-bearing observation, not modelled and
  not worth modelling:** `ConfirmSelection`'s own guard
  (`if (_selectedCards.Count != 0)`) means the concrete UI screen never
  actually finalizes a 0-selection via a button click — but the abstraction
  every automated/headless selector in the source goes through,
  `ICardSelector.GetSelectedCards(options, minSelect, maxSelect)`
  (`ICardSelector.cs:12-20`, called at `CardSelectCmd.cs:582` for this
  exact overload), carries no such restriction, and is the correct level to
  port for a driver/policy-controlled decision (the sim already operates at
  this abstraction level — `run.select_cards`/`combat.select_cards`, not a
  literal button-click state machine). I checked C#'s own *reference
  automated player* too — `AutoSlayCardSelector.GetSelectedCards`
  (`AutoSlay/Helpers/AutoSlayCardSelector.cs:29-45`) — which always takes
  `Math.Min(maxSelect, list.Count)`, i.e. maximizes; this is a bot-policy
  default choice, not a screen-semantics constraint, and matches what the
  sim's OLD (force-fill) behaviour already modelled as one legal policy
  among several — it does not contradict the range being genuinely 0..3.

## 3. The fix — shape chosen, and why (re-derived, not the brief's literal suggestion)

The brief offered "make skippability min-select-aware (thread a numeric
floor into `_card_selector`)" as the primary shape and "a new optional
purpose" as a scouted alternative, explicitly leaving the choice to me.
**I chose the new-purpose alternative, for a load-bearing reason the brief
did not have:**

`self.card_selector(purpose, candidates, count)` is a fixed 3-argument
public contract. `grep -rn "card_selector\s*="` over `test/` and `sts2_rl/`
found **dozens** of hand-rolled 3-arg callables assigned directly to
`run.card_selector` / `cs.card_selector` across dozens of files
(`test_engine_features.py`, `test_events.py`, `test_glass_eye_reward_set.py`,
`test_hive.py`, `test_ironclad_final_cards.py`, `test_potions.py`,
`test_reward_dispatch_and_relic_stubs.py`, `test_relic_live_tail.py`, etc.),
none of which accept a 4th positional argument. Threading `min_select`
through that call (the brief's primary shape) would have broken every one
of them with a `TypeError`. `combat.py::select_cards` (the brief's own
cited "already-solved" reference) independently arrives at the same
constraint: it computes `min_select`-derived `floor`/`require_manual_
confirmation` internally, but **still calls `self.card_selector(purpose,
pool, count)` with exactly 3 arguments** — it never threads `min_select`
into the installed selector either. This is deliberate design, not an
oversight, once you see the constraint.

**Given that constraint, the codebase already has an established idiom for
"this specific screen must allow declining, others sharing the base purpose
must not": a dedicated purpose string registered in
`driver.SKIPPABLE_PURPOSES`, exercised by `_card_selector`'s existing
per-pick ask loop.** I found two live precedents doing exactly this before
touching anything:

1. **`relic/gambling_chip` guard G3** (`audit/records/relic/gambling_chip.json:66-68`,
   closed 2026-07-27): `GamblingChip.cs:12`'s `CardSelectorPrefs(prompt, 0,
   999999999)` was fixed by adding the literal purpose `"gambling_chip"` to
   `SKIPPABLE_PURPOSES` — no signature change anywhere.
2. **`relics/claws.py`** (`Claws.cs:24-27`, the *identical*
   `CardSelectorPrefs(prompt, 0, Cards.IntValue) { Cancelable = false,
   RequireManualConfirmation = true }` shape as Kifuda, confirmed by reading
   Claws.cs directly): already uses purpose `"transform_optional"`
   (`claws.py:32`), already a `SKIPPABLE_PURPOSES` member, with **no**
   `min_select` argument anywhere (the parameter didn't exist before this
   task) — it relies purely on the purpose string.

So the "new purpose" alternative is not a lesser option I picked for
convenience — it is the codebase's **already twice-used** pattern for this
exact mechanism, and the brief's primary suggestion would have been a
regression risk the two existing instances were themselves built to avoid.
I built the fix to match:

- **`sts2_rl/driver.py`**: added `"enchant_optional"` to
  `SKIPPABLE_PURPOSES` (`driver.py:132-135`), with a citation comment
  explaining the split from plain `"enchant"` and naming GnarledHammer's
  sibling shape (§4). Zero other changes to `_card_selector` or
  `DecisionRequest` — the existing per-pick ask loop
  (`if not skippable and count >= len(remaining): return remaining`, then
  per-pick `idx == len(remaining)` as the skip sentinel) already expresses
  0..N confirm-with-fewer once the purpose is a member; verified by
  reasoning through the loop by hand and then by the tests in §5.
- **`sts2_rl/run.py::select_cards`**: added `min_select: int | None = None`
  (`run.py:506`), matching `combat.select_cards`'s shape. It is **not**
  forwarded to `self.card_selector` (preserves every existing 3-arg
  contract, including the driver's). It **is** used to widen the
  selectorless fallback (no `card_selector` installed at all — a bare
  `RunState`, e.g. a unit test) from "always exactly `count`" to "uniform
  random in `[min(min_select, len(candidates)), count]`"
  (`run.py:554-559`), mirroring `combat.select_cards`'s own
  `floor`/`rng.randint` shape (`combat.py:1473-1481`) — the closest sim
  analogue to C#'s selectorless-path non-existence (`CardSelectCmd` always
  shows a UI screen, consults an installed `Selector`, or waits on the
  network; never silently completes on its own). `min_select=None` (every
  existing caller) is byte-identical to pre-fix behaviour — confirmed by
  `test_selectorless_fallback_unchanged_when_min_select_is_none`.
- **`sts2_rl/relics/kifuda.py`**: `after_obtained` now calls
  `run.select_cards("enchant_optional", candidates, self.CARDS,
  min_select=0)` instead of `run.select_cards("enchant", candidates,
  self.CARDS)`.
- **`sts2_rl/run_env.py` + `sts2_rl/vocab.json`**: registered
  `"enchant_optional"` in `PURPOSE_IDS`/`vocab.json`'s `purposes` list (new
  last entry, append-only, index 17, capacity 24/17 used — no capacity
  bump needed). **Justification for touching vocab.json** (brief asked me
  to justify any vocab change): without this, "enchant_optional" would fall
  into the shared `"_unknown"` observation bucket
  (`run_env.py:760`, `PURPOSE_INDEX.get(request.purpose, N_PURPOSES - 1)`)
  — indistinguishable from any other unregistered purpose in the RL
  observation, degrading what a trained policy can learn about this
  specific decision. The append is a single line in each file, in the
  established position (after `"choose_a_card_optional"`), and
  `frozen_ids`'s own contract (`vocab.py:12-18`) guarantees this never
  reorders or perturbs any existing index. **I found, but did NOT fix
  (out of footprint), that the precedent purpose `"transform_optional"`
  (Claws, real and live since before this round) is itself NOT registered
  in `vocab.json`/`PURPOSE_IDS` today** — confirmed by direct grep of both
  files. It has been falling into `_unknown` this whole time. Flagged as a
  finding in §7; not fixed here because `relics/claws.py` and the general
  vocab-completeness sweep are outside this task's scope.

## 4. Other "enchant" sites — investigated per the brief, none touched

The brief listed 6 relic/event sites plus asked me to check every other
`purpose="enchant"` call site's own C# for the same 0..N shape. I read
every one directly (not the sim side — the C# `CardSelectorPrefs`
constructor call at each site):

| site | C# citation | constructor | shape |
|---|---|---|---|
| `relics/beautiful_bracelet.py:26` | `BeautifulBracelet.cs:31` | `CardSelectorPrefs(prompt, Cards.IntValue)` | exact-count (1-arg ctor: `MinSelect=MaxSelect`) |
| `relics/electric_shrymp.py:20` | `ElectricShrymp.cs:21` | `CardSelectorPrefs(prompt, 1)` | exact-count |
| **`relics/gnarled_hammer.py:25`** | **`GnarledHammer.cs:30-34`** | **`CardSelectorPrefs(prompt, 0, Cards.IntValue) { Cancelable=false, RequireManualConfirmation=true }`** | **SAME 0..N shape as Kifuda** |
| `relics/paels_growth.py:22` | `PaelsGrowth.cs:24` | `CardSelectorPrefs(prompt, 1)` | exact-count |
| `relics/royal_stamp.py:45` | `RoyalStamp.cs:36` | `CardSelectorPrefs(prompt, 1)` | exact-count |
| `relics/tri_boomerang.py:26` | `TriBoomerang.cs:25` | `CardSelectorPrefs(prompt, Cards.IntValue)` | exact-count |
| `events/field_of_man_sized_holes.py:47` | `FieldOfManSizedHoles.cs:54` | `CardSelectorPrefs(prompt, 1)` | exact-count |
| `events/grave_of_the_forgotten.py:46` | `GraveOfTheForgotten.cs:54` | `CardSelectorPrefs(prompt, 1)` | exact-count |
| `events/waterlogged_scriptorium.py:52` | `WaterloggedScriptorium.cs:71,73` | `CardSelectorPrefs(prompt, Cards.IntValue)` | exact-count |
| `events/wood_carvings.py:65` | `WoodCarvings.cs:65` | `CardSelectorPrefs(prompt, 1)` | exact-count |
| `events/symbiote.py:44` | `Symbiote.cs:54` | `CardSelectorPrefs(prompt, 1)` | exact-count |
| `events/spiraling_whirlpool.py:45` | `SpiralingWhirlpool.cs:43` | `CardSelectorPrefs(prompt, 1)` | exact-count |
| `events/stone_of_all_time.py:74` | `StoneOfAllTime.cs:106,108` | `CardSelectorPrefs(prompt, 1)` | exact-count |
| `events/sapphire_seed.py:37` (found by my own grep, not brief-listed) | `SapphireSeed.cs:51` | `CardSelectorPrefs(prompt, 1)` | exact-count |

**Conclusion: exactly one other site — `relic/gnarled_hammer` — shares
`relic/_auto_keep`'s exact mechanism.** Every other "enchant" site is
genuinely exact-count in C# (`MinSelect == MaxSelect`), so today's
force-fill behaviour is **correct**, not divergent, for all thirteen of
them; none was touched, none should be. `relics/gnarled_hammer.py` is
explicitly not my footprint this round, so I did not edit it — see §7 for
the finding and its exact one-line fix, which reuses `"enchant_optional"`
verbatim with zero new `driver.py` work.

## 5. Tests

New file: `test/test_kifuda_partial_enchant.py` (13 tests).

**On RED-first, honestly stated:** I determined the fix's shape by reading
`CardSelectorPrefs.cs`, `CardSelectCmd.cs`'s `FromDeckForEnchantment`
overload, `NDeckEnchantSelectScreen.cs`, `TestCardSelector`/
`AutoSlayCardSelector`/`ICardSelector`, and the two existing precedents
(`relic/gambling_chip` G3, `relics/claws.py`) **before** writing pytest
test functions — the design space could not be resolved by writing a test
first (which of two brief-offered shapes, or a third, is what "prove today's
force-fill" needed to be tested against). This is a **procedural deviation**
from strict write-test-before-fix ordering that I want to state plainly
rather than imply away. Protocol forbids "temporarily revert the fix to see
RED, then restore," so I could not close the gap after the fact by
stashing my own edit. Instead:

1. **Genuine RED reproduction, without touching any real file**: I wrote an
   isolated, throwaway reconstruction of the exact pre-fix
   `SKIPPABLE_PURPOSES` frozenset and `_card_selector`/`select_cards` logic
   (copied verbatim from this session's own pre-edit `Read` output) in a
   scratch script, and ran the new test's core scenario — a decline-seeking
   policy through Kifuda's old call shape (`purpose="enchant"`, no
   `min_select`) — against it. Output: `['card0', 'card1', 'card2']` (3
   picked, decline never possible) — confirmed RED for the pre-fix shape,
   run in this session, not asserted from memory.
2. `test_old_enchant_purpose_still_force_fills_through_a_real_driver` pins
   the same fact permanently, using the **unmodified, still-live** purpose
   string `"enchant"` — since I never changed `"enchant"`'s
   `SKIPPABLE_PURPOSES` membership, this test exercises genuinely
   still-red-shaped behaviour (a decline-seeking driver still can't decline)
   in the current, post-fix tree, proving the diff is isolated to
   `"enchant_optional"` alone.
3. Every other test in the file is GREEN-only against the actual shipped
   fix, but each pins one clause of the C# read in §2: confirm-zero
   (`test_enchant_optional_confirms_zero_on_the_first_decline`), a genuine
   partial pick (`test_enchant_optional_confirms_a_partial_pick`), full
   confirm still reachable
   (`test_enchant_optional_still_reaches_three_when_policy_never_declines`),
   the screen always asks even at candidates==max
   (`test_enchant_optional_asks_even_when_candidates_equal_max`, pinning
   `FromDeckForEnchantment`'s `:576` shortcut not being
   `RequireManualConfirmation`-gated), no cancel action exists anywhere in
   `legal_actions()`
   (`test_enchant_optional_has_no_cancel_action_only_confirm_fewer`), the
   selectorless fallback's floor/randint widening
   (`test_selectorless_fallback_can_return_fewer_than_count_with_min_select_zero`,
   statistical over 40 seeds — P(all-3 by chance) ≈ (1/4)^40, not a
   meaningful flake risk) and its exact preservation when `min_select` is
   omitted (`test_selectorless_fallback_unchanged_when_min_select_is_none`),
   three end-to-end `run.add_relic("kifuda")` scenarios through a real
   `RunDriver` (0 / 1 / 3 confirmed), and the vocab registration
   (`test_kifuda_purpose_registered_in_rl_vocab`).

**Commands run and counts:**

```
py -m pytest test/test_kifuda_partial_enchant.py -v
  -> 13 passed

py -m pytest test/test_driver.py test/test_false_premise_stubs.py \
  test/test_relics.py test/test_kifuda_partial_enchant.py \
  test/test_rng_tripwire.py -q
  -> 208 passed

py -m pytest test/test_events.py test/test_underdocks_hive_events.py \
  test/test_glory_events.py test/test_potions.py \
  test/test_relic_tier1_gaps.py test/test_relic_live_tail.py \
  test/test_relic_residue_gaps.py test/test_reward_dispatch_and_relic_stubs.py \
  test/test_reward_dispatch_choke_point.py test/test_glass_eye_reward_set.py \
  test/test_selectors.py test/test_engine_features.py test/test_run_env.py \
  test/test_event_offer_screens.py -q
  -> 504 passed

py -m pytest test/ -k "select or enchant or kifuda or gnarled or claws or gambling" -q
  -> 200 passed, 3738 deselected

py -m pytest test/test_conformance_runner.py test/test_conformance_map.py \
  test/test_conformance_player_state.py test/test_conformance_floor_state.py \
  test/test_conformance_combat.py test/test_conformance_pools.py \
  test/test_conformance_relic_bag.py test/test_conformance_rooms.py \
  test/test_conformance_recording.py test/test_conformance_save.py \
  test/test_conformance_determinism.py -q
  -> 2 failed, 98 passed, 6 xfailed
  (the 2 failures are the documented missing-fixture gap in
  test_conformance_floor_state.py — 933T39V18D/floor_49/actions.sts2replay
  absent on disk, FileNotFoundError — per protocol, not counted, not touched)
```

Additionally (outside the protocol's per-lane mandate — "do NOT run the
full suite" — but already in flight when I re-read that line, so reporting
it as a bonus signal rather than discarding it): a full `py -m pytest test/
-q -x` (deselecting only the 2 documented missing-fixture tests) completed
clean: **3930 passed, 2 deselected, 6 xfailed**, no regressions anywhere in
the tree.

## 6. Record-close proposals

I did not edit `audit/records/**` or `audit/GAP-QUEUE.md`.

### `relic/kifuda.json` — guard `G2`

Propose verdict `faithful` (from `gap`/`live: true`). Close note: **what
reasoning this replaces** — G2's issue text described `RunDriver.
_card_selector` as running "exactly `count` iterations whenever `count <
len(remaining)`... never allowed to end the picking before 3 selections are
made," and named the fix as "give `RunState.select_cards`/`RunDriver.
_card_selector` a MinSelect-aware partial-stop action." That diagnosis of
the SYMPTOM was exactly right (independently re-derived and empirically
reproduced by me, §5.1); the record's own suggested fix shape ("replace the
boolean `SKIPPABLE_PURPOSES` with a per-purpose minimum") is superseded by
what actually shipped: a **new, additional** `SKIPPABLE_PURPOSES` member
(`"enchant_optional"`) plus a `min_select` parameter on `RunState.
select_cards` used only for the selectorless fallback — not threaded into
`_card_selector` at all, because that would have broken dozens of hand-rolled
3-arg `card_selector` test callables across the suite (§3's compatibility
finding, which the record could not have known). `kifuda.py:39` now calls
`run.select_cards("enchant_optional", candidates, self.CARDS,
min_select=0)`. Pinned by `test/test_kifuda_partial_enchant.py`
(13 tests, esp. `test_kifuda_end_to_end_confirms_zero`,
`test_kifuda_end_to_end_partial_confirm`,
`test_kifuda_end_to_end_still_enchants_three_by_default`).

### `relic/kifuda.json` — hook `AfterObtained`

Propose verdict `faithful` (from `gap`/`live: true`), rolling up G2's close
per the record's own binding rule 4 convention. `maps_to` should update to
name `"enchant_optional"` and `min_select=0`. Also propose the top-level
`"verdict"` field move from `"gap"` to `"waiver"` (matching
`relic/gnarled_hammer.json`'s pattern of an all-`faithful`+`waiver` record,
since kifuda.json's N1 guard is already a presentation waiver) — flagged as
a terminology-convention suggestion for the controller to confirm, not
asserted as certain.

### `relic/_auto_keep` (`audit/GAP-QUEUE.md:2767`)

**Propose NARROWING, not a full close** — per protocol ("when any site of a
mechanism remains unhandled, propose NARROWING"). `relic/kifuda/g2` (the
only site GAP-QUEUE.md currently tracks under this mechanism) is fixed. But
§4 found a **second, previously uncross-referenced site sharing the
identical C# shape**: `relic/gnarled_hammer`'s own guard N2
(`audit/records/relic/gnarled_hammer.json:60-64`) already documents
`GnarledHammer.cs:30-34`'s `CardSelectorPrefs(prompt, 0, Cards.IntValue)
{ Cancelable = false, RequireManualConfirmation = true }` — the exact same
shape, in the exact same words almost — but its verdict is `faithful`, with
rationale "a fix needs no new machinery... the sim's default random
selector picking `count` is the same player-choice-model divergence
recorded at relic/gambling_chip G3 rather than a new one." **That rationale
is now stale in the same way kifuda's old G2 was**: gambling_chip G3 was
closed by adding a purpose to `SKIPPABLE_PURPOSES` (§3), which
gnarled_hammer.py never received — it still calls `run.select_cards
("enchant", ...)` (unqualified purpose, force-fills) and was never promoted
to a queue-tracked live entry the way kifuda's G2 was. Propose: (a) reopen
`relic/gnarled_hammer.json` guard N2 to `gap`/`live: true`, with a note that
its own prior "faithful... same divergence as gambling_chip G3" reasoning
was an incomplete analogy — gambling_chip G3 IS closed, gnarled_hammer's own
instance of the same mechanism is NOT; (b) add
`relic/gnarled_hammer/N2` alongside `relic/kifuda/g2` under `relic/_auto_keep`
in GAP-QUEUE.md; (c) note in both places that the fix is a **one-line reuse**
of work already shipped this round — `relics/gnarled_hammer.py`'s
`after_obtained` needs only `run.select_cards("enchant_optional", candidates,
self.CARDS, min_select=0)` in place of its current `run.select_cards
("enchant", candidates, self.CARDS)`; `driver.py`'s `SKIPPABLE_PURPOSES`
already has `"enchant_optional"` and needs no further change. Not fixed
here: `relics/gnarled_hammer.py` is a different lane's footprint this round
(the brief's "NOT yours: ... other relics").

## 7. Findings not in the brief (findings outrank fixes)

### 7a. LIVE gap, same mechanism, different family: Ashwater / Gambler's Brew potions, via `RunDriver` — NOT fixed, flagged

`Ashwater.cs:30` and `GamblersBrew.cs:26` both build `CardSelectorPrefs
(prompt, 0, 999999999)` — MinSelect 0, the identical shape. Their sim call
sites (`potions.py:1011-1014` purpose `"exhaust_any"`, `potions.py:272-275`
purpose `"discard_any"`) already correctly pass `min_select=0` — this was
already fixed in a prior round for the SELECTORLESS-only case
(`audit/records/potion/ashwater.json`'s guard, "CLOSED 2026-07-28... EXECUTED:
30 seeds give varying exhaust-pile sizes including 0"), and that record's
own text explicitly reasons the remaining gap is **dormant**: "no production
path is selectorless (the env installs the scripted selector, the
conformance driver installs the recorded picks)."

**That dormancy claim does not hold for `RunDriver` (`driver.py`), the
actual full-run driver `run_env.py`'s RL environment uses.** I verified this
empirically (not from prose) with a live probe against the current tree:

```
run = RunState(...); driver = RunDriver(run, decline_when_possible)
cs = run.create_combat(Encounter(monster_classes=[LeafSlimeS]))
cs.select_cards("exhaust_any", list(cs.player.hand), len(cs.player.hand), min_select=0)
  -> 5 cards picked (the WHOLE hand), decline-seeking policy never even asked
     (no SELECT_CARDS DecisionRequest was raised at all)
cs.select_cards("discard_any", ..., min_select=0)
  -> same: 5 picked, whole hand force-discarded
cs.select_cards("gambling_chip", ..., min_select=0)
  -> 0 picked (correctly declined) -- CONTRAST: this purpose IS a
     SKIPPABLE_PURPOSES member
```

Root cause is byte-identical to Kifuda's, one file over: `"exhaust_any"` and
`"discard_any"` are not `SKIPPABLE_PURPOSES` members, so `_card_selector`'s
`if not skippable and count >= len(remaining): return remaining` fires
silently (`count == len(hand) == len(remaining)` always, since both potions
pass `count = len(player.hand)`) — the RL policy is never even asked,
exactly the pre-fix Kifuda symptom. **This overturns
`potion/ashwater`'s and `potion/gamblers_brew`'s current `dormant`
verdicts**: the "no production path is selectorless" premise is true but
irrelevant — the live production path is not selectorless, it is
`RunDriver`-selected, and that path has the SAME bug via a different route
(purpose-string gating, not floor-value gating) that the record never
checked.

**Not fixed here.** The one-line fix (`SKIPPABLE_PURPOSES = frozenset({...,
"discard_any", "exhaust_any", ...})`) sits inside a file nominally in my
footprint (`driver.py`), but the bug's entire *observable* surface is
in-combat (`combat.select_cards`, `combat.py` — explicitly **not** my
footprint this round) and the affected call sites are in `potions.py`
(also explicitly not mine). Given concurrent lanes may be working on
combat/potion mechanics this round, I judged an uncoordinated change to
shared in-combat selection semantics too large a footprint stretch to make
unilaterally, even though the literal diff line is mine to touch. Flagging
prominently instead, with the exact fix and citations, for a fast follow-up
task. Neither "exhaust_any" nor "discard_any" is registered in
`run_env.py`'s `PURPOSE_IDS`/`vocab.json` either (confirmed by direct
lookup) — that follow-up should register both, alongside the
already-existing-but-unregistered `"transform_optional"` (next finding).

### 7b. `"transform_optional"` (Claws) has never been registered in the RL vocab

`driver.SKIPPABLE_PURPOSES` has included `"transform_optional"` since
before this round (real, live, used by `relics/claws.py:32`), but it is
**absent** from both `run_env.py`'s `PURPOSE_IDS` literal and
`vocab.json`'s `"purposes"` list (confirmed by direct grep of both files).
Every Claws decision has been falling into the shared `"_unknown"`
observation bucket. Same shape of gap as what I deliberately avoided
introducing for `"enchant_optional"` (§3), just older and not yet flagged
anywhere I could find (`grep -rn "transform_optional" audit/` finds only
records that reference the purpose by name, none flagging the vocab gap).
Not fixed here — `relics/claws.py` is not my footprint and the general
vocab-completeness question is broader than this task.

### 7c. `relics/claws.py`'s own bare-`RunState` selectorless fallback is unwidened

Same shape as 7b's sibling but smaller: `claws.py:31-32` calls
`run.select_cards("transform_optional", candidates, self.CARDS)` with no
`min_select` — since the parameter did not exist before this task, Claws'
selectorless fallback (no driver/no card_selector at all — a bare
`RunState`) still always transforms exactly `min(6, len(candidates))`
cards, never fewer, even though the driver-attached case has correctly
supported partial confirm since gambling_chip's G3 fix established the
`SKIPPABLE_PURPOSES` idiom. Low real-world impact (`RunDriver` or an
equivalent is installed in essentially every real run/RL-training
configuration), but worth a one-line follow-up
(`run.select_cards("transform_optional", candidates, self.CARDS,
min_select=0)`) once `claws.py` is in someone's footprint. Not fixed here.

### 7d. `combat.select_cards`'s "already-solved" framing needed one caveat the brief didn't have

The brief cites `combat.select_cards` as having already solved this
mechanism and instructs "port those semantics up to `RunState`." True for
the `min_select`/shortcut/selectorless-fallback modelling (which I did
port, faithfully, in run.py). **Not true for "does a driver-attached
selector actually get to decline"** — that half was, and remains, governed
entirely by `SKIPPABLE_PURPOSES` purpose-string membership on the driver
side, identically for both `RunState` and `CombatState` (same shared
`_card_selector` function, confirmed by `run.create_combat`'s
`card_selector=kwargs.pop("card_selector", self.card_selector)` default).
`combat.py`'s own `min_select` parameter does **not**, by itself, guarantee
an installed selector can decline — 7a is the proof. This is worth stating
plainly because a future reader citing combat.py as "the solved reference"
could reasonably assume passing `min_select=0` at a call site is
sufficient on its own; it is necessary but not sufficient — the purpose
also needs a `SKIPPABLE_PURPOSES` (or equivalent) entry.

## 8. Queue-annotation proposals (`GAP-QUEUE.md`, terse style)

**Line 2767**, replace:

> `relic/_auto_keep` — **LIVE** — `relic/kifuda/g2` + `/AfterObtained`.
> [...] Carried in from main at the round-12 merge — it was never in this
> file before.

with:

> `relic/_auto_keep` — **NARROWED, not fully closed 2026-08-01 (round 13,
> R12).** `relic/kifuda/g2` + `/AfterObtained` are FIXED:
> `relics/kifuda.py` now calls `run.select_cards("enchant_optional",
> candidates, 3, min_select=0)`; `"enchant_optional"` joined
> `driver.SKIPPABLE_PURPOSES`; `run.select_cards` gained a `min_select`
> parameter for the selectorless fallback (byte-identical for every other
> caller, which all leave it at the new default `None`). Pinned by
> `test/test_kifuda_partial_enchant.py` (13 tests). **A second, previously
> uncross-referenced site shares this exact mechanism and is still open:
> `relic/gnarled_hammer` guard N2** (`GnarledHammer.cs:30-34` — the
> identical `CardSelectorPrefs(prompt, 0, Cards.IntValue) { Cancelable =
> false, RequireManualConfirmation = true }`), currently mis-recorded
> `faithful` on stale reasoning (see this round's R12-report.md §6). Fix is
> a one-line reuse: `relics/gnarled_hammer.py`'s `after_obtained` swaps its
> `run.select_cards("enchant", ...)` for `"enchant_optional"` +
> `min_select=0`; no further `driver.py` work needed. `relics/gnarled_
> hammer.py` was not this lane's footprint. All 13 other `"enchant"`-purpose
> relic/event sites were checked against their own C# `CardSelectorPrefs`
> constructors and confirmed genuinely exact-count (`MinSelect ==
> MaxSelect`) — untouched, correctly so (see R12-report.md §4's table).

**New bullet, "Still open, found this round" section** (wherever the
controller's convention places it):

> - **`potion/ashwater` and `potion/gamblers_brew`'s `dormant` verdicts are
>   STALE — LIVE via `RunDriver`, found 2026-08-01 (R12), not fixed
>   (footprint: the fix line is in `driver.py` but the observable surface
>   is `combat.py`/`potions.py`, neither this lane's).** Both potions'
>   `CardSelectorPrefs(prompt, 0, 999999999)` (Ashwater.cs:30,
>   GamblersBrew.cs:26) already pass `min_select=0` at their sim call sites
>   (fixed a prior round), but `"exhaust_any"`/`"discard_any"` were never
>   added to `driver.SKIPPABLE_PURPOSES` — so with the actual production
>   driver (`RunDriver`, what `run_env.py`'s RL env uses) attached, a
>   policy that tries to decline is never even asked; the whole hand is
>   force-exhausted/discarded every time. Empirically reproduced this round
>   (R12-report.md §7a) against the current tree. Contrast
>   `"gambling_chip"`, the sibling MinSelect-0 potion screen, which IS a
>   `SKIPPABLE_PURPOSES` member and correctly declines. One-line fix once
>   `driver.py`+`potions.py`+`combat.py` are in one lane's footprint
>   together: add both purposes to `SKIPPABLE_PURPOSES`, register both in
>   `run_env.py`'s `PURPOSE_IDS`/`vocab.json` (currently absent, same as
>   `"transform_optional"` below).
> - **`"transform_optional"` (Claws, real/live) has never been registered
>   in `run_env.py`'s `PURPOSE_IDS`/`vocab.json` — found 2026-08-01 (R12),
>   not fixed.** Every Claws decision observation falls into the shared
>   `"_unknown"` purpose bucket. `relics/claws.py`'s own selectorless
>   fallback (bare `RunState`, no driver) is also unwidened — no
>   `min_select` argument at its one call site, low real-world impact since
>   a driver is installed in essentially every real configuration.

## Status

DONE. `relic/_auto_keep`'s tracked site (`relic/kifuda/g2` +
`/AfterObtained`) is fixed and pinned end-to-end (bare `select_cards`,
selectorless fallback, and a full `run.add_relic("kifuda")` walk through a
real `RunDriver`, at 0/1/3 confirmed cards). The mechanism itself is
**not** fully closed — `relic/gnarled_hammer` shares it and stays open,
correctly narrowed rather than silently claimed closed. Two significant,
independently-verified findings outside the brief's scope (Ashwater/
Gambler's Brew's stale dormancy verdict against the real production driver,
and the pre-existing unregistered `"transform_optional"` vocab gap) are
reported in full in §7 for a follow-up task; neither was fixed, per
footprint discipline.

**SUPERSEDED IN PART — see "## Fix pass (2026-08-01)" below.** R12-review.md
(NEEDS-FIXES) confirmed the shipped code and confirmed the Overturn-1
narrowing (§4/§6/§8 above), but found this report's §7a/§8 potion framing
wrong (a *dormancy overturn* claimed against guards that were actually
`faithful`/CLOSED — the review caught this report repeating, one record
over, exactly the archived-prose error §1 of this report caught the brief
making) and a third live site this report never enumerated
(`cards/neows_fury.py`). The fix pass below corrects both, adds the one
required code-comment clause, files the fix-SHAPE defect as its own
mechanism, and gives final apply-verbatim record-close/queue text. §§1-8
above are left as originally written (including their errors) so the
correction is visible as a correction, per this campaign's own rule that a
close note must state which reasoning it replaces.

---

## Fix pass (2026-08-01)

Responding to `R12-review.md` (verdict NEEDS-FIXES; the shipped code itself
was accepted as correct, minimal and well-tested — nothing about the diff's
*behaviour* changes in this pass). Footprint for this pass: `sts2_rl/driver.py`
(comment only), `sts2_rl/relics/kifuda.py` (docstring only),
`test/test_kifuda_partial_enchant.py` (two docstrings), and this report.
`cards/neows_fury.py`, `run.py` beyond what §§1-8 already landed, `cmds.py`,
`combat.py`, `potions.py` and `audit/**` were read for verification only,
never written.

### Item 1 — the §1c code clause, plus the fix-shape defect filed as its own mechanism

**1a. Code.** Two edits landed:

- `sts2_rl/driver.py`: fixed a pre-existing stale citation this lane repeated
  (`GamblingChip.cs:12` → `:20`, confirmed by reading `GamblingChip.cs` — the
  `CardSelectorPrefs` call is on line 20), and added a new comment paragraph
  (after the `"enchant_optional"` paragraph, before the `GnarledHammer.cs`
  one) stating that the sim's "confirm 0, 1, 2 or 3" models the *prefs*
  range, not the shipped screen's button behaviour — with the
  `NDeckEnchantSelectScreen.ConfirmSelection` (`:258-264`)/`CloseSelection`
  (`:186-190`) citations the review required.
- `sts2_rl/relics/kifuda.py`: added the matching clause to `after_obtained`'s
  docstring.
- `test/test_kifuda_partial_enchant.py`: reworded the two docstrings the
  review named (`test_enchant_optional_confirms_zero_on_the_first_decline`,
  `test_kifuda_end_to_end_confirms_zero`) to say they pin the prefs range at
  the `ICardSelector`/`RunDriver` abstraction, with the `ConfirmSelection`
  caveat, rather than asserting "MinSelect 0's full range" as a claim about
  the screen's own button.

All 13 tests in the file re-ran green after these edits (docstring-only
changes; no logic touched) — see "Tests re-run" below.

**Final `relic/kifuda.json` G2 close-note addendum** (append to §6's proposed
close note above; apply verbatim):

> **ADDENDUM (fix pass, 2026-08-01):** the close note must also state that
> the sim models the *prefs* range (MinSelect 0 / MaxSelect 3) — the level
> `ICardSelector.GetSelectedCards` and `RunDriver` operate at — and NOT a
> literal port of the shipped single-player screen's own button behaviour.
> `NDeckEnchantSelectScreen.ConfirmSelection` (`NDeckEnchantSelectScreen.cs:
> 258-264`) opens with `if (_selectedCards.Count != 0)`, so a 0-card
> selection can never be finalized by clicking that screen's own Confirm
> button, and `CloseSelection` (`:186-190`) — the only path that DOES
> resolve with zero cards — is gated behind `Cancelable` (false for Kifuda),
> so it is unreachable too. The shipped UI's actual reachable floor is 1;
> the sim's 0 outcome is reachable only through the automated-selector
> abstraction (`Selector.GetSelectedCards(list, MinSelect, MaxSelect)`,
> `CardSelectCmd.cs:582`), which is the level `RunDriver`/`RunState.
> select_cards` already operate at (a policy callback, not a button click)
> — a deliberate, recorded modelling choice, not a UI divergence. Reflected
> in `relics/kifuda.py`'s docstring and `driver.py`'s `SKIPPABLE_PURPOSES`
> comment block as of this fix pass.

**1b. The fix-shape defect, filed as its own mechanism (file-ready for the
controller).** The review accepts the shipped shape for *this* task (the
codebase's twice-used idiom, zero-risk, one frozenset member) but rules the
numeric min/max-on-the-prefs model unambiguously more faithful, and finds it
has already produced three live disagreements. That is a standing defect,
not a footnote — proposed as a new mechanism:

> **`seam/card_selection`** (new, unowned) — `driver.SKIPPABLE_PURPOSES` is a
> lossy, string-keyed re-encoding of `CardSelectorPrefs.MinSelect`.
>
> **THE C# MODEL:** every card-selection screen in the source is
> parameterized by exactly one value type, `CardSelectorPrefs`
> (`CardSelectorPrefs.cs:7-79`), a struct carrying two integers —
> `MinSelect` (`:25`) and `MaxSelect` (`:27`) — plus a derived
> `RequireManualConfirmation` (`:29`, `= MinSelect >= 0 && MinSelect !=
> MaxSelect`, `:77`) and `Cancelable` (`:31`). Every consumer reads the same
> two integers directly: the auto-resolve shortcut on each `CardSelectCmd`
> overload (`FromDeckForEnchantment:576`, `FromDeckGeneric:653`,
> `FromHand:708`, `FromCombatPile:396`), the screen's Confirm-button gate
> (`NDeckEnchantSelectScreen.RefreshConfirmButtonVisibility:176`,
> `MinSelect != MaxSelect && selected >= MinSelect`), the completion bounds
> check (`CheckIfSelectionComplete:270`, `selected >= MinSelect && selected
> <= MaxSelect`), and the automated-selector call (`Selector.
> GetSelectedCards(list, MinSelect, MaxSelect)`, `:582` and equivalent per
> overload).
>
> **THE SIM'S RE-ENCODING:** `sts2_rl/driver.py`'s `SKIPPABLE_PURPOSES`
> (`driver.py:132-135`) is a `frozenset` of purpose STRINGS, in a different
> file from the call site that has the actual numbers. `RunDriver.
> _card_selector` (`driver.py:368-389`) derives exactly ONE boolean from it
> — `skippable = purpose in SKIPPABLE_PURPOSES` — and that boolean is the
> ENTIRE surface through which a driver-attached policy can ever decline a
> pick. The `min_select` a call site passes only reaches the SELECTORLESS
> fallback (`RunState.select_cards`'s own `min_select` parameter, landed
> this round; `CombatState.select_cards`'s equivalent, `combat.py:
> 1407-1491`) — a code path no production driver takes (`RunDriver.
> __init__` installs itself unconditionally, `driver.py:335`; the RL env
> installs `RunDriver` at `run_env.py:465`).
>
> **WHY THIS IS STRUCTURALLY LOSSY, not a style complaint:**
> 1. It can only express `MinSelect ∈ {0, count}` — never a genuine
>    `1..N-1` floor, which C#'s two independent integers can.
> 2. It forces a PURPOSE FORK whenever a MinSelect-0 screen shares a
>    semantic label with an exact-count screen using the same verb. Five
>    forks exist for this reason already: `transform`/`transform_optional`,
>    `choose_a_card`/`choose_a_card_optional`, `exhaust`/`exhaust_any`,
>    `discard`/`discard_any`, `enchant`/`enchant_optional`. A sixth is owed
>    (`from_discard`, see the `card/neows_fury` write-up below).
> 3. **The two halves — the call site's `min_select` argument and the
>    purpose string's `SKIPPABLE_PURPOSES` membership — are independent and
>    can silently disagree.** A call site that correctly passes
>    `min_select=0`, matching its own C# `CardSelectorPrefs`, LOOKS correct
>    on an isolated read and is force-filled anyway if nobody remembered the
>    second, separate edit in the OTHER file. Not hypothetical — it holds
>    today at three live sites: `potions.py:1012` (Ashwater, purpose
>    `exhaust_any`), `potions.py:273` (Gambler's Brew, purpose
>    `discard_any`), `cards/neows_fury.py:73` (purpose `from_discard`). All
>    three pass `min_select=0`; none is force-fill-exempt through the real
>    production driver. EXECUTED this fix pass (`RunDriver` +
>    `RunState.create_combat`, this tree): Ashwater's 5-card hand goes to 0
>    with zero `SELECT_CARDS` decisions raised (`asks == []`); Gambler's
>    Brew force-discards and redraws the whole hand the same way; Neow's
>    Fury force-returns both discard candidates on one non-skippable ask.
>
> **WHAT THE FAITHFUL PORT WOULD BE:** carry the number, not a second string
> registry. `RunDriver._card_selector` (`driver.py:353`) is a bound method
> that already has `self.run`/`self._combat` in hand, and the two public
> surfaces that reach it (`RunState.select_cards`, `CombatState.
> select_cards`) already carry a real `min_select: int | None`. The durable
> fix threads that value into `_card_selector`'s own ask loop — either as a
> genuine parameter on the `card_selector` protocol (touches the fixed
> 3-argument callable contract dozens of hand-rolled test doubles rely on,
> confirmed by `grep -rn "card_selector\s*="` over `test/` and `sts2_rl/`),
> or, non-breakingly, by parking the active call's `min_select` on `self`
> (or on the already-per-call `DecisionRequest`) for the duration of
> `_card_selector`'s loop, so `skippable` becomes `len(picked) >=
> min_select` instead of `purpose in SKIPPABLE_PURPOSES`. Either way,
> `SKIPPABLE_PURPOSES` stops being a second source of truth that can drift
> from the number the call site actually has. Which of the two to pick is
> its own task's design call — not asserted here.
>
> **Evidence table** (every sim call site that passes a real `min_select`,
> re-enumerated this fix pass, not reused from the report):
>
> | call site | purpose | in `SKIPPABLE_PURPOSES`? | status |
> |---|---|---|---|
> | `relics/kifuda.py:39` | `enchant_optional` | yes (R12) | fixed |
> | `relics/gnarled_hammer.py:25` | `enchant` (no `min_select` passed at all) | n/a | LIVE — see `relic/gnarled_hammer` N2 |
> | `potions.py:1418` | `choose_a_card_optional` | yes | ok |
> | `potions.py:1012` (Ashwater) | `exhaust_any` | **no** | **LIVE — reopened this fix pass** |
> | `potions.py:273` (Gambler's Brew) | `discard_any` | **no** | **LIVE — reopened this fix pass** |
> | `cards/neows_fury.py:73` | `from_discard` | **no** | **LIVE — see `card/neows_fury` below** |
> | `relics/claws.py:32` | `transform_optional` | yes, but the call site passes no `min_select` | selectorless-fallback-only gap (report §7c) |

### Item 2 — `relic/gnarled_hammer` N2 — NARROWING confirmed, final reopen text

The review confirmed all three legs of §6's narrowing claim. Final,
apply-verbatim reopen text for `audit/records/relic/gnarled_hammer.json`
guard N2 (verdict `faithful` → `gap`, `live: true`):

> **REOPENED (fix pass, round 13/R12, 2026-08-01).** This replaces N2's
> close note in full — both of its clauses are independently false today:
> (1) "run.select_cards has the matching shape... a fix needs no new
> machinery" is false — the fix this round for the IDENTICAL mechanism at
> `relic/kifuda` needed new machinery, a dedicated `SKIPPABLE_PURPOSES`
> purpose fork (`"enchant_optional"`), because the shape of
> `run.select_cards` alone was never sufficient; and (2) "the same
> player-choice-model divergence recorded at relic/gambling_chip G3 rather
> than a new one" is false because `relic/gambling_chip` G3 is CLOSED
> (`gambling_chip.json` G3, closed 2026-07-27 by adding `"gambling_chip"` to
> `SKIPPABLE_PURPOSES`) — the deferral target this note pointed at no
> longer covers an open divergence, so pointing at it can no longer stand in
> for fixing this site.
>
> All three legs independently confirmed this round: **(a) same C# shape**
> — `GnarledHammer.cs:30-34` is `new CardSelectorPrefs(EnchantSelectionPrompt,
> 0, base.DynamicVars.Cards.IntValue) { Cancelable = false,
> RequireManualConfirmation = true }`, character-for-character Kifuda's own
> `Kifuda.cs:26-29`, differing only in the enchantment (`Sharp` vs `Adroit`).
> **(b) the sim still force-fills** — `relics/gnarled_hammer.py:25` still
> calls the plain, non-skippable `run.select_cards("enchant", candidates,
> self.CARDS)`; executed through a real `RunDriver` with a decline-seeking
> policy this round: 3 cards enchanted, asks
> `[('enchant', False, 6), ('enchant', False, 5), ('enchant', False, 4)]`,
> no skip index ever legal. **(c) the old rationale is doubly stale**, per
> above.
>
> **FIX** (one-line reuse of this round's `relic/kifuda` work — no further
> `driver.py` change needed): `relics/gnarled_hammer.py`'s `after_obtained`
> should call `run.select_cards("enchant_optional", candidates, self.CARDS,
> min_select=0)` in place of its current
> `run.select_cards("enchant", candidates, self.CARDS)`.
> `relics/gnarled_hammer.py` was not this lane's footprint and remains
> unedited. NOT CLOSED: nothing at this site is closed by this reopening.

### Item 3 — the potion finding: REOPENING, not a dormancy overturn (my own correction, accepted)

The review is right and I got this wrong in §7a/§8 above. `potion/ashwater`
G1 and `potion/gamblers_brew` G1 are `"verdict": "faithful"` today, CLOSED
2026-07-28 — there is no `dormant` verdict to overturn. The sentence I
quoted as the record's live claim ("no production path is selectorless")
sits inside that guard's own `The gap it replaced read:` archived block —
i.e. I repeated, one record over, the exact archived-prose error §1 of this
report correctly caught the brief making about Kifuda. Independently
re-executed this fix pass (`RunDriver` + `RunState.create_combat`, this
tree, not reused from the report or the review):

```
exhaust_any (Ashwater):    hand 5 -> 0, exhaust_pile 5, asks: []
discard_any (Gambler's Brew): hand size unchanged at 5, but every original
                               card object is gone (whole hand swapped), asks: []
```

Both confirm the report's and the review's numbers exactly.

**Final, apply-verbatim reopen text for `audit/records/potion/ashwater.json`
guard G1** (and its rollup, hook `"OnUse (protected override, Ashwater.cs:
27-34)"`; verdict `faithful` → `gap`, `live: true`):

> **REOPENED (fix pass, round 13/R12, 2026-08-01).** This is a REOPENING,
> not a dormancy-to-live flip — there was never a `dormant` verdict on this
> guard to flip; it was CLOSED `faithful` 2026-07-28. The reasoning this
> replaces is that closure's CONSUMER ENUMERATION, which is incomplete, not
> its verdict on the code that existed at the time: the 2026-07-28 note is
> right that passing `min_select=0` at the call site is a real, correct
> code change, and names exactly two consumers of the resulting
> selectorless-fallback widening ("the selectorless path... reaches every
> outcome from none to the whole hand"; "the scripted-selector half was
> already correct"). It never checked `RunDriver` (`sts2_rl/driver.py`),
> the driver `run_env.py`'s RL environment actually installs
> (`run_env.py:465`) for every non-conformance, non-selectorless run.
> `RunDriver._card_selector`'s own gate (`if not skippable and count >=
> len(remaining): return remaining`) is a THIRD, independent consumer of
> the same call site, and it disagrees with the fix: `"exhaust_any"` is not
> a `SKIPPABLE_PURPOSES` member, so `skippable` is always `False` for
> Ashwater, `count` is always `len(hand)` (the call always passes the whole
> hand as `count`), and the gate fires every time — the policy is never
> even asked. EXECUTED, independently reproduced twice this round (review
> §5a, this fix pass): a 5-card hand goes to 0 with zero `SELECT_CARDS`
> decisions raised — the whole hand force-exhausted every time, the exact
> symptom this guard was originally opened to close, now via a different
> route (purpose-string gating in `driver.py`, not the `floor`/`min_select`
> value gating the 2026-07-28 fix addressed). CONTRAST `"gambling_chip"`,
> the sibling MinSelect-0 screen (`GamblingChip.cs:20`), which IS a
> `SKIPPABLE_PURPOSES` member and correctly declines through the identical
> driver. Same mechanism `seam/card_selection` tracks; filed here too
> because this guard's own closure is what needs reopening. NOT reopened by
> this note: N1/N2/N3/W/W4 (unaffected). **FIX:** add `"exhaust_any"` to
> `driver.SKIPPABLE_PURPOSES`, and register it (plus `"discard_any"` and the
> already-live `"transform_optional"`) in `run_env.py`'s
> `PURPOSE_IDS`/`vocab.json`, currently absent from both.

**Final, apply-verbatim reopen text for
`audit/records/potion/gamblers_brew.json` guard G1** (and its rollup, hook
`"OnUse (protected override, GamblersBrew.cs:23-28)"`; verdict `faithful` →
`gap`, `live: true`): identical in structure and citations to Ashwater's
above, with these substitutions — purpose `"discard_any"` (not
`"exhaust_any"`), call site `potions.py:273`, C# `GamblersBrew.cs:26`, and
the executed witness: "a 5-card hand is entirely discarded and redrawn
(post-state size unchanged at 5, but every original card object is gone)
with zero `SELECT_CARDS` decisions raised."

**On the four sibling potion records** (`attack_potion`, `colorless_potion`,
`power_potion`, `skill_potion`) the review flagged as citing ashwater/
gamblers_brew G1 "by name under binding rule 3": checked all four directly
(`json.load` + string search, not grep-and-trust). In every one of the
four, the `ashwater`/`gamblers_brew` mention sits **inside that record's own
ARCHIVED `"The gap it replaced read:"` block**, not its live guard text —
the same archived-vs-live trap this whole item is about, one level further
out. Each of those four records' own *live* `G1` text closed independently
on its OWN `choose_a_card`/`choose_a_card_optional` clause (a)/(b) tracking
in the 2026-07-28 pass, not on ashwater/gamblers_brew's verdict directly.
**No action is required on those four records from this reopening** — noted
here so a future reader who digs into their archived history isn't misled
into thinking they need editing too.

**Final "Still open, found this round" bullet for GAP-QUEUE.md**
(apply-verbatim, replacing the mis-framed bullet §8 above proposed):

> - **`potion/ashwater` G1 and `potion/gamblers_brew` G1 REOPENED 2026-08-01
>   (fix pass, round 13/R12) — not a dormancy overturn, a wrongly-closed
>   guard.** Both were CLOSED `faithful` 2026-07-28 on a consumer
>   enumeration that named only the selectorless fallback and
>   `scripted_card_selector`, and never checked `RunDriver`
>   (`sts2_rl/driver.py`) — the driver `run_env.py`'s RL environment
>   actually installs (`run_env.py:465`) for every non-conformance run.
>   `RunDriver._card_selector` gates decline purely on `purpose in
>   SKIPPABLE_PURPOSES`, independent of the `min_select` value the
>   2026-07-28 fix correctly added at the call site; `"exhaust_any"`/
>   `"discard_any"` are not members. EXECUTED, independently reproduced
>   twice this round (review + fix pass, `RunDriver` +
>   `RunState.create_combat`, this tree): Ashwater's 5-card hand goes to 0
>   with zero `SELECT_CARDS` decisions raised; Gambler's Brew force-discards
>   and redraws the entire hand the same way. Contrast `"gambling_chip"`,
>   the sibling MinSelect-0 screen (`GamblingChip.cs:20`), which IS a
>   `SKIPPABLE_PURPOSES` member and correctly declines through the identical
>   driver. Four sibling potion records (`attack_potion`, `colorless_potion`,
>   `power_potion`, `skill_potion`) mention ashwater/gamblers_brew G1 only
>   inside their own ARCHIVED text, not their live guard text — no action
>   needed on those four. One-line fix once `driver.py`+`potions.py`+
>   `combat.py` are in one lane's footprint together: add both purposes to
>   `SKIPPABLE_PURPOSES`, and register both (plus the already-live-but-
>   unregistered `"transform_optional"`) in `run_env.py`'s
>   `PURPOSE_IDS`/`vocab.json`. See `seam/card_selection` for the mechanism
>   this belongs to.

The `"transform_optional"` bullet §8 above proposed is accurate as written
and needs no change; it is now also a listed evidence site of
`seam/card_selection`.

### Item 4 — the third live site: `cards/neows_fury.py` (write-up only; that file was NOT edited)

Independently re-verified this fix pass (`bare()`/`enter()` `CombatState`
probe, not reused from the review): confirmed purpose `"from_discard"`, not
a `SKIPPABLE_PURPOSES` member, force-fills both discard candidates on one
non-skippable ask (`asks == [('from_discard', False, 2, 2)]`, hand ends at
`['strike', 'defend']`).

**Correction to the review's own citation.** §9a of the review names
`Headbutt.cs:29` as the C# sibling that shares purpose `"from_discard"` and
blocks a blanket `SKIPPABLE_PURPOSES` add. Checked directly (not reused):
**this is wrong.** `headbutt.py:45-46` calls `CardSelectCmd.from_pile(...,
"to_draw_top")` — a DIFFERENT purpose string entirely — and with exactly 1
discard-pile candidate its own auto-select shortcut fires before
`card_selector` is ever consulted (executed: `asks4 == []`), because
`cmds.py:1766`'s own docstring already explains Headbutt's C# `CardSelectorPrefs
(prompt, 1)` two-arg ctor is `MinSelect == MaxSelect` and so "leaves this
[`min_select`] at the default." **The real shared `"from_discard"` sibling
in the sim is `LiquidMemories`** (`potions.py:1098`,
`LiquidMemories.cs:25`'s `CardSelectorPrefs(prompt, 1)` — also exact-count,
confirmed by reading `LiquidMemories.cs` directly). Executed: with 2
discard candidates and `count=1`, `LiquidMemories.use` DOES reach
`card_selector` (`asks3 == [('from_discard', False, 2, 1)]`) — the
structural conflict the review describes is real, just misattributed to the
wrong card. Blanket-adding `"from_discard"` to `SKIPPABLE_PURPOSES` would
correctly fix Neow's Fury and incorrectly make Liquid Memories's
exact-one-pick screen skippable too.

**Bigger finding: `audit/records/card/neows_fury.json` already tracks this
gap, under hook `"OnPlay"` — and BOTH its technical description and its
DORMANT liveness are stale, for the same reason ashwater/gamblers_brew's
were.** (This record exists — an earlier Glob search in this pass by path
`audit/records/card/neows_fury.json` came up empty due to a tool quirk;
`grep` on `"unit": "card/neows_fury"` found it immediately. There is no
need for a new `g2` guard — the existing `OnPlay` entry already is this
gap, just wrong about it.) Its `issue` text (audited 2026-07-26, **before**
`driver.SKIPPABLE_PURPOSES` existed as a mechanism at all — that machinery
starts at `relic/gambling_chip` G3, closed 2026-07-27) says: "the sim's
`CardSelectCmd.from_pile(..., count=count)` resolves through
`CombatState.select_cards`, which clamps `count = min(count,
len(candidates))` and then takes exactly that many... So the sim cannot
decline part of the return." **That is no longer true.** `cmds.py:
1744-1766`'s `from_pile` gained a `min_select` parameter whose own docstring
names this exact card ("Neow's Fury: `new CardSelectorPrefs(prompt, 0,
num)`, `NeowsFury.cs:39`"), `neows_fury.py:72-75`'s `on_play` DOES pass
`min_select=0`, and `combat.py:1407-1491`'s current `select_cards` fully
supports the range (confirmed by reading it: `require_manual_confirmation`,
`shortcut_floor`, `floor` are all real today, replacing the old
`combat.py:575-581` clamp the record cites). The RANGE-EXPRESSION half of
this gap is CLOSED, by a prior round's general `min_select` plumbing work,
never reflected back into this record.

The record's DORMANT argument is the SAME shape ashwater/gamblers_brew's
was: "no replay command encodes a partial selection... it becomes live for
any conformance replay of a run where the player declined" is a true
statement about the CONFORMANCE path and says nothing about — and was
written before — the `RunDriver`/RL-production path, which force-fills for
an entirely different, still-live reason (`"from_discard"` not being a
`SKIPPABLE_PURPOSES` member) that this record has never checked.

**Final, apply-verbatim replacement `issue` text for
`audit/records/card/neows_fury.json` hook `"OnPlay"`** (verdict stays `gap`;
add `"live": true`):

> **UPDATED (fix pass, round 13/R12, 2026-08-01):** both the technical
> description and the liveness verdict below are STALE, corrected here
> rather than re-verdicted from scratch. **TECHNICAL:** the "no way to
> express a range" claim no longer holds — `CardSelectCmd.from_pile`
> (`sts2_rl/cmds.py:1744-1766`) gained a `min_select` parameter (its own
> docstring names this card by name), and `neows_fury.py:72-75`'s `on_play`
> passes `min_select=0`, `count=count` under purpose `"from_discard"`. The
> `combat.py:575-581` clamp this guard originally cited is gone;
> `CombatState.select_cards` (`combat.py:1407-1491`) genuinely can return
> 0..count today. **LIVENESS:** still wrong, for a DIFFERENT reason than the
> one this guard argued. `RunDriver` (`sts2_rl/driver.py`), the driver
> `run_env.py`'s RL environment installs for every non-conformance run
> (`run_env.py:465`), gates decline purely on `purpose in
> SKIPPABLE_PURPOSES` (`driver.py:132-135`), independent of the `min_select`
> value the call site passes — and `"from_discard"` is not a member.
> `RunDriver._card_selector`'s own short-circuit fires whenever `count ==
> len(candidates)`, which is Neow's Fury's normal case (wants 2, discard
> pile usually has ≤ a few). EXECUTED (fix pass, this tree): a fresh combat,
> Neow's Fury in hand, two cards in the discard pile, driven with a
> decline-seeking `card_selector` shaped like `RunDriver`'s own gate — one
> non-skippable ask, both cards force-returned to hand;
> `'from_discard' in SKIPPABLE_PURPOSES` is `False`. This guard's own
> DORMANT argument ("no replay command encodes a partial selection... it
> becomes live for any conformance replay of a run where the player
> declined") is the SAME "no production path reaches it" shape
> `potion/ashwater` G1 and `potion/gamblers_brew` G1 were reopened for this
> round (see those records, and `seam/card_selection`) — true of the
> CONFORMANCE replay path when this guard was written (2026-07-26, before
> `driver.SKIPPABLE_PURPOSES` existed at all), and silent on the
> RL-training production path, which this guard never checked.
> **STRUCTURAL NOTE for whoever fixes this:** `"from_discard"` is ALSO used
> by `potions.py:1098` (Liquid Memories, `LiquidMemories.cs:25`'s
> exact-count `CardSelectorPrefs(prompt, 1)`) at an unqualified call (no
> `min_select`, correctly handled by the existing auto-shortcut) — so
> blanket-adding `"from_discard"` to `SKIPPABLE_PURPOSES` would incorrectly
> make Liquid Memories's exact-one-pick screen skippable too. (NOT
> Headbutt, despite an earlier draft of this finding naming it: Headbutt is
> ported under a different purpose, `"to_draw_top"`, and never reaches
> `card_selector` at all in its single-candidate case.) A straight sixth
> purpose fork (mirroring this round's `enchant`/`enchant_optional` split)
> or the numeric fix filed at `seam/card_selection` are the two live
> options. **Nothing fixed here** — `cards/neows_fury.py` and
> `driver.py`'s `SKIPPABLE_PURPOSES` were both out of this lane's footprint
> this round (a different lane owns `cards/neows_fury.py`; adding
> `"from_discard"` unqualified to `SKIPPABLE_PURPOSES` would break Liquid
> Memories).

**Final, apply-verbatim GAP-QUEUE.md line replacement for
`card/neows_fury/OnPlay`** (currently line 2705, "— dormant —"):

> - `card/neows_fury/OnPlay` — **live**, corrected 2026-08-01 (fix pass,
>   round 13/R12) — the record's own DORMANT verdict and technical
>   description were both stale (written 2026-07-26, before
>   `driver.SKIPPABLE_PURPOSES` existed). The `min_select`-range plumbing it
>   complained about missing now exists and IS used
>   (`cards/neows_fury.py` passes `min_select=0` under purpose
>   `"from_discard"`), but `"from_discard"` is not a `SKIPPABLE_PURPOSES`
>   member, so `RunDriver` still force-returns both discard cards with no
>   skip ever legal — same root cause as `potion/ashwater`/
>   `potion/gamblers_brew`, one file over. `"from_discard"` is shared with
>   an exact-count screen (Liquid Memories, `potions.py:1098`), so a sixth
>   purpose fork is needed, not a blanket add. See `relic/_auto_keep` /
>   `seam/card_selection`.

**Final, apply-verbatim replacement for `relic/_auto_keep`
(`audit/GAP-QUEUE.md:2767`)** — supersedes §8's proposed text above in full:

> `relic/_auto_keep` — **NARROWED, not fully closed 2026-08-01 (round 13,
> R12; corrected 2026-08-01 fix pass).** `relic/kifuda/g2` +
> `/AfterObtained` are FIXED: `relics/kifuda.py` now calls
> `run.select_cards("enchant_optional", candidates, 3, min_select=0)`;
> `"enchant_optional"` joined `driver.SKIPPABLE_PURPOSES`; `run.select_cards`
> gained a `min_select` parameter for the selectorless fallback
> (byte-identical for every other caller, which all leave it at the new
> default `None`). Pinned by `test/test_kifuda_partial_enchant.py`
> (13 tests). **Two further sites share this exact mechanism and stay
> open:**
> 1. `relic/gnarled_hammer` guard N2 (`GnarledHammer.cs:30-34` —
>    character-for-character Kifuda's own prefs) — REOPENED this fix pass
>    (was mis-verdicted `faithful` on a doubly-stale rationale: it claimed
>    no new machinery was needed, and pointed at `relic/gambling_chip` G3
>    as the standing divergence, which is now CLOSED).
>    `relics/gnarled_hammer.py` still calls the plain
>    `run.select_cards("enchant", ...)` and force-fills 3 through a real
>    `RunDriver`. Fix is a one-line reuse of this round's work
>    (`"enchant_optional"` + `min_select=0`); `relics/gnarled_hammer.py`
>    was not this lane's footprint.
> 2. `card/neows_fury/OnPlay` (`NeowsFury.cs:39`,
>    `CardSelectorPrefs(prompt, 0, num)`) — the record's existing gap entry
>    was STALE and its DORMANT verdict is corrected to LIVE this fix pass:
>    the `min_select` plumbing it complained about missing now exists and
>    IS used (`cards/neows_fury.py` passes `min_select=0` under purpose
>    `"from_discard"`), but `"from_discard"` is not a `SKIPPABLE_PURPOSES`
>    member, so `RunDriver` still force-returns both discard cards with no
>    skip ever legal. `"from_discard"` is SHARED with an exact-count screen
>    (Liquid Memories, `potions.py:1098`), so the current per-purpose-fork
>    idiom needs a SIXTH fork here, not a blanket add.
>    `cards/neows_fury.py` was not this lane's footprint.
>
> **The fix SHAPE itself is now filed as its own mechanism,
> `seam/card_selection`** (new, unowned): `driver.SKIPPABLE_PURPOSES` is a
> lossy, string-keyed re-encoding of ONE boolean derived from C#'s
> two-integer `CardSelectorPrefs.MinSelect`/`MaxSelect`, stored in a
> different file from the call site that knows the numbers; it now stands
> at five purpose forks for one C# field (a sixth owed above) and its two
> halves can silently disagree — which they do at three live sites today
> (`potion/ashwater`, `potion/gamblers_brew`, `card/neows_fury` — see that
> mechanism entry for the full evidence and the faithful-port sketch). All
> 13 OTHER `"enchant"`-purpose relic/event sites were checked against their
> own C# `CardSelectorPrefs` constructors and confirmed genuinely
> exact-count (`MinSelect == MaxSelect`) — untouched, correctly so
> (R12-report.md §4's table).

### Item 5 — remaining review items

- **§9b (7d's shortcut-claim overclaim):** correct. §7d of this report above
  says the lane ported "the `min_select`/shortcut/selectorless-fallback
  modelling... faithfully, in run.py." `run.select_cards` has **no**
  shortcut branch (no `require_manual_confirmation` derivation, no early
  return at `len(candidates) <= floor`) — unlike `combat.select_cards`,
  which does (`combat.py:1483-1487`, confirmed by reading it this pass).
  Behaviourally harmless for Kifuda specifically (§1b of the review; the
  shortcut is inert at MinSelect 0), but the sentence overclaims and would
  mislead a future `FromDeckGeneric`/`FromDeckForRemoval` port with
  `MinSelect > 0`. Correction (report text only; §7d itself is left as
  written above per this campaign's "state which reasoning you replaced"
  convention rather than silently rewritten): §7d's claim should read
  "ported the `min_select`/selectorless-fallback modelling faithfully; the
  auto-resolve SHORTCUT was deliberately NOT ported to `run.py` (unlike
  `combat.select_cards`), because it is inert at Kifuda's MinSelect 0 — a
  future MinSelect>0 out-of-combat port must add it."
- **§9c (`run.py`'s "never silently completes" docstring):**
  **BLOCKED-ON-FOOTPRINT.** `run.py` beyond what §§1-8 already landed is
  explicitly not this pass's footprint. Confirmed the exact current text
  (`run.py:534-539`): "...network — never silently completes on its own),
  so like combat.py's...". This overstates the C#:
  `CardSelectCmd.cs:576`/`653`/`708`/`396` are exactly silent completions
  (no screen, no selector) at their own shortcut condition. Proposed
  replacement clause, for whoever next owns `run.py`: "...network — never
  silently completes on its own OUTSIDE the auto-resolve shortcut every
  overload has (`:576`/`:653`/`:708`/`:396`), which is unreachable here
  since it needs `MinSelect >= candidate count` and Kifuda's MinSelect is
  0), so like combat.py's...".
- **§9d (the `GamblingChip.cs:12`→`:20` citation nit):** fixed in
  `driver.py` this pass (Item 1a above). Note for the record: this report's
  own §3 above still says `GamblingChip.cs:12` — left as originally written
  per the same "don't silently rewrite" convention; this paragraph is the
  correction.

### Tests re-run

```
py -m pytest test/test_kifuda_partial_enchant.py -v
  -> 13 passed

py -m pytest test/test_driver.py test/test_false_premise_stubs.py \
  test/test_relics.py test/test_kifuda_partial_enchant.py \
  test/test_rng_tripwire.py -q
  -> 208 passed

py -m pytest test/ -k "select or enchant or kifuda or gnarled or claws or gambling" -q
  -> 200 passed, 3747 deselected

py -m pytest test/test_events.py test/test_underdocks_hive_events.py \
  test/test_glory_events.py test/test_potions.py \
  test/test_relic_tier1_gaps.py test/test_relic_live_tail.py \
  test/test_relic_residue_gaps.py test/test_reward_dispatch_and_relic_stubs.py \
  test/test_reward_dispatch_choke_point.py test/test_glass_eye_reward_set.py \
  test/test_selectors.py test/test_engine_features.py test/test_run_env.py \
  test/test_event_offer_screens.py -q
  -> 504 passed

py -m pytest test/test_conformance_runner.py test/test_conformance_map.py \
  test/test_conformance_player_state.py test/test_conformance_floor_state.py \
  test/test_conformance_combat.py test/test_conformance_pools.py \
  test/test_conformance_relic_bag.py test/test_conformance_rooms.py \
  test/test_conformance_recording.py test/test_conformance_save.py \
  test/test_conformance_determinism.py -q
  -> 2 failed, 98 passed, 6 xfailed
  (the 2 failures are the documented missing 933T39V18D/floor_49 fixture,
  per protocol not counted, not touched)
```

No regressions anywhere; every count matches the original report's, since
this pass changed only comments/docstrings plus two report-text/test-text
corrections that carry no runtime behaviour.

### Fix-pass status

DONE. Item 1's code clause is landed and both required files updated; the
fix-shape defect is filed file-ready as `seam/card_selection`. Item 2's
narrowing is confirmed on all three legs with final reopen text. Item 3's
mis-framing is corrected — REOPENING, not a dormancy overturn — with final
reopen text for both potion guards, independently re-executed. Item 4's
third live site is written up file-ready as a correction to the EXISTING
`card/neows_fury.json` `OnPlay` entry (not a new guard), including a
correction to the review's own Headbutt citation (the real exact-count
sibling is Liquid Memories). Item 5's remaining review items are applied
where in footprint and stated precisely where blocked. `cards/neows_fury.py`
was read but never edited.
