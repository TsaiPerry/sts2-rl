# Continuing `audit/GAP-QUEUE.md` after the Tier 1 campaign

Paste this whole file as the opening prompt of a fresh session.

---

## Where the work stands

**Tier 1 — every mechanism with a LIVE site on ported content — was fixed on
2026-07-27/28.** Read `docs/superpowers/plans/2026-07-27-tier1-gap-fixes.md`
first; it has the wave plan, the outcome, and the traps that cost the most time.

Measured, and reproducible right now:

```
py -m pytest test/ -q                    2 failed, 2857 passed, 13 xfailed
py audit/tools/gap_queue.py counts       1160 entries / 749 mechanisms / 5 pinned
py audit/tools/gap_queue.py pins         6 strict xfails, ALL Tier 2 (dormant)
py audit/tools/audit_status.py           846 records, 0 invalid, 0 stale
py audit/tools/harness.py validate       846 record(s), 0 invalid
py audit/tools/gap_queue.py cite-check   0 problem(s)
```

The 2 failures are pre-existing and environmental — a missing
`RunReplays/RunReplays/Resources/933T39V18D/floor_49/actions.sts2replay`
fixture. They were failing before the campaign and are not sim defects. **Do not
"fix" them**; treat 2857 passed / those same 2 failures as the floor.

Before the campaign: 2518 passed, 36 pins, 1612 entries, 856 mechanisms, 319
with a live entry.

**Nothing is committed.** ~994 files are staged. Perry commits — never run
`git commit`, `push`, `checkout`, `stash`, `reset` or `restore` (CLAUDE.md §4).

---

## Task 0 — reconcile the ledger with the code. Do this FIRST.

**The audit ledger is one pass behind the engine, and the queue's own numbers
are therefore wrong in the optimistic direction.** The per-record verdict
re-derivation ran *concurrently with* the last round of code fixes, so several
mechanisms are closed in code and still recorded `gap`. Two confirmed:

| mechanism | ledger | code |
|---|---|---|
| `potion/_use_pipeline` (51 sites) | `gap`, LIVE | closed — `combat.py:736` dispatches `before_potion_used`, `:739` calls `_check_for_empty_hand()` |
| `event/EV-1` (17 sites) | `gap`, LIVE | closed — `run.py:333-334` runs the `should_die` / `after_preventing_death` pass |

`py audit/tools/gap_queue.py mechanisms | head -40` lists the current
largest-first order; walk it and check each LIVE mechanism against today's code
before believing it. Others to check specifically, because they were fixed
*after* the re-derivation started:

- `relic/fake_orichalcum` — split into `on_player_turn_end_very_early` +
  `on_player_turn_end`, mirroring Orichalcum (`FakeOrichalcum.cs:46/60`).
- `power/diamond_diadem` — regained its `is_powered_attack` gate
  (`DiamondDiademPower.cs:27-30`).
- `power/buffer` — moved to `modify_hp_lost_late` (`BufferPower.cs:20` is
  `ModifyHpLostAfterOstyLate`).
- `enchantment/swift` — moved onto the real `on_play` slot (`Swift.cs:15`).
- `enchantment/imbued` — moved onto `after_auto_pre_play_phase_entered` and lost
  the extra `card in player.hand` clause C# does not have.
- `card/howl_from_beyond`, `relic/whispering_earring` — moved onto the
  AutoPost/AutoPre phases.
- `CardPileCmd._enter_combat` now registers `card.enchantment` (it did not, which
  was a hard crash — see below).

**The rule that governs this whole task, and the reason it exists:** a verdict
flips ONLY on evidence you gathered yourself from today's code. Not because a
plan says it was fixed, not because a test name sounds right. When the campaign
re-derived ~470 verdicts, an adversarial audit pass caught **18 false clears**
across five of eight kinds. All 18 were real and were reverted. Budget for that
ratio.

Finish with, **in this order**:

```
py audit/tools/harness.py validate            # 0 invalid
py audit/tools/harness.py rehash --all        # ONLY after every verdict is settled
py audit/tools/gap_queue.py counts            # then update GAP-QUEUE.md's Summary
py audit/tools/gap_queue.py cite-check        # must exit 0
```

Rehashing before the verdicts are settled re-pins stale `gap`s as freshly
verified — the exact false clear the pipeline exists to prevent.

---

## The remaining work, largest first

`GAP-QUEUE.md` now opens with a banner saying Tier 1 is closed. **Sections 1A–1F
are history, not a work list** — their prose was not rewritten entry by entry, so
present-tense claims in them describe the pre-fix sim. Tier 2 and Tier 3 are
untouched and are the real backlog.

### A. Tier 1 partials — named, bounded, and the highest-value thing left

Each of these carries a narrowed `issue` in its record saying exactly what
remains:

- **`relic/_auto_keep`** — the driver now issues real take-or-skip decisions, but
  not all 15 grant sites are rerouted. `rewards.py:474-479` and `:515-519` still
  force-grant by the old house rule and have **no owning record anywhere**.
  Keep `neows_bones`, `claws` and `glass_eye`'s transform half as
  `deliberate-divergence` — they are correct.
- **`relic/_stub`** — 13 of 21 implemented. Five stay no-ops with real reasons now
  in their docstrings: `prayer_wheel` + `white_star` need a second pick-1-of-N
  reward group `rewards.CombatRewards` cannot represent; `cauldron` needs a
  run-level declinable offer; `punch_dagger` + `royal_stamp` need the Momentum /
  Royally Approved **enchantments**, which `enchantments.py` does not register.
- **`potion/_min_select_zero`** — `CombatState.select_cards` gained `min_select`
  but **no caller passes it** (`potions.py:1348` does not), and
  `scripted_card_selector` does not handle the `"choose_a_card"` purpose, so it
  returns `candidates[0]`. The machinery landed without its consumers.
- **`potion/foul_potion`** — the shop arm is ported; the Fake Merchant arm
  (`FoulPotion.cs:89-108`) still *discards* the potion instead of using it, so no
  `OnUseWrapper` and no `AfterPotionUsed`.
- **`power/_side_turn_slot`** — 13 sites still LIVE. The `AfterSideTurnEnd`
  residue is `TemporaryStrengthPower` / `TemporaryDexterityPower`
  (`powers.py:929`, `:1003`), which feed dark_shackles, feeding_frenzy,
  flex_potion, mangle, reptile_trinket, setup_strike, shackling_potion,
  speed_potion. The `AfterSideTurnStart` leg (plating, rampart, crimson_mantle,
  inferno) is a *different* leg and needs a side-scoped turn-start slot the sim
  does not have.
- **`hook_dispatch/G3`** — the phase machinery exists and works, but nine relic
  sites still need re-homing onto `_very_early` / `_early` / `_late`
  (choices_paradox, fiddle, mercury_hourglass, mr_struggles, pendulum,
  petrified_toad, tungsten_rod, …).

### B. The 6 remaining pins — all Tier 2, all with a ready-made failing test

```
power_cmd/G1               test_artifact_blocks_negative_signed_debuff
hook_dispatch/G8   (x2)    test_select_cards_refuses_once_the_combat_is_over
                           test_no_listener_runs_after_the_combat_starts_ending
monster_state_machine/G3   test_move_state_accepts_a_string_follow_up_id
monster_state_machine/G7   test_max_times_zero_disables_the_branch_instead_of_raising
monster_state_machine/G8   test_duplicate_state_id_is_rejected_at_machine_construction
```

Each xfail's `reason` text is long, precise, and effectively specifies the fix.
`hook_dispatch/G8` is the big one — 20 sites, no `IsEnding` / `IsOverOrEnding`
dispatch gate anywhere. A `strict=True` xfail that starts passing FAILS the
suite, so deleting the marker is part of the fix, not an afterthought.

### C. Tier 2 dormant families, by size

`potion/_effect_bracket` (51 — no `BeginCardOrPotionEffect` /
`EndCardOrPotionEffect` re-entrancy bracket), `card/_unplayable_cost` (29 —
canonical cost −1 in C#, 0 in the sim), `card/_printed_vars` (23),
`power/_stack_type_single` (16 — `PowerStackType.Single` misread as "do not
stack"), `power_cmd/G5` (13 — no `PowerInstanceType`).

### D. Tier 3 — the long tail

~700 single-site, single-unit mechanisms. Cheaper to read straight out of the
record than to restate; the queue rows give id, liveness and the lead clause.

---

## Things that will bite you, learned the hard way

1. **Substring scans match prose.** A sweep that checked whether each modifier
   implementer self-gated found `is_powered_attack` inside a *comment* and
   cleared `DiamondDiademPower`, which had no gate at all — shipping a real
   regression (unpowered damage halved). Strip comments before scanning code.
2. **The tripwire finds what the queue does not.**
   `py -m pytest test/test_rng_tripwire.py -q` is a fuzz gate that fails on ANY
   in-combat draw from the legacy shared rng, with an exact `file:line`. It
   caught two latent wrong-stream bugs the fixes *unmasked* — `StampedePower`
   (`StampedePower.cs:28` names `Rng.Shuffle`) and `HavocCard`
   (`CardCmd.cs:77` names `Rng.CombatTargets`). Both were invisible until a fix
   made the code path actually execute. Run it after any change to a code path
   that draws.
3. **Fixing one thing exposes the next.** Making a prevented death leave the
   creature dead at 0 HP (the C# shape) broke three revives that silently relied
   on the old 1-HP floor — Illusion, Adaptable/Test Subject, Lizard Tail — plus
   `CreatureCmd.heal`, which had a dead-creature guard C# does not have. Expect a
   cluster, not a single edit.
4. **A pin can be wrong.** Three were, and were corrected rather than worked
   around: `test_extra_turn_still_runs_the_turn_end_pipeline` expected
   `should_take_extra_turn` first when `CombatManager.cs:1364` evaluates it
   *after* both end-turn phases; `monster_state_machine/G5`'s assertion
   contradicted its own comment; `/G6`'s was unsatisfiable as written. When a pin
   and the C# disagree, the C# wins — and say so loudly.
5. **Legacy tests encode the old, wrong semantics.** Several assert pre-fix
   numbers (Lizard Tail healing to 41 rather than 40, a doubled attack being one
   history entry rather than two). Update them with a comment citing the C#.
   Never delete one, never `xfail` it away.
6. **Machinery without consumers is not a fix.** `select_cards` gained
   `min_select` that nothing passes; the AutoPre/AutoPost phases were built and
   only 2 of 5 implementers were moved onto them. Land the consumers with the
   surface, and grep for the old call shape afterwards.
7. **Dual-mode ports have two verdicts.** Many units branch on
   `combat_rng.is_parity`; the parity arm is often faithful while the **legacy**
   arm — the default, and the RL training path — diverges. Audit both.
8. **`py audit/tools/citation_check.py`** reports ~19 MISSING and ~59
   OUT-OF-RANGE citations, all pre-existing, mostly one batch that transcribed
   offsets from a concatenated listing. It has never failed the build. Worth a
   cleanup pass; not urgent.

## Ground rules

- **The decompiled C# at `c:\Users\Perry\Desktop\Slay the Spire 2` is the source
  of truth**, not the queue's paraphrase and not the sim's docstrings. Several
  docstrings assert the opposite of what the code does — the campaign found five
  such false docstrings, and `PlayerCombatState.add_potion`'s still cites a
  deleted out-of-scope clause. Use NON-ASCENSION values.
- Surgical changes only; every changed line traces to a named entry.
- Test-driven: failing test first, watch it fail, then fix.
- Stage freely, commit never.

---

# Outcome — 2026-07-28

## Measured

```
py -m pytest test/ -q               25 failed, 2840 passed, 25 deselected, 7 xfailed
py -m pytest test/test_hook_order.py -q          51 passed, 0 xfailed   (was 45 / 6)
py audit/tools/gap_queue.py counts   1117 entries / 722 mechanisms / 0 pinned
py audit/tools/gap_queue.py pins     0 strict xfails
py audit/tools/audit_status.py       846 records, 0 invalid, 0 stale
py audit/tools/harness.py validate   846 record(s), 0 invalid
py audit/tools/gap_queue.py cite-check   0 problem(s)          exit 0
py audit/tools/gap_queue.py coverage     0 missing / 0 unlisted exit 0
```

**The suite floor moved, and not because of this work.** A character-porting
refactor (`sts2_rl/characters.py` + ~40 files) landed uncommitted in the same
working tree mid-session and is paused, not finished. Of the 25 failures, 2 are
the pre-existing missing `933T39V18D/floor_49` fixture and **23 are that
refactor** — every failing frame is in `curriculum_env.py:305`,
`cards/pool.py:80`, `potion_pools.py:169` or `dusty_tome.candidates()`, none in a
file this pass touched. The arithmetic closes exactly: 2857 (baseline) − 23 +
6 (pins now passing) = 2840. `test/test_characters.py` is that refactor's own new
file and is deselected above.

## Task 0 — the ledger reconciliation

All 207 then-LIVE mechanisms (368 entries) re-derived against today's code by 24
read-only agents; every proposed clear attacked by two adversarial lenses.

| | |
|---|---|
| entries re-derived | 368 |
| still a real gap | 316 |
| proposed clears | 52 |
| applied (18 faithful + 26 narrowed) | 44 |
| **refuted, kept as gaps with corrected text** | **8** |

The prompt's two named examples were already closed and were confirmed; so were
`relic/fake_orichalcum`, `power/corruption`, `enchantment/imbued` and 7 of 9
`enchantment/EG2` sites. **The 8 refutations were all real**, at roughly the
prompt's predicted ratio.

## The regression this pass introduced, and how it was caught

`test_no_listener_runs_after_the_combat_starts_ending` **was a wrong pin**, and
following it caused a real defect. It asserted that `Hook.AfterCardPlayed`
reaches nobody once the killing blow lands. The C# says the opposite:
`Hook.AfterCardPlayed` (`Hook.cs:278-294`) iterates `IterateHookListeners()`
**directly**, and `Hook.cs:275-276` says why — *"Dispatched directly, not through
the IterateCombatHookListeners guard: it completes resolution of the card that
caused the kill."* Its only gate is `IsInProgress` (`CardModel.cs:1957`), still
true between the blow and the teardown.

Gating that site on the new `is_over_or_ending` suppressed **every**
`AfterCardPlayed` listener on the winning card play — including Game Piece's
`DrawCmd.draw`, which can force a reshuffle and consume RNG, so it was
stream-observable for the conformance exporter. The adversarial verification pass
caught it, both sides were re-read at source, the change was reverted, and the pin
was rewritten as `test_after_card_played_still_fires_on_the_killing_blow`.
**Fourth wrong pin on this project; the rule held.**

## Closed

- **All six strict-xfail pins.** `power_cmd/G1` (`Power.type_for_amount` ports
  `GetTypeForAmount`, so Artifact is sign-aware); `monster_state_machine/G3`
  (`MoveState.follow_up_id`), `/G7` (`max_times == 0` disables the branch rather
  than raising), `/G8` (`register_states` rejects a colliding id);
  `hook_dispatch/G8`'s CardSelectCmd half (`CombatState.is_over_or_ending` +
  `select_cards`).
- **`hook_dispatch/G3` re-homes**: Fiddle → `modify_hand_draw_late`, Petrified
  Toad → `on_combat_start_late`, The Boot → `modify_hp_lost_late`.
- **`HookSystem._each` structure**: each phase pass now re-enumerates
  (`hook_dispatch/step30`), and a `_live` id set gives the lazy `Contains`
  re-check of `CombatState.cs:482-488` (`hook_dispatch/step11`, a `G7` site).
- **The `coverage` hole.** `gap_queue.py coverage` had been exiting 1 since the
  Tier 1 campaign — 25 mechanisms the re-derivation split out and the queue never
  named. New §3G names them all; `coverage` exits 0. **The campaign ran
  `cite-check` and not `coverage`; run both.**

## NOT done — the remaining backlog, unchanged

- **§A remainder.** `relic/_auto_keep`, `relic/_stub`, `potion/_min_select_zero`
  (`select_cards` has `min_select` and still **no caller passes it**;
  `scripted_card_selector` handles the three MinSelect-0 purposes but not
  `"choose_a_card"`), `potion/foul_potion`'s Fake Merchant arm, and
  `power/_side_turn_slot`.
- **The turn-start split**, which is the biggest single remaining Tier 1 item and
  is now precisely scoped: `AfterPlayerTurnStart` (`CombatManager.cs:675`) and
  `AfterSideTurnStart` (`CombatManager.cs:522`) are **two different C# hooks**
  collapsed onto one `on_player_turn_started` — 9 relics on the first and 14 on
  the second share one flat pass, and the phase machinery cannot help because
  these are not two suffixes of one hook. It needs a real side-scoped turn-start
  dispatcher, which is also what `power/_side_turn_slot`'s `AfterSideTurnStart`
  leg (plating, rampart, crimson_mantle, inferno) is waiting on. Executed
  witnesses: `relic_probes_b09.py b09-simple` and `relic_probes_b12.py
  b12-pendulum`.
- **`hook_dispatch/G8` proper.** 19 of 20 sites open. Census done: **72 of
  Hook.cs's 146 dispatchers go through `IterateCombatHookListeners`; 73 bypass it
  deliberately** (the kill/death/combat-end sequence). The gate belongs in
  `HookSystem._each` scoped to exactly those 72 — and the sim↔C# hook-name map is
  the real work, since the sim renames most hooks (`on_card_drawn` ←
  `AfterCardDrawn`, `on_player_turn_start` ← `AfterSideTurnStart`, …). Also open
  and newly found: `Hook.BeforeCardPlayed` **is** gated in C# and is not gated in
  the sim — the inverse mismatch.
- **§C Tier 2 families** and **§D Tier 3** entirely.

## For whoever picks this up

`rehash --all` was run with the character refactor in the tree, on its author's
explicit instruction that records staled by it can still be trusted. It is
paused, not finished — when it resumes, staleness re-fires, which is the detector
working.

---

# Outcome, round 2 — 2026-07-28 (after the character port landed)

The character port was committed as `650c3202`, which cleared the 23 refactor
failures and re-staled 108 records. This round worked **all of §A** — the Tier 1
partials the reconciliation left standing.

## Measured

```
py -m pytest test/ -q                    2 failed, 2910 passed, 7 xfailed
   (both failures are the known missing RunReplays/933T39V18D/floor_49 fixture)
py audit/tools/harness.py validate       846 record(s), 0 invalid
py audit/tools/harness.py rehash --all   846 record(s), re-pinned 585
py audit/tools/audit_status.py           0 invalid, 0 stale
py audit/tools/gap_queue.py counts       1097 entries / 720 mechanisms / 174 live
py audit/tools/gap_queue.py cite-check   0 problem(s)                exit 0
py audit/tools/gap_queue.py coverage     0 missing / 0 unlocatable   exit 0
```

Entries 1117 → **1097**, mechanisms 722 → **720**, mechanisms with a live entry
179 → **174**, suite 2857 → **2910** passing.

## What closed

- **`relic/_auto_keep`** — `Hook.ModifyRewards`' two passes factored into
  `rewards.apply_reward_modifiers` and dispatched from *every* screen generator,
  matching its single C# caller `RewardsSet.GenerateWithoutOffering`
  (`RewardsSet.cs:136`). New `CombatRewards.room` (= `RewardsSet.Room`, `None` on
  a custom set) is what keeps the room-gated relics off a rest-site screen while
  Driftwood and Pael's Wing reach it. `Event.pending_rewards` was dead state;
  `RunDriver._run_event` now offers it where the `await` sits.
- **`relic/_stub`** — `CombatRewards` models a **list** of `CardReward`s, each
  its own screen with its own odds / reroll / alternatives. **Prayer Wheel** and
  **Lasting Candy** implemented on top of it; Lasting Candy is the game's only
  EARLY `TryModifyCardRewardOptions` implementer, so both passes now carry a
  `CardCreationOptions` (pool + source + odds).
- **`relic/calling_bell`** — the port had implemented `GenerateRewards`'
  `TestMode.IsOn` branch. Now the shipping arm: Common / Uncommon / Rare pulled
  from the bag, all populated before any is offered.
- **`relic/wongos_mystery_ticket`** — the final-act-boss early return skipped the
  hook passes; C# skips only the room's own rewards.
- **`power/_side_turn_slot`** — the temporary Strength/Dexterity revert moved to
  the `AfterTurnEnd` pass.
- **`potion/_min_select_zero`** — `min_select=0` actually passed at all three
  `CardSelectorPrefs(prompt, 0, 999999999)` screens, plus a new
  `choose_a_card_optional` purpose (skippability is per-SCREEN in the source).

## Narrowed, not closed — and why

- **`potion/_any_time_usage`.** The conformance half is done: `ReplayRunner` now
  drains an out-of-combat `UsePotion` through `RunState.use_potion` instead of
  scanning past it. The RL half is **deliberately not done** — exposing an
  out-of-combat potion action is an action-space change that invalidates existing
  checkpoints. That is the owner's call, not a fidelity pass's side effect.
- **The four generator potions' `choose_a_card` guards.** The SKIP clause closed;
  what remains is that `scripted_card_selector` has no arm for the new purpose and
  still returns `candidates[0]`. That is a policy heuristic, not an engine limit —
  but it is the observable those guards were verdicted on, so they stay gaps.

## Two things to be sceptical of, recorded

1. **`power/_side_turn_slot`'s executed witness was stale.** It turned on
   Stampede auto-playing an Attack in the same pass; Stampede has since moved to
   `after_auto_post_play_phase_entered`, a strictly earlier phase, so that
   ordering could no longer occur. A repo-wide check found **no** ported listener
   between the two passes that reads Strength or Dexterity — the numeric
   consequence was dormant-with-a-named-trigger by the time it was fixed. The slot
   was wrong regardless. An issue text that cites an execution is only as current
   as the last change to the code it executed against.
2. **A green gate turned red for an unrelated reason.**
   `test_rng_tripwire.py`'s allowlist was keyed on `(file, LINE)`; adding six
   comment lines above `RunDriver._ask` moved it 252 → 259 and re-opened the gate
   on a site allow-listed since it was written. Re-keyed on `(file, function)`,
   which is what the allowlist's own comment argues from. Any gate keyed on a line
   number in a file people edit is a false alarm waiting to fire.

## Still not done

Unchanged from round 1 except that §A is now empty:

- **The turn-start split** (`AfterPlayerTurnStart` vs `AfterSideTurnStart`), the
  biggest single remaining Tier 1 item — and what `power/_side_turn_slot`'s
  *AfterSideTurnStart* leg (plating, rampart, crimson_mantle, inferno) waits on.
- **`hook_dispatch/G8` proper** — 19 of 20 sites; census done, the sim↔C#
  hook-name map is the work. Plus the inverse mismatch: `Hook.BeforeCardPlayed`
  **is** gated in C# and is not gated in the sim.
- **`relic/glass_eye/g5`** — populate-all-then-offer; untouched, still dormant.
- **§C Tier 2 families** and **§D Tier 3** entirely.

---

# Outcome, round 3 — 2026-07-28 (the five items behind section A)

Round 2 closed §A and left five named items. All five shipped, on the owner's
instruction to "expose the out-of-combat potion action change" and continue
through everything listed before Tiers 2 and 3.

## Measured

```
py -m pytest test/ -q                    2 failed, 2996 passed, 7 xfailed
   (both failures are the known missing RunReplays/933T39V18D/floor_49 fixture)
py audit/tools/harness.py validate       846 record(s), 0 invalid
py audit/tools/harness.py rehash --all   846 record(s), re-pinned 595
py audit/tools/audit_status.py           0 invalid, 0 stale
py audit/tools/gap_queue.py counts       1057 entries / 699 mechanisms / 170 live
py audit/tools/gap_queue.py cite-check   0 problem(s)                exit 0
py audit/tools/gap_queue.py coverage     0 missing / 0 unlocatable   exit 0
```

Entries 1097 → **1057**, mechanisms 720 → **699**, mechanisms with a live entry
174 → **170**, suite 2910 → **2996** passing. 40 entries closed, 20 narrowed.

## What closed

- **The turn-start split.** A player's turn start ran **four** C# hooks through
  **two** sim slots. It now runs four through four: `before_side_turn_start` =
  `Hook.BeforeSideTurnStart` (`CombatManager.cs:458`, before the block clear),
  `on_player_turn_start` = `Hook.BeforeHandDraw` (`:653`),
  `on_player_turn_started` = `Hook.AfterPlayerTurnStart` (`:675`), and the new
  `after_side_turn_start` = `Hook.AfterSideTurnStart` (`:522`). **50 listeners
  moved.** The slot for each was read off the `public override` in that unit's
  own C# file, not off the sim's docstrings — a scripted census (sim class →
  C# file → declared override) with the seven it could not decide resolved by
  hand. Two of those seven were not turn-start hooks at all: Sparkling Rouge is
  `AfterBlockCleared`, and Blood Vial / Fake Blood Vial are
  `AfterPlayerTurnStartLate`, which the existing `_each` suffix machinery
  already supported and nothing was using.
- **`hook_dispatch/G8`.** `HookSystem._each` implements
  `Hook.IterateCombatHookListeners`' `if (IsOverOrEnding && !IsStarting) yield
  break`. The gate is **per hook** — a map of the 41 sim dispatchers whose C#
  counterpart is in the guarded bucket, each named with the C# dispatcher it
  *is*, with the run-side/bypass/no-counterpart exclusions justified inline.
  Both generators, so the guard lands at enumeration start in both: a listener
  that ends the combat mid-dispatch does not cut off the ones after it.
  `IsStarting` came for free — `CombatState` back-references itself into
  `HookSystem` before it assigns `phase`, so setup dispatches find no phase.
  Also closed: the inverse mismatch `Hook.BeforeCardPlayed`.
- **`relic/glass_eye` G2–G5.** The relic builds a real reward set: five
  `CardRewardGroup`s, all populated, then `Hook.ModifyRewards`' two passes,
  then `RunState.offer_rewards` — a new `RewardsCmd.OfferCustom` seam the
  driver installs alongside `card_selector` / `option_selector` /
  `reward_selector`. Each group draws through `create_reward_cards`.
- **`potion/_any_time_usage`, the RL half.** Its own action block, legal on
  every out-of-combat screen, because `NPotionPopup.cs:322-325` enables the Use
  button for an AnyTime potion with **no screen predicate at all**. Drinking
  re-asks the same decision, as the overlay does.
- **`potion/_min_select_zero` clause (b).** A `choose_a_card` /
  `choose_a_card_optional` arm in `scripted_card_selector`.

## Two RNG-parity bugs that came from reading the source, not the queue

1. `CardFactory.CreateForReward`'s **Uniform** branch takes no rarity roll
   (`CardFactory.cs:219-221`). The sim ran `RollWithBaseOdds` anyway — one
   extra `PlayerRng.Rewards` draw per card, on all three Uniform callers (15
   for Glass Eye, 8 for Room Full of Cheese, 3 for The Future of Potions).
2. `InfernoPower.cs:26-35` fires its self-damage with no `> 0` test, so a
   turn-1 Inferno runs a 0-damage command through the whole pipeline.

Neither was in any gap entry. Both were found by reading the C# a fix had to
touch anyway.

## Three entries were stale, not open

`turn_structure/G8`, `turn_structure/step26` and `enchantment/imbued/BR-4` all
said Howl From Beyond, Whispering Earring and Imbued were hand-rolled onto
neighbouring slots. All three are already on their real phase hooks. What this
round actually changed there was the other side of the same ordering: Crossbow,
genuinely `Hook.AfterSideTurnStart`, moved onto the new dispatcher and now runs
strictly before the AutoPrePlay phase instead of sharing a registration-ordered
pass with it. **Second round running that a stale witness turned up** — an issue
text is only as current as the last change to the code it was written against.

## Explicitly not done

- **The command-level `IsOverOrEnding` guard family**
  (`creature_card_cmds/G14`, `power_cmd/G6`) — 16 of `hook_dispatch/G8`'s
  entries, which the queue merges under that key because their issue texts
  cross-reference. Those are `CreatureCmd` / `CardCmd` / `CardPileCmd`
  returning early; the mutation each performs still happens, only the hooks it
  would have dispatched are stopped. Both narrowed with that observation.
- **`turn_structure/G5`** — the enemy side is still per-enemy where the game is
  per-side, so the two new side-scoped dispatchers are deliberately player-side
  only. `hooks.py` says so at the map, and the enemy legs of Plating, Hardened
  Shell, Poison, Sandpit and Slow still wait on it.
- **`turn_structure/G12`'s residue** — FakeOrichalcum's
  `BeforeSideTurnEndVeryEarly` snapshot and Sandpit's enemy-side
  `AfterSideTurnStartLate`. Content, not machinery.
- **§C Tier 2 families** and **§D Tier 3** entirely.

## Checkpoint note

`RUN_OBS_SCHEMA_VERSION` is **6**. The observation is byte-identical to v5 and
the potion block is appended **last**, so every existing action keeps its index.
`checkpoints.migrate_checkpoint_actions` grows the policy head by four zero rows
and its Adam moments to match, and touches nothing else — the value function and
the logits over every old action are preserved exactly.
`py migrate_ckpt.py <ckpt> <new>` now picks the hop (v3→v4 or v5→v6) from the
source checkpoint's own `obs_schema`.


# Outcome, round 4

The three residues round 3 listed under "Explicitly not done" (everything except
§C Tier 2 and §D Tier 3) are done.

| | before | after |
|---|---|---|
| gap entries | 1057 | **1014** |
| distinct mechanisms | 699 | **683** |
| mechanisms with a live entry | 170 | **169** |
| suite | 2996 passed | **3018 passed, 7 xfailed** (+ the 2 known missing-fixture failures) |

Gates: `validate` 846/0 invalid, `rehash --all` re-pinned 543, `audit_status`
0 invalid / 0 stale, `cite-check` 0 problems, `coverage` 0 missing /
0 unlocatable.

## `turn_structure/G5` — the enemy side is one SIDE turn

`_run_enemy_turns` now follows `CombatManager.StartTurn` +`ExecuteEnemyTurn` +
`EndEnemyTurnInternal`: capture the participants once (`:444`),
`Hook.BeforeSideTurnStart` once (`:458`), a complete block-clear pass
(`:492-499`), a complete `AfterBlockCleared` pass (`:500-507`),
`Hook.AfterSideTurnStart` once (`:522`), `CheckWinCondition` (`:598`), the moves
(`:1072-1090`), then `Hook.BeforeTurnEnd` (`:1251`) and `Hook.AfterTurnEnd`
(`:1256`) once each.

The sim's `on_enemy_turn_start` / `on_enemy_turn_end` are **deleted**, not
re-slotted. C# has no per-creature turn hook at all, so every listener on them
was implementing a side hook; a census against each unit's own `public override`
moved 15 powers onto `before_enemy_side_start`, `after_enemy_side_start`
(+`_late`), `before_enemy_side_end` (+`_very_early`, `_early`) and the existing
`on_enemy_side_end`. The Slumbering Beetle's stun-move shim became a `take_turn`
override, which is where `MonsterModel.PerformMove` actually runs it.

The sim expresses C#'s one `(state, side, participants)` hook as a **pair** of
dispatchers, one per side. That is the idiom it already used for
`Hook.AfterTurnEnd` (`after_player_turn_end` / `on_enemy_side_end`), and it is
behaviour-preserving: every C# implementer opens by testing `side` or
`participants.Contains(Owner)`, and the two sides never start a turn at the same
moment, so there is no cross-side order to lose.

## `turn_structure/G12` residue — one of two clauses was stale

Sandpit reached `after_enemy_side_start_late` with G5. **Fake Orichalcum was
already correct** — `on_player_turn_end_very_early` for the `Block > 0` snapshot
and plain `on_player_turn_end` for the grant, since the phase machinery landed.
The still-flat half was the *other* side of that interaction: PlatingPower's
grant sat on the plain pass on both sides where `PlatingPower.cs:61` is
`BeforeSideTurnEndEarly` and says why in as many words. Both legs moved to
`_early`, which makes the ordering `FakeOrichalcum.cs:40-45` describes in prose
an actual guarantee.

## `creature_card_cmds/G14` + `power_cmd/G6` — the command guards

`CombatState.is_ending` is now a real predicate (`CombatManager.cs:180-202`):
not `phase == COMBAT_OVER` but a live recomputation of "a loss is pending, or no
primary enemy is alive and nothing vetoes the end", which already carries
`Hook.ShouldStopCombatFromEnding`. Guards landed at their C# strength:
`IsOverOrEnding` on `BlockCmd.apply`, `discard_hand`, `_draw`, both shuffles and
`CardCmd.afflict` (with its combat-pile asymmetry); `IsEnding` on
`PowerCmd.apply` and `CardCmd.transform_to_random`, which is what keeps the
out-of-combat deck transformers working; the three `CardPileCmd.Add` refusals on
the pile helpers. `PowerCmd`'s mid-pipeline `CanReceivePowers` re-check
(`:133`) landed with them, on the new-power branch alone as C# has it.

Steps 1 and 7 closed by **re-reading**, not by code: `!IsLiveCombat()` is the
`NullCombatState` test (`CombatState.cs:608` returns `true` unconditionally;
only `NullCombatState.cs:146` returns `false`), not an ending test, and the
sim's `combat is None` is its counterpart.

## What the window turned up

Four existing tests moved, each re-derived from source:

1. **Daughter of the Wind's lethal-Strike Block does not land.** `AfterCardPlayed`
   bypasses the hook gate on purpose so the listener runs, but
   `CreatureCmd.GainBlock` refuses (`CreatureCmd.cs:637`). Round 3 pinned the
   Block having checked only the hook half. The bypass is about dispatch, not
   about effect.
2. **A Tough Egg laid on the enemy side takes that side's Hatch tick.**
   `ToughEgg.cs:133` applies 2 on the enemy side and 1 elsewhere — a
   compensation that only makes sense if the same-turn decrement happens.
3. **The Lost / The Forgotten repayment needs a live sibling**, because it goes
   through `PowerCmd.Apply`. The tests use the real two-enemy encounter now.
4. **`StockPower.ShouldStopCombatFromEnding` was unported** (`StockPower.cs:28-31`).
   Without it the last Axebot's death made the combat "ending" and killed its own
   respawn.

Plus two guards the per-creature slot had been hiding: `RegenPower`'s
`!Owner.IsDead` (`RegenPower.cs:22`), and `HardenedShellPower.cs:71`'s complete
absence of a `side`/`participants` filter — its counter resets at the start of
BOTH sides' turns.

## Explicitly not done

- `turn_structure`'s **G7** (no `EndOfTurnCleanup`), **G8** (AutoPrePlay /
  AutoPostPlay phases), **G10** (the combat-end collapse), **G13** (the
  mid-pipeline `CheckWinCondition` sites, narrowed), **G15**, **G16**, and
  **N1/N4/N5**.
- `power_cmd/G6` carries one observation forward rather than a closure: the
  sim's duration ticks mutate `amount` through `Power._tick` instead of routing
  through `PowerCmd`, so `ModifyAmount`'s `IsEnding` guard does not reach them.
- **§C Tier 2 families** and **§D Tier 3** entirely.

## New tests

- `test/test_enemy_side_per_side.py` (8) — the three-pass shape, the two-enemy
  Poison trace, Sandpit's `_late` pass, Slow's once-per-side reset, Hardened
  Shell unfiltered, Plating's side-end grant, Asleep-before-Plating.
- `test/test_combat_ending_command_guards.py` (14) — the window itself
  (`is_ending` vs `is_over_or_ending` vs `ShouldStopCombatFromEnding`) and every
  guarded command.
- `test_fake_merchant.py::test_fake_orichalcum_is_suppressed_by_platings_earlier_grant`.
- Replaced: `test_hook_order.py::test_enemy_side_is_interleaved_per_enemy`, which
  pinned the old interleaved order as a deliberate divergence.


# Outcome, round 5

Everything round 4 listed under "Explicitly not done" except §C Tier 2 and
§D Tier 3 is done. **`seam/turn_structure` has no open gap entry left.**

| | before | after |
|---|---|---|
| gap entries | 1014 | **975** |
| distinct mechanisms | 683 | **665** |
| mechanisms with a live entry | 169 | **165** |
| suite | 3018 passed | **3063 passed, 7 xfailed** (+ the 2 known missing-fixture failures) |

Gates: `validate` 846/0 invalid, `rehash --all` re-pinned 671, `audit_status`
0 invalid / 0 stale, `cite-check` 0 problems, `coverage` 0 missing /
0 unlocatable, `power_census slots` 0 mis-slotted.

## `turn_structure/G8` + `/N1` — the phase model and the setup window

`sts2_rl/turn_phase.py` is a port of `PlayerTurnPhase.cs`: an **IntEnum in the
game's declaration order**, because `UnceasingTop.IsValidPhase` (`:29-36`)
compiles to `(uint)(phase - 2) <= 2u` — the ordinals are load-bearing.
`PlayerCombatState.turn_phase` is driven at every C# transition (`:429`, `:464`,
`:616`/`:618`, `:1165`/`:1175`, `:978`).

`CombatState._start_player_turn` opens `_inPlayerTurnSetup` around
`player.start_turn()` and closes it in a `finally`, which is
`ReleaseDeferredEndTurnTransitionIfNeeded` (`:722-735`) — `:720` requires it on
every exit path. `end_turn()` inside the window STORES the transition instead of
running it, so an end-turn from a card auto-played during AutoPrePlay cannot
recurse into the tail of `StartTurn`.

The CONTENT residue G8 listed was **stale**: all three implementers had been on
their real phase hooks since round 3.

## `turn_structure/G16` — where the hand-empty check runs

`CombatManager.cs:869-883` is unusually explicit that there are exactly two call
sites and that ending the turn is not one of them. Both exist now
(`CardModel.cs:1992`, `PotionModel.cs:340`), `discard_hand` fires nothing, and
`!IsExecutingCardOrPotionEffect` is a real nesting depth
(`_card_or_potion_effect`) released in a `finally` around the play-count loop and
the potion body — which is what stops the docstring's own worked example
(Unceasing Top + Pommel Strike) drawing twice.

## `turn_structure/G7` — EndOfTurnCleanup

Ported at both C# sites, over every pile, with the three single-turn card states
it exists to clear. The start-of-turn `reset_turn_cost_modifiers` loop is gone:
the sim's expiry window was a full enemy turn wider than the game's. The flush
partitions on `should_retain_this_turn` (`CardModel.cs:590-600`) and
`exhaust_on_next_play` is consumed where `GetResultPileTypeForCardPlay` consumes
it (`:2078`) — before OnPlay, not after.

## `turn_structure/G13` — the remaining CheckWinCondition sites

`:1181`, `:1207-1208` and `:830` are recomputations now, and the four inline
`_all_enemies_dead()/is_dead` pairs were `CheckWinCondition` with the tie-break
the wrong way round — they call `_check_win_condition()`, so a simultaneous
death resolves as a LOSS as `:1048` does.

## `turn_structure/G10` + `/N5` — the combat-end path

Two asymmetric exits. `_process_pending_loss` (`ProcessPendingLoss`, `:956-965`)
fires **no hook at all**; `_end_combat_internal` revives a dead player to 1 HP
BEFORE any hook (`Player.cs:821-827`, whose comment explains that relics are not
subscribed while their owner is dead), then `Hook.AfterCombatEnd` (`:988`), then
`Hook.AfterCombatVictory` (`:999`). `lose_combat()` is the deferral C# uses to
avoid processing a loss at an unsafe point.

## `turn_structure/N4` — two counters

`turn` stays `TurnNumber` (bumped on extra turns, `:1417`); `round_number` is
`RoundNumber` (normal rounds only, `:1413`). CombatHistory stamps
`round_number`, as `CombatHistory.cs:40-120` does, so an extra player turn is
the same round and "did X happen this turn" survives it.

## Six content ports were on the wrong hook

Each re-derived from source: **Joss Paper** (`AfterSideTurnEnd`, not
`AfterHandEmptied` — and its own comment asks for exactly that position),
**Unceasing Top** (`AfterHandEmptied` with its phase gate, not a hand-rolled
`on_card_played` condition), **Chosen Cheese** (`AfterCombatEnd`, and its extra
`is_dead` guard deleted because the revive makes one unnecessary), **Burning
Blood** and **Black Blood** (`AfterCombatVictory`), **Meat on the Bone**
(`AfterCombatVictoryEarly`). Three of them tested a `player_won` flag to
compensate for the collapsed hook; there is no flag and no losing dispatch now.

**Whispering Earring's hand-rolled loop guard turned out to be FAITHFUL** rather
than the workaround N1 called it — `WhisperingEarring.cs:58-69` breaks on three
conditions of its own — but it was missing two. It breaks on `IsOverOrEnding`,
`IsPlayerReadyToEndTurn` and the turn change now, in the source's order.

## Explicitly not done

- `power_cmd/G6` closes with an honest exclusion: the decrement path does NOT
  run `ModifyAmount`'s `ModifyPowerAmountGiven`/`ModifyPowerAmountReceived`
  chains (`:229-233`), because `power_cmd/G2` — a separate open entry — leaves
  the sim's Unsettling Lamp without C#'s `amount <= 0` early bail, so it would
  double a -1 duration tick into -2.
- `Card.is_sly_this_turn` exists with no consumer: no sim content grants or
  reads Sly. The STATE is there because `EndOfTurnCleanup`'s job is to clear it.
- **§C Tier 2 families** and **§D Tier 3** entirely.

## New tests

- `test/test_turn_structure_gaps.py` (48) — one class per named guard: the
  phase walk, both hand-empty call sites and the effect-depth gate, the deferred
  end-turn, `EndOfTurnCleanup` at both sites, the win-condition recomputations,
  the two combat-end exits, the two counters, and the ethereal wrapper.
- Updated: `test_relics.py`'s two Unceasing Top tests and `test_no_heal_on_defeat`
  (which now proves the loss fires nothing rather than that the relic tests a
  flag), `test_combat_over_hook_gate.py`'s `on_combat_end` signature, and
  `test_hook_order.py`'s end-turn sequence (no `on_hand_emptied` from the flush).
