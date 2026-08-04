# Engine seam: `potion_pipeline`

**STATUS: AUDITED, verdict `gap`.** Wired 2026-08-03 (P1-T2 of the
systems-tier campaign, `commands_remainder` decision) and audited the same
day (P2). `audit/records/seam/potion_pipeline.json` carries 14 `steps`
(`PotionModel.OnUseWrapper` plus the three named base virtuals) and 9
`guards` (the `PotionCmd` verbs, the belt, generation draws, and the
placeholder/cross-character potion split) — `harness.py validate` and
`citation_check.py` both report 0 problems.

**Headline finding: the documented hole this seam was created to close was
already closed by the time this pass started, just not where the hole's own
paper trail said to look.** `harness.MODEL_ROOT_CLASSES`'s comment and
`audit/content/potion/shared-mechanisms.md` (the "recorded once" narration
doc, written 2026-07-26/27) both still describe `Hook.BeforePotionUsed` (W2)
and `Hook.AfterPotionUsed`'s empty-hand follow-up (`CheckForEmptyHand`, W10)
as undispatched LIVE gaps, and `IsExecutingCardOrPotionEffect` (W4) as an
unported dormant gap. **All three are faithful today.** A later round
(2026-07-29, "round 6/7") shipped `combat.py`'s `before_potion_used` /
`_card_or_potion_effect()` / `_check_for_empty_hand` dispatches, and — this is
the part that matters for how staleness actually happens in this campaign —
**every one of the 51 `potion/*` content records already carries the
corrected, current verdict** (their shared `W`/`W4` guards, all `faithful`,
citing the same fix). The narration doc in `audit/content/potion/` is the
only place that never got the update; this seam's own record does not
re-derive those three steps, it matches the 51 records' already-correct
verdict per rule 3 and calls out the doc's staleness in its steps 2/4/10
rather than re-opening a closed question. One new LIVE gap was found in the
process: `potion/foul_potion.json`'s `PassesCustomUsabilityCheck` gap is
tagged `live: false` on 2026-07-27 evidence ("nothing drives
`RunState.use_potion`") that a *sibling* fix in the same record (its `Usage`
hook, dated 2026-07-28) already invalidated — `conformance/runner.py:846`'s
`_use_map_potion` now wires that path into every replay. See this record's
step 13.

## Why this seam exists: the `commands_remainder` decision

`src/Core/Commands/` has 20 `.cs` files. Seven were already claimed by
existing seams before this task (`DamageCmd`, `CreatureCmd`, `PowerCmd`,
`CardCmd`, `CardPileCmd`, `CardSelectCmd`, and — the file the P1-T2 brief's
own count of "seven" missed — `PlayerCmd`, claimed by `creature_card_cmds`).
The remaining 13 were reviewed one file at a time rather than made a seam of
their own, per the source prompt's instruction to "fold each file into the
seam above that owns its subject instead."

**The full disposition of all 13:**

| File | Disposition | Reason |
|---|---|---|
| `RewardsCmd.cs` | → `rewards` | `OfferForRoomEnd`/`OfferCustom`/etc. — thin wrappers around `RewardsSet`. |
| `MapCmd.cs` | → `rooms_and_map` | `SetBossEncounter`'s one behavioral line. |
| `RelicCmd.cs` | → `relic_pools` | `Obtain`/`Remove`/`Replace`/`Melt`. |
| `RelicSelectCmd.cs` | → `relic_pools` | The choose-a-relic screen pick. |
| `ForgeCmd.cs` | Out of scope | Regent-only (Forge mechanic); Ironclad-irrelevant. |
| `OrbCmd.cs` | Out of scope | Defect-only (Orb mechanic); Ironclad-irrelevant. |
| `OstyCmd.cs` | Out of scope | Necrobinder-only (Osty/pet mechanic); Ironclad-irrelevant. |
| `SfxCmd.cs` | Out of scope | Presentation (sound effect triggers). |
| `VfxCmd.cs` | Out of scope | Presentation (visual effect triggers). |
| `TalkCmd.cs` | Out of scope | Presentation (dialogue/talk bubbles). |
| `ThinkCmd.cs` | Out of scope | Presentation (monster "thinking" UI state). |
| `Cmd.cs` | Out of scope | **Overrules the brief's suggested `run_layer` fold** — on inspection this file is nothing but Godot scene-tree timer waits (`Wait`/`CustomScaledWait`) for animation pacing, i.e. presentation, the same category as the four `*Cmd` files above it in this table, not run orchestration. |
| `PotionCmd.cs` | → **this seam** (`potion_pipeline`) | No natural fold target — see below. |

`PotionCmd.cs` does not belong to any existing seam's subject: it is not
reward generation (`rewards`), not pool composition (`relic_pools`), and not
run orchestration (`run_layer`) — it is the entire belt-procurement/discard
pipeline (`TryToProcure`/`Discard`, each wrapping a `Hook.*` dispatch). Folding
it into `rewards` or `relic_pools` would misdescribe it as one of those
subjects' problems. It is paired here with `PotionModel.cs` rather than left
to float alone, because `PotionModel.cs`'s `OnUseWrapper` — the shared use-path
wrapper every one of the 51 potions' own `OnUse` override runs inside — was an
already-documented, explicitly-flagged hole: `harness.MODEL_ROOT_CLASSES`'s
block comment named it directly ("There is no potion seam, so stopping at
`PotionModel` means `PotionModel.OnUseWrapper` — the whole use path for all 51
potions — is verdicted nowhere"). That comment is updated alongside this
seam's wiring to point here instead of asserting the hole is still open.

**Alternative considered:** name this seam `commands_remainder` (matching the
brief's own working name for the decision) rather than `potion_pipeline`.
Rejected — the seam's actual claim (procurement/use/discard pipeline for one
model kind) has nothing to do with "leftover command files" once `Cmd.cs`
through `ThinkCmd.cs` are correctly filed as out-of-scope; a name describing
what it audits is more useful to a Phase-2 auditor than a name describing how
it was decided.

## Scope

**Claims:** the potion belt procurement/discard pipeline
(`PotionCmd.TryToProcure`/`Discard`, the `Hook.ShouldProcurePotion`/
`AfterPotionProcured`/`AfterPotionDiscarded` call sites around them) and
`PotionModel`'s shared use-path wrapper (`OnUseWrapper`) — the target
validation, consumption timing, and hook dispatch every potion's own `OnUse`
runs inside, once, for all 51 potions.

**Does NOT claim:**
- Any individual potion's own `OnUse` behavior — that is each potion's own
  content record's job (the `potion` kind, unaffected by this seam). This
  seam's record cites 4 of the 51 records by name (`fire_potion`,
  `foul_potion`, `entropic_brew`'s sibling `alchemize`, `mazaleths_gift`) as
  matched evidence, never to re-verdict their own `OnUse`.
- Potion POOL composition (which potions exist, at what rarity, and the
  Ironclad-pool-vs-genuinely-cross-character split) — `relic_pools`'s job
  (`potion_pools.py`, `PotionFactory.cs`, `PotionPools/*.cs`). This seam's
  guards G7/G8 record the two *failure modes* a pool gap produces (a
  pool-member placeholder raises on use; a non-member id is silently dropped
  at belt resync) as PotionModel/PotionCmd-shaped facts, not the pool
  membership itself.
- Potion GENERATION stream *identity* (which named `RunRngSet` stream a
  generator draws off, and whether that stream is a silent fallback to the
  shared legacy RNG) — `rng_streams`'s job. This seam's guard G5 records only
  the draw COUNT and ORDER (one `NextFloat` + one `NextItem` per potion) as a
  PotionFactory-shaped fact, citing `rng_streams`-adjacent content records
  (`card/alchemize`, `relic/delicate_frond`) as the stream-identity owners.
- Reward-screen/shop plumbing around a potion offer (`RewardsCmd.OfferCustom`,
  `MerchantPotionEntry` pricing) — `rewards`'s job. This seam's guard G6 cites
  `event/potion_courier.json` (already faithful) as the worked example of a
  potion generation path that is NOT this seam's (`PotionCourier` is an
  `EventModel`, and the draw is off `PlayerRng.Rewards`, not
  `CombatPotionGeneration`).
- The bare belt-slot list itself as *player state* (`Player.PotionSlots`
  serialization, save/load) — `creature_card_cmds`'s job, to the extent it is
  claimed anywhere; this seam's guard G4 claims only the SLOT-ASSIGNMENT
  behavior (first-open-slot default, explicit-slot form, no compaction, the
  `TooFull` failure mode), which is `PotionCmd`/`PotionModel`'s own
  contract, not player-state plumbing.
- The `Hook.*` dispatch mechanism itself (listener ordering, registry) —
  `hook_dispatch`'s job; this seam claims that `PotionCmd`/`PotionModel` CALL
  into specific hooks at specific points, not how those hooks resolve their
  listeners.

**Subsumes, per audit rule 3 (one verdict per mechanism):** the shared
`W`/`W4` guard every one of the 51 `potion/*` records carries, pointing at
`audit/content/potion/shared-mechanisms.md`. That doc's own W1–W10 table is
now this seam's `steps` 1–2, 4, 6–11 (renumbered; `W5`/`OnUse` stays each
potion's own). The 51 records' own `W`/`W4` text is CURRENT (all `faithful`,
independently re-derived through 2026-07-29) and is matched here rather than
superseded — this seam does not overrule them, it gives the mechanism an
engine-level home so a future re-audit has one record to update instead of
51. `audit/content/potion/shared-mechanisms.md` itself is the one artifact
that is now stale (see the STATUS banner above) and is out of this seam's
authority to edit (per this task's brief); the controller should consider
retiring it in favor of this record once the 51 citations are repointed.
This seam does **not** subsume any potion's OWN `OnUse`-body guard (the
majority of each record's `guards` list), only the shared-wrapper entry.

## Game sources claimed, with justification

- `src/Core/Commands/PotionCmd.cs` — `TryToProcure`/`Discard`.
- `src/Core/Models/PotionModel.cs` — `OnUseWrapper` (the shared wrapper) plus
  `CanBeGeneratedInCombat`/`PassesCustomUsabilityCheck`/`ShouldReceiveCombatHooks`
  (the base-level virtuals every potion either uses as-is or overrides).

## Sim sources claimed, with justification

- `sts2_rl/potions.py` — every ported potion's `OnUse` body (already cited by
  `hook_dispatch` for unrelated gap evidence — cross-seam sim citation is
  normal in this pipeline; `hooks.py`/`combat.py`/`player.py` are each already
  cited by 2+ seams).
- `sts2_rl/player.py` — the belt itself (`add_potion`/`discard_potion`), the
  direct counterpart of `PotionCmd.TryToProcure`/`Discard`.
- `sts2_rl/combat.py` — `use_potion`, the in-combat consumption path
  (`OnUseWrapper`'s sim-side entry point).
- `sts2_rl/run.py` — `add_potion` at the run level (the non-combat grant path,
  e.g. from a reward).

## What the pre-audit brief asked, and how it resolved

1. ~~This is the smallest of the six new seams by file count... treat it as
   high-value despite the small footprint.~~ Confirmed: the OnUseWrapper hole
   was real, but by audit time three of its four dispatches (`W2`/`W4`/`W10`)
   had already been fixed by an unrelated round and matched by all 51 potion
   records — only the narration doc and this seam's own scaffold were still
   describing the pre-fix shape. One genuinely new LIVE finding came out of
   the base-virtuals half instead: `PotionModel.PassesCustomUsabilityCheck`
   has no sim concept at all, and `potion/foul_potion.json`'s existing gap for
   it is mis-tagged dormant against evidence a sibling entry in the SAME
   record already overturned (see step 13, `conformance/runner.py:846`).
2. `PotionCmd.TryToProcure`'s gate-before/event-after-on-success shape: YES,
   preserved, for the four ported COMBAT-side procure callers (Alchemize,
   Delicate Frond, Petrified Toad, Entropic Brew) via `potions.try_to_procure`
   — see guard G1. The RUN-level (out-of-combat) path, `RunState.add_potion`,
   preserves the gate but never fires the AFTER event at all — see guard G2
   (filed `gap`, `dormant`: the one implementer of that event is itself
   `CombatManager.IsInProgress`-gated, so it wouldn't have fired anyway).
3. `OnUseWrapper` read in full — 14 steps recorded, in source order.
4. `PotionModel` stays in `MODEL_ROOT_CLASSES` (no seam covers a base class,
   this seam covers three of its virtuals plus `OnUseWrapper`); the 51 potion
   records' `shared-mechanisms.md` citations should be repointed at this
   seam's record — see "Subsumes" above. Not done here: the brief for this
   task forbids editing the 51 records or the narration doc; the controller
   reconciles.
