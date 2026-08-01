# R9 — AfterAttack: results payload fidelity + skittish/suck/painful_stabs

Read first: `.superpowers/sdd/round13/PROTOCOL.md` (binding). Maps scouted
2026-08-01. Wave 3: R1 (hooks.py registry rework) and R5 (Play pile,
cmds.py/combat.py) have landed — read current code, line numbers below may
have drifted; re-verify everything.

## Premise correction (the queue and ledger are stale)

The sim ALREADY HAS an AttackCommand-level `after_attack` hook: an
attack "bracket" (`hooks.before_attack`/`after_attack`, `hooks.py:1061-1090`)
around `combat.py:951/:964` (player card, once per play-count iteration)
and `monsters/base.py:190/:195` (monster move). Results accumulate at
`cmds.py:404-408` into `hooks._attack_results` as a FLAT
`list[(receiver, hp_lost)]`. Suck (`powers.py:2000-2023`) and Painful
Stabs (`powers.py:4102-4134`) are ALREADY on it; VigorPower (`:2340`) and
GigantificationPower (`:4756`) too. The gap-ledger citations
(`audit/content/power/gap-ledger.md:428-432, 707-709, 856-859`) describe a
pre-port world. What actually remains:

## 1. Skittish moves onto after_attack (the LIVE-ish item)

C# `SkittishPower.cs:56-69` (AfterAttack): guards
`!HasGainedBlockThisTurn && command.DamageProps.HasFlag(ValueProp.Move)
&& command.ModelSource is CardModel`, then
`command.Results.SelectMany(r=>r).FirstOrDefault(r => r.Receiver == Owner)`
and requires **that first result** to have `UnblockedDamage != 0`.
- **`FirstOrDefault`, not `Any`**: a multi-hit attack whose FIRST hit on
  the owner is fully blocked and second connects grants NO block. Pin
  this exact semantic.
- Sim today (`powers.py:2199-2242`): on_damage_received per hit — fires
  once per HIT, and (worse) C# skips a victim's AfterDamageReceived on a
  killing blow while AfterAttack still fires — the hook-level divergence
  this port fixes.
- Gate mapping: `card is not None` in after_attack is a sufficient proxy
  for Move+CardModel (both DamageProps.CARD and CARD_UNPOWERED include
  MOVE — `valueprops.py:34,36`); block gain stays
  `BlockCmd.apply(..., props=ValueProp.UNPOWERED)` (`SkittishPower.cs:66`);
  reset slot `after_player_turn_end` (`powers.py:2240-2242`) already
  matches AfterSideTurnEnd-with-side-guard.
- The results payload must then carry enough for the Receiver search —
  see item 4.

## 2. Suck counts GROUPS, not results (power/suck/g2)

C# `SuckPower.cs:22-47`: guards `Attacker != Owner || TargetSide ==
Owner.Side || !DamageProps.IsPoweredAttack()`; then per HIT-GROUP
(`foreach List<DamageResult> item in Results`): strip pet-owner
duplicates, `if (item.Any(r => r.UnblockedDamage > 0)) num++` — one AoE
hit touching 3 creatures = 1. Then `PowerCmd.Apply<StrengthPower>(...,
Amount * num, applier: Owner)`.
Sim (`powers.py:2018-2019`) counts RESULTS and omits the
`is_powered_attack` guard (`valueprops.py:47-49` exists) and the
`applier=self.owner`. Fix all three. Note: no pets and a single player
creature make groups==results TODAY for Suck's owner (Fossil Stalker) —
dormancy-preserving, but the payload fix (item 4) makes it faithful
outright.

## 3. Painful Stabs: the removal veto

C# `PainfulStabsPower.cs:29-32`:
`ShouldCreatureBeRemovedFromCombatAfterDeath(creature) => creature != Owner`.
Sim has the hook surface (`hooks.py:1588-1595`, consumed `cmds.py:159-161`)
and four powers implement it (Illusion `powers.py:1949-1956`, SteamEruption
`:2459-2460`, Reattach `:2873-2876`, Adaptable `:4078-4082`) — Painful
Stabs does not. Add it (`creature is not self.owner`). AdaptablePower on
the same Test Subject makes it behaviorally redundant today — say so in
the close note; add the pin anyway (monkeypatch/synthetic if needed).
Also verify the AfterAttack body against `PainfulStabsPower.cs:34-68`:
flatten (unlike Suck), early-out if nothing unblocked, bucket by PLAYER
receiver, ONE AddToCombatAndPreview per receiver with `Amount * num`
count — the sim loops `range(amount*hits)` with per-card calls
(`powers.py:4126-4130`-ish): same observable? Derive and say.

## 4. The results payload has three fidelity defects — fix them

C#: `AttackCommand._results` is `List<List<DamageResult>>` — outer axis
HITS, inner axis targets-of-that-hit (`AttackCommand.cs:76, :138-143`,
appended per hit at `:653/:673-676`); AfterAttack dispatched ONCE at
`:656` after the hit loop (and the AttackContext grouping twin,
`AttackContext.cs:74`, used by EchoingSlash/Omnislice). DamageResult
carries Receiver/Blocked/Unblocked/Overkill/WasBlockBroken/
WasFullyBlocked/WasTargetKilled (`DamageResult.cs`).
Sim defects:
a. **No grouping** — flat list loses hit boundaries (Suck's axis). Make
   the accumulator grouped (one group per hit): monster hit loop
   (`monsters/base.py:191-194`) pushes a group per iteration; the player
   AoE fan-out (`combat.py:952-959` — one on_play per living enemy inside
   ONE bracket) must yield ONE group per hit — derive from C# what a
   sim "hit" is on that path and document it.
b. **Non-attack damage pollutes the window** — `cmds.py:407` appends on
   EVERY DamageCmd.deal while the bracket is open (Thorns reflect,
   poison...). C# only appends its own attack's damage. Filter (by
   dealer-of-the-bracket and/or props) — derive the correct predicate
   from where C#'s AttackCommand.Execute calls CreatureCmd.Damage.
c. **Nested brackets clobber** — `after_attack` nulls `_attack_results`
   unconditionally (`hooks.py:1088`); an attack auto-playing another
   attack (havoc path) makes the inner close wipe the outer accumulator.
   Save/restore a stack.
Ordering: AfterAttack sits after every Damage incl. Kill processing —
the sim bracket already closes after `_resolve_death` (`cmds.py:358-359`);
keep it that way, and keep `after_attack` in `_COMBAT_GATED_HOOKS`.
A victim's powers strip on death (`cmds.py:180-196`) so a dead Skittish
owner gains nothing — matches C# (`ShouldPowerBeRemovedAfterOwnerDeath`).

## Footprint (yours alone this wave)

`sts2_rl/powers.py` (Skittish/Suck/PainfulStabs), `sts2_rl/hooks.py`
(bracket/accumulator), `sts2_rl/cmds.py` (the append site),
`sts2_rl/monsters/base.py` (`_execute_attack` grouping),
`sts2_rl/combat.py` (`:951-964` bracket/AoE grouping only), plus tests.
NOT yours: `driver.py`, `run.py`, `rewards.py`, `events/**`, relic/card
content files, `audit/**`.

## Tests

WILL BREAK (scouted): `test/test_underdocks.py:400/:412/:420` — the three
skittish tests call DamageCmd.deal directly with NO attack bracket;
re-stage them (wrap in a bracket or play a real card) preserving intent.
`TestFossilStalker` (`:169-189`) covers Suck. New pins: once-per-attack
firing with multi-hit; FirstOrDefault semantics (first-hit-blocked case);
group counting for an AoE hit; pollution filter (thorns during an attack
doesn't enter results); nested-bracket isolation (havoc-shaped);
painful-stabs veto. Natural home: `test/test_new_features.py`
TestAttackBoundary (`:317-353`), `test/test_glory.py:628` area.

## Entries to settle (propose in report; controller applies)

`power/skittish/AfterAttack` (hooks key), `power/suck/AfterAttack` +
`power/suck/g2`, `power/painful_stabs/AfterAttack` +
`power/painful_stabs/ShouldCreatureBeRemovedFromCombatAfterDeath` — these
five were carved OUT of the triage batches for you. Also flag the stale
gap-ledger citations and the BoneFlute/Flatten (Osty-pet-only,
unreachable: no pets in sim) facts for the record notes.

Report path: `.superpowers/sdd/round13/R9-report.md`.
