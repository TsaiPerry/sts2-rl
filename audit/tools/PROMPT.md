# Audit prompt — source-to-sim unit audits (v1)

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

## Scope

Potions: out of scope entirely. Ascension values: out of scope. Characters
other than Ironclad: `waiver` with rationale. Multiplayer-only params
(PlayerChoiceContext etc.): note in `maps_to` mapping, not a divergence by
themselves.
