# Monster stream — shared findings from the pool-wide sweeps

Written before batch 1, per `audit/tools/PROMPT.md`'s "Sweep the shape before
you audit the units". Every number here is reproducible with
`py audit/tools/monster_probes.py <probe>` (and `state_machine_probes.py` for
the branch-argument work the seam already owns).

**Binding on every batch.** Governing rule 3 says the same mechanism gets ONE
verdict at every site, *including across records*. Sections 1–4 below are
mechanisms that recur across dozens of units and their verdicts are fixed here
so eight concurrent batches cannot disagree. Copy the verdict and the rationale;
do not re-derive it, and do not "improve" it into a different verdict. If your
unit gives you evidence that one of these verdicts is WRONG, do not silently
diverge — record your unit with the shared verdict, and report the conflict.

---

## 0. What the sweeps cleared, and what they did not

`hp` — **102 of 109 units compared, 0 mismatches.** Every ported `min_hp`/
`max_hp` pair equals the C# `MinInitialHp`/`MaxInitialHp` **non-ascension**
branch (`AscensionHelper.GetValueIfAscension(level, ascensionValue,
fallbackValue)` — the non-ascension value is the LAST argument, PROMPT.md v5).
Seven are **INCONCLUSIVE and yours to settle by hand**:

| unit | why |
|---|---|
| `__battle_friend`, `__cultist` | roster mis-resolves (see §5) |
| `decimillipede_segment_{front,middle,back}` | inherit HP from `DecimillipedeSegment.cs` |
| `mysterious_knight` | inherits from `FlailKnight.cs` |
| `test_subject` | `MinInitialHp => FirstFormHp`, an indirection the parser does not follow |

A match is **not** a clear for the unit — it compares two numbers and nothing
else. Damage, block, power amounts and counts are still per-unit work.

`kind` — **82 MachineMonster ports, 27 hand-rolled.** The stream prompt
estimated ~18 hand-rolled; the real number is **27**, and this correction goes
in the report. Eight of the 27 face a C# model that builds a **branch** state,
so their sequence-equivalence argument is the hard kind (a distribution, not a
chain): `flyconid`, `inklet`, `leaf_slime_s`, `nibbit`, `phrog_parasite`,
`slithering_strangler`, `twig_slime_m`, `wriggler`. **Zero** ported monsters
face a C# model with no machine at all.

---

## 1. `AddBranch` integer arguments (the stream's headline bug class)

**Already recorded by the seam — do NOT re-verdict (rule 3).**
`audit/records/seam/monster_state_machine.json` **G1** is LIVE and names the
five ports that convert a C# `maxRepeats`/`cooldown` into a sim `weight`:
`flail_knight`, `hunter_killer`, `scroll_of_biting`, `spectral_knight`
(`glory/knights.py`) and `fake_merchant`. Re-run with
`py audit/tools/state_machine_probes.py mismatch` — current output is
**12 resolved pairs covering 13 C# `RandomBranchState`s, 7 exact matches,
5 misreads.**

What that probe does **not** cover, and what each batch therefore MUST do:

- It resolves **one pair per sim module** and only for modules that call
  `add_branch`. The **27 hand-rolled ports draw no branches through it at all**
  (`flyconid` prints "NO add_branch calls (hand-rolled port)"). If your unit is
  hand-rolled and its C# model has a `RandomBranchState`, you must reconstruct
  the branch parameters by hand and compare the resulting **distribution**, not
  the code.
- It compares parameters, never reachability or move CONTENT.

If you find a **sixth** misreading monster, that is a new unit-level `gap`
(cite it as the same bug class as G1, do not restate G1 itself), and it goes in
the report under the headline list.

## 2. Starting powers applied from `__init__` instead of an add-to-room dispatch

**46 sim monsters** apply a power (or block) from `Monster.__init__`
(`py audit/tools/monster_probes.py ctor-order` prints the list).

> **CORRECTED 2026-07-27 — this section shipped the number 35 and it was wrong.**
> Batch 2 found the defect while auditing its own units, not by reviewing the
> tool: `ctor-order`'s `_CTOR` regex was `def __init__\(self`, which cannot
> match a **wrapped** signature (`def __init__(\n        self, ...)`), so the
> sweep under-reported by 11. This is the third instance of PROMPT.md v6 item 1
> and the first caused by a signature-shape assumption; an under-reporting
> sweep **silently clears** units, the direction nothing downstream re-checks.
> The regex is fixed and `ctor-order` now prints its own coverage (109 roster
> units, 28 with no `__init__` matched, 0 unreadable) so a future regex failure
> is visible rather than mute. The eleven units the old sweep hid are
> `axebot, chomper, corpse_slug, decimillipede_segment, exoskeleton, inklet,
> kin_follower, phantasmal_gardener, punch_construct, scroll_of_biting,
> wriggler`. **A batch that cleared any of those of the constructor-order shape
> on the strength of this section's list must re-check it.**
>
> The fix also exposed a site the old regex hid entirely: **`wriggler` calls
> `CreatureCmd.Stun` — not `PowerCmd.apply` — from `__init__`, and its C# model
> has no `AfterAddedToRoom` override at all**, so clause (a) below (which is
> about power/block listeners) does not even address it. It is one of only two
> such units, with `__battle_friend`.

The game
applies these from `MonsterModel.AfterAddedToRoom`, awaited by
`CombatManager.AfterCreatureAdded` (`CombatManager.cs:860-867`) inside
`StartCombatInternal` (`CombatManager.cs:394-398`) — i.e. after every creature
is on the board and **before** `Hook.BeforeCombatStart` (`CombatManager.cs:403`).

The sim runs them at `create_monsters` (`combat.py:134`), which is **before**
relics attach (`combat.py:157-159`), before belt potions register
(`combat.py:164-166`), before the parity Niche HP roll overwrites `hp`/`max_hp`
(`combat.py:152-153`) and before `hooks.on_combat_start` (`combat.py:208`).

**SHARED VERDICT: `deliberate-divergence`.** Rationale to copy (adapt only the
unit's own file:line):

> The sim has no add-to-room phase — creature creation *is* construction — so
> `AfterAddedToRoom`'s effect is applied from `__init__`
> (`<sim file>:<lines>`). Same observable today, established by execution
> rather than assumed, on all three clauses:
> (a) **listener set** — the only ported listeners on the hooks a starting
> power can reach are `relics/ruined_helmet.py:23-38` and
> `relics/unsettling_lamp.py:44-53` (`modify_power_amount`) and
> `relics/vambrace.py:26-40` / `relics/paels_legion.py:36-43`
> (`modify_block_multiplicative`); all four gate on `target is self.player` /
> `applier is self.player` / `card is not None`, and a monster's starting power
> is self-applied with no card, so none of them can fire. `sts2_rl/potions.py`
> implements none of the four hooks.
> (b) **HP-roll inversion** — the sim applies the power before the Niche roll
> and the game after it; of the 35 constructor-applied power classes, only
> `IllusionPower` mentions `max_hp` at all and only inside `revive()`
> (`powers.py:1581`), never at apply time, so no starting amount is computed
> from the pre-roll HP.
> (c) **roll ordering** — `MachineMonster.__init__` rolls the first move
> (`state_machine.py:301`) *before* the subclass applies its powers, but
> `py audit/tools/monster_probes.py roll-order` shows all 29 machine sites are
> `sticky-no-op`: every initial state is a `MoveState`, so
> `monster_state_machine` step 30's early return fires and the first roll
> evaluates no branch and reads no power.
> Concrete trigger that would make it a gap: any relic, potion or power that
> listens on `modify_power_amount` / `on_power_applied` /
> `modify_block_*` without gating on the player, or a starting power whose
> amount reads `owner.max_hp`.

Rule 7: that rationale cites four relic files and `powers.py`; they are **not**
hashed by your record, so say so in the entry as the seam records do.

**Escalate instead of copying** if your unit does something the three clauses
above do not cover — e.g. it reads `hooks.combat.enemies` from `__init__`
(that list does not exist yet: the assignment at `combat.py:134` has not
completed), or it applies a power to a creature other than itself. `Rocket`
(`hive/kaiser_crab.py:108-115`) is the one unit that applies to the **player**
at construction, and `SurroundedPower`'s only `combat.enemies` read is in
`on_death` (`powers.py:2590`), not at apply time — batch 5 must still say so
in the record rather than inherit this paragraph blind.

## 3. `MoveState` ids differ between the two sides

Ports routinely rename states (`CLAW` vs C#'s `CLAW_MOVE`). **`faithful`, and
not worth a guard entry of its own** unless the id is load-bearing: the two
places it is are the cooldown arm of `RandomBranchState._effective_weight`,
which matches by **string id** (`state_machine.py:208`) while the repeat arms
match by object identity, and `CreatureCmd.stun`'s `next_move_key`
(`cmds.py:216-217`). Within one machine the ids are internal and consistent, so
a rename is unobservable; call it out only if a *cross-file* reference uses the
id.

## 4. Presentation surface

`GenerateAnimator`, `SetupSkins`, `DeathSfx`, `HurtSfx`, `TakeDamageSfx`,
`TakeDamageSfxType`, `ShouldFadeAfterDeath`, `ShouldDisappearFromDoom`,
`GenerateBestiaryMoveList`, `L10NMonsterLookup` / `TalkCmd` / `ThinkCmd` barks,
`Cmd.Wait` / `CustomScaledWait`, `TriggerAnim`, `NRunMusicController`,
`NCombatRoom` vfx: **`waiver`, presentation**, matching
`monster_state_machine`'s N2 and N5 and the `KinPriest` precedent (N6 — an
override that *looks* mechanical can be entirely a barks line; read it to the
end before recording a gap). One entry per hook is still required by the
harness, but the rationale can be one line.

`ShouldDisappearFromDoom` was flagged here as the one to think about rather
than reflex-waive. **ANSWERED 2026-07-27 — `waiver`, presentation, at all nine
overriding models.**

> This clause did its job as a rule-3 *detector* and the result is worth
> keeping. Three batches answered it three ways: batch 5 filed a dormant `gap`
> ("the creature is NOT removed when DoomPower's kill sweep fires"), batch 8
> filed `faithful` ("`grep` returns ten sites and every one is a declaration —
> a member the game never reads"), and batches 1/2/3/4/6 waived it. Settling it
> showed **neither of the first two was right**, which is exactly what rule 3
> predicts.
>
> There **is** exactly one reader — `grep -rn ShouldDisappearFromDoom
> --include=*.cs src/` returns 11 lines: the `MonsterModel` virtual, nine
> monster overrides, and `DoomPower.cs:90`. So batch 8's premise is false. But
> that reader does **not** gate removal, so batch 5's is false too:
> `DoomPower.cs:90` sits inside `private static async Task PlayVfx`, which
> early-returns when the creature has no visual node (`:82-86`), and its result
> feeds only `StartDoomAnim(nCreature, flag)` and a
> `Cmd.Wait(0.25f)`/`Cmd.Wait(1.5f)` timing branch (`:101-111`).
> `StartDoomAnim`'s `shouldDie` arm (`:117-134`) is `Monster?.OnDieToDoom()`, an
> `AnimDisableUi` tween, `QueueFreeSafely`, a Spine "Hit" trigger,
> `NCombatRoom.RemoveCreatureNode` (the **node**, i.e. the view) and the
> `NDoomVfx` variant — and `OnDieToDoom` is documented at
> `MonsterModel.cs:485-491` as "Primarily used set up the creature visuals for
> the Doom vfx", with an empty base body and one override
> (`TorchHeadAmalgam.cs:67-79`) that hides three light nodes. **The death itself
> is unconditional and outside `PlayVfx`**: `DoomPower.DoomKill` (`:40-53`) is
> `await PlayVfx(creature); await CreatureCmd.Kill(creature);`.
>
> So the property decides whether the sprite vanishes with the doom animation,
> never whether the creature dies or leaves `Enemies`. `crusher`, `rocket` and
> `test_subject` were amended to `waiver` and their rollups recomputed.
>
> **The transferable lesson is about the grep, not about Doom.** Both wrong
> answers came from counting *matches* instead of reading the one *reader* to
> its enclosing member — batch 8 undercounted by one and concluded "no reader",
> batch 5 found the reader and stopped at the line instead of the method. That
> is PROMPT.md class 20 (a hook dispatched from the wrong *site*) pointed at a
> property: **resolve the enclosing member, not the line.**

## 5. Roster mis-resolutions (report only — `harness.py` is not ours)

`py audit/tools/harness.py roster monster` reports **2 unmatched**:

- `monster/__battle_friend` → expects `src\Core\Models\Monsters\BattleFriend.cs`;
  the real files are `BattleFriendV1.cs` / `V2` / `V3` and the sim's
  `_BattleFriend` is a shared base with no C# counterpart of that name.
- `monster/__cultist` → expects `Cultist.cs`; the real files are
  `CalcifiedCultist.cs` / `DampCultist.cs`.

Both sim classes are leading-underscore intermediate bases. The batch that owns
each decides between a `sim_only` record (needs a rationale naming why there is
no C# counterpart) and pointing at the concrete C# file, and **reports the need
for a `name_overrides.json` entry** — the relic stream owns that file and we do
not touch it.

## 6. The 11 unclaimed hook overrides

`monster_state_machine` boundary hole 5 hands these to us, one per owning
batch. Enumerate with `py audit/tools/dormancy_probes.py cs-monster-hooks`.
`KinPriest` is Task 10's **N6** (`waiver`) and is **not** ours to re-verdict.
For each of the other 11: read the override **to the end** first (N6's lesson),
then find the open-coded sim counterpart — the sim has no `MonsterModel`
listener category (`hook_dispatch` **G5**, dormant, `monsters/base.py:78-81`),
so a ported equivalent lives somewhere else.

> **CORRECTION (batch 3, after reading the override to the end).** This section
> originally repeated `monster_state_machine.md:296-298`'s claim that
> "`LagavulinMatriarch.AfterDamageReceived` is the wake-from-damage path whose
> sim counterpart is `AsleepPower` → `wake_up(stunned=True)`". **The first half
> is false.** `LagavulinMatriarch.cs:130-146` is entirely presentation — a
> `target != Creature` early return, `SleepingVfx?.Stop()`, and two
> `eyes_open` Spine calls plus `IsShellAwake = true`, a flag whose only three
> references in the whole game tree are its own declaration, read and write
> (`grep -rn IsShellAwake --include=*.cs src/`). The mechanical wake really
> lives in `AsleepPower.cs:21-36`, ported at `powers.py:1840-1851`. The seam
> record does not *verdict* the sentence — it is a boundary-hole hand-off — so
> there is no rule-3 verdict conflict, but do not inherit the framing. It is
> the N6 lesson firing a second time: an override that looks mechanical can be
> entirely presentation, and only reading it to the end tells you.

Verdict the **mechanical** behaviour only; do not re-verdict `hook_dispatch`'s G5.

## 7. Findings you must NOT re-verdict (rule 3)

- move-roll RNG stream — `turn_structure` **G9** and `monster_state_machine`
  **G6**;
- the turn-loop half of Stun (`turn_structure`) and its move-machine half
  (`monster_state_machine` **G4**/**G5**);
- `monster_state_machine` **G1**, **G2**, **G3**, **G7**, **G8**, **G9**;
- `creature_card_cmds` step 26 — `SetMaxAndCurrentHp` raw-assigned in
  `hive/decimillipede.py:68,167` and `hive/ovicopter.py`, skipping the clamp,
  the `MaxHp <= 0 → Kill` and `AfterCurrentHpChanged`. **Dormant there; check
  whether YOUR monster makes it live** — that would be a monster-level gap.
- **Death ≠ removal**: a 0-HP creature can persist and keep taking turns. If a
  port conflates death with removal, that IS a monster-level gap.
