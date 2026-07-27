# Potion-scope re-verdict pass — report

**Date:** 2026-07-26 · **Branch:** `audit-pipeline` · **Write scope:**
`audit/records/card/**`, `audit/records/power/**`, this file. Nothing committed;
`git status --porcelain sts2_rl/` is **empty**.

## What changed and why

`audit/prompts/_shared-audit-contract.md` §"Global scope" no longer says
"Out of scope everywhere: potions (deferred by Perry)". `potion` is an ordinary
audit kind (51 sim units, `harness.py roster potion`, `audit/records/potion/`)
and it is **unaudited**, exactly like `monster`. A potion may never again be the
reason for a `waiver`.

Ten entries across nine `card`/`power` records rested on that clause. All ten
were re-derived from the C# and the sim rather than patched. **Four of them were
protecting real divergences**, three of which nobody had looked at before.

---

## Every entry, before → after

| record | entry | before | after | why |
|---|---|---|---|---|
| `card/alchemize` | hook `OnPlay` | waiver | **gap (LIVE)** | whole card was waived; procure half really diverges |
| `card/alchemize` | guard "TryToProcure drops on a full belt" | waiver | **faithful** | ordering claim now EXECUTED, not asserted |
| `card/alchemize` | *(new)* guard G1 | — | **gap (LIVE)** | `Hook.ShouldProcurePotion` (Sozu) never runs |
| `card/alchemize` | *(new)* guard G2 | — | **gap (LIVE)** | `Hook.AfterPotionProcured` (Belt Buckle) never fires |
| `card/alchemize` | *(new)* guard N1 | — | **faithful** | generation half: right stream, 2 draws, right filter set |
| `power/buffer` | guard "applier is a potion" | waiver | **faithful** | Lucky Tonic applies `BufferPower(1)`, applier matches |
| `power/clarity` | guard "applier is a potion" | waiver | **faithful** | Clarity Extract: Draw(1)→Power(3), order correct |
| `power/flex_potion` | guard "applier is a potion" | waiver | **faithful** | Flex Potion applies the WRAPPER, not `StrengthPower` |
| `power/gigantification` | guard "applier is a potion" | waiver | **faithful** | Gigantification Potion applies 1 stack |
| `power/radiance` | guard "applier is a potion" | waiver | **faithful** | Radiant Tincture keeps energy-per-turn and stack-count apart |
| `power/speed_potion` | guard "applier is a potion" | waiver | **faithful** | Speed Potion applies the WRAPPER, not `DexterityPower` |
| `power/shackling_potion` | guard "applier is a potion" | waiver | **gap (LIVE)** | applier targets `not is_gone`, C# targets `HittableEnemies` |
| `power/surrounded` | hook `BeforePotionUsed` | faithful | **gap (LIVE)** | the sim never dispatches `BeforePotionUsed` at all |

### Rollups that moved

- `card/alchemize`: **waiver → gap**
- `power/radiance`: **waiver → faithful** (that guard was its only non-`faithful`
  entry)
- The other seven rollups were already `gap` and stay `gap`.

### Status deltas (measured, baseline via `git stash` of `audit/records`)

| | before | after |
|---|---|---|
| card gaps | 109 | **110** |
| card `live` records | 0 | **1** |
| power gaps | 117 | 117 |
| power `live` records | 1 | **3** |

`686 record(s), 0 invalid` under `validate --strict-inherited`, unchanged. The
4 stale `power` records are **pre-existing** — the same 4 appear in the stashed
baseline, so this pass staled nothing.

---

## The four real findings

### 1. `card/alchemize` — the whole card was waived (rule-3 break, LIVE ×2)

The old record waived `OnPlay` outright: *"The entire body is potion
procurement … Potions are out of scope entirely per the shared contract."*
The relic tier had **already filed this exact mechanism as a LIVE gap**, and
`audit/records/relic/sozu.json` guard G1 even names Alchemize as its trigger.
One mechanism, two answers — a binding-rule-3 break the contract itself caused.

`Alchemize.cs:24` is one statement with two halves.

**The generation half is faithful** (new guard N1), and I re-derived it rather
than inheriting the old claim, which asserted the stream was right without
executing the draw count and never checked the filter set:

- **Stream:** `colorless_skills.py:42-48` uses
  `rng_set.combat_potion_generation` — the stream C# names — with a shared-rng
  fallback only on the non-parity RL path (`run.py:138-143`). Same two-branch
  shape `card/infernal_blade` and `relic/alchemical_coffer` both hold up as
  correct. PROMPT.md bug class 16 does not bite.
- **Draw count (executed):** one Alchemize play on `RunRngSet('89U21BV1TZ')`
  advances `combat_potion_generation` by exactly **2**, matching
  `PotionFactory.cs:67-81` (`NextFloat` band + `NextItem`) — on a full belt as
  well as an open one.
- **Filter set:** `PotionFactory.cs:62-64` keeps `p.CanBeGeneratedInCombat`;
  exactly three potions override it (`FairyInABottle.cs:19`, `FruitJuice.cs:20`,
  `RegenPotion.cs:22` — executed grep over `src/Core/Models/Potions/`), and
  `potion_pools.py:75-77` is exactly that set.

**The procure half is not.** `PotionCmd.TryToProcure` (`PotionCmd.cs:28-53`) is
a gate (`:31` `Hook.ShouldProcurePotion`) and an event (`:46`
`Hook.AfterPotionProcured`) wrapped around `AddPotionInternal` (`:40`). The sim
calls the bare belt write `player.add_potion` (`player.py:107-121`), whose own
docstring concedes the omission **while citing the deleted clause**:

> `player.py:112-115` — "…does not run the `Hook.ShouldProcurePotion` gate today
> … unchanged by this fix, **out of scope**."

Executed at the Alchemize site:

```
relics=[]        -> belt ['explosive_ampoule', None, None]
relics=['sozu']  -> belt ['explosive_ampoule', None, None]   # C#: EMPTY
relics=['belt_buckle']: dexterity 2 before AND after         # C#: 0 after
```

Both **grade B** (belt / Dexterity, not stream): the generation draws are spent
before the gate on both sides, so the stream stays aligned.

**Reachability (LIVE):** Alchemize is in `cards/pool.py:46`'s `COLORLESS_POOL`
and obtainable from the Brain Leech event (`events/brain_leech.py:53-66`) and
Lead Paperweight (`relics/lead_paperweight.py:16-31`). Sozu comes from the ported
Darv shrine; Belt Buckle is Shop rarity in the transcribed grab bag.

The belt-full guard flipped to **faithful** on executed evidence (binding rule 5
— the old rationale asserted the create-then-drop ordering without running it).
Worth noting: the belt-full case is *more* reachable in the sim than in the game,
because `relic/potion_belt`'s +2 slots is itself a LIVE gap (the sim's stub
grants none).

### 2. `power/shackling_potion` — ADDITIONAL, LIVE. The applier's target set diverges

`ShacklingPotion.cs:35` applies over `CombatState.HittableEnemies`, which is
`Enemies.Where(e => e.IsHittable)` (`CombatState.cs:142`) and `IsHittable` is
`!IsDead && Hook.ShouldAllowHitting(...)` (`Creature.cs:285-299`).
`potions.py:910` loops `[e for e in ctx.enemies if not e.is_gone]` — no
`ShouldAllowHitting` leg.

That mismatch is already recorded at `power/the_bomb` G1, `power/inferno` and
`power/rolling_boulder` as a gap labelled **DORMANT**, on the argument that
`DamageCmd.deal` re-checks `should_allow_hitting` at entry (`cmds.py:51-52`) and
returns 0. **That argument does not reach this site**: the applier applies a
POWER, and `PowerCmd.apply` (`cmds.py:271-327`) has no such guard anywhere in it.
Same verdict (rule 3), different liveness — with evidence, not inheritance.

Executed: two Fogmogs (`monsters/overgrowth/fogmog.py:34` applies
`IllusionPower`), one driven to the revival state:

```
is_dead=False is_gone=False is_reviving=True should_allow_hitting=False
sim Shackling Potion targets (3): Fuzzy Wurm Crawler, Eye with Teeth, Eye with Teeth
C#  HittableEnemies       (2): Fuzzy Wurm Crawler, Eye with Teeth
reviving enemy ends holding ('strength', -7), ('shackling_potion', 7)   # C#: neither
```

Shackling Potion is pool-registered (rare, `potion_pools.py:59`); The Obscura
(`monsters/hive/the_obscura.py:38`) and Test Subject's `AdaptablePower`
(`monsters/glory/test_subject.py:61`) are two further ported routes to an
alive-but-unhittable enemy. **LIVE, grade B.**

The amounts, power class and applier were all checked and are faithful
(`PowerVar<StrengthPower>(7m)` → `STRENGTH = 7`; C#'s fourth `PowerCmd.Apply`
argument is `base.Owner.Creature`, i.e. `applier=ctx.player`).

### 3. `power/surrounded` — ADDITIONAL, LIVE. `BeforePotionUsed` is not ported at all

I disagree with the prompt's expectation that this verdict would survive. It does
not, and the old rationale was wrong on *both* halves, not just the scope clause.

C# has **two** potion-use hooks, fired on either side of the effect
(`PotionModel.cs`): `:293` `RemoveBeforeUse` → `:297` `Hook.BeforePotionUsed` →
`:325` `OnUse` → `:338` `Hook.AfterPotionUsed`. An executed grep of `src/` finds
exactly three model implementers: **`SurroundedPower.cs:82` is the only
`BeforePotionUsed`**, while `BeltBuckle.cs:81` and `ReptileTrinket.cs:22` are
`AfterPotionUsed`.

The sim has **one** hook. `hooks.py:566-571` declares `on_potion_used` and its own
docstring says *"Fires after a potion's effect resolves (mirrors
AfterPotionUsed)"*; `combat.py:604-610` dispatches it **after** `potion.use(...)`.
Belt Buckle and Reptile Trinket sit in the right slot; SurroundedPower's port
(`powers.py:2580-2582`) was hung on the same method and runs one phase late.
`grep before_potion_used sts2_rl/` returns nothing.

It is observable whenever a targeted potion kills its target — C# flips facing on
the **live** target, then the death fires `AfterDeath` which re-faces on the
survivors; the sim runs the death re-face first and then flips on the corpse.
Executed on the ported Kaiser Crab boss with the Crusher at 1 HP and a Fire Potion:

```
sim final facing = left    -> Rocket multiplier 1.5
C#  final facing = right   -> Rocket multiplier 1.0
Rocket's 18-damage Precision Beam: player 80 -> 44 (sim) vs 80 -> 56 (game)
```

**12 HP on one hit.** Kaiser Crab is `monsters/hive/kaiser_crab.py:159-162` and
its Rocket arm applies this very power at `:112-114`; Fire Potion is pooled
common and targeted. Four other pooled potions are targeted too (`weak_potion`,
`vulnerable_potion`, `beetle_juice`, `powdered_demise`). **LIVE, grade B.**

Fix shape: split the sim's single dispatch into `before_potion_used` (before
`combat.py:609`) and `on_potion_used` (after, `:610`), and move SurroundedPower
onto the former. Belt Buckle and Reptile Trinket stay put.

### 4. The six that really were fine — but only after checking

`power/buffer`, `clarity`, `flex_potion`, `gigantification`, `radiance`,
`speed_potion`. Each applier potion was read in full against its `.cs` model.
All six are faithful: amounts are the pinned non-ascension values (no
`AscensionHelper.GetValueIfAscension` in any of the seven files), the applier is
`base.Owner.Creature` in C# (fourth parameter of `PowerCmd.cs:101`) and
`applier=ctx.player` in the sim, and `cardSource` is null on both sides.

Two things worth recording because they are traps a copy-paste verdict would have
walked into:

- **Flex Potion and Speed Potion declare their var on the WRONG class on purpose.**
  `FlexPotion.cs:22` is `PowerVar<StrengthPower>(5m)` but `:30` applies
  `FlexPotionPower`; `SpeedPotion.cs:22` is `PowerVar<DexterityPower>(5m)` but
  `:30` applies `SpeedPotionPower`. The var only supplies the number. Reading it
  as the applied class gives permanent Strength/Dexterity instead of the
  end-of-turn-reverting wrapper. Both ports take the wrapper correctly.
- **Two-number potions keep the numbers apart.** Clarity draws **before** applying
  (so the immediate card is not itself boosted); Radiant Tincture's `EnergyVar(1)`
  is energy-per-turn and its `PowerVar<RadiancePower>(3m)` is the stack count, and
  swapping them gives 1 turn of 3 energy instead of 3 turns of 1. Both orders are
  correct in the sim.

The residue of those guards is now a **coverage** statement, not a scope one:
`potion/<id>` has no record because the whole potion kind is unaudited. Nothing
in any of these records depends on it.

---

## Outside my write scope — named file, exact edit

1. **`audit/tools/PROMPT.md` (relic stream owns it).** Its `## Scope` section,
   final paragraph, still reads:

   > `Potions: out of scope entirely. Ascension values: out of scope.`

   That is the deleted clause, still binding on every future unit auditor who
   reads the checklist. **Exact edit:** replace `Potions: out of scope entirely.`
   with something like *"Potions: IN SCOPE — `potion` is an ordinary (currently
   unaudited) kind; a potion may never be the reason for a waiver."* Worth a v7
   header bump and a new bug class, because this pass exhibited two fresh ones
   (see item 4).

2. **`audit/GAP-QUEUE.md` (gap-queue stream owns it).** Four new gap entries need
   queueing:
   - `card/alchemize` G1 → folds into the existing `relic/sozu` G1 mechanism
     (missing `ShouldProcurePotion` on the in-combat procure path). Grade B.
   - `card/alchemize` G2 → folds into the existing `relic/belt_buckle`
     `AfterPotionProcured` mechanism. Grade B.
   - `power/shackling_potion` G8 → **new liveness on an existing mechanism**
     (`HittableEnemies` vs `is_gone`). The queue currently carries that mechanism
     as dormant; it now has a LIVE site, and the fix must add the
     `should_allow_hitting` leg to the *target selection*, not only to
     `DamageCmd`.
   - `power/surrounded` `BeforePotionUsed` → **a genuinely new mechanism**: the
     sim has no `BeforePotionUsed` dispatch. One site today, one-line fix in
     `combat.py`, grade B.
   `py audit/tools/gap_queue.py coverage` will fail until these are added — that
   is the tool working, not a defect.

3. **`audit/README.md` (nobody's to edit casually).** Its Status section says
   "Not audited at all: `monster` (109 units)". `audit_status.py` now also reports
   `potion 51 unaudited`. The README's prose undercounts.

4. **`sts2_rl/player.py:112-115` (gap-fix stream only).** The `add_potion`
   docstring cites the deleted clause as its justification
   (`"…out of scope"`). It is now a documented LIVE gap; the comment should say so
   rather than excuse it. **I did not touch it** — `git status --porcelain
   sts2_rl/` is empty.

5. **Lessons for PROMPT.md's bug-class list**, both exhibited here:
   - *A dormancy argument does not transfer between COMMANDS.* `HittableEnemies`
     vs `is_gone` is dormant under `DamageCmd` (which re-checks) and LIVE under
     `PowerCmd` (which does not). Check which command the site actually calls
     before inheriting a sibling record's liveness.
   - *Two C# hooks collapsed onto one sim method: check WHICH one the sim's
     dispatch site implements.* `on_potion_used` serves `BeforePotionUsed` and
     `AfterPotionUsed`; the dispatch is in the After slot, so the Before
     implementer is silently one phase late. This is class 25's shape but with the
     two passes carrying *different names*, which grepping for "Late" misses.

## Could not settle

Nothing. Every claim above is either a direct source citation or an executed
result.

One judgement call worth flagging rather than hiding: **the RL fallback path is
not filed as a gap.** `colorless_skills.py:49-52` picks a potion *uniformly* over
the 45 in-combat-generable classes (P(Rare) = 14/45 = 0.311 vs the game's 0.10)
whenever `rng_set is None`. I verdicted it faithful, following the settled house
position at `card/infernal_blade` (which calls the two-branch shape "exactly what
card/discovery … fail to do") and `relic/alchemical_coffer` (identical shape,
"the RNG stream is right"). `relic/delicate_frond` G1 is a LIVE gap for the same
uniform pick precisely *because* it has no parity branch at all. If that house
position is ever revisited, Alchemize is a site.

## Verification (run, not asserted)

```
py audit/tools/harness.py validate --strict-inherited   -> 686 record(s), 0 invalid
py audit/tools/audit_status.py                          -> card 110 gaps / 1 live
                                                           power 117 gaps / 3 live
                                                           (stale 4 in power: PRE-EXISTING,
                                                            same in the stashed baseline)
py audit/tools/citation_check.py                        -> 6 MISSING, 58 OUT-OF-RANGE,
                                                           NONE of them in the 9 edited
                                                           records (all pre-existing)
py audit/tools/backfill_sources.py --kind card          -> +17 extra_sources, 1 record
py audit/tools/backfill_sources.py --kind power         -> +25 extra_sources, 8 records
py -m pytest test/ -q                                   -> 2523 passed, 38 xfailed
git status --porcelain sts2_rl/                         -> (empty)
```

**Note on the suite count:** the brief expected 2522/38. The tree already carried
uncommitted edits to `test/test_audit_harness.py` (part of the `potion`-kind
harness change) before this pass began, which is where the extra test comes from.
Audits add no executable code and `sts2_rl/` is untouched, so 2523/38 is this
tree's baseline, not a regression.
