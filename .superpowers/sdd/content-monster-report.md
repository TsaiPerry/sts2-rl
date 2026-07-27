# Stream 5 — content audits: monsters. Final report

Branch `audit-monster` (worktree `C:\Users\Perry\Desktop\sts2-rl-monster`),
merged from eight batch branches `audit-monster-b01`…`b08`.

**109 of 109 units audited. `harness.py validate`: 795 records, 0 invalid.
`audit_status --kind monster`: 109 audited, 0 invalid, 0 stale, 36 gaps, 24
live.** Test suite `2512 passed, 38 xfailed, 2 failed` — the two failures are
pre-existing and environmental and are discussed under "Suite" below. No file
under `sts2_rl/` or `test/` differs from `audit-pipeline` (`git diff --stat
audit-pipeline...HEAD -- sts2_rl/ test/` is empty).

| unit rollup | count |
|---|---|
| `gap` | 36 |
| `waiver` | 37 |
| `deliberate-divergence` | 35 |
| `faithful` | 1 |

45 `gap` **entries** across those 36 units: **28 LIVE, 17 dormant, 0 unlabelled**
(every gap entry carries the boolean `live` field).

---

## 1. The headline deliverable — monsters misreading an `AddBranch` integer

**No sixth monster.** The population is exactly the five the seam's **G1**
already names, and all eight batches confirmed it independently:
`flail_knight`, `hunter_killer`, `scroll_of_biting`, `spectral_knight`
(`glory/knights.py`) and `fake_merchant`. `state_machine_probes.py mismatch`
still prints **12 resolved pairs / 13 C# `RandomBranchState`s / 7 exact matches
/ 5 misreads**, unchanged by this stream.

This is a stronger result than "we found nothing", because the negative was
established over the population the seam's probe *cannot* reach:

- The `mismatch` probe resolves **one pair per sim module and only for modules
  that call `add_branch`**, so it is blind to all 27 hand-rolled ports. Batches
  1, 2 and 6 reconstructed every hand-rolled graph node-for-node from the C# and
  drove it against the port on identically seeded `MonsterAi` streams (§3).
- Batches 3, 4, 5, 7 and 8 re-derived each of their own branch states against
  the seam's 10-overload table rather than trusting the probe. Two ports that
  *look* like G1 are correct and were confirmed as the seam's counter-evidence:
  `fossil_stalker` reads `AddBranch(state, 2)` as `max_times=2` (overload #9)
  and `two_tailed_rat` reads `AddBranch(SCREECH, 3, CannotRepeat)` as
  `cooldown=3` (overload #1). `twig_slime_m` was re-derived from the overload
  table rather than from its own docstring and executed: POKEY 57.35 % / STICKY
  42.65 % on **both** sides — neither 50/50 nor the 2:1 a weight misread would
  give.
- Most units cannot exhibit the class at all: the overwhelming majority of C#
  `AddBranch` sites use overloads #5, #6 and #10, which take **no integer**.

**Two additions to G1's liveness list** (reported, not edited into the seam
record):

1. `mysterious_knight` is a **second reachable route** to the `flail_knight`
   misread — The Lantern Key event (`events/the_lantern_key.py:41`) — which G1
   does not name.
2. `scroll_of_biting` and `spectral_knight` were verified line-for-line against
   `ScrollOfBiting.cs:89-90` and `SpectralKnight.cs:52-53`; the seam's text is
   accurate.

### A NEW bug class the integer check cannot catch: branch **add order**

`inklet` is a LIVE gap of the same family that **no parameter comparison can
find**. `Inklet.cs:73-74` adds `PIERCING_GAZE` then `WHIRLWIND`; the port rolls
`["WHIRLWIND", "PIERCING_GAZE"]` (`inklets.py:64`). The parameters are all
identical, so `mismatch` passes it, and because the weights are equal the
**marginal distribution is also identical** (sim 10022 W / 9978 PG, game 10022
PG / 9978 W over 20 000 rolls) — so a distribution check clears it too. Only a
**per-draw sequence diff on a shared stream** finds it: **0/20 000 agreement**,
diverging at the first `JAB→RAND` transition on every seed, with identical draw
counts (20 vs 20), so it is pure move content and not stream drift. Add order is
observable by seam step 14 (ties resolve toward the earlier branch).

Worse, **the existing regression pin locks the defect in**:
`test_monster_branch_audit.py::TestInkletMoveSequence::test_jab_rolls_exactly_one_draw_matching_game_primitive`
computes its own expectation using the same reversed order it should be
checking, and its docstring's "a true 50/50 every time" is a true statement
about the marginal that is silent about the mapping.

---

## 2. Every LIVE gap (28 entries, 20 units)

Grouped by mechanism; each was proved reachable on ported content by execution,
per verdict rule 6.

**Move-selection / RNG streams**
- `flail_knight`, `mysterious_knight`, `hunter_killer`, `scroll_of_biting`,
  `spectral_knight` — the seam's G1, recorded at unit level, not re-verdicted.
- `inklet` — branch add order reversed (above).
- `corpse_slug` — `EnsureCorpseSlugsStartWithDifferentMoves` draws
  `NextInt(3)` on the **per-encounter** `Rng`; the port uses
  `rng.randrange(3)` on the combat rng and ignores `selection_rng` entirely.
  Executed: **6 of 10 seed/floor configurations disagree**, the selection stream
  is drawn 0 times where the game draws 1 — and under a *fixed* seed the sim
  returned `[2,0,1] [0,1,2] [1,2,0] [1,2,0]` on four consecutive runs, i.e.
  **Corpse Slug replays are non-deterministic**.
- `slithering_strangler` — same root cause in its encounter builder (0 selection
  draws vs the game's 2–3).
- `scroll_of_biting` — `_ScrollsEncounter.create_monsters` draws its starter
  index off the wrong stream (executed, seed 0 →
  `['CHEW','MORE_TEETH','CHOMP','MORE_TEETH']`).
- `fabricator` — `_spawn_bot` picks the bot class from the shared combat rng,
  not `MonsterAi`; under parity `CombatRng` the two streams are distinct.
- `thieving_hopper` — `THIEVERY` steals off `ctx.combat._rng.choice` where
  `ThievingHopper.cs:222` names `RunRng.CombatCardGeneration`; the stream **is**
  consumed, and `combat_rng.card_gen` exists and is unused.

**Death is not removal (PROMPT.md class 21)**
- `eye_with_teeth`, `parafright`, `the_obscura` — `IllusionPower` implements
  `ShouldCreatureBeRemovedFromCombatAfterDeath`; the sim ports it onto
  `should_die` (`powers.py:1566`), so the creature never dies and `on_death`
  never dispatches.
- `waterfall_giant` — the same shape via `SteamEruptionPower`
  (`powers.py:2016`). Executed with a ported Gremlin Horn attached: energy 3→3
  and hand 5→5 on the killing blow where the game pays +1 energy / +1 card; the
  sim fires `on_death` once for the fight, the game twice.
- `test_subject` — three entries. Across the three-form fight the sim dispatches
  `on_death` **once** where the game dispatches `Hook.AfterDeath` **three**
  times; the revive delta is **+199 vs +200** (the sim floors the corpse at 1 HP
  where C# leaves it at 0); and `RemoveAllPowersAfterDeath` never runs, so
  Enrage 2 and all its stacked Strength survive two resets the game wipes.
- **Counter-example worth recording**: `decimillipede_segment` is *correct* —
  `ReattachPower` lands on `should_remove_from_combat_after_death`, and executed,
  a killed segment fires `on_death`, sets `retained_after_death=True` and keeps
  taking turns (DEAD → REATTACH → WRITHE → CONSTRICT → BULK). That is the
  positive half class 21 currently lacks: it names the wrong landing site but
  not the right one.

**Creature placement and identity**
- `living_fog` — the spawned Gas Bomb is appended where
  `CombatManager.AddCreature` re-sorts `Enemies` by encounter slot. Executed:
  sim `[LivingFog, GasBomb]` vs game `[GasBomb, LivingFog]`; turn order **and**
  every enemy index flip, and `combat_driver.py:184-191` zips enemy state
  positionally.
- `ovicopter` — egg-slot placement in the enemy list (the legacy arm; the parity
  arm is correct, and legacy is the RL default).

**Numbers and telegraphs**
- `punch_construct` — Punch Off's `StartingHpReduction` cuts **max** HP where
  `PunchConstruct.cs:75-78` cuts **current** HP with `MaxHp` pinned at 55.
  Executed at seed 4: sim `hp=53 max_hp=53` vs a game `MaxHp` of 55.
- `tough_egg` — the hatchling HP roll uses Python's inclusive `randint` against
  a C# `NextInt` bound that is **max-exclusive** (`Rng.cs:95-109`); observed
  returning 22 where the game cannot.
- `vantom` / `vine_shambler` — `DISMEMBER` and `GRASPING_VINES` are built with
  **two** intents in C# and the port keeps one, dropping `StatusIntent(3)` and
  `CardDebuffIntent`. Observable: `env.py:163-167` and `full_env.py:568-571`
  read `Intent.has()` for exactly those types, and the sim *can* express them
  (`kin_priest` and `axe_ruby_raider` do). Of 45 moves checked by probe, exactly
  these two mismatch.
- `queen` — `Queen.cs:226-232`'s `AfterDeath` is not all presentation: it sets
  `HasAmalgamDied`, nulls `Amalgam`, and `SetMoveImmediate(EnragedState)` if the
  telegraphed move is Burn Bright. The sim substitutes at *resolution* time
  instead. Executed: the sim still telegraphs `BURN_BRIGHT_FOR_ME_MOVE
  intent=BUFF` where the game shows `ENRAGE_MOVE`; effect and next move agree,
  so it is precisely an intent/replay gap.
- `the_insatiable` — the three *discard* Frantic Escapes use
  `CardPilePosition.Random`, which is one `Rng.Shuffle` draw each for **both**
  pile types (`CardPileCmd.cs:512-514`); the port appends. **3 draws vs 6**,
  plus fixed vs random discard order.
- `thieving_hopper` — all four steal predicates lose a clause (**Event** from
  tier 2, **Quest** from tier 3, both `Imbued` arms). Reachable: 19 EVENT and 3
  QUEST cards are ported and `ImbuedEnchantment` is granted by the ported
  Electric Shrymp.
- `slumbering_beetle` — `CreatureCmd.Stun(owner, WakeUpMove, "ROLL_OUT_MOVE")`
  makes the Plating removal the *stun move's* perform body; the sim strips it
  mid-player-turn instead.

---

## 3. The hand-rolled population — corrected, and equivalence established

**The stream prompt's "~18 hand-rolled" is wrong: there are 27**
(`monster_probes.py kind`). Zero ported monsters face a C# model with no
machine at all. The corrected split is **82 `MachineMonster` / 27 hand-rolled**.

**Equivalence was established by execution for 26 of the 27, and none needs a
state-machine port as a fidelity fix.** The method that made this cheap, and
which is the reusable artifact here: each batch rebuilt the C#
`GenerateMoveStateMachine` **node-for-node on the sim's own
`MonsterMoveStateMachine`** and diffed it against the shipped port from
identically seeded `RunRngSet`s.

- Batch 1 (12 units): 15 configurations, 20 turns, 0 mismatches in sequence or
  draw count; `flyconid` matched turn-for-turn on 5 seeds.
- Batch 2 (14 units): 18 configurations × 3 seeds × 40 turns, **0 mismatches**;
  plus 4000 combats × 12 turns for the three branch units, frequencies identical
  to the last digit.
- Batch 6 (`parafright`): matched.
- The one exception is `inklet`, whose divergence is the LIVE add-order gap
  above — found *by* this method and by nothing else.

Things the execution caught that reading would have missed: `crossbow`,
`leaf_slime_m` and `vine_shambler` all have an initial state that is **not** the
first-declared one, and `leaf_slime_s`'s initial state **is** the branch, so it
legitimately draws once at construction.

**Correction to my own SHARED-FINDINGS §0**: I listed 8 hand-rolled ports as
facing a "branch" state needing a distribution argument. `nibbit` and `wriggler`
build a **`ConditionalBranchState`**, which draws nothing and is a deterministic
chain. The real count is **6**.

---

## 4. The 11 unclaimed hook overrides (`monster_state_machine` boundary hole 5)

All 11 audited. **Ten are `waiver`, presentation — and the KinPriest N6 pattern
held far more often than anyone expected.** Read to the end, each of
`Aeonglass.AfterDeath`, `TheInsatiable.AfterDeath`, `Vantom.AfterDeath`,
`SoulFysh.AfterDeath`, `WaterfallGiant.AfterDeath`,
`DecimillipedeSegment.AfterDeath`, `TestSubject.AfterDeath`,
`LagavulinMatriarch.AfterDamageReceived` + `.AfterDeath`, and
`Crusher`/`Rocket`'s `AfterCurrentHpChanged` + `BeforeDeath` reduces to a music
parameter, a barks line, a texture assignment or an animation call.

**One is a LIVE gap: `Queen.AfterDeath`** (§2). The lesson is that N6 is a
*prior*, not a rule — nine overrides that look mechanical are not, and the tenth
hides three real statements inside the same presentation shell.

Two findings worth the seam's attention:

- **`monster_state_machine.md:296-298` is factually wrong.** It says
  "`LagavulinMatriarch.AfterDamageReceived` is the wake-from-damage path whose
  sim counterpart is `AsleepPower` → `wake_up(stunned=True)`". The override is
  entirely presentation; `grep -rn IsShellAwake --include=*.cs src/` returns
  **three** hits, all inside `LagavulinMatriarch.cs` (declaration, its own read,
  its own write), so the flag gates nothing. The mechanical wake really lives in
  `AsleepPower.cs:21-36`. The sentence carries no verdict, so there is no rule-3
  conflict — but it had already been copied into SHARED-FINDINGS §6 and is now
  annotated there.
- **Crusher and Rocket genuinely differ** (rule 29): same guards and bodies, but
  different `ArmSide` and a different FMOD parameter (`2f` vs `1f`). Copying one
  sibling's verdict onto the other would have been wrong in principle even
  though both land on `waiver`.

---

## 5. Cross-record disagreements under rule 3

### 5.1 `ShouldDisappearFromDoom` — three batches, three answers, and **neither of the two confident ones was right**

This is the clearest instance of rule 3 working as a *gap detector* in this
stream, and it is worth reading as a method finding rather than a content one.

SHARED-FINDINGS §4 flagged the property as the one presentation-looking hook not
to reflex-waive. Batch 5 filed a **dormant `gap`** ("the creature is NOT removed
when DoomPower's kill sweep fires"). Batch 8 filed **`faithful`** ("`grep`
returns ten sites and every one is a declaration — a member the game never
reads"). Five other batches filed `waiver`.

Adjudicated by reading `DoomPower.cs` end to end:

- There **is** exactly one reader — `grep -rn ShouldDisappearFromDoom
  --include=*.cs src/` returns 11 lines (the `MonsterModel` virtual, nine
  overrides, and `DoomPower.cs:90`). **Batch 8's premise is false**; it
  undercounted by one.
- But that reader does **not** gate removal. `DoomPower.cs:90` is inside
  `private static async Task PlayVfx`, which early-returns with no visual node
  (`:82-86`), and its result feeds only `StartDoomAnim(nCreature, flag)` and a
  `Cmd.Wait(0.25f)`/`Cmd.Wait(1.5f)` timing branch (`:101-111`).
  `StartDoomAnim`'s `shouldDie` arm is `Monster?.OnDieToDoom()`, a tween,
  `QueueFreeSafely`, a Spine trigger, `RemoveCreatureNode` (the **node**) and a
  vfx variant — and `OnDieToDoom` is documented at `MonsterModel.cs:485-491` as
  "Primarily used set up the creature visuals for the Doom vfx", with an empty
  base body and one override that hides three light nodes.
  **`DoomKill` (`:40-53`) is `await PlayVfx(creature); await
  CreatureCmd.Kill(creature);` — the kill is unconditional and outside
  `PlayVfx`.** **Batch 5's premise is false too.**

**Resolution: `waiver`, presentation, at all nine overriding models.**
`crusher` and `rocket` were amended from dormant `gap` (their rollups fell to
`deliberate-divergence`) and `test_subject` from `faithful`; **two false dormant
gaps left the queue.** The transferable lesson is not about Doom: both wrong
answers came from counting grep *matches* instead of resolving the one reader to
its **enclosing member** — PROMPT.md class 20 pointed at a property.

### 5.2 Prior records this stream contradicts (reported, not edited)

- **`power/sandpit`'s guard "Frantic Escape as the counterplay" is `faithful`**
  and should not be: it compared counts and pile types but not
  `CardPilePosition`, and so cleared what is now `the_insatiable`'s LIVE gap.
- **`power/withering_presence` cites `WitheringPresencePower.cs:37`** as where
  generated Withers are matched. That line is inside `ExtraHoverTips`, a hover
  preview; the real matching happens in `Aeonglass.AfterCardGeneratedForCombat`.
- **`monster_state_machine` G7b's dormancy does not cover its own reachable
  case.** `flyconid`'s `RAND` reaches an **all-zero weight vector** on ported
  act-1 content — the tail `[V_SPORES, FRAIL_SPORES, SMASH]` zeroes all three,
  hit on all five probe seeds at turns 3–23. C# burns one `NextFloat(0)` and
  returns branch 0, and the hand-rolled port does exactly the same, so the port
  is faithful — but the **sim machinery raises** `RuntimeError("No valid
  branch…")`. G7b was labelled dormant on a fuzz of 82 *machines*, and Flyconid
  is hand-rolled, so the fuzz never saw it. **Porting Flyconid onto
  `MachineMonster` — the convention this stream is told to prefer — would crash
  the run.** This is the highest-value cross-record finding in the report.
- **Four new sites of G2's shape** (registered-but-unwired states) beyond G2's
  own Inklet/PhrogParasite: `BygoneEffigy.cs:45` (`SLEEP_MOVE_2`),
  `CeremonialBeast.cs:148` (`STUN_MOVE`), `TerrorEel.cs:73,81` (`STUN_MOVE`).
- `fabricator.py:125-127`'s docstring contradicts `monster_state_machine` seed
  fact 3; it is a stale comment (class 24) and the code is right.
- Hand-off to the **power** stream: the sim's `ImbalancedPower` listens on
  `on_damage_received`, which `cmds.py:118` suppresses on a killing blow, where
  C#'s `AfterDamageGiven` is unguarded. Unreachable for BowlbugRock, but the
  mapping is wrong in principle.

---

## 6. A defect in this stream's own tooling, found by a unit and not by review

`monster_probes.py ctor-order`'s `_CTOR` regex was `def __init__\(self`, which
cannot match a **wrapped** signature (`def __init__(\n        self, ...)`). It
therefore reported **35** constructor-applied-power sites where the true count
is **46**, and SHARED-FINDINGS §2 shipped the wrong population. Batch 2 found it
while auditing its own units; nothing about reviewing the tool would have.

This is the third instance of PROMPT.md v6 item 1 and the first caused by a
*signature-shape* assumption. It matters because an under-reporting sweep
**silently clears** units — the direction nothing downstream re-checks. Fixed,
and `ctor-order` now prints its own coverage (`109 roster units, 28 with no
__init__ matched, 0 unreadable`) so a future regex failure is visible rather
than mute. The eleven hidden units were `axebot, chomper, corpse_slug,
decimillipede_segment, exoskeleton, inklet, kin_follower, phantasmal_gardener,
punch_construct, scroll_of_biting, wriggler`.

The fix also exposed a site the old regex hid completely: **`wriggler` calls
`CreatureCmd.Stun` — not `PowerCmd.apply` — from `__init__`, and its C# model
has no `AfterAddedToRoom` override at all.**

---

## 7. Roster mis-resolutions (reported — `harness.py` and `name_overrides.json` are not ours)

`harness.py roster monster` reports 2 unmatched; both are leading-underscore sim
intermediates and the two batches resolved them **differently, and both are
right**, because the two cases are genuinely different:

- **`__cultist` → `sim_only` record.** There is no shared cultist base in the
  game: `CalcifiedCultist.cs` and `DampCultist.cs` are both `sealed :
  MonsterModel` and each duplicates the whole graph, so pointing the record at
  either would double-count that file's overrides. Executed: `_Cultist(hooks,
  rng)` raises `AttributeError: no attribute 'dark_strike_dmg'` — the base is
  abstract in practice.
- **`__battle_friend` → `BattleFriendV1.cs`**, with V2/V3 hashed as
  `extra_sources`. `_BattleFriend` is the *exact* common part of three real C#
  classes whose `:26-36` are byte-identical, so a `sim_only` rationale would be
  false and would leave the shared machine and starting power audited against
  nothing. Recommended entry:
  `"monster/__battle_friend": "src/Core/Models/Monsters/BattleFriendV1.cs"`.

Note the prompt's premise for `__battle_friend` was itself a tooling artifact:
`ctor-order` said "C# model has NO `AfterAddedToRoom` override" only because the
roster resolved to a nonexistent `BattleFriend.cs`. All three real files
override it.

Also for the seam stream: **`harness.py validate <dir> --strict-inherited`
raises `PermissionError` when given a directory** (it works per-file and in bare
`validate`).

---

## 8. Lessons for `PROMPT.md` (the relic stream owns the file; nothing applied here)

Ranked by how much they would have saved:

1. **New class — branch ADD ORDER, distinct from class 6.** Class 6 catches
   integers; it cannot catch correct-parameter, wrong-order branches. With equal
   weights the histogram is *identical*, so every distribution or marginal check
   clears it. Only a per-draw sequence diff on a shared stream finds it.
   (`inklet`, LIVE, 0/20 000 agreement.)
2. **A regression pin that computes its own expectation from the sim is not a
   pin.** `TestInkletMoveSequence` derives `expected` with the same reversed
   order it should be checking. Pins must name the *source* constant.
3. **Never take a sweep's "0 hits" as covering hand-rolled ports.** G7b's fuzz
   enumerated *machines*; its one reachable instance lives in a port with no
   machine.
4. **A monster's mechanical death behaviour usually lives on its POWER, not its
   model.** `TestSubject.AfterDeath` is cosmetic while `AdaptablePower.AfterDeath`
   carries the whole respawn; auditing the model alone would have cleared the
   boss.
5. **`wasRemovalPrevented` is misnamed in the decompiled source** — it is
   `false` on the real-death branch (`CreatureCmd.cs:519`) and `true` only when
   `ShouldDie` vetoed (`:566`). Reading it as its name inverts every guard using
   it.
6. **Class 21 needs its positive half stated.** `ReattachPower` shows the
   correct landing site is `should_remove_from_combat_after_death`; the class
   currently names only the wrong one. It also needs a companion clause: the
   sim's prevention arm **floors HP at 1** (`cmds.py:112`) where C# leaves the
   corpse at 0, producing off-by-one deltas downstream (`test_subject`: +199 vs
   +200).
7. **New class — a mid-combat spawn has a POSITION, not just an existence.**
   `CombatManager.AddCreature` re-sorts `Enemies` by `Encounter.Slots.IndexOf`
   whenever the added creature carries a slot. (`living_fog`, LIVE; the same
   check *cleared* `gremlin_merc` and `phantasmal_gardener`.)
8. **New class — an encounter builder that ignores its parity RNG parameter.**
   Two gaps here are one line each (`selection_rng` accepted and unused). It is
   invisible to every move/damage probe and breaks replay determinism, not just
   parity. `EncounterModel._rng` (run seed + floor + id hash) has **no sim
   analogue at all** and 20 `create_monsters` overrides take the shared rng.
9. **Check RNG bound conventions, not just constants.** `Rng.NextInt(min,max)`
   is max-**exclusive**; Python's `randint` is inclusive. (`tough_egg`, LIVE.)
   Batch 1 checked all 9 of its HP ranges and found the parity port correct for
   a subtle reason worth recording: the game's range is inclusive *because*
   `Creature.cs:378` pre-computes `MaxInitialHp + 1` and feeds it to both arms.
10. **New class — a C# override may be DEAD in the shipped game while the port's
    equivalent path is live.** `TerrorEel.STUN_MOVE` and
    `BowlbugRock.POST_HEADBUTT→DIZZY` are unreachable in C#; a reviewer diffing
    graphs would file two false gaps.
11. **New candidate — "the initial state is a branch".** Every calibration doc
    assumes step 30's sticky rule makes the opening roll inert. `Fabricator` and
    `ScrollOfBiting` break that: a branch initial state draws and reads live
    combat state during `__init__`, when `combat.enemies` does not yet exist.
    Checklist line: *print `machine._initial_state` and check `is_move` before
    trusting the sticky-no-op argument.*
12. **A C# property can be pure presentation even when its name is mechanical —
    and the way to tell is to resolve the enclosing MEMBER, not the line.**
    (`ShouldDisappearFromDoom`, §5.1; also `WitheringPresencePower.cs:37` inside
    `ExtraHoverTips`.)
13. **`TestMode.IsOff` is the SHIPPING arm.** Class 18 currently reads as if the
    test arm were the trap in both directions; in monster models the guarded arm
    ships and is always presentation.
14. **`AscensionHelper` argument order earned its warning**: one batch had 11
    constants whose ascension value is 1–4 higher than the shipped one; a
    left-to-right read would have produced ~11 false gaps in a single batch.
15. **`extra_sources` hashes must come from `harness.file_sha256`** (LF-
    normalized text), not raw `hashlib.sha256(read_bytes())` — a raw-bytes hash
    validates clean but reports every record stale, so a batch can commit fully
    stale work.
16. **`PowerCmd.Apply`'s `applier` is not decoration**: a null applier skips the
    whole `Hook.ModifyPowerAmountGiven` pass and changes
    `FindExistingInstanceForStacking`'s key.
17. **A C# member with zero readers is `faithful`, not `waiver`** — the v6
    item-3 (`undo_after_obtained`) shape generalises. (Stated for completeness;
    it did **not** apply to `ShouldDisappearFromDoom`, which has one reader.)

---

## 9. Shared verdicts fixed centrally (so eight concurrent batches could not break rule 3)

`audit/content/monster/SHARED-FINDINGS.md` is the durable artifact.

- **Starting powers applied from `__init__` instead of an add-to-room dispatch**
  (46 sites) — **`deliberate-divergence`**, with all three clauses executed:
  (a) the only four ported relics on the reachable hooks gate on `target is
  self.player` / `applier is self.player` / `card is not None`; (b) of the 46
  constructor-applied power classes only `IllusionPower` mentions `max_hp`, and
  only inside `revive()`; (c) all 29 machine sites are `sticky-no-op` first
  rolls. `rocket` and `living_shield` escalated rather than inheriting it and
  came back consistent.
- **The dropped `applier` argument** (11 dedicated guard entries) —
  `deliberate-divergence`, executed: probe enumerates all six sim listeners that
  could see it and none can distinguish. Verified consistent across all records
  at merge.
- **State-id renames** — `faithful`, not worth a guard unless the id is
  load-bearing (the cooldown arm matches by string id; the repeat arms by object
  identity).
- **Presentation surface** — `waiver`, matching N2/N5/N6.

---

## 10. Suite

`2512 passed, 38 xfailed, 2 failed`. Both failures are
`test/test_conformance_floor_state.py` and both are
`FileNotFoundError: …\RunReplays\Resources\933T39V18D\floor_49\actions.sts2replay`.
**Verified environmental, not caused by this stream, on two independent
grounds**: (1) `git diff --stat audit-pipeline...HEAD -- sts2_rl/ test/` is
empty, so no code or test file changed; (2) the fixture directory genuinely does
not exist — `RunReplays/Resources/` contains only `89U21BV1TZ`, `DJDCSAQZNR`,
`L081UMJX4M`, `QRWCVDPZN5`, `TZEKRYTSNT`. The second Ironclad seed's fixture was
captured but never installed on this machine.

---

## 11. Cost data, and the batch-sizing answer the plan asked for

The prompt asked for per-unit cost after batch 1 because the plan's batch size
of 15 was set from cheaper kinds.

**Per-unit cost is dominated by a fixed setup, not by the unit.** Every batch
reported the same curve: the C# and sim reads amortise across a module tree
(units in one module share both files), and building the batch's probe harness
is a one-time cost that pays for every subsequent unit. Measured:

| batch | units | shape of the cost |
|---|---|---|
| 1 | 15 | ≈9 h; ~2.5 h building the reference-machine harness, then ~15 min/unit; 3 units (`ceremonial_beast`, `eye_with_teeth`, `inklet`) took the rest |
| 2 | 15 | ~4–5 min/unit for 11 mechanical units, ~15 min each for 4, +35 min shared probe |
| 3 | 15 | ~14 min/unit for 12, ~40 min each for the 3 with executed reachability; ≈4.5 h total |
| 4 | 15 | ~15–20 min/unit; the 4 Decimillipede records + `waterfall_giant` were half the batch |
| 5 | 15 | ~12 min/unit including four shared reads and six probes |
| 6 | 13 | ~4 tool calls/unit after 3 shared read batches |
| 7 | 15 | ~30 min shared reads, then ~8–12 min/unit, +35 min probe |
| 8 | 6 | ≈6 h for 6 units — deliberately deep; `test_subject` alone was half |

**Recommendation: keep 15 only when the batch is module-coherent.** Batch 1's
own conclusion is the right rule — 15 works *because* all 15 shared one act, one
module tree and one probe harness. A batch spanning acts, or containing several
`MachineMonster` ports with distinct branch shapes, should be **8–10**.

Batch 8's 6-unit batch is the strongest evidence for the exception: the extra
depth is what produced reading `TestSubject.AfterDeath` **to the end** (avoiding
a false gap), reading `AdaptablePower.cs` alongside it (finding the real one),
and *executing* the phase transition with a relic attached rather than reasoning
about it — which is what produced the 1-vs-3 `on_death` count, the +199 delta
and the surviving Enrage. **Bosses and multi-form monsters should be batched at
6, not 15.**
