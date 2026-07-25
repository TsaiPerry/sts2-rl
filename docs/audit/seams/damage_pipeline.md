# Engine seam: `damage_pipeline`

Audited 2026-07-25 (Task 5 of the six seam audits, Tier 2 of the
source-audit-pipeline design). Verdicts and rationale live in
`audits/seam/damage_pipeline.json`; this file is the durable ordering spec
extracted from the C# source that the JSON record judges the sim against.

## Source correction (Step A)

`tools/audit/harness.py`'s `SEAM_SOURCES["damage_pipeline"]` originally listed
only `src/Core/Commands/DamageCmd.cs`. That file is real but contains only two
`AttackCommand`-builder factory methods (`DamageCmd.Attack(...)`) — no
pipeline logic. The actual per-hit pipeline (block order, modifier order,
kill order) lives in `CreatureCmd.Damage` (`src/Core/Commands/CreatureCmd.cs`),
dispatched through the static `Hook.*` methods it calls
(`src/Core/Hooks/Hook.cs`). The table was corrected to hash all three files;
the corrected table is staged in this branch.

### Scope boundary with `creature_card_cmds` (Task 7) — READ BEFORE TASK 7

The correction leaves `CreatureCmd.cs` listed under **two** seams, so the file
is split by region to keep the two audits from overlapping or contradicting
each other:

- **`damage_pipeline` (this record) owns `CreatureCmd.cs:240-572`** — the
  per-hit damage pipeline (`Damage`) plus `Kill` /
  `KillWithoutCheckingWinCondition`. Every numbered step below is drawn from
  that region.
- **`creature_card_cmds` (Task 7) should scope to the remainder of the file**
  — the other creature verbs (heal, stun, escape, block, power application
  helpers, …) — and should NOT re-audit the `Damage`/`Kill` region. If Task 7
  finds a `Damage`/`Kill` behavior this record missed, it belongs here as an
  amendment to `audits/seam/damage_pipeline.json`, not as a second verdict
  under a different unit id.

## Sim entry point

`sts2_rl.cmds.DamageCmd.deal(hooks, target, amount, dealer=None, card=None,
props=None)` — **one target per call.** `CreatureCmd.Damage` takes
`IEnumerable<Creature> targets` and batches multiple simultaneous targets in
one call (relevant to step 17/18 below); the sim's callers (card code,
`Monster._execute_attack`) loop over targets themselves and call `deal` once
per target, each a fully independent pipeline run. See guard **N2**.

## Numbered ordering spec (from `CreatureCmd.Damage`, `CreatureCmd.cs:240-412`,
and `CreatureCmd.Kill`/`KillWithoutCheckingWinCondition`, `CreatureCmd.cs:409,
439-572`)

0. **(pre-step, sim-only)** `should_allow_hitting` predicate — no single C#
   analogue inside `CreatureCmd.Damage`; see guard **N1**.
1. Guard: `dealer != null && dealer.IsDead` → return a zero-damage
   `DamageResult` for every target; no hook fires at all.
   `CreatureCmd.cs:242-245`. See guard **G5**.
2. Guard: empty target list → return no results. `CreatureCmd.cs:247-251`.
3. Per-target loop; guard: `originalTarget.IsDead` → skip (continue) this
   target. `CreatureCmd.cs:256-259`.
4. `Hook.ModifyDamage`: additive (sum) → multiplicative (product) → cap
   (min of any listener's cap), each phase iterating every hook listener;
   floor the result at 0. `Hook.cs:1486-1569` (`ModifyDamage`),
   `Hook.cs:2511-2558` (`ModifyDamageInternal`). Each listener self-gates on
   `props.IsPoweredAttack()` where it needs to (`ValuePropExtensions.cs:5-12`
   — `Move && !Unpowered`); the cap phase applies unconditionally to every
   damage type. The additive/multiplicative loops in C# are a **sequential
   chain** — each listener receives the running total including every
   earlier listener's contribution, not the pre-step base. See guards
   **G3**, **N3**.
5. Event: `AfterModifyingDamageAmount(modifiers)` — fires for the subset of
   listeners whose additive/multiplicative/cap call actually changed the
   value. `CreatureCmd.cs:262`; `Hook.cs:694`. See guard **G2**.
6. Event: `BeforeDamageReceived` — fires **unconditionally**, before block,
   before HP loss, before any death check, for every non-dead target.
   `CreatureCmd.cs:263`; `Hook.cs:403-408`. The **only** current override in
   the whole codebase is `ThornsPower.BeforeDamageReceived`
   (`ThornsPower.cs:17-24`), gated on
   `props.IsPoweredAttack() || cardSource is Omnislice`. See guard **G1**.
7. Block absorption: `Creature.DamageBlockInternal` — `Unblockable` flag →
   0 blocked; else `min(Block, amount)`; `Block -= blocked`.
   `CreatureCmd.cs:264-265`; `Creature.cs:430-435`. (Block belongs to
   `PetOwner` if the target has one — Osty/pet redirection, waiver, see N2.)
8. `Hook.ModifyHpLost`, `BeforeOsty` phase — chain-modifies
   `max(modifiedAmount - blockedDamage, 0)`. `CreatureCmd.cs:266`;
   `Hook.cs:1717+`.
9. Event: `AfterModifyingHpLostBeforeOsty(modifiers)`. `CreatureCmd.cs:267`;
   `Hook.cs:754`. See guard **G2**.
10. Osty pet-damage redirection: `Hook.ModifyUnblockedDamageTarget` may
    retarget the unblocked HP loss to a pet owner. `CreatureCmd.cs:268`;
    `Hook.cs:2048`. Waiver — no pet/companion system in the Ironclad-only
    sim.
11. `Hook.ModifyHpLost`, `AfterOsty` phase — re-run on the (possibly
    redirected) target. `CreatureCmd.cs:269`.
12. Event: `AfterModifyingHpLostAfterOsty(modifiers)`. `CreatureCmd.cs:270`.
    See guard **G2**.
13. Apply: `Creature.LoseHpInternal` mutates `CurrentHp` and computes
    `UnblockedDamage` / `WasTargetKilled` / `OverkillDamage`.
    `WasTargetKilled = CurrentHp > 0 && amount >= CurrentHp`, evaluated
    **before** the subtraction — a pure arithmetic snapshot, not gated by
    any death-prevention hook. `CreatureCmd.cs:271`; `Creature.cs:445-457`.
14. `WasBlockBroken = originalTarget.Block <= 0 && blockedDamage > 0`;
    `WasFullyBlocked = !Unblockable && (blockedDamage>0 || Block>0) &&
    unblockedDamage==0` — computed from the already-decremented `Block`.
    `CreatureCmd.cs:273-274`.
15. Osty overkill split: if the HP-loss target differs from the original
    target, a second `LoseHpInternal` call assigns `OverkillDamage` back to
    the original target. `CreatureCmd.cs:275-290`. Waiver (pet/multiplayer).
16. Per-result loop: VFX/SFX/history/screen-shake bookkeeping only — no
    gameplay-logic hooks fire here. `CreatureCmd.cs:291-369`. Waiver
    (presentation).
17. **Second, separate loop over every result from every target in the
    batch** (all targets have already completed steps 4-16 above):
    1. Event: `AfterBlockBroken`, if `WasBlockBroken`. `CreatureCmd.cs:376-379`.
       Fires **after** HP loss has already been applied (step 13), unlike the
       sim's `on_block_broken` (fires during step 7, before HP loss). See
       guard **N5**.
    2. Event: `AfterCurrentHpChanged`, if `UnblockedDamage > 0`.
       `CreatureCmd.cs:380-383`.
    3. `dealer.Player.ExtraFields.DamageDealt` stat bump — telemetry, not
       gameplay logic. `CreatureCmd.cs:384-387`. Waiver.
    4. Event: `AfterDamageGiven` (dealer side) — fires whenever
       `combatState != null`, **regardless of `WasTargetKilled`**.
       `CreatureCmd.cs:388-391`.
    5. **Killing-blow guard:**
       `if (!WasTargetKilled || !originalTarget.IsDead) AfterDamageReceived(...)
       else killedCreatures.Add(originalTarget)`. The skip decision is
       locked in **here**, using the state as of this loop — **before**
       `Kill()` (and therefore before any `ShouldDie`/`ShouldDieLate`
       death-prevention listener) has run. `CreatureCmd.cs:392-399`. See
       guard **G4**.
    6. VFX for fully-blocked hits. `CreatureCmd.cs:400-407`. Waiver.
18. `await Kill(killedCreatures)` — runs **after** every target in the batch
    has already had its `AfterDamageGiven`/`AfterDamageReceived`-or-skip
    resolved (step 17). Internally, per creature
    (`KillWithoutCheckingWinCondition`, `CreatureCmd.cs:489-572`):
    `Hook.BeforeDeath` → `Hook.ShouldDie` (early-phase listeners) →
    `Hook.ShouldDieLate` (late-phase listeners, e.g. `LizardTail.ShouldDieLate`,
    `LizardTail.cs:40-47`) — any `false` prevents death
    (`Hook.cs:2229-2249`). On death: `InvokeDiedEvent`, `AfterDeath`, corpse
    removal (`ShouldCreatureBeRemovedFromCombatAfterDeath`), power removal.
    On prevention: `AfterDeath(wasRemovalPrevented: true)` +
    `AfterPreventingDeath` — **no generic HP reset happens in `Kill()`
    itself** (HP was already zeroed by step 13); the preventer's own
    `AfterPreventingDeath` override is entirely responsible for restoring
    HP (e.g. `LizardTail.AfterPreventingDeath`, `LizardTail.cs:49-55`, heals
    to 50% max HP). See guard **G4**.

## Sim comparison (Step C summary — full verdicts in the JSON)

The sim's `DamageCmd.deal` (`sts2_rl/cmds.py:30-117`) numbers its own steps
1-8 in-source; they line up with the C# spec as: 1↔4, 2↔6/7 (cap always
applies, matching C#), 3↔6 (`on_attacked`↔`BeforeDamageReceived`), 4↔7
(block), 5↔8/11 (`modify_hp_lost`, collapsed BeforeOsty/AfterOsty into one
call — faithful, since Osty redirection is waived), 6↔13 (apply +
`should_die`, collapsed with step 18's `Kill()`), 7↔17e/18 (post-damage
events + kill, collapsed into a single guard `if not target.is_dead`).

**Note added in review — step 3↔6's call-site gate is narrower than C#'s.**
C# calls `BeforeDamageReceived` **unconditionally** (`CreatureCmd.cs:263`) and
lets each listener self-gate; the sim gates the `on_attacked` call itself on
`amount > 0 and ValueProp.MOVE in props` (`cmds.py` step 3). That is the same
pipeline-level-filter shape as **G3**, applied to a different event. It stays
`faithful` today only because Thorns is this event's sole listener anywhere,
its own self-gate (`IsPoweredAttack() || cardSource is Omnislice`) is a strict
subset of the sim's MOVE condition, and Omnislice's damage keeps the MOVE
flag — so no ported content diverges. A future `BeforeDamageReceived`-
equivalent listener that is *not* MOVE-gated would silently inherit this
filter; re-check this step when porting one.

**Gaps found** (full detail in the JSON `guards` entries; short form here):

- **G1 — `ThornsPower` wired to the wrong hook.** C#'s `ThornsPower`
  overrides `BeforeDamageReceived` (spec step 6: unconditional, pre-block,
  pre-death). The sim's `ThornsPower` (`sts2_rl/powers.py:328-353`) hooks
  `on_damage_received` (spec step 17e: killing-blow-guarded, post-block,
  post-death-resolution) instead. Two observable consequences: (a) Thorns
  does **not** reflect on the hit that kills its owner in the sim, but does
  in the real game; (b) the sim's `ThornsPower.on_damage_received` has no
  `is_powered_attack`/Omnislice-equivalent gate at all, so it would
  incorrectly reflect against Unpowered, dealer-attributed damage that C#
  excludes. Pinned with an `xfail` in `test/test_hook_order.py` (part (a)).
- **G2 — no `AfterModifyingXxx(modifiers)` machinery.** Spec steps 5, 9, 12
  have no sim counterpart at all — the sim's modifier hooks
  (`modify_damage_additive/multiplicative/cap`, `modify_hp_lost`) return an
  aggregated value with no companion "who actually changed this" event.
  This is not merely a VFX gap: C#'s `BufferPower.AfterModifyingHpLostAfterOsty`
  (`BufferPower.cs:29-32`) uses exactly this event to decrement its own
  stack **only on the hit(s) where it actually reduced HP loss to 0** — that
  power cannot be ported faithfully without adding this machinery. Currently
  dormant (BufferPower is unported).
- **G3 — pipeline-level `is_powered_attack` gate for additive/multiplicative
  dispatch.** The sim gates the *entire* `modify_damage_additive`/
  `modify_damage_multiplicative` call behind `is_powered_attack(props)`
  (`cmds.py:56-58`). C#'s `ModifyDamageInternal` always calls every
  listener for every damage type and leaves the `IsPoweredAttack` check to
  each implementation (`Hook.cs:2515-2538`). All three of Strength/
  Vulnerable/Weak self-gate identically in both places (faithful). But the
  already-ported `SurroundedPower` (Kaiser Crab's back-attack multiplier,
  `sts2_rl/powers.py:2523-2565`, mirroring `SurroundedPower.cs:46-72`) does
  **not** self-gate on `IsPoweredAttack` in either source — so an Unpowered,
  dealer-attributed hit against a Surrounded player would still get the
  1.5× multiplier in C# but silently skip it in the sim (the whole hook
  call is skipped at the pipeline level). Currently dormant: Kaiser Crab's
  own attacks (`Rocket.cs`) never set the Unpowered flag.
- **G4 — killing-blow skip decision recomputed after death-prevention.** C#
  locks the `AfterDamageReceived`-skip decision to the pre-`Kill()` snapshot
  (spec step 17e) — a hit that was arithmetically lethal permanently skips
  it, even if `ShouldDie`/`ShouldDieLate` later prevents the death. The sim
  resets HP to 1 first (inside the same apply step) and only *then* checks
  `target.is_dead` for the `on_damage_received` guard — so a prevented
  death does **not** skip `on_damage_received` in the sim. Evidenced by the
  ported `LizardTail` (`sts2_rl/relics/lizard_tail.py`) combined with any
  `on_damage_received`-gated power on the same creature (e.g. the player's
  own Thorns, if granted this run).
- **G5 — no `dealer.IsDead` backstop in `DamageCmd.deal` itself.** C#'s
  `CreatureCmd.Damage` refuses to process any hit from an already-dead
  dealer (spec step 1) as a hard backstop, independent of caller discipline.
  The sim's `DamageCmd.deal` has no such guard; it relies entirely on call
  sites to check `is_dead` between hits of a multi-hit/multi-target attack.
  Spot-checked call sites currently do this correctly
  (`sts2_rl/monsters/base.py:114-117`, `sts2_rl/cards/whirlwind.py:43-49`),
  so no concrete failure is demonstrated, but the pipeline itself provides
  no defense-in-depth guarantee the way `CreatureCmd.Damage` does.

**Lower-severity / no-current-effect notes** (`deliberate-divergence` or
`waiver`, see JSON for rationale): **N1** `should_allow_hitting` vs upstream
`IsAlive` filtering; **N2** single-target-per-call vs C#'s batched
multi-target semantics for step 17/18 (cross-reference the `creature_card_cmds`
seam, Task 7); **N3** parallel-sum/product additive-multiplicative dispatch
vs C#'s sequential chain (safe today because every ported modifier is
amount-independent); **N4** `ShouldDie`/`ShouldDieLate` two-phase priority
collapsed to one phase (no second Ironclad-reachable listener exists yet);
**N5** `AfterBlockBroken`/`on_block_broken` timing relative to HP
application (neither ported listener reads HP/death state).

## Existing test coverage (Step D)

- **Killing-blow hook skip** (non-Thorns case): `test/test_hook_order.py::
  TestDamagePipelineOrder::test_killing_blow_skips_on_damage_received`
  (added in Task 4) and `test/test_hive.py::
  test_hive_generates_no_dazed_on_killing_blow`. Recorded, not duplicated.
- **Unpowered damage skips modifiers**: `test/test_powers.py::TestStrength::
  test_does_not_apply_to_unpowered_card` (and
  `test_strength_not_applied_to_unpowered_burn_card`, line 680) already
  cover the additive case end to end. Recorded, not duplicated.
- **Unblockable skips block**: no existing test isolates block absorption
  from a nonzero starting `Block` with a direct `DamageCmd.deal` call — the
  closest (`test_powers.py::TestPoison::
  test_deals_unblockable_damage_on_enemy_turn_start`) is confounded by
  block being cleared at turn start regardless of Poison, per its own
  comment. New direct pin added:
  `test/test_hook_order.py::TestDamagePipelineOrder::
  test_unblockable_skips_block_absorption`.
- **G1 (Thorns killing-blow gap)**: new `xfail` pin added:
  `test/test_hook_order.py::TestDamagePipelineOrder::
  test_thorns_reflects_even_on_killing_blow` — asserts the C#-correct
  behavior, marked `xfail` referencing this gap.
