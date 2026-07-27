# Source-to-Sim Audit Pipeline — Design

**Date:** 2026-07-24
**Status:** Approved design, pre-implementation
**Goal:** Prove that the sim encodes the same rules as the decompiled game
source by *comparing the two codebases directly*, instead of discovering
divergences one at a time through recorded-run convergence. Audits are
performed by **agents reading both sources** and recording verdicts in a
ledger; a thin mechanical harness enforces completeness and staleness, so
agent judgment is checked but never replaced by parser tooling. The output is
a standing report that answers: which ported units are verified faithful,
which diverge deliberately (and why), which have never been audited, and
which audits have gone stale.

## Problem

Seed convergence (SP3) verifies the sim only along the trajectories that
recorded runs happen to exercise. Bugs like Unsettling Lamp firing through an
Artifact-negated debuff (a hook-ordering bug in `PowerCmd.apply`, since fixed)
survive until a recording happens to combine the right relic, power, and
timing. Manual recordings cannot enumerate that space. The two codebases,
however, are both available in full — so equivalence can be checked at the
source level.

The sim is a deliberate re-architecture, not a transpilation (e.g. C#'s
`cardSource` parameter on the power pipeline became the sim's
`before_card_played`/`on_card_played` bracket), so no mechanical diff can
settle faithfulness; the comparison is inherently semantic. That is agent
work. What agents cannot be trusted with unaided is *completeness* — knowing
they saw every unit and every hook — and that part is trivially mechanical.

**Worked example (found while designing this):** `UnsettlingLamp.cs` guards on
`power.IsVisible`, on `GetTypeForAmount(amount)` (sign-aware — a negative
Dexterity amount counts as a Debuff), and on `ITemporaryPower` double-dipping.
`sts2_rl/relics/unsettling_lamp.py` models none of the three. Each needs a
recorded verdict: faithful, deliberate divergence with rationale (e.g.
`ITemporaryPower` may be unreachable in the Ironclad-only sim), or gap → fix.
That per-guard comparison, recorded durably, is the unit of work.

## Scope

- **In:** engine seams (command layer, turn/combat flow, hook dispatch),
  relics, powers, monsters (stats, moves, state machines), cards,
  enchantments, events' combat-facing effects.
- **Out (for now):** potions (explicitly deferred by Perry), out-of-combat
  UI-only behavior, multiplayer-only code paths, ascension values (sim uses
  non-ascension numbers by convention).
- **Character scope:** the sim is Ironclad-only. Findings about
  unreachable-in-scope mechanics are recorded as waivers, not silently
  skipped.

## Architecture

### The completeness harness (mechanical, deliberately dumb)

`audit/tools/harness.py` — grep/glob-level enumeration only, no parsing:

- **Unit roster:** enumerate ported units by joining the sim registries
  (`ALL_RELICS`, `ALL_POWERS`, card registry, `ENCOUNTERS`, event registry)
  against the game's model directories (`src/Core/Models/<Kind>/*.cs`),
  producing the audit work queue and flagging units present on one side only.
- **Hook checklist per unit:** list every `public override` signature in the
  unit's C# file (a one-regex scan of decompiled output, which is uniform).
  These become required entries in that unit's audit record.
- **Hashing:** sha256 of both source files (line-ending-normalized) recorded
  at audit time; hash drift ⇒ the audit is stale.
- **Record validation:** an audit record is rejected unless every enumerated
  hook has a verdict, every verdict uses the allowed vocabulary, and
  gap/waiver/deliberate-divergence verdicts carry rationale text.

The harness never judges faithfulness. It guarantees that agents cannot skip
a unit, skip a hook, or leave a verdict vague — the failure modes of pure
LLM audits.

### Tier 1 — agent content audits (relics, powers, monsters, cards, …)

An audit batch = one pool slice (e.g. 15 relics). For each unit, an agent:

1. Reads the C# model and the sim counterpart in full.
2. Fills in the harness-generated record skeleton: per-hook mapping and
   verdict, per-guard findings (the Lamp example above is the template),
   numeric constants checked against the non-ascension branch of
   `AscensionHelper.GetValueIfAscension(...)`, and — for monsters — the move
   state machine (`AddState`/`AddBranch` graphs, with explicit attention to
   argument roles: weight vs cooldown vs maxRepeats, the exact misreading
   that produced the TwigSlimeM/Flyconid bug).
3. Files every **gap** with a queued fix; a gap fix follows the normal
   workflow (failing test first, then the engine change).

The audit prompt is a versioned artifact (`audit/tools/PROMPT.md`) listing
the known bug classes to check for — killing-blow guards, Artifact
interception order, sign-aware power typing, visibility guards, pile-limbo
membership — so lessons from past divergences compound instead of living in
one session's context.

### Tier 2 — engine-seam ordering audit (the Lamp×Artifact class)

Ordering and guard bugs concentrate in a small file set:

| C# seam | Sim counterpart |
|---|---|
| `src/Core/Commands/DamageCmd.cs` (+ `ValueProps/`) | `cmds.py` DamageCmd, `valueprops.py` |
| `src/Core/Commands/PowerCmd.cs` | `cmds.py` PowerCmd (Artifact interception) |
| `src/Core/Commands/CreatureCmd.cs`, `PlayerCmd.cs`, `CardCmd.cs`, `CardPileCmd.cs` | `cmds.py` remainder |
| `src/Core/Combat/CombatManager.cs`, `PlayerTurnPhase.cs` | `combat.py`, `player.py` |
| `src/Core/Hooks/Hook.cs`, `AbstractModel.cs` | `hooks.py` |
| `src/Core/MonsterMoves/` machinery | `monsters/state_machine.py` |

For each seam, an agent:

1. **Extracts an ordering spec from the C#**: a numbered sequence of steps,
   guards, and early returns (e.g. the damage pipeline: powered modifiers →
   cap → `on_attacked` → block absorption → `modify_hp_lost` → apply → death
   check → post-damage events; the killing-blow guard at `CreatureCmd.cs:392`
   `!WasTargetKilled || !IsDead`). Specs live as markdown in
   `audit/seams/<seam>.md` — human-reviewable, and the durable statement
   of what the sim claims to implement.
2. **Compares the sim step-by-step** against the spec; every step gets a
   verdict in the seam's ledger record.
3. **Pins the verdict with an order-tracing test** in
   `test/test_hook_order.py`: wrap/instrument `HookSystem` dispatch in the
   test to record the exact hook-call sequence for a crafted scenario, and
   assert the full ordered sequence. The tests — not the agent's reading —
   are what make the audit durable: a future edit cannot silently reorder a
   seam without a failure.

Every seam bug already found and fixed becomes a spec line plus a pinned
test on day one: Artifact-interception vs `modify_power_amount` order
(Unsettling Lamp), the killing-blow `AfterDamageReceived` skip, the
Play-limbo reshuffle exclusion, `CheckWinCondition` running after player-turn
setup, out-of-combat transform appending at deck end, `AfterTurnEnd` firing
after the hand flush.

### Tier 3 — audit ledger with staleness tracking

One JSON record per audited unit under `audit/records/<kind>/<id>.json` (JSON, not
YAML — no new dependency), written by the auditing agent and accepted only
if it passes harness validation:

```json
{
  "unit": "relic/unsettling_lamp",
  "game_source": {
    "path": "src/Core/Models/Relics/UnsettlingLamp.cs",
    "sha256": "<recorded at audit time>"
  },
  "sim_source": { "path": "sts2_rl/relics/unsettling_lamp.py", "sha256": "<...>" },
  "hooks": {
    "BeforeCombatStart": { "maps_to": "on_combat_start", "verdict": "faithful" },
    "BeforePowerAmountChanged": {
      "maps_to": "modify_power_amount",
      "verdict": "deliberate-divergence",
      "rationale": "cardSource parameter modeled as before/on_card_played bracket"
    }
  },
  "guards": [
    { "what": "power.IsVisible", "verdict": "gap",
      "issue": "sim doubles debuffs from invisible powers" },
    { "what": "ITemporaryPower double-dip", "verdict": "waiver",
      "rationale": "no ITemporaryPower in Ironclad-obtainable scope" }
  ],
  "verdict": "gap",
  "audited": "2026-07-25"
}
```

Verdict vocabulary (per hook/guard and rolled up per unit): **faithful**,
**deliberate-divergence** (+ rationale), **waiver** (out of scope, + rationale),
**gap** (divergence found → fix queued; the record is updated when the fix
lands and a re-audit of the changed unit confirms).

**`audit/tools/audit_status.py`** aggregates the ledger against the harness roster
and the source trees:

- coverage: audited / unaudited units per pool;
- staleness: any unit whose current source hash (either side) differs from
  the hash recorded at audit time is **stale** and drops out of "verified"
  until re-audited;
- open gaps;
- exit code non-zero on new unaudited content, stale audits, or open gaps
  above thresholds — suitable as a standing check beside the test suite.

The success statement this enables: *"N of M in-scope units audited faithful,
zero stale, zero open gaps."*

## Order of attack

1. **Engine seams (Tier 2)** — highest blast radius; every content audit
   implicitly relies on them.
2. **Relics + powers** — interaction-heavy; where the Lamp-class bugs live.
3. **Monsters** — state-machine monsters audited graph-against-graph; the
   ~18 hand-rolled monsters are flagged for either careful manual audit or
   state-machine ports (preferred, per existing convention).
4. **Cards** — mostly numbers and keywords; the cheapest per-unit audits.
5. **Enchantments / event combat effects** — small pools, after the above.

Audit passes run as dispatched agent batches (one batch ≈ one pool slice),
with the harness roster as the work queue and `audit_status.py` as the
progress report. Batches are independent, so they parallelize.

## Testing

- Harness tests: roster join (unit on one side only), override enumeration
  against a fixture C# file with `Early`/`Late` variants, record validation
  (missing hook verdict / bad vocabulary / missing rationale each rejected),
  staleness detection (hash drift), exit codes.
- Order-tracing tests are themselves the Tier 2 deliverable; they run in the
  normal suite (`py -m pytest test/ -q`).
- Every **gap** fix lands with its own failing-then-passing regression test,
  per the standard workflow — so agent findings are verified by execution,
  not taken on faith.

## Honest limits

- Agent audits are fallible readers: a wrong "faithful" verdict is the
  residual risk the harness cannot catch. Mitigations: the versioned
  bug-class checklist in the audit prompt, order-pinning tests for
  everything in Tier 2, execution-verified fixes for every gap, and the
  five recorded conformance seeds remaining as the runtime regression net.
- Re-audits cost agent time, not script time — staleness is expected to be
  rare (the game source is frozen; sim files change on fixes), so the cost
  is bounded and `audit_status.py` makes it visible rather than silent.
- A static audit proves the sim *encodes the same rules*; it can miss
  emergent interactions that two individually-faithful units produce
  jointly. The previously-designed game-in-the-loop self-play fuzzer remains
  a compatible future add-on, and ledger entries agents flag as statically
  unsettleable are its natural target list.
- The decompiled source is itself the ground truth per the golden rule; where
  decompilation artifacts obscure semantics, the audit records the ambiguity
  rather than guessing.
