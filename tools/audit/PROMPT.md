# Audit prompt — source-to-sim unit audits (v4)

> **v2 (2026-07-26, relic Tier 1 pilot):** bug classes 11–16 added, all six
> drawn from defects the pilot batch actually found. Classes 11, 12 and 14
> each caught a LIVE gap that reading the sim's own docstrings would have
> talked you out of.
>
> **v3 (2026-07-26, relic pool-wide sweeps):** added the
> "Sweep the shape before you audit the units" procedure section. Classes
> 12, 13 and 16 turned out to be pool-wide shapes; sweeping all 258 relics
> for them cost ~1 h and found two live gaps and a 16-relic single-fix
> cluster that per-unit batches would have taken sixteen batches to reach.
>
> **v4 (2026-07-26, relic batch 3):** class 17 added — shallow card "clones"
> that drop per-instance state. Found as `burning_sticks` G3, then swept
> (`sweep-clone`) and found to be five sites across three kinds. Class 18
> added — a port that implements the source's `TestMode.IsOn` branch;
> `calling_bell` grants three fixed relics where the game pulls three from
> the pool.

You are auditing ONE ported unit for behavioral fidelity: the decompiled C#
model (ground truth) vs the sim implementation. You judge; the harness only
checks completeness. Read BOTH files fully before writing any verdict.

## Procedure

1. `py tools/audit/harness.py skeleton <kind>/<id>` (skip if the record
   exists from a previous incomplete pass — then re-read it critically).
2. Read the C# file top to bottom. List for yourself: every override, every
   guard clause / early return, every numeric constant (take the
   NON-ascension branch of `AscensionHelper.GetValueIfAscension(...)`),
   every state field and when it resets.
3. Read the sim counterpart the same way.
4. Fill the record: for each hook, `maps_to` (the sim method(s) — the sim
   re-architects, so one C# hook may map to a bracket of sim hooks) and a
   verdict. Record guard-level findings in `guards` — one entry per guard
   that needed thought, not only per problem.
5. Verdicts: `faithful` | `waiver` (unreachable in Ironclad-only sim scope —
   rationale required) | `deliberate-divergence` (sim models it differently
   on purpose — rationale required) | `gap` (real divergence — `issue`
   required, describing the observable wrong behavior). NEVER fix engine
   code during an audit; record the gap.
6. `py tools/audit/harness.py validate audits/<kind>/<id>.json` must pass.

## Known bug classes — check EVERY one against your unit

1. **Hook order at seams**: effects that must precede/follow Artifact
   interception, block absorption, or death checks (Unsettling Lamp fired
   through an Artifact-negated debuff).
2. **Killing-blow guards**: C# often skips the victim's after-damage hooks
   on death (`CreatureCmd.cs:392`-style `!WasTargetKilled || !IsDead`).
3. **Sign-aware power typing**: `GetTypeForAmount(amount)` — negative
   Dexterity IS a Debuff; `power_type` class attrs alone miss this.
4. **Visibility guards**: `power.IsVisible` gates several relic triggers.
5. **Temporary-power double-dip**: `ITemporaryPower.InternallyAppliedPower`
   (doubling a wrapper must not also double its internal power).
6. **State-machine int args**: `AddBranch` integers are weight OR cooldown
   OR maxRepeats depending on position/overload — misreading produced the
   TwigSlimeM/Flyconid bug. Verify against the RandomBranchState overloads.
7. **Pile limbo**: a card mid-OnPlay is in `PileType.Play`, so a reshuffle
   it triggers excludes it.
8. **Append position**: out-of-combat transform APPENDS at deck end
   (`CardCmd.cs:437`); random picks are StableShuffle + take-first;
   StableShuffle ties keep incoming order, sorted on UPPERCASE id.
9. **Per-Replay iteration**: the game builds a fresh CardPlay per Replay
   loop iteration; the sim fires `before_card_played` once per play.
10. **Reset timing**: when does per-combat/per-turn state clear —
    BeforeCombatStart vs AfterCombatEnd vs turn boundaries; compare exactly.
11. **The sim's own mapping docstrings are evidence, not truth.** The hook
    table in `sts2_rl/relics/base.py:10-18` says `BeforeSideTurnStart (player)
    → on_player_turn_start`. It is WRONG: executed order (`py
    tools/audit/relic_probes.py turn-order`) is `on_block_cleared →
    on_energy_reset → on_player_turn_start → modify_hand_draw →
    on_player_turn_started`, so `on_player_turn_start` sits at
    `turn_structure` step ~18, not step 9. Two relics in the pilot inherited
    the confusion. **Never verdict a hook mapping off a docstring — print the
    real order and diff it against `audits/seam/turn_structure.json`'s steps.**
12. **A port that does nothing usually justifies itself with a claim about the
    sim — check the claim.** Two pilot units were no-op stubs resting on
    premises that are false today: Amethyst Aubergine's "the sim has no gold"
    (it has `RunState.gold`, a rewards screen that grants it, and the exact
    `modify_combat_rewards` hook the port needs) and Big Mushroom's "RunState
    has no run-level AfterObtained dispatch" (`run.py:552` calls it, and the
    sibling relic from the same event uses it). Both were LIVE gaps. Grep the
    sim for the capability the docstring says is missing **before** accepting a
    stub, and check whether a sibling unit already does the thing.
13. **Missing reset ≠ gap; missing reset with nothing shadowing it = gap.**
    Sim relic instances live on `RunState.relics` and are re-attached to every
    combat, so a dropped `BeforeCombatStart`/`AfterCombatEnd` reset latches for
    the whole run. Three pilot units dropped one: Unsettling Lamp and Art of
    War are safe (a combat-start reset / an unconditional turn-start clear runs
    before any reader), Belt Buckle is a live gap that disables the relic from
    combat 2 onward. **Trace to the first READER of the stale field**, then
    verdict.
14. **Unguarded `Card.upgrade()`.** `CardCmd.Upgrade` skips cards whose
    `IsUpgradable` is false (`CurrentUpgradeLevel < MaxUpgradeLevel`,
    `CardModel.cs:785-789`). The sim's `Card.upgrade()`
    (`cards/base.py:146-147`) is a bare `upgrade_level += 1` with no guard —
    35 ported cards (every curse and status) have `max_upgrade_level = 0`.
    Astrolabe calls it unguarded (live gap), Bellows guards it. Curses ARE
    transformable and roll into curses, so this is reachable.
15. **Paired hooks rarely carry the same guard set.** Unsettling Lamp checks
    applier, target side and `IsVisible` on its *latch*
    (`BeforePowerAmountChanged`) and none of the three on its *modifier*
    (`ModifyPowerAmountGivenMultiplicative`). The sim collapses both into one
    method and applies the UNION of the guards. Whenever the sim maps two C#
    hooks onto one method, **list both C# guard sets side by side** and
    verdict each difference; the collapse is where the divergence hides.
16. **Two whole C# concepts have no sim counterpart at all** — check every
    unit for them rather than rediscovering them per unit:
    `RelicModel.IsAllowed(runState)` pool-eligibility overrides (e.g.
    `IsBeforeAct3TreasureChest`, `RelicModel.cs:452-456`) have no `is_allowed`
    on `Relic`; and callers that name an RNG stream in C#
    (`CreateRandomCardForTransform(..., Rng.Niche)`) often reach a sim helper
    whose stream argument defaults to `None` and silently falls back to the
    legacy shared `random.Random` (`run.transform_card`'s `pick_rng`). The
    second is invisible outside the conformance harness — check it anyway.
    *Do not assume it fires whenever a stream is named:* `claws` passes
    `PlayerRng.Transformations` to `CardCmd.Transform`, but every
    `CardTransformation` it builds carries an explicit `Replacement`, so
    `GetReplacement(rng)` never touches the Rng (`CardTransformation.cs:55-59`)
    and neither side draws. Check whether the stream is *consumed*, not
    whether it is named.
17. **A "clone" that is a rebuild.** `CardModel.CreateClone()` is
    `ClonePreservingMutability()` (`CardModel.cs:2168-2179`) and carries the
    card's enchantment, affliction, keyword edits and local energy-cost
    modifiers as well as its upgrade level. The sim has **no clone helper**;
    all five ports rebuild from the id/class and replay the upgrades, so only
    the level survives (`burning_sticks` G3, LIVE — executed: an enchanted,
    afflicted, cost-modified Defend clones to `enchantment=None`,
    `affliction=None`, `energy_cost` back to 1). It is reachable inside one
    combat with no second relic, because five ported enemy powers afflict
    cards in hand. Pool-wide list: `py tools/audit/relic_probes.py
    sweep-clone`; it spans relics, cards (Dual Wield) and powers, so the card
    and power streams should re-run it rather than rediscover it.
18. **`TestMode.IsOn` branches are not the shipping behaviour.** Several
    models fork on it, and the test arm is the readable one — fixed lists
    instead of pool rolls. `TestMode.TurnOnInternal` (`TestMode.cs:38`) is
    documented "NEVER CALL THIS" and has no caller anywhere under `src/`, so
    the shipping game always takes the other arm. `calling_bell` ported the
    test arm: it grants Anchor + Gremlin Horn + Mummified Hand where the game
    pulls one Common, one Uncommon and one Rare from the grab bag — wrong
    relics *and* three unconsumed `PullNextRelicFromFront` draws, which shifts
    every later pull. `cauldron`'s C# has the same fork (a fixed five-potion
    list vs five pool rolls) and is the next place to get it wrong. Whenever a
    C# body has two arms, check which one ships **before** reading the code.

## Sweep the shape before you audit the units

Classes 12, 13 and 16 are **pool-wide shapes**, not per-unit quirks: the same
mistake repeats across dozens of ports, and finding it fifteen units at a time
wastes the budget. Before a kind's second batch, run one cheap scan per shape
over the whole roster and let the batches confirm rather than discover.

`tools/audit/relic_probes.py` has the relic versions and is the template —
`sweep-reset` / `sweep-reset-exec` (class 13), `sweep-isallowed` (class 16),
`sweep-stubs` / `sweep-stub-premises` (class 12), `sweep-upgrade` (class 14),
`sweep-clone` (class 17); findings in
`.superpowers/sdd/content-relic-sweeps.md`. They cost ~1 h and turned up two
live gaps (`centennial_puzzle`, `paels_eye`) that batch 1 could not have seen,
plus a 16-relic single-fix cluster. **Write the equivalent for your own kind.**

Two rules learned building them, both the hard way:

- **Scan the MRO, not the class body.** Several ports implement their behaviour
  in a shared intermediate base (`relics/_eggs.py`'s `EggRelic`). A body-only
  scan reported all three egg relics as unimplemented stubs. A sweep that
  over-reports is worse than useless as a work list.
- **Diff the observable, not just the object.** `belt_buckle`'s stale flag
  settles at the same value on a carried and a fresh instance; the divergence
  is 2 Dexterity on the *player*. Snapshot the game state the unit can move,
  or the sweep will clear its own founding example.

## Recording lessons

Add a bug class here only when a unit actually exhibited it, and say which
unit. A checklist entry that never fired is noise the next 700 units pay for.

## Scope

Potions: out of scope entirely. Ascension values: out of scope. Characters
other than Ironclad: `waiver` with rationale. Multiplayer-only params
(PlayerChoiceContext etc.): note in `maps_to` mapping, not a divergence by
themselves.
