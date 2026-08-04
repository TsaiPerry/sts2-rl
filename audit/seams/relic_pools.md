# Engine seam: `relic_pools`

**STATUS: AUDITED 2026-08-03 (Phase 2).** `audit/records/seam/relic_pools.json`
carries 15 steps + 5 guards, every hashed source re-read, rollup verdict
`gap` (2 LIVE, 3 dormant). `harness.py validate` and `citation_check.py
--strict` both report 0 problems for this record.

## Scope

**Claims:** pool composition (which relics/cards/potions exist in which named
pool, and their rarity), the rarity ladder / escalation and refill behavior
when a bag/deque of the requested rarity is empty, the three factories that
turn a pool entry into a live instance, and the two `Commands/*.cs` files
whose subject is a relic reaching or leaving a player (as opposed to a pool
being built or drawn from).

**Does NOT claim:**
- Reward GENERATION (deciding a reward should include a relic/card/potion at
  all, and offering it to the player) — that is `rewards`'s job. This seam
  claims what happens once something asks a pool "give me a Rare relic",
  including the escalation logic, not the decision to ask. `CardFactory`'s
  card-RARITY odds/pity (`RollForRarity`, `PlayerOdds.CardRarity`) are
  `rewards`'s subject too; this seam only owns `CardFactory`'s
  pool-composition legs (`FilterForCombat`, `GetDefaultTransformationOptions`).
- The RNG draws a pool consumption spends, or their stream identity — that is
  `rng_streams`'s job.
- `GrabBag.cs` (`src/Core/Helpers/GrabBag.cs`), the generic weighted-pop
  primitive. Re-confirmed this audit round, not just inherited: read
  `RelicGrabBag.cs` in full again — `GetAvailableDeque`/`RefreshRarity`/both
  `Populate` overloads use `List<T>.UnstableShuffle` + linear front/back pull,
  never `GrabBag<T>`. `GrabBag.cs`'s real caller is `ActModel`'s tag-safe
  encounter/event picking (`AddWithoutRepeatingTags`), claimed by
  `rooms_and_map` instead.
- `sts2_rl/combat_card_db.py` — checked and excluded. It is
  `NetCombatCardDb`'s per-combat card-ID assigner (multiplayer net identity
  for replay/sync), not pool composition. A different subject with a
  superficially similar name.
- The single-player DECISION inside a "choose one of N relics" screen
  (`RelicSelectCmd.FromChooseARelicScreen`'s real payload) — that belongs to
  whichever event/room record consumes the choice. This seam claims only the
  multiplayer-choice-synchronization wrapper around it (waived).
- Shop stock GENERATION as a room/pricing mechanism (`MerchantInventory`,
  `MerchantCardEntry`/`MerchantColorlessCardEntry`/`MerchantPotionEntry`/
  `MerchantCardRemovalEntry`, `sts2_rl/shop.py`) — that is `rooms_and_map`'s
  file. This seam claims the PULL/GENERATION PRIMITIVES shop.py calls
  (`RelicFactory.PullNextRelicFromBack` ≈ `run.pull_relic_from_back`,
  `PotionFactory.CreateRandomPotionsOutOfCombat` ≈
  `potion_pools.generate_random_potions`, `CardFactory.CreateForMerchant`'s
  pool-membership half), not the entry/pricing/restock orchestration around
  them. One of this round's two LIVE findings sits exactly on that boundary:
  the shop's Shop-rarity relic slot (`shop.py`) calls a pull primitive
  (`run.pull_relic_from_back`) that misroutes to a bag this seam's own
  population step (`run.py`) never actually feeds — see below.
- `EncounterModel`'s monster-slot generation and per-encounter content —
  `encounter` kind's subject, untouched here.
- Ascension-scaled odds — out of scope for the whole campaign; confirmed
  `RelicFactory.RollRarity` and `PotionFactory`'s rarity thresholds are FIXED
  constants with no `AscensionHelper.GetValueIfAscension` dependency at all
  (unlike `CardFactory`'s upgrade-odds scaling, which IS ascension-aware and
  is `rewards`'s to verdict).

## Pool inventory (all re-derived this round, not inherited)

| Pool | Game file(s) | Sim roster | Result |
|---|---|---|---|
| Relic (Shared+Ironclad) | `SharedRelicPool.cs` (118), `IroncladRelicPool.cs` (8) | `relic_pools.py` `SHARED_RELIC_POOL`/`IRONCLAD_RELIC_POOL` | 0 discrepancies: order, membership, rarity all match |
| Relic (other 7 pool files) | Defect/Necrobinder/Regent/Silent character pools, `DeprecatedRelicPool`, `EventRelicPool`, `FallbackRelicPool` | none (Ironclad-only sim) | census-confirmed out of scope; `FallbackRelicPool` additionally confirmed DEAD CODE game-wide (3 refs, all model-registry bookkeeping, never a pull source — `RelicFactory.FallbackRelic` is the real mechanism) |
| Card (Ironclad/Colorless/Curse) | `IroncladCardPool.cs` (87), `ColorlessCardPool.cs` (64), `CurseCardPool.cs` (18), each minus their own `MultiplayerConstraint.MultiplayerOnly` cards | `cards/pool.py` `IRONCLAD_POOL`/`COLORLESS_POOL`/`CURSE_POOL` | 0 discrepancies; both multiplayer-exclusion lists exact and complete against a game-wide 21-card census |
| Card (Status, for in-combat transform) | `StatusCardPool.cs` (12, non-alphabetical declared order) | `cards/pool.py`'s `transform_options_in_combat` STATUS branch (`sorted(_CARD_CLASSES.items())`) | **GAP, LIVE** — alphabetizes instead of reading declared order; reachable via the ported Entropy card/power transforming a Status card in hand |
| Card (other pools) | `Defect/Deprecated/Event/Mock/Necrobinder/Quest/Regent/Silent/Token CardPool.cs` | not separately rostered | out of scope, per-character/per-mechanism as expected |
| Potion (Shared+Ironclad) | `SharedPotionPool.cs` (45), `IroncladPotionPool.cs` (3, via `Ironclad4Epoch`) | `potion_pools.py` `_SHARED_RAW_POOL`/`_IRONCLAD_RAW_POOL` | 0 discrepancies: order, membership, rarity, and all 3 `CanBeGeneratedInCombat=false` overrides all match |
| Potion (other 8 pool files) | Defect/Necrobinder/Regent/Silent character pools; Deprecated/Event/Mock/Token | none | census-confirmed out of scope (different character or a rarity value the reward/shop roll never draws) |

## Known findings this seam claims (do not silently drop)

Two findings pre-date this round and are RE-DERIVED (not inherited) against
today's `RelicGrabBag.cs`, both filed as `relic/circlet/g4`:

1. **The escalation ladder** (`GetAvailableDeque`, `RelicGrabBag.cs:218-243`):
   CONFIRMED faithful, no change from `relic/circlet/g4`'s reading.
2. **The `_refreshAllowed` refill branch** (`RelicGrabBag.cs:222-226`):
   `relic/circlet/g4` frames this as "applies to the shop's own RelicGrabBag
   instance" and dormant pending an exhausted rarity. **That framing is
   wrong, and this record corrects it rather than inheriting it (a
   cross-record disagreement, reported to the controller, `relic/circlet.json`
   left untouched):** there is no per-shop `RelicGrabBag` instance anywhere in
   the game. The only `refreshAllowed:true` object is the RUN-LEVEL
   `RunState.SharedRelicGrabBag`, and it is never the subject of
   `GetAvailableDeque`/`PullFromFront`/`PullFromBack`/`HasAvailableRelics`
   anywhere in the decompiled tree — every `player.RelicGrabBag` (the only
   bag ever actually pulled from) is permanently `refreshAllowed:false` by
   construction. The branch is dead in EVERY mode, not merely dormant.
   Executable witness: `py audit/tools/relic_pool_probes.py
   refresh-allowed-dead`.

Two NEW findings this round, both LIVE and both executed
(`py audit/tools/relic_pool_probes.py back-pull-ladder` /
`shop-rarity-misroute`):

3. **`pull_relic_from_back` has neither the escalation ladder nor the Circlet
   fallback** that `pull_relic_from_front` has and that C#'s
   `PullNextRelicFromBack` shares with `PullNextRelicFromFront` (same
   `GetAvailableDeque`, same `?? FallbackRelic`). An exhausted rarity leaves a
   shop slot visibly empty where the game always shows a purchasable relic.
4. **The shop's Shop-rarity relic slot draws from a disconnected legacy bag.**
   `run.pull_relic_from_back(SHOP, ...)` routes to `run._get_shop_relic_bag()`
   — independently built from `ALL_RELICS` and shuffled on the legacy shared
   RNG — instead of the properly UpFront-populated Shop deque already sitting
   in `run.player_relic_bag['Shop']`/`run.relic_grab_bag`. Confirmed by
   execution: the parity-populated bag is untouched (same length) before and
   after the pull, and the relic the shop hands out is left duplicated,
   unconsumed, inside it.

Plus the Status-card transform-order finding from the pool inventory table
above (STATUS row).

## Game sources claimed, with justification

Unchanged from the wiring pass — see `audit/records/seam/relic_pools.json`'s
`game_sources` for the pinned list (`RelicGrabBag.cs`, `RelicFactory.cs`,
`CardFactory.cs`, `PotionFactory.cs`, `RelicCmd.cs`, `RelicSelectCmd.cs`, all
32 `RelicPools`/`CardPools`/`PotionPools` files). This round's `extra_sources`
adds the files the new findings rest on: `Player.cs`, `RunState.cs`,
`NullRunState.cs` (the `_refreshAllowed` census), `MerchantRelicEntry.cs`,
`MerchantEntry.cs` (the shop-misroute finding), `RelicModel.cs`,
`ToxicEgg.cs`/`MoltenEgg.cs`/`FrozenEgg.cs`, `SwordOfStone.cs`/
`TouchOfOrobas.cs`/`RanwidTheElder.cs`/`RelicTrader.cs` (the `RelicCmd.Remove/
Replace/Melt` census), and the three potions with `CanBeGeneratedInCombat`
overrides plus `RunManager.cs` (a pinned line citation each).

## Sim sources claimed, with justification

Unchanged singular pin — `sts2_rl/relic_pools.py`, `sts2_rl/potion_pools.py`,
`sts2_rl/cards/pool.py`. **Flagged for the next auditor:** a large fraction of
this seam's ACTUAL mechanism — `RelicFactory`'s and `RelicCmd`'s ported
behavior — lives in `sts2_rl/run.py` (`pull_relic_from_front`/`_back`,
`roll_relic_rarity`, `has_available_relics`, `add_relic`,
`_get_shop_relic_bag`), not in the three pinned pool-data files, and
`sts2_rl/shop.py` is where the pool primitives get consumed. Both are added to
this round's `extra_sources` (hashed, cited by member name rather than line
number per the citation rules, since both files change often) rather than
promoted to the singular `sim_sources` list, since re-pinning that list was
outside this batch's authorized edits (only `relic_pools.json`,
`relic_pools.md` and a probe file). **A future re-pinning pass should
seriously consider adding `run.py` and `shop.py` to `sim_sources` directly** —
most of this round's findings are `run.py` bugs, not `relic_pools.py` ones.

## What the Phase-2 auditor needs to know (updated)

1. `RelicGrabBag`'s two construction sites are NOT "shared bag vs shop bag" —
   see the corrected `_refreshAllowed` finding above. There is no shop-specific
   `RelicGrabBag`; shops draw from the SAME per-player bag as reward/chest
   pulls (via `PullFromBack` instead of `PullFromFront`), except that the
   sim's shop path has been rerouted onto a disconnected substitute (finding
   4 above).
2. `HasAvailableRelics` (`RelicGrabBag.cs:47-58`) is faithful in the PARITY
   path only; the LEGACY (no `string_seed`) path's `run.py` `_BAG_RARITIES`
   constant omits Shop from the merged bag it scans, which under-reports
   availability to `luminous_choir`/`shovel` in an extreme-length legacy run.
   Recorded dormant (no executed witness), not claimed live.
3. `RelicSelectCmd.ShouldSelectLocalRelic`'s multiplayer/replay branch
   (`RelicSelectCmd.cs:18-25`) is presentation/multiplayer plumbing around a
   real single-player choice — waived, not the whole method.
4. `RelicCmd.Remove`/`Replace`/`Melt` have no shared sim command, but this is
   `deliberate-divergence`, not a gap: `AfterRemoved()` has ZERO overrides
   anywhere in the decompiled game (faithful-by-vacuity), and `Replace`'s two
   real callers (`SwordOfStone`, `TouchOfOrobas`) are BOTH ported with
   correct index-preserving swaps. Checked, not assumed.
5. The card-pool and potion-pool literal-composition sweeps came back clean
   except for one gap each: cards' `StatusCardPool` transform ordering (LIVE,
   via Entropy) and — at the seam-mechanics level, not a pool-composition
   issue — the two `RelicGrabBag`-consumption bugs above.
