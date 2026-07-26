# Stream 2 continuation — content audits: powers (89 remaining units)

The power stream audited **45 of 134** units on branch `audit-power` and
stopped on session context, not on scope. This prompt continues it. Everything
the first session learned that is reusable is either in the committed report or
in a committed probe — the point of this prompt is that you should **not**
re-derive any of it.

Prior commits on `audit-power`: `e6170905` (batch 1), `e9a046ad` (batch 2),
`62b0d42f` (batch 3), `e90f112f` + `370ce70c` (the report).

## Read first, in order

1. `docs/superpowers/prompts/_shared-audit-contract.md` — your binding
   contract. The eight verdict rules, file ownership, the per-unit procedure.
   Follow it exactly.
2. **`.superpowers/sdd/content-power-report.md` — the most valuable thing you
   will read.** It carries the finished census results (final for all 134
   units), every recurring mechanism already named so you can cross-reference
   instead of re-arguing, the per-group residual queue, and the cost data.
3. `tools/audit/PROMPT.md` — the bug-class checklist. **Read-only for you**;
   the relic stream owns it. It may have been hardened since the last session,
   so read the current version and re-read it at each batch boundary. The
   report's section 7 lists seven lessons proposed for it that had not landed
   as of the last session — treat those as live checklist items even if the
   file does not yet contain them.
4. `docs/audit/seams/power_cmd.md` and `docs/audit/seams/hook_dispatch.md` —
   the machinery your units plug into. You need their gap lists (G1-G9 in
   hook_dispatch, G1-G6 plus the two step-level findings in power_cmd) because
   a large fraction of your verdicts are cross-references to them under rule 3.
   Skim `docs/audit/seams/turn_structure.md`'s **G5** and **G11** too.
5. Two or three existing records, as format calibration — `audits/power/thorns.json`
   (a live gap with executed evidence), `audits/power/tainted.json` (a clean
   faithful unit) and `audits/power/rebound.json` (a unit whose verdicts are
   mostly cross-references).

## Your scope

The **89 unaudited power units**. Split into two disjoint halves so two
sessions can run concurrently in sibling worktrees; take the half you are
assigned.

```bash
cd C:/Users/Perry/Desktop/sts2-rl
git worktree add C:/Users/Perry/Desktop/sts2-rl-power-a -b audit-power-a audit-power   # half A
git worktree add C:/Users/Perry/Desktop/sts2-rl-power-b -b audit-power-b audit-power   # half B
```

**Do not share one worktree between two sessions.** `harness.py validate` with
no arguments validates every record in the tree, so an unfilled skeleton left
by the other session blocks yours, and `git add audits/power` would stage their
half-written records. Separate worktrees keep both problems away; the branches
merge trivially afterwards because the records are disjoint files.

**Half A — 41 units, player-side: Ironclad card powers, colorless, potion-source,
event-card:**
`automation, battleworn_dummy_time_limit, block_next_turn, buffer, calamity,
clarity, confused, curious, dark_shackles, diamond_diadem, draw_cards_next_turn,
energy_next_turn, entropy, fasten, feeding_frenzy, free_attack, gigantification,
hello_world, improvement, juggernaut, mangle, mayhem, no_block, nostalgia,
plating, prep_time, pyre, radiance, reptile_trinket, retain_hand,
rolling_boulder, setup_strike, shackling_potion, stampede, stratagem, the_bomb,
the_gambit, toric_toughness, unmovable, vicious, vigor`

**Half B — 48 units, enemy powers (Overgrowth / Hive / Glory):**
`adaptable, asleep, back_attack_left, back_attack_right, burrowed,
chains_of_binding, crab_rage, dampen, escape_artist, flutter, galvanic,
hard_to_kill, hardened_shell, hatch, hex, high_voltage, illusion, imbalanced,
infested, mind_rot, minion, nemesis, painful_stabs, paper_cuts, personal_hive,
plow, possess_speed, possess_strength, rampart, ravenous, reattach, sandpit,
slippery, sloth, slow, slumber, soar, steam_eruption, stock, strangle, suck,
surprise, surrounded, swipe, territorial, vital_spark, waste_away,
withering_presence`

Verify your half against the live roster rather than trusting this list:

```
py -c "import json,glob,sys; sys.path.insert(0,'.'); from tools.audit.harness import roster; done={json.load(open(p))['unit'].split('/')[1] for p in glob.glob('audits/power/*.json')}; print([r['unit'].split('/')[1] for r in roster('power') if r['unit'].split('/')[1] not in done])"
```

## Do not re-derive these — they are settled and committed

`tools/audit/power_census.py` is committed and answers the population
questions once for all 134 units. Run all nine subcommands at the start and
keep the output; several of your verdicts are one lookup each.

```
py tools/audit/power_census.py typing | slots | stack | instance | visible
py tools/audit/power_census.py multipliers | neg-appliers | unregistered | overrides
```

Settled facts, with the record wording already drafted in the report:

- **Bug class 3 (sign-aware typing) is CLOSED.** Only `strength` and
  `dexterity` flip. `shriek` and all 28 arm-2 powers are inert, the latter
  because the sim's `_tick`/`_tick_duration` bypass `PowerCmd` entirely. If
  your unit shows up in the `typing` census, say so and cite the census; do not
  re-argue it.
- **Bug class 4 (visibility guards) is CLOSED game-wide.** `0 of 260` power
  `.cs` files override `IsVisibleInternal`, so an `IsVisible` guard is always a
  `waiver`.
- **`PowerStackType.Single` does not mean "re-application is a no-op."** 15
  units override `on_stack` to `pass` citing it and are wrong; the only
  per-unit question left is "does anything read `Amount`". Report section 10
  item 2 lists which of the 15 are still unaudited.
- **Non-dyadic multipliers**: Shrink `0.7`, Slow `0.1`, and
  `Vulnerable + Cruelty`'s computed factor. All damage; every block multiplier
  is dyadic. If you find a fourth, say so loudly — it widens `hook_dispatch` G9.
- **The side-hook → sim-slot table** (report section 5) resolves every
  `*SideTurn*` override to its `CombatManager` call site. `AfterSideTurnEnd` is
  dispatched by `Hook.AfterTurnEnd`, which is not guessable from the name.

## The recurring gap shapes to check on every unit

These came out of the first 45 and each one hit multiple units. Check all of
them; the report has citable wording for each.

1. **`props` omitted on a `BlockCmd.apply` / `DamageCmd.deal` call.** Defaults
   to `ValueProp.MOVE`, i.e. *powered*, picking up Dexterity/Frail/Strength/
   Vulnerable the game excludes. Live on `feel_no_pain` and `curl_up`; eight
   sibling powers pass `UNPOWERED` correctly, so it is a call-site omission.
2. **Wrong turn slot** (section 5's table). The player-side
   `AfterSideTurnEnd → on_player_turn_end` case has a concrete live route:
   `StampedePower` auto-plays Attacks from its own `on_player_turn_end`, so the
   power is still present in the game and registration-order-dependent in the sim.
3. **`all_cards` omits the Play pile** (`player.py:100-103` vs
   `PlayerCombatState.cs:70-80`). Any unit that sweeps the owner's cards.
4. **A before-hook ported onto an after-hook.** `thorns`
   (`BeforeDamageReceived`), `curl_up` and `skittish` (`AfterAttack`). Two
   consequences each: the killing-blow guard (`cmds.py:121`) suppresses the
   after-hook, and effects granted inline are visible to later hits of the same
   multi-hit card. `hooks.py` has `before_attack`/`after_attack` slots that go
   unused.
5. **A missing `applier=`** on a `PowerCmd.apply` call C# passes one to.
   `PossessStrengthPower`/`PossessSpeedPower` are the ported readers.
6. **A hook the sim HAS but the unit does not use.**
   `modify_card_play_result_pile`, `after_attack`, `after_player_turn_end`,
   `after_modify_hp_lost`. When the right hook exists and is unused, the
   contention with the unit that *does* use it is usually the real gap
   (`corruption`/`rebound` vs `nostalgia`).
7. **`HittableEnemies` vs `not is_gone`.** The sim aims at creatures
   `Hook.ShouldAllowHitting` would refuse; mitigated because `DamageCmd.deal`
   re-checks, so usually dormant.
8. **A guard the sim ADDS.** Sometimes defensive and harmless, sometimes a real
   divergence — `tangled`'s added `Affliction == null` changes the outcome
   because C#'s `AfterApplied` deliberately overwrites.

## Method that worked, and the traps

- Dump C# in groups of 6-8 with **real line numbers**:
  `grep -n "" X.cs | grep -v "^[0-9]*:using \|^[0-9]*:$\|^[0-9]*:namespace \|ExtraHoverTips\|CanonicalVars\|HoverTip\|SfxCmd\|Flash()\|Vfx"`.
  **Do not** filter with `awk` before numbering — it renumbers and every
  citation you write will be wrong (this happened once and had to be redone).
- Write records through a small filler script in the scratchpad that takes a
  compact `{hook: (maps_to, verdict, text)}` dict, recomputes the rollup, stamps
  `audited`, and calls `harness.validate_record`. Hand-writing JSON for 40 units
  is not worth the tokens. Keep it in the scratchpad — it produces no numbers,
  so the contract does not require committing it.
- **`python` is not on PATH in this environment. Use `py`.**
- `harness.list_overrides` **misses overrides whose return type is a tuple**
  (`ModifyCardPlayResultPileTypeAndPosition` — hit `corruption` and `rebound`).
  Validation accepts extra hook keys, so add the missing override to the record
  by hand and note it. Check every unit's C# for a `public override (A, B) Name`.
- A `public` method that is not `public override` is not a hook and the harness
  will not enumerate it (`CrueltyPower.ModifyVulnerableMultiplier`,
  `PoisonPower.CalculateTotalDamageNextTurn`). Record that you saw it so a
  reader does not think it was skipped.
- Never leave an unfilled skeleton at a batch boundary — `validate` fails on
  empty verdicts. Only generate skeletons for units you are about to fill.
- The suite takes ~4 minutes and correctly never moves off the baseline
  (audits add no code). Budget for it; do not skip it.

## Batching

15 units per batch. After each batch, in this order:

```
py tools/audit/harness.py validate          # 0 invalid
py tools/audit_status.py --kind power
py -m pytest test/ -q                       # must be 2476 passed / 31 xfailed
git add audits/power && git commit          # name the units and the gap count
```

Commit the moment it validates; do not polish first. Sessions here die at usage
limits and committed files are what survive. **Never push. Never touch `main`.**

## Report

**Do not start a new report.** Update
`.superpowers/sdd/content-power-report.md` at the end of every batch — it is
written to be extended, and its section numbering is referenced by the commit
messages. Keep the counts table, section 4 (live gaps), section 5 (the slot
population), section 6 (rule-3 disagreements), section 7 (PROMPT.md lessons),
section 8 (harness/roster problems), section 9 (cost data) and section 10 (the
residual queue) current.

If you are working half A or half B concurrently with the other, write your
batch findings to `.superpowers/sdd/content-power-report-<a|b>.md` instead and
leave the main report alone; whoever merges the two branches folds them in.
That avoids the one file the two halves would otherwise collide on.

Carry forward in particular:

- any **fourth non-dyadic multiplicative factor** (widens `hook_dispatch` G9);
- any **cross-record disagreement** under rule 3. One is already open: section 6
  argues `turn_structure` **G5**'s dormancy rests on "every ported listener
  self-filters to its own owner", which does not reach `battleworn_dummy_time_limit`
  (escapes its owner), `asleep` (removes another power) or `slumber` (stuns) —
  **all three are in half B**, so half B should settle it, ideally by executing
  a two-dummy Battle Friend witness;
- the **live/dormant split** on every gap, with reachability proven per rule 6;
- **cost data** — wall time and tokens per unit, gap rate, how many units needed
  execution.
