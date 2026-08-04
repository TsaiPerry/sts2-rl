# Ironclad fidelity-closure baseline (Task 0)

Date: 2026-08-03
HEAD commit: `77fbbc004a9299c9ba158ddd3872b55548faf43e`

## 1. Pytest suite summary

Command: `py -m pytest test/ -q`

```
4652 passed, 4 xfailed, 3 warnings in 286.99s (0:04:46)
```

(Two warnings observed about `obs segment 'select.candidates'` row overflow/truncation in
`test_run_obs_v4.py` and `test_select_candidate_actions.py` — pre-existing, expected.)

## 2. Triage baselines

### 89U21BV1TZ / floor_49 (`py tools/converge_triage.py 89U21BV1TZ floor_49 2`)

Run 1 and run 2 were IDENTICAL. Full output (run 1, representative of both):

```
=== 89U21BV1TZ/floor_49 (stop_after_act=2) ===
forced_combats=0  unresolved_play_card_ids=[]

[DETECTOR 2] stream counter diffs: 0

[DETECTOR 3] player-state deltas at act boundaries: 0

[DETECTOR 4] per-floor state deltas (3 checkpoints, resync ON — each floor's deltas are INDEPENDENT bugs): 0 divergent floor(s)

[DETECTOR 1] in-combat draws from the UNSEEDED shared rng (wrong-stream bugs): 0 site(s)

  (benign constructor HP rolls, overwritten by Niche parity roll: 38 site(s) / 50 draws)

=== FULLY CONVERGED ===
```

### 933T39V18D / floor_49 (`py tools/converge_triage.py 933T39V18D floor_49 2`)

Run 1 and run 2 were IDENTICAL. Full output (run 1, representative of both):

```
=== 933T39V18D/floor_49 (stop_after_act=2) ===
forced_combats=0  unresolved_play_card_ids=[]

[DETECTOR 2] stream counter diffs: 3
  Shuffle: expected 909 got 892 (sim under-drew 17)
      -> source: Commands/CardPileCmd.cs
         rule:   Deck reshuffle (StableShuffle) + random draw-pile insertion (CardPilePosition.Random => Rng.Shuffle.NextInt(Count+1)).
  CombatCardSelection: expected 8 got 9 (sim over-drew 1)
      -> source: Cards/Thrash.cs, Commands/CardPileCmd.cs:946, etc.
         rule:   Card AI picks (exhaust-an-Attack, random draw-pile autoplay) draw here.
  CombatTargets: expected 26 got 25 (sim under-drew 1)
      -> source: (auto-play random targeting)
         rule:   Random ANY_ENEMY target for auto-played cards.

[DETECTOR 3] player-state deltas at act boundaries: 1
  act 2 player_hp: expected 67 got 80 (sim high by 13)
      -> damage/heal pipeline (DamageCmd/BlockCmd, relic heals like BurningBlood on_combat_end, rest-site heal).

[DETECTOR 4] per-floor state deltas (49 checkpoints, resync ON — each floor's deltas are INDEPENDENT bugs): 2 divergent floor(s)
  floor 47: hp, counter_CombatTargets
      floor_hp: expected 74 got 66
      floor_counter_CombatTargets: expected 21 got 22
  floor 49: hp, counter_Shuffle, counter_CombatCardSelection
      floor_hp: expected 80 got 67
      floor_counter_Shuffle: expected 892 got 909
      floor_counter_CombatCardSelection: expected 9 got 8

[DETECTOR 1] in-combat draws from the UNSEEDED shared rng (wrong-stream bugs): 0 site(s)

  (benign constructor HP rolls, overwritten by Niche parity roll: 32 site(s) / 37 draws)

=== DIVERGENCES REMAIN ===
```

These numbers match the brief's "Verified starting facts" exactly (floor 47 hp 74 vs 66,
CombatTargets 21 vs 22; floor 49 hp 80 vs 67, Shuffle 892 vs 909, CombatCardSelection 9 vs 8;
DETECTOR 2 Shuffle 909/892, CombatCardSelection 8/9, CombatTargets 26/25; DETECTOR 3 act 2
hp 67 vs 80). No premise drift.

## 3. Audit status table

Command: `py audit/tools/audit_status.py`

```
kind         total  audited  invalid  stale  gaps  live  unaudited
affliction       7        7        0      0     1     0          0
card           203      202        0    159    27     0          1
character        5        5        0      0     0     0          0
enchantment     20       20        0     19     0     0          0
encounter       85       85        0     59    13     0          0
event           65       65        0     62     7     0          0
monster        109      109        0     88     2     0          0
potion          51       51        0     51     6     0          0
power          138      138        0    138    65     0          0
relic          260      260        0    255    90     0          0
seam            12       12        0     12    10     0          0
```

Stale column sums to 843 (159+19+59+62+88+51+138+255+12 = 843), matching the expected
"~843" figure.

## 4. Gap queue counts

Command: `py audit/tools/gap_queue.py counts`

```
gap entries        : 347
  labelled live    : 0
  labelled dormant : 347
  unlabelled       : 0 (inherit their mechanism's liveness)
  in a LIVE mech   : 0
  in a dormant mech: 347
distinct mechanisms: 322
  with a live entry: 0
  pinned           : 0
  unpinned         : 322
strict xfail pins  : 0 (of 0 xfail decorators in test/test_hook_order.py)

per kind (records / gap entries / mechanisms anchored / live entries):
  seam             12 /   34 /   29 /    0
  power           138 /   94 /   93 /    0
  card            202 /   29 /   29 /    0
  event            65 /    7 /    7 /    0
  enchantment      20 /    0 /    0 /    0
  relic           260 /  151 /  146 /    0
  monster         109 /    2 /    1 /    0
  potion           51 /   15 /   12 /    0
  encounter        85 /   14 /    4 /    0
  affliction        7 /    1 /    1 /    0
  character         5 /    0 /    0 /    0
  NOT AUDITED  : none -- all 10 content kinds and 12 seams have records (first true 2026-07-27)

per seam record (entries / mechanisms anchored there / live entries):
  damage_pipeline            1 /   1 /   0
  power_cmd                  6 /   5 /   0
  creature_card_cmds         9 /   7 /   0
  turn_structure             2 /   3 /   0
  hook_dispatch              8 /   5 /   0
  monster_state_machine      0 /   0 /   0
  rng_streams                1 /   1 /   0
  rewards                    1 /   1 /   0
  relic_pools                3 /   3 /   0
  potion_pipeline            2 /   2 /   0
  run_layer                  1 /   1 /   0

largest mechanisms:
  encounter/_all_possible_monsters     n=  9 dormant  kinds=encounter
  potion/_strength_applier             n=  4 dormant  kinds=potion
  damage_pipeline/G2                   n=  3 dormant  kinds=seam
  hook_dispatch/N5                     n=  3 dormant  kinds=seam
  creature_card_cmds/N3                n=  2 dormant  kinds=seam
  creature_card_cmds/N9                n=  2 dormant  kinds=seam
  encounter/_slot_row_unpopulated      n=  2 dormant  kinds=encounter
  encounter/nibbits_normal/Slots       n=  2 dormant  kinds=encounter
  hook_dispatch/G3                     n=  2 dormant  kinds=power,relic
  hook_dispatch/G7                     n=  2 dormant  kinds=seam
  power/_death_prevention_branch       n=  2 dormant  kinds=monster,power
  relic/_is_allowed                    n=  2 dormant  kinds=relic
```

347 entries / 322 mechanisms / 0 live — matches expectation exactly.

## 5. Date and HEAD commit

- Date: 2026-08-03
- HEAD: `77fbbc004a9299c9ba158ddd3872b55548faf43e`

## Adjudication summary (Task 4, collapsed to verification — 2026-08-04)

Every baseline divergence signal was classified and resolved in Task 3; NO
real sim gap survived. One line each (full evidence: .superpowers/sdd/task-3-report.md):

- D2 Shuffle 909/892, CombatCardSelection 8/9, CombatTargets 26/25 — harness
  artifact (resync cascade from floor 47's bad backup + final-floor pin); fixed.
- D3 act-2 player_hp 67 vs 80 — same cascade corrupting the resync-ON arm's
  run.hp; the resync-OFF arm was never wrong; fixed.
- D4 floor 47 (hp 74/66, CombatTargets 21/22) — capture artifact: the floor-47
  backup save's hp (74) is unreachable from any oracle; sim agrees with
  map_point_history (66); excluded by _is_inconsistent_floor_save (which
  requires sim-agrees-with-history before excluding).
- D4 floor 49 (hp 80/67, Shuffle 892/909, CCS 9/8) — structural wrong-moment
  comparison (entry-style backup vs post-room state); final checkpointed floor
  now skips both diff and resync; the true post-room oracle (run-END save) is
  covered by DETECTORS 2/3.
- D5 room 12 (elite, 66 vs 74) — symptom of the same resync cascade; gone
  after the fixes; resync-OFF sim was always correct here.
- D5 terminal boss room (0/0/0) — capture artifact present in BOTH seeds'
  recordings; skipped by the all-zero + sim-side-tiebreak reachability guard.

Post-fix state: 89U21BV1TZ and 933T39V18D both print FULLY CONVERGED
(verified twice each by the implementer and once each independently by the
controller); suite 4662 passed / 0 failed / 4 xfailed.

Ledger-trust note: the divergences adjudicated here were all instrument
artifacts, so no audit-record verdict was proven wrong — the 347 dormant
labels' trust calibration is unchanged by this phase.

## Final verification (Task 9, 2026-08-04)

- Triage: 89U21BV1TZ and 933T39V18D each ran 3x — six of six runs printed
  FULLY CONVERGED (all detectors, resync ON arm; the resync-OFF arm is
  gated in test_conformance_hard_gates.py).
- Hard gates: 5/5 passed (2 seeds x 2 resync arms + predicate unit test).
- Full suite: 4671 passed / 0 failed / 4 xfailed (baseline was 4652; +19 =
  the new tests added by Tasks 1-6).
- Audit ledger: 954 records, 0 stale, 0 invalid, all 10 kinds + 12 seams.
- Gap queue: 325 entries (1 live: card/mad_science GainsBlock, fix recipe
  queued; 324 dormant; 0 unlabelled), 300 mechanisms; counts/coverage/
  cite-check all exit 0.
