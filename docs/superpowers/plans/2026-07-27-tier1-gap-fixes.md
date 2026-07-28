# Tier 1 gap fixes — implementation plan

**Source of truth for the work list:** `audit/GAP-QUEUE.md` §"Tier 1 — live gaps"
(sections 1A–1F, 80 entries numbered 1–75 plus 46a–46l). Every entry there
already carries `divergence`, `observable`, `fix` and `radius`; this plan does
not restate them. It decides **order**, **batching** and **done-ness**.

This reverses the queue's standing "queued, not fixed" decision for Tier 1 only.
Tier 2 (dormant) and Tier 3 (long tail) are out of scope.

---

## Baseline (measured 2026-07-27, before any edit)

```
py -m pytest test/ -q                    -> 2 failed, 2518 passed, 42 xfailed (249s)
py -m pytest test/test_hook_order.py -q  -> 14 passed, 36 xfailed
py audit/tools/audit_status.py           -> 8 kinds, 846 records, 0 invalid, 0 stale
py audit/tools/gap_queue.py counts       -> 1612 entries / 856 mechanisms / 32 pinned
```

Working tree clean on `main`.

**The 2 baseline failures are pre-existing and environmental**, not sim defects:
`test_conformance_floor_state.py::test_floor_checkpoints_and_resync_run_to_completion`
and `::test_resync_does_not_degrade_replay_vs_no_floor_saves_baseline[933T39V18D]`
both raise `FileNotFoundError` on
`RunReplays/RunReplays/Resources/933T39V18D/floor_49/actions.sts2replay` — a
fixture that is not on this disk. They stay failing; "at or above baseline"
means 2518 passed and these same 2 failures, nothing new.

## Definition of done, per work package

A package is done when **all five** hold:

1. **Code** — the sim change described by the entry's `fix` field, and nothing
   beyond it (CLAUDE.md §3, surgical changes).
2. **Test** — a failing-first test asserting the entry's `observable` numbers.
   For a **pinned** entry the test already exists as a `strict=True` xfail in
   `test/test_hook_order.py`: the fix makes it XPASS, which under `strict=True`
   **fails the suite**, so the package must also delete that xfail marker. That
   is the acceptance signal — a pinned package is not done until its marker is
   gone and the test passes green.
3. **Suite** — `py -m pytest test/ -q` at or above baseline. Legacy tests that
   encoded the old (wrong) semantics get **updated, not deleted** — per the
   standing project rule that "original behavior" means the decompiled game.
4. **Records** — the `verdict` of every gap entry the package closes flips
   `gap` → `faithful`, with an `issue`/note naming this fix. Then
   `py audit/tools/harness.py rehash --all` re-pins the sha256s the edits staled.
5. **Queue** — `py audit/tools/gap_queue.py coverage` and `cite-check` exit 0,
   and `GAP-QUEUE.md`'s counts are regenerated.

Steps 4–5 run **once per wave**, not once per package, because `rehash` is bulk
and the queue is regenerated from the records.

**No commits.** Changes are staged only (CLAUDE.md §4). Perry commits.

---

## Ordering principle

The queue orders by convergence impact (A before B). This plan orders by
**dependency**, because several entries explicitly say a fix measured before its
prerequisite lands is measured against a moving target. Within a wave, grade A
goes first.

Dependencies taken from the entries' own `radius`/`fix` text:

| entry | needs first | stated where |
|---|---|---|
| 35 `turn_structure/G12` | 21 `hook_dispatch/G3` | "Land G3 first, then convert these three dispatchers" |
| 49 `relic/_reward_late_pass` | 21 | "Same shape as G3's phase passes" |
| 55 `relic/_victory_flatten` | 21 | "Sibling of G3" |
| 57 `damage_pipeline/N4` | 21 | early `ShouldDie` pass = a phase pass |
| 23 `power/_killing_blow_guard` | 19, `damage_pipeline/G4` | "fix those first or the re-hosting is measured against a moving target" |
| 24 `damage_pipeline/G1` | 23 (same family) | leg 1 is the killing-blow guard |
| 13 `event/EV-1` | run-level listener list (`hook_dispatch/N5`) | "needs N5 first or a narrower belt-only iteration" |
| 26 `event/EV-2` | 13 | "which needs EV-1's death pass to be right" |
| 36 `turn_structure/G3` | 42 `turn_structure/G18` | "fix G18 first or the test fixture will disagree with itself" |
| 22 `enchantment/EG1` | 16 `hook_dispatch/G4` | "This is the same loop — do them together" |
| 8 `event/EV-5` | 7 `event/EV-7` | "a site can need all three fixes before it converges" |
| 62 `power/shackling_potion/g8` | 25 | "second live consequence of PowerCmd.apply lacking the backstop" |
| 45 `power/diamond_diadem/g1` | 51 `relic/_combat_reset` | "the same missing-reset mechanism at 16 sites" |
| 63 `power/surrounded/BeforePotionUsed` | — | same dispatch as 46a; land together |
| 61 `card/alchemize/g3` | 60 | "one fix likely serves both" |

Entries the queue groups as **one work package** by its own words:

- **3 + 12 + `msm/G5` + `msm/G6`** — "These four are one work package … fixing
  them separately risks fixing the draw count twice."
- **37 + 38 + 39** — "the same three lines of `player.py`; land all three in one
  pass." **30** joins them (same `_first_turn` block).
- **15 + 32 + 33 + 58** — "one editing pass over `cmds.py:56-58` / `145-147` and
  `hooks.py:52-122` can land all three"; 58 is 32 at a listener the census
  missed.
- **40 + 41 + `G16`** — "all three should be read together before touching
  `joss_paper.py`."
- **1 + 6 + 7 + 8 + 9 + 11** — the event RNG/pick sweep; the entries compound,
  "fixing the stream without fixing the pick leaves the site still divergent."

---

## Waves

Each wave is a set of packages with **disjoint file ownership**, so the packages
inside one wave can run concurrently without stepping on each other. Waves run
in sequence.

### Wave 0 — foundation: hook dispatch machinery

Everything ordering-shaped in Tier 1 measures against these two. They rewrite
`sts2_rl/hooks.py`'s dispatch core, so nothing else runs concurrently.

| pkg | entries | files | pin |
|---|---|---|---|
| **W0.1** | **20** `hook_dispatch/G2` — derived listener order (per-creature buckets, allies→enemies, powers→relics→potions→orbs→cards) | `hooks.py`, `combat.py`, `cmds.py` | `test_powers_modify_energy_cost_before_relics_do` |
| **W0.2** | **21** `hook_dispatch/G3` — Early/VeryEarly/Late phase passes, re-enumerating listeners per pass | `hooks.py` | `test_late_energy_cost_modifiers_run_after_early_ones` |

W0.2 depends on W0.1 (a phase pass re-walks the derived list). Run W0.1, then
W0.2.

### Wave 1 — damage / block modifier pipeline

One editing pass over `cmds.py:51-58, 145-147` and `hooks.py:52-155`.

| pkg | entries | acceptance |
|---|---|---|
| **W1.1** | **15** `hook_dispatch/G9` — multiplicative modifiers fold sequentially, not as a parallel product | Shrink+Vulnerable on 20 damage = **21**; Corrupted Strike +Str 3 = **12** |
| **W1.2** | **32 + 58** `damage_pipeline/G3` — delete the pipeline-level `is_powered_attack` gates; push self-gating into Strength/Vulnerable/Weak/Dexterity/Frail/Fasten and **not** into Vambrace / Pael's Legion / Surrounded / Unmovable | Vambrace doubles an Entrench block gain; Entrench from 10 block with Unmovable 1 = **30** |
| **W1.3** | **33** `damage_pipeline/G2` — generalise the `modify_hp_lost` `modifiers` out-param + `after_modify_<x>` notifier to the block and power-amount dispatchers; re-home Vambrace, Pael's Legion, Fasten | Vambrace doubles **both** block gains of one card play and neither gain of the next |

W1.1–W1.3 all touch the same two functions; run them **sequentially** as one
agent, in the order given (the shape change first, then the gate, then the
notification), not concurrently.

### Wave 2 — death, power lifecycle and the power-application guard

| pkg | entries | files |
|---|---|---|
| **W2.1** | **19** `power/_death_prevention_branch` — prevention leaves the creature **dead at 0 HP retained in combat**; `on_death(was_removal_prevented=)` fires on both arms; Feed reads the kill not `is_dead` | `cmds.py`, `powers.py`, `cards/feed.py` |
| **W2.2** | **14** `creature_card_cmds/step8b` — `RemoveAllPowersAfterDeath`: new `should_power_be_removed_after_owner_death` defaulting **True**, `Hook.ShouldPowerBeRemovedOnDeath` with Illusion as its one implementer, `on_removed` per stripped power. Delete the hand-rolled `_expire()` compensations the strip makes redundant | `cmds.py`, `hooks.py`, `powers.py` |
| **W2.3** | **23 + 24** `power/_killing_blow_guard` + `damage_pipeline/G1` — per-unit re-hosting of the 7 listeners onto `before_damage_received` / `on_damage_dealt` where the C# hook is not `AfterDamageReceived`; Thorns moves to `before_damage_received` **and** gains the `is_powered_attack or Omnislice` gate | `powers.py`, `cmds.py`, `hooks.py` |
| **W2.4** | **25 + 62** `power/_should_allow_hitting` — `should_allow_hitting` guard at the top of `PowerCmd.apply`; Shackling Potion's applier uses the hittable predicate | `cmds.py`, `potions.py` |
| **W2.5** | **57** `damage_pipeline/N4` — early `ShouldDie` pass before the late one (needs W0.2) | `hooks.py`, `cmds.py`, `potions.py` |
| **W2.6** | **43** `power_cmd/step20` — move the two `skip_next_tick` lines inside the new-power branch. *Cheapest live fix in the queue* | `cmds.py` |

W2.1 → W2.2 → W2.3 sequential (each moves the window the next is measured in).
W2.4, W2.5, W2.6 are independent of that chain and of each other.

### Wave 3 — turn structure

| pkg | entries | files |
|---|---|---|
| **W3.1** | **37 + 38 + 39 + 30** — `player.py` block-clear and turn-1: unconditional `on_block_cleared` second pass; `should_clear_block` returns `(bool, preventer)` + `after_preventing_block_clear`; turn-1 early return before `ClearBlock`; the `ShouldStartAtBottomOfDrawPile` bottom-move pass before the Innate top-move pass with `.Except`. Un-rewire Anchor / Fake Anchor onto `before_combat_start`; move Sturdy Clamp's cap onto the preventer hook | `player.py`, `hooks.py`, `relics/{anchor,fake_anchor,sturdy_clamp}.py` |
| **W3.2** | **42 → 36** — `CardPlayedEntry.is_auto_play`; Pael's Eye filters auto-plays and short-circuits on turn-1 Whispering Earring; **then** move `should_take_extra_turn` to the bottom of `end_turn` so it skips only `_run_enemy_turns`, and split `self.turn` into `turn_number` / `round_number` | `history.py`, `combat.py`, `relics/paels_eye.py` |
| **W3.3** | **40 + 41 + `G16`** — flush tail runs unconditionally (`after_flush` + `EndOfTurnCleanup`), `should_flush_hand` decides only which cards move; `on_card_exhausted(caused_by_ethereal=)` passed True from exactly the two turn-end sites; Joss Paper reads the cause not the card | `combat.py`, `player.py`, `hooks.py`, `relics/joss_paper.py` |
| **W3.4** | **34** `turn_structure/G8` — AutoPrePlay / AutoPostPlay as explicit phase steps in `end_turn` / `start_turn`, and rehome `turn_structure/N1`'s hand-rolled recursion guard | `combat.py`, `player.py`, `relics/whispering_earring.py` |
| **W3.5** | **35** `turn_structure/G12` — convert the three side-turn dispatchers to phase passes (needs W0.2) | `hooks.py`, `combat.py` |
| **W3.6** | **29** `turn_structure/G13` — a real recomputing `_check_win_condition()` after `on_combat_start` → `start_turn`; decide the other two flag-reads | `combat.py` |
| **W3.7** | **17** `power/_side_turn_slot` — move the 29 `AfterSideTurnEnd` powers onto `after_player_turn_end`, using `py audit/tools/power_census.py slots` as the checklist (some of the 54 are correctly placed and must not move) | `powers.py`, `combat.py` |

All of these touch `combat.py` or `player.py`. Run W3.1 (player.py) concurrently
with W3.2 (combat.py end-of-turn) only if the diff hunks stay disjoint;
otherwise sequence 3.1 → 3.2 → 3.3 → 3.4 → 3.5 → 3.6 → 3.7.

### Wave 4 — card play loop

| pkg | entries | files |
|---|---|---|
| **W4.1** | **16 + 22 + 56** — move `before_card_played` / `on_card_played` **inside** the play-count loop with a per-iteration play index; add the `card.enchantment.on_play(...)` slot after the card's own `on_play` and before `on_card_played`; thread `is_auto_play` so Brilliant Scarf ignores auto-plays (and `rainbow_ring` / `razor_tooth` keep counting them) | `combat.py`, `enchantments.py`, `history.py`, `relics/brilliant_scarf.py` |

Acceptance: Pen Nib's counter advances by 2 on a Throwing-Axe-doubled Strike;
Corrupted + Rupture Strike deals 9; Corrupted under Throwing Axe takes 4
self-damage; one `auto_play_card` leaves `cards_played_this_turn == 0`.

### Wave 5 — monster AI (mostly disjoint per-monster files)

| pkg | entries | files |
|---|---|---|
| **W5.1** | **3 + 12 + `msm/G5` + `msm/G6`** — the stunned-enemy package: `_roll_enemy_intents()` walking `self.enemies` in list order at player-turn start (skipped on an extra turn), `telegraph_next_move` stops rolling, stun becomes a real `MoveState` pinned by `must_perform_once_before_transitioning` with the deferred move re-logged, `next_move_key` reaches a `MachineMonster`, Flutter's splice consumes no shared draw | `combat.py`, `monsters/{base,state_machine}.py`, `cmds.py` |
| **W5.2** | **2** `monster_state_machine/G1` — re-read the five misread `AddBranch` calls (Flail Knight, Hunter Killer, Scroll of Biting, Spectral Knight, Fake Merchant) against the C# overload table; positional slot 2 is cooldown-or-maxRepeats, never weight. Fix the false docstring at `fake_merchant.py:40` | `monsters/hive/{flail_knight,hunter_killer}.py`, `monsters/glory/{scroll_of_biting,knights}.py`, `monsters/fake_merchant.py` |
| **W5.3** | **64** inklet branch add order (+ rewrite the pin, which currently derives its expectation from the sim); **69** ovicopter backwards egg slots (legacy arm); **68** living fog slot-sorted spawn via `CreatureCmd.add(index=)`; **71** the_insatiable `CardPilePosition.Random` for `add_to_discard` | `monsters/overgrowth/inklets.py`, `monsters/…/ovicopter.py`, `living_fog.py`, `the_insatiable.py`, `cmds.py`, `test/test_monster_branch_audit.py` |
| **W5.4** | **65** per-encounter `Rng` (build the concept, thread through `create_monsters`); **66** fabricator → `combat_rng.monster_ai`, thieving hopper → `combat_rng.card_gen` | `monsters/base.py`, `combat_rng`, `fabricator.py`, `thieving_hopper.py` |
| **W5.5** | **67** queen amalgam death substitutes the telegraph; **70** punch construct cuts current HP not max; **72** thieving hopper steal predicates regain Event/Quest/Imbued clauses; **73** tough egg exclusive `NextInt`; **74** slumbering beetle stun body runs on the stunned turn; **75** the two dropped second intents (`Intent.also`) | one file each |

W5.1 owns `combat.py` and `state_machine.py`; W5.2–W5.5 own per-monster files.
W5.1 must not run concurrently with Wave 3.

### Wave 6 — events

| pkg | entries | files |
|---|---|---|
| **W6.1** | **1 + 6 + 7 + 8 + 9 + 11** — the RNG/pick sweep. Thread `self.event_rng` through the 28 modules `event_probes.py eventrng` lists; route the 4 `PlayerRng.Rewards` potion offers at `rewards_rng.next_item`; uppercase sort key at every `stable_shuffle` call site; replace `rng.sample` / bare shuffle with `actmap.stable_shuffle`; swap `random_pool_cards` → `rewards.create_reward_cards` at Infested Automaton and the two hand-rolled offers | 28+ modules under `events/` |
| **W6.2** | **4** unrest_site's 70% gate in integers (`hp * 100 <= max_hp * 70`), and sweep the other event gates for the same float shape | `events/unrest_site.py` + sweep |
| **W6.3** | **5** Combat-layout events build their encounter at **room entry**, unconditionally | `events/{punch_off,the_lantern_key}.py`, `run.py`, `rooms.py` |
| **W6.4** | **10** the 7 `OfferCustom` take-or-skip screens return their reward instead of granting it | 7 event modules, `driver.py` |
| **W6.5** | **44** Dense Vegetation rests through `run.rest_heal()` + `run.rest_heal_rewards()` | `events/dense_vegetation.py` |

### Wave 7 — run layer (`run.py`)

| pkg | entries |
|---|---|
| **W7.1** | **13** `event/EV-1` — `RunState.lose_hp` gets the `should_die` / `after_preventing_death` pass over a run-level listener list (belt-scoped is acceptable per the entry) and clamps at 0; drop the Fairy's `self.combat is None` early return |
| **W7.2** | **26** `event/EV-2` — `lose_max_hp` computes the new max unfloored, routes the overflow through the HP-loss path, **then** floors (needs W7.1) |
| **W7.3** | **27** `event/EV-10` — split `transformable_cards` off the removal predicate (`Type != Quest && IsTransformable`) |
| **W7.4** | **31** `creature_card_cmds/G3` — `transform_card` routes through `modify_card_being_added_to_deck` + the deck-add shim, keeping the append-at-end position |

### Wave 8 — relics

| pkg | entries |
|---|---|
| **W8.1** | **51 + 45** `relic/_combat_reset` — the combat-boundary reset dispatch for 13 relics, **including** the combat-ends-on-your-own-turn hole that leaves Diamond Diadem broken and looking fixed. Pin as one parametrized "same instance, two combats, equal observations" test |
| **W8.2** | **46** `relic/_is_allowed` — add `is_allowed(run)` to `relics/base.py`, consult it in the pool builders, and make `is_allowed_at_neow` **delegate** to it |
| **W8.3** | **47** `relic/_off_stream_draw` — route 15 relics at their named streams (grade A) |
| **W8.4** | **52** `relic/_stable_shuffle` — one shared helper: top-first orientation, UPPERCASE key, and restore the dropped `.Take(N)` at `sand_castle` / `war_hammer` |
| **W8.5** | **49 + 55** the two split dispatches: `TryModifyCardRewardOptions{,Late}` / `TryModifyRewards{,Late}`, and `AfterCombatVictoryEarly` before `AfterCombatVictory` (both need W0.2) |
| **W8.6** | **50** `relic/_auto_keep` — route 15 relics through the selection/skip machinery; **do not** touch `neows_bones`, `claws`, or `glass_eye`'s transform half |
| **W8.7** | **53** `undo_after_obtained` subtracts instead of clamping (5 relics); **54** `modify_merchant_price` hook + `MerchantEntry` cost routed through it (truncating division) |
| **W8.8** | **48** `relic/_stub` — re-audit each of the 21 stubs whose docstring cites a system the sim now has, and implement the ones that are now implementable. **The stub docstrings are the index.** Report any that remain genuinely out of reach |

### Wave 9 — potions, cards, enchantments

| pkg | entries |
|---|---|
| **W9.1** | **46a + 63** the use pipeline: add `before_potion_used` and dispatch it before `potion.use`; call the empty-hand check after |
| **W9.2** | **59 + 60 + 61** — combat-side procurement runs the `ShouldProcurePotion` gate and fires `AfterPotionProcured`; **delete `player.py:112-115`'s out-of-scope docstring in the same change** |
| **W9.3** | **46b** legacy arm of the four generated-card potions gets `offer_screen_selection`; **46d** `select_cards` gains `min_select` |
| **W9.4** | **46c** `PotionUsage.AnyTime` — a `usage` attribute and a run-level `use_potion` |
| **W9.5** | **46e–46l** the eight single-unit findings: foul potion thrower-first ordering (+ the win-check ordering bug it exposes) and its two out-of-combat arms; fairy-in-a-bottle routes through the use wrapper; touch of insanity's global-cost filter; entropic brew's legacy factory |
| **W9.6** | **18** `enchantment/EG2` — the five rebuild copy sites carry the enchantment **and** the affliction; fix `_clone`'s false docstring. **28** `Card.downgrade`/`upgrade` re-apply `enchantment.modify_card` after the rebuild |

---

## Risks and how they are handled

**A fix that changes RNG draw counts breaks conformance fixtures.** Waves 5 and
6 are exactly that. `test/test_conformance_*.py` and the seed fixtures are the
tripwire; a failure there is *expected* for a stream fix and must be
investigated, not silenced. Where a fixture encodes the old stream, it is
re-recorded or the test is updated with a note — never `xfail`ed away.

**The 36 strict xfails will start XPASSing mid-wave.** That is the acceptance
signal, not a regression. Any package that lands a pinned fix deletes its marker
in the same change. A package that lands only *part* of a pinned mechanism
leaves the marker and says so.

**Record staleness.** Every sim edit invalidates the sha256 pins on the records
citing that file. `harness.py rehash --all` is run **once per wave**, after the
verdict flips, so the re-pin records the post-fix state.

**Over-broad fixes.** Three entries name a specific trap:
- 56 — `rainbow_ring` / `razor_tooth` deliberately count auto-plays; keep them.
- 50 — `neows_bones` / `claws` / `glass_eye` transform half are correct
  `deliberate-divergence`; keep them.
- 46 — `is_allowed_at_neow` must *delegate*, not be a second independent flag.

**Entries that may not be closeable as written.** 46a's own text says the
structural fix is a new `potion_pipeline` seam; 65's is "the missing thing is a
concept". Where the code fix lands but the structural debt remains, the record
verdict flips only for the part actually closed, and the remainder is reported.

## Reporting

At the end: which entries closed, which partially closed and why, the suite
delta, the pin delta (36 xfails → N), and the regenerated
`gap_queue.py counts`.

---

# Outcome

**Tier 1 is closed.** Every mechanism in sections 1A–1F with a LIVE site on ported
content has been fixed, or is explicitly recorded as partially closed with the
remainder named.

## Measured

```
py -m pytest test/ -q      2 failed, 2857 passed, 13 xfailed      (baseline 2 / 2518 / 42)
py -m pytest test/test_hook_order.py -q   45 passed, 6 xfailed    (baseline 14 / 36)
py audit/tools/gap_queue.py pins          6                       (baseline 36)
```

The 2 failures are the same pre-existing environmental ones throughout: a
missing `RunReplays/.../933T39V18D/floor_49/actions.sts2replay` fixture.

**All 6 remaining strict-xfail pins are Tier 2 (dormant) mechanisms** —
`power_cmd/G1`, `hook_dispatch/G8` (two tests), `monster_state_machine/G3`,
`/G7`, `/G8`. Zero Tier 1 pins remain.

## The two convergence gates

`test_resync_lets_full_run_replay_without_cascade_death` (89U) regressed
mid-campaign and **came back green on its own**, exactly as its temporary
`xfail(strict=False)` reason predicted. The mark is gone and it is a hard
assertion again. The cause was the sim becoming *more* faithful: the Late
energy-cost pass makes the recorded `UNRELENTING` → `BLUDGEON` sequence
playable, which changed the whole run trajectory until enough of the rest of
Tier 1 had landed. `test_free_attack_makes_a_three_cost_attack_playable` pins
the reason so it cannot silently revert.

## Found by the tools rather than by the queue

Two latent wrong-stream bugs the fixes *unmasked*, both caught by
`test_rng_tripwire`'s fuzz gate and neither in the queue:

- **`StampedePower`** drew its auto-play pick from the legacy shared rng where
  `StampedePower.cs:28` names `Rng.Shuffle`. Latent because the old listener
  order meant Stampede's auto-plays often did not fire.
- **`HavocCard`** picked its auto-play target from the shared rng where
  `CardCmd.cs:77` names `Rng.CombatTargets`.

Both are the class the tripwire exists to catch, and both were invisible until
a fix made the code path actually execute.

## Corrections made to the audit's own pins

Three pins were wrong and were corrected rather than worked around:

- `test_extra_turn_still_runs_the_turn_end_pipeline` listed
  `should_take_extra_turn` FIRST, which was the sim's old position;
  `CombatManager.cs:1364-1368` evaluates it inside
  `SwitchFromPlayerToEnemySide`, i.e. after both end-turn phases. The entry's
  own text said so and the source agreed.
- `monster_state_machine/G5`'s assertion contradicted its own comment about
  `SetMoveImmediate`.
- `monster_state_machine/G6`'s pin was unsatisfiable as written (its setup never
  logged the move the branch reads, and in legacy mode every `CombatRng`
  accessor is the same object, so "not off the shared stream" cannot hold).

## Partially closed, with the remainder named

- **`relic/_auto_keep`** — the driver now issues real take-or-skip decisions,
  but not every one of the 15 grant sites is rerouted.
- **`relic/_stub`** — 13 of 21 implemented. Five stay no-ops for reasons now
  written into their docstrings instead of a dead premise (prayer_wheel and
  white_star need a second pick-1-of-N reward group the rewards model cannot
  represent; cauldron needs a run-level declinable offer; punch_dagger and
  royal_stamp need the Momentum / Royally Approved enchantments, which are not
  registered). `massive_scroll` is correctly multiplayer-only.
- **`potion/foul_potion`** — the shop arm is ported; the Fake Merchant arm still
  discards the potion rather than using it.

## Engine surface added along the way

`HookSystem` gained a derived per-creature dispatch order and complete phase
passes (`_very_early` / `_early` / plain / `_late`), plus these hooks, each
mirroring a named C# one: `before_damage_received`, `before_potion_used`,
`should_power_be_removed_on_death`, `should_stop_combat_from_ending`,
`after_preventing_block_clear`, `after_modify_damage_amount`,
`after_modify_block_amount`, `after_auto_pre_play_phase_entered`,
`after_auto_post_play_phase_entered`. `on_death`, `on_card_played` and
`on_card_exhausted` gained the C# parameters they were missing
(`was_removal_prevented`, `is_auto_play`, `caused_by_ethereal`).

`RUN_OBS_SCHEMA_VERSION` moved 4 → 5: a new `DecisionKind` (the take-or-skip
relic offer) widened the leading phase segment, which shifts every later index.
The v3 → v4 lossless migration is still offered to v3 checkpoints; v4 → v5 is a
retrain.

---

# Progress — 2026-07-27

**Suite: 2637 passed / 2 failed / 35 xfailed** (baseline 2518 / 2 / 42). The 2
failures are the same pre-existing missing-fixture ones. **Pins 36 -> 28.**
101 files staged, +3304 / -738. Nothing committed.

## Closed and verified

| wave | entries | evidence |
|---|---|---|
| 0 | **20**, **21** | both pins XPASS; `_ordered()` + `_each()` in `hooks.py`, 64 dispatchers converted |
| 1 | **15**, **32**, **58**, **43** | 4 pins XPASS; sequential fold, per-listener props gates, `skip_next_tick` scoped |
| 5 | **2**, **64**, **67**–**75** | monster packages; `state_machine_probes.py mismatch` now 12/12 exact, 0 misreads |
| 6 | **1**, **4**, **6**–**9**, **11**, **44** | event RNG sweep + decimal gate + rest hooks |
| 8 | **47**, **52**, **53**, **54** | relic streams, StableShuffle, undo clamp, shop prices |

Also fixed, found by the tripwire rather than the queue: **StampedePower drew its
auto-play pick on the legacy shared rng** where `StampedePower.cs:28` names
`Rng.Shuffle`. Latent until entry 20 made Stampede's auto-plays run first and
reliably; `test_rng_tripwire` caught it immediately.

## Not done

- **Wave 1 remainder**: entry **33**'s machinery (`after_modify_block_amount`,
  the `modifiers` out-params) is in `hooks.py` and wired at both call sites, but
  Vambrace / Pael's Legion / Fasten are **not yet re-homed onto it**, so the
  entry is open and its pin still xfails.
- **Waves 2, 3, 4, 7, 9** untouched: entries 13, 14, 16–19, 22–31, 34–42,
  45, 46, 48–51, 55–57, 59–63, 46a–46l.

## The bookkeeping decision, and why `rehash` was NOT run

`audit_status` now reports **676 stale records**. That is correct and should
stay that way until the verdicts are re-derived. Running
`harness.py rehash --all` now would re-pin every record's sha256 against the
**new** code while its verdict still says `gap` — i.e. it would mark
already-fixed findings as freshly-verified-present. That is the exact
false-clear this pipeline exists to prevent, and the workflow's own verifier
flagged it: `audit/records/seam/monster_state_machine.json` still reads
"7 match and 5 MISREAD" when the probe now reports 12/12 and 0.

Order for whoever picks this up: flip the verdicts of the closed entries to
`faithful` (citing the fix), **then** `rehash --all`, **then** regenerate the
queue.

## Regression to re-check

`test_conformance_player_state.py::test_resync_lets_full_run_replay_without_cascade_death`
is marked `xfail(strict=False)` with the full evidence in its reason. It is the
sim becoming more faithful (the Late energy pass makes the recorded
UNRELENTING -> BLUDGEON sequence playable) and should XPASS back to green as the
remaining waves land. Drop the mark then. Do not revert the dispatch order.
