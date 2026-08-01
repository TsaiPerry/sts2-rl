# R6 — wire `run.reward_offer_selector` (take-or-skip screens auto-accept in real play)

Read first: `.superpowers/sdd/round13/PROTOCOL.md` (binding). Maps scouted
2026-08-01; R10 (reward-dispatch consolidation, wave 1) has landed in
`rewards.py`/`run.py`/`driver.py` — re-verify line numbers and read R10's
report (`.superpowers/sdd/round13/R10-report.md`) before building.

## The gap — probably the largest known live divergence in the sim

`reward_offer_selector` is defined NOWHERE: it is a duck-typed
`getattr(run, "reward_offer_selector", None)` with exactly ONE reader —
`Event._accept_offer` (`events/base.py:204-222`, getattr at `:219`) — and
ONE writer, a test helper (`test/test_event_offer_screens.py:37`).
`RunState.__init__` (`run.py:133, :196-198`) declares `card_selector` but
not this. `driver.py:296-302` wires four seams (`card_selector`,
`option_selector`, `reward_selector`, `rewards_offerer`) — never this one.
Result: with no selector, `_accept_offer` returns True → every
take-or-skip EVENT screen auto-accepts in real play (and in the
conformance `_ForceWinDriver`, `conformance/runner.py:187`).

Auto-accepting consumers:
- `Event.offer_potion` (`events/base.py:224-229`) — callers:
  `events/drowning_beacon.py:30`, `events/endless_conveyor.py:130`,
  `events/potion_courier.py:49,62,79`,
  `events/the_legends_were_true.py:49`, `events/wellspring.py:32`,
  `events/whispering_hollow.py:68`. Note it bypasses
  `RunState.offer_potion` and calls `run.add_potion` directly.
- `Event.offer_card_reward` (`events/base.py:231-240`) — sole caller
  `events/the_future_of_potions.py:95`. (Its reroll surface is R2, a
  LATER task — do not build it; but your selector decision gates it.)

The asymmetry that shows the fix shape: `RunState.offer_relic`
(`run.py:545-566`, selector read `:563`) and `RunState.offer_potion`
(`run.py:568-576`, read `:573`) already route through `run.reward_selector`,
which IS wired (`driver.py:298` → `_reward_selector`, `driver.py:360-378`,
raising REWARD_RELIC/REWARD_POTION decisions). Identical offers from
relics are surfaced; the same offers from events are not. Two names for
one concept.

## C# reference

`RewardsSet.cs` — `Offer()` `:153-196`; per-reward take/skip protocol
`Reward.cs:92/:111-113/:120-134` (concrete: `PotionReward.cs:76/:95`,
`CardReward.cs:183/:313`); test mode auto-takes everything
(`RewardsSet.cs:172-189`) — i.e. the sim today is permanently in C#'s
TestMode. The player can decline any reward on these screens.

## The fix

Derive the shape from the C# and today's driver conventions; the scouted
option: wire `run.reward_offer_selector` in `driver.py` next to `:296-302`
with an adapter routing `"potion"` → REWARD_POTION and `"card_reward"` →
REWARD_CARD decisions (reuse `_reward_selector`'s machinery), OR unify
`_accept_offer` onto the already-wired `reward_selector` and retire the
second name. Whichever you choose: say why, and keep `events/base.py`
edits inside `:204-229` (`offer_card_reward` at `:231-240` is R2's
territory — touch only what the selector read needs).
- `conformance/runner.py`: the `_ForceWinDriver` must answer the new
  decisions such that recorded replays still traverse (the recorded runs
  contain the real player's take/skip choices — derive how the runner
  answers today for REWARD_POTION and match; dispatch table
  `:247-268`). The conformance suite must stay at its baseline.
- RL action space: both decision kinds already exist in the layout
  (scouted: no `run_env.py` change needed) — verify, state it.

## Watch items

- `test/test_rng_tripwire.py:15` pins `driver.py` line numbers — adding
  lines above `_ask` trips it; update if so.
- The default when NO driver is attached (bare RunState in unit tests)
  must stay auto-accept (today's `selector is None → True`) or hundreds
  of event tests change meaning — preserve that and pin it.
- Do NOT change what any event GRANTS — only whether the player is asked.

## Footprint (yours alone this wave)

`sts2_rl/driver.py`, `sts2_rl/run.py` (only if unifying the selector
names), `sts2_rl/events/base.py` (`:204-229` only),
`sts2_rl/conformance/runner.py`, plus tests
(`test/test_event_offer_screens.py`, `test/test_driver.py`).
NOT yours: `events/the_future_of_potions.py`, other `events/*`,
`rewards.py`, `hooks.py`, `combat.py`, `player.py`, `cmds.py`,
`powers.py`, `relics/**`, `audit/**`.

## Entries to settle

This gap is recorded ON `event/the_future_of_potions/g15` "for want of a
better home" (round-12 note) — your report should propose how the record
should now read: the selector-wiring half closes; the reroll-surface half
(R2) stays open. Also propose the queue annotation for the "Still open,
owned by nobody" section. Controller applies both.

Report path: `.superpowers/sdd/round13/R6-report.md`.
