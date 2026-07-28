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
