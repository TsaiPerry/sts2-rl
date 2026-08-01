# R2 review — `event/the_future_of_potions/g15`

**Verdict: NEEDS-FIXES.**

The assigned gap (the reroll surface) is genuinely fixed, well-designed and
correctly pinned; the premise corrections were honoured; the dispatch is
exactly-once. But the unpinned side-effect fix R2 was told to verify hardest
is **half right and half a new regression**: setting `is_card_reward=True`
also un-gated `DingyRug`, whose *operative* gate in this sim is that same
flag (`NO_CARD_POOL_MODIFICATIONS` is set nowhere in the tree). The event's
card offer now admits Colorless cards where `TheFutureOfPotions.cs:127`
forbids pool modification. Executed both ways below. R2's proposed record
text asserts the opposite ("the existing pool guard is unaffected"), so it
must not be applied as written.

Everything below was re-derived independently. Where I say "executed", I ran
it; the pre-fix behaviour was reproduced **out of tree** (HEAD's module and
HEAD's `offer_card_reward` loaded into a throwaway process via
`git show HEAD:…` + registry swap), never by reverting the shared worktree.

---

## 1. The reroll now reaches this screen — **CONFIRMED**

**Pre-fix RED is genuine, and stronger than "declined":** driving HEAD's
`the_future_of_potions` with a real `RunDriver`, Driftwood held, and a policy
that takes the reroll index whenever it is legal:

```
PRE-FIX with Driftwood held:
  kinds raised        : ['EVENT', 'SELECT_CARDS']
  REWARD_CARD raised  : False
  deck delta          : 1
  decline-everything deck delta: 0
```

`DecisionKind.REWARD_CARD` was never raised, so `own_actions`' reroll slot
(`driver.py:207-214`) could not exist. Structurally impossible, not merely
declined — R2's characterisation is exact. (The decline delta of 0 also
re-confirms the ADDENDUM's correction 1 against HEAD, independently of R6.)

**Post-fix, executed:**

```
offers shown : [['tear_asunder','conflagration','mangle'],
                ['conflagration','thrash','feed']]
reroll taken : True   deck +1   taken card upgrade_level = 1
taken card came from the SECOND offer: True
legal actions across the two asks: [0,1,2,3,4] then [0,1,2,3]   (one-shot)
```

**The regeneration matches C#.** `Reroll` (`CardReward.cs:322-332`) sets
`CanReroll=false` (`:324`), `_hasBeenRerolled=true` (`:329`), clears `_cards`
(`:330`) and re-enters `Populate` (`:331`); `Populate`'s `_cards.Count <= 0`
branch (`:156-164`) re-runs `CardFactory.CreateForReward` (`:158`) and
re-fires `AfterGenerated` (`:162`) — which is `UpgradeCardsInReward`
(`TheFutureOfPotions.cs:129`, body `:132-138`). For the 3-arg ctor
(`CardReward.cs:110-118`) `RerollOptions == Options` (`:114-115`), so the
reroll redraws from the *same* filtered pool.

R2's `_PotionCardRewardGroup.populate` override
(`the_future_of_potions.py:44-47`) is the right shape for that: `reroll()`
calls `self.populate(run)` (`rewards.py:544-548`), so Python dispatch re-runs
the upgrade on every redraw, and because the group carries
`pool=tuple(candidates)` + `odds_type=UNIFORM` (`:120-123`) the redraw uses
the same options, exactly like `RerollOptions`. This is a materially better
pattern than the two sibling sites' `populated=True` + pre-drawn list — see
finding **F2**, which that comparison uncovered.

Order is also right: C# runs the modify hooks inside `CreateForReward`
(`CardFactory.cs:104-107`) and fires `AfterGenerated` afterwards
(`CardReward.cs:162`); the sim runs the hook passes at the end of
`create_reward_cards` (`rewards.py:395-418`) and the subclass upgrades after
`super().populate()` returns. Same sequence.

Pael's Wing also lands now (`paels_wing.py:22-27` over `rewards.card_rewards`,
no room check — matching `PaelsWing.cs:73-81`), and `rewards.room` correctly
stays `None` (`RewardsSet.cs:106-110`), which is what keeps the room-gated
relics off it.

RNG accounting unchanged: 6 `rewards_rng` draws for one offer, pre- and
post-fix (3 `NextItem` + 3 `RollForUpgrade`). `mutate_pity` still resolves
to `False` (`rewards.py:539`, `pool is not None`), matching the old explicit
`mutate_pity=False`.

## 2. Exactly-once dispatch — **CONFIRMED**

A state-mutating spy relic implementing both `modify_combat_rewards` and
`modify_combat_rewards_late`, co-held through a full `RunDriver._run_event`:

```
modify_combat_rewards calls      : 1
modify_combat_rewards_late calls : 1
```

Not zero, not two. `_trade` calls `apply_reward_modifiers`
(`the_future_of_potions.py:135`), which sets `rewards.generated = True`
(`rewards.py:721`); `driver._offer_rewards`'s R10 backstop (`driver.py:484`)
then early-returns on the guard (`rewards.py:701-702`). Mirrors
`RewardsSet.Offer` → `GenerateWithoutOffering` (`RewardsSet.cs:159`) hitting
`_isGenerated` (`:127-130`). Bare `RunState` with no driver: also 1/1
(construction-site dispatch only). R2 added nothing to `rewards.py`; the
whole `rewards.py` hunk in the diff is R10's, correctly attributed.

`pending_rewards` has exactly one production drainer, `driver.py:564-574`
(`_run_event`); `grep -rn pending_rewards sts2_rl/` shows no other reader, and
`RunDriver` is the only production event runner (`driver.py:394, 429, 634,
649`). So no "set but never drained" path in real play. (Bare-`RunState` unit
tests *do* change semantics — the card is no longer added immediately — which
is why `test_shared_events.py` needed the driver; that is correct and the
sibling events already work this way.)

## 3. The two premise corrections — **HONOURED**

- **No second accept gate.** `_accept_offer` now has exactly one caller,
  `offer_potion` (`events/base.py:263`); the `purpose == "card_reward"`
  fall-through is dead. The card path asks once, at `REWARD_CARD`. That
  matches C#: `CardReward.OnSelect` (`CardReward.cs:183-311`) opens one screen
  (`:192`) over one combined index space — `_cards` then `cardRewardOption`
  (`:234`, `:244-249`) — and `CardRewardAlternative.Generate`
  (`CardRewardAlternative.cs:53-74`) puts Skip (`:56-59`, `CanSkip` default
  true at `CardReward.cs:95`, never overridden here) and REROLL (`:60-67`) on
  that same screen. There is no prior accept/decline screen anywhere in the
  `OfferCustom` path.
- **Not built on `select_cards`.** `SELECT_CARDS` no longer appears for this
  event (executed; also pinned by
  `test_the_future_of_potions_no_longer_uses_select_cards`).

## 4. THE SIDE-EFFECT FIX — **(a) yes, (b) yes, (c) NO, (d) three tests**

### (a) Is the C# claim right? **Yes.**

`TheFutureOfPotions.cs:128` uses the 3-arg `CardReward(options, 3, Owner)`
ctor, whose body unconditionally does
`Options = options.WithFlags(CardCreationFlags.IsCardReward)` and the same for
`RerollOptions` (`CardReward.cs:114-115`). The event's own flags are
`NoRarityModification | NoCardPoolModifications` (`:127`) — `NoModifyHooks`
is **not** among them, so `CardFactory.CreateForReward` does dispatch
`Hook.TryModifyCardRewardOptions` (`CardFactory.cs:104-107`). Silken Tress
(`SilkenTress.cs:53-56`) and Silver Crucible (`SilverCrucible.cs:104-107`)
therefore fire on this screen in C#.

### (b) Was the pre-fix sim wrong? **Yes — executed against HEAD.**

```
PRE-FIX offer (silken_tress   ): [('tear_asunder',1),('conflagration',1),('mangle',1)]  is_used=False
PRE-FIX offer (silver_crucible): [('tear_asunder',1),('conflagration',1),('mangle',1)]
POST-FIX     (silken_tress   ): is_used=True          (the one-shot engages)
POST-FIX     (silver_crucible): all three cards at upgrade_level 2
```

Silver Crucible's `+1` inside the late pass plus the event's `AfterGenerated`
`+1` gives `+2`, which is the C# order (`CardFactory.cs:104-107` then
`CardReward.cs:162`). Silken Tress spending its one-shot even when no offered
card can take Glam is also faithful — `SilkenTress.cs:72` returns true
unconditionally and `:75-83` burns the charge. Real, live, pre-existing
divergence; R2's diagnosis is correct and its half of the fix is correct.

### (c) Is the fix correct and complete? **NO — it introduces a new divergence.**

`create_reward_cards` builds its `CardCreationOptions` from exactly two
inputs — `is_card_reward` and `modify_hooks` (`rewards.py:339-348`).
**`NO_CARD_POOL_MODIFICATIONS` is never set at any call site in the tree**
(`grep -rn NO_CARD_POOL_MODIFICATIONS sts2_rl/` → the enum member
`rewards.py:114` and one *read* at `dingy_rug.py:31`). So Dingy Rug's real
gate in this sim is its second guard, `IS_CARD_REWARD` (`dingy_rug.py:33`,
porting `DingyRug.cs:23-26`) — the first guard (`DingyRug.cs:19-22`) is
inert here.

Consequence, executed:

```
PRE-FIX  offer (dingy_rug held) : ['tear_asunder','conflagration','mangle']   (== no-relic offer)
POST-FIX offer (dingy_rug held) : ['secret_technique','mangle','hand_of_greed']
   colorless leaked into the offer: ['secret_technique','hand_of_greed']
```

`secret_technique` and `hand_of_greed` are `COLORLESS_POOL` members. In C#
they cannot appear: `TheFutureOfPotions.cs:127` sets
`CardCreationFlags.NoCardPoolModifications` and `DingyRug.cs:19-22` returns
`options` untouched on it. Pre-fix the sim got this right by accident (no
flags at all ⇒ Dingy Rug bailed on the *second* guard); post-fix it gets it
wrong. This is not only a card-identity divergence, it is an **RNG-order**
divergence — the widened pool changes every `NextItem` draw on the Rewards
stream for the rest of the run — i.e. conformance-visible.

It also **flips a record guard that is currently `faithful` into a gap**:
`audit/records/event/the_future_of_potions.json:186-187` states *"UNLIKE
room_full_of_cheese, NoCardPoolModifications IS set here, so the sim's static
pool is correct rather than merely currently-unobservable: the four
ModifyCardRewardCreationOptions implementers that widen a pool (DingyRug.cs:19,
PrismaticGem.cs:34, CharacterCards.cs:46, BigGameHunter.cs:40) all bail on that
flag."* R2 quoted that very guard in its §7.4 and its record text says it "is
unaffected — it only concerns the FOUR pool-widening relics gated on
NoCardPoolModifications, a different flag." **That sentence is false as of
this change** and must not be applied. (`prismatic_gem.py` is a documented
single-character no-op and `character_cards`/`big_game_hunter` are unported,
so Dingy Rug is the only *executable* one — which is exactly why no test
caught it.)

This is the round-12 lesson landing again: 317 tests over the reward/event
surface pass with the divergence in place.

**Required fix (BLOCKED-ON-FOOTPRINT for R2, must be reported as such).** The
honest resolution needs `rewards.py`, which R2 may not touch: give
`create_reward_cards` a flags passthrough (e.g. `extra_flags:
CardCreationFlags = CardCreationFlags(0)`, OR-ed in at `rewards.py:344-347`)
and `CardRewardGroup` a `flags` field forwarded from `populate()`
(`rewards.py:530-542`); then `_PotionCardRewardGroup` declares
`NO_CARD_POOL_MODIFICATIONS | NO_RARITY_MODIFICATION`, matching
`TheFutureOfPotions.cs:127` literally. `NO_RARITY_MODIFICATION` has no reader
today and Uniform odds take no rarity roll, so it is documentation; only
`NO_CARD_POOL_MODIFICATIONS` is load-bearing. There is **no clean
within-footprint workaround** — I looked: the subclass cannot express the
flag because `create_reward_cards` constructs the options internally, and
suppressing the widening by passing `modify_hooks=False` would re-break
Silken Tress/Silver Crucible (that is precisely the sibling bug **F3**).

Until that lands, the correct disposition is either (i) hold R2 for one
`rewards.py` line-item, or (ii) land R2 and open the flag-plumb as its own
queue item with the pool guard demoted — but **not** land R2 with a record
that says the pool guard is unaffected.

### (d) What test would pin it — three, one of which is the missing negative

All three belong in `test/test_event_offer_screens.py` alongside R2's pins:

1. `test_the_future_of_potions_offer_is_not_widened_by_dingy_rug` — **the
   missing negative.** Run holding `dingy_rug`, drive the trade, assert no
   `COLORLESS_POOL` id appears in `event.pending_rewards.cards` **and** that
   the offered id list is identical to the same-seed no-relic offer. Cite
   `TheFutureOfPotions.cs:127` + `DingyRug.cs:19-22`. This test is RED today.
2. `test_the_future_of_potions_offer_is_upgraded_twice_with_silver_crucible`
   — assert every offered card is `upgrade_level == 2` (late-pass `+1` then
   `AfterGenerated` `+1`) and `relic.times_used == 1`. Cite
   `SilverCrucible.cs:104-107`/`:121-129`, `CardReward.cs:114-115`, `:162`.
   Would have been RED pre-fix (cards were `+1`).
3. `test_the_future_of_potions_offer_enchants_with_silken_tress` — pick a
   potion/rarity whose candidate set contains a Glam-enchantable card, assert
   the Glam enchantment landed and `relic.is_used` flipped. Cite
   `SilkenTress.cs:53-72`, `:75-83`. Note the seed I probed drew three
   non-enchantable Attacks, so this test must select its candidates
   deliberately; asserting only `is_used is True` is an acceptable weaker
   pin and is still RED pre-fix.

### Does it need its own record entry? **Yes — two.**

- A **new guard** on `audit/records/event/the_future_of_potions.json` for
  `IsCardReward` on this screen (`CardReward.cs:114-115`): verdict `faithful`
  once test 2 (and ideally 3) lands, close note naming the two relics and the
  fact that the sim's old hand-rolled `create_reward_cards` call omitted the
  flag. This is *this event's* record, not the relics' — the divergence was
  in the screen, not in `silken_tress.py`/`silver_crucible.py`, both of which
  are byte-faithful ports.
- The **existing** pool guard at `:186-187` must be updated: either demoted
  `faithful → gap` with the Dingy Rug finding, or left `faithful` with the
  flag plumbed. It cannot stay as-is with R2's change landed.

### Cross-check against R8 — **consistent; R8's `hefty_tablet` verdict is untouched**

R8's census (its §6.7 and the `test_reward_option_census_is_ten_relics_not_
four_or_seven` pin) says `silken_tress` and `silver_crucible` are exactly the
two reward-options implementers that decline on `IsCardReward`, while the egg
family gates on `NoHookUpgrades` and `glitter` has no flag check. R2's finding
is the same flag seen from the producing side: a screen that *should* set it
and didn't. The two are consistent, and R2's numbers agree with the ten-relic
census (`fresnel_lens`, `lava_lamp`, `wing_charm`, `glitter`, `_eggs`×4 were
firing at this event before and after — only the three `IS_CARD_REWARD`
readers changed behaviour).

**R8's `relic/hefty_tablet/AfterObtained` G2 LIVE verdict is unaffected.**
That verdict rests on `HeftyTablet.cs:29` setting `NoUpgradeRoll` and *not*
`IsCardReward`, so the egg relics (`NoHookUpgrades`-gated) fire on Hefty
Tablet's screen while `silken_tress`/`silver_crucible` correctly decline —
none of which touches `the_future_of_potions`. R2 changed one construction
site inside one event module; `hefty_tablet.py` is untouched and its screen
still never runs a reward-options pass at all. No interaction, no change to
R8's fix instructions (which explicitly require *not* setting `IsCardReward`
there — still correct).

## 5. Scope discipline — **correct, with one more residue than reported**

`Event.offer_card_reward` deletion is correct: `grep -rn offer_card_reward
sts2_rl/ test/` now returns only comments/docstrings, no call site. The
tombstone comment at `events/base.py:267-286` is inside R2's declared block.

`_accept_offer`'s docstring has **two** stale references, not one:

1. step 3's *"`offer_card_reward`'s sole caller is `the_future_of_potions.py:95`"*
   (`base.py:233`) — the method no longer exists. R2 flagged this.
2. step 3's closing parenthetical cites
   `test_the_future_of_potions_card_offer_already_declines_through_select_cards`
   (`base.py:244-245`) — **R2 renamed that test** to
   `test_the_future_of_potions_no_longer_uses_select_cards`. R2 did not flag
   this, and its §2d replacement text targets only "step 3's opening clause",
   so applying §2d verbatim can leave a dangling test name. The controller
   should replace the whole of step 3 (`base.py:232-247`), and the substitute
   should point at `test_drowning_beacon_declines_through_a_real_driver_with_
   no_explicit_selector` (the surviving empirical evidence for the potion
   leg) rather than the deleted card-leg claim.

The unused `from ..cards import Card` at `base.py:32` is confirmed dead (sole
occurrence in the file) — correctly identified, correctly left alone
(TYPE_CHECKING-only, inert, outside the block).

`sts2_rl/rewards.py` contains no R2 content — R2 respected the "NOT yours"
list there, which is worth saying explicitly because the diff file includes it.

## 6. Tests — sound, one under-pinned assertion

| test | pins C#? | survives deleting the mechanism? |
|---|---|---|
| `..._driftwood_reroll_reaches_the_event` | yes — reroll slot (`CardRewardAlternative.cs:60-67`) + re-upgrade on reroll (`CardReward.cs:156-164`, `:322-332`) | no — fails on `rerolled["done"]` if `apply_reward_modifiers` is dropped, and on `upgrade_level == 1` if the `populate` override is moved out to a one-shot upgrade in `_trade` |
| `..._not_rerollable_without_driftwood` | negative guard | it *would* pass with Driftwood deleted entirely — acceptable only because it is paired with the positive pin above |
| `..._no_longer_uses_select_cards` | migration shape, C# rationale documented | no |
| `..._declined_screen_adds_no_card` | `CanSkip` default (`CardReward.cs:95`) + `PotionCmd.Discard` happening either way (`TheFutureOfPotions.cs:126`) | no |
| `..._taken_screen_adds_one_upgraded_card` | `AfterGenerated` upgrade | no |

One weakness: the reroll pin asserts the deck grew and the taken card is
`+1`, but never that the *offer changed*. A `reroll()` that cleared the flag
without redrawing would pass it. Behaviour is in fact correct (my probe: the
two offers differ and the taken card comes from the second), so this is a
strengthening request, not a defect: add
`assert offers[0] != offers[1]` and `assert run.deck[-1].id in offers[1]`.
Cheap, and it makes "the reroll REGENERATES" — the brief's stated whole point
— actually pinned rather than inferred.

RED evidence is honestly reported, including the candid note that
`..._taken_screen_adds_one_upgraded_card` was green by coincidence pre-fix.
That is exactly the right disclosure.

Counts reproduced: `test/test_event_offer_screens.py` → **19 passed**; my own
sweep `test_event_offer_screens + test_event_rng_streams + test_shared_events
+ test_event_reward_modifiers + test_reward_dispatch_choke_point +
test_rewards + test_event_live_tail + test_event_gate_precision +
test_relics` → **317 passed**. The 2 `test_conformance_floor_state.py`
failures are the known missing-fixture gap; not counted.

## 7. Protocol — **clean**

- No `audit/**` edits by R2. `audit/records/event/the_future_of_potions.json`
  is staged-modified, but its content is R6's update ("THE REROLL-SURFACE GAP
  IS UNCHANGED AND REMAINS OPEN"), applied by the controller.
- No git index mutation attributable to R2. Its report files are untracked
  (`??`); the source/test edits show as staged because the controller stages
  the tree.
- Footprint respected. `git diff HEAD -- sts2_rl/driver.py sts2_rl/run.py`
  contains nothing matching `future_of_potions` or `offer_card_reward` —
  R2 did not touch either, as reported. `rewards.py` is R10-only.
- No revert-to-see-RED: R2 wrote the tests first. (I obtained pre-fix
  behaviour out-of-process, not by touching the tree.)

## 8. Record / queue text — **do not apply as written**

`g15` itself **CLOSES**: the reroll surface is built, reachable, one-shot,
re-upgrading, and pinned. The reasoning it replaces is stated accurately (the
round-12 "needs new capability, not a missing call" line, and R6's division
into a potion half and a reroll half). Citations spot-checked and all
correct: `RewardsCmd.cs:47-50`, `RewardsSet.cs:106-110`/`:136`,
`CardReward.cs:114-115`/`:156-164`/`:183-311`/`:322-332`,
`CardRewardAlternative.cs:53-74`, `Driftwood.cs:14-25`,
`SilkenTress.cs:53-56`, `SilverCrucible.cs:104-107`, `driver.py:207-214`,
`driver.py:519-542`.

Two mandatory edits before the controller applies it:

1. **Delete the final sentence** — *"The existing 'offer's pool and filters'
   guard above (verdict faithful) is unaffected — it only concerns the FOUR
   pool-widening relics gated on NoCardPoolModifications, a different flag."*
   — and replace with:

   > "**Caveat on the guard above (`:186-187`).** That guard's argument
   > assumes `NoCardPoolModifications` keeps the four pool-widening relics
   > off this screen. The sim does not model that flag anywhere
   > (`grep NO_CARD_POOL_MODIFICATIONS sts2_rl/` = one enum member, one read
   > in `dingy_rug.py:31`), so Dingy Rug's operative gate here is
   > `IS_CARD_REWARD` (`dingy_rug.py:33` / `DingyRug.cs:23-26`) — which this
   > change now sets. Executed: with `dingy_rug` held the offer became
   > `['secret_technique','mangle','hand_of_greed']` (two Colorless) where
   > pre-change it matched the no-relic offer exactly. C# forbids this
   > (`TheFutureOfPotions.cs:127` + `DingyRug.cs:19-22`), so the guard at
   > `:186-187` is **demoted `faithful` → `gap`** until
   > `create_reward_cards`/`CardRewardGroup` (`rewards.py:339-348`,
   > `:530-542`) grow a flags passthrough and `_PotionCardRewardGroup`
   > declares `NO_CARD_POOL_MODIFICATIONS`. Pre-existing correctness here was
   > accidental (no flags at all), so this is a newly-created divergence, not
   > a newly-exposed one."

2. The `IsCardReward` paragraph should be lifted out of the g15 close into
   its **own guard** on this record (see §4), because it is a distinct
   mechanism with a distinct verdict and needs its own tests; the g15 close
   should merely cross-reference it.

Queue text: R2's paragraph is accurate and terse for the reroll half, but the
side-effect sentence needs the second half — suggest appending:

> …fixed by routing the draw through `CardRewardGroup.populate()`, which
> always sets that flag — **but the same flag un-gated Dingy Rug**
> (`dingy_rug.py:33`; the sim never sets `NoCardPoolModifications`), so the
> event's offer now admits Colorless cards C# forbids
> (`TheFutureOfPotions.cs:127`). NEW live gap, same construction site:
> plumb `NO_CARD_POOL_MODIFICATIONS` through `create_reward_cards` /
> `CardRewardGroup` and declare it on `_PotionCardRewardGroup`.

---

## 9. My own findings (outrank the task)

**F1 — Dingy Rug pool widening at `the_future_of_potions`.** New LIVE gap
created by this change; full derivation and executed evidence in §4(c). This
is the blocking item.

**F2 — `brain_leech` and `trial` reroll from the WRONG POOL (pre-existing,
LIVE, unrecorded).** Both build their groups as
`CardRewardGroup(cards=…, populated=True)` with no `pool`/`odds_type`
(`brain_leech.py:79-80`, `trial.py:109-110`). `CardRewardGroup.reroll()`
→ `populate()` (`rewards.py:544-548`, `:530-542`) then redraws with
`pool=None` ⇒ the **character** pool at **Monster** odds with pity mutation.
C# rerolls on `RerollOptions`, which for the 3-arg ctor is the same options
(`CardReward.cs:115`) — Brain Leech's is
`ForNonCombatWithDefaultOdds(ColorlessCardPool)` (`BrainLeech.cs:56`).
Executed, Driftwood held, Rip taken:

```
offer 0: ['volley','panache','impatience']      all-colorless: True
offer 1: ['armaments','stampede','true_grit']   all-colorless: False   ← after reroll
```

A Colorless-only screen turns into an Ironclad screen on reroll. `trial.py`
has the same shape (its groups would reroll with `mutate_pity=True` where C#
uses a non-Encounter source). R2's `_PotionCardRewardGroup` — a group that
carries its own `pool` — is the correct pattern and is exactly what these two
sites need. Not in R2's footprint; recommend a queue item under
`event/brain_leech` and `event/trial`.

**F3 — `brain_leech` uses `modify_hooks=False` to stand in for
`NoCardPoolModifications` (pre-existing, LIVE).** `brain_leech.py:74-78`
passes `modify_hooks=False` under a comment reading
"`CardCreationFlags.NoRarityModification|NoCardPoolModifications`". Those are
different flags: `modify_hooks=False` maps to `NO_MODIFY_HOOKS`
(`rewards.py:346-347`), which suppresses the whole
`Hook.TryModifyCardRewardOptions[Late]` dispatch (`CardFactory.cs:104-107`).
`BrainLeech.cs:56` does **not** set `NoModifyHooks`, so in C# Silken Tress,
Silver Crucible, the eggs and Glitter all fire on Brain Leech's three
Colorless screens; in the sim none of them do. This is F1's mirror image —
the same missing flag, under-firing instead of over-firing — and is the
strongest argument that the flag plumb in §4(c) is the right systemic fix
rather than a one-event patch.

**F4 — two stale references in `_accept_offer`'s docstring, not one.** §5.

**F5 (minor) — `CardRewardAlternative.Generate` throws above two
alternatives** (`CardRewardAlternative.cs:69-72`), so C# cannot present
Skip + REROLL + SACRIFICE together, while `driver.py:207-214` happily offers
`n+1` and `n+2` at once. Pre-existing and not specific to this event (every
combat screen can reach it with Driftwood + Pael's Wing co-held); noting it
because this event is now a new site for it. Low value; no action proposed.

**F6 (minor) — strengthen the reroll pin** to assert the offer actually
changed. §6.

---

## Spec-compliance and code-quality verdicts

**Spec compliance: PARTIAL.** The reroll port is faithful and well-cited —
one screen, one decision, one-shot reroll, re-upgrade on redraw, same options
on reroll, `room=None`, correct hook order, unchanged RNG accounting. The
`IsCardReward` half is faithful. The omitted `NoCardPoolModifications` half is
not, and it regresses a previously-correct behaviour.

**Code quality: GOOD.** `_PotionCardRewardGroup` is a genuinely better
abstraction than the copy-paste alternative and than the two sibling sites'
approach; the comments cite the C# at the right granularity; the tombstone
comment where a deleted method used to live is the right call in a
concurrently-edited tree; footprint discipline was excellent (nothing in
`rewards.py`/`driver.py`/`run.py`); the report is candid about the coincidental
green test and the unpinned side effect. The one process failure is that a
change to a creation-options *flag* was made without enumerating the flag's
readers — `grep IS_CARD_REWARD sts2_rl/` returns three relics, and only two of
them were checked.

---

# Re-review (2026-08-01)

Scope: only the NEEDS-FIXES items. §1 (reroll) and §4(a)/(b) of the original
review stand unchanged. Everything below was re-executed against the current
tree; the pre-fix baseline was again taken from `git show HEAD:` loaded into a
throwaway process, never by reverting the worktree.

**Verdict: APPROVED**, with a pre-apply correction list in RR-7 that is
sed-level (line numbers in the apply-verbatim text), not re-work.

## RR-1. The Dingy Rug regression — **FIXED, and fixed in the right place**

Executed, current tree vs HEAD, same seed:

```
CURRENT  dingy_rug act0: (3 draws, [('tear_asunder',1),('feed',1),('conflagration',1)])
CURRENT  no relic  act0: (3 draws, [('tear_asunder',1),('feed',1),('conflagration',1)])
         colorless leaked: []                       <- byte-identical, zero leak
HEAD     dingy_rug act0: (6 draws, [('tear_asunder',1),('conflagration',1),('mangle',1)])
```

The offer with Dingy Rug held is now *identical* to the no-relic offer, which
is the correct assertion — the divergence was RNG-order as much as
card-identity. `test_the_future_of_potions_offer_is_not_widened_by_dingy_rug`
asserts both halves and its docstring records the executed RED
(`['secret_technique','mangle','hand_of_greed']`). Removing
`NO_CARD_POOL_MODIFICATIONS` from `_SCREEN_FLAGS` puts it straight back to
RED, so the test pins the mechanism rather than the symptom.

**Leaving `dingy_rug.py` untouched is correct**, and I want to be explicit
about why, because the opposite call would have been the classic symptom
patch. `dingy_rug.py:31-38` is a guard-for-guard transcription of
`DingyRug.cs:15-35` in source order — `NoCardPoolModifications` (`:19-22`),
`IsCardReward` (`:23-26`), already-contains-Colorless (`:27-30`) — with the
owner check and the `CustomCardPool != null` guard (`:31-34`) omitted under
documented deviations. Nothing about it was wrong. The defect was that the
*producing* side could not express a flag the *consuming* side already read,
so the consumer's first guard was structurally unreachable. Any edit to
`dingy_rug.py` would have hidden that, and would have left Prismatic Gem /
Character Cards / Big Game Hunter (unported or no-op today) to reintroduce it
the moment they land.

**The passthrough is complete, not a one-event patch.** I checked the shape,
not just the outcome:

- `create_reward_cards(..., extra_flags)` ORs onto the two flags it already
  derived (`rewards.py:376-380`), mirroring `WithFlags` = `Flags |= flag`
  (`CardCreationOptions.cs:212-216`, verified exact). The full set is written
  into `CardCreationOptions.flags`, so *every* listener that reads a flag off
  the options object gets the real set — not just the two with in-function
  behaviour.
- Both directions of the `modify_hooks` bool <-> `NO_MODIFY_HOOKS` flag are
  reconciled (`rewards.py:381-386`), so a caller spelling it either way gets
  the same behaviour. That was a real hazard and it was handled.
- `CardRewardGroup.flags` is forwarded from `populate()` (`rewards.py:611`),
  and `reroll()` goes through `self.populate(run)`, so the flags survive a
  Driftwood reroll too. Verified: the post-reroll draw still takes 1 draw/card.
- Blast radius is nil: `grep extra_flags sts2_rl/` shows one producer
  (`the_future_of_potions.py:166`) and one consumer. `CardRewardGroup.flags`
  defaults empty, and `CardCreationOptions.ForRoom` — the post-combat path —
  correctly sets none, so no existing screen changed.
- Honest about what is still inert: `NO_HOOK_UPGRADES`,
  `FORCE_RARITY_ODDS_CHANGE`, `NO_CARD_MODEL_MODIFICATIONS`,
  `NO_RARITY_MODIFICATION` have no ported reader (`grep` confirms), and the
  docstring says so.

Regression sweep: **480 passed** across `test_event_offer_screens /
test_event_rng_streams / test_shared_events / test_event_reward_modifiers /
test_reward_dispatch_choke_point / test_rewards / test_event_live_tail /
test_event_gate_precision / test_relics / test_relic_tier1_gaps /
test_rng_tripwire / test_driver / test_glass_eye_reward_set /
test_reward_dispatch_and_relic_stubs`. Conformance (10 files, excluding the
known-broken `floor_state`): **95 passed, 6 xfailed** — important, because the
6→3 draw change shifts the Rewards stream for any seed touching this event,
and parity did not move.

## RR-2. The newly-claimed `NoUpgradeRoll` divergence — **VERIFIED, real, correctly fixed**

This one I re-derived from scratch rather than checking the lane's arithmetic.

**Is the C# reading right? Yes, and it is exact.**
`ForNonCombatWithUniformOdds` does not merely allow the flag — it *ORs it in
itself*: `CardCreationOptions.cs:162` returns
`new CardCreationOptions(cardPools, Other, Uniform, filter).WithFlags(
CardCreationFlags.NoUpgradeRoll)`, and the sibling factories do the same at
`:139` and `:152` (grep-verified line-exact). `WithFlags` is `Flags |= flag`
(`:212-216`), so `TheFutureOfPotions.cs:127`'s
`.WithFlags(NoRarityModification | NoCardPoolModifications)` *adds to* it
rather than replacing it. Then in `CardFactory`:

```
 98: if (!options.Flags.HasFlag(CardCreationFlags.NoUpgradeRoll))
 99: {
100:     Rng rng = options.RngOverride ?? player.PlayerRng.Rewards;
101:     RollForUpgrade(player, cardModel, 0m, rng);
102: }
```

and the draw lives *inside* the guarded call —
`decimal num = (decimal)rng.NextFloat();` at `CardFactory.cs:290`. So the flag
suppresses the roll **and gives the draw back**. Confirmed independently.

**Was the pre-fix sim wrong in both halves? Yes — executed.** With a Rare
target the level half is invisible (rares get `odds = 0.0` regardless of act),
which is why my act-0 probes in the first review never showed it; it needs a
Common-target potion and act >= 1:

```
seed=OFFERSCREEN act=2  HEAD (6, [('sword_boomerang',2),('anger',1),('iron_wave',2)])
                        CUR  (3, [('sword_boomerang',1),('cinder',1),('anger',1)])
seed=UPG1        act=3  HEAD (6, [('perfected_strike',2),('cinder',1),('molten_fist',2)])
                        CUR  (3, [('perfected_strike',1),('pommel_strike',1),('cinder',1)])
seed=UPG2        act=3  HEAD (6, [('havoc',2),('bloodletting',2),('blood_wall',1)])
                        CUR  (3, [('havoc',1),('shrug_it_off',1),('blood_wall',1)])
```

Both halves are real: HEAD burns 6 Rewards draws where C# burns 3, and offers
`+2` cards where C# offers `+1`. Note the third column — the card *identities*
change too (`cinder`, `pommel_strike`, `shrug_it_off` appear), because
removing the interleaved upgrade draws re-phases the stream. That makes this a
conformance-visible divergence, not a cosmetic one, and it is exactly the
class of act-scaled drift that would poison an act-2/3 seed while looking
clean at act 0.

**Does the fix restore both? Yes.** 3 draws and `+1` at every act (0/1/2/3),
with and without relics.
`test_the_future_of_potions_offer_takes_no_upgrade_roll` asserts *both*
(`counter delta == 3` and `all(upgrade_level == 1)`) at act 2 with a
Common-target potion, so it cannot pass with the flag removed.

**Ruling: this is a genuine, well-found second divergence and the lane was
right to chase it.** It also vindicates the architectural choice in RR-1 — it
was found *because* the flag set was re-derived from the factory rather than
from the one visible `.WithFlags(...)` call, which is the correct method and
is now written down in `_SCREEN_FLAGS`' comment for the next reader.

## RR-3. `_accept_offer` docstring + dead import — **CONFIRMED, both**

Step 3 (`events/base.py:231-254`) is fully rewritten. Both stale references
are gone: no `offer_card_reward`-sole-caller line-cite, and the renamed test
citation is replaced by
`test_drowning_beacon_declines_through_a_real_driver_with_no_explicit_selector`
— the surviving empirical evidence for the potion leg, which is exactly the
substitution I asked for. The branch is now correctly labelled HISTORICAL/dead
with the reason it is kept rather than raising. `from ..cards import Card` is
gone from the TYPE_CHECKING block (`base.py:31-37`). Both items closed.

## RR-4. The three file-ready findings — **all accurately characterised and correctly scoped**

**FIND-A (`brain_leech`/`trial` reroll from the wrong options) — accurate.**
Independently executed (my own seed, one reroll on the Rip screen):
`['volley','panache','impatience']` (all Colorless) →
`['armaments','stampede','true_grit']` (all Ironclad). The lane's example uses
a different seed and shows the same thing. The C# claim is right:
`CardReward.cs:114-115` sets `RerollOptions = options.WithFlags(IsCardReward)`
for the 3-arg ctor, and `Populate` selects `RerollOptions` when
`_hasBeenRerolled` (`:148`), so the reroll draws from Brain Leech's Colorless
pool. Trial's `mutate_pity` sub-claim is also right — `Trial.cs` uses
`ForNonCombatWithDefaultOdds`, i.e. `CardCreationSource.Other`, so no pity
mutation. Scope: correctly filed against `event/brain_leech` +
`event/trial`, not against `rewards.py`. One citation fix, RR-7.

**FIND-B (`modify_hooks=False` is the wrong flag) — accurate, executed by me.**
Brain Leech's Rip with both relics held, driven end to end:
`silver_crucible.times_used == 0`, `silken_tress.is_used == False`. C# would
fire both: `BrainLeech.cs:56` sets `NoRarityModification |
NoCardPoolModifications` and *not* `NoModifyHooks`, so `CardFactory.cs:104`
dispatches, and `CardReward.cs:114-115` supplies `IsCardReward`. This is the
exact mirror of the bug fixed here — the same missing-flag class, under-firing
instead of over-firing — and with `extra_flags` now in place the fix is a
two-line change at that site. Correctly scoped as pre-existing and not R2's to
land.

**FIND-D (`NoUpgradeRoll` unmodelled elsewhere) — accurate, and the warning is
not hypothetical.** I enumerated the sites myself: excluding `rewards.py`'s
three internal (post-combat `ForRoom`) calls, `grep create_reward_cards(`
returns **11** non-combat sites, matching the lane's count. And the "blind
sweep would be wrong" warning is load-bearing, with **two** confirmed
exceptions:

- `CardCreationFlags.cs:20-24` documents Orrery as a site where the roll DOES
  apply (`:22`), and `Orrery.cs:22` proves it — it builds
  `new CardCreationOptions(...)` through the **raw constructor**, bypassing
  every `ForNonCombatWith*` factory, so it never gets the flag. `orrery.py:30`
  is literally one of the 11 grep hits, so an unqualified sweep would have
  broken it.
- `LastingCandy.cs:127` likewise uses the raw ctor
  (`.WithFlags(NoModifyHooks | NoCardPoolModifications)`) — also no
  `NoUpgradeRoll`.

The correct rule is therefore "every creation built through a
`ForNonCombatWith*` factory", not "every non-combat creation", and the finding
says so. One membership nit: the site list names `glass_eye` (which reaches
`create_reward_cards` via `CardRewardGroup.populate`, so it is a real site)
but omits `lasting_candy.py:61` — which is fine, because that one is
separately called out as a raw-ctor exception. Worth making explicit when
filing so nobody reads the omission as an oversight. I would also add: each
site needs its per-site *draw arithmetic* re-derived, not assumed — Brain
Leech's counter behaviour did not match a naive `2*count` prediction in my
probe, so whoever takes this must measure rather than compute.

## RR-5. The two record entries and three queue paragraphs — **true as written**

**Entry 1 (the pool guard at `:186-187`) — correct, and it carries my ruling.**
It stays `faithful`, which is option (ii) from my original §4(c) ("left
`faithful` with the flag plumbed") and is now *earned*: the offer with Dingy
Rug held is byte-identical to the no-relic offer. Crucially it does not paper
over the interim state — it states plainly that the original argument "was
true of the C# but not of the sim", that setting `IsCardReward` alone "turned
the guard into a gap", and quotes the executed leak. **Reasoning replaced** is
stated explicitly ("the flag keeps them off" -> "the flag now EXISTS in the sim
and keeps them off"), and the four-implementer enumeration is correctly
carried forward unchanged. This is the right disposition and it is honestly
told.

**Entry 2 (new guard, "the screen's `CardCreationFlags`") — correct.** Both
legs verified above; both pinned; the derivation of the four-flag set from
factory + `.WithFlags` + ctor is exactly right and is the reusable part.
**Reasoning replaced** is stated, and — the part I care most about — it
explicitly retracts the first pass's false claim ("R2's first pass ALSO
asserted, wrongly, that the pool guard 'is unaffected'; it was not"). A record
that records its own overturned reasoning is worth more than one that quietly
fixes it.

**Queue paragraphs — all three true.** The g15 replacement sentence, the
`event/brain_leech` + `event/trial` item, and the `reward/no_upgrade_roll_flag`
item all match what I executed, and the last carries the Orrery caveat inline
so it cannot be lost.

**One housekeeping hazard, please fix before applying:** the report's original
**§5 and §6 (lines 367-448) are superseded but not marked**, and §5 still
contains the sentence I ruled must be deleted — *"The existing 'offer's pool
and filters' guard above (verdict faithful) is unaffected…"* — plus a now-false
"I did not add a dedicated pinning test for this specific relic × event
interaction". Both are apply-verbatim-shaped text sitting above the real
proposals. Add a `**SUPERSEDED by the fix-pass sections below**` banner to each
so no future reader (or controller) applies the wrong block.

## RR-6. Tests — **23 pass; each new pin fails with its mechanism removed**

`py -m pytest test/test_event_offer_screens.py -q` → **23 passed** (was 19).

| new/changed pin | mechanism it removes-to-RED |
|---|---|
| `..._offer_is_not_widened_by_dingy_rug` | drop `NO_CARD_POOL_MODIFICATIONS` → Colorless leaks; the exact-equality half also catches any pool change that happens not to be Colorless |
| `..._offer_takes_no_upgrade_roll` | drop `NO_UPGRADE_ROLL` → `counter delta == 6`, and `+2` at act 2 |
| `..._offer_is_upgraded_twice_with_silver_crucible` | drop `is_card_reward` → `+1`, `times_used == 0` |
| `..._offer_enchants_with_silken_tress` | drop `is_card_reward` → `is_used False`, no enchantment |
| `..._driftwood_reroll_reaches_the_event` (strengthened) | `assert offers[0] != offers[1]` + `assert run.deck[-1].id in offers[1]` — a reroll that clears the flag without redrawing now fails, closing my F6 |

The `_potions_offer` helper is a good consolidation (bare `RunState`, reads
`pending_rewards` directly, no driver needed for the generation-side pins).
Two nits, neither blocking:

- `..._offer_enchants_with_silken_tress` asserts `enchantable` is non-empty,
  which depends on the specific cards this seed happens to draw — and that
  draw just moved once already (the `NoUpgradeRoll` fix re-phased the stream).
  The robust assertions are `tress.is_used` and the `isinstance` check on
  whatever *is* enchanted; the non-empty assertion is the fragile one.
- `..._not_rerollable_without_driftwood` remains a guard rather than a pin (it
  would pass with Driftwood deleted entirely). Acceptable only because the
  positive reroll pin sits next to it — unchanged from my original review.

## RR-7. Citation corrections required before applying the record text

Every substantive claim checked out; the line numbers added *this pass* for
`CardFactory.cs` drifted. These are `sed`-level and matter because the record
text is apply-verbatim into the audit corpus, where future audits re-derive
from the numbers:

| written | actual (grep-verified) | where |
|---|---|---|
| `CardFactory.cs:97-101` | **`:98-102`** (`if` at 98, `RollForUpgrade` at 101, `}` at 102) | `rewards.py` enum docstring, `create_reward_cards` docstring, the inline `roll_for_upgrade` comment, `the_future_of_potions.py:40`, the `..._takes_no_upgrade_roll` docstring ×2, report Entry 2(b), queue item |
| `CardFactory.cs:102` / `:102-105` | **`:104`** (block `:104-107`) | `rewards.py` enum docstring + `create_reward_cards` docstring, `the_future_of_potions.py:156-157`, the silver-crucible test docstring, report Entry 2(a) |
| `Trial.cs:181` | **`:183`** | FIND-A queue item |
| `CardCreationOptions.cs:160-162` | signature `:159`, `WithFlags` at `:162` — prefer `:159-162` or just `:162`, for consistency with the exact `:139/152/162` used elsewhere | several |

**Note the second row is a regression**: the pre-fix comment in
`the_future_of_potions.py` cited `CardFactory.cs:104` and was *correct*; this
pass changed it to `:102-105`.

Verified-exact and needing no change: `CardCreationOptions.cs:139/152/162`,
`:212-216`; `CardFactory.cs:290`; `CardCreationFlags.cs:20-24` (Orrery at
`:22`); `DingyRug.cs:19-22`/`:23-26`; `SilkenTress.cs:53-56`/`:72`/`:75-83`;
`SilverCrucible.cs:104-107`/`:121-129`;
`CardReward.cs:114-115`/`:148`/`:162`/`:156-164`/`:322-332`; `BrainLeech.cs:56`;
`LastingCandy.cs:127`; `Orrery.cs:22`.

Two wording nits: the enum docstring says "THREE of these are live" and then
names a fourth (`NO_CARD_POOL_MODIFICATIONS`) in the next sentence — it means
"three change behaviour inside this function, one is read by a listener", so
say that. And `dingy_rug.py`'s own docstring still claims the
`CustomCardPool != null` guard is modelled by "a caller that passes its own
pool" — a documented-but-unimplemented deviation. It is harmless now that the
flag is plumbed, but leave it alone rather than sweeping it: `glass_eye` and
`room_full_of_cheese` genuinely lack `NoCardPoolModifications` in C# and use
`CardPools` + filter rather than `CustomCardPool`, so Dingy Rug widening
*those* screens is correct.

## Re-review verdict

**APPROVED.** Both NEEDS-FIXES items are closed with executed evidence and
mechanism-level pins; the second divergence the lane found on its own is real,
correctly diagnosed and correctly fixed; the record and queue text is true,
names the reasoning it replaces, and — unusually and to its credit — records
its own overturned first-pass claim. Outstanding before the controller applies:
the RR-7 citation corrections and the RR-5 SUPERSEDED banners on report §5/§6.
