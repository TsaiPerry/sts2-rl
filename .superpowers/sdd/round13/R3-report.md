# R3 report — batch `power-1` (12 unlabelled entries, 10 records)

Footprint: `sts2_rl/powers.py` + `test/test_r13_*` + one existing test file
(`test/test_underdocks_hive_events.py`, edited because a pre-existing test in
it encoded a divergence this batch's own fix corrects — see finding F1).
`hooks.py`, `combat.py`, `cmds.py`, `player.py` were read but never written.

Mix: **4 stale-already-fixed / 5 fixed / 2 dormant-enumerated / 1
blocked-on-footprint(-with-a-narrowed-sibling)**. Two entries (`corruption`,
`nostalgia/g8`) share one open residual that genuinely needs `hooks.py` +
`combat.py`.

> **AMENDED 2026-08-01** per `R3-review.md` (verdict NEEDS-FIXES). A live
> defect in the shipped Rebound fix (a Rebound stack was spent on an
> Exhaust-keyword card play where C# abstains) is now fixed, and the
> Corruption/Nostalgia and `vital_spark` entries' reasoning is corrected —
> the report's original claims about C# were wrong in both cases even though
> the verdicts (LIVE, DORMANT respectively) stand. See entries #2, #4, #6,
> #7, #8, #12 (each amended in place, struck text preserved not deleted) and
> the **"Fix pass (2026-08-01)"** section at the end for the full RED/GREEN
> evidence and test counts. The `power/rebound` record-overturn (F1 below)
> is unaffected and stands as originally reported.

## Environment note (not my bug)

Mid-session, a concurrent agent's in-progress rewrite of `hooks.py` (a
dispatch-order derivation rework, docstrings say "round 13 measurement")
intermittently broke unrelated tests in this shared worktree, including a
run where even `TestStrength` failed on
`AttributeError: 'PlayerCombatState' object has no attribute
'is_active_for_hooks'` — the attribute exists in `player.py:94` and the
failure vanished on the next run, i.e. it was a live read of a file another
agent was mid-write on. **As of my final verification run**, three tests
remain consistently red and are **not caused by this batch**:
`test_powers.py::TestPowerInstanceType::test_instanced_power_applied_twice_yields_two_independently_ticking_instances`,
`::test_rolling_boulder_two_applications_deal_independent_growing_damage`,
`::test_toric_toughness_two_applications_track_independent_block_and_duration`
— all about `PowerInstanceType` dispatch (`hooks.py`/`cmds.py`), a mechanism
I never touched. `git diff sts2_rl/powers.py` shows exactly 4 hunks, all
inside `DarkEmbracePower`, `ReboundPower` and `RetainHandPower` — nowhere
near instancing. Confirmed by diffing before reporting, not assumed.

---

## Per-entry verdicts

### 1. `power/artifact/AfterModifyingPowerAmountReceived` — STALE-ALREADY-FIXED

Record still says the stack-consumption event is hand-inlined
(`cmds.py:301-305`, decrementing `.amount` and calling `_expire()` directly,
bypassing `ShouldRemoveDueToAmount`). **That is no longer the code.** Round
12's Task 18 (per the R3 brief's own hint) rebuilt this as a real listener
pair: `ArtifactPower.after_modify_power_amount_received` (`sts2_rl/powers.py`,
class `ArtifactPower`) now calls `self._tick()`, and `Power._tick`
(`powers.py:144-151`) routes through `PowerCmd.modify_amount`
(`cmds.py:993-1032`), which applies the `IsEnding` guard AND the
`power.amount <= 0 -> power._expire()` check — i.e. the full ModifyAmount
pipeline, exactly `PowerCmd.Decrement(this)` (ArtifactPower.cs:38-41). Verified
by reading the current `powers.py`/`cmds.py` (not memory/prose, per protocol
rule "verify against the actual committed tree"). Existing coverage:
`test/test_powers.py::TestArtifact::test_blocks_one_debuff_per_stack` already
exercises decrement-to-expiry through this exact path and passes.

No code change. **Close note:** record predates round 12 Task 18's
`AfterModifyingPowerAmount*` machinery (power_cmd/G3+G4); re-verified against
today's `powers.py`/`cmds.py` and the sim now matches ArtifactPower.cs:38-41
exactly. Verdict: `faithful`.

### 2. `power/corruption/ModifyCardPlayResultPileTypeAndPosition` — LIVE, BLOCKED-ON-FOOTPRINT

> **REVISED 2026-08-01 per R3-review.md §1.2/§5 RF1.** The original text
> below claimed order-independence (Corruption always winning over
> Nostalgia) *was itself* the divergence. **That claim was wrong and has
> been struck; the corrected analysis follows it.** Re-derived directly
> from the two C# listeners rather than trusting the previous version of
> this entry:
>
> - `CorruptionPower.cs:27-38` returns `(PileType.Exhaust, position)` for
>   any owner-owned Skill with **no `pileType` guard at all**.
> - `NostalgiaPower.cs:39-42` and `ReboundPower.cs:25-28` both bail with
>   `if (pileType != PileType.Discard) return (pileType, position);`.
>
> So for EITHER application order in C#: Corruption-first sets Exhaust and
> Nostalgia/Rebound then see `!= Discard` and abstain; Nostalgia/
> Rebound-first sets Draw-top/Discard and Corruption then overwrites it
> unconditionally. **Both orders end at Exhaust.** C# is *also*
> order-independent here, and Corruption *also* always wins — the sim's
> executed result (`exhausted=True` both orders, reproduced below) already
> **matches the game on the final pile**. Order-independence was never the
> gap; the entry stays LIVE, but on three different, narrower residues (see
> revised body below). Struck reasoning left visible, not deleted, per the
> protocol's close-note contract ("state which reasoning you replaced").

~~Confirmed still exactly as described, and confirmed **LIVE** by execution
(both orders tried):~~

```
nostalgia_first exhausted=True draw_top=False
corruption_first exhausted=True draw_top=False
```

`CorruptionPower.on_card_played` (`powers.py`, class `CorruptionPower`) still
hand-removes the card from `discard_pile` into `exhaust_pile` from inside the
play loop (`combat.py`'s `_resolve_card_play`, dispatched at the
`on_card_played` call site inside `for play_index in range(play_count)`),
which runs BEFORE the generic post-loop `modify_card_play_result_pile`-driven
move (`if card in player.discard_pile and result_pile == "draw_top"`, after
the loop). ~~**Corruption therefore always wins over Nostalgia regardless of
which power was applied first** — the opposite of C#'s single
`ModifyCardPlayResultPileTypeAndPosition` chain with last-writer-wins
(Hook.cs:1391-1405, `CardModel.cs:1890`), where the winner would depend on
listener order. Order-independence is itself the divergence: a faithful port
would let application order decide (hook_dispatch/G2's territory, correctly
not re-argued here), not hard-code one power as always dominant.~~ **CORRECTED:
C# is also order-independent and Corruption also always wins there (see box
above) — the sim's final pile already matches. The real, LIVE residues are:**

1. **Rebound's stack is spent unconditionally under Corruption, where C#
   spends it order-dependently.** Executed both orders
   (`corruption+rebound`, Corruption-first and Rebound-first): the sim's
   Rebound power is gone (stack consumed) in BOTH orders. In C#, the tick
   comes from `AfterModifyingCardPlayResultPileOrPosition`, fired only over
   the listeners whose OWN chain call changed the value
   (`Hook.cs:1391-1406`) — so if Corruption is ordered first, Rebound's own
   chain call sees `pileType == Exhaust`, abstains per `ReboundPower.cs:25-28`,
   is never added to the `modifiers` list, and **keeps its stack**; only if
   Rebound runs first (redirecting to Discard→Draw-top) and Corruption then
   overwrites it does Rebound get credited with having changed the value on
   its own call and tick. The sim's `CorruptionPower.on_card_played`
   short-circuits outside the chain entirely, so this order-dependence is
   invisible to it — Rebound's stack is consumed every time, order or no.
2. **Exhaust timing.** `CorruptionPower.on_card_played` (`powers.py`) runs
   inside the play-count loop (`combat.py`'s `_resolve_card_play`, inside
   `for play_index in range(play_count)`), where C# performs the exhaust
   move once, AFTER the whole loop (`CardModel.cs:1976-1990`, the
   `case PileType.Exhaust` arm at `:1984`). For a replayed Skill (e.g. a
   Throwing-Axe-doubled Burst, or any card with `base_replay_count > 0`),
   the sim's card sits in the exhaust pile for the remaining loop
   iterations where the game still holds it in `PileType.Play` limbo, and
   `on_card_exhausted`-reacting powers (Feel No Pain, Dark Embrace, Charon's
   Ashes) fire mid-loop in the sim instead of once after it in C#.
3. **Corruption never joins the chain**, so the `modifiers` notification set
   C#'s `AfterModifyingCardPlayResultPileOrPosition` would carry differs
   (today cosmetic-only — nothing in `sts2_rl/` implements that
   notification-list hook at all, `seam/power_cmd` G4 — but it is still an
   absence from the mechanism the sim is supposed to be modelling).

**Why this is still BLOCKED-ON-FOOTPRINT:** the shared
`hooks.modify_card_play_result_pile` chain (`hooks.py`) only accepts
`"discard"`/`"draw_top"` as return values — there is no `"exhaust"` value,
and even if Corruption returned one, `combat.py`'s post-loop resolution
(`_resolve_card_play`) only branches on `result_pile == "draw_top"`; nothing
consumes `"exhaust"`. A faithful fix needs: (a) `hooks.py` to let
`modify_card_play_result_pile` express an exhaust destination (mirroring
C#'s full `(PileType, CardPilePosition)` return, not a two-value string), and
(b) `combat.py`'s post-loop move to branch on it and fire
`on_card_exhausted` there instead of inside `CorruptionPower.on_card_played`.
Both files are explicitly outside this batch's footprint. What I would have
done (unchanged from the original proposal — the fix SHAPE was already
right, only the justification for it was wrong): extend
`modify_card_play_result_pile`'s return type to `(pile: str, position: str)`
with `pile` also accepting `"exhaust"`, move Corruption's decision onto that
hook (mirroring the Rebound fix below, `return "exhaust" if <skill guard>
else pile`), and add the exhaust branch to `combat.py`'s post-loop dispatch,
deleting `CorruptionPower.on_card_played` entirely. That one change closes
all three residues above at once: Rebound's chain call would then correctly
see `pileType == Exhaust` when Corruption runs first and abstain (residue 1),
the exhaust move would happen post-loop like every other exhaust (residue
2), and Corruption would be a real chain participant (residue 3).

No code change. **Queue annotation (stays `gap`, liveness LIVE — this
promotes it out of `unlabelled`):** Re-derived 2026-08-01 (R3-review.md
§1.2/RF1): the sim's final pile already matches C# in both application
orders (`CorruptionPower.cs:27-38` has no pileType guard;
`NostalgiaPower.cs:39-42`/`ReboundPower.cs:25-28` bail on non-Discard, so C#
is also order-independent and Corruption also always wins there) —
order-independence is NOT the gap. The entry stays LIVE on three narrower
residues instead: (1) Rebound's stack is spent unconditionally under
Corruption where C# spends it only when Rebound's own chain call is the one
that changed the pile (order-dependent); (2) the exhaust move happens inside
the play-count loop instead of once after it, so `on_card_exhausted`
listeners see wrong timing on a replayed card; (3) Corruption never
registers as a chain participant. Fix needs `hooks.py` (an `"exhaust"`
pile-destination value) and `combat.py` (the post-loop dispatch for it) —
both out of the power-tier footprint; `power/rebound`'s sibling entries in
this same batch show the pattern once that machinery exists. **Do not build
"let application order decide the winner" — it already doesn't, in either
engine.**

### 3. `power/dark_embrace/AfterCardExhausted` — FIXED

`DarkEmbracePower.on_card_exhausted` drew a hard-coded `1`
(`DrawCmd.draw(self.owner, 1)`) instead of `self.amount`
(DarkEmbracePower.cs:47 — `CardPileCmd.Draw(base.Amount, ...)`). Fixed: now
`DrawCmd.draw(self.owner, self.amount)`.

**Test:** `test/test_r13_power1.py::TestDarkEmbraceAmountAndEtherealDeferral::test_draws_amount_cards_per_exhaust_not_a_hardcoded_one` (RED before, GREEN after — `PowerCmd.apply(..., DarkEmbracePower, 3)` then one exhaust now draws 3, not 1).

**Close note:** the hard-coded `1` is fixed; `on_card_exhausted` now draws
`self.amount`, matching DarkEmbracePower.cs:47. Verdict: `faithful`.

### 4. `power/dark_embrace/AfterSideTurnEnd` — FIXED

C# defers an Ethereal-caused exhaust's draw to `AfterSideTurnEnd`
(DarkEmbracePower.cs:52-60), so the cards land AFTER the hand flush instead
of being flushed away by it (source comment DarkEmbracePower.cs:18-23 states
this is deliberate). The sim had no `AfterSideTurnEnd` implementation at all
and drew immediately for every exhaust including Ethereal-caused ones.

The brief's own guard note (dark_embrace.json's `causedByEthereal` guard) was
right that the blocking issue — no `caused_by_ethereal` parameter on the
sim's `on_card_exhausted` — is **already fixed** (closed 2026-07-30,
verified present at `hooks.py`'s `on_card_exhausted` dispatch and dispatched
`True` from `combat.py`'s two ethereal-exhaust call sites,
`_process_turn_end_cards`). What remained unbuilt was Dark Embrace's own use
of it.

Fixed: `DarkEmbracePower` now tracks `self._ethereal_count` (init in
`__init__`), increments it instead of drawing when
`caused_by_ethereal=True`, and implements `after_player_turn_end` (the sim's
existing player-side `AfterSideTurnEnd` slot — see `power/retain_hand` and
`power/rebound`'s own `after_player_turn_end` for the established pattern)
to draw `self.amount * self._ethereal_count` and reset the counter, matching
DarkEmbracePower.cs:52-60's shape exactly, at the correct slot (`combat.py`'s
`_end_turn_internal` fires `after_player_turn_end` AFTER
`_process_turn_end_cards` — where the ethereal exhausts happen — and AFTER
`discard_hand`'s flush, verified by reading that function).

**Tests:** `test/test_r13_power1.py::TestDarkEmbraceAmountAndEtherealDeferral`:
- `test_ethereal_exhaust_does_not_draw_immediately`
- `test_ethereal_exhaust_draw_is_deferred_to_after_player_turn_end`
- `test_ethereal_exhaust_draw_survives_the_hand_flush` — drives the REAL
  sequence (`_process_turn_end_cards()` -> `discard_hand(flush=...)` ->
  `after_player_turn_end(...)`), pinning the actual regression the C# source
  comment names (a card drawn before the flush gets flushed away).

~~All three RED before the fix, GREEN after.~~ **CORRECTED 2026-08-01 per
R3-review.md §1.4a:** only `test_ethereal_exhaust_does_not_draw_immediately`
and `test_ethereal_exhaust_draw_survives_the_hand_flush` were actually RED
against the reconstructed pre-fix class. `test_ethereal_exhaust_draw_is_deferred_to_after_player_turn_end`
**passed** pre-fix too: with `amount=1` and three ethereal exhausts, the old
(buggy) code drew `1` immediately three times and the new code draws
`1*3=3` once at turn end — the same net draw-pile delta, so that particular
assertion shape doesn't distinguish old from new behavior. It remains a
legitimate documentation test (it pins the deferred-batching arithmetic
against the correct call sequence) but it is not itself a pin and should not
have been reported as RED-before. No fidelity consequence — the other two
tests in the class do cover the actual regression — but the claim itself was
wrong and is corrected here rather than left standing.

**RF5 residual (R3-review.md §1.4, note 4b) — recorded, not fixed (footprint
does not require a code change; dormant today):** C# calls
`CardPileCmd.Draw(ctx, base.Amount * etherealCount, …)` **unconditionally**
whenever the owner is a still-a-participant creature, including with a
product of `0` (`DarkEmbracePower.cs:52-60`). `CardPileCmd.cs:804-813` fires
`Hook.ShouldDraw` (and, on a refusal, `Hook.AfterPreventingDraw`) **before**
the `drawsRequested == 0` early return. The sim's
`after_player_turn_end`'s `if … self._ethereal_count == 0: return` skips
that dispatch entirely when nothing was deferred this turn. Provably
unobservable on current content: the two `should_draw` implementers are
`NoDrawPower` (`powers.py:814`) and `relics/fiddle.py:32`, both pure
predicates with no side effect worth skipping, and
`grep -rn "def after_preventing_draw" sts2_rl/` finds zero
listeners (dispatcher exists at `hooks.py:1921`, one call site at
`player.py:568`, nobody implements the hook). DORMANT, but it should be a
named residual on the record rather than silently absent — a future
`should_draw`/`after_preventing_draw` listener would see this call site skip
it on a zero-count turn where C# still dispatches.

**Close note:** the `causedByEthereal` guard was already fixed (STALE note
already recorded on that guard); this hook's own absence is now fixed —
`DarkEmbracePower` implements the etherealCount deferral and
`after_player_turn_end`, matching DarkEmbracePower.cs:37-60. The
`self._ethereal_count == 0: return` early exit skips C#'s unconditional
`Hook.ShouldDraw`/`Hook.AfterPreventingDraw` dispatch on a zero-count turn
(RF5 above) — DORMANT today (zero `after_preventing_draw` listeners exist),
recorded as a named residual rather than left silent. Verdict: `faithful`
(with the RF5 residual tracked, not blocking closure).

### 5. `power/draw_cards_next_turn/AfterSideTurnStart` — STALE-ALREADY-FIXED

Record claims `PowerModel.AmountOnTurnStart` has **no sim counterpart**
("executed grep for `amount_on_turn_start` across sts2_rl/ returns
nothing"). **That grep now returns 6 hits.** The machinery exists in full:
`Creature.snapshot_powers_on_turn_start` (`sts2_rl/creatures.py:79-99`,
mirroring `Creature.BeforeTurnStart`, Creature.cs:673-679, setting
`power.amount_on_turn_start = power.amount` for every power), called from
`combat.py` for both the enemy pass and the player
(`self.player.snapshot_powers_on_turn_start()`). And
`DrawCardsNextTurnPower` itself (`powers.py`, class `DrawCardsNextTurnPower`)
already reads it on BOTH hooks the record's two entries are about:
`modify_hand_draw` guards on `getattr(self, "amount_on_turn_start", 0) == 0`
(DrawCardsNextTurnPower.cs:28) and `after_side_turn_start` — MY entry — guards
the `_expire()` on `getattr(self, "amount_on_turn_start", 0) != 0`
(DrawCardsNextTurnPower.cs:35-38), exactly the condition the record says is
missing. `HelloWorldPower` uses the identical pattern (`powers.py:3387-3398`),
confirming this is general engine machinery, not a one-off.

Confirmed by `git log --oneline -- sts2_rl/creatures.py sts2_rl/powers.py`:
this is committed (`c9bc337 second round of bug fixes`), not a
concurrently-running agent's uncommitted work.

No code change. **Close note:** `Creature.snapshot_powers_on_turn_start`
(`creatures.py:79-99`) plus `amount_on_turn_start` on `DrawCardsNextTurnPower`
(both hooks) already exist and already match
DrawCardsNextTurnPower.cs:28/:35-38 exactly; the record's "no sim
counterpart" grep result is stale. Verdict: `faithful` (for both the
`AfterSideTurnStart` entry here AND the already-dormant `ModifyHandDraw`
entry in the same record, which reads the same field the same way — not
separately re-verdicted since it isn't in my batch, but the controller should
know it's stale too).

### 6. `power/nostalgia/g8` — NARROWED (half fixed, half open)

This guard records contention with BOTH `power/corruption` and
`power/rebound`. Splitting it:

- **vs Rebound: now correctly resolved**, as a consequence of fix #7/#8
  below. Rebound moved onto the same `modify_card_play_result_pile` chain
  Nostalgia already uses, so the two now genuinely contend on ONE chain the
  way C#'s Hook.ModifyCardPlayResultPileTypeAndPosition does (last relevant
  writer wins) — see `test/test_r13_power1.py::TestReboundResultPileHook::test_rebound_registered_first_wins_the_redirect_and_ticks` and
  `::test_nostalgia_registered_first_leaves_rebound_unticked`, both GREEN,
  both asserting a C#-consistent (if listener-order-dependent) outcome
  instead of the old always-broken one.
- **vs Corruption: still open, but REVISED 2026-08-01 per R3-review.md §1.6/§1.2.**
  ~~identical root cause to entry #2 — same BLOCKED-ON-FOOTPRINT reasoning
  applies (Corruption physically moves the card from inside the play loop,
  before Nostalgia's chain decision can be acted on).~~ That framing
  implied Nostalgia's *contention with Corruption over the winning pile* is
  the open gap. It is not: `CorruptionPower.cs:27-38` has no pileType guard
  and `NostalgiaPower.cs:39-42` bails on non-Discard, so in C# too Corruption
  always overrides Nostalgia's redirect regardless of order — the sim's
  order-independent "Corruption always wins" final pile is already faithful
  here, the same correction as entry #2. What stays open is entry #2's three
  *residues* (Rebound's stack spent unconditionally instead of
  order-dependently, exhaust-timing inside vs. after the play loop,
  Corruption absent from the chain) — this guard is a duplicate surface of
  the same mechanism, not a second distinct gap, and should close on the same
  fix and be cross-referenced to entry #2 rather than tracked as separately
  "contended."

No code change beyond what #7/#8 already made (this is a queue-text
narrowing, not a separate fix). **Queue annotation (stays `gap`, liveness
mixed — the Rebound half is closed, the Corruption half is LIVE, but the
Corruption half's TEXT changes):** the Rebound half of this contention is now
FIXED (see `power/rebound`'s two entries in this same batch — both moved onto
`modify_card_play_result_pile`, so Rebound and Nostalgia now contend on one
real chain with an order-dependent, C#-consistent outcome, pinned by
`test/test_r13_power1.py::TestReboundResultPileHook`). The Corruption half is
unchanged and stays LIVE, but NOT because Corruption "always wins where C#
would let order decide" — C# also always has Corruption win
(`CorruptionPower.cs:27-38` has no pileType guard; `NostalgiaPower.cs:39-42`
bails on non-Discard) — the sim's final pile already matches. The live part
is `power/corruption`'s own three residues (Rebound's stack spent
unconditionally, exhaust timing inside the play loop, Corruption absent from
the chain) — see `power/corruption/ModifyCardPlayResultPileTypeAndPosition`
in this same report for the full analysis; this entry should be closed as a
cross-reference to that one rather than carry its own copy of the reasoning.

### 7. `power/rebound/ModifyCardPlayResultPileTypeAndPosition` — FIXED

`ReboundPower` used to reach into the piles by hand from `on_card_played`
(dispatched inside the play loop), instead of using the chain hook Nostalgia
already uses (`modify_card_play_result_pile`, dispatched at `combat.py`'s
`_resolve_card_play` BEFORE the loop — matching `CardModel.cs:1890`, which
runs before `OnPlay` at `:1931`).

Fixed: `ReboundPower.modify_card_play_result_pile(card, pile)` now: abstains
(`return pile`) unless `pile == "discard"` AND the card is actually in
`discard_pile` (the second half reproduces the original `on_card_played`
guard, since `pile` always arrives as the literal string `"discard"`
regardless of the card's real type at the call site — Power cards never
enter `discard_pile` at all, so this check is what keeps them exempt); ticks
and returns `"draw_top"` otherwise.

> **FIX PASS 2026-08-01 (R3-review.md §1.7, RF2 — the batch's one
> BLOCKING defect).** The guard above was incomplete: `pile == "discard" and
> card in discard_pile` is true not only for an ordinary Attack/Skill play
> but also for an **Exhaust-keyword card**, because `combat.py`'s
> `_resolve_card_play` passes this hook the literal string `"discard"` for
> EVERY non-Power card (`exhausts_this_play` is computed only after this
> call returns, at `combat.py:938`) and the card really is sitting in
> `discard_pile` at hook time (appended at `combat.py:905`, before the hook
> runs). C#'s seed is not that flat: `GetResultPileTypeForCardPlay`
> (`CardModel.cs:2070-2083`) hands the chain `PileType.Exhaust` — not
> Discard — for `ExhaustOnNextPlay || Keywords.Contains(CardKeyword.Exhaust)`,
> and `ReboundPower.cs:25-28` bails on any non-Discard `pileType`, so C#
> Rebound **abstains** on an exhausting play: no redirect, no stack spent.
> Pre-fix, the sim's Rebound ticked (and, on an otherwise-undecided chain,
> would have redirected) an exhausting card — and because a LATER, separate
> branch in `combat.py` still moves an exhausting card out of `discard_pile`
> regardless of `result_pile`, the final pile came out right while the stack
> silently vanished, invisible to every pre-existing test (this is round
> 12's own named failure mode recurring inside this very fix). **Fixed** by
> adding one more bail condition, read before `combat.py` clears it at
> `:939`: `if card.exhausts or card.exhaust_on_next_play: return pile`
> (`sts2_rl/powers.py`, `ReboundPower.modify_card_play_result_pile`). Pinned
> RED-first by
> `test/test_r13_power1.py::TestReboundResultPileHook::test_exhausting_card_does_not_spend_a_rebound_stack`
> (played `ImperviousCard()`, an ordinary Rare Skill with `exhausts = True`
> — `Impervious.cs:17` declares `CardKeyword.Exhaust` — under
> `ReboundPower(1)`; RED pre-fix with `KeyError: 'rebound'`, i.e. the power
> had already ticked to 0 and expired even though it never redirected
> anything; GREEN post-fix: card exhausts normally, `rebound` stays at
> amount 1, and the untouched stack still redirects the NEXT ordinary
> play). See "Fix pass (2026-08-01)" at the end of this report for the full
> before/after evidence and counts.

**Finding F1 (not in the brief, discovered while fixing this): a
previously-`faithful`-verdicted guard on this same record was wrong.**
`rebound.json`'s guard "Rebound redirects the Rebound card itself" claims
"the power is applied during Rebound's own resolution, so — matching the
game's ordering — the Rebound card itself is the first play redirected."
**This is false in C#.** Read `CardModel.cs:1867-1992` (`OnPlayWrapper`)
directly: `Hook.ModifyCardPlayResultPileTypeAndPosition` is evaluated once at
line 1890, captured into `resultPileType`, and used for the FINAL pile
disposition after the whole play loop (lines 1976-1990) — but
`Rebound.cs:31`'s `PowerCmd.Apply<ReboundPound>` call is inside `OnPlay`, which
only runs at line 1931, deep inside the loop the decision at line 1890
already ran before. **The power the card's own play applies is not yet a
listener when its own pile decision is made.** This makes Rebound's own card
land in the ordinary discard pile, not the draw-pile top — confirmed by
reading `Rebound.cs` (the card: damage, then `PowerCmd.Apply<ReboundPower>`)
and by execution (see tests below). The sim's old `on_card_played`-based
implementation only "worked" because it ran from a LATER dispatch point
(inside the loop, after `OnPlay`) where the just-applied power WAS already a
listener — an artifact of the wrong hook slot, not a correctly-ported
behavior. **I updated the class docstring and the pre-existing test that
encoded this (`test/test_underdocks_hive_events.py::test_rebound_puts_card_on_top_of_draw`,
renamed/split into `test_rebound_does_not_redirect_its_own_play` +
`test_rebound_puts_the_next_play_on_top_of_draw`)** since it is now
red-for-cause, not a regression — the assertion itself encoded the wrong
behavior. Flagging this prominently per protocol ("findings outrank fixes"):
**the `rebound.json` guard "Rebound redirects the Rebound card itself" should
be re-verdicted from `faithful` to `gap`-then-`faithful`-after-this-fix (i.e.
close it as `faithful` under the NEW, corrected reasoning, not the old
one)** — it is not one of my 12 assigned entries, so I did not edit the
record, but the controller should not leave the old rationale standing.

**Tests:** `test/test_r13_power1.py::TestReboundResultPileHook::test_does_not_redirect_the_card_that_applied_it`, `::test_redirects_the_next_play_and_consumes_a_stack`, `::test_exhausting_card_does_not_spend_a_rebound_stack` (added 2026-08-01, RF2 fix pin), plus the two order tests under #8. Also `test/test_underdocks_hive_events.py::test_rebound_does_not_redirect_its_own_play` and `::test_rebound_puts_the_next_play_on_top_of_draw` (both GREEN; the original assertion was RED against the fix, confirmed, then corrected — not silently reverted).

**Close note (REVISED 2026-08-01):** the decision moved onto
`modify_card_play_result_pile`, matching ReboundPower.cs:19-30 and
CardModel.cs:1890's timing exactly; this also corrects the sibling guard
"Rebound redirects the Rebound card itself" from a mistaken `faithful` to a
`faithful` under the right reasoning (it does NOT self-redirect — see F1
above; propose the controller update that guard's text too even though it's
outside this batch). ~~Verdict: `faithful`.~~ **The 2026-07-31 verdict below
was premature: the guard as originally shipped still ticked/redirected an
Exhaust-keyword card, where `GetResultPileTypeForCardPlay`
(CardModel.cs:2070-2083) seeds the chain with `PileType.Exhaust` for those
and `ReboundPower.cs:25-28` abstains — see the "FIX PASS 2026-08-01" box
above and the "Fix pass" section at the end of this report. The hook MOVE
itself was correct and needed no further change; only the guard's condition
was incomplete.** Verdict (now, post fix-pass): `faithful`.

### 8. `power/rebound/AfterModifyingCardPlayResultPileOrPosition` — FIXED

C# consumes the stack from a dedicated after-hook fired only over listeners
whose OWN call changed the pile (`Hook.cs:1391-1405`) — machinery the sim
doesn't have (same absence as `seam/power_cmd.json` G4, confirmed still true:
no `after_modify_card_play_result_pile`/notification-list mechanism exists
anywhere in `hooks.py`/`combat.py`, grepped). Rather than building that
machinery (out of footprint), the tick is folded into
`modify_card_play_result_pile` itself, gated on the SAME condition the
dedicated after-hook's "did I change it" check would require: `pile ==
"discard"` on entry. This reproduces the observable coupling exactly —
whichever of Rebound/Nostalgia's chain calls is the one that actually
performs the discard->draw_top mutation is the one (and only one) that
consumes a stack — without adding the extra machinery.

> **REVISED 2026-08-01 (R3-review.md §1.8).** "`pile == "discard"` on
> entry" was **not actually the same condition** as C#'s "did I change it"
> check, for the same reason as #7's fix pass: `combat.py` hands this hook
> the literal `"discard"` for an Exhaust-keyword card too (its real
> `defaultPileType` seed in C# is `Exhaust`, not `Discard`), so the
> pre-fix-pass gate ticked on a play where C#'s dedicated after-hook would
> never have fired at all (Rebound was never added to `Hook.cs:1391-1404`'s
> `modifiers` list because it abstained on the non-Discard seed). The gate
> is now `pile == "discard" and card in discard_pile and not (card.exhausts
> or card.exhaust_on_next_play)` — i.e. #7's exhaust check is exactly what
> makes THIS entry's "did I change it" condition correct too, since the tick
> lives inside the same method. No separate code change was needed here
> beyond #7's; this entry closes on the same fix.

**Tests (the order-dependence, matching C#'s per-listener semantics):**
`test/test_r13_power1.py::TestReboundResultPileHook::test_rebound_registered_first_wins_the_redirect_and_ticks` (Rebound applied before Nostalgia: Rebound sees `pile=="discard"`, redirects, ticks to 0/expires) and `::test_nostalgia_registered_first_leaves_rebound_unticked` (Nostalgia applied first: it redirects first, Rebound then sees `pile=="draw_top"` already and abstains — does NOT tick). Both GREEN. This order-dependence is not a bug: it is C#'s actual per-listener "did I change it" rule (Hook.cs:1391-1405) reproduced faithfully; WHICH order wins is `hook_dispatch/G2`'s question and correctly not re-argued here. **Plus (2026-08-01) `::test_exhausting_card_does_not_spend_a_rebound_stack`** — the case where the "did I change it" gate was wrong: an exhausting card under Rebound alone must leave the stack unspent, not just correctly ordered against Nostalgia.

**Close note (REVISED 2026-08-01):** the tick now fires exactly when this
power's own chain call performed the redirect, folded into
`modify_card_play_result_pile` since the sim has no dedicated
notification-list hook (same absence as `power_cmd` G4); observably matches
ReboundPower.cs:32-39 for every case executed, **including the exhaust case
the original fix missed** (see box above). Verdict: `faithful`.

### 9. `power/retain_hand/AfterSideTurnEnd` — FIXED

`RetainHandPower` ticked from `on_enemy_side_end`
(`Hook.AfterTurnEnd` for the ENEMY side), which an extra player turn never
reaches — `combat.py`'s `_end_turn_internal` checks `should_take_extra_turn`
and, if true, calls `_start_player_turn()` directly, returning before
`_execute_enemy_turn()` ever runs. C#'s `AfterSideTurnEnd`
(RetainHandPower.cs:28-34) is the PLAYER side's `Hook.AfterTurnEnd`
(CombatManager.cs:1307), which fires every end_turn regardless. Fixed:
`RetainHandPower` now implements `after_player_turn_end` (the same slot
`ReboundPower` already uses for its own `AfterSideTurnEnd`), which
`combat.py` fires unconditionally, right after the flush and before the
extra-turn check.

**Tests:** `test/test_r13_power1.py::TestRetainHandTicksOnPlayerSideEnd::test_ticks_on_a_normal_turn_end` (already passed pre-fix — regression coverage) and `::test_ticks_on_an_extra_turn_too` (RED before: the power survived an extra turn at amount 1; GREEN after: it's gone). The extra turn is forced via a minimal `should_take_extra_turn` stub listener (`_ExtraTurn`, mirrors an existing helper class in `test/test_turn_structure_gaps.py` rather than depending on the Pael's Eye relic, which is out of footprint).

**Close note:** the tick moved from `on_enemy_side_end` to
`after_player_turn_end`, matching RetainHandPower.cs:28-34/
CombatManager.cs:1307's PLAYER-side timing exactly; an extra turn (which
never reaches `_execute_enemy_turn`) now still ticks it, as C# does.
Verdict: `faithful`.

### 10. `power/steam_eruption/g4` — DORMANT-ENUMERATED

Mechanism: `power/_death_prevention_branch` (shared, already labelled
`[DORMANT]` in `audit/GAP-QUEUE.md:425`). Per the brief's instruction, this
needs its OWN site verified, not inherited.

**The re-entry gap this guard describes cannot be reached through Steam
Eruption at all.** Read `SteamEruptionPower.cs` directly: it declares
`AfterDeath`, `ShouldStopCombatFromEnding`,
`ShouldCreatureBeRemovedFromCombatAfterDeath`,
`ShouldPowerBeRemovedAfterOwnerDeath` — **no `ShouldDie` override**. Its
`AfterDeath` guards on `!wasRemovalPrevented` (real death only). Read
`WaterfallGiant.cs` (the monster) directly: no other power or override
touches `ShouldDie` either. So the Waterfall Giant's death ALWAYS takes
`_resolve_death`'s real-death arm (`cmds.py`'s `if target.max_hp <= 0 or
hooks.should_die(...)`), never the prevention (`else`) arm — and the
re-entry concern (`CreatureCmd.cs:562-565`'s recursive re-kill) is
exclusively inside that `else` arm in C#. **Enumerated every `should_die`
implementer in the sim** (`grep -rn "def should_die" sts2_rl/`): exactly
three hits — the dispatcher itself (`hooks.py:1568`), Fairy in a Bottle
(`potions.py:1338`, guards `creature.side != "player"` — explicitly refuses
to prevent a non-player's death), and Lizard Tail
(`relics/lizard_tail.py:32`, a relic — relics only ever belong to the
player in this sim). **No listener can ever make `hooks.should_die` return
False for a monster.** Confirms current `sts2_rl/powers.py`'s own
`AdaptablePower`/`IllusionPower` (the two sibling units under this
mechanism, not in my batch) have ALSO already been corrected to drop their
`ShouldDie` overrides — their class comments say so explicitly ("no
ShouldDie override at all, so the death is REAL"). See finding F2 below.

**Close note:** enumerated every `should_die` implementer in `sts2_rl/`
(3 total: the dispatcher, Fairy in a Bottle [player-only], Lizard Tail
[player-only, relic]); none can apply to a monster, and
`SteamEruptionPower`/`WaterfallGiant` implement no `ShouldDie` override of
their own, so `_resolve_death`'s prevention arm — where the missing
re-entry modeling would matter — is provably never reached through this
power. DORMANT for this site (`_death_prevention_branch`'s mechanism-level
`gap` verdict stands unchanged, cross-referenced not re-argued per rule 3).

**Finding F2 (not in the brief — a stale mechanism-level note, likely
relevant to whoever settles `power/adaptable/g5` / `power/illusion/g6`,
neither in my batch):** `audit/GAP-QUEUE.md:425-439`'s summary of
`power/_death_prevention_branch` still describes the OLD, pre-fix state —
"The sim **prevents** the death from `should_die`
(`sts2_rl/powers.py:3365-3370` returns `False`) and `sts2_rl/cmds.py:106-113`
floors the creature at **1 HP**." Reading today's `powers.py`, BOTH
`AdaptablePower` and `IllusionPower` (the other two units this mechanism
covers) have their own comments stating they no longer override `ShouldDie`
either ("This is the ONLY death-side predicate the power implements... no
ShouldDie override at all, so the death is REAL"), matching what I found for
Steam Eruption. If that holds up under the dedicated agent's own
verification, **none of the three named power sites exercises the
prevention branch any more**, and the mechanism-level "still open 4 of 15
sites" bullet at `GAP-QUEUE.md:427` may be entirely stale for the power tier
(only `monster/test_subject/g1`, a different family, might still be live) —
worth a fast recheck by whoever owns those two entries, since it could close
the whole mechanism rather than three separate sites.

### 11. `power/the_bomb/InstanceType` — LIVE (confirmed), no footprint-only fix available

Mechanism: `power_cmd/G5` (shared). Re-executed the record's own
reproduction against today's tree:

```
bombs: [[2, 40], [3, 40]] amount: 2
```

Matches the record's 2026-07-26 executed evidence exactly — two Bomb plays
on consecutive turns still collapse into ONE `the_bomb` power entry with
`amount=2` (the shorter fuse), where C# holds two independently-Amount'd
`TheBombPower` instances (2 and 3). Damage is exact (each fuse tracks its
own `turns_left`/`damage`); the STATE is not — `full_env.py` encodes one
presence-bit + signed-amount pair per power id, so the two-instance case is
unrepresentable in the observation regardless of what `powers.py` does. This
is a real, executed, reachable divergence — confirmed **LIVE**, not
inherited-dormant from `power_cmd/G5`'s current `[DORMANT]` mechanism-level
label (`GAP-QUEUE.md:1631`, "**Still open:** `power/the_bomb/InstanceType`
and `power/swipe/InstanceType` — both already reproduce the observable
behaviour via their own pre-existing hand-rolled workarounds"). **That
mechanism-level claim is not accurate for The Bomb's own state
representation** — see finding F3.

No code change: `TheBombPower`'s `self.bombs` fuse-list workaround
(`powers.py`, class `TheBombPower`) is already the best achievable
approximation without real `PowerInstanceType` dispatch, and its own
docstring already explains exactly why switching to
`instance_type = PowerInstanceType.INSTANCED` would be a regression (it
would silence `on_stack`, which is what the workaround needs). A full fix
needs real per-instance `PowerCmd.apply`/`on_stack` semantics (`cmds.py`) AND
an observation encoding that can represent N instances of one power id
(`full_env.py`) — both out of footprint.

**Queue annotation (promotes out of `unlabelled` to explicit LIVE,
overriding the inherited-dormant default from its mechanism):** Re-executed
2026-07-31, unchanged from the 2026-07-26 evidence already on this record:
two Bomb plays collapse to one power-list entry with the shorter fuse's
amount, where C# shows two. LIVE — confirmed by execution, not inherited.
The damage stays exact so this is a state/observation divergence, not a
combat-outcome one. No footprint-only fix exists (needs `cmds.py` +
`full_env.py`); `powers.py`'s current fuse-list workaround is already the
best available mitigation and should not be touched further without those
two files in scope.

**Finding F3 (not in the brief):** `power_cmd/G5`'s mechanism-level entry in
`GAP-QUEUE.md:1631` is labelled `[DORMANT]` and states both remaining units
(`the_bomb`, `swipe`) "already reproduce the observable behaviour via their
own pre-existing hand-rolled workarounds" with no caveat. That is true for
DAMAGE but not for STATE — `the_bomb.json`'s own record already argues this
in detail (full_env.py's one-entry-per-power-id encoding), and my
re-execution confirms it still holds today. The mechanism-level DORMANT
label should carry an exception note for these two units' *observation*
divergence, or the two should be tracked as their own live sub-entries
rather than folded into the mechanism's blanket dormant summary. I did not
re-verify `power/swipe/InstanceType` (not in my batch, and its record cites
`RunState.finish_combat`'s escaped-hopper deck-reconciliation walk as a
reason migrating it would regress something today's workaround protects
against — that's a different, possibly more load-bearing shape than The
Bomb's, and deserves its own look rather than a blanket "same as the_bomb").

### 12. `power/vital_spark/BeforeCombatStart` — DORMANT-ENUMERATED

> **REVISED 2026-08-01 per R3-review.md §1.12/RF3.** The record's issue
> text (`audit/records/power/vital_spark.json`, `BeforeCombatStart`) states:
> "the sim adds a `card.affliction is None` test that VitalSparkPower.cs:33-38
> does not have, **where C#'s `CardCmd.Afflict` overwrites**." **The
> "overwrites" claim is false and this report's original text below repeated
> it without re-deriving `CardCmd.Afflict` itself.** Corrected:
>
> - `CardCmd.cs:625-659`, `:641` — `if (!affliction.CanAfflict(card)) return
>   null;` — the afflict call can REFUSE outright.
> - `AfflictionModel.cs:200-203` — `CanAfflict` returns **false** when
>   `card.Affliction != null && (!IsStackable || card.Affliction.GetType() !=
>   GetType())` — i.e. a DIFFERENT affliction type already present blocks the
>   new one entirely.
> - `CardCmd.cs:645-657` — a same-TYPE affliction already present does
>   `card.Affliction.Amount += (int)amount` — it **stacks**, it does not
>   overwrite.
>
> So the real split is: (a) a *different* affliction already on the card →
> C# refuses (`CanAfflict` false) — and the sim's `card.affliction is None`
> guard produces the SAME outcome here, so this half is not a divergence at
> all (the sim's own `CardCmd.afflict`, `cmds.py:1218-1242`, already ports
> `CanAfflict`, making the power-level guard redundant, not divergent, for
> this case); (b) `Tainted` ALREADY present → C# **stacks** the amount
> (`Tainted.cs:9-19` declares `is_stackable = True`) where the sim's `and
> card.affliction is None` guard skips the application entirely. **(b),
> and only (b), is the real divergence** — one-sixth the size the record's
> "overwrites" text implies (one of the six card-type × affliction-state
> combinations, not the general case).

Confirmed the divergence is real and current: C#'s `BeforeCombatStart`
(VitalSparkPower.cs:25-38) afflicts every Skill card unconditionally (no
`Affliction == null` test — contrast its own `AfterCardEnteredCombat`, which
DOES test it, VitalSparkPower.cs:41-46); the sim's `on_combat_start`
(`powers.py`, class `VitalSparkPower`) adds `and card.affliction is None`
that C# does not have at this call site. ~~[This framing suggested the
divergence was "any pre-existing affliction blocks the sim's re-afflict
where C# would overwrite it" — corrected above: C# only ever STACKS a
same-type affliction here, never overwrites, and refuses a different-type
one exactly like the sim's guard already does.]~~

This is the exact sibling of `power/galvanic/BeforeCombatStart`, **which is
already labelled `dormant` in `audit/GAP-QUEUE.md:2545`** with the identical
reasoning ("no affliction survives across combats... Trigger: a second
Power-card afflicter, or a persistent affliction") — **and the identical
"overwrites" mis-statement, per rule 3 inheritance; that record's text needs
the same correction, though `galvanic` is not one of my 12 entries.** Per
binding rule 3 the dormancy verdict carries over, re-verified rather than
blindly inherited:

- Grepped every `on_combat_start` implementer in `powers.py`: exactly two —
  `VitalSparkPower` (Skills) and `GalvanicPower` (Powers). Disjoint by
  `card_type` (a card cannot be both), so they can never race each other.
- No affliction persists across combats in a way that would leave a Skill
  card non-`None` when a NEW combat's `on_combat_start` runs, absent the
  ALSO-dormant `power/vital_spark/AfterRemoved` gap (not in my batch) firing
  via a non-death removal path — and that gap's own text confirms Infested
  Prism (Vital Spark's sole applier) never removes the power by any route
  but death, which correctly clears the affliction via `on_death`.
- The narrowed (b)-only divergence (a same-combat `Tainted` re-afflict
  should stack, not no-op) needs the SAME reachability fact to matter as the
  original framing did: a Skill card must already carry `Tainted` when a
  NEW combat's `BeforeCombatStart` runs. That is exactly as unreachable as
  before — the correction narrows WHAT the gap is, not WHETHER it is
  dormant.

**Close note (REVISED 2026-08-01, replaces the "overwrites" framing
entirely):** the record's stated mechanism was wrong — `CardCmd.Afflict`
(`CardCmd.cs:625-659`) refuses a different-type affliction via `CanAfflict`
(`AfflictionModel.cs:200-203`, which the sim's own `CardCmd.afflict`,
`cmds.py:1218-1242`, already ports) and STACKS a same-type one
(`CardCmd.cs:656`); it never overwrites. The sim's `card.affliction is
None` guard at `BeforeCombatStart` therefore matches C# for a
different-affliction card and diverges only for the narrower case of a
Skill that already carries `Tainted` specifically (`Tainted.cs:9-19`,
`is_stackable = True`) — that case should stack, the sim's guard makes it a
no-op. Dormancy verdict unchanged and re-verified independently of the
`galvanic` sibling: identical shape and dormancy to the already-settled
`power/galvanic/BeforeCombatStart` (`gap`, dormant, `GAP-QUEUE.md:2545`,
which carries the same "overwrites" mis-statement and should be corrected
identically); confirmed exactly two `on_combat_start` affliction listeners
exist in `powers.py` and they are disjoint by `card_type`, and confirmed the
only path to a stale non-`None` affliction surviving into a new combat (the
separately-tracked, also-dormant `AfterRemoved` gap) is itself unreachable
with current content. Verdict:
`gap`, dormant.

---

## Record-close proposals

| Record | Entry key | Proposed verdict | Section |
|---|---|---|---|
| `audit/records/power/artifact.json` | `AfterModifyingPowerAmountReceived` | `faithful` (STALE-ALREADY-FIXED) | hooks |
| `audit/records/power/corruption.json` | `ModifyCardPlayResultPileTypeAndPosition` | stays `gap`, liveness LIVE — **issue text REPLACED 2026-08-01, order-independence is not the gap; see entry #2** | hooks |
| `audit/records/power/dark_embrace.json` | `AfterCardExhausted` | `faithful` (FIXED) | hooks |
| `audit/records/power/dark_embrace.json` | `AfterSideTurnEnd` | `faithful` (FIXED) — **RF5 residual added 2026-08-01, does not block close** | hooks |
| `audit/records/power/draw_cards_next_turn.json` | `AfterSideTurnStart` | `faithful` (STALE-ALREADY-FIXED) | hooks |
| `audit/records/power/nostalgia.json` | `g8` | stays `gap`, text NARROWED (Rebound half closed, Corruption half LIVE) — **Corruption-half text REPLACED 2026-08-01, cross-referenced to `power/corruption` instead of independently reasoned; see entry #6** | guards |
| `audit/records/power/rebound.json` | `ModifyCardPlayResultPileTypeAndPosition` | `faithful` (FIXED) — **exhaust gate ADDED 2026-08-01 (RF2); the earlier 2026-07-31 verdict was premature, see "Fix pass" section** | hooks |
| `audit/records/power/rebound.json` | `AfterModifyingCardPlayResultPileOrPosition` | `faithful` (FIXED) — **closes on the same 2026-08-01 exhaust-gate fix; the tick's gate is not a separate mechanism from the entry above** | hooks |
| `audit/records/power/rebound.json` | *(not in batch — F1)* guard "Rebound redirects the Rebound card itself" | re-verdict from mistaken `faithful` to `faithful`-under-corrected-reasoning | guards |
| `audit/records/power/retain_hand.json` | `AfterSideTurnEnd` | `faithful` (FIXED) | hooks |
| `audit/records/power/steam_eruption.json` | `g4` | stays `gap`, liveness DORMANT (site-specific, enumerated) | guards |
| `audit/records/power/the_bomb.json` | `InstanceType` | stays `gap`, liveness LIVE (confirmed, not inherited-dormant) | hooks |
| `audit/records/power/vital_spark.json` | `BeforeCombatStart` | stays `gap`, liveness DORMANT (cross-referenced to galvanic) — **issue text REPLACED 2026-08-01 (RF3): the "CardCmd.Afflict overwrites" claim is false; the real (dormant) divergence is narrower — a same-combat Tainted re-afflict should STACK, not no-op; see entry #12. `power/galvanic.json`'s identical text needs the same correction (not my batch).** | hooks |

Each close note (what reasoning it replaces) is spelled out per-entry above,
not just the verdict.

**2026-08-01 fix pass note:** the `power/rebound` rows above changed FROM
"FIXED" TO "FIXED" — the verdict did not move, but the review found the
2026-07-31 fix incomplete (see "Fix pass (2026-08-01)" section at the end of
this report), so if the controller already queued a record update off the
pre-fix-pass version of this report, it should re-pull the current text
before applying it: the `ModifyCardPlayResultPileTypeAndPosition` and
`AfterModifyingCardPlayResultPileOrPosition` close notes both now describe
the exhaust-aware guard, not the guard that shipped 2026-07-31.

## Queue-annotation proposals

See each entry's "Close note" / "Queue annotation" text above — written in
`GAP-QUEUE.md`'s established terse style, ready to paste. Two additional
mechanism-level notes for the controller (not entries I own):

- `power_cmd/G5`'s `[DORMANT]` mechanism summary (`GAP-QUEUE.md:1631`)
  overstates closure for `power/the_bomb/InstanceType` — see finding F3.
- `power/_death_prevention_branch`'s `[DORMANT]` mechanism summary
  (`GAP-QUEUE.md:425-439`) may be entirely stale for the power tier now
  that all three named units (`adaptable`, `illusion`, `steam_eruption`)
  appear to have dropped their `ShouldDie` overrides — see finding F2, and
  recommend whoever owns `power/adaptable/g5`/`power/illusion/g6` re-check
  quickly since it could close the whole mechanism at once.

## Findings not in the brief

- **F1** (`power/rebound`): the guard "Rebound redirects the Rebound card
  itself" was mis-verdicted `faithful` — C# never does this
  (`CardModel.cs:1890` decides before `OnPlay` at `:1931` applies the
  power). Corrected as a side effect of fixing entries #7/#8; a pre-existing
  test encoding the wrong behavior
  (`test/test_underdocks_hive_events.py::test_rebound_puts_card_on_top_of_draw`)
  was split/corrected, not silently left red.
- **F2** (`power/_death_prevention_branch`): the mechanism's `GAP-QUEUE.md`
  summary describes a pre-fix state that no longer matches any of its three
  named power units' current code; possibly closeable as a whole once
  `adaptable`/`illusion` are independently re-checked (not my batch).
- **F3** (`power_cmd/G5`): the mechanism's `[DORMANT]` summary glosses over
  a real, executed, LIVE state/observation divergence on `the_bomb` (and
  possibly `swipe`, unchecked); the blanket "both already reproduce the
  observable behaviour" claim is true for damage only.

## Tests

**New file:** `test/test_r13_power1.py` (10 tests as of 2026-07-31: Dark
Embrace amount + ethereal deferral x4, Rebound result-pile hook x4, Retain
Hand extra-turn tick x2 — now 11, +1 exhaust-gate pin, see "Fix pass
(2026-08-01)" at the end of this report).

**Edited file:** `test/test_underdocks_hive_events.py` — one pre-existing
test (`test_rebound_puts_card_on_top_of_draw`) encoded the F1 bug; split
into `test_rebound_does_not_redirect_its_own_play` (asserts the corrected
behavior) and `test_rebound_puts_the_next_play_on_top_of_draw` (preserves
the original coverage of the redirect mechanic, retargeted at the next
play instead of Rebound's own).

**Commands run:**
```
py -m pytest test/test_r13_power1.py -v
py -m pytest test/test_underdocks_hive_events.py -q
py -m pytest test/test_r13_power1.py test/test_underdocks_hive_events.py test/test_powers.py test/test_ironclad_powers.py test/test_new_features.py test/test_card_plays_started.py test/test_stack_type_single.py test/test_previews.py test/test_relic_live_tail.py test/test_can_receive_powers.py test/test_overgrowth_powers.py test/test_power_modifier_phases.py test/test_power_type_for_amount.py test/test_relics.py test/test_turn_start_snapshot.py -q
```

**Final counts:** `test_r13_power1.py` 10/10 passed. Combined sweep above:
**717 passed, 3 failed** — the 3 failures are `TestPowerInstanceType` cases
unrelated to this batch (see "Environment note" at the top; confirmed by
diff that `powers.py`'s only changes are inside `DarkEmbracePower`,
`ReboundPower`, `RetainHandPower`). Did not run the full suite per protocol.

## Concerns for the controller

1. Two entries (`corruption`, and half of `nostalgia/g8`) are genuinely
   BLOCKED-ON-FOOTPRINT — they need `hooks.py` (an `"exhaust"`
   pile-destination value) and `combat.py` (the post-loop dispatch for it).
   Whoever owns those files next should look at this report's entry #2 for
   the exact shape needed; `power/rebound`'s fix in this batch is the
   template for what Corruption's fix would look like once that machinery
   exists.
2. `the_bomb/InstanceType` needs `cmds.py` (real per-instance apply/stacking)
   and `full_env.py` (multi-instance observation encoding) to fully close —
   also out of footprint, and probably a bigger, dedicated task given the
   observation-space implications (11 ported InstanceType units total per
   `power_cmd/G5`).
3. F1/F2/F3 above are handoffs to other lanes/rounds, not requests — I did
   not touch the records or files they concern beyond what my 12 entries
   required.

## Fix pass (2026-08-01)

Amending this report per `R3-review.md` (**Verdict: NEEDS-FIXES**). The
overturn on `power/rebound`'s self-redirect guard **STANDS** and every other
confirmed verdict in the review **stands unrelitigated**; the items below are
exactly the review's "Required before this batch folds" (§6) list, applied
in the same footprint as the original batch (`sts2_rl/powers.py`
`ReboundPower` only, `test/test_r13_power1.py`).

### 1. The blocking defect (RF2 / review §1.7) — FIXED, RED-first

**Root cause, confirmed by re-deriving the C#, not by trusting the review's
prose:** `GetResultPileTypeForCardPlay` (`CardModel.cs:2070-2083`) is the
`ModifyCardPlayResultPileTypeAndPosition` chain's `defaultPileType` seed. It
returns `PileType.Exhaust` — not `Discard` — for
`ExhaustOnNextPlay || Keywords.Contains(CardKeyword.Exhaust)`.
`ReboundPower.cs:25-28` bails on any `pileType != Discard`. So on an
exhausting card, C# Rebound's chain call never fires past its own guard: no
redirect, **no stack spent** — it abstains completely, identically to how it
already abstains once Nostalgia has redirected first.

The sim's dispatcher (`sts2_rl/combat.py:934`, confirmed by reading it —
untouched, out of footprint) always calls
`self.hooks.modify_card_play_result_pile(card, "discard")` with the literal
string `"discard"` for every non-Power card, regardless of the card's real
keywords; `exhausts_this_play = card.exhausts or card.exhaust_on_next_play`
is computed only on the NEXT line (`:938`), after the hook has already run.
The card is genuinely present in `player.discard_pile` at hook time
(appended unconditionally at `:905`, before the hook call at `:934` —
C#'s `PileType.Play` limbo during `OnPlay` is not modelled). So
`ReboundPower.modify_card_play_result_pile`'s pre-fix-pass guard
(`pile != "discard" or card not in discard_pile`) could not tell an
exhausting card from an ordinary one: it ticked and returned `"draw_top"`
regardless.

**Why this was silent, not loud:** `combat.py`'s post-loop resolution runs
the exhaust move (`:1040-1043`, `if exhausts_this_play and card in
discard_pile: … exhaust_pile.append(card)`) BEFORE the result-pile redirect
move (`:1048-1050`, `if card in discard_pile and result_pile ==
"draw_top"`). By the time the redirect move runs, the exhausting card has
already left `discard_pile`, so its guard is false and the (wrong)
`"draw_top"` verdict never actually relocates anything. **The final pile
came out right. Only the power's internal stack count was wrong**, and
nothing before this fix pass observed that count on an exhausting play —
exactly the "silent divergence invisible to every test" failure mode the
campaign has hit before (round 12's own lesson, restated in
`tier2-round12-method-lessons`).

**RED first, without touching the fix:** added
`TestReboundResultPileHook::test_exhausting_card_does_not_spend_a_rebound_stack`
to `test/test_r13_power1.py` (plays `ImperviousCard()` — a Rare Skill,
`exhausts = True`, `Impervious.cs:17` declares `CardKeyword.Exhaust`, chosen
per the review's suggestion that "a unit-level pin with any exhausting card
is fine" over the Trash Heap `ReboundCard` path) under `ReboundPower(1)` and
asserted the power stays at amount 1. Run against the tree exactly as it
stood after the original batch (the pre-existing, un-amended
`modify_card_play_result_pile`):

```
py -m pytest test/test_r13_power1.py::TestReboundResultPileHook::test_exhausting_card_does_not_spend_a_rebound_stack -v
FAILED — KeyError: 'rebound'
```

(`cs.player.powers["rebound"]` — the power had already ticked 1 → 0 and
self-expired via `Power._tick`/`_expire`, even though it never performed a
redirect. This is RED obtained by writing the test BEFORE the fix, per
protocol — the tree was never reverted.)

**Fix** (`sts2_rl/powers.py`, `ReboundPower.modify_card_play_result_pile`):
added one more bail condition, checked before the tick:

```python
if card.exhausts or card.exhaust_on_next_play:
    return pile
```

placed after the existing `pile != "discard" or card not in discard_pile`
guard and before `self._tick()`. `card.exhaust_on_next_play` is still
`True` at this point in the call sequence — `combat.py:939` only clears it
on the line AFTER the hook call returns — so reading it here reproduces
`GetResultPileTypeForCardPlay`'s own consume-on-the-spot timing rather than
reading a value `combat.py` has already zeroed. This is the two-line shape
the review proposed in §1.7 (`review §1.7`'s suggested patch and the shipped
fix differ only in comment length, confirming the review's "two lines
inside the lane's footprint" framing — see next paragraph). Re-ran the same
test: **GREEN**. Also updated the class docstring to state the abstention
rule (it previously covered only the Discard-redirect/self-play cases).

**Confirming the review's footprint framing:** correct, exactly. The whole
fix is the one `if` statement above, entirely inside
`ReboundPower.modify_card_play_result_pile` in `sts2_rl/powers.py` — no
change to `hooks.py` or `combat.py` was needed, because the information the
guard needs (`card.exhausts`, `card.exhaust_on_next_play`) is already an
attribute of the `Card` object the hook already receives as its first
argument; `combat.py` passing the literal `"discard"` string is a real,
separately-tracked staleness (RF4, `hooks.py:1081-1090`'s docstring — out of
footprint, unchanged), but working around it from inside the power did not
require touching it.

Because `AfterModifyingCardPlayResultPileOrPosition`'s tick (review entry
#8) is folded into this same method (round 12/13's `power_cmd` G4
workaround), the exhaust guard fixes both `power/rebound` entries at once —
there is no second code change for entry #8.

### 2. Corrected R3-report.md's entry #2/#6 Corruption framing (RF1) — DONE

Rewrote entry #2 (`power/corruption/ModifyCardPlayResultPileTypeAndPosition`)
and entry #6's Corruption half (`power/nostalgia/g8`) in place above (struck
the old text visibly with `~~…~~`, did not delete it, per the report
contract's "state which reasoning you replaced"). Re-derived directly from
`CorruptionPower.cs:27-38` (no `pileType` guard at all),
`NostalgiaPower.cs:39-42` and `ReboundPower.cs:25-28` (both bail on
`pileType != Discard`) and confirmed by hand-tracing both application
orders: C# reaches `Exhaust` either way, so order-independence — the
report's original headline divergence — is not a divergence; the sim's
final pile already matches. The entry stays LIVE on the three narrower
residues the review named (Rebound's stack spent unconditionally instead of
order-dependently under Corruption; the exhaust move happening inside the
play-count loop instead of after it; Corruption never joining the chain).
The proposed fix SHAPE (extend `modify_card_play_result_pile` to express an
`"exhaust"` destination, move Corruption's decision onto it, branch on it in
`combat.py`'s post-loop dispatch) is unchanged — only the justification for
doing it was wrong, and BLOCKED-ON-FOOTPRINT still holds (`hooks.py` +
`combat.py`, neither in this lane's footprint).

### 3. Other review-listed fix items

- **§6.3 / RF3** — `power/vital_spark/BeforeCombatStart`'s close note
  rewritten in place above: `CardCmd.Afflict` does not "overwrite" (it
  refuses a different-type affliction via `CanAfflict`,
  `AfflictionModel.cs:200-203`, and STACKS a same-type one, `CardCmd.cs:656`);
  the real, still-dormant divergence is narrower — a same-combat `Tainted`
  re-afflict should stack, not no-op. Flagged that `power/galvanic.json`
  carries the identical false claim and needs the identical correction
  (out of this batch — `galvanic` is not one of my 12 entries).
- **§6.4** — entry #4's "All three RED before the fix" claim corrected: only
  2 of 3 pins were actually RED pre-fix (verified by re-deriving from the
  existing `test/test_r13_power1.py` assertions and the review's own
  reconstruction finding); added the RF5 residual (Dark Embrace's
  zero-ethereal-count early return skips C#'s unconditional
  `Hook.ShouldDraw` dispatch — dormant, zero `after_preventing_draw`
  listeners exist) as a named, non-blocking residual on the close note.
- **§6.5 (optional)** — RF4 (`hooks.py:1081-1090`'s stale docstring) and RF6
  (no `is_dupe` concept anywhere in `sts2_rl/`, the third arm of
  `GetResultPileTypeForCardPlay`) were already handed off in the review
  itself; restating them here for the controller's benefit since they were
  the direct cause of this fix pass's defect (RF4) and are the next-nearest
  gap in the same C# function (RF6): both are out of `sts2_rl/powers.py`'s
  footprint and need whoever owns `hooks.py`/`cards/base.py` next.

### Tests

**Command:**
```
py -m pytest test/test_r13_power1.py -v
```
**Result:** 11 passed (10 pre-existing + 1 new:
`test_exhausting_card_does_not_spend_a_rebound_stack`), 0 failed.

**Command:**
```
py -m pytest test/test_r13_power1.py test/test_underdocks_hive_events.py -q
```
**Result:** 97 passed (was 96), 0 failed.

**Command (the review's full sweep, re-run against the fix-pass tree):**
```
py -m pytest test/test_r13_power1.py test/test_underdocks_hive_events.py \
   test/test_powers.py test/test_ironclad_powers.py test/test_new_features.py \
   test/test_card_plays_started.py test/test_stack_type_single.py \
   test/test_previews.py test/test_relic_live_tail.py test/test_can_receive_powers.py \
   test/test_overgrowth_powers.py test/test_power_modifier_phases.py \
   test/test_power_type_for_amount.py test/test_relics.py \
   test/test_turn_start_snapshot.py test/test_turn_structure_gaps.py -q
```
**Result:** 769 passed (was 768), 0 failed. The `TestPowerInstanceType`
failures noted in the original report's "Environment note" and in the
review's re-run are gone (confirmed green, consistent with the review's
finding that they were a transient read of a concurrent agent's in-progress
`hooks.py` rewrite, not caused by this lane).

### Footprint discipline

Touched only `sts2_rl/powers.py` (the `ReboundPower.modify_card_play_result_pile`
guard and its class docstring) and `test/test_r13_power1.py` (one new test).
No edit to `hooks.py`, `combat.py`, `cmds.py`, or any `audit/**` path. No git
index mutation (`git status --porcelain` still shows `R3-report.md` as `??`,
same as the review found).
