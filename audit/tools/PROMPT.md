# Audit prompt — source-to-sim unit audits (v6)

> **v6 (2026-07-26, after relic batches 9–13):** bug classes 24–29 added, each
> from a defect a batch actually exhibited. Three binding items:
>
> **1. A POOL-WIDE SWEEP MAY ESCALATE A CANDIDATE. IT MAY NEVER CLEAR ONE.**
> Ten batches used the relic sweeps and **eight distinct defects** came back —
> six in sweep A, one in B, one in C. Every one was found by a batch auditing a
> unit on its merits; none by reviewing the tooling. **Three produced false
> clears**, the direction nothing downstream re-checks: an unstimulated execution
> driver cleared `red_skull`, whose un-reset flag makes combat 2 open with
> **Strength −3**; an incomplete C# hook census cleared `permafrost` (0 block vs
> 7); a construction-time-only snapshot cleared `paels_legion`. Two more were
> **under-reports** where a mechanical check silently did nothing at all: sweep B
> read only the first *line* of a C# method body, and sweep C compared PascalCase
> C# hook names against snake_case `vars(HookSystem)` keys, so its "is this a
> real hook?" branch was dead code. When you write a sweep: never give a bucket a
> label that makes a safety claim ("safe only if…") without executing the claim,
> and prefer reporting `INCONCLUSIVE` over reporting agreement.
>
> **2. `RelicModel.IsAllowedAtNeow` DEFAULTS to `IsAllowed(player.RunState)`**
> (`RelicModel.cs:443-446`). The sim models the two as independent members, so
> whoever fixes the 17-relic `is_allowed` pool gate must make
> `is_allowed_at_neow` delegate, or Neow will silently keep using a stale flag.
>
> **3. Rule-3 resolution — `undo_after_obtained`.** Its **absence** is
> `faithful` at every site: the helper has no C# counterpart (nothing in the game
> un-picks a relic), so a sim lacking it is not diverging from the source, which
> is the only question this audit asks. It is not a waiver either — a waiver is
> in-scope-adjacent and declined, and here there is no source behaviour to be
> faithful to. Keep flagging the operational consequence in the entry text (a
> missing undo breaks the conformance runner's relic swap and its DETECTOR 3 HP
> assertion) — that is a tooling defect, not a fidelity gap. **Distinct
> mechanism, still a gap:** an `undo_after_obtained` that EXISTS and *clamps*
> instead of subtracting violates its own stated contract (`mango` G1,
> `lees_waffle` N4, `looming_fruit` N3 — and all five implementers do it).

> **v5 (2026-07-26, after relic batches 4–8 ran as five concurrent subagents):**
> bug classes 19–23 added, each from a defect a batch actually found. Two
> calibration facts that cost real time are now stated outright — the
> **`GetValueIfAscension` argument order** below, and the fact that **a sweep's
> own output is evidence, not authority**. Sweeps A and B were both found
> unsound by the batches that used them and have been rewritten; see
> `.superpowers/sdd/content-relic-sweeps.md`. If a sweep's bucket label makes a
> safety claim ("safe only if…"), either test the claim or do not put units in
> that bucket.
>
> **`AscensionHelper.GetValueIfAscension(level, ascensionValue, fallbackValue)`
> puts the ASCENSION value SECOND and the non-ascension value THIRD.** Reading a
> call left-to-right takes the first numeric as the base and gets it backwards;
> a batch nearly filed a correct sim value as a gap on that basis. Non-ascension
> is the **last** argument.

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

1. `py audit/tools/harness.py skeleton <kind>/<id>` (skip if the record
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
6. `py audit/tools/harness.py validate audit/records/<kind>/<id>.json` must pass.

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
19. **A docstring that misquotes the *source* — not the sim.** Class 12 covers a
    false claim about what the sim can do. This is the other direction:
    `relics/iron_club.py` pins `CARDS = 6` and its docstring asserts
    "`CardsVar(6)`", where `IronClub.cs:38` is `new CardsVar(4)`. The wrong
    constant is *protected* by a citation that looks verified, so both readers
    and shape-level sweeps pass over it. Re-read every numeric against the C#
    even when the port names the C# expression — especially then.
20. **A hook can be dispatched from the wrong SITE, not just the wrong slot.**
    Class 11 is about turn-order slots. This is about *which branch* calls the
    hook at all. `Hook.ModifyGeneratedMapLate` has exactly one caller,
    `RunManager.cs:740`, inside the **save-load** arm of `GenerateMap`; the
    fresh-generation `else` arm calls `ModifyGeneratedMap` instead. `run.py:857`
    runs Late on every generation, so `fur_coat` re-rolls its marks and burns an
    extra shuffle. Method: grep every dispatch site of the C# hook and read its
    *enclosing branch*, not just its file. `Cards/SpoilsMap.cs:63` is the same
    exposure for the card stream.
21. **Death is not removal.** The whole game has four `ShouldDie` implementers —
    `FairyInABottle`, `LizardTail`, and two Mocks. `IllusionPower`,
    `SteamEruptionPower` and `AdaptablePower` implement
    `ShouldCreatureBeRemovedFromCombatAfterDeath`: the creature **really dies**,
    fires `AfterDeath`, stays in `Enemies` and revives later. The sim ports all
    three onto `should_die` (`powers.py:1566`, `:2016`, `:3365`), so it vetoes
    the death itself and `on_death` never fires — `gremlin_horn` pays nothing
    for a lethal hit on a Fogmog-summoned Eye With Teeth. Affects **every**
    `on_death` listener, so it is a cross-stream defect.
22. **Rerouting C# hook A onto sim hook B inherits B's CALLER SET.** Timing is
    the obvious half; the callers are the half that bites. `lizard_tail`'s port
    defers its heal onto `on_damage_received`, which `CreatureCmd.kill` and
    `cards/breakthrough.py:49` never fire — so the relic is spent and the heal
    never lands. Diff the callers of both hooks, not just their order.
23. **A verify fluent-helper's name against its body.** `EventOption
    .ThatDecreasesMaxHp` / `.ThatDoesDamage` are red-flash *presentation*
    predicates that apply nothing. `distinguished_cape`'s port assumed the
    helper paid the cost, dropped the relic's own −9 Max HP, and is right only
    by accident because Vakuu's option pays it instead. `DrowningBeacon` and
    `UnrestSite` are the other callers.
24. **A docstring that misdescribes the PORT — pointing at a *false* gap.**
    Classes 12 and 19 cover claims that talk you *out of* a real gap; this is
    the opposite direction and it wastes a whole audit. `nunchaku.py:14-15`
    calls its counter per-combat when the port really keeps it per-run — which
    is *correct*, because C#'s is a `[SavedProperty]`. `pendulum.py:13-14` and
    `happy_flower.py` claim a per-combat reset they do not perform, and the
    behaviour is right. Verdict the CODE, never the comment; a batch that
    trusted these would have filed three false gaps and "fixed" working relics.
25. **A C# dispatcher with TWO passes is an ordering guarantee.** The sim's
    single duck-typed listener loop destroys it, and the two passes are often
    two *different hook names* rather than an `X`/`X`Late pair — so grepping for
    "Late" misses them. Three instances found: `AfterCombatVictoryEarly` is a
    separate earlier full pass and `meat_on_the_bone` is its only implementer
    (LIVE — at 38/80 the sim heals 44 where the game heals 56, because index-0
    Burning Blood gets to heal first); turn start runs steps 22 and 23 as two
    passes over 9 and 14 relics (LIVE on `gambling_chip × bone_tea`); card
    rewards are the same shape but dormant. Read the C# `Hook.X` body and count
    the `foreach`es before verdicting any ordering question.
26. **A control-flow predicate moved earlier drops every hook between the two
    positions.** Distinct from class 11 (wrong slot) and class 20 (wrong site):
    here the hook order is right, but a `return` happens too early. C# asks
    `ShouldTakeExtraTurn` **last** (`CombatManager.cs:1366`, after
    `BeforeTurnEnd`/`DoTurnEnd`/the hand flush/`AfterTurnEnd`); the sim asks it
    first and returns (`combat.py:648-652`), so Pael's Eye skips the **entire**
    turn-end pass. A sentinel listener recording which hooks fire is the cheapest
    way to see this: `[on_player_turn_end, on_hand_emptied,
    after_player_turn_end]` without the relic, `[NONE]` with it.
27. **A filter hoisted from the listener to the dispatcher changes WHICH
    listeners run.** `Hook.ModifyBlock` has no `props` gate and `PaelsLegion`
    filters on the looser `IsCardOrMonsterMove`; the sim put the props check in
    the dispatcher, so an unpowered card silently skips the listener entirely —
    Entrench on 10 block gives 20 with *and* without the relic where C# gives 30.
    The fix must add the field, not flip a flag, because `brilliant_scarf` G1
    needs the same distinction pointing the other way.
28. **A one-implementer hook is still a hook.** `Hook.BeforeCardRemoved` has a
    single C# implementer (`SpoilsMap`), and the port re-implemented that
    implementer's intent as a local flag — which only the map-generation readers
    consult, not the payout reader. A removed Spoils Map still pays 600 gold
    (`precise_scissors` / `precarious_shears` / `preserved_fog`, all LIVE).
    "Only one thing uses it" is never a reason to skip the dispatch.
29. **Sibling relics may differ ON PURPOSE — never copy a sibling's verdict.**
    Rule 3 says one verdict per *mechanism*, not per family. `brilliant_scarf`
    deliberately excludes `IsAutoPlay` (its LIVE G1); `RainbowRing` and
    `RazorTooth` deliberately do not, so the sim counting auto-plays is correct
    at those two sites. Copying across would have filed two false gaps. Same
    trap in reverse for the `undo_after_obtained` family below.

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
