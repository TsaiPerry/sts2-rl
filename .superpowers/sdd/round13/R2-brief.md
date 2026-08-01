# R2 — event/the_future_of_potions/g15: give the event's card reward a real reward surface

Read first: `.superpowers/sdd/round13/PROTOCOL.md` (binding). Maps scouted
2026-08-01. Wave 3: R10 (consolidated reward dispatch, wave 1) and R6
(reward_offer_selector wiring, wave 2) have landed — read BOTH reports
(`R10-report.md`, `R6-report.md`) and the current code first; your fix
builds directly on both.

## The gap (LIVE — recorded round 12, `event/the_future_of_potions/g15`)

`events/base.py::Event.offer_card_reward` (`:231-240`, sole caller
`events/the_future_of_potions.py:95`) routes through
`run.select_cards("card_reward", cards, 1)` — a pick-or-skip card
selection with NO reroll and NO sacrifice surface, and it never touches
`CombatRewards`, so reward modifiers (Driftwood's `can_reroll`) have
nowhere to land. In C# the event's screen IS rerollable:
`TheFutureOfPotions.cs:123-139` `Trade` builds
`new CardReward(options, 3, Owner)` (`:128`, options `:127` =
`ForNonCombatWithUniformOdds(...).WithFlags(NoRarityModification |
NoCardPoolModifications)`), hooks `reward.AfterGenerated +=
UpgradeCardsInReward` (`:129`, body `:132-138`), then
`RewardsCmd.OfferCustom` (`:130`) → `RewardsSet.WithCustomRewards` →
`GenerateWithoutOffering` → `Hook.ModifyRewards` (`RewardsSet.cs:136`).
Driftwood (`Driftwood.cs:14-25`) sets `CanReroll` on every CardReward
with no room check.

## ADDENDUM (2026-08-01) — READ THIS BEFORE THE FIX SHAPE BELOW

Two corrections from R6 and its review; both change what you should build.

1. **The premise in the round-12 record is half wrong, CONFIRMED BY EXECUTION.**
   `Event.offer_card_reward` NEVER auto-accepted in real play: its decline
   path already ran through `RunState.select_cards` -> `_card_selector` ->
   `SKIPPABLE_PURPOSES`. (Proven by driving the pre-fix code with a real
   `RunDriver`: `the_future_of_potions` raised `['event','select_cards']`,
   and a decline-everything policy left the deck at 10 while a take policy
   took it to 11.) So the ONLY thing missing on this screen is the
   **reroll**, not the take-or-skip. Do not "fix" a decline that works.
2. **Do NOT put the reroll surface on `select_cards`** — R6's report
   suggests that and its reviewer overturned it. In C#,
   `CardRewardAlternative.Generate` (`CardRewardAlternative.cs:53-74`) puts
   **Skip AND REROLL as options on the card-selection screen itself**, so
   the game presents ONE screen offering `{cards..., Skip, REROLL}`. The
   sim's existing `REWARD_CARD` decision already has exactly that shape
   (pick / skip / reroll / sacrifice — `driver.py`'s `_offer_card_group`
   and `own_actions`). **The reroll belongs on that existing decision**;
   routing this event's offer onto the reward-screen path is what gives it
   the reroll, and a second accept gate would invent a decision the game
   does not have.
   Re-derive both claims from the C# yourself before building.

## The fix shape (scouted; re-derive against C#)

Convert `the_future_of_potions.py::_trade` to the `pending_rewards`
channel already used by `events/brain_leech.py:90` and
`events/trial.py:119`: build a `CombatRewards` + populated
`CardRewardGroup`, set `self.pending_rewards`; the driver drains it
(`driver.py:533-543`) through `_offer_rewards` → `_offer_card_group`
(`driver.py:488-511`) which surfaces reroll (`:500-504`) and sacrifice
(`:506-509`). Under R10's consolidation the new construction site gets
its dispatch per whatever scheme R10 landed — follow R10's report.
Details to preserve from the C#:
- The 3 cards, their creation options and the per-card upgrade behavior
  (`the_future_of_potions.py:86-91` today) — only the OFFER protocol
  changes, not what is offered. Verify the reroll REGENERATES the cards
  the same way C#'s `CardReward` re-populate + `AfterGenerated` upgrade
  does — that is the whole point of the port.
- The potion-discard leg (`PotionCmd.Discard`, `TheFutureOfPotions.cs:126`)
  stays where it is.
- Whole-screen skip: C#'s custom offer allows skipping the reward
  (`Reward.OnSkipped`); `_offer_card_group` folds skip into index n
  (`driver.py:204`) — with the R6 selector landed, decide whether
  `_accept_offer`'s gate at `events/base.py:235` is now redundant
  double-asking (scout's view: the pending_rewards path makes it
  redundant AND that matches C#) — derive, decide, document.
- `Event.offer_card_reward` (`events/base.py:231-240`) afterwards: if
  this was its sole caller, either delete it or leave it with a
  documented reason — coordinate with what R6 did at `:204-229`.

## Footprint (yours alone this wave)

`sts2_rl/events/the_future_of_potions.py`, `sts2_rl/events/base.py`
(`:231-240` block), `sts2_rl/run.py` ONLY if the offer must route through
`run.offer_rewards` (`:523-543`) rather than `pending_rewards`, plus
tests (`test/test_event_offer_screens.py:132-154` will need re-staging; a
new Driftwood-reroll-reaches-the-event pin is REQUIRED — RED first: prove
the reroll is unavailable today, then available).
NOT yours: `driver.py`, `rewards.py`, other events, relics, `hooks.py`,
`combat.py`, `cmds.py`, `powers.py`, `audit/**`.

## Entries to settle

`event/the_future_of_potions/g15` (record
`audit/records/event/the_future_of_potions.json` around `:202`/`:235`) —
propose the close (or narrow, if any leg remains), naming the reasoning
replaced: the round-12 text says "needs new capability, not a missing
call"; your close should say what capability was built and how the
selector-wiring half (R6) and reroll half divide. Controller applies.

Report path: `.superpowers/sdd/round13/R2-report.md`.
