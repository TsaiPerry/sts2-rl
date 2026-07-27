# Relic content audit — batch 18 lessons

**Date:** 2026-07-26 · **Branch:** `audit-relic-b18` (based on `audit-relic` @ 3a300d94)
**Units:** 2 — the roster's tail.
**Probes:** `tools/audit/relic_probes_b18.py` (8 probes, re-runnable, no engine code touched)

| Unit | Rollup | Hooks | Guards | LIVE | Dormant |
|---|---|---|---|---|---|
| `wongos_mystery_ticket` | **gap** | 7 | 14 | 1 | 2 |
| `yummy_cookie` | waiver | 3 | 9 | 0 | 0 |

`py tools/audit/harness.py validate` → 203 records, **0 invalid**.
`py tools/audit/citation_check.py audits/relic` → 2503 citations, **MISSING 0,
OUT-OF-RANGE 0** (one out-of-range was caught and fixed before commit:
`events/tezcatara.py:49` in a 48-line file).
`py tools/audit_status.py --kind relic` → `total 258 · audited 198 · invalid 0 ·
stale 0 · gaps 149 · unaudited 60`.
`py -m pytest test/ -q` → **2476 passed, 31 xfailed** — unchanged.

---

## The LIVE gap

**`wongos_mystery_ticket` G1 — a ripe ticket pays nothing on the final act's
boss, where the game pays its 3 relics.**

Both codebases special-case the run's last boss, at **different depths**:

- sim: `generate_combat_rewards` returns an empty `CombatRewards` at
  `rewards.py:440-441` (`if room_type == RoomType.BOSS and run.is_final_act`) —
  *above* the `modify_combat_rewards` dispatch at `rewards.py:499-500`, so **no
  relic's reward hook runs at all**.
- C#: `RewardsSet.WithRewardsFromRoom` returns early at `RewardsSet.cs:85-89`
  without adding gold/potion/card rewards, **but it has already set `Room`**, and
  the separate `GenerateWithoutOffering` (`RewardsSet.cs:125-146`) still runs
  `Hook.ModifyRewards(runState, player, Rewards, Room)` on the empty list. The
  ticket's guards all pass (`room is CombatRoom`; no act filter), so it appends 3
  `RelicReward`s, they Populate in the `Rewards.Except(second)` pass, and
  `Offer()` shows the screen (`Rewards.Count <= 0 && !flag` cannot fire — `flag`
  is `Room is CombatRoom`). The screen is reached for the final boss like any
  other win: `NCombatUi.OnCombatWon → ShowRewards → OfferRoomEndRewards`
  (`NCombatUi.cs:180-226`), gated only on `Encounter.ShouldGiveRewards`.

**Executed evidence** (`py tools/audit/relic_probes_b18.py b18-ticket-final`),
same relic state (5 combats finished) on a BOSS screen:

```
is_final_act=False  screen relics=['parrying_shield','game_piece','bellows']  run.relics 1->4  bag 96->93  gave_relic=True
is_final_act=True   screen relics=[]                                          run.relics 1->1  bag 96->96  gave_relic=False
```

The C# half is established by reading (`RewardsSet.cs`, `NCombatUi.cs`), not by
execution. Reachable with ported content: the relic is bought at the ported
Welcome to Wongo's mystery box (`events/welcome_to_wongos.py:82-83`),
`is_final_act` is really set (`run.py:676`, `run.py:750`) and reached by the
driver (`driver.py:296-298`), and the relic has **no act, room-type or floor
restriction** — any run whose 5th reward-giving combat after the purchase is the
last act's boss lands here.

**It is the only ported relic exposed to it.** The other four sim
`modify_combat_rewards` implementers cannot reach the case:
`black_star` (Elite only), `lava_rock` (act 0 only), `driftwood` and
`paels_wing` (both gate on `rewards.cards`, empty on that screen).

**Not a cross-record disagreement.** `audits/relic/lava_rock.json` guard N7
already noticed the structure and correctly called it harmless *at its own site*
("it means a future act-3 reward relic would never see the hook"). Batch 18 is
that relic arriving. Rule 3 is satisfied: one mechanism, one verdict, and the
verdict is now attached to the site where it is observable.

**Fix note for the gap-fix stream.** The fix is *not* to delete the early
return — the final boss legitimately has no gold/card/potion reward. It is to
split `rewards.py:440-441` so the relic hook loop (and only it) still runs, which
is exactly what C# does by putting the guard in `WithRewardsFromRoom` and the
dispatch in `GenerateWithoutOffering`.

## Dormant gaps, with the concrete thing that would make each live

| Unit | Gap | What would make it live |
|---|---|---|
| `wongos_mystery_ticket` N5 | the sim's single `modify_combat_rewards` collapses C#'s `TryModifyRewards` / `TryModifyRewardsLate` two-pass dispatch (`Hook.cs:1981-1998`) | porting any `TryModifyRewardsLate` implementer that reads or rewrites `rewards.relics`; today the only ported Late implementer is `driftwood` and its domain is disjoint. Same mechanism as `lava_rock` N4 / `lasting_candy` G4 (rule 3) |
| `wongos_mystery_ticket` N6 | an exhausted grab bag makes the sim hand out fewer than 3 relics and still spend the ticket, where `PullNextRelicFromFront` pads with `RelicFactory.FallbackRelic` (`RelicFactory.cs:45-50`) | draining the 96-relic bag — executed: bag=2 pays 2 where C# pays 3, bag=0 pays 0 and `gave_relic` latches anyway |

## Both of this batch's sweep pre-diagnoses were STALE — in opposite directions

The batch-18 brief pre-diagnosed both units from sweep output that has since been
corrected. **Neither pre-diagnosis matches the sweeps as they stand today.** No
edit was made to the sweep document (it is read-only to this batch); reported
here for the stream owner.

1. **`wongos_mystery_ticket`** — the brief says "Sweep A candidate
   (`combats_finished`, `gave_relic`; **C# resets at `AfterCombatEnd`**)". That
   parenthetical is the *old override-census* reading. The rewritten sweep prints
   the actual assignments and reports
   `wongos_mystery_ticket ['combats_finished','gave_relic'] … C# resets: NONE
   (may be per-run by design)` — correct, because `CombatsFinished++` is not an
   assignment. So sweep A's **defect 3 is genuinely fixed**, and the *prompt*
   still carries the pre-fix text.

   Settled on the merits anyway, because "C# resets: NONE (may be per-run by
   design)" is explicitly not proof: both fields are `[SavedProperty]`
   (`WongosMysteryTicket.cs:38-51`, `:53-70`), i.e. per-run by definition.
   Executed (`b18-ticket-persist`): the carried instance climbs 1→5 while a fresh
   one stays 0, and only the carried one pays out; a ticket reset every combat
   pays **0 relics after 20 combats** — the reset the stale column implies would
   make the relic dead code. Verdict `faithful`, matching `fishing_rod` N1 and
   `lava_rock` N5.

   **Worth knowing about sweep A's coverage:** `wongos_mystery_ticket` appears in
   the *static* "NOT RESET BEFORE A READER" bucket but **nowhere in
   `sweep-reset-exec` output** — not in CONFIRMED, not in INCONCLUSIVE, not in
   NO-DELTA. A unit that is silently outside the executed pass's candidate set is
   even easier to read as clean than an `INCONCLUSIVE` one, because it produces
   no line at all. If the exec driver's candidate selection is ever documented,
   the count of statically-flagged units it *skips* belongs next to the
   INCONCLUSIVE count.

2. **`yummy_cookie`** — the brief says it is in "sweep D's unguarded-upgrade
   list". The **current** sweep D output lists it under `guarded (for contrast)`
   alongside `pomander`, `fishing_rod` and twelve others, and sweep D's own
   published correction footnote names `yummy_cookie` as one of the five sites its
   first 3-line-window version over-reported. So this pre-diagnosis is stale in
   the *harmless* direction (it sent a batch to look at a clean unit) rather than
   the dangerous one.

   Confirmed on the merits anyway (`b18-cookie`): `run.upgradable_cards()`
   (`run.py:368-369`) filters on `Card.is_upgradable`
   (`cards/base.py:167-170` = `CurrentUpgradeLevel < MaxUpgradeLevel`), matching
   where the source filters (`CardSelectCmd.cs:442`). A deck carrying
   `curse_of_the_bell` and `dazed` offers neither and leaves both at level 0; a
   Strike already at 1/1 is excluded and unchanged.

**Generalisation for `PROMPT.md`'s existing item 1:** a sweep's output is not
authority *and neither is a batch prompt that quotes it*. Both of this batch's
pre-diagnoses were quotations of pre-correction output frozen into the prompt
text. Batch prompts should cite the sweep *command* rather than paraphrase its
findings, or they become the last surviving copy of a defect the sweep itself has
fixed.

## Candidate new bug class — the guard everyone checks protects the wrong thing

**Class 14 (unguarded `Card.upgrade()`) has a sibling nobody checks: a filtered
candidate list does not protect against a *repeated* candidate.**

Exhibited by `yummy_cookie` (guard N7, executed): with a `card_selector` that
returns `[target] * count`, a Strike whose `max_upgrade_level` is 1 comes out at
`upgrade_level 4`. Two independent things have to be missing for this:
`run.select_cards` (`run.py:371-390`) truncates to `count` but does **not
de-duplicate**, and `Card.upgrade()` (`cards/base.py:146-148`) does **not clamp**.
C# cannot reach the state: `FromDeckForUpgrade` returns either the filtered list
itself or a distinct set from the selection screen, and `CardCmd.Upgrade`
re-checks `IsUpgradable` **per card** (`CardCmd.cs:273-276`) — so the guard sits
on the *mutation* in C# and only on the *candidate list* in the sim.

**Recorded as `faithful`, not as a dormant gap, and the distinction is the
point.** Rule 6 requires proving reachability rather than asserting it, and both
shipped selectors pick distinct cards — `RunDriver._card_selector` pops each
choice out of `remaining` (`driver.py:246-267`) and `scripted_card_selector`
slices a sorted `enumerate` (`selectors.py:57-83`); the no-selector fallback is
`rng.sample`, without replacement. What would make it live is a **new selector
implementation, not new content**, which is a category the dormant/live axis does
not have a slot for.

Two things make it worth a checklist line rather than a footnote:

- **It is silent for `upgrade` and loud for `remove`.** `run.remove_cards`
  (`run.py:356-358`) calls `list.remove` and raises on a duplicate; an extra
  `upgrade()` just exceeds the max with no error. So the 15 relics sweep D lists
  as "guarded" are guarded against the wrong failure, and the `upgrade`-purpose
  ones are the ones that would fail quietly.
- **It scales with `count`.** All the other relic upgrade sites select 1 card,
  where a duplicate is impossible. `yummy_cookie`'s `CARDS = 4` is the largest
  `select_cards("upgrade", …)` in the relic pool, so it is the site where the
  precondition first has teeth. `run.select_cards` is shared with the card and
  event streams (`events/trial.py:77` selects 2 for upgrade), so a one-line
  `dict.fromkeys` de-dupe in `select_cards` would close it everywhere at once.

## Nothing else surfaced

- **No cross-record disagreement under rule 3.** Six mechanisms already carried a
  verdict and all six are reproduced with the same one, cited, not re-derived:
  the relic-offer auto-keep (`calling_bell` G3 / `lava_rock` N1 →
  deliberate-divergence), `PullNextRelicFromFront`'s single Rewards-stream rarity
  roll (`lava_rock` N2 → faithful, executed here as a counter delta of exactly 3),
  the Populate ordering (`lava_rock` N3), the `TryModifyRewards(Late)` collapse
  (`lava_rock` N4 / `lasting_candy` G4 → dormant gap), the `[SavedProperty]`
  per-run counter (`fishing_rod` N1 / `lava_rock` N5), the victory-only
  `after_combat_end` dispatch (`fishing_rod` N3 / `turn_structure` G10), the
  class-14 candidate filter (`pomander` N1 / `fishing_rod` N2) and
  `CardCmd.Upgrade`'s history bookkeeping (`neows_talisman` N3 → waiver).
- **No roster mis-resolution.** Both units resolved to a real C# file on the
  first `skeleton` call; `tools/audit/name_overrides.json` needs no addition.
- **Nothing wrong found in `PROMPT.md` v6 or in `audits/seam/**`.** v6's item 3
  (`undo_after_obtained` absence = faithful) applied cleanly to `yummy_cookie` N8
  and its "distinct mechanism, still a gap" carve-out correctly does not apply
  (there is no implementer here to clamp).
- **Bug classes that fired:** 13 and 24 (`wongos_mystery_ticket` N1/N8 — the
  port's own docstring says the payout is on "the next combat's reward screen"
  when both codebases pay on the 5th combat's own screen; trusting it would have
  filed a false one-combat-late gap), 19 (the C# body uses a literal `5` rather
  than its own `combatsToActivate` const), 25 (`AfterModifyingRewards` is a
  genuine second full pass — checked and harmless, it only sets a flag on the
  relic itself), 14 and 29 (`yummy_cookie` N1/`HasUponPickupEffect` — `pomander`
  correctly *omits* the declaration this relic correctly *makes*), 16 (checked
  `Rng.Chaotic` in `IconBaseName`: it is wall-clock-seeded, `Rng.cs:22`, so it is
  not part of run determinism at all). **Class 20 is the near-miss worth naming:**
  G1 is not a wrong slot or a wrong branch but a *dispatch site the sim moved
  above a guard*, which is closest to class 26 (a control-flow predicate moved
  earlier drops the hooks between the two positions) applied to a run-level hook
  instead of a turn-end one.

## Refutation pass on `content-relic-sweeps.md`'s confirmed-carriers table

A two-unit batch has spare capacity, and the highest-value use of it is **not**
more depth on two already-deep records — it is attacking findings nothing
downstream re-checks. So the four boldest LIVE rows of sweep A's CONFIRMED table
were re-derived from the C# and re-executed with **independently written** probes
(`b18-refute-*`), each trying to make the claim fail. None of these units belongs
to batch 18 and **no record of theirs was edited.**

**Result: 4 re-tested, 0 refuted, 0 overstated.** Each unit's own record already
names the observable the probe reproduces.

| Claim (source) | Re-tested outcome |
|---|---|
| `red_skull` — "combat 2 at full HP opens **Strength −3**" (batch 13) | **Reproduces, both branches.** Carried instance, hp 30/80 → `[('strength', 3)]`; same instance at 80/80 in combat 2 → `[('strength', -3)]`, `_applied` False; a fresh instance there → `[]`. And the *other* branch, which the published sweep row is actually showing: still at 30/80 in combat 2, carried → `[]` vs fresh → `[('strength', 3)]`, i.e. the relic silently grants nothing. `red_skull.json` G1 already states both as (a) and (b) — accurate as written. |
| `ruined_helmet` — "Strength 4 then 2 across two combats" (batch 13) | **Reproduces exactly.** Combat 1: first +2 → 4, second +2 → 6 (matching C#). Combat 2 same instance: first +2 → **2** where C# gives 4; fresh instance there → 4. |
| `permafrost` — "block 0 carried vs 7 fresh" (batch 12) | **Reproduces, and persists.** Carried instance: combat 1 → 7 Block, combat 2 → 0, combat 3 → 0; fresh instance in combat 2 → 7. Consistent with the record's "first combat of a run only". |
| `diamond_diadem` — "stale 3 read at combat-2 turn 1" (batch 4, turn-END-only reset) | **Reproduces, and so does the second fact it depends on.** (a) 3 cards played, kill the last enemy mid-turn, then `end_turn()`: `phase=COMBAT_OVER`, `is_over=True`, counter **still 3** — the turn-end reset really is skipped by the winning turn. (b) combat 2 turn 1 opens at counter 3, and a spy relic sitting after the diadem in the turn-end pass sees `(none)` where the fresh instance's pass sees `diamond_diadem` — the grant is denied. |

**Method note worth keeping** (it cost the pass one wrong reading before it was
caught): `DiamondDiademPower` is removed once the *enemy* side's turn ends, and
`CombatState.end_turn` runs the whole enemy turn — so sampling
`player.powers` after `end_turn()` returns shows the power gone **even when it was
granted**, and the first version of the probe therefore reported "fresh instance
also got nothing", which would have looked like a refutation. The fix is a spy
`Relic` placed *after* the unit in the relic list, observing the same turn-end
pass one dispatch later. Any future probe for an until-end-of-enemy-turn power
needs the same trick; sampling after the fact silently reports absence.
