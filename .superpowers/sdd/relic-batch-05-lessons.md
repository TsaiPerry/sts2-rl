# Relic content audits — batch 5 of 18

**Date:** 2026-07-26 · **Branch:** `audit-relic-b05` (based on `audit-relic` @ `4542c32f`)
**Probes:** `audit/tools/relic_probes_b05.py` (14 probes, committed, re-runnable)
**Companions:** [`content-relic-report.md`](content-relic-report.md) (the pilot),
[`content-relic-sweeps.md`](content-relic-sweeps.md) (the five pool-wide sweeps)

Batch 5 was the only batch with **no pre-diagnosed units** — no sweep flagged
any of the 15, so all 15 were audited cold. Two of the three live gaps found
here are invisible to every existing sweep, and one of those is a new
pool-wide shape (see "New shapes" below).

---

## Units audited (15)

| Unit | Rollup | Hooks | Guards |
|---|---|---|---|
| `electric_shrymp` | **gap** | 3 | 7 |
| `ember_tea` | **gap** | 5 | 5 |
| `empty_cage` | **gap** | 3 | 5 |
| `eternal_feather` | waiver | 2 | 4 |
| `fake_anchor` | **gap** | 3 | 5 |
| `fake_blood_vial` | **gap** | 3 | 5 |
| `fake_happy_flower` | waiver | 6 | 4 |
| `fake_lees_waffle` | waiver | 4 | 4 |
| `fake_mango` | **gap** | 4 | 3 |
| `fake_merchants_rug` | faithful | 1 | 3 |
| `fake_orichalcum` | **gap** | 5 | 4 |
| `fake_snecko_eye` | **gap** | 4 | 4 |
| `fake_strike_dummy` | **gap** | 3 | 4 |
| `fake_venerable_tea_set` | **gap** | 4 | 4 |
| `festive_popper` | **gap** | 2 | 6 |

**11 of 15 roll up to `gap`** (73%, in line with the pilot's 69%).
119 entries — 52 hooks + 67 guards — verdicted **75 faithful / 16 waiver /
3 deliberate-divergence / 25 gap**.

Gate results: `harness.py validate` → **66 records, 0 invalid**;
`citation_check.py audit/records/relic` → **496 citations, MISSING 0, OUT-OF-RANGE 0**;
`audit_status.py --kind relic` → **audited 61, invalid 0, stale 0**;
`pytest test/ -q` → **2476 passed, 31 xfailed** (unchanged — audits add no code,
and `git status` showed only the 15 records plus the new probe module).

**Obtainability is executed for all 15** (`relic_probes_b05.py b05-pool`):
`eternal_feather` (Uncommon) and `festive_popper` (Common) come from the
transcribed grab bag; nine knock-offs from the ported Fake Merchant event
(`events/fake_merchant.py`, 50 gold, acts 2–3); `fake_merchants_rug` from that
event's fight reward; `electric_shrymp` from Orobas; `ember_tea` from Tea
Master; `empty_cage` from Darv.

---

## LIVE gaps (3), each with its executed evidence

**1. `fake_venerable_tea_set` G1 — the relic does nothing in any run that buys
it.** `FakeVenerableTeaSet.cs:43-51` latches `GainEnergyInNextCombat` from
`AfterRoomEntered(RestSiteRoom)`; the port implements only the *spend* half and
expects the latch as a constructor argument (`fake_venerable_tea_set.py:25-27`),
which `RunState.add_relic` → `make_relic(id)` never supplies (`run.py:546-548`).
*Evidence (`relic_probes_b05.py tea-set-rest`):* `make_relic(...)._pending`
`False`; no `after_room_entered` override; firing the exact dispatch
`run.py:983` performs with `RoomType.REST_SITE` leaves `_pending=False`; the
next combat's turn-1 energy is **3 where C# gives 4**. Forcing `_pending=True`
gives 4, isolating the defect to the missing latch. The pipeline the port needs
already exists and the *sibling in this same batch* uses it —
`relics/eternal_feather.py:19-22` filters on `RoomType.REST_SITE` from
`after_room_entered`. **The fix is one method, copied from that sibling.**

**2. `fake_orichalcum` G1 — acquiring Cloak Clasp first silently switches the
relic off.** `FakeOrichalcum.cs:46-58` latches `Block == 0` in the
`BeforeSideTurnEndVeryEarly` pass — and the source carries a doc comment
(`FakeOrichalcum.cs:40-45`) saying that is *why* — so no plain-phase turn-end
listener can suppress the Block. The sim has no phase concept and tests
`player.block == 0` inline (`fake_orichalcum.py:26`).
*Evidence (`relic_probes_b05.py orichalcum-order`):* with a 5-card hand,
registration order `[cloak_clasp, fake_orichalcum]` ends the turn on **5** block
and `[fake_orichalcum, cloak_clasp]` on **8**, where C# always gives 8. Both
ported and co-holdable (Cloak Clasp is Rare in the grab bag; Fake Orichalcum is
Fake Merchant stock). This is `turn_structure` **G12** at a site that record
already names by name ("Fake Orichalcum and Ripple Basin are the same shape") —
executed here for the fake rather than inherited from the real Orichalcum.

**3. `electric_shrymp` G1 — the Imbued card auto-plays 47% of the time instead
of always.** `Imbued.cs:20-26` calls `CardCmd.AutoPlay` unconditionally on turn
≤ 1 regardless of pile, and `Imbued.cs:11`'s `ShouldStartAtBottomOfDrawPile`
puts the card at the bottom of the draw pile before the turn-1 draw
(`CombatManager.cs:657-672`). The sim's port requires `self.card in player.hand`
(`enchantments.py:261-267`) and never bottoms the card.
*Evidence (`relic_probes_b05.py shrymp-imbued`):* over 200 seeds the card
auto-plays on turn 1 in **94** (47%) and not at all in the other 106; C# plays
it in all 200. **Electric Shrymp is the only ported grantor of Imbued**, so it
is the reachability witness for `turn_structure` **G14**. The relic's own two
files are faithful — the divergence lives in `enchantments.py`, which the
event+enchantment stream owns.

---

## DORMANT gaps, each naming the concrete unported thing

| Unit | Gap | What would make it live |
|---|---|---|
| `ember_tea` G1 | C#'s `AfterRoomEntered` runs strictly **before every** `BeforeCombatStart` listener (`CombatRoom.cs:224-228` vs `CombatManager.cs:403`); the sim's `on_combat_start` is interleaved in relic-acquisition order | a `BeforeCombatStart` effect that **reads** the player's Strength. Executed: 23 ported relics have `on_combat_start`, 6 mention Strength and all six only *apply* it (addition commutes); an AST scan of **every** `on_combat_start` body under `sts2_rl/` finds **zero** that read a power at all |
| `electric_shrymp` N3, `empty_cage` N2 | `run.select_cards` falls back to `self.rng.sample` where C# opens a choice screen and draws **no** RNG (bug class 16, out-of-combat) | a parity run reaching either relic with no `run.card_selector` installed; the conformance runner does install one from the replay's `SelectGridCard` commands |
| `fake_anchor` N3 | block granted at the step-14 `AfterBlockCleared` loop instead of step 3 (same mechanism as `anchor` N3) | a block-reading monster intent, or a `BeforeCombatStart` listener that reads Block — executed: **zero** ported relics' `on_combat_start` reads `.block` |
| `fake_blood_vial` G1 | the hook is `AfterPlayerTurnStart`**Late**; the sim has one flat pass (`hook_dispatch` G3 / `turn_structure` G12) | a turn-start pair where one member's amount depends on the other's result. The only ported turn-start effect that damages the player, `royal_poison`, sits in the same flat pass, so the HP total is the same either way |
| `fake_blood_vial` G2, `festive_popper` G1 | `AfterPlayerTurnStart` (step 22) mapped to the sim's step-23 slot (bug class 11) | for `festive_popper` specifically: an auto-played turn-1 card whose outcome depends on the 9 damage having landed — C#'s auto-pre-play is step **26**, strictly after both, while the sim's Imbued auto-play fires *earlier* in the same dispatch because cards register before relics (`hook_dispatch` G2 / `turn_structure` G8) |
| `fake_mango` N2 | `undo_after_obtained` is a no-op for a relic that raises **both** max HP and current HP (the `big_mushroom` defect from the other direction) | a conformance seed whose replay buys a knock-off at a node the runner resyncs relics at; neither convergeable Ironclad seed (89U21BV1TZ, 933T39V18D) reaches the Fake Merchant. DETECTOR 3's act-boundary HP assertion is what would report it |
| `fake_snecko_eye` `AfterObtained` | C# applies Confused immediately on a mid-combat pickup (`FakeSneckoEye.cs:23-29`) | ported content that grants a relic **inside** a fight — the same unported shape `belt_buckle`'s `AfterObtained` names |
| `fake_strike_dummy` G1 | C#'s fourth clause is an **OR** (`dealer == owner` **or** `cardSource.Owner == owner`), so in single-player it never declines; the sim requires `dealer is self.player` | a player-side minion swinging a player card, or any effect dealing a Strike card's **powered** damage with `dealer=None`. Executed: 8 ported cards carry `CardTag.Strike`; an AST scan of all **119** `DamageCmd.deal` sites finds **13** that pass a card without a dealer and every one is a non-Strike self-damage/HP-loss effect with unpowered props |
| `fake_strike_dummy` N3 | parallel additive aggregation vs C#'s running-value `decimal` fold (`hook_dispatch` G9 / `damage_pipeline` N3) | a listener whose return **depends** on the value it is handed; this relic returns a constant, so the two agree by construction |
| `festive_popper` G2 | `HittableEnemies` vs `living_enemies()` (same mechanism as `bag_of_marbles` G2) | a turn-1 untargetable enemy. Partial backstop `bag_of_marbles` lacks: `DamageCmd.deal` re-applies `should_allow_hitting` (`cmds.py:49-50`), so only the hit event and per-target side effects diverge, not the HP |
| `festive_popper` G3 | the port hand-rolls `_check_win()` where C# reaches `CheckWinCondition` only at step 27, after the auto-pre-play phase (`turn_structure` G13, which cites `festive_popper.py:21` by name) | a turn-1 listener whose effect matters after the last enemy dies. The compensating call means the relic does **not** exhibit G13's pinned failure (player death) — it damages enemies only |

---

## New shapes and bug classes

**One new pool-wide shape — "constructor-injected state that nothing
injects".** Reported here for the relic stream owner to fold into `PROMPT.md`;
not applied, per the concurrency contract.

> **Candidate bug class 19.** A port models out-of-combat state as a
> **constructor parameter with a default** rather than as the hook the source
> uses. `RunState.add_relic` builds every relic through `make_relic(id)` with no
> arguments (`run.py:546-548`), so the parameter can only ever hold its default
> and the relic is inert for the whole run. **This is invisible to sweep A**
> (`sweep-reset`), which diffs a field across two combats: a field that is never
> *written* looks identical on a carried and a fresh instance, so sweep A
> cleared `fake_venerable_tea_set` — the founding example, and a live gap.
> Executed census (`relic_probes_b05.py injected-state`): exactly **3 of 258**
> ported relics take a constructor argument at all, and `git grep` finds
> **nothing** under `sts2_rl/` constructing any of the three with arguments:
>
> | Relic | Param | Status |
> |---|---|---|
> | `fake_venerable_tea_set` | `rested` | **LIVE gap, recorded (this batch)** |
> | `venerable_tea_set` | `rested` | **identical defect, unaudited — its own batch** |
> | `girya` | `times_lifted` | needs a trace: the relic appends its own rest-site LIFT option (`girya.py`'s `modify_rest_site_options`), so the counter may be written through that path |
>
> The tell in the source is a docstring that says state is "injected via the
> constructor". Grep for it: it is a **claim about the sim** of exactly the kind
> bug class 12 says to check.

`relic/venerable_tea_set` and `relic/girya` are **not verdicted here** — no
record is written for an unaudited unit. They are pre-populated work for their
own batches, in the same way sweep A pre-populated `centennial_puzzle` and
`paels_eye`.

**A second, smaller lesson worth a line in `PROMPT.md` class 11.** The warning
"the sim's own mapping docstrings are evidence, not truth" fired again, and this
time in the *safe* direction: `relics/base.py:20-24` says Happy Flower's
carry-over turn counter is "per-combat / constructor-injected", and
`fake_happy_flower` has **no constructor argument at all** and correctly
persists its counter across combats (executed: a relic leaving combat 1 with
`turns_seen=4` fires on combat 2's first turn, matching C#'s `[SavedProperty]`).
A docstring can be wrong about a port that is right.

**Two questions the batch closed for other records, by execution:**

- **`beautiful_bracelet` G1 is answerable.** That record left "does the sim's
  `can_enchant` equal C#'s eligibility test?" flagged as an open question needing
  `Swift.cs` and `CardSelectCmd.cs`. `CardSelectCmd.cs:549` shows
  `FromDeckForEnchantment`'s filter is **exactly** `enchantment.CanEnchant(c)`
  with no extra pile-level clause — the Quest exclusion that record worried about
  belongs to `FromDeckForTransformation`, a different path. For Imbued the two
  predicates were then compared over all **203** ported cards with **0
  disagreements** (`relic_probes_b05.py shrymp-imbued`). The same method settles
  Swift in `beautiful_bracelet`'s own batch; this record does not edit it.
- **`fake_lees_waffle`'s decimal heal is exact.** C# truncates the *sum*
  (`Creature.cs:488-491`), the sim truncates the *amount*
  (`fake_lees_waffle.py:21`). Exhaustive execution over `max_hp` 1–399 × every
  current-HP value (~80,000 pairs): **0 mismatches**
  (`relic_probes_b05.py waffle-round`). Recorded because "10% of Max HP" looks
  like a rounding bug and is not.

**Bug classes that fired:** 1 (hook order at seams — `fake_anchor` N3,
`festive_popper` G1), 3/4/5 — no, 10/13 (reset timing — `ember_tea` N2,
`fake_happy_flower` N1, `fake_venerable_tea_set` N2, all three *cleared* by the
reader trace), 11 (`fake_blood_vial` G2, `festive_popper` G1), 12
(`fake_merchants_rug` — the rare stub whose premise is **true**;
`fake_venerable_tea_set` — a premise that is false), 15 (paired-hook guard
asymmetry — `fake_orichalcum` N1), 16 (`electric_shrymp` N3, `empty_cage` N2;
and **no unit in this batch overrides `IsAllowed`**, checked against sweep B),
18 (`fake_snecko_eye` N1 — a `TestMode.AssertOn` entry point the port correctly
**drops**, unlike `calling_bell` which ported the test arm).
**Classes 6, 7, 8, 9, 14 and 17 did not fire** — no monsters, no pile moves, no
deck-append, no per-Replay hook, no `.upgrade()` call and no card clone anywhere
in these 15 units.

---

## Cross-record consistency (binding rule 3)

Eight mechanisms already carried a verdict elsewhere. All eight are reproduced
with the **same** verdict, cited, and not re-derived:

| Mechanism | Prior record | Verdict here |
|---|---|---|
| `BeforeCombatStart` block granted from the turn-1 block clear | `relic/anchor` hook + N1/N2/N3 | `deliberate-divergence` + dormant `gap` (`fake_anchor`) |
| `HittableEnemies` vs `living_enemies()` | `relic/bag_of_marbles` G2 | `gap`, dormant (`festive_popper` G2) |
| multi-target `CreatureCmd.Damage` vs a per-enemy loop | `relic/bag_of_marbles` N2 | `faithful` (`festive_popper` N1) |
| turn-start hook collapsed onto the step-23 slot | `relic/bag_of_marbles` G1 | `gap`, dormant (`fake_blood_vial` G2, `festive_popper` G1) |
| missing `Early`/`Late`/`VeryEarly` phase passes | `hook_dispatch` G3 / `turn_structure` G12 | `gap` — **LIVE** (`fake_orichalcum` G1), dormant (`fake_blood_vial` G1) |
| the turn-1 `ShouldStartAtBottomOfDrawPile` pass | `turn_structure` G14 | `gap` — **LIVE** (`electric_shrymp` G1) |
| `CheckWinCondition` not run after turn-1 setup | `turn_structure` G13 | `gap`, dormant at this site (`festive_popper` G3) |
| pipeline-level `is_powered_attack` gate; parallel vs running-value aggregation | `damage_pipeline` G3 / `hook_dispatch` G9 + `damage_pipeline` N3 | `deliberate-divergence` at the relic's own dropped self-gate; `gap` dormant for the aggregation shape (`fake_strike_dummy` N1, N3) |
| mid-combat relic pickup with no sim path | `relic/belt_buckle` `AfterObtained` | `gap`, dormant (`fake_snecko_eye` `AfterObtained`) |

**No cross-record disagreement was found.** Two tensions worth naming, neither
a disagreement:

1. `turn_structure` **G12** says "Fake Orichalcum and Ripple Basin are the same
   shape" as Orichalcum but executed only the real Orichalcum. This batch
   executed the fake and confirms it — 5 vs 8 block. **Ripple Basin remains
   unexecuted** and belongs to its own batch.
2. `festive_popper` G3's compensating `_check_win()` is a *fix-ordering
   constraint* for the gap-fix stream: if `turn_structure` G13 is ever fixed by
   adding a real `CheckWinCondition` after turn-1 setup, the relic's inline call
   becomes a redundant early end and should be removed in the same change, or
   the relic will keep ending combats a phase too soon.

## Roster mis-resolutions

**None.** `harness.py roster relic` reports 258 sim units, 0 unmatched, and all
15 units resolved to a real C# file on the first try.
`audit/tools/name_overrides.json` needs no additions.

---

## Unverified / left out, stated plainly

- **`festive_popper` G1's C#-side auto-play ordering** is argued from
  `turn_structure` steps 22/23/26 and `hook_dispatch` G2, not executed on the
  C# side (nothing here runs the game). The *sim* side is executed.
- **`fake_mango` N2's dormancy** rests on neither convergeable Ironclad seed
  reaching the Fake Merchant. That is read off the event's gate
  (`events/fake_merchant.py:50-58`, acts 2–3 plus 100 gold or a Foul Potion) and
  the seed notes, **not** from replaying the seeds.
- **`empty_cage` N4** cannot see `CardSelectorPrefs.RequireManualConfirmation`'s
  value; the entry states why the outcome is the same either way rather than
  resolving the flag.
- **`girya`** is reported as a candidate for the new shape and deliberately not
  verdicted; its `times_lifted` may legitimately be written through the
  rest-site option the relic itself appends.
- **`relic/venerable_tea_set`** (the real one) almost certainly carries
  `fake_venerable_tea_set` G1 verbatim. Not verdicted — it is not this batch's
  unit.
- Ascension values, potions, multiplayer params and presentation are waived per
  the shared contract; every waiver in these 15 records is one of
  presentation/animation, multiplayer plumbing, meta-progression bookkeeping or
  dead C# test scaffolding. **No waiver in this batch rests on an
  unreachability claim.**

**Commit:** see `git log --oneline -1` on `audit-relic-b05` (recorded in the
handoff message; this file is written in the same commit as the records).
