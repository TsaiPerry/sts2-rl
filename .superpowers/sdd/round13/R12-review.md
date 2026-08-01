# R12 review — `relic/_auto_keep` / `relic/kifuda`: partial-confirm out-of-combat card selection

**Verdict: NEEDS-FIXES.** The shipped code is correct, minimal, well-cited and
genuinely closes `relic/kifuda/g2`; the tests genuinely pin it (mutation-probed
below); the `gnarled_hammer` narrowing is right; the potion finding is real and
I reproduced it end-to-end. The fixes required are (1) one code-comment
correction where the sim's comments assert something `NDeckEnchantSelectScreen`
contradicts, (2) two corrections to the record-close / queue text the controller
will apply nearly verbatim — the potion finding is mis-framed as a *dormancy
overturn* when it is a **wrongly-closed guard**, and (3) a **third site of the
same live mechanism the report did not enumerate** (`cards/neows_fury.py`).
None of these is large; all of them are things that get baked into the audit
record if they go in as written.

Everything below was re-derived from the C# and from execution in this
worktree. I did not take a single claim from the brief or the report on trust.

---

## 0. Scope and attribution

`git diff HEAD -- sts2_rl/run.py sts2_rl/driver.py sts2_rl/relics/kifuda.py
sts2_rl/run_env.py` carries three lanes. Attributed and **excluded from this
review** per the review scoping:

| hunk | owner | evidence |
|---|---|---|
| `run.py` `pending_treasure_extra_rewards` + `enter_point` TREASURE block; `run.offer_rewards`/`driver._offer_rewards` `apply_reward_modifiers` backstop; `driver._offer_treasure_extra_rewards`; the two `.rewards` import edits | **R10** | `R10-report.md:69,79,84,86,101-110,132-145` names each of these by line |
| `run.py:457-464` `card.has_been_removed_from_state = True` in `remove_cards` | **R1** (landed by the controller after review) | `R1-report.md:989` filed it BLOCKED-ON-FOOTPRINT; `R1-review.md:1087-1092` ruled "LAND" |

R12's own delta is exactly: `driver.py` SKIPPABLE_PURPOSES (+ its comment
block), `run.py::select_cards` (`min_select` param + docstring + 4 fallback
lines), `relics/kifuda.py` (call + docstring), `run_env.py` PURPOSE_IDS,
`vocab.json` `purposes`, and the new `test/test_kifuda_partial_enchant.py`.
That is inside the declared footprint. `vocab.json` was permitted with
justification and the justification is given; note additionally that
`frozen_ids` (`vocab.py:101-121`) **auto-persists** appended ids, so that file
would have been rewritten by the first `import sts2_rl.run_env` regardless —
the "hand edit" concern does not arise.

---

## 1. The core fix vs the C# — VERIFIED, with one corrected clause

### 1a. The prefs are what the brief and report say

`Kifuda.cs:26-30`:

```csharp
CardSelectorPrefs prefs = new CardSelectorPrefs(CardSelectorPrefs.EnchantSelectionPrompt, 0, base.DynamicVars.Cards.IntValue)
{ Cancelable = false, RequireManualConfirmation = true };
```

with `CanonicalVars => new CardsVar(3)` (`Kifuda.cs:20`) → **MinSelect 0,
MaxSelect 3**. The range constructor (`CardSelectorPrefs.cs:68-78`) derives
`RequireManualConfirmation = MinSelect >= 0 && MinSelect != MaxSelect` at
`:77` → `true` here anyway; the object-initializer is redundant, not
load-bearing. Confirmed by reading both files, not by citation transfer.

### 1b. The auto-resolve shortcut

`CardSelectCmd.FromDeckForEnchantment` (`:562-608`) gates at `:576` on
`cards.Count <= prefs.MinSelect` — **and does not consult
`RequireManualConfirmation`**, unlike `FromDeckGeneric` (`:653`) and `FromHand`
(`:708`), both of which read `!prefs.RequireManualConfirmation && list.Count <=
prefs.MinSelect`. (`FromCombatPile` `:396` is the same gated form; `:287`/`:343`
likewise.) For Kifuda `MinSelect == 0`, so `:576` fires only on an empty
candidate list — a case `run.select_cards` already returns `[]` for. **So the
overload difference is inert for Kifuda**, and the sim's not modelling `:576`
in `run.select_cards` is harmless *here*. The lane's
`test_enchant_optional_asks_even_when_candidates_equal_max` pins the right
consequence.

### 1c. Screen semantics — the report's §2 is right about cancel and **over-permissive about zero**

- `Cancelable` gates **only** `_closeButton` (`NDeckEnchantSelectScreen.cs:120-127`,
  re-enabled at `:214-217`), and `CloseSelection` (`:186-190`) is the *only*
  code path in the screen that resolves the completion source with
  `Array.Empty<CardModel>()`. With `Cancelable = false` that button is
  `Disable()`d at `_Ready`. So **backing out is impossible** — correct, and the
  sim models this by simply having no cancel action (pinned by
  `test_enchant_optional_has_no_cancel_action_only_confirm_fewer`). Agreed.
- `RefreshConfirmButtonVisibility` (`:174-184`) enables the grid Confirm once
  `MinSelect != MaxSelect && _selectedCards.Count >= MinSelect` — true at 0
  selected for Kifuda. Agreed.
- **But the grid Confirm is wired to `PreviewSelection`, not to completion**
  (`:119`). Completion runs through `ConfirmSelection` (`:258-264`), whose
  first statement is `if (_selectedCards.Count != 0)`. An empty selection
  therefore **cannot be finalized through the screen**; and the escape from
  that preview, `CancelSelection`, calls
  `_grid.GetCardHolder(_selectedCards.Last())` at `:222`, which throws on an
  empty `HashSet`. So in the shipped single-player UI the reachable outcome
  set for Kifuda is **{1, 2, 3}**, not {0, 1, 2, 3}. The multiplayer arm
  (`CardSelectCmd.cs:600` `WaitForRemoteChoice`) is the same screen on the
  remote client. The only path that reaches 0 is
  `Selector.GetSelectedCards(list, 0, 3)` (`:582`), and `Selector` is
  `MegaCrit.Sts2.Core.TestSupport.ICardSelector` — "used by both test mode and
  AutoSlay" (`src/Core/TestSupport/ICardSelector.cs:8-10`) — never installed in
  a normal run.

**Ruling.** I *accept the sim's 0..3 as the model*: `MinSelect` is 0, the
confirm button is deliberately enabled at 0, and the `Count != 0` guard reads
as a UI oversight (the same oversight makes `CancelSelection` throw). Modelling
the prefs range rather than a button-state machine is the right altitude and
matches the abstraction the sim already operates at. **But the sim currently
asserts the opposite of what the screen does, in three places, with no caveat**:

- `relics/kifuda.py:27-29` — "The player may confirm having enchanted 0, 1, 2 or 3 eligible cards";
- `driver.py:99-102` — "the player may confirm 0, 1, 2 or 3 enchants";
- `test_kifuda_partial_enchant.py:85-89` / `:268-270` — "confirming NOTHING …
  is a first-class outcome", "MinSelect 0's full range".

A porter who later reads `NDeckEnchantSelectScreen.ConfirmSelection` will
conclude the sim is wrong and "fix" it. **Required fix (small, in footprint):**
add one clause to `relics/kifuda.py`'s docstring and `driver.py`'s comment
saying that the *prefs* range is 0..3 and that is what is modelled, while
`NDeckEnchantSelectScreen.ConfirmSelection` (`:258-264`) refuses to finalize an
empty selection so the shipped UI's reachable floor is 1 — a deliberate,
recorded modelling choice at the `ICardSelector.GetSelectedCards` altitude
(`CardSelectCmd.cs:582`). The same clause belongs in the `G2` close note (§8).

### 1d. Ordering / filter — no divergence

`:568-574` sorts the candidates by deck index before the selector sees them;
`kifuda.py:38` builds `candidates` by iterating `run.deck` in order, so the
sort is already satisfied. `CardCmd.Preview` (`Kifuda.cs:35`) is presentation.
Amount 3 (`Kifuda.cs:34` literal `3m`) matches `ADROIT_AMOUNT`.

### 1e. Executed

```
gnarled_hammer: enchanted=3 asks=[('enchant', False, 6), ('enchant', False, 5), ('enchant', False, 4)]
kifuda:         enchanted=0 asks=[('enchant_optional', True, 10)]
```
(decline-seeking policy through a real `RunDriver`, this tree, today.) The fix
works; the sibling does not.

---

## 2. The fix SHAPE — ACCEPT for this task, but it is *less* faithful and it
   *has already* misled porters

**Which is more faithful, plainly: the numeric one.** C# carries exactly two
integers on a struct (`CardSelectorPrefs.MinSelect`/`MaxSelect`,
`CardSelectorPrefs.cs:25-27`) and every consumer derives its behaviour from
them — the shortcut (`:576`/`:653`/`:708`/`:396`), the confirm-button gate
(`NDeckEnchantSelectScreen.cs:176`), the bounds check (`:270`) and the
automated selector call (`:582`). The sim's `driver.SKIPPABLE_PURPOSES` is a
**lossy re-encoding of one boolean derived from those two numbers, keyed on a
string, stored in a different file from the call site that knows the numbers.**
Consequences that are not hypothetical:

1. It can only express `min_select ∈ {0, count}`. A genuine `1..3` screen
   cannot be represented at all.
2. It forces a **purpose fork per screen** whenever a MinSelect-0 screen shares
   a semantic label with an exact-count one. Already forked:
   `transform`/`transform_optional`, `choose_a_card`/`choose_a_card_optional`,
   `exhaust`/`exhaust_any`, `discard_any`, and now `enchant`/`enchant_optional`.
   A sixth is already owed (`from_discard`, §9a).
3. **The two halves can silently disagree, and today they do at three sites.**
   A call site passing `min_select=0` looks correct in isolation and is
   force-filled anyway. I reproduced this at `exhaust_any`, `discard_any`
   (§5) and `from_discard` (§9a).

The report's stated reason for rejecting the brief's primary shape — "dozens of
hand-rolled 3-arg `card_selector` callables would `TypeError`" — is **factually
true** (I confirmed the 3-arg protocol at `run.py:551-552`,
`combat.py:1461-1465`, and that `combat.select_cards` deliberately does *not*
thread `min_select` into the selector either) but it is **not a proof that the
numeric shape is impossible** — only that it cannot be threaded through the
*selector call signature*. A non-breaking numeric route exists (park the active
`min_select` on the state for the duration of the call; `RunDriver._card_selector`
is a bound method with `self.run`/`self._combat` in hand). The report presents a
constraint on one implementation as a constraint on the design.

**Ruling.** For *this* task the chosen shape is the right call: it is the
codebase's twice-used idiom (`relic/gambling_chip` G3, `relics/claws.py`), it is
zero-risk, it is one frozenset member, and it closes the gap. I do **not**
require it to be redone. But it is structurally unlike C#, it *will* mislead
the next porter (it already has, three times), and the report's own §7d caveat
— "necessary but not sufficient" — is the correct diagnosis of a design defect
that should be filed as a mechanism, not left as a footnote. **Recommended
addition to the queue text (§8):** a standing entry that `SKIPPABLE_PURPOSES`
is a lossy encoding of `CardSelectorPrefs.MinSelect` and should be replaced by
a min-select-aware `_card_selector`, listing the three live sites as its
evidence.

---

## 3. No behaviour change for existing callers — VERIFIED

### 3a. `run.select_cards`

```python
floor = count if min_select is None else min(min_select, len(candidates))
if floor < count:
    count = self.rng.randint(floor, count)
```
With `min_select=None` (every pre-existing caller) `floor == count`, the branch
is dead, **no RNG draw is added**, and the trailing `rng.sample` is reached
with the identical argument. Byte-identical, including RNG stream position.
Pinned by `test_selectorless_fallback_unchanged_when_min_select_is_none` (which
survives mutation B, correctly — it is a control).

Minor note: the `randint` draw on the Kifuda path comes off the **shared run
RNG** (`self.rng`), where `combat.select_cards` deliberately routes its
equivalent onto the named parity stream (`combat_rng.card_selection`,
`combat.py:1470`). Only reachable with **no** selector installed, which no
production or conformance path is (the conformance runner installs recorded
picks — `conformance/runner.py:298`; `RunDriver.__init__` installs
`_card_selector` — `driver.py:320`). Not a defect; worth a line in the record
so a future parity investigation does not have to rediscover it.

### 3b. The other "enchant" sites — independently re-verified, table is correct

I read every `CardSelectorPrefs` construction the report's §4 table names,
rather than trusting it. All 13 use the **one-argument** constructor
(`CardSelectorPrefs.cs:62-66`, which delegates with `min == max`, so
`RequireManualConfirmation` derives `false`):

`BeautifulBracelet.cs:31`, `ElectricShrymp.cs:21`, `PaelsGrowth.cs:24`,
`RoyalStamp.cs:36`, `TriBoomerang.cs:25`, `FieldOfManSizedHoles.cs:54`,
`GraveOfTheForgotten.cs:54`, `WaterloggedScriptorium.cs:71` and `:88`,
`WoodCarvings.cs:65`, `Symbiote.cs:54`, `SpiralingWhirlpool.cs:43`,
`StoneOfAllTime.cs:106`, `SapphireSeed.cs:51`. **§4's table is accurate and its
conclusion — exactly one other site (`GnarledHammer.cs:30-34`) shares the shape
— is correct.** Good, load-bearing work; this is the part of the report I
tried hardest to break and could not.

`"enchant"` remains out of `SKIPPABLE_PURPOSES`; `test_enchant_purpose_not_in_
skippable_purposes` and `test_old_enchant_purpose_still_force_fills_through_a_
real_driver` pin it. 234 tests across `test_driver / test_false_premise_stubs /
test_relics / test_rng_tripwire / test_run_env / test_selectors /
test_kifuda_partial_enchant` pass, and 203 across `test_potions / test_events /
test_relic_live_tail / test_engine_features /
test_reward_dispatch_and_relic_stubs`.

### 3c. RL action space / vocab — VERIFIED, no dim change, no index shift

- `PURPOSE_IDS` gains `"enchant_optional"` at **index 17**; `N_PURPOSES =
  vocab_capacity("purposes") = 24` (`vocab.py:74`), so obs width is unchanged
  and slot 17 was previously a permanently-zero reserved slot. `frozen_ids`'
  append-only contract (`vocab.py:88-99`) guarantees no existing index moves.
  Executed: `PURPOSE_INDEX` = `{_unknown:0 … choose_a_card_optional:16,
  enchant_optional:17}`.
- Action space: `SELECT_CARDS` masks candidates into the card-id-keyed block
  and the skip into `mask[CHOICE_BASE]` when `request.skippable`
  (`run_env.py:563-568`, decoded at `:533-534`). `"enchant_optional"` reuses
  that existing mechanism; `N_ACTIONS` is unchanged.
- The `_unknown` fallback is `PURPOSE_INDEX.get(purpose, N_PURPOSES - 1)`
  (`run_env.py:768`) → index **23**, which is *not* the `"_unknown"` string's
  own slot (0). Pre-existing quirk, not this lane's; worth one line somewhere
  eventually.
- **`"transform_optional"` (Claws) really is unregistered** — confirmed by
  executing `PURPOSE_INDEX`, not by grep. So are `"exhaust_any"` and
  `"discard_any"`. §7b of the report is correct.

---

## 4. THE NARROWING CLAIM (`relic/gnarled_hammer`) — **CONFIRMED on all three legs**

1. **Same C# shape.** `GnarledHammer.cs:30-34` is
   `new CardSelectorPrefs(CardSelectorPrefs.EnchantSelectionPrompt, 0,
   base.DynamicVars.Cards.IntValue) { Cancelable = false,
   RequireManualConfirmation = true }` with `CanonicalVars` `new CardsVar(3)`
   (`:20`) — character-for-character Kifuda's, differing only in the
   enchantment (`Sharp`, `:35`) and the amount (`SharpAmount` 3, `:21`/`:36`).
2. **The sim really does force-fill.** `relics/gnarled_hammer.py:25` is still
   `run.select_cards("enchant", candidates, self.CARDS)`. Executed through a
   real `RunDriver` with a decline-seeking policy: **3 enchanted**, three
   `('enchant', skippable=False, …)` asks with no skip index in
   `legal_actions()`. The player cannot enchant 1 or 2.
3. **The record really is mis-verdicted.** `audit/records/relic/
   gnarled_hammer.json` guard **N2** is `"verdict": "faithful"` on the
   rationale *"…run.select_cards has the matching shape … an installed selector
   may return fewer or none — so a fix needs no new machinery, and the sim's
   default random selector picking `count` is the same player-choice-model
   divergence recorded at relic/gambling_chip G3 rather than a new one."*
   Both clauses are now false: a fix **does** need machinery (the purpose
   fork), and `relic/gambling_chip` G3 is **closed** — its own close note
   (`gambling_chip.json`) says so and names `SKIPPABLE_PURPOSES` as the fix, so
   the deferral target no longer covers this site.

**Ruling: NARROWING is the right verdict for `relic/_auto_keep`, and the
mis-verdict call is correct.** Do not close the mechanism. I would go one step
further than the report and note that `relic/_auto_keep` is better understood
as the *class* "MinSelect-0 screen that the driver force-fills", in which case
the potion and Neow's Fury sites belong under it too (§5, §9a) rather than as
loose "found this round" bullets.

---

## 5. THE POTION CLAIM — **substance CONFIRMED and it is worse than reported;
   the FRAMING is wrong and must not be applied as written**

### 5a. Reproduced independently, end to end

`Ashwater.cs:30` and `GamblersBrew.cs:26` both build
`new CardSelectorPrefs(base.SelectionScreenPrompt, 0, 999999999)`.
`GamblersBrew` goes through `FromHandForDiscard` (`CardSelectCmd.cs:746-759`),
which delegates to `FromHand`, whose shortcut (`:708`) is
`!RequireManualConfirmation && list.Count <= MinSelect` — false, so the screen
is **always** shown and any subset is confirmable. `potions.py:1012` and
`potions.py:273` both already pass `min_select=0`.

Through the real production driver, in this tree, today:

```
exhaust_any    skippable=False  hand=5  picked=5  asks=[]
discard_any    skippable=False  hand=5  picked=5  asks=[]
gambling_chip  skippable=True   hand=5  picked=0  asks=[('gambling_chip', True, 5)]

ashwater       used=True  hand 5 -> 0  exhaust_pile=5  asks=[]
gamblers_brew  used=True  hand 5 -> 5  discard_pile=5  asks=[]
```

Drinking Ashwater **exhausts the entire hand** and the policy is never asked.
This is a large, live, in-production divergence — bigger in impact than the
task it was found beside. The report's §7a is right on the mechanism, right on
the root cause (`_card_selector`'s `if not skippable and count >=
len(remaining): return remaining`, `driver.py:354-356`, with `count ==
len(hand)` always), and right that `run_env.py:465` installs `RunDriver`, whose
`__init__` sets `run.card_selector` (`driver.py:320`) which `create_combat`
inherits (`run.py:1546`). **Confirmed in full.**

### 5b. But it is NOT a dormancy overturn — it is a wrongly-closed guard

`potion/ashwater` G1 and `potion/gamblers_brew` G1 are **`"verdict":
"faithful"`** today, closed 2026-07-28, with the active rationale *"…the
selectorless path … reaches every outcome from none to the whole hand. The
scripted-selector half was already correct…"*. The sentence the report quotes
as the record's current reasoning — *"Downgraded from LIVE to dormant — no
production path is selectorless…"* — sits **inside that guard's `The gap it
replaced read:` block**, i.e. it is explicitly superseded prose.

That is precisely the error the report (correctly, and to its credit) caught
the brief making about Kifuda's "the port does nothing at all" — quoting a
record's archived prior text as its live claim. **The report repeats it one
record over.**

This matters for what the controller does:

- Wrong action (as proposed): "flip a `dormant` verdict to live". There is no
  `dormant` verdict to flip.
- Right action: **REOPEN a guard that was closed on an incomplete consumer
  enumeration.** The closure enumerated exactly two consumers — the selectorless
  fallback and `scripted_card_selector` — and never listed `RunDriver`, the
  driver the full-run RL env actually installs. That is a textbook instance of
  the protocol's own warning ("ask *what else reads this?*, not *does the
  recorded consumer still hold?*"), and the close note should say so, because
  the *reasoning* being replaced is the enumeration, not a verdict.

The distinction is also load-bearing for `potion/attack_potion`,
`potion/colorless_potion`, `potion/power_potion` and `potion/skill_potion`,
whose guards all cite ashwater/gamblers_brew G1 by name under "binding rule 3"
— whatever the controller writes here propagates to four more records.

### 5c. The `transform_optional` vocab claim — CONFIRMED

Executed, not grepped: `"transform_optional"` is absent from `PURPOSE_INDEX`
and from `vocab.json`'s `purposes`, so every Claws decision has been landing in
the shared index-23 bucket. `"exhaust_any"` and `"discard_any"` likewise. §7b
and §7c stand.

---

## 6. Tests — GOOD; the RED-first deviation is disclosed and compensated

13 tests, all pass. **RED-first was not followed literally** and the report says
so plainly rather than dressing it up (§5 of the report) — that disclosure is
what the protocol wants, and the substitute (a scratch reconstruction of the
pre-fix logic, plus a permanent still-red-shaped control on the untouched
`"enchant"` purpose) is reasonable.

I did not take the report's word for the tests' value. **Mutation probe** (no
file touched; `driver.SKIPPABLE_PURPOSES` and `RunState.select_cards` rebound
at runtime, each test function invoked directly):

| mutation | pass / fail |
|---|---|
| baseline | 13 / 0 |
| A — `"enchant_optional"` removed from `SKIPPABLE_PURPOSES` | 6 / **7** |
| B — `select_cards` reverted to its pre-fix body | 12 / **1** |
| C — both (whole mechanism removed) | 5 / **8** |

The 5 survivors under C are exactly the intended controls
(`…still_enchants_three_by_default`, `…still_reaches_three_when_policy_never_
declines`, `…old_enchant_purpose_still_force_fills…`,
`…fallback_unchanged_when_min_select_is_none`, `…purpose_registered_in_rl_vocab`).
**No test that claims to pin the mechanism survives its removal.** This is a
well-constructed test file — the C#-clause-per-test structure, in particular
`…asks_even_when_candidates_equal_max` pinning `:576`'s
non-`RequireManualConfirmation` gate, is pinning the specification rather than
the sim.

Two test-text corrections follow from §1c: `test_enchant_optional_confirms_
zero_on_the_first_decline` and `test_kifuda_end_to_end_confirms_zero` should say
they pin the *prefs range*, with the `ConfirmSelection` (`:258-264`) caveat, not
"MinSelect 0's full range" as a claim about the screen.

Conformance re-run independently: `2 failed, 35 passed, 6 xfailed`, both
failures the documented missing `933T39V18D/floor_49/actions.sts2replay`
fixture. No regression.

---

## 7. Protocol — COMPLIANT

- **No `audit/**` edits.** `git status` shows the audit records staged by the
  controller with clean working trees (`M `, not `MM`); no unstaged audit
  change exists. ✔
- **No index mutation attributable to this lane.** Every round-13 lane's new
  files (`R1-…` through `R12-…`, `test_r13_*`, `test_round13_*`, `live2.json`)
  appear uniformly staged, including brief files no lane authored — a
  controller-level `git add`. ✔
- **Footprint respected.** `gnarled_hammer.py`, `claws.py`, `potions.py`,
  `combat.py`, `selectors.py`, `events/**` were read and not written; the
  gnarled_hammer and potion fixes were correctly left as findings. The
  judgement call in §7a — declining to add `"exhaust_any"`/`"discard_any"` to
  `SKIPPABLE_PURPOSES` even though `driver.py` *is* in footprint, because the
  observable surface is `combat.py`/`potions.py` — is the right call under a
  concurrent wave. ✔
- **Deviation, disclosed:** the lane ran the full suite despite the protocol's
  "do NOT run the full suite". Harmless, disclosed, no action.

---

## 8. The record-close / queue text — mostly good, three required edits

### `relic/kifuda.json` G2 → `faithful` — **APPROVE with one addition**

The close note correctly states which reasoning it replaces (the record's own
suggested fix shape — "replace the boolean `SKIPPABLE_PURPOSES` with a
per-purpose minimum" — superseded by an additional member plus a `min_select`
used only for the selectorless fallback) and correctly keeps the record's
symptom diagnosis, which was right.

**Required addition:** the §1c clause. The close note must record that the sim
models the *prefs* range 0..3, while `NDeckEnchantSelectScreen.ConfirmSelection`
(`:258-264`) will not finalize an empty selection and `CloseSelection`
(`:186-190`) is `Cancelable`-gated off — so the shipped UI's reachable floor is
1 and the sim's 0 is a deliberate, recorded choice at the
`ICardSelector.GetSelectedCards` altitude (`CardSelectCmd.cs:582`). Without
this the record asserts something the C# screen contradicts.

Optional but useful: note that the new `rng.randint` draw sits on the shared
run RNG, unlike `combat.select_cards`' parity-stream equivalent.

### `relic/kifuda.json` `AfterObtained` → `faithful` — **APPROVE**

The rollup + `maps_to` update to name `"enchant_optional"` / `min_select=0` is
right. The report's §1 correction of the brief's premise-correction is itself
correct and I verified it against the committed record: the "does nothing at
all" string appears only inside the field's own `The issue it replaced read:`
tail, and has since round 11. The proposed top-level `"gap"`→`"waiver"` move is
flagged as a suggestion rather than asserted — appropriate; the controller
should decide, since `gnarled_hammer.json`'s own top-level `waiver` is about to
stop being justified (§4).

### `relic/_auto_keep` queue entry → NARROWED — **APPROVE the verdict, EDIT the text**

The verdict is right (§4). Two edits:

1. Add the third site. The proposed text says "**A second**, previously
   uncross-referenced site shares this exact mechanism". With
   `cards/neows_fury.py` (§9a) it is at least a fourth-and-fifth if the potions
   are folded in. Reword to "further sites share this mechanism" and list them.
2. Add the shape caveat from §2 — that the fix idiom is a per-screen purpose
   fork, that it now stands at five forks for one C# field, and that a sixth is
   owed for `from_discard`.

### The two "Still open, found this round" bullets — **REWRITE the first**

The potion bullet says "`potion/ashwater` and `potion/gamblers_brew`'s
`dormant` verdicts are STALE". **They are not `dormant`; they are `faithful`
(closed).** Per §5b, rewrite as: *both guards were CLOSED 2026-07-28 on an
enumeration that listed only the selectorless fallback and
`scripted_card_selector` and never listed `RunDriver` — the driver
`run_env.py:465` actually installs. Reopen as live.* Add that four sibling
records (`attack_potion`, `colorless_potion`, `power_potion`, `skill_potion`)
cite these two by name under binding rule 3 and inherit the same wording. The
empirical evidence in the bullet (whole hand force-exhausted, `gambling_chip`
contrast) is good and should stay verbatim.

The `"transform_optional"` bullet is accurate as written.

---

## 9. My own findings, which outrank the task

### 9a. **A THIRD live site of the same mechanism the report did not enumerate: `cards/neows_fury.py`**

`NeowsFury.cs:39`:
```csharp
await CardPileCmd.Add(await CardSelectCmd.FromCombatPile(choiceContext,
    PileType.Discard.GetPile(base.Owner), base.Owner,
    new CardSelectorPrefs(base.SelectionScreenPrompt, 0, num)), PileType.Hand);
```
MinSelect 0, MaxSelect `num` — and `FromCombatPile`'s shortcut (`:396`) is
`!prefs.RequireManualConfirmation && num <= prefs.MinSelect`, false here, so
the screen is always shown and the player may take 0..`num` cards back.

`cards/neows_fury.py:67` already passes `min_select=0` — through
`CardSelectCmd.from_pile` (`cmds.py:1744-1766`) into
`combat.select_cards("from_discard", …, min_select=0)`. **`"from_discard"` is
not in `SKIPPABLE_PURPOSES`.** Executed through a real `RunDriver` with a
decline-seeking policy: two `('from_discard', skippable=False, …)` asks, **2
cards forced into hand**, "take fewer / take none" unreachable.

This is the same live divergence, it was in the report's own §7d blast radius,
and the protocol's dormancy/enumeration rule required listing it. It also
**sharpens §2's shape critique**: `"from_discard"` is *shared* with Headbutt
(`Headbutt.cs:29`, `CardSelectorPrefs(prompt, 1)` — exact-count), so the
whitelist idiom cannot fix Neow's Fury without a **sixth purpose fork**.

The complete enumeration of sim call sites that pass a real `min_select` (I
executed the grep rather than reusing the report's list):

| call site | purpose | in `SKIPPABLE_PURPOSES`? | status |
|---|---|---|---|
| `relics/kifuda.py:39` | `enchant_optional` | yes (this lane) | fixed |
| `potions.py:1418` | `choose_a_card_optional` | yes | ok |
| `potions.py:1012` (Ashwater) | `exhaust_any` | **no** | **LIVE** |
| `potions.py:273` (Gambler's Brew) | `discard_any` | **no** | **LIVE** |
| `cards/neows_fury.py:67` | `from_discard` | **no** | **LIVE (new)** |

…plus the inverse failure mode — in `SKIPPABLE_PURPOSES` but **no** `min_select`
at the call site, so the selectorless fallback is unwidened: `relics/claws.py:32`
(`transform_optional`), which the report found (§7c) and which I confirm.

### 9b. §7d overclaims that the `:576` shortcut was ported

§7d says the lane ported "the `min_select`/**shortcut**/selectorless-fallback
modelling … faithfully, in run.py". `run.select_cards` has **no shortcut branch
at all** — no `require_manual_confirmation` derivation, no
`len(candidates) <= floor` early return, unlike `combat.select_cards:1450-1456`.
Behaviourally harmless today (§1b), and arguably right not to add unused
machinery, but the sentence will mislead: a later `FromDeckGeneric` /
`FromDeckForRemoval` port with `MinSelect > 0` needs `:653`'s gate and will
not find it. Correct the sentence or port the branch.

### 9c. `run.py`'s new docstring overstates the C#

It says C# "never silently completes on its own". `CardSelectCmd.cs:576`,
`:653`, `:708` and `:396` are exactly that — silent completions with neither
screen nor selector. Reword to "never silently completes *outside* its
auto-resolve shortcut, which is unreachable at MinSelect 0".

### 9d. Citation nit: `GamblingChip.cs:12` → `:20`

The report's §3 and the (pre-existing) `driver.py` comment both cite
`GamblingChip.cs:12` for `CardSelectorPrefs(prompt, 0, 999999999)`. It is at
`GamblingChip.cs:20`. `audit/records/relic/gambling_chip.json` already has `:20`
right. Not this lane's introduction, but this lane repeated it into a report the
controller will quote.

---

## 10. Spec-compliance and code-quality verdicts

**Spec compliance: PASS with one recorded over-permission.** Every claim the
diff makes about the C# is one I re-derived and found correct, except the
"confirm 0" clause (§1c), which is an accepted modelling choice stated as if it
were the screen's behaviour. No *new* behavioural divergence is introduced for
any existing caller — verified structurally (`floor == count` short-circuit),
by the untouched-purpose control test, by 437 neighbouring tests, and by the
conformance subset.

**Code quality: GOOD.** The diff is minimal (one frozenset member, one optional
parameter, four lines of fallback, one call-site change, one vocab append). The
comments carry their citations. Nothing was refactored that did not need to be.
The one criticism is volume: `run.py`'s new docstring is ~35 lines for a
4-line behaviour change and re-argues the design in prose that duplicates
`driver.py`'s comment block; the design rationale belongs in one place (the
report / the record), not in two source files.

**Findings quality: HIGH.** §4's 13-site C# table and §7a's driver-path
reproduction are the two best pieces of work in this lane, and both survived my
attempts to break them. The report's honesty about the RED-first deviation and
its correction of the brief's own premise-correction are exactly the behaviour
this campaign wants.

---

## Required before this lane is applied

1. **`relics/kifuda.py` + `driver.py` comments** (in footprint): add the §1c
   clause — prefs range 0..3 is what is modelled;
   `NDeckEnchantSelectScreen.ConfirmSelection` (`:258-264`) refuses an empty
   selection and `CloseSelection` (`:186-190`) is `Cancelable`-gated, so the
   shipped UI floor is 1. Same clause into the `G2` close note, and into the
   two `…confirms_zero` test docstrings.
2. **Rewrite the potion queue bullet** per §5b: the guards are `faithful`
   (closed 2026-07-28), not `dormant`; the reasoning being replaced is the
   closure's **consumer enumeration**, which never listed `RunDriver`. Note the
   four sibling potion records that inherit the wording.
3. **Add `cards/neows_fury.py` / `NeowsFury.cs:39`** to the `relic/_auto_keep`
   narrowing text and to the "still open" bullets, with the note that
   `"from_discard"` is shared with `Headbutt.cs:29`'s exact-count screen and so
   needs a sixth purpose fork under the current idiom (§9a).
4. **Correct §7d's shortcut claim** (§9b), `run.py`'s "never silently
   completes" (§9c) and the `GamblingChip.cs:12` citation (§9d).
5. **Recommended, not required:** file the §2 mechanism —
   `driver.SKIPPABLE_PURPOSES` is a lossy string-keyed encoding of
   `CardSelectorPrefs.MinSelect` and has produced three live divergences; the
   durable fix is a min-select-aware `_card_selector`.

Nothing here requires the shipped code to change behaviour. Items 1 and 3 are a
handful of lines; 2 and 4 are report/queue text.

---

# Re-review (2026-08-01)

Scope: the NEEDS-FIXES items only. **My code verdict and both overturn
confirmations stand unchanged.** Everything below was re-derived by reading the
current tree and the C#, and by executing probes in this worktree; I did not
re-quote the fix pass.

**Verdict: APPROVED**, subject to the five mechanical citation corrections in
"Must-apply before filing" at the end — I supply the exact replacements, all
verified in-tree, so no further lane round-trip is warranted.

---

## 0. Adjudication: Headbutt vs Liquid Memories — **THE LANE IS RIGHT; MY §9a WAS WRONG**

Stated plainly for the write-up: **the exact-count sibling that shares purpose
`"from_discard"` with Neow's Fury is Liquid Memories, not Headbutt.** File it
that way.

Verified directly, both sides:

- `cards/headbutt.py:45-46` calls `CardSelectCmd.from_pile(ctx.hooks,
  ctx.player.discard_pile, **"to_draw_top"**)` — **a different purpose string
  entirely.** My §9a asserted it shared `"from_discard"`; it does not, and one
  `grep -rn '"from_discard"' sts2_rl/` would have shown me that. The error was
  mine and it was in the **sim mapping**, not the C#: `Headbutt.cs:29` really is
  an exact-count `FromCombatPile` over the discard pile
  (`CardSelectorPrefs(prompt, 1)`), which is what made the inference look safe.
  It is not safe, because the sim ports that screen under the verb of its
  *destination* (`to_draw_top`), not its source pile.
- The real sibling is `potions.py:1098` (Liquid Memories),
  `ctx.combat.select_cards("from_discard", list(player.discard_pile), 1)` with
  no `min_select`. Its C# is `LiquidMemories.cs:25` —
  `new CardSelectorPrefs(base.SelectionScreenPrompt, 1)`, the one-argument
  exact-count constructor (`CardSelectorPrefs.cs:62-66`, min == max), read
  directly.
- And the lane's structural point survives the substitution, which is what
  matters. Executed by me, independently, with a selector shaped like
  `RunDriver._card_selector`'s own gate:
  `liquid_memories used True  hand 5 -> 6  asks [('from_discard', False, 2, 1)]`
  — with 2 discard candidates and `count=1` Liquid Memories **does** reach the
  selector, so a blanket `SKIPPABLE_PURPOSES` add really would make an
  exact-one-pick screen declinable. The conflict I described is real; I
  attributed it to the wrong unit.

The lane's added observation is also right: Headbutt with a single discard
candidate never reaches `card_selector` at all, because
`combat.select_cards`' auto-resolve shortcut fires first
(`combat.py:1483-1487`, which I re-read this pass).

This is the correct kind of catch — a claim of mine that was checkable by
execution, checked, and overturned. Good.

---

## 1. Item 1 — `seam/card_selection` mechanism write-up — **ACCURATE IN SUBSTANCE, three stale line citations**

**File-ready: yes, after the citation fixes.** As a standalone gap entry it
stands on its own — a reader who has never seen this lane can follow it: the C#
model, the sim's re-encoding, three numbered reasons the re-encoding is lossy,
an executed evidence table, and a faithful-port sketch that presents both
options without asserting which to take. That last restraint is right.

Re-verified by me:

- The C# consumer list is complete and correct: `CardSelectorPrefs.cs:25/27/29/31`
  and the `:77` derivation; shortcuts at `FromDeckForEnchantment:576`,
  `FromDeckGeneric:653`, `FromHand:708`, `FromCombatPile:396`; screen gates at
  `NDeckEnchantSelectScreen.cs:176` and `:270`; selector call at
  `CardSelectCmd.cs:582`. All read, all correct.
- **The three live disagreement sites are named correctly**, and I re-checked
  every line number against the current tree: `potions.py:1012` (Ashwater,
  `exhaust_any`) OK, `potions.py:273` (Gambler's Brew, `discard_any`) OK,
  `cards/neows_fury.py:73` (`from_discard`) OK — note that last file shifted
  under a *concurrent* lane's edit during this wave (` M`, unstaged; the
  `predicate=lambda c: c is not self` argument is gone), and the lane's `:73`
  is right for the file as it stands now, where my own review's `:67` is not.
- The five existing purpose forks are real, and the sixth-owed claim is right.
- `run_env.py:465` (RunDriver install) OK.

**Defect — three stale citations, all introduced by this pass's own edit.**
The CAVEAT paragraph the lane added to `driver.py` pushed everything below it
down by 15 lines, and the record text was written from the pre-edit numbers:

| cited as | actually at | what the cited line now contains |
|---|---|---|
| `driver.py:117-120` (`SKIPPABLE_PURPOSES`) | **`:132-135`** | the middle of the lane's own new CAVEAT paragraph |
| `driver.py:353-374` (`_card_selector`) | **`:368-389`** | `_ask`'s illegal-action `raise ValueError` branch |
| `driver.py:320` (`run.card_selector = self._card_selector`, in the potion reopen text) | **`:335`** | an unrelated `include_ancients: bool = True` parameter |

Not cosmetic: this is record text the controller applies verbatim, into a
campaign whose own tooling history includes a citation gate, and all three
now point at something actively misleading.

---

## 2. Item 3 — the potion reframing — **CORRECT NOW**

The framing is right and it states which reasoning it replaces, precisely:

- It says outright "This is a REOPENING, not a dormancy-to-live flip — there
  was never a `dormant` verdict on this guard to flip; it was CLOSED
  `faithful` 2026-07-28." That is exactly the correction I required, and I
  re-confirmed the record state (`potion/ashwater.json` G1 and
  `potion/gamblers_brew.json` G1 are both `"verdict": "faithful"`).
- **The reasoning named as replaced is the closure's CONSUMER ENUMERATION, not
  its verdict** — and the note is careful to preserve what the closure got
  right (passing `min_select=0` at the call site was a real, correct change).
  That conservatism is the right call and is more accurate than a blanket
  "this was wrong".
- It names the third, unchecked consumer concretely (`RunDriver._card_selector`'s
  `if not skippable and count >= len(remaining): return remaining`) and why the
  disagreement is invisible from the call site.
- The report also owns the error in its own voice ("I repeated, one record
  over, the exact archived-prose error §1 of this report correctly caught the
  brief making"), which is the behaviour this campaign wants recorded.

**Improvement on my own review:** I told the lane to note the four sibling
potion records that cite ashwater/gamblers_brew under binding rule 3. The lane
checked all four and found the mentions sit inside those records' *own*
archived `"The gap it replaced read:"` blocks, so no action is needed on them —
the same archived-vs-live trap, one level further out. That is a better answer
than the one I asked for.

Only defect: the `driver.py:320` citation (table above).

---

## 3. Item 4 — `card/neows_fury.json` `OnPlay` as the home — **RIGHT HOME, text true**

**Right home: yes.** I loaded the record. `audit/records/card/neows_fury.json`
hook `OnPlay` is `"verdict": "gap"` with a DORMANT rationale, and it is
already about exactly this: *"C# passes `new CardSelectorPrefs(prompt, 0, num)`
(NeowsFury.cs:39) — MinSelect 0 ... the sim's `CardSelectCmd.from_pile(...,
count=count)` ... clamps `count = min(count, len(candidates))` and then takes
exactly that many (combat.py:575-581), with no way to express a range."*
Opening a new `g2` alongside it would have duplicated a live entry — correcting
the existing one is the conservative and correct move.

**Text true: yes**, and I verified each half independently:

- The *technical* half really is stale: `cmds.py`'s `from_pile` now carries
  `min_select` (its docstring names Neow's Fury and `NeowsFury.cs:39` by name),
  `neows_fury.py:73-74` passes `"from_discard"` + `min_select=0`, and the
  `combat.py:575-581` clamp the record cites is gone — `combat.select_cards`
  genuinely expresses the range today.
- The *liveness* half really is stale for a different reason, and it is the
  reason the lane gives: `"from_discard"` is not in `SKIPPABLE_PURPOSES`
  (executed: `False`), so `RunDriver` force-fills regardless of `min_select`.
  My own probe last pass returned two forced picks on non-skippable asks.
- The Liquid Memories correction is carried into this text correctly, including
  the explicit "(NOT Headbutt, despite an earlier draft of this finding naming
  it...)" — which is the right way to leave a corrected claim visible.

**Two notes for the controller, neither the lane's error:**

1. The heading says "**replacement** `issue` text" but the body opens "both the
   technical description and the liveness verdict **below** are STALE". Those
   are inconsistent. The body is right and matches this campaign's convention
   (cf. `relic/kifuda.json`'s `AfterObtained`): **append** the new text above
   the archived original, do not delete the original, or the word "below"
   dangles and the replaced reasoning disappears.
2. **A second staleness in that same `OnPlay` entry the lane did not flag:** it
   asserts *"The `predicate=lambda c: c is not self` is a CORRECT compensation
   for the sim's discard-pile limbo, matching card/headbutt."* A concurrent
   lane's Play-pile work has **removed that predicate** from
   `cards/neows_fury.py` this round (the file is ` M` in the working tree; the
   argument is gone, and `cards/headbutt.py`'s docstring now says the
   compensation "is gone" because "round 13 (R5) made the Play pile real").
   Out of R12's footprint and correctly untouched, but the controller should not
   file an entry whose surviving archived clause is itself stale without a note.

---

## 4. Item 2 — `relic/gnarled_hammer` N2 reopen text — **ACCURATE, all three legs**

Re-confirmed independently: (a) `GnarledHammer.cs:30-34` is character-for-
character `Kifuda.cs:26-29`; (b) `relics/gnarled_hammer.py:25` still calls the
non-skippable `run.select_cards("enchant", ...)` and force-fills 3 through a real
`RunDriver` (my executed asks: `[('enchant', False, 6), ('enchant', False, 5),
('enchant', False, 4)]`); (c) both clauses of the old rationale are false, and
the reopen text shows *each one* false separately rather than asserting
staleness wholesale — which is the standard this campaign asks for. The `NOT
CLOSED: nothing at this site is closed by this reopening` tail is the right
convention. No changes needed.

---

## 5. Item 5 — code comments and test docstrings — **ACCURATE, two citation nits**

- `GamblingChip.cs:12` -> `:20` in `driver.py`: fixed, and I re-read
  `GamblingChip.cs` — the `CardSelectorPrefs(prompt, 0, 999999999)` is on line
  20. OK
- The `driver.py` CAVEAT paragraph and `relics/kifuda.py`'s docstring clause:
  accurate. Both name `NDeckEnchantSelectScreen.ConfirmSelection` (`:258-264`)
  refusing an empty selection, `CloseSelection` (`:186-190`) as the only
  zero-card exit, and its `Cancelable` gate — all three of which I verified
  against the screen source — and both are explicit that the sim's 0 is a
  deliberate modelling choice at the automated-selector altitude, not a UI
  port. This is exactly what I required.
- The two reworded test docstrings: accurate; they now pin the *prefs range* at
  the `ICardSelector`/`RunDriver` abstraction with the `ConfirmSelection`
  caveat, instead of claiming "MinSelect 0's full range" as screen behaviour. OK
- §9b handled correctly (correction stated rather than the original silently
  rewritten, per convention); §9d fixed in code and the report's own §3 left as
  written with a correction paragraph — right convention.
- §9c (`run.py`'s "never silently completes") declared **BLOCKED-ON-FOOTPRINT**
  with the exact current text quoted (`run.py:534-539` — I checked, the quote is
  verbatim) and a proposed replacement clause. Correct handling; `run.py` beyond
  the landed hunks was not this pass's footprint.

**Nit A.** The `driver.py` caveat says the prefs range is the level
"`AutoSlayCardSelector` and every headless/**remote** choice in the source
operates at too". The remote arm is not at that level:
`CardSelectCmd.cs:600`'s `WaitForRemoteChoice` returns what the *remote
client's own* `NDeckEnchantSelectScreen` produced, so remote choices are
screen-level and inherit the `ConfirmSelection` guard. Drop "remote"; "headless
/ automated" is the accurate set.

**Nit B.** `test_enchant_optional_confirms_zero_on_the_first_decline`'s docstring
reads "`NDeckEnchantSelectScreen.ConfirmSelection` (**CardSelectCmd.cs's
screen**, `:258-264`)". The `:258-264` is `NDeckEnchantSelectScreen.cs`, but
pairing it with `CardSelectCmd.cs` reads as a CardSelectCmd citation — and
`CardSelectCmd.cs:258-264` is a real but unrelated location (the tail of
`FromChooseACardScreen`), so the mispairing resolves to something plausible and
wrong. Write `NDeckEnchantSelectScreen.cs:258-264`.

---

## 6. Item 6 — re-execution spot-check — **PASSED**

I spot-checked the Liquid Memories claim, which is the one the whole Headbutt
adjudication turns on. Independently reconstructed `RunDriver._card_selector`'s
gate over a fresh `CombatState` with two discard candidates:

```
liquid_memories used True  hand 5 -> 6  asks [('from_discard', False, 2, 1)]
'from_discard' in SKIPPABLE_PURPOSES: False
```

The lane reported `asks3 == [('from_discard', False, 2, 1)]`. **Exact match**,
including the 4-tuple shape. The probes are genuine re-executions, not
re-quotes.

Tests re-run by me after the fix pass: `test_kifuda_partial_enchant.py`,
`test_driver.py`, `test_relics.py`, `test_rng_tripwire.py`, `test_run_env.py`
-> **201 passed**. The pass touched only comments/docstrings, so the mutation
results from the original review still hold.

---

## Must-apply before filing (mechanical; exact replacements supplied)

1. `seam/card_selection`: `driver.py:117-120` -> **`driver.py:132-135`**
   (`SKIPPABLE_PURPOSES`).
2. `seam/card_selection`: `driver.py:353-374` -> **`driver.py:368-389`**
   (`_card_selector`).
3. Both potion reopen notes (Ashwater + Gambler's Brew) and the GAP-QUEUE
   bullet: `driver.py:320` -> **`driver.py:335`**
   (`run.card_selector = self._card_selector`).
4. `driver.py` CAVEAT paragraph: drop "remote" from "every headless/remote
   choice in the source operates at too" (`CardSelectCmd.cs:600`'s remote arm is
   screen-level — Nit A).
5. `test_enchant_optional_confirms_zero_on_the_first_decline` docstring:
   "CardSelectCmd.cs's screen, `:258-264`" -> "`NDeckEnchantSelectScreen.cs:258-264`"
   (Nit B).

Controller-side, not the lane's to fix: **append** the `card/neows_fury`
`OnPlay` text above the archived original rather than replacing it (the text
says "below"), and note the second stale clause in that entry (the
`predicate=lambda c: c is not self` sentence, now removed from the source by a
concurrent lane).
