# Engine seam: `rewards`

**STATUS: AUDITED 2026-08-03.** `audit/records/seam/rewards.json` carries 18
steps and 7 guards, `harness.py validate` clean (0 invalid) and
`citation_check.py` clean (0 MISSING, 0 OUT-OF-RANGE, 0 UNHASHED-with-a-line).
Rollup verdict is `gap` — one live-candidate finding (step 16, filed `live:
false` matching an existing cross-record verdict, with a flagged staleness
concern — see below), everything else `faithful`/`waiver`/
`deliberate-divergence`.

## Scope

**Claims:** the reward-generation pipeline end to end — what a `Reward`
object is (six subtypes: Card/Gold/Potion/Relic/SpecialCard/CardRemoval), how
a `RewardsSet` populates itself for a room or a custom source
(`RewardsSet.WithRewardsFromRoom`/`WithCustomRewards`/`GenerateWithoutOffering`/
`Offer`), the choke point where hooks can add/remove/modify the generated set
(`Hook.ModifyRewards`, straddled by RewardsSet's two populate loops), and the
card-creation-request layer that decides pool/rarity/flags for any reward that
generates cards (`CardCreationOptions`/`CardCreationFlags`/
`CardCreationSource`/`CardRarityOddsType` — see the file-list note below for
why these four are here and not in `run_layer`).

**Does NOT claim:**
- The relic/card/potion POOLS a reward draws from (composition, rarity
  ladder, escalation/refill behavior) — that is `relic_pools`'s job. This seam
  claims the request (`CardCreationOptions.GetPossibleCards`, `RelicReward`,
  `PotionReward` asking a pool for a candidate) and the offer/accept flow, not
  the pool itself.
- Which RNG stream a reward draw actually spends, or in what count — that is
  `rng_streams`'s job (the stream *map*); this seam's job is *that* a reward
  draw happens and in what order relative to other reward-generation steps.
- `RunManager.cs`'s or `RoomSet.cs`'s decision of WHEN a room offers a reward
  (room-transition orchestration) — that is `run_layer`'s / `rooms_and_map`'s
  respectively; this seam starts at `RewardsCmd.OfferForRoomEnd` being called.

## Known finding this seam must claim (do not silently drop)

`RewardsSet.GenerateWithoutOffering`'s two populate loops, straddling
`Hook.ModifyRewards`, were the root cause of a LIVE gap closed 2026-08-03
(`event/crystal_sphere/g3`) — nothing currently owns the choke point itself,
only the one content record that hit it by accident. **CLAIMED, steps 3-9 of
the record.** Re-derived from `RewardsSet.cs` directly (not inherited from the
event record): the snapshot (`second = Rewards.ToList()`), the first populate
loop, the two-pass `Hook.ModifyRewards` dispatch, the second populate loop
restricted to `Rewards.Except(second)`, `Hook.AfterModifyingRewards`, and the
final display-order sort are each their own step with an independent verdict.
The sim's `apply_reward_modifiers` (`sts2_rl/rewards.py`) reproduces the shape
correctly; `event/crystal_sphere.json`'s `g3` finding (the relic pull hoisted
behind every card group's populate, since fixed) is cited as a live witness
in step 7's rationale rather than re-derived.

## What this audit found, beyond the known finding

- **A live-candidate mechanism already on file elsewhere, with a flagged
  staleness concern (step 16).** `CardReward.OnRelicObtained` (a relic
  obtained from the SAME reward screen retroactively re-modifies a
  still-pending card reward's options) has no sim counterpart at all. This was
  already found and verdicted DORMANT by `relic/silver_crucible`'s
  `AfterModifyingCardRewardOptions` entry (round 6, 2026-07-26) on the premise
  "the sim grants relics between rooms, never with a reward screen open."
  Matched here per rule 3 (`live: false`), but flagged: `generate_combat_rewards`'s
  own Elite branch resolves that SAME elite's relic (`run.offer_relic`) AFTER
  that SAME elite's cards are already drawn, inside the SAME function call —
  which reads narrower than "between rooms" for this one case. Confirming it
  live needs a specific Common/Uncommon relic reachable via an Elite's own bag
  pull that also modifies already-drawn card options — `relic_pools`'/
  content-tier's determination, not re-derived here. See "Cross-record
  disagreements" in the batch report.
- **Two pieces of dead reward infrastructure**, both fully wired for
  presentation/dispatch but never constructed by any C# content:
  `LinkedRewardSet` (zero `new LinkedRewardSet(` sites anywhere in
  `src/Core`) and `Hook.AfterRewardTaken` (zero overriding implementers
  anywhere in `src/`). Both waived as unreachable, not modeled as gaps.
- **`CardCreationFlags.ForceRarityOddsChange`/`NoRarityModification`'s only
  readers are Custom/Daily-mode `Modifier`s** (`SealedDeck.cs`,
  `BigGameHunter.cs`) — out of the Ironclad-only sim's scope, so the sim's
  absence of a reader is correctly unreachable rather than missing.
- **`RewardsSet` on a `TreasureRoom` yields an empty base reward list, and
  `Hook.ModifyRewards` still dispatches over it** (`GenerateRewardsFor`'s
  switch has no `TreasureRoom` case) — already correctly reproduced in
  `sts2_rl/run.py`'s own `RoomType.TREASURE` branch, which builds an empty
  `CombatRewards` and calls `apply_reward_modifiers` on it directly, citing
  the exact C# line numbers in its own comment. Verified faithful.
- **`Hook.ModifyCardRewardCreationOptions` is dispatched once PER CARD in C#**
  (inside the private per-card `CardFactory.CreateForReward`) but only ONCE
  total in the sim's `create_reward_cards` (before its per-card loop). Verified
  safe today because the only two Ironclad-reachable implementers (`DingyRug`,
  `PrismaticGem`) are stateless pure functions of the input options — but
  flagged as fragile against a future stateful implementer.

## Game sources claimed, with justification

- `src/Core/Rewards/CardRemovalReward.cs`, `CardReward.cs`, `GoldReward.cs`,
  `PotionReward.cs`, `RelicReward.cs`, `SpecialCardReward.cs` — the six reward
  subtypes.
- `src/Core/Rewards/Reward.cs` — the shared base every subtype above overrides.
- `src/Core/Rewards/LinkedRewardSet.cs` — groups multiple `Reward`s that must
  be claimed together (e.g. a card removal that also grants gold).
- `src/Core/Rewards/RewardType.cs`, `RewardTypeExtensions.cs` — the reward-kind
  enum and its extension helpers.
- `src/Core/Rewards/RewardsSet.cs` — the per-room/per-source generator; this
  file's `GenerateWithoutOffering` is the seam's central claim (see the known
  finding above).
- `src/Core/Commands/RewardsCmd.cs` — the only `Commands/*.cs` file whose
  subject is rewards. All four methods (`OfferForRoomEnd`/`OfferCustom`/
  `GenerateForRoomEnd`/`GenerateCustom`) are thin wrappers that build a
  `RewardsSet` and call one of its own methods — no logic of its own, but the
  entry point every room-end/event/relic reward path calls through.
- `src/Core/Runs/CardCreationFlags.cs`, `CardCreationOptions.cs`,
  `CardCreationSource.cs`, `CardRarityOddsType.cs` — **reassigned here from
  `run_layer`, overruling the P1-T2 brief's own controller-analysis.** These
  four files live under `src/Core/Runs/` in the game tree, which is why the
  brief filed them under `run_layer`, but their whole subject is "what cards
  can a reward generate, at what rarity, under what restrictions" — and the
  sim proves it: all four are ported *inside* `rewards.py`
  (`RarityOddsType`, `CardCreationSource`, `CardCreationFlags`,
  `CardCreationOptions` classes, `rewards.py:76-191`), not in `run.py`. Filing
  them under `run_layer` would split one audited concept across two records
  for no reason but which C# folder it happened to ship in.

## Sim sources claimed, with justification

- `sts2_rl/rewards.py` — the entire counterpart: the four reassigned
  `CardCreation*`/`CardRarityOddsType` ports, plus the reward-generation
  pipeline itself (`roll_gold_reward`, `create_reward_cards`,
  `CardRewardGroup`, `CombatRewards`, `apply_reward_modifiers`,
  `generate_combat_rewards`, `RewardExtra`/`RewardExtraKind`). Nothing else in
  the sim generates a reward.

## Scope boundary against the neighbouring seams (as audited)

- **`relic_pools`** owns pool COMPOSITION, rarity ladder membership, refill/
  escalation behavior, and the grab-bag mechanics `RelicFactory.PullFromFront`/
  `CardFactory`'s pool-widening hooks read from. This seam owns the REQUEST
  side only: that a rarity roll happens, that a bag pull consumes no further
  draw, that `CardCreationOptions.GetPossibleCards` reads the full unlocked
  pool rather than the combat-filtered one (guard G5) — never the pool's own
  contents or ordering. `relic/circlet/g4`'s escalation-ladder finding is
  `relic_pools`' to own, not re-derived here.
- **`rng_streams`** owns stream IDENTITY — which named stream a draw lands on,
  how a stream is seeded, the primitive draw semantics (`NextFloat`/
  `NextInt`/`NextItem`). This seam's every step and guard verdicts DRAW COUNT
  and ORDER only; where a rationale names a stream (`PlayerRng.Rewards`,
  `TreasureRoomRelics`) it is citing `rng_streams`' territory for context, not
  claiming it. The one place the two seams' subjects visibly diverge —
  Elite/Boss relic rarity rolls on `Rewards`, a Treasure chest's relic rarity
  roll on the separate `TreasureRoomRelics` stream — is noted in step 10's
  rationale as a stream-identity fact and left to `rng_streams` to verdict.
- **`run_layer`** and this seam are "joined at the hip" on the
  `CardCreationFlags`/`Options`/`Source`/`CardRarityOddsType` reassignment
  (see the game-sources justification above) — do not move those four files
  back to `run_layer` on a future re-read; the reasoning is unchanged by this
  audit. `run_layer` (not this seam) owns `RunManager.InitializeNewRun` and
  everything about HOW/WHEN a room transition happens; this seam starts at
  `RewardsCmd` being called.
- **`rooms_and_map`** owns room-transition orchestration (which room comes
  next, act structure) and `EncounterModel.ShouldGiveRewards`'s *value* per
  encounter kind; this seam owns `RewardsCmd.OfferForRoomEnd`'s *branch* on
  that value (the `EmptyForRoom` vs `WithRewardsFromRoom` fork itself, audited
  and faithful — `sts2_rl/driver.py:522` and `conformance/runner.py:263` both
  gate on `encounter.should_give_rewards` at the matching site).
- **A hole neither this seam nor any other currently claims:** a Treasure
  chest's actual gold+relic grant runs through `OneOffSynchronizer.cs`/
  `TreasureRoomRelicSynchronizer.cs` (`src/Core/Multiplayer/Game/`), a
  completely separate code path from `RewardsSet`/`RewardsCmd` that this
  seam's pinned sources do not cover and that `rooms_and_map`'s file list
  (Rooms/Map/Acts/Merchant) does not cover either. This seam verified that
  `RewardsSet`'s OWN behavior on a TreasureRoom (an empty base list,
  `Hook.ModifyRewards` still dispatched over it) is faithfully reproduced —
  see the finding above — but the chest's own gold/relic mechanism itself,
  and whether `sts2_rl/run.py`'s `RoomType.TREASURE` branch faithfully mirrors
  `OneOffSynchronizer.DoTreasureRoomRewards`/`TreasureRoomRelicSynchronizer`
  line for line, is unclaimed by any of the 12 current seam records. Flagged
  for the controller; not claimed here because `OneOffSynchronizer.cs` was
  never in this seam's assigned `SEAM_SOURCES["rewards"]` list and reading it
  in full was out of this batch's mandate.
