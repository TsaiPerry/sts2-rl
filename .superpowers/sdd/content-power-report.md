# Stream report — content audits: powers

Branch `audit-power`, worktree `c:\Users\Perry\Desktop\sts2-rl-power`, based on
`audit-pipeline` at `3d63f3b0`. Written 2026-07-26, updated as batches land.

**Status: 30 of 134 units audited and committed; 104 remain.** The stream did
not finish. What DID finish is the part Perry asked for by name — the
sign-awareness determination is **complete for all 134 units**, because it was
settled by a committed census rather than unit by unit. Section 2 is therefore
final; sections 4-6 cover only the 30 audited units, and section 8 is the
residual queue with the work already scoped per unit.

| | |
|---|---|
| units audited | 30 / 134 |
| unit rollups | 26 gap, 2 faithful, 1 waiver, 1 deliberate-divergence |
| entries (hooks + guards) | 256 — 169 faithful, 59 gap, 21 waiver, 7 dd |
| gap rate | 87% of units carry at least one gap |
| suite | 2476 passed / 31 xfailed, unchanged at every batch boundary |
| commits | `e6170905` (batch 1), `e9a046ad` (batch 2) |

## 1. The tool this stream added

`tools/audit/power_census.py` (committed in batch 1, follows
`dormancy_probes.py`'s pattern). Every number in every record and in this
report is re-derivable from it:

```
py tools/audit/power_census.py typing        # sign-aware-typing census, all 134
py tools/audit/power_census.py slots         # C# side-hook -> sim slot mapping
py tools/audit/power_census.py stack         # on_stack no-ops vs C# stacking
py tools/audit/power_census.py multipliers   # dyadic check on every factor
py tools/audit/power_census.py neg-appliers  # C# sites applying a power < 0
py tools/audit/power_census.py instance      # PowerInstanceType overrides
py tools/audit/power_census.py visible       # IsVisibleInternal overrides
py tools/audit/power_census.py unregistered  # Power classes absent from ALL_POWERS
py tools/audit/power_census.py overrides     # per-unit override list
```

Building it first was the right call and is the main process lesson: five of
the eight bug classes are *population* questions, and answering them by
census once beats answering them 134 times by reading.

## 2. Sign-aware power typing — the deliverable, complete for all 134 units

`py tools/audit/power_census.py typing`. `GetTypeForAmount`
(`PowerModel.cs:460-471`) has two arms that can disagree with a static
`power_type` attribute:

- **arm 1**, `StackType == Counter && AllowNegative && amount < 0` → `Debuff`.
  **3 ported powers qualify: `strength`, `dexterity`, `shriek`.**
- **arm 2**, `!AllowNegative && Type == Debuff && amount < 0` → `Buff`.
  **28 ported powers qualify.**

**Only two powers actually carry the defect: `strength` and `dexterity`.**

- `shriek` qualifies for arm 1 but is *inert*: its `Type` is already `Debuff`,
  so the arm returns the answer the static attribute already gives. Recorded
  as `faithful` with that reasoning in `audits/power/shriek.json`.
- All **28** arm-2 powers are inert too, and for a reason worth writing down:
  arm 2 is a *protective* rule in C#. Every duration tick goes through
  `PowerCmd.Decrement` → `ModifyAmount(-1)` → `ModifyPowerAmountReceived`, so
  without arm 2 an Artifact holder would try to intercept its own
  Vulnerable ticking down. The sim never reaches that code at all: `_tick` /
  `_tick_duration` (`powers.py:70-84`) decrement the field directly and bypass
  `PowerCmd`. Different mechanism, identical observable. Independently,
  `neg-appliers` finds **no Debuff-typed ported power is applied with a
  negative amount anywhere in the decompiled source** — the only five powers
  C# ever applies negatively are Strength, Dexterity, Focus (unported),
  Shrink and Thorns.
- `shrink` is the one power whose `AllowNegative` the sim gets **wrong**
  (C# `true`, sim absent → `False`). It is not a *typing* defect — at a
  negative amount Shrink's `StackType` flips to `Single`, so neither arm fires
  and both sides say `Debuff` — but it is a real gap through
  `ShouldRemoveDueToAmount`, and it is the sharpest one in this batch: a
  negative Shrink is C#'s **infinite-duration** encoding, and the sim deletes
  it on re-application. Executed: two `Shrink -1` applications give the sim
  `Shrink(-1)` then `None`, the game `Shrink(-2)`. Dormant only because the
  Shrinker Beetle's move machine plays `SHRINKER` exactly once.
- `thorns` is applied negatively by two ported monsters (`SpinyToad.cs:-5`,
  `Toadpole.cs:-SpikenAmount`) and is `AllowNegative == false`, so neither arm
  fires and both sides remove it at ≤ 0. Faithful.

**Consequence for the seam tier: `power_cmd`'s G1 and G2 stay dormant and
their trigger is confirmed as stated.** I looked for a second route and there
isn't one. Every sim site that applies Strength or Dexterity negatively is
either a monster targeting the player (Artifact needs a player-side source
that exists nowhere in the game) or an applier-less self-application (Lamp
needs `applier is player`). Porting `Malaise.cs:39` or `Resonance.cs:33`
remains the single named trigger.

## 3. Non-dyadic multiplicative factors — `hook_dispatch` G9's blast radius

The prompt asked for this loudly, so: **`py tools/audit/power_census.py
multipliers` finds exactly two non-dyadic literal factors, and a third
computed one.** All three are on **damage**; **every ported block multiplier
is dyadic**, so `hook_dispatch`'s block-site dormancy argument is unaffected.

| factor | site | note |
|---|---|---|
| `0.7` | `ShrinkPower` (`powers.py:1386`) | already G9's executed witness. C# computes `(100m - 30m)/100m` in decimal. |
| `0.1` | `SlowPower` (`powers.py:1261`) | the factor is `1.0 + 0.1 * cards_played`, so it is non-dyadic for most counts. **Not previously named by G9.** |
| computed | `VulnerablePower` + `CrueltyPower` (`powers.py:414-416`) | `1.5 + cruelty.amount / 100.0`. Non-dyadic for most Cruelty amounts (10 → 1.6, 30 → 1.8). **Not previously named by G9.** |

Dyadic and therefore safe: Weak `0.75`, Frail `0.75`, Colossus `0.5`, Flutter
`0.5`, Soar `0.5`, Diamond Diadem `0.5`, Surrounded `1.5`, Unmovable `2.0`,
No Block `0.0`, Gigantification `3`.

**Caveat on the census's own method, stated because it bit me:**
`float.as_integer_ratio()` has a power-of-two denominator for *every* finite
float, so the obvious dyadic test calls `0.7` dyadic. The committed probe
parses the literal with `Fraction(str(val))` instead. Anyone re-deriving this
number a different way should check that first.

## 4. LIVE gaps found (all executed, all on ported content)

1. **`ritual` — the skip-first-trigger flag keys on the wrong thing.**
   `RitualPower.cs:36-43` sets the skip whenever **`Owner.IsEnemy`**; the sim
   (`powers.py:194-196`) sets it when the applier is on the opposing side.
   Every ported Ritual source is a monster buffing *itself*, so the sim's test
   is false exactly where C#'s is true. Executed with the ported Calcified
   Cultist: after one round the sim shows `Strength(2)`, the game shows none.
   Damp Cultist (Ritual 5) and Devoted Sculptor are the same shape.
2. **`thorns` — C#'s `BeforeDamageReceived` ported onto `on_damage_received`,
   and the `IsPoweredAttack` gate dropped.** Two executed consequences: a
   99-damage Strike into a 3-HP Thorns-5 enemy costs the sim's player 0 HP and
   the game 5 (the sim's after-damage hook is skipped on a killing blow, C#'s
   before-damage hook is not); and 3 unpowered non-card damage with
   `dealer = player` costs the sim's player 5 and the game 0. Reachable from
   the ported Ironclad card Juggernaut against a Toadpole or Spiny Toad.
3. **`rupture` — the `CurrentSide == Owner.Side` guard is missing.**
   `RupturePower.cs:47` makes Rupture pay out only for damage taken during the
   owner's own turn, i.e. self-inflicted. The sim pays out for every enemy
   attack that gets through, turning a self-harm payoff card into a free
   Strength engine. Its `BeforeCardPlayed`/`AfterCardPlayed`
   accumulate-then-apply-once deferral is also absent, so even the in-scope
   case grants Strength mid-card. `InfernoPower` has the identical guard in C#
   and the sim **does** implement it there (`powers.py:757-759`), so the
   concept and the accessor both exist — this is an omission, not an absence.
4. **`feel_no_pain` and `curl_up` — block gained without `props`.** Both call
   `BlockCmd.apply` with no `props`, which defaults to `ValueProp.MOVE`
   (`cmds.py:143-144`) and so runs both block-modifier families, where C#
   passes `ValueProp.Unpowered`. Feel No Pain 3 under Dexterity 3 gives the sim
   6 block and the game 3; under Frail the sim gives 2 and the game 3. **Eight
   sibling powers pass `UNPOWERED` correctly** (Crimson Mantle, Rage, Plating,
   Toric Toughness, Skittish, Crab Rage, Rampart, Blocked Off), so this is a
   two-call-site omission and a cheap fix.
5. **`curl_up` — the block is granted inline instead of after the card play.**
   C# latches the card in `AfterDamageReceived` and gains the block in
   `AfterCardPlayed`; the sim gains it immediately, so the *second and later
   hits* of a multi-hit attack are absorbed by block the game has not granted
   yet. Also drops the `IsPoweredAttack` and `cardSource == null` guards and
   never sets `LouseProgenitor.Curled`.
6. **`demon_form`, `crimson_mantle`, `inferno` — pre-draw turn-start slot.**
   The sim's `on_player_turn_start` (`player.py:169`) is pre-draw; C#'s
   `AfterSideTurnStart` / `AfterPlayerTurnStart` are post-draw
   (`CombatManager.cs:522` vs `:514`). Executed witness for Demon Form using
   two ported Ironclad cards: with Hellraiser auto-playing Strikes as they are
   drawn, the turn after Demon Form 2 lands the sim deals 24 damage
   (enemy 41 → 17) and the game 18 (41 → 23). For Crimson Mantle and Inferno
   the self-damage can cancel a hand draw the game already made, which is
   conformance-visible even when nothing dies. **The sim already has the right
   slot and does not use it: `on_player_turn_started` (`player.py:186`).**
7. **`dark_embrace` — the `causedByEthereal` deferral is missing.**
   `DarkEmbracePower.cs:37-60` banks ethereal-caused exhausts and draws for
   them at side end, *after* the flush, and the source comment says that is
   deliberate. The sim draws immediately, so those cards are flushed away. The
   draw count is also hard-coded to 1 where C# draws `Amount`.
8. **`aggression` — wrong RNG stream and wrong algorithm.**
   `AggressionPower.cs:28` is `UnstableShuffle(Rng.CombatCardSelection).Take(N)`;
   `powers.py:514` is `random.sample` on the shared unseeded combat rng. Both
   the stream and the selection algorithm differ, so any replay that plays
   Aggression diverges and every later shared-rng draw is perturbed.
9. **`corruption` — a Late-phase cost modifier flattened, and a pile decision
   replaced by an after-the-fact move.** `Nostalgia` runs first in the sim's
   `modify_card_play_result_pile` chain and can move the Skill to the draw
   pile, after which Corruption's `card in discard_pile` test fails and the
   Skill is never exhausted. Both are ported Ironclad-pool powers.
10. **`no_draw` — removed at `BeforeTurnEnd` instead of `AfterTurnEnd`**, so a
    turn-end draw the game blocks succeeds in the sim.

## 5. The systematic finding: side-hook → sim-slot mapping

`py tools/audit/power_census.py slots`. **54 of the 134 ported powers override
a C# side-scoped turn hook. 19 of those implement it with a per-creature sim
slot, or with no matching slot at all.** Resolved by following each dispatcher
to its `CombatManager` call site:

| C# override | dispatcher | correct sim slot (player / enemy) |
|---|---|---|
| `AfterSideTurnEnd` | `Hook.AfterTurnEnd` (`Hook.cs:1267`) | `after_player_turn_end` (`combat.py:665`) / `on_enemy_side_end` (`combat.py:345`) |
| `BeforeSideTurnEnd` | `Hook.BeforeTurnEnd` | `on_player_turn_end` (`combat.py:654`) / — |
| `AfterSideTurnStart` | `Hook.AfterSideTurnStart` (`CombatManager.cs:522`) | `on_player_turn_started` (`player.py:186`) / — |
| `BeforeSideTurnStart` | `Hook.BeforeSideTurnStart` (`CombatManager.cs:458`) | `on_player_turn_start` (`player.py:169`) / — |

Two distinct sub-classes, and they are worth separating because they have
different owners:

- **Enemy-side per-creature slots** (`on_enemy_turn_start`/`_end`) are
  `turn_structure`'s **G5** and I did not re-verdict them (rule 3) — the
  records cross-reference with the identical `gap` verdict. Affected:
  `asleep`, `battleworn_dummy_time_limit`, `demon_form`, `escape_artist`,
  `hardened_shell`, `hatch`, `plating`, `poison`, `regen`, `ritual`,
  `sandpit`, `slow`, `slumber`.
- **Player-side `AfterSideTurnEnd` mapped to `on_player_turn_end`** is *not*
  covered by any seam record I could find, and it is one slot too early —
  before the turn-end card effects and the hand flush, where C# is after both.
  Affected: `constrict`, `demise`, `disintegration`, `duplication`, `juggling`,
  `no_draw`, `no_energy_gain`, `one_two_punch`, `panache`, `rage`, `rebound`,
  `ringing`, `shrink`, `skittish`, `smoggy`, `tangled`, `tender`. Of the four
  audited so far, `no_draw` is live and the other three are dormant with named
  triggers; **the 13 unaudited ones are the highest-value part of the residual
  queue**, because `constrict`/`demise`/`disintegration` all deal damage in
  that slot and `tender` restores Strength there.

## 6. Cross-record disagreements spotted under rule 3

1. **`turn_structure` G5's dormancy argument is narrower than its dormancy
   claim.** G5 rests on "every ported listener on these hooks self-filters to
   its own owner", which is true and does establish that *ordering within one
   hook* is unobservable. It does not cover a listener whose effect changes
   state other creatures then read, and three audited or scoped units do
   exactly that: `battleworn_dummy_time_limit` **escapes** its owner in that
   slot (and the Battle Friend encounters field more than one dummy, so the
   sim can remove dummy #1 before dummy #2 acts), `asleep` **removes another
   power** (`Plating`) and wakes the owner, and `slumber` stuns. I have not
   executed a two-dummy witness, so I am **not** asserting G5 is live — I am
   reporting that its dormancy argument does not reach these three cases and
   that the seam session should re-examine it. The verdict itself is `gap` on
   both sides, so rule 3 is satisfied either way.
2. **`hook_dispatch` G9's factor population was incomplete.** It names Shrink
   `0.7` and reasons about block factors; it does not name `SlowPower`'s `0.1`
   or the `Vulnerable + Cruelty` computed factor. Both widen the damage-site
   gap. The *block*-site dormancy argument survives intact — see section 3.
3. **`power_cmd`'s G1/G2 trigger is confirmed, not contradicted** (section 2).
   Recorded here because a confirmation found by looking for a counterexample
   is worth as much as a contradiction.

## 7. Lessons for `tools/audit/PROMPT.md` (relic stream to fold in)

The relic stream owns `PROMPT.md`; I did not touch it. Proposed additions, in
descending order of how much time they would have saved me:

1. **New bug class — "the applied `props` are the block/damage typing."** Two
   of my ten live gaps are `BlockCmd.apply(...)`/`DamageCmd.deal(...)` calls
   that omit `props=ValueProp.UNPOWERED`, silently defaulting to powered and
   picking up Dexterity/Frail/Strength/Vulnerable the game excludes. Checklist
   line: *for every damage or block a unit deals, compare the C# `ValueProp`
   argument against the sim's `props=`; an omitted `props` is not a neutral
   default.*
2. **New bug class — side hooks vs per-creature slots.** Section 5's table
   belongs in `PROMPT.md`. `AfterSideTurnEnd` in particular is dispatched by
   `Hook.AfterTurnEnd`, which is not guessable from the name, and 19 of 134
   power units get it wrong. Checklist line: *resolve every `*SideTurn*`
   override to its `CombatManager` call site before believing a sim slot.*
3. **Bug class 3 is a population question, not a per-unit one.** Add the
   finding rather than the instruction: only `strength` and `dexterity` flip;
   arm 2 is inert because the sim's ticks bypass `PowerCmd`. That saves the
   next auditor from re-deriving it on all 134.
4. **Bug class 4 (visibility guards) can be closed game-wide.** `0 of the 260
   files under src/Core/Models/Powers override IsVisibleInternal`
   (`power_census.py visible`). `IsVisible` is provably always `true` for
   every power in the whole decompiled game, so an `IsVisible` guard is always
   a `waiver`. Worth stating once in `PROMPT.md` instead of being re-litigated.
5. **`PowerStackType.Single` does not mean "re-application is a no-op."** It
   means "Amount is hidden, and is always 1" (`PowerStackType.cs:10-13`);
   `PowerCmd.ModifyAmount:236` adds unconditionally with no `StackType` branch.
   **15 ported powers override `on_stack` to `pass` citing Single and are
   therefore wrong** (`power_census.py stack`). All 15 are currently dormant
   because none reads `Amount` — but the comment is repeated 15 times and will
   be copied a 16th.
6. **A unit-level `deliberate-divergence` needs the mechanism named, not just
   the outcome.** I used it 7 times, mostly for `_expire()` standing in for
   `PowerCmd.Remove` and for `StrengthCmd.apply` standing in for
   `PowerCmd.Apply<StrengthPower>(applier: Owner)`. Both are observably
   identical today and both would break a future `AfterRemoved` / applier
   reader. Worth a checklist line so they are recorded rather than waved past.

## 8. Roster and harness problems (I own neither; reporting per the contract)

1. **4 ported powers are invisible to the roster and to the RL observation.**
   `py tools/audit/power_census.py unregistered`: `ALL_POWERS` has 134
   entries, but 138 `Power` subclasses carry an `id`. Missing:
   `flex_potion`, `heist`, `speed_potion`, `thievery`. All four are live
   content (`HeistPower`/`ThieveryPower` drive the Gremlin Merc's gold theft,
   referenced by class rather than by id), so they work in play but:
   - the roster never enumerates them, and `harness.skeleton power/thievery`
     raises `StopIteration`, so **they cannot be audited at all** through the
     harness — they are 4 units of silent under-coverage in the 134 total;
   - `full_env.POWER_IDS` is built from `ALL_POWERS` (`full_env.py:147`), so
     they are **absent from the observation vector** the policy sees.
   The second half is an engine issue for the gap-fix stream, not an audit
   finding. `name_overrides.json` cannot express it — the fix is four lines in
   `ALL_POWERS`.
2. **`harness.list_overrides` misses overrides with a tuple return type.**
   `CorruptionPower.ModifyCardPlayResultPileTypeAndPosition` returns
   `(PileType, CardPilePosition)`, and `_OVERRIDE_RE`'s
   `[\w<>,.?\[\] ]+?` return-type class does not match the parentheses — the
   **exact** 147-vs-146 defect `hook_dispatch` documented for `Hook.cs`, now
   reproducing in the content tier. The harness therefore *under-*enumerates
   required hooks, which is a silent-skip failure mode rather than a loud one.
   I added the hook to `audits/power/corruption.json` by hand; validation
   accepts extra keys, so the record is complete. Any other content unit whose
   C# file has a tuple-returning override has the same blind spot.
3. **`audit_status.py` reports no live/dormant split.** Not a defect, but with
   59 gap entries of which 10 are live, `gaps` as a single column understates
   how much of the ledger is a queue and overstates how much is a fire.

## 9. Cost data

Wall-clock is dominated by the suite, not the auditing: `py -m pytest test/ -q`
is **~4m15s** and runs once per batch, so 2 batches spent ~8.5 minutes of the
session on a gate that (correctly) never moved off 2476 passed / 31 xfailed.

- **30 units in 2 batches.** Batch 1 (15 units) and batch 2 (15 units) each
  took roughly the same effort, but batch 1's cost was front-loaded: reading
  `sts2_rl/powers.py` in full (4221 lines), the four binding documents, and
  building `power_census.py`. That shared cost is now paid for all 134.
- **Marginal cost is ~4 units per C# dump.** The efficient loop is:
  `grep -n "" X.cs | grep -v using` for 6-8 files at a time (real line numbers
  — an `awk` filter that renumbers makes every citation wrong, which I did
  once and had to redo), then write records through one Python filler rather
  than hand-writing JSON.
- **7 of 30 units needed execution to settle** (ritual, thorns ×2, shrink,
  demon_form, and the two slot-semantics probes). Execution was decisive every
  time: it confirmed 5 gaps as live, corrected one wrong claim of mine
  (Shriek's stun *is* faithful — `TerrorEel.trigger_terror` does call
  `CreatureCmd.stun`, which I had asserted it did not before reading it), and
  falsified one claim in the *sim's own docstring* (Hellraiser's
  infinite-HP-enemy justification).
- **Gap rate 87% of units, 23% of entries.** The high unit rate is mostly
  cross-references to already-recorded seam mechanisms — a unit inherits `gap`
  from one cross-referenced entry — so the unit rollup is a poor severity
  signal. The 59 gap *entries* split roughly 10 live / 49 dormant.

## 10. Residual queue — the 104 unaudited units

Ordered by expected yield, with what is already known about each group:

1. **The 13 unaudited player-side `AfterSideTurnEnd` units** (section 5):
   `constrict`, `demise`, `disintegration`, `duplication`, `juggling`,
   `one_two_punch`, `panache`, `rage`, `rebound`, `ringing`, `skittish`,
   `smoggy`, `tangled`, `tender`. The slot is known wrong; what is unknown is
   observability per unit. Three of them deal damage in that slot.
2. **The 15 `on_stack`-no-op units** (section 7 item 5): `adaptable`,
   `burrowed`, `confused`, `corruption`✓, `dampen`, `hellraiser`✓, `hex`,
   `imbalanced`, `nemesis`, `no_draw`✓, `no_energy_gain`✓, `smoggy`, `soar`,
   `surrounded`, `the_gambit`. Four are done; the rest need only the
   "does anything read `Amount`" question answered.
3. **The 9 `PowerInstanceType` units** (`power_census.py instance`):
   `automation`, `panache`, `rolling_boulder`, `sandpit`, `strangle`
   (`InstancedPerApplier`), `swipe`, `the_bomb`, `toric_toughness`,
   `withering_presence`. `power_cmd`'s G5 already owns the mechanism; what is
   per-unit is whether two simultaneous instances are reachable. `strangle` is
   the interesting one — it is the only ported `InstancedPerApplier` power.
4. **The remaining enemy powers** (Overgrowth / Hive / Glory, ~50 units).
   Expect more of the `props` omission (bug class new-1) and more
   per-creature-slot instances. `asleep`, `plating` and `slumber` are already
   flagged by the slots census as touching *other* creatures' state in a
   side-hook slot, which is the section-6 disagreement with `turn_structure`
   G5 — settling those three would resolve it.
5. **The Colorless/potion-source powers** (~17 units). Lower yield: several
   are pure data (`minion`, `back_attack_left/right`, `improvement`) and the
   potion-sourced ones are dormant by scope, though the *power* still has to
   be audited.
6. **The 4 unauditable units** (section 8 item 1) — blocked on a 4-line
   `ALL_POWERS` fix that this stream must not make.

**Suggested entry point for whoever resumes:** re-read
`tools/audit/PROMPT.md` first (the relic stream may have hardened it), then
run all nine census commands and start at queue item 1. The per-unit procedure
that worked is in section 9; `power_census.py` means the population questions
do not need re-deriving.
