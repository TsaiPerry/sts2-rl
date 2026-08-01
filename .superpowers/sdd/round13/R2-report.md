# R2 report — event/the_future_of_potions/g15: a real reward surface

Footprint touched: `sts2_rl/events/the_future_of_potions.py` (full file),
`sts2_rl/events/base.py` (`offer_card_reward` block only — deleted, plus a
comment left in its place), `test/test_event_offer_screens.py`,
`test/test_event_rng_streams.py`, `test/test_shared_events.py`.
`sts2_rl/run.py` and `sts2_rl/driver.py` were read but **not edited** — the
fix did not need either (see §1).

## 0. Re-verifying the addendum and both predecessor reports against the live tree

Read `R10-report.md` and `R6-report.md` in full, then re-derived every
citation against the current files rather than trusting either document:

- `events/base.py`: `_accept_offer` is now `:204-258` (R6's fallback logic,
  confirmed present and unchanged by me except the comment left where
  `offer_card_reward` used to be), `offer_potion` `:260-265`,
  `offer_card_reward` (pre-my-edit) `:267-276` — matches the brief's `:231-240`
  citation only after accounting for R6's docstring expansion; re-derived,
  not trusted.
- `events/the_future_of_potions.py`: `_trade` (pre-edit) at `:69-96`, sole
  caller of `offer_card_reward` at `:95` — confirmed by
  `grep -rn "offer_card_reward" sts2_rl/ test/` (4 hits: the two comment
  mentions, the definition, and this one real call).
- `driver.py`: `_offer_rewards` `:475-517`, `_offer_card_group` `:519-542`
  (brief cited `:488-511`/`:500-509` — shifted since R10; re-verified by
  reading the file, not by trusting either brief's line numbers).
  `DecisionRequest.own_actions`'s `REWARD_CARD` branch (`:207-214`): legal
  actions are `range(n+1)` (cards + skip) plus `n+1` iff
  `rewards.can_reroll`, plus `n+2` iff `rewards.sacrifice_relic is not None`.
- `rewards.py`: `CardRewardGroup` (`:485-548`) and `CombatRewards`
  (`:551-659`) read in full, plus `apply_reward_modifiers` (`:661-723`).
  Confirmed `CardRewardGroup.populate()` (`:530-542`) already sets
  `is_card_reward=True` unconditionally and `reroll()` (`:544-548`) just
  clears `can_reroll` and calls `self.populate(run)` — i.e. Python dispatch
  means a subclass overriding `populate()` gets the override on reroll too,
  with zero extra wiring.
- `driftwood.py` / `paels_wing.py`: both iterate `rewards.card_rewards` with
  **no room check** (Driftwood: `modify_combat_rewards_late`; Pael's Wing:
  `modify_combat_rewards` for the sacrifice slot, `on_sacrifice` for the
  grab-bag pull) — confirmed by reading both files, matching R10's dormancy
  table finding ("no gate, but the base list is always empty here" — for
  this event the list is NOT empty, so both relics are live on this screen
  the moment they're wired here).

## 1. Re-deriving the addendum's two corrections against the C#

**Correction 1 (round-12 record half wrong):** confirmed. Pre-fix,
`_trade` called `self.offer_card_reward(cards)` →
`self.run.select_cards("card_reward", cards, 1)`, and `"card_reward"` is a
member of `driver.py`'s `SKIPPABLE_PURPOSES` — so a driver-attached policy
could already decline. My new RED tests independently reproduce this: see
`test_the_future_of_potions_no_longer_uses_select_cards`'s docstring and
§3 below. The correction changes the fix's SHAPE, not its target: only the
reroll/sacrifice surface was missing, not a decline path.

**Correction 2 (reroll belongs on the existing REWARD_CARD decision, not
`select_cards`):** confirmed directly against the source, not deferred to
the addendum's claim:

- `CardReward.OnSelect` (`CardReward.cs:183-311`) calls
  `CardRewardAlternative.Generate(this)` (`:189`) and then runs ONE
  selection loop (`:194-292`) over a single combined index space —
  `_cards` (the drawn cards) followed by `cardRewardOption` (Skip +
  REROLL + any relic-added alternatives, e.g. Pael's Wing's sacrifice).
  There is no separate accept/decline screen before this one.
- `CardRewardAlternative.Generate` (`CardRewardAlternative.cs:53-74`):
  `:56-59` adds `"Skip"` gated on `CardReward.CanSkip` (default `true`,
  `CardReward.cs:95`, never overridden by `TheFutureOfPotions.cs`); `:60-67`
  adds `"REROLL"` gated on `reward.CanReroll` (Driftwood).
- The sim's `driver.py:207-214` (`REWARD_CARD`'s `own_actions`) and
  `driver.py:519-542` (`_offer_card_group`, the reroll-and-re-ask loop) are
  already exactly this shape — one screen, one decision, reroll re-asks the
  same decision. Building a second accept gate on top (either on
  `select_cards` or by wiring a NEW selector) would invent a decision the
  game does not have. This is why I converted `_trade` to the
  `pending_rewards` → driver `_offer_rewards` → `_offer_card_group` channel
  instead of extending `select_cards`.

## 2. The fix

### 2a. `_trade` now builds a real `CombatRewards`/`CardRewardGroup`

`sts2_rl/events/the_future_of_potions.py::_trade` (was: build a bare card
list, call `self.offer_card_reward(cards)`) now:

1. Computes `candidates` exactly as before (same rarity/type filter, same
   `reward_pool_card_ids` call — **RNG order and pool are unchanged**, per
   the brief's "only the OFFER protocol changes, not what is offered").
2. Builds a `_PotionCardRewardGroup` (a small local subclass of
   `CardRewardGroup`, defined at module scope) with `pool=candidates`,
   `odds_type=RarityOddsType.UNIFORM`, `count=3`, and calls
   `group.populate(self.run)` — this is the FIRST draw, done eagerly
   (mirroring `brain_leech.py`'s Rip and `trial.py`'s Nondescript Guilty,
   which both pre-populate their group(s) before calling
   `apply_reward_modifiers`, matching the RNG-order-preserving convention
   R10's `apply_reward_modifiers` docstring documents).
3. Wraps it in `CombatRewards(room_type=RoomType.MONSTER,
   card_rewards=[group])` (`rewards.room` stays `None` — no `AbstractRoom`
   behind a mid-event `OfferCustom` screen, `RewardsSet.cs:106-110` — same
   as brain_leech/trial) and calls `apply_reward_modifiers(self.run,
   rewards)`. Since the group is already `populated=True` by step 2, the
   populate-sweep inside `apply_reward_modifiers` is a no-op for it; the two
   relic-hook passes (Driftwood's reroll flag, Pael's Wing's sacrifice slot)
   run over it exactly as they would over any other `CombatRewards`.
4. Sets `self.pending_rewards = rewards` and calls `self._finish("DONE")` —
   the exact `brain_leech.py`/`trial.py` convention; `driver.py:564-574`
   (`_run_event`) drains `pending_rewards` through `_offer_rewards` →
   `_offer_card_group` between the option resolving and the next page being
   asked for.

### 2b. `_PotionCardRewardGroup` — why the reroll re-upgrades

`CardReward.Populate` (`CardReward.cs:146-165`) fires
`AfterGenerated?.Invoke()` (`:162`) **only inside the `_cards.Count <= 0`
branch** (`:156-164`) — i.e. whenever cards are actually (re)drawn, not on
every call. `Reroll()` (`CardReward.cs:322-332`) clears `_cards` (`:330`)
then calls `Populate()` again (`:331`), so it re-enters that same branch and
re-fires `AfterGenerated`. `TheFutureOfPotions.Trade` hooks
`reward.AfterGenerated += UpgradeCardsInReward` (`TheFutureOfPotions.cs:129`,
body `:132-138`, upgrading every card currently in `reward.Cards`) — so in
C#, **every reroll re-upgrades the newly-drawn cards**, not just the first
draw.

`sts2_rl/rewards.py`'s `CardRewardGroup.populate()` is the sim's `Populate`
analogue and is called both by the first (eager) draw and by `reroll()`
(`rewards.py:544-548`, unchanged, out of my footprint). I subclassed it
locally:

```python
class _PotionCardRewardGroup(CardRewardGroup):
    def populate(self, run: "RunState") -> None:
        super().populate(run)
        for card in self.cards:
            card.upgrade()
```

Because `reroll()` calls `self.populate(run)` (not
`CardRewardGroup.populate`), Python's normal method dispatch runs my
override on every reroll automatically — no duplicated draw logic, no risk
of the initial draw and a rerolled draw silently taking different code
paths. Pinned by
`test_the_future_of_potions_driftwood_reroll_reaches_the_event`'s final
assertion (`run.deck[-1].upgrade_level == 1` after a forced reroll).

### 2c. A bug found and fixed as a direct consequence of 2b: `IsCardReward`

The OLD hand-rolled call was:
`create_reward_cards(self.run, RarityOddsType.UNIFORM, count=3,
mutate_pity=False, pool=candidates)` — **no `is_card_reward=True`.**
`CardRewardGroup.populate()` (`rewards.py:541`) always passes
`is_card_reward=True`, mirroring `CardReward.cs:114-115`'s constructor,
which unconditionally does `Options = options.WithFlags(CardCreationFlags.
IsCardReward)` for every `CardReward`, including this exact
`new CardReward(options, 3, base.Owner)` call
(`TheFutureOfPotions.cs:128`). So in C#, this screen's `CardCreationOptions`
**always** carries `IsCardReward`.

Two sim relics gate their late-pass card-reward hook on exactly that flag:

- `sts2_rl/relics/silken_tress.py:36` — `if options is None or not
  options.has_flag(CardCreationFlags.IS_CARD_REWARD): return False`
  (mirrors `SilkenTress.cs:53-56`).
- `sts2_rl/relics/silver_crucible.py:35` — same guard (mirrors
  `SilverCrucible.cs:104-107`).

`create_reward_cards`'s `modify_hooks` pass (default `True`, and the OLD
call never set `modify_hooks=False`) already iterates every relic and calls
`relic.modify_card_reward_options_late(run, cards, options)`
(`rewards.py:414-416`) — so these two relics WERE being asked, every time,
but were bailing immediately because `options` never carried the flag they
check for. Concretely: **a player holding Silken Tress or Silver Crucible
who traded a potion at this event got an un-enchanted / un-upgraded card
where C# would have enchanted/upgraded it** — a real, live divergence,
distinct from g15, that the existing audit record never caught (its own
"the offer's pool and filters" guard, `audit/records/event/
the_future_of_potions.json` around line 187, only checks the FOUR
pool-widening relics gated on `NoCardPoolModifications`
— DingyRug/PrismaticGem/CharacterCards/BigGameHunter — and never mentions
`IsCardReward` or these two relics at all).

Since I was already replacing this exact call site with
`group.populate()` for the reroll fix, and the base `CardRewardGroup.
populate()` already passes `is_card_reward=True` unconditionally, this bug
is fixed as a direct, unavoidable consequence of routing through the shared
method rather than hand-rolling the call — not a separate, bolted-on
change. I verified no existing test pins the old (buggy) skip behavior
(`grep -rn "silken_tress\|silver_crucible" test/*.py` → only
`test_neow.py`, `test_r13_relic2.py` (Hefty Tablet material, unrelated),
`test_relic_tier1_gaps.py`, `test_relics.py`; none combine either relic
with `the_future_of_potions`), so nothing regressed. **I did not add a new
pinning test for this specific interaction** — it's a byproduct fix
discovered mid-task, not this task's assigned gap, and adding
Silken-Tress/Silver-Crucible-specific coverage felt like scope creep beyond
"give the reward a real surface"; flagging it here for the controller to
decide whether it deserves its own record/test.

### 2d. `Event.offer_card_reward` — deleted

`the_future_of_potions.py:95` was `offer_card_reward`'s sole caller
(confirmed: `grep -rn "offer_card_reward" sts2_rl/ test/`, pre-edit, found
only the definition, its own docstring self-reference, and this one call).
With `_trade` no longer calling it, it had zero callers, so per the brief's
"either delete it or leave it with a documented reason" I deleted the
method and left an explanatory comment in its place (within the declared
"`offer_card_reward` block" footprint).

**BLOCKED-ON-FOOTPRINT (documentation only, not behavior):**
`_accept_offer`'s docstring (`events/base.py:204-258`, R6's text, outside my
declared block) step 3 says *"`purpose == "card_reward"` (today's only
other purpose — `offer_card_reward`'s sole caller is
`the_future_of_potions.py:95`)..."* — this is now stale: that method no
longer exists, and `_accept_offer`'s `purpose == "card_reward"` branch
(`events/base.py:254-... return True` path — actually the branch is simply
"no `if purpose == "potion"` match, falls through to `return True`") is
dead code with zero callers anywhere in the tree. I did not touch this
because it lives in `_accept_offer`, not the `offer_card_reward` block. If
useful, the exact prose fix I'd apply: replace step 3's opening clause
*"`purpose == "card_reward"` (today's only other purpose —
`offer_card_reward`'s sole caller is `the_future_of_potions.py:95`) falls
straight to the true-default below..."* with something like *"`purpose ==
"card_reward"` — historical: `Event.offer_card_reward`, the only method
that ever passed this purpose, was removed 2026-08-01 (R2, round 13); this
branch is dead code kept for any future `OfferCustom`-style caller that
might reintroduce the purpose, in which case the same reasoning applies —
its real take-or-skip/reroll/sacrifice decision belongs on
`pending_rewards` → `REWARD_CARD`, not a second ask here."* Low risk,
comment-only, safe to land at fold time.

The stray `"Card"` TYPE_CHECKING import at the top of `base.py` (used only
by the now-deleted method's signature) is now unused; left untouched for
the same footprint reason — it's inert (TYPE_CHECKING-only, no runtime
effect) and outside the declared block.

## 3. Tests — RED first, then GREEN

### RED evidence (pre-fix, confirmed by running the new tests against the unmodified tree)

Ran the 4 new/rewritten tests below against the pre-fix code; all 4 failed
for the diagnostic reason, not an incidental one:

- `test_the_future_of_potions_declined_screen_adds_no_card` (rewritten to
  use a real `RunDriver` and decline via `REWARD_CARD`'s skip index) —
  failed because `DecisionKind.REWARD_CARD` was never raised at all
  (the screen went through `SELECT_CARDS` instead).
- `test_the_future_of_potions_driftwood_reroll_reaches_the_event` (new) —
  failed on `assert DecisionKind.REWARD_CARD in kinds`: **the reroll was
  not merely declined, it was structurally impossible** — no
  `REWARD_CARD` decision, hence no reroll slot, existed for this event at
  all, Driftwood held or not. This is the addendum's required "prove the
  reroll is unavailable today" RED.
- `test_the_future_of_potions_not_rerollable_without_driftwood` (new) —
  failed on `assert seen` (empty list — no `REWARD_CARD` decision seen).
- `test_the_future_of_potions_no_longer_uses_select_cards` (rewritten from
  the old `..._card_offer_already_declines_through_select_cards`) — failed
  on `assert DecisionKind.SELECT_CARDS not in kinds` (it WAS in kinds,
  pre-fix).

(`test_the_future_of_potions_taken_screen_adds_one_upgraded_card` happened
to stay green pre-fix by coincidence — `SELECT_CARDS`'s "take index 0"
happens to equal `REWARD_CARD`'s "take index 0" under a driver policy that
always answers `legal_actions()[0]` for non-`REWARD_CARD` kinds — so it
isn't RED evidence on its own; the three above are.)

### GREEN after the fix

All 4 pass, plus the untouched regression guards. Full list of
added/changed tests:

- `test/test_event_offer_screens.py`:
  - `test_the_future_of_potions_declined_screen_adds_no_card` — rewritten
    to drive through a real `RunDriver`, decline via `REWARD_CARD`'s skip
    index.
  - `test_the_future_of_potions_taken_screen_adds_one_upgraded_card` —
    rewritten the same way (take index 0).
  - `test_the_future_of_potions_driftwood_reroll_reaches_the_event` (NEW,
    the brief-required pin) — forces one reroll via the driver, then takes
    the re-rolled first card; asserts `REWARD_CARD` was raised, the reroll
    slot was taken, the deck grew by one, and the taken card is still
    `upgrade_level == 1` (proving `AfterGenerated` re-fired on reroll, not
    just the first draw).
  - `test_the_future_of_potions_not_rerollable_without_driftwood` (NEW) —
    regression guard: no Driftwood, reroll index never legal.
  - `test_the_future_of_potions_no_longer_uses_select_cards` (renamed from
    `..._card_offer_already_declines_through_select_cards`, whose premise —
    declining through `SELECT_CARDS` — is no longer true for this event)
    — pins the migration: `SELECT_CARDS` never appears, `REWARD_CARD` does.
- `test/test_event_rng_streams.py::test_the_future_of_potions_offer_runs_the_reward_hooks`
  — rewritten to read `event.pending_rewards.cards` directly (bare
  `RunState`, no driver needed) instead of a `card_selector` callback that
  no longer fires for this event; same assertions (cards upgraded,
  `run.rng.draws == 0`).
- `test/test_shared_events.py::test_future_of_potions_trades_potion_for_upgraded_card`
  — rewritten to attach a `RunDriver` and drain `event.pending_rewards` via
  `driver._offer_rewards(...)` before asserting the deck grew; same
  assertions otherwise (`option_keys()`, potion discarded, common+upgraded
  card added).

### Commands run and counts

```
py -m pytest test/test_event_offer_screens.py -v
  -> 19 passed

py -m pytest test/test_event_rng_streams.py test/test_shared_events.py test/test_event_offer_screens.py -q
  -> 113 passed

py -m pytest test/test_event_offer_screens.py test/test_event_rng_streams.py \
  test/test_shared_events.py test/test_rewards.py test/test_relic_tier1_gaps.py \
  test/test_rng_tripwire.py test/test_reward_dispatch_and_relic_stubs.py \
  test/test_event_reward_modifiers.py test/test_glass_eye_reward_set.py \
  test/test_driver.py test/test_darv.py test/test_tier1_last_five.py \
  test/test_reward_dispatch_choke_point.py -q
  -> 366 passed

py -m pytest test/test_rewards.py test/test_relic_tier1_gaps.py test/test_rng_tripwire.py \
  test/test_event_offer_screens.py test/test_reward_dispatch_and_relic_stubs.py \
  test/test_event_reward_modifiers.py test/test_glass_eye_reward_set.py test/test_driver.py \
  test/test_darv.py test/test_shared_events.py test/test_tier1_last_five.py \
  test/test_reward_dispatch_choke_point.py test/test_event_rng_streams.py \
  test/test_event_live_tail.py test/test_underdocks_hive_events.py test/test_relics.py -q
  -> 591 passed

py -m pytest test/ -k "event" -q
  -> 433 passed, 3488 deselected

py -m pytest test/test_conformance_runner.py test/test_conformance_map.py \
  test/test_conformance_player_state.py test/test_conformance_floor_state.py \
  test/test_conformance_combat.py test/test_conformance_pools.py \
  test/test_conformance_relic_bag.py test/test_conformance_rooms.py \
  test/test_conformance_recording.py test/test_conformance_save.py \
  test/test_conformance_determinism.py -q
  -> 2 failed, 98 passed, 6 xfailed
  (the 2 failures are test_conformance_floor_state.py's documented missing-
  fixture gap — 933T39V18D/floor_49/actions.sts2replay absent on disk,
  FileNotFoundError trace, per PROTOCOL.md never fixed/counted)

py -m pytest test/test_run_env.py -q
  -> 12 passed
```

No regressions anywhere in the swept set. `git status`/`git diff HEAD` on
my 5 touched files show only my edits (`base.py` and
`test_event_offer_screens.py` show `MM` — already-staged controller state
plus my new unstaged edits, consistent with "the tree is largely STAGED by
the controller").

## 4. Verdict per queue entry

### `event/the_future_of_potions/g15`

**FIXED.** The reroll-surface gap (`Event.offer_card_reward` skipped
`Hook.ModifyRewards`, no reroll/sacrifice surface) is closed: `_trade` now
builds a real `CombatRewards`/`CardRewardGroup`, calls
`apply_reward_modifiers`, and hands it to the driver via `pending_rewards`
→ `_offer_card_group`, which already implements pick/skip/reroll/sacrifice.
Diff summary: `sts2_rl/events/the_future_of_potions.py` (full-file rewrite
of `_trade` plus a new module-level `_PotionCardRewardGroup` subclass);
`sts2_rl/events/base.py` (`offer_card_reward` deleted). Tests:
`test_the_future_of_potions_driftwood_reroll_reaches_the_event`,
`test_the_future_of_potions_not_rerollable_without_driftwood`,
`test_the_future_of_potions_no_longer_uses_select_cards`,
`test_the_future_of_potions_declined_screen_adds_no_card`,
`test_the_future_of_potions_taken_screen_adds_one_upgraded_card` (all in
`test/test_event_offer_screens.py`).

## 5. Record-close proposal

I did not edit `audit/records/**`.

### `audit/records/event/the_future_of_potions.json` — guard "G-new" (informally g15, around `:230-236`)

**Propose: verdict `gap` → `faithful`.** Replace the guard's `issue` text
(the long paragraph starting "G-new (found 2026-07-31...)" through the R6
update) with something like:

> "**R2 update (2026-08-01, round 13): CLOSED.** `_trade`
> (events/the_future_of_potions.py) no longer routes through
> `Event.offer_card_reward` (deleted — zero callers left,
> `events/base.py`). It now builds a `CombatRewards` holding one
> `CardRewardGroup` (a local `_PotionCardRewardGroup` subclass whose
> `populate()` re-runs `TheFutureOfPotions.cs:129`'s `AfterGenerated`
> upgrade on every draw, including Driftwood's reroll —
> `CardReward.cs:156-164`/`322-332`), calls `apply_reward_modifiers`
> (rewards.py) directly (mirroring `RewardsCmd.OfferCustom` →
> `RewardsSet.WithCustomRewards(rewards).Offer()`, `RewardsCmd.cs:47-50`),
> and hands it to `self.pending_rewards` — the same mid-event OfferCustom
> channel `brain_leech.py`'s Rip and `trial.py`'s Nondescript Guilty
> already use (R10's choke-point consolidation covers this construction
> site automatically: `driver._offer_rewards`'s idempotent backstop, per
> `event/brain_leech.json`'s updated note). The driver's existing
> `_offer_card_group` (driver.py:519-542) surfaces pick/skip/reroll
> (Driftwood, no room check, `Driftwood.cs:14-25`) /sacrifice (Pael's Wing,
> `PaelsWing.cs`), exactly matching C#'s single `CardReward.OnSelect`
> screen (`CardReward.cs:183-311`,
> `CardRewardAlternative.Generate`/`CardRewardAlternative.cs:53-74`).
> Pinned by `test_the_future_of_potions_driftwood_reroll_reaches_the_event`
> (RED confirmed pre-fix: no `REWARD_CARD` decision was ever raised for
> this event, Driftwood held or not — the reroll was structurally
> impossible, not merely declined) and 4 other tests in
> test/test_event_offer_screens.py. **What reasoning this replaces:** the
> R6 update correctly separated the potion-wiring half (fixed by R6) from
> the reroll-surface half (left open, correctly identified as belonging on
> REWARD_CARD not SELECT_CARDS) — R2 executes exactly that plan. Also
> found and fixed in the same pass, NOT part of g15 itself: the old
> hand-rolled `create_reward_cards(...)` call never set
> `is_card_reward=True`, where C#'s `CardReward` constructor always does
> (`CardReward.cs:114-115`) — this caused Silken Tress
> (`silken_tress.py:36`) and Silver Crucible (`silver_crucible.py:35`) to
> incorrectly skip their card-reward hook on this event's screen (both
> gate on that exact flag, `SilkenTress.cs:53-56`/`SilverCrucible.cs:
> 104-107`). Routing the card draw through `CardRewardGroup.populate()`
> (which always passes `is_card_reward=True`) fixed it as a side effect;
> see R2-report.md §2c. The existing 'offer's pool and filters' guard
> above (verdict faithful) is unaffected — it only concerns the FOUR
> pool-widening relics gated on `NoCardPoolModifications`, a different
> flag."

### New finding, no home yet: `silken_tress`/`silver_crucible` × `the_future_of_potions`

Not part of g15, found and fixed as an unavoidable consequence of the g15
fix (see §2c). I did not add a dedicated pinning test for this specific
relic × event interaction (would need to construct a run holding
Silken Tress or Silver Crucible, trigger this event, and assert the
enchant/upgrade landed) — flagging for the controller to decide whether it
warrants its own guard/test, e.g. under `relic/silken_tress.json` /
`relic/silver_crucible.json`, or a note on this event's record.

## 6. Queue-annotation proposal (`GAP-QUEUE.md`, terse style)

Wherever `event/the_future_of_potions/g15` (or "7 remaining live
mechanisms... new this round") is currently listed as live, replace with:

> - ~~`event/the_future_of_potions/g15`: `Event.offer_card_reward` skips
>   `Hook.ModifyRewards`, no reroll surface.~~ **CLOSED 2026-08-01 (round
>   13, R2):** the event's CardReward now rides `pending_rewards` →
>   `driver._offer_card_group`, the same mid-event OfferCustom channel
>   brain_leech/trial use, so Driftwood's reroll and Pael's Wing's
>   sacrifice both reach it, matching C#'s single `{cards…, Skip, REROLL}`
>   screen (`CardReward.cs:183-311`,
>   `CardRewardAlternative.cs:53-74`) — not a second ask bolted onto
>   `select_cards`, per R6's corrected parting advice. `Event.
>   offer_card_reward` deleted (zero callers left). Side-effect fix found
>   in the same pass (not g15 itself): the old hand-rolled card draw never
>   set `IsCardReward`, so Silken Tress / Silver Crucible incorrectly
>   skipped this event's screen — fixed by routing the draw through
>   `CardRewardGroup.populate()`, which always sets that flag.

## 7. Findings not in the brief

1. **Silken Tress / Silver Crucible × the_future_of_potions bug** — see
   §2c and §5. Real, live, pre-existing (not introduced by me), fixed as a
   byproduct; not independently pinned by a test.
2. **`_accept_offer`'s docstring is now stale in one spot** (its step-3
   sentence names `offer_card_reward` as "today's only other purpose" and
   cites its sole caller by line) — this method no longer exists.
   Documentation-only, BLOCKED-ON-FOOTPRINT per §2d, exact replacement text
   included there.
3. **A stray unused `"Card"` TYPE_CHECKING import** in `events/base.py`
   (only ever used by the now-deleted method's signature) — harmless,
   outside my declared block, left untouched; noted for whoever next
   touches that file's imports.
4. The audit record's own "the offer's pool and filters" guard
   (`audit/records/event/the_future_of_potions.json`, around line 187)
   already correctly distinguishes this event from `room_full_of_cheese` on
   the `NoCardPoolModifications` flag ("UNLIKE room_full_of_cheese,
   NoCardPoolModifications IS set here") — but its enumeration of the "four
   ModifyCardRewardCreationOptions implementers" never widens to cover
   `IsCardReward`-gated relics (a different hook,
   `TryModifyCardRewardOptionsLate`, gated by a different flag). Worth
   knowing for any future record audit that assumes that guard's
   enumeration is exhaustive over ALL flag-gated relic hooks.

## Status

DONE. `event/the_future_of_potions/g15` is fixed and pinned with a RED-
before/GREEN-after test proving the reroll was structurally impossible
before this change and works (including re-upgrading on reroll) after.
No footprint violations — one documentation-only staleness in
`_accept_offer`'s docstring reported as BLOCKED-ON-FOOTPRINT with the exact
replacement text (§2d), not applied.

**Test summary:** `test/test_event_offer_screens.py` 19/19 passed (5
new/rewritten for this task); full footprint-relevant sweep (16 files
spanning rewards/events/driver/relic-tier1/conformance-adjacent tests) 366
passed, plus a separate 591-test sweep including `test_relics.py` and
`test_underdocks_hive_events.py`, both clean; conformance suite 98
passed/6 xfailed/2 known-environmental-failures (missing fixture, per
PROTOCOL.md, not counted); `test_run_env.py` 12/12.

**Concerns:** none blocking. One documentation-only footprint item deferred
to the controller (§2d); one adjacent relic-interaction fix made without
its own dedicated test (§2c/§7.1) — flagged, not hidden.

---

# Fix pass (2026-08-01)

Second pass, driven by `R2-review.md` (verdict NEEDS-FIXES). The reroll work
of the first pass is unchanged — the reviewer confirmed it by execution.
Footprint this pass: `sts2_rl/events/the_future_of_potions.py`,
`sts2_rl/events/base.py`, `sts2_rl/rewards.py` (newly granted),
`test/test_event_offer_screens.py`. **`sts2_rl/relics/dingy_rug.py` was NOT
touched — see F1 for why the fix does not belong there.**

All "pre-fix" numbers below were obtained **out of tree**, by loading
`git show HEAD:sts2_rl/events/the_future_of_potions.py` into a throwaway
process (a fresh module object with `__package__ = "sts2_rl.events"`, plus a
capture-only stand-in for the deleted `Event.offer_card_reward`). The shared
worktree was never reverted, per PROTOCOL.md.

## F1. The Dingy Rug regression — FIXED, and the fix is in `rewards.py`

### Confirmed, independently

```
PRE-FIX (HEAD module, throwaway process)
  no relic        : [('tear_asunder',1), ('conflagration',1), ('mangle',1)]
  dingy_rug       : ['tear_asunder', 'conflagration', 'mangle']      (== no-relic)
POST-first-pass (worktree, before this pass)
  dingy_rug       : ['secret_technique', 'mangle', 'hand_of_greed']  (2 Colorless)
```

The reviewer's diagnosis is exactly right and I reproduce it verbatim. The
first pass set `IS_CARD_REWARD` and nothing else; `NO_CARD_POOL_MODIFICATIONS`
was set at no call site in the tree, so `dingy_rug.py:31`'s first guard was
inert and `:33`'s `IS_CARD_REWARD` guard was the operative one. Un-gating it
widened a screen whose C# options carry `NoCardPoolModifications`
(`TheFutureOfPotions.cs:127`), which `DingyRug.cs:19-22` respects.

### The fix does NOT belong in `dingy_rug.py`

`dingy_rug.py` is a faithful, guard-for-guard port of `DingyRug.cs:13-36` in
source order (owner / `NoCardPoolModifications` / `IsCardReward` /
already-contains-Colorless). Nothing in it is wrong. The defect was on the
PRODUCING side: `create_reward_cards` could not express the flag, so
`_PotionCardRewardGroup` could not declare it. Editing the relic to compensate
would have hidden a missing capability behind a lie in the one file that was
correct.

### What I built (`sts2_rl/rewards.py`)

1. `create_reward_cards(..., extra_flags: CardCreationFlags = CardCreationFlags(0))`.
   `extra_flags` is OR-ed onto the two flags the function already derives from
   `is_card_reward` / `modify_hooks` — mirroring `CardCreationOptions.WithFlags`,
   which is `Flags |= flag` (`CardCreationOptions.cs:212-216`), not an
   assignment. Two of the carried flags change behaviour here, exactly as in
   `CardFactory.CreateForReward`:
   - `NO_MODIFY_HOOKS` now also turns off the reward-options passes, so the
     flag spelling and the boolean spelling agree (`CardFactory.cs:102` is
     C#'s single gate).
   - `NO_UPGRADE_ROLL` skips `RollForUpgrade` **and its Rewards draw** — see F2.
   The rest are inert here and exist for the listeners to read off
   `CardCreationOptions.flags`.
2. `CardRewardGroup.flags: CardCreationFlags = CardCreationFlags(0)`, forwarded
   as `extra_flags=self.flags` from `populate()`. Default empty, because
   `CardCreationOptions.ForRoom` — every post-combat screen — sets no flags, so
   nothing else in the tree changes behaviour.

### What I declared (`sts2_rl/events/the_future_of_potions.py`)

`_SCREEN_FLAGS`, re-derived from the source rather than from the single
`.WithFlags(...)` call the brief quoted:

```
CardCreationOptions.ForNonCombatWithUniformOdds(pool, predicate)
    -> .WithFlags(NoUpgradeRoll)                     CardCreationOptions.cs:160-162
.WithFlags(NoRarityModification | NoCardPoolModifications)
                                                     TheFutureOfPotions.cs:127
new CardReward(options, 3, Owner)
    -> Options = options.WithFlags(IsCardReward)     CardReward.cs:114-115
```

so the creation runs against **four** flags, not two.
`_SCREEN_FLAGS = NO_UPGRADE_ROLL | NO_RARITY_MODIFICATION |
NO_CARD_POOL_MODIFICATIONS`; `IS_CARD_REWARD` is left to
`CardRewardGroup.populate()`, which ORs it on for every group exactly as the
constructor does.

`NO_RARITY_MODIFICATION` has no ported reader and Uniform odds take no rarity
roll — declared as documentation, as the reviewer noted.

## F2. A SECOND divergence at the same construction site — `NoUpgradeRoll`

**This is not in the review, and it is live.** `ForNonCombatWithUniformOdds`
itself ORs `NoUpgradeRoll` onto the options (`CardCreationOptions.cs:160-162`;
`ForNonCombatWithDefaultOdds` does the same at `:139` and `:152`), and
`CardFactory.cs:97-101` guards the whole `RollForUpgrade` call on it —
including the `rng.NextFloat()` that lives inside `RollForUpgrade`
(`CardFactory.cs:290`). The sim rolled unconditionally.

Executed (HEAD module, throwaway process, act 2, seed `UPGRADEROLL`, a Common
potion so the candidates are Common cards rather than upgrade-immune Rares):

```
PRE-FIX act2 UPGRADEROLL: draws = 6  [('armaments',2), ('havoc',2), ('shrug_it_off',2)]
POST-FIX                : draws = 3  all cards at upgrade_level 1
```

Two divergences in one:

- **RNG order.** 6 Rewards draws where C# takes 3. Conformance-visible for the
  rest of the run. (The review's "RNG accounting unchanged: 6 draws" was an
  accurate description of the sim, but 6 was already the wrong number.)
- **Card identity.** In acts >= 1 the act-scaled roll (`act_index * 0.25`) could
  upgrade a card, and then this event's `AfterGenerated` upgraded it again — so
  the screen offered `+2` cards where C# always offers exactly `+1`. A sweep of
  7 seeds x acts {0,2,3} showed the leak in 13 of 14 later-act cases and never
  in act 0 (where the odds are 0).

Fixed by declaring `NO_UPGRADE_ROLL` in `_SCREEN_FLAGS` and honouring it in
`create_reward_cards`. Pinned by
`test_the_future_of_potions_offer_takes_no_upgrade_roll`.

**Scope note:** `create_reward_cards` honours the flag only for callers that
pass it, and this event is the only such caller. Every OTHER
`ForNonCombat*`-shaped site in the sim still takes the roll C# suppresses. That
is a pre-existing, unrecorded, live gap class — see FIND-D — which I
deliberately did NOT fix, because each site needs its own C# derivation and
several are other lanes' files.

## F3. The three tests the review named, plus a fourth — all in `test/test_event_offer_screens.py`

A shared helper `_potions_offer(*relic_ids)` drives the trade on a bare
`RunState` and returns the screen off `event.pending_rewards` (no driver
needed; the same shape `test_brain_leech_rip_costs_5_and_offers_colorless`
uses).

| test | RED evidence | how obtained |
|---|---|---|
| `test_the_future_of_potions_offer_is_not_widened_by_dingy_rug` | `AssertionError: Colorless cards leaked onto a NoCardPoolModifications screen: ['secret_technique', 'hand_of_greed']` | **run in-tree, before the `rewards.py` fix** — a genuine RED-then-GREEN |
| `test_the_future_of_potions_offer_is_upgraded_twice_with_silver_crucible` | `[('tear_asunder',1),('conflagration',1),('mangle',1)] times_used = 0` (asserts `==2` and `==1`) | HEAD module, throwaway process |
| `test_the_future_of_potions_offer_enchants_with_silken_tress` | `[('tear_asunder',None),('conflagration',None),('mangle',None)] is_used = False` | HEAD module, throwaway process |
| `test_the_future_of_potions_offer_takes_no_upgrade_roll` (**new, mine**) | `draws = 6  [('armaments',2),('havoc',2),('shrug_it_off',2)]` (asserts 3 draws, all `+1`) | HEAD module, throwaway process |

The Dingy Rug pin asserts BOTH legs the review asked for: no `COLORLESS_POOL`
id in the offer, **and** exact list equality against the same-seed no-relic
offer (the RNG-order half — a pool that widens re-orders every later
`NextItem`).

Silken Tress: the candidate set at seed `OFFERSCREEN` is three Rare Attacks,
all of which Glam CAN enchant (Glam adds no restriction beyond the base
`EnchantmentModel.CanEnchant`: no Status/Curse/Quest, playable, not already
enchanted). So the test pins the strong form — `is_used` flipped AND at least
one card actually carrying a `GlamEnchantment` — not just the one-shot burn.

## F4. Review section 6 — the reroll pin strengthened (review F6)

`test_the_future_of_potions_driftwood_reroll_reaches_the_event` now records
every offer the `REWARD_CARD` decision shows and asserts `len(offers) == 2`,
`offers[0] != offers[1]`, and `run.deck[-1].id in offers[1]`. A `reroll()`
that cleared `CanReroll` without redrawing passed the old assertions; it
cannot pass these. Executed offers:
`[['tear_asunder','conflagration','mangle'], ['conflagration','thrash','feed']]`.

## F5. Review section 5 — both stale docstring references fixed (review F4)

`base.py` is fully in this pass's footprint (the first pass had it restricted
to "the `offer_card_reward` block only"), so I applied the fix rather than
deferring it. **The whole of step 3 of `_accept_offer`'s docstring was
replaced**, which covers both stale references:

1. `offer_card_reward`'s "sole caller is `the_future_of_potions.py:95`" — the
   method no longer exists.
2. the closing parenthetical citing
   `test_the_future_of_potions_card_offer_already_declines_through_select_cards`
   — **renamed** by the first pass, which my section-2d text did not cover. The
   replacement points at
   `test_drowning_beacon_declines_through_a_real_driver_with_no_explicit_selector`
   (verified present, `test/test_event_offer_screens.py:428`), i.e. the
   surviving empirical evidence for the POTION leg, and drops the deleted
   card-leg claim entirely.

The replacement also re-states WHY the branch must stay un-wired in C# terms
(`CardReward.OnSelect` + `CardRewardAlternative.Generate`'s single index
space), so the reasoning survives the deletion of its old evidence.

Also removed: the now-dead `from ..cards import Card` TYPE_CHECKING import at
`base.py:32` (sole occurrence in the file, verified by
`grep -n Card sts2_rl/events/base.py` — the remaining hits are all prose). The
reviewer had correctly left it alone as out-of-footprint; it is in footprint
now.

## F6. Further findings, file-ready

### FIND-A — `brain_leech` / `trial` reroll from the WRONG OPTIONS (LIVE, pre-existing, unrecorded)

*(the review's F2, re-derived and re-executed)*

**C#.** The 3-arg `CardReward(options, count, owner)` ctor sets
`RerollOptions = Options` (`CardReward.cs:114-115`), so `Reroll` (`:322-332`)
-> `Populate` (`:331`) -> `CardFactory.CreateForReward` (`:158`) redraws from
the SAME options. Brain Leech's are
`ForNonCombatWithDefaultOdds(ColorlessCardPool).WithFlags(NoRarityModification | NoCardPoolModifications)`
(`BrainLeech.cs:56`); Trial's are
`ForNonCombatWithDefaultOdds(Owner.Character.CardPool)` (`Trial.cs:181`).

**Sim.** Both build `CardRewardGroup(cards=..., populated=True)` with no `pool`
and no `odds_type` (`brain_leech.py:79-80`, `trial.py:109-110`). `reroll()`
(`rewards.py`) calls `populate()`, which redraws with `pool=None` => the
CHARACTER pool at `ROOM_RARITY_ODDS[MONSTER]` = REGULAR odds with
`mutate_pity=True` (because `self.pool is None`).

**Executed** (Driftwood held, RIP taken, reroll taken on the offered slot,
seed `F2PROBE`):

```
brain_leech RIP
  offer 0: ['panache', 'flash_of_steel', 'dramatic_entrance']   all-colorless = True
  offer 1: ['true_grit', 'sword_boomerang', 'molten_fist']      all-colorless = False
```

A Colorless-only screen becomes an Ironclad screen on reroll. Trial's is the
quieter half: its pool is already the character pool, but the reroll mutates
the rare-pity counter (`CardCreationSource.Encounter`) where C#'s source is
`Other`, so `RollForRarity` takes the wrong branch (`CardFactory.cs:246-258`).
Note Trial's FIRST draw has the same defect independently: `trial.py:108`
calls `create_reward_cards(run, REGULAR, count=3)` with the default
`mutate_pity=True`.

**Exact fix shape** (now cheap, because this pass built the parts):

```python
group = CardRewardGroup(
    room_type=RoomType.MONSTER, count=3,
    pool=COLORLESS_POOL, odds_type=RarityOddsType.REGULAR,
    flags=(CardCreationFlags.NO_UPGRADE_ROLL
           | CardCreationFlags.NO_RARITY_MODIFICATION
           | CardCreationFlags.NO_CARD_POOL_MODIFICATIONS),   # BrainLeech.cs:56
)
group.populate(run)
```

i.e. the `_PotionCardRewardGroup` pattern — a group that CARRIES its options —
instead of `populated=True` over a pre-drawn list. For Trial the group needs
`pool` set to the character reward pool explicitly (or `create_reward_cards`
needs an explicit non-Encounter source), because `pool=None` is what currently
selects Encounter semantics.

**Liveness:** LIVE. Reachable by any run holding Driftwood that takes Brain
Leech's RIP or Trial's Nondescript Guilty. Card identity AND RNG order.
**Not in this pass's footprint** (`events/brain_leech.py`, `events/trial.py`).
Recommend queue items under `event/brain_leech` and `event/trial`.

### FIND-B — `brain_leech` uses `modify_hooks=False` for a flag that is not `NoModifyHooks` (LIVE, pre-existing)

*(the review's F3, re-derived and executed)*

`brain_leech.py:73-78` passes `modify_hooks=False` under a comment that reads
`CardCreationFlags.NoRarityModification|NoCardPoolModifications`. Those are
different flags. `modify_hooks=False` is `NO_MODIFY_HOOKS`, which suppresses
the entire `Hook.TryModifyCardRewardOptions[Late]` dispatch
(`CardFactory.cs:102`). `BrainLeech.cs:56` does **not** set `NoModifyHooks`,
and the `CardReward` ctor stamps `IsCardReward` on its options
(`CardReward.cs:114-115`), so in C# Silken Tress, Silver Crucible, the four egg
relics and Glitter all fire on that screen.

**Executed** (seed `F3PROBE`, Brain Leech RIP):

```
with silver_crucible: [('stratagem',0,None), ('dark_shackles',0,None), ('catastrophe',0,None)]  times_used = 0
with silken_tress   : [('stratagem',0,None), ('dark_shackles',0,None), ('catastrophe',0,None)]  is_used   = False
```

C# would give `+1` on all three and spend one Silver Crucible charge; would
enchant all three with Glam and burn Silken Tress's one-shot.

This is F1's mirror image — the same missing flag, under-firing instead of
over-firing — and is the strongest argument that the `extra_flags` /
`CardRewardGroup.flags` plumb built in this pass is the right systemic shape
rather than a one-event patch. **Same fix as FIND-A**: one `CardRewardGroup`
carrying `pool` + `odds_type` + `flags` fixes both findings at once.

**Liveness:** LIVE. `_REWARD_COUNT = 1` in the sim (`brain_leech.py:11`,
`IntVar RewardCount`), so it is one screen per RIP, not three. Not in
footprint.

### FIND-C — the second stale `_accept_offer` docstring reference

The review's F4. **FIXED this pass** — see F5 above. Filed here only so the
controller has it in the findings list; no action left.

### FIND-D (new) — `NoUpgradeRoll` is unmodelled at EVERY other non-combat creation site

Generalisation of F2. `ForNonCombatWithDefaultOdds`
(`CardCreationOptions.cs:139` and `:152`) and `ForNonCombatWithUniformOdds`
(`:160-162`) all OR `NoUpgradeRoll` onto their options, and
`CardFactory.cs:97-101` skips both the upgrade and its Rewards draw. The sim's
`create_reward_cards` now honours the flag, but only `the_future_of_potions`
passes it. Every other site is still taking `2 * count` draws where C# takes
`count`, and can still hand out upgraded cards C# would not:

`events/brain_leech.py:44` (ShareKnowledge, `BrainLeech.cs:181`),
`events/brain_leech.py:74` (Rip, `BrainLeech.cs:56`),
`events/trial.py:108` (`Trial.cs:181`),
`events/room_full_of_cheese.py:52`, `events/endless_conveyor.py:118`,
`events/infested_automaton.py:39`, `relics/lost_coffer.py:19`,
`relics/lead_paperweight.py:24`, `relics/orrery.py:30`,
`relics/dream_catcher.py:31`, `relics/glass_eye.py:45`.

**Caveat, and why I did not sweep them:** `Orrery` is named in
`CardCreationFlags.cs:20-24` as a site where the built-in reward upgrade *does*
apply, and `LastingCandy.cs:127` builds its options from the raw ctor (no
factory) so it takes the roll too. Each site needs its own derivation — a blind
sweep would create new divergences, which is precisely the failure this pass is
correcting. **Liveness: LIVE, class-wide, unrecorded.** Recommend a queue item
`reward/no_upgrade_roll_flag` covering the enumeration above.

### FIND-E (new, DORMANT) — `modify_hooks=False` also gates a hook C# never gates

`create_reward_cards` gates the `modify_card_reward_creation_options` loop on
`modify_hooks` (`rewards.py`). In C# that hook is dispatched
**unconditionally** from inside the per-card `CardFactory.CreateForReward`
(`CardFactory.cs:216`); only `Hook.TryModifyCardRewardOptions` is gated on
`NoModifyHooks` (`CardFactory.cs:102`).

**Dormant, and I enumerated why rather than assuming it.** Both callers that
pass `modify_hooks=False`:

- `events/brain_leech.py:76` — C# options set `NoCardPoolModifications`
  (`BrainLeech.cs:56`), so `DingyRug.cs:19-22` bails anyway.
- `relics/lasting_candy.py:63` — C# options set
  `NoModifyHooks | NoCardPoolModifications` **and** use a custom pool
  (`LastingCandy.cs:127`), so Dingy Rug bails at `:19-22` *and* at `:31`.

`grep -rn "def modify_card_reward_creation_options" sts2_rl/` returns exactly
two implementers: `relics/dingy_rug.py:25` and `relics/base.py` (the no-op
default). `prismatic_gem.py` is a documented single-character no-op;
`character_cards` and `big_game_hunter` are unported. So there is no listener
today for which the over-gating is observable. **If FIND-B is fixed by
switching Brain Leech off `modify_hooks=False`, this becomes moot for that
site.** Recorded so it is not re-derived from scratch later.

## Record-close proposals — the TWO entries the review requires

I did not edit `audit/records/**`. Both texts below are apply-verbatim.

### Entry 1 — `audit/records/event/the_future_of_potions.json:186-187`, the existing "offer's pool and filters" guard

**Verdict: stays `faithful`** (the review's option (ii): "left `faithful` with
the flag plumbed" — the flag is now plumbed). Its **reasoning** must be
replaced, because as written it was accidentally true. Append to the guard's
note:

> **R2 fix-pass update (2026-08-01, round 13).** This guard's original
> argument — "UNLIKE room_full_of_cheese, NoCardPoolModifications IS set here,
> so the sim's static pool is correct rather than merely
> currently-unobservable: the four ModifyCardRewardCreationOptions implementers
> that widen a pool (DingyRug.cs:19, PrismaticGem.cs:34, CharacterCards.cs:46,
> BigGameHunter.cs:40) all bail on that flag" — was **true of the C# but not of
> the sim**. The sim modelled `NO_CARD_POOL_MODIFICATIONS` at no call site
> (`grep NO_CARD_POOL_MODIFICATIONS sts2_rl/` = the enum member plus one read
> at `dingy_rug.py:31`), so Dingy Rug's operative gate here was its SECOND
> guard, `IS_CARD_REWARD` (`dingy_rug.py:33` / `DingyRug.cs:23-26`), and the
> pool was correct only because this screen set no flags at all. Setting
> `IsCardReward` alone (R2's first pass) therefore turned the guard into a gap:
> executed, a run holding `dingy_rug` was offered
> `['secret_technique','mangle','hand_of_greed']` — two Colorless — where the
> same-seed no-relic offer is `['tear_asunder','conflagration','mangle']`. The
> fix pass makes the guard's argument TRUE OF THE SIM: `create_reward_cards`
> takes `extra_flags` and `CardRewardGroup` carries a `flags` field
> (`rewards.py`), and `_PotionCardRewardGroup` declares
> `NO_UPGRADE_ROLL | NO_RARITY_MODIFICATION | NO_CARD_POOL_MODIFICATIONS`
> (`the_future_of_potions.py::_SCREEN_FLAGS`), the full set
> `ForNonCombatWithUniformOdds` (`CardCreationOptions.cs:160-162`) and
> `TheFutureOfPotions.cs:127` accumulate. Pinned by
> `test_the_future_of_potions_offer_is_not_widened_by_dingy_rug`, which asserts
> both no `COLORLESS_POOL` id in the offer AND exact equality with the
> same-seed no-relic offer (the pool widening is an RNG-order divergence, not
> only a card-identity one). **Reasoning replaced:** "the flag keeps them off"
> -> "the flag now EXISTS in the sim and keeps them off"; the enumeration of
> the four implementers is unchanged and still correct.

### Entry 2 — NEW guard on the same record: "the screen's `CardCreationFlags`"

**Verdict: `faithful`.** Two legs, both fixed and both pinned this round; the
controller may split them into two guards if the record's granularity prefers
that.

> **Guard: the flag set this screen's `CardCreationOptions` carry.**
> `CardCreationOptions.ForNonCombatWithUniformOdds` ORs `NoUpgradeRoll`
> (`CardCreationOptions.cs:160-162`), `TheFutureOfPotions.cs:127` ORs
> `NoRarityModification | NoCardPoolModifications`, and the `CardReward`
> constructor ORs `IsCardReward` onto `Options` and `RerollOptions`
> unconditionally (`CardReward.cs:114-115`); `WithFlags` is `Flags |= flag`
> (`CardCreationOptions.cs:212-216`), so the creation runs against all four.
> The sim's hand-rolled `create_reward_cards(...)` call carried NONE of them.
> Two consequences, both live, both fixed 2026-08-01 (round 13, R2 fix pass):
>
> (a) **`IsCardReward` absent.** Silken Tress (`silken_tress.py:36` /
> `SilkenTress.cs:53-56`) and Silver Crucible (`silver_crucible.py:35` /
> `SilverCrucible.cs:104-107`) decline when the flag is missing, so a player
> holding either got an un-enchanted / un-upgraded offer on this screen.
> Executed pre-fix (HEAD module, throwaway process): `silver_crucible` -> cards
> at `+1`, `times_used = 0`; `silken_tress` -> no enchantment,
> `is_used = False`. Post-fix: `+2` on every card (the late pass's `+1` inside
> `CardFactory.cs:102-105`, then `AfterGenerated`'s `+1` at
> `CardReward.cs:162`) with `times_used = 1`, and Glam attached with
> `is_used = True`. Pinned by
> `test_the_future_of_potions_offer_is_upgraded_twice_with_silver_crucible` and
> `test_the_future_of_potions_offer_enchants_with_silken_tress`. Note this is
> the SCREEN's bug, not the relics': both relic ports are byte-faithful.
>
> (b) **`NoUpgradeRoll` absent.** `CardFactory.cs:97-101` guards the entire
> `RollForUpgrade` call on the flag, and the `rng.NextFloat()` lives inside
> `RollForUpgrade` (`CardFactory.cs:290`), so C# takes 3 Rewards draws for this
> screen and never pre-upgrades. The sim took 6 and, in acts >= 1, could
> pre-upgrade a card that `AfterGenerated` then upgraded again — offering `+2`
> where C# offers `+1`. Executed pre-fix (act 2, seed `UPGRADEROLL`):
> `draws = 6, [('armaments',2),('havoc',2),('shrug_it_off',2)]`; post-fix
> `draws = 3`, all `+1`. Pinned by
> `test_the_future_of_potions_offer_takes_no_upgrade_roll`.
>
> **Reasoning replaced:** the record previously reasoned about this screen's
> creation ONLY through the pool guard at `:186-187`, whose enumeration covers
> the four `NoCardPoolModifications`-gated pool-wideners and no other
> flag-gated hook. It had no entry for `IsCardReward` (a different hook,
> `TryModifyCardRewardOptionsLate`) or for `NoUpgradeRoll` (not a hook at all,
> a `CardFactory` branch), so both divergences were invisible to it. R2's first
> pass ALSO asserted, wrongly, that the pool guard "is unaffected"; it was not
> — see Entry 1.

## Queue-annotation proposal (`GAP-QUEUE.md`)

Replace the side-effect sentence at the end of the
`event/the_future_of_potions/g15` entry filed in section 6 of the first pass
(everything from "Side-effect fix found in the same pass...") with:

> Side-effect fixes found in the same pass (not g15 itself): the old
> hand-rolled card draw carried NONE of the source's `CardCreationFlags`.
> Setting only `IsCardReward` fixed Silken Tress / Silver Crucible but
> **un-gated Dingy Rug** — its first guard, `NoCardPoolModifications`
> (`DingyRug.cs:19-22`), was modelled nowhere in the sim, so the offer briefly
> admitted Colorless cards `TheFutureOfPotions.cs:127` forbids. Closed properly
> by a flags passthrough: `create_reward_cards(extra_flags=...)` +
> `CardRewardGroup.flags` (`rewards.py`), with `_PotionCardRewardGroup`
> declaring `NO_UPGRADE_ROLL | NO_RARITY_MODIFICATION |
> NO_CARD_POOL_MODIFICATIONS` — the full set `ForNonCombatWithUniformOdds`
> (`CardCreationOptions.cs:160-162`) and `:127` accumulate. `NoUpgradeRoll` was
> a second live divergence at the same site: C# skips `RollForUpgrade` *and its
> draw* (`CardFactory.cs:97-101`, `:290`), so the screen took 6 Rewards draws
> instead of 3 and could offer `+2` cards in acts >= 1. All four legs pinned in
> `test/test_event_offer_screens.py`.

New queue items proposed (one paragraph each, terse style):

> - `event/brain_leech` + `event/trial`: their `CardReward`s are built as
>   `CardRewardGroup(cards=..., populated=True)` with no `pool`/`odds_type`, so
>   Driftwood's reroll redraws from the CHARACTER pool at Monster odds with
>   pity mutation. C# rerolls on `RerollOptions == Options`
>   (`CardReward.cs:114-115`), which for Brain Leech is
>   `ForNonCombatWithDefaultOdds(ColorlessCardPool)` (`BrainLeech.cs:56`).
>   Executed: `['panache','flash_of_steel','dramatic_entrance']` (all
>   Colorless) -> `['true_grit','sword_boomerang','molten_fist']` after one
>   reroll. Brain Leech additionally passes `modify_hooks=False` as a stand-in
>   for `NoRarityModification|NoCardPoolModifications` — a different flag —
>   which suppresses `TryModifyCardRewardOptions[Late]` entirely, so Silken
>   Tress / Silver Crucible / the eggs / Glitter never fire on a screen where
>   `BrainLeech.cs:56` lets them (executed: `times_used = 0`,
>   `is_used = False`, cards at `+0`). Trial's first draw also uses the default
>   `mutate_pity=True` where `Trial.cs:181`'s source is `Other`. One fix for
>   all three: give each group `pool` + `odds_type` + `flags` and call
>   `populate()`, the `_PotionCardRewardGroup` pattern R2 built.
>
> - `reward/no_upgrade_roll_flag`: every `ForNonCombatWith*` factory ORs
>   `NoUpgradeRoll` (`CardCreationOptions.cs:139/152/162`) and
>   `CardFactory.cs:97-101` skips `RollForUpgrade` **and its Rewards draw**
>   (`:290`) on it. `create_reward_cards` now honours the flag (R2, round 13)
>   but only `the_future_of_potions` passes it; 11 other sites (brain_leech x2,
>   trial, room_full_of_cheese, endless_conveyor, infested_automaton,
>   lost_coffer, lead_paperweight, orrery, dream_catcher, glass_eye) still take
>   `2*count` draws where C# takes `count` and can hand out upgraded cards C#
>   would not. NOT a blind sweep: `CardCreationFlags.cs:20-24` names Orrery as a
>   site where the roll DOES apply, and `LastingCandy.cs:127` uses the raw ctor,
>   so each site needs its own derivation.

## Tests — files, commands, counts

Changed: `test/test_event_offer_screens.py` only (4 tests added, 1
strengthened, 1 helper added).

```
py -m pytest test/test_event_offer_screens.py -q
  -> 23 passed          (19 before this pass)

py -m pytest test/test_event_offer_screens.py test/test_event_rng_streams.py \
  test/test_shared_events.py test/test_rewards.py test/test_event_reward_modifiers.py \
  test/test_reward_dispatch_choke_point.py test/test_reward_dispatch_and_relic_stubs.py \
  test/test_glass_eye_reward_set.py test/test_relic_tier1_gaps.py test/test_relics.py \
  test/test_event_live_tail.py test/test_event_gate_precision.py test/test_driver.py \
  test/test_darv.py test/test_tier1_last_five.py test/test_tier1_residue.py \
  test/test_rng_tripwire.py test/test_underdocks_hive_events.py test/test_run_rng_wiring.py -q
  -> 651 passed

py -m pytest test/ -k "event or reward or relic" -q
  -> 873 passed, 3052 deselected

py -m pytest test/test_conformance_runner.py test/test_conformance_map.py \
  test/test_conformance_player_state.py test/test_conformance_combat.py \
  test/test_conformance_pools.py test/test_conformance_relic_bag.py \
  test/test_conformance_rooms.py test/test_conformance_recording.py \
  test/test_conformance_save.py test/test_conformance_determinism.py test/test_run_env.py -q
  -> 107 passed, 6 xfailed
```

`test/test_conformance_floor_state.py` not run: known missing-fixture
environment gap per PROTOCOL.md.

No regressions. `git diff -- sts2_rl/rewards.py` shows only my hunks (the
staged content is R10's); `sts2_rl/relics/dingy_rug.py` is untouched; nothing
outside the declared footprint was edited.

## Protocol

No git index mutation. No `audit/**` edits. No revert-to-see-RED: the Dingy Rug
pin was written first and run RED in-tree before `rewards.py` changed; the
other three RED reproductions came from HEAD's module loaded into a throwaway
process. Files edited: `sts2_rl/events/the_future_of_potions.py`,
`sts2_rl/events/base.py`, `sts2_rl/rewards.py`,
`test/test_event_offer_screens.py`.

## Status (fix pass)

DONE_WITH_CONCERNS. The Dingy Rug regression is fixed at the right layer and
pinned; a second divergence at the same construction site (`NoUpgradeRoll`) was
found, fixed and pinned. **Concerns:** FIND-A / FIND-B (brain_leech, trial) and
FIND-D (the `NoUpgradeRoll` site sweep) are live, unrecorded and outside this
footprint — FIND-D in particular means the flag machinery built here is correct
but applied at exactly one of ~12 sites that need it.
