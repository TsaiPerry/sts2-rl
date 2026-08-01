# R10 — consolidate the reward-modifier dispatch onto one choke point

Read first: `.superpowers/sdd/round13/PROTOCOL.md` (binding).

## The divergence

C# calls `Hook.ModifyRewards` from `RewardsSet.GenerateWithoutOffering`
(`RewardsSet.cs:125-147`, dispatch at `:136`), guarded idempotent by
`_isGenerated` (`:127-130`, set `:146`). `Offer()` also calls
`GenerateWithoutOffering` at `:159`, so every screen passes through the
choke point exactly once no matter how it was built. The sim instead calls
`apply_reward_modifiers(run, rewards)` (`sts2_rl/rewards.py:646-670`)
manually at each construction site. Round 12 (T32) fixed two missing sites
per-site and recorded: "the next event ported this way reintroduces the
same bug." Your job is to remove that trap.

## The map (scouted 2026-08-01 — verify, then build)

Real construction sites that dispatch today:
1. `rewards.py:698` (final-act-boss early return in `generate_combat_rewards`)
2. `rewards.py:761` (normal path)
3. `run.py:1419` (`rest_heal_rewards`)
4. `relics/glass_eye.py:78`
5. `events/brain_leech.py:89`
6. `events/trial.py:118`
(7. `events/dense_vegetation.py:75` rides on #3.)

Wrapper constructions that must NOT dispatch (display-only re-wraps):
`driver.py:374`, `driver.py:467-471`, `driver.py:493-495`, `driver.py:517`,
`rewards.py:597-598`.

Consumers: every caller of `driver._offer_rewards` (`driver.py:448`, `:543`,
`:655`; `conformance/runner.py:242`; `run.py:537` via `rewards_offerer`)
receives a set whose modifiers ALREADY fired. A naive central call at the
top of `_offer_rewards` double-fires 100% of the time. Concretely
duplicated because the hooks mutate run state:
- `relics/amethyst_aubergine.py:31-32` (+15 gold twice = +30)
- `relics/black_star.py:21-25` (second relic pull per elite)
- `relics/prayer_wheel.py:31`, `relics/white_star.py:34` (extra card group
  + extra Rewards-stream draws)
(`lava_rock.py`/`wongos_mystery_ticket.py` self-guard; `driftwood.py`/
`paels_wing.py` are idempotent.)

## The fix — two candidate shapes; derive the choice from the C#

(a) **C#-faithful idempotency**: give `CombatRewards`
(`rewards.py:547-587`) a `generated` flag mirroring
`RewardsSet._isGenerated`; make `apply_reward_modifiers` return early when
set; add the offer-time backstop dispatch in `driver._offer_rewards`
(`driver.py:452`) and `run.offer_rewards` (`run.py:523-543` — note its
selectorless fallback loop at `:539-543` needs covering too). Every
existing construction-site call becomes a harmless first-fire, exactly like
C#'s construction-time `GenerateWithoutOffering` + `Offer()`'s repeat call.
Construction-time RNG order is preserved.

(b) **True consolidation**: dispatch only at offer time and DELETE the six
construction-site calls. Hazard: `rewards.py:761` currently runs BEFORE the
`pending_reward_extras` loop (`rewards.py:773-792`) and before the elite
`offer_relic` (`:740`/`:758`); moving the dispatch changes gold/relic grant
ordering and Rewards-stream draw order, which parity tests pin.

Shape (a) is the scout's recommendation as materially safer AND closer to
the C# call structure — but do not defer to this brief: re-derive from
`RewardsSet.cs` which shape reproduces C#'s observable order, and say so in
your report. Whatever you choose, prove idempotency with a RED-first test
(a hook that mutates state fires exactly once per screen), and prove each
of the 6 sites still dispatches exactly once end-to-end.

## Second item — the treasure-room hole (investigate; propose, don't record)

`run.py:1297-1319` grants chest gold + relic with NO `CombatRewards` and no
dispatch. In C#, `RewardsCmd.OfferForRoomEnd` for a TreasureRoom still
builds a `RewardsSet` with `Room` set (`RewardsSet.cs:206-219` returns an
empty reward list for TreasureRoom but does not throw) and
`GenerateWithoutOffering` still fires `Hook.ModifyRewards` at `:136`. So a
C# `TryModifyRewards` implementer can see treasure rooms; a sim one cannot.
Verify this reading of the C#; enumerate which PORTED listeners could
observe the difference (check every `modify_combat_rewards`/`_late`
implementer for room-sensitivity); then either fix it inside your footprint
(if the fix is contained) or write the complete gap analysis in your report
for the controller to record. Do NOT edit `audit/**`.

## Footprint (yours alone this wave)

`sts2_rl/rewards.py`, `sts2_rl/run.py`, `sts2_rl/driver.py`,
`sts2_rl/relics/glass_eye.py`, `sts2_rl/events/brain_leech.py`,
`sts2_rl/events/trial.py`, `sts2_rl/conformance/runner.py`, plus tests.
NOT yours (BLOCKED-ON-FOOTPRINT instead): `events/base.py`,
`events/the_future_of_potions.py`, `hooks.py`, `combat.py`, `player.py`,
`cmds.py`, `powers.py`, any other relic file, `audit/records/**`,
`audit/GAP-QUEUE.md`.

## Watch items

- `test/test_rng_tripwire.py:15` pins `driver.py` line numbers; adding
  lines above `driver.py:306` trips it — update it if you do.
- Do not change WHAT the modifiers do — only WHERE the dispatch lives.
  Rewards-stream RNG draw order is pinned by parity tests; run
  `test/test_rewards*.py`, `test/test_relic_tier1_gaps.py`,
  `test/test_rng_tripwire.py`, `test/test_event_offer_screens.py` and any
  test file you touch.
- Round 12 note: `run.reward_offer_selector` wiring and the
  `the_future_of_potions/g15` reroll surface are SEPARATE tasks in later
  waves — do not fix them here even though you will see them.

Report path: `.superpowers/sdd/round13/R10-report.md`.
