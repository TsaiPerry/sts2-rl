# Stream 4 report — event + enchantment content audits

Branch `audit-event`, worktree `C:\Users\Perry\Desktop\sts2-rl-event`.
Written 2026-07-26. Six commits on top of `8583546a`.

## Status

| kind | total | audited | invalid | gaps | unaudited |
|---|---|---|---|---|---|
| `enchantment` | 17 | **17** | 0 | 12 | **0** |
| `event` | 65 | **65** | 0 | 47 | **0** |

**Stream 4 is complete.** Both kinds are at `unaudited 0`.

`py tools/audit/harness.py validate` → 87 records, 0 invalid.
`py -m pytest test/ -q` → 2476 passed, 31 xfailed, unchanged at every commit
(audits add no executable code; the two probe modules under `tools/audit/` are
not imported by the suite).

Commits:

- `3abf27d9` audit(enchantment): all 17 units, 12 gaps
- `c3c9f8de` audit(event): batch 1/5 — 13 units, 8 gaps
- `53b54670` audit(event): batch 2/5 — 7 units, 5 gaps
- `4432d5e1` docs(audit): stream 4 report (first cut)
- `c61f34c3` audit(event): batch 3 — 9 units, 7 gaps
- `cb207419` audit(event): batch 4 — 13 units, 10 gaps
- (this commit) audit(event): batch 5 — the final 23 units, 17 gaps

**Both kinds are complete.** The enchantment kind reached `unaudited 0` at
`3abf27d9`; the event kind reaches it here.

### A note on how batch 5 was run

The final 23 units were audited by **three agents working concurrently** on
disjoint slices of the same branch (A: `potion_courier` … `the_future_of_potions`;
B: `the_lantern_key` … `vakuu`; C: `war_historian_repy` … `zen_weaver`). None of
them committed, edited this report, or edited the shared
`tools/audit/event_probes.py`; each wrote its own probe module and validated only
its own records by explicit path, and the batch was consolidated, validated and
committed once.

That worked, but it has one failure mode worth recording for the other streams:
**all three independently minted the id `EV-9`, and two minted `EV-10`, for five
different mechanisms.** Renumbering was mechanical here (the ids are prose, not
schema), but a concurrent stream should either partition the id space up front
or use provisional slice-local ids. The merge also revealed that two of the three
`EV-9`s were legs of *one* defect — see EV-9 below — which a sequential audit
would probably have recorded as a single finding from the start.

## Reproducible evidence

Five probe modules, following `tools/audit/dormancy_probes.py`'s pattern — every
number any record states is produced by one of them:

- `tools/audit/enchantment_probes.py` — `order`, `onplay-slot`, `replay`,
  `imbued`, `goopy`, `eternal`, `slither-rng`, `souls-reset`, `grants`
- `tools/audit/event_probes.py` — `lethal`, `maxhp`, `eventrng`, `heal`,
  `deckverbs`, and (batch 4) `kill`, `sortkey`, `relictrade`, `enchantstack`,
  `potiondiscard`, `cheese`, `reach`
- `tools/audit/event_probes_a.py` (batch 5, slice A) — `ancienthook`,
  `combatlayout`, `ancientdraws`, `punchhp`, `ransack`, `futurepotions`,
  `reflect`, `reacha`
- `tools/audit/event_probes_b.py` (batch 5, slice B) — `potionoffer`, `cape`,
  `trialoffer`, `draws`, `ids`, `rng5b`, `quest`, `gate`
- `tools/audit/event_probes_c.py` (batch 5, slice C) — `hollow`, `drawcount`,
  `nextitem`, `potionroll`, `enchsel`, `grabbag`, `wongo`, `repy`

The three batch-5 modules are separate because their authors ran concurrently,
not because the split means anything. A future session consolidating them should
also fix the `eventrng` regex — see the EV-3 correction below.

## New mechanisms found (all executed, all LIVE unless stated)

Each is one mechanism carried at every site with one verdict (rule 3).

### EG1 — `EnchantmentModel.OnPlay` / `AfterCardPlayed` have no sim slot

C# calls `Enchantment.OnPlay` as a **direct call inside the per-Replay loop**,
after the card's own `OnPlay` and before `Hook.AfterCardPlayed`
(`CardModel.cs:1904` loop, `:1931`, `:1937-1945`, `:1959`). The sim has no such
slot, so the three `OnPlay` ports and the three `AfterCardPlayed` ports hang off
`before_card_played` / `on_card_played`, both of which fire **once per card
play, outside the loop** (`combat.py:466`, `:514`).

Two legs, four executed witnesses (`py tools/audit/enchantment_probes.py
onplay-slot replay`):

| witness | sim | game |
|---|---|---|
| Corrupted Strike with Rupture 1 (position leg) | 10 | 9 |
| Corrupted + Throwing Axe, self-damage (replay leg) | 2 | 4 |
| Vigorous(8) + Throwing Axe, total damage | 28 | 20 |
| Goopy(1) + Throwing Axe, block gained | 10 | 11 |
| Swift(3) + Throwing Axe, cards drawn (**control**) | 3 | 3 |

**LIVE.** Every ingredient is ported and obtainable: Corrupted from the Symbiote
event, Vigorous from Stone of All Time, Goopy from Pael's Claw, Rupture from the
Ironclad card pool, Throwing Axe an Ancient relic. Glam is the negative control
— it rides the same hook but its only reader (`EnchantPlayCount`) is consumed
*before* the loop starts (`CardModel.cs:1895`), so the slot cannot be observed;
recorded as guard EG1-N on `enchantment/glam`.

### Imbued's extra hand guard

`Imbued.cs:20-25` auto-plays the card with **no pile check**, and
`CombatManager.cs:657-664` deliberately sinks it to the **bottom of the draw
pile** first. The sim requires `self.card in player.hand`
(`enchantments.py:261-267`) — the very outcome the C# pass exists to prevent.
Executed: over seeds 0-19 the sim's auto-play fires on **7 of 20** openings; the
game fires on 20 of 20. LIVE (Electric Shrymp is ported).

Distinct from `turn_structure` G8 (which owns the missing AutoPrePlay *phase*)
and G14 (the missing *pile pass*) — this is the hook **body** carrying an extra
condition. Both of those are recorded as blast radius on the same record.

### Slither rolls the wrong RNG stream

`Slither.cs:61` rolls `Rng.CombatEnergyCosts.NextInt(4)`; the sim rolls
`self.combat._rng.randrange(4)`. The correct accessor exists and is already used
by Snecko Oil (`combat_rng.py:23` → `potions.py:1049`). Parity-only observable,
which is an exercised sim mode.

### EV-1 — no run-level death prevention on event HP loss

`RunState.lose_hp` (`run.py:294-302`) subtracts directly. C# event damage goes
through `CreatureCmd.Damage`, whose `Hook.ShouldDie` / `AfterPreventingDeath`
pass runs over `RunState.IterateHookListeners`, **which yields the potion belt
outside combat** (`RunState.cs:545-596`). Fairy in a Bottle is ported
(`potions.py:1222-1250`) and in the pool (`potion_pools.py:49`) but returns early
when `self.combat is None` and is only registered by `CombatState`.

Executed (`py tools/audit/event_probes.py lethal`): a run at 5 HP holding a belt
Fairy that loses 15 HP ends **dead at hp=-10**; the game ends **alive at 24 HP**
with the Fairy consumed. **LIVE, and it ends runs.** 18 `lose_hp` sites.
Secondary: `lose_hp` does not clamp at 0, so the sim carries negative HP.

This is the single most consequential finding in the stream.

**Batch 4 widened EV-1's radius to a second verb.** `RunState.kill`
(`run.py:304-305`) sets `hp = 0`; `CreatureCmd.Kill(creature, force: false)`
runs `Hook.BeforeDeath` and then the same `ShouldDie` /
`AfterPreventingDeath` pass (`CreatureCmd.cs:439-448`, `:489-507`) — the
`force` argument exists precisely to bypass it and the event passes `false`.
Executed (`py tools/audit/event_probes.py kill`): a 20/20 run holding a belt
Fairy that deciphers Tablet of Truth three times (costs 3, 6, then 12 against
a max of 11, taking the kill branch) ends **dead at 1/0** with the Fairy still
in the belt; the game's pass has the Fairy answer and leaves the player alive
at 1/1. Same mechanism, same verdict (rule 3); the radius is now 18 `lose_hp`
sites **plus** `run.kill` (`event/tablet_of_truth`).

### EV-2 — `lose_max_hp` clamps instead of damaging

`CreatureCmd.LoseMaxHp` damages the overflow through the damage pipeline
(Unblockable|Unpowered) against the **unfloored** new max, and only then calls
`SetMaxHp(Math.Max(1m, newMaxHp))`. `run.lose_max_hp` (`run.py:316-321`) floors
first and clamps HP.

- leg 1 (LIVE): at 80/80 losing 10 max HP with the ported Tungsten Rod, sim 70,
  game 71.
- leg 2 (dormant): losing more max HP than you have — game kills the player,
  sim leaves them at 1/1. No ported event amount reaches it.

### EV-3 — events roll on the shared run RNG

C# events roll on the per-event `base.Rng`. `Event.event_rng` already exists
(`events/base.py:84-88`) and 6 modules branch on it; **28 of the 34 rolling
event modules roll only on `self.rng`** (`py tools/audit/event_probes.py
eventrng`). LIVE for the parity path the conformance harness grades.

**Correction (batch 5): treat that 28-of-34 as approximate.** The `eventrng`
probe's detector is a regex, and batch 5 found it wrong in both directions:

- **False positives.** It counts any `run.transform_card(` call as a roll, but a
  call passing `into=` is a fixed replacement that never enters the random
  branch. `wood_carvings` takes **0 draws on every path** and is not an EV-3
  site (`py tools/audit/event_probes_c.py drawcount`). It also misses
  `(self.event_rng if … else self.rng).shuffle(...)`, so `tanx` is filed as
  "rolls nothing" when it rolls correctly, and `potion_courier` is filed as
  "shared rng only" when its parity branch correctly uses `run.rewards_rng`.
- **False negatives.** It looks only for `self.rng.…`, so a roll delegated to a
  `RunState` helper is invisible: `wellspring`'s `run.random_potion()` is a real
  draw on the shared rng and was filed under "rolls nothing".

The mechanism is unaffected and every *record* states a per-path draw count
measured by `drawcount`/`draws`/`rng5b` rather than by the regex. It is the
report's roll-up figure that is soft. A one-line regex fix belongs to whoever
next owns `event_probes.py`.

Also note the report previously said **six** events have a parity RNG branch.
That undercounts: `nonupeipe`, `tinker_time` and `vakuu` have one too, so it is
at least nine. Every one of them was checked for draw *count*, not just stream —
the `orobas` lesson (below) is that a correct stream can still take the wrong
number of draws.

### EV-4 — `RewardsCmd.OfferCustom` force-granted

`OfferCustom` is a take-or-skip screen. The sim already models the contract —
`Event.resume_after_combat` *returns* potions "to surface as take-or-skip
offers" (`events/base.py:116-122`), which is how `battleworn_dummy` hands over
its Setting1 potion — so this is an internal inconsistency, not a missing
capability. The source distinguishes the two screens deliberately: BrainLeech's
SHARE_KNOWLEDGE sets `Cancelable = false` while its RIP branch uses plain
`OfferCustom`. Forced sites: `brain_leech` RIP, `drowning_beacon` BOTTLE,
`endless_conveyor` SUSPICIOUS_CONDIMENT.

### EV-5 — `StableShuffle`-and-take reduced to another primitive

`StableShuffle` is sort-then-Fisher-Yates, and the sort is the point: it makes
the pick independent of the pile's incidental order. `actmap.stable_shuffle`
(`actmap.py:193-201`) is the sim's faithful port and *is* used correctly by
`doll_room` and `fragrant_mushroom`. Sites that dropped it:
`doors_of_light_and_dark` LIGHT (`random.sample` — a different algorithm),
`battleworn_dummy` Setting2 (bare `shuffle`). `fake_merchant`'s stock roll is
`UnstableShuffle` in the source, so its shape is right and only EV-3 applies.

### EV-6 — `CreateForReward` replaced by `GetForCombat`

Several events call `CardFactory.CreateForReward(owner, n,
CardCreationOptions.ForNonCombatWithDefaultOdds(pool, filter))`; the sim uses
`random_pool_cards` (`cards/pool.py:136-161`), whose own docstring says it
"Mirrors CardFactory.GetForCombat (uniform, with replacement)" — the in-combat
generator behind Infernal Blade and Stoke. The sim **has** a faithful
`CreateForReward` port: `rewards.create_reward_cards` (`rewards.py:235-275`),
which does the rarity roll with escalation, the act-scaled upgrade draw, the
distinct constraint, the `GetUnlockedCards` reward pool and the per-player
Rewards stream — and `brain_leech` already uses it for this exact shape.

Three observables at every wrong site: no rarity odds (Rares appear at pool
frequency), no upgrade draw, and the wrong stream. Sites: `infested_automaton`
STUDY and TOUCH_CORE, `endless_conveyor` FRIED_EEL (which also gets the *pool*
wrong — see below).

### EV-7 — `StableShuffle`'s sort comparand is the UPPERCASE `ModelId`

New in batch 4, and the second half of the EV-5 story: EV-5 was about sites
that dropped `StableShuffle`'s sort; EV-7 is about the sites that kept it and
**sorted on the wrong string**.

`StableShuffle` sorts with the element's natural `IComparable` order before
Fisher-Yates (`ListExtensions.cs:22-31`). For an `AbstractModel` that is
`AbstractModel.CompareTo → Id.CompareTo` (`AbstractModel.cs:87-98`), i.e.
`string.Compare(ModelId.Entry, …, StringComparison.Ordinal)`
(`ModelId.cs:42-50`) over the **uppercase** slug. The sim's `stable_shuffle`
callers pass the **lowercase** sim id.

`'_'` is `0x5F`: above `'A'`–`'Z'` (`0x41`–`0x5A`) and below `'a'`–`'z'`
(`0x61`–`0x7A`). So for two ids sharing a prefix where one continues with
`'_'`, the two orders are **opposite** — and the sorted order is exactly what
fixes the permutation Fisher-Yates then produces from a given draw sequence.

Executed (`py tools/audit/event_probes.py sortkey`):

| id set | size | ids landing at a different index |
|---|---|---|
| sim relic ids | 258 | **8**, in 4 pairs: (`pen_nib`, `pendulum`), (`sea_glass`, `seal_of_gold`), (`wing_charm`, `winged_boots`), (`wongo_customer_appreciation_badge`, `wongos_mystery_ticket`) |
| Ironclad card ids | 85 | **2**: (`blood_wall`, `bloodletting`) |

Recorded on `event/relic_trader` (`events/relic_trader.py:39-40`, which sorts
the player's tradable relics with `key=lambda r: r.id`). The fix is a
`key=str.upper`-equivalent at each call site. LIVE for parity; invisible in
legacy mode. Distinct from EV-3, which is *which stream* — Relic Trader
carries both.

**Radius beyond this batch (not re-verdicted, rule 3):** `events/doll_room.py:53`
(`stable_shuffle(list(_DOLLS), self.rng)` — bare, so lowercase relic ids) and
`relics/fragrant_mushroom.py:31-36` (`key=lambda c: (c.id, c.upgrade_level)` —
lowercase card ids, and the second tuple element has no counterpart in
`ModelId.CompareTo` at all). `doll_room` is already audited; a follow-up
should fold EV-7 into its record. `fragrant_mushroom` belongs to the relic
stream and is flagged for them below.

### EV-8 — a hand-rolled card offer skips the reward-offer hooks

`CardFactory.CreateForReward`'s tail runs
`Hook.ModifyCardRewardCreationOptions` (`CardFactory.cs:215`) and
`Hook.TryModifyCardRewardOptions` + `Hook.AfterModifyingCardRewardOptions`
(`CardFactory.cs:262-266`) unless `NoModifyHooks` is set. The sim **has** the
offer-side hook — the egg relics implement `modify_card_reward_options`
(`relics/_eggs.py:38-41`), whose own docstring says the game applies it "so the
card is already upgraded when the player takes it (a recording's `TakeCard`
annotation shows the `+`)". An offer built by hand never reaches it.

Executed (`py tools/audit/event_probes.py cheese`): holding Molten Egg, Room
Full of Cheese's GORGE screen offers 8 Commons of which 4 are Attacks — the
sim shows **0** of the 4 upgraded, the game shows **4**. The *deck* outcome
coincides (`run.add_card` still runs the deck-entry hook, and the probe
confirms none of the taken Commons is upgradable a second time, so there is no
double-upgrade either), but the **screen** differs, which is what a player and
a replay both read. LIVE: `py tools/audit/event_probes.py reach` shows
`molten_egg` / `toxic_egg` / `frozen_egg` all ported **and** in the relic grab
bag, and the event gates only on act 0-1.

Related to but distinct from EV-6. EV-6's three observables are rarity odds,
the upgrade draw and the stream; here the odds are `Uniform` and
`NoUpgradeRoll` is already set by `ForNonCombatWithUniformOdds`
(`CardCreationOptions.cs:160-163`), so those two legs do not apply and the
missing hook pass is the defect. Sites: `room_full_of_cheese` GORGE.

**Batch 5 adds a second site with a *different* witness: `the_future_of_potions`
TRADE.** The egg leg is inert there — `reward.AfterGenerated` already upgrades
all three offers, and **0 of 85** Ironclad pool cards is upgradable twice
(`futurepotions`), so the source's egg-then-AfterGenerated pair cannot reach +2
either. Liveness comes from a non-egg implementer instead: `Glitter.cs:18-33`
enchants every Glam-eligible option with no flag gate. On the Attack branch
(seed 0 → breakthrough / anger / body_slam) all three satisfy
`Glam.CanEnchant`, so the game's screen shows **3** Glam cards and the sim's
shows **0**. Rule 6 is discharged: `glitter` is ported, is Ancient rarity
(correctly out of the grab bag), and **is in Nonupeipe's Ancient option pool**.
`silken_tress` and `silver_crucible` reach the same hook via
`CardReward.cs:114-115`, and `WingCharm.cs:36` even takes an `Rng.Niche` draw
the sim never takes.

### EV-9 — the potion generator: wrong stream, wrong tiering, wrong draw count

New in batch 5. Two slices found this independently from opposite ends and both
called it `EV-9`; they are legs of one defect, merged here.

`run.random_potion` (`run.py:513-520`) is a single `self.rng.choice` over every
potion class flagged `in_reward_pool`. The game's out-of-combat generator is
`PotionFactory.CreateRandomPotionOutOfCombat` → `CreateRandomPotion`
(`PotionFactory.cs:67-80`): a `NextFloat()` for the rarity tier (≤0.1 Rare,
≤0.35 Uncommon, else Common) and *then* a `NextItem` within that tier — two
draws, on the per-player `Rewards` stream. Executed (`potionroll`):

| | sim | game |
|---|---|---|
| draws per offered potion | 1 | 2 |
| stream | shared `run.rng` | `PlayerRng.Rewards` |
| P(rare) | **0.3333** | **0.10** |
| P(uncommon) | 0.3333 | 0.25 |
| P(common) | 0.3333 | 0.65 |

The 1-in-3 Rare rate is not a rounding difference — the sim's reward pool
happens to hold 48 classes split exactly 16/16/16, so dropping the tier roll
makes Rares **3.3× more common** than the game allows.

Two source sub-shapes, and the difference matters for the draw count:

- `new PotionReward(player)` → `Populate` → the full tiered generator: **2
  Rewards draws.** Site: `whispering_hollow` GOLD (two potions).
- a bare `PlayerRng.Rewards.NextItem(character pool ∪ shared pool)`: **1 draw,
  no tier** — the population is wrong but the odds question does not arise.
  Sites: `the_legends_were_true`, `wellspring` BOTTLE, `battleworn_dummy`
  Setting1, `endless_conveyor` SUSPICIOUS_CONDIMENT.

Every sim site draws on the shared rng. **The capability exists and one site
already uses it correctly** — `events/potion_courier.py:55` calls
`run.rewards_rng.next_item` — so, like EV-4 and EV-6, this is an internal
inconsistency rather than a missing port.

**Retroactive radius: two already-committed records.** `battleworn_dummy` and
`endless_conveyor` were both already `gap`, so no verdict changes; but
`endless_conveyor`'s guard labelled the defect "(EV-3)", which is wrong — the
source never touches `base.Rng` there. That label is corrected in place in this
commit.

### EV-10 — the transform screen is missing its `Quest` clause

New in batch 5. `CardSelectCmd.FromDeckForTransformation` filters
`c.Type != CardType.Quest && c.IsTransformable`
(`CardSelectCmd.cs:485-489`). `RunState.transformable_cards`
(`run.py:364-366`) returns `removable_cards()` and drops the Quest clause.

Executed (`quest`): three Quest cards are ported (`byrdonis_egg`,
`lantern_key`, `spoils_map`); a deck of `[strike, spoils_map, lantern_key]`
offers all three where the game offers only `strike`, and transforming
`spoils_map` **destroys it** into a Rare. Grant paths are
`the_legends_were_true.py:41`, `the_lantern_key.py:44`, `byrdonis_nest.py:45`.

Ten call sites: `aroma_of_chaos.py:25`, `endless_conveyor.py:96`,
`morphic_grove.py:41`, `symbiote.py:50`, `trial.py:97`,
`whispering_hollow.py:62`, `wood_carvings.py:38`, plus `relics/astrolabe.py:21`
and `relics/new_leaf.py:16` (**relic stream**).

The sharpest consequence is not the transform itself: `morphic_grove.py:30`'s
`IsAllowed` gates on `len(transformable_cards()) >= 2`, so a Quest card can make
the sim **offer a map node the game would not**.

Note the sim's comment is half right — for a card sitting in the deck
`IsTransformable` really does reduce to `IsRemovable` (`CardModel.cs:737-750`),
and `FromDeckForRemoval` genuinely has no Quest clause, so `removable_cards()`
is correct as written. It is reusing it for *transformation* that is wrong.

### EV-11 — the relic-pull ladder and its fallback

New in batch 5. **Dormant**, and recorded because the shape is load-bearing
elsewhere. `run.pull_relic_from_front` (`run.py:559-595`) scans the merged bag
and, on no match, pops the bag front at any rarity.
`RelicGrabBag.GetAvailableDeque` (`RelicGrabBag.cs:218-243`) instead walks
**Shop → Common → Uncommon → Rare → None**, and
`RelicFactory.PullNextRelicFromFront` (`RelicFactory.cs:13, :47`) falls back to
**Circlet**.

Executed (`grabbag`): with the Common deque emptied, BARGAIN_BIN hands out
`gremlin_horn` (Uncommon) with no ladder walk; with no Rare left, FEATURED_ITEM
hands out `gremlin_horn` where the game hands out Circlet — and **`circlet` is
not ported**. Dormant because the parity bag holds 122 relics (36 Rare plus
shop-legal), so no ported run empties a deque.

Radius: `luminous_choir`, `round_tea_party`, `relic_trader` and
`relics/wongos_mystery_ticket.py:47` all verdicted the pull faithful on the
*stream* question without examining the ladder.

### EV-12 — a Combat-layout event builds its encounter at room entry

New in batch 5. `EventRoom.EnterInternal` (`EventRoom.cs:67-71`) calls
`GenerateInternalCombatState` for **every** `EventLayoutType.Combat` event,
which runs `GenerateMonstersWithSlots` on the encounter Rng and then
`CreateCreature` → max-HP roll on `RunState.Rng.Niche` per monster
(`EventModel.cs:383-403`, `CombatState.cs:232-247`) — unconditionally, before
any option is chosen. `EnterCombatWithoutExitingEvent` then *reuses* that state
(`ShouldCreateCombat = LayoutType != Combat`). The sim only records
`pending_encounter` and builds monsters later, when the driver runs the fight.

Executed (`combatlayout`): entering Punch-Off consumes **0 Niche draws in the
sim on both the NAB and the FIGHT path**, where the game consumes **2**, plus 2
encounter-Rng `NextInt(2,10)` draws. LIVE for parity, invisible in legacy mode.

Three Combat-layout events exist: `PunchOff.cs:33`, `TheLanternKey.cs:15`, and
the unported `TheArchitect.cs:52`. **The divergence is wider at
`the_lantern_key`**: both of Punch-Off's options end in a fight, so the sim
eventually spends the draws either way, but `the_lantern_key`'s RETURN_THE_KEY
option ends the event with no combat — the game has still paid for a Mysterious
Knight it never fights.

This mechanism also **overturned a waiver written in the same batch.**
`the_lantern_key`'s first cut waived `LayoutType` as presentation, reasoning
that it "constrains how the room system builds the combat, not what the combat
is". That is observationally false in parity mode: the layout decides *when* the
encounter is built, and building it costs RNG. The hook now carries EV-12's
verdict, and the record says so explicitly.

### Unit-level gaps

- **`endless_conveyor` FRIED_EEL** rolls the CHARACTER pool where C# rolls the
  COLORLESS pool. The code comment claiming no colourless pool exists is false —
  `brain_leech` already passes `COLORLESS_POOL` for the same shape. LIVE (the
  event needs 120 gold; FRIED_EEL is weight 3 of a base 15).
- **`fake_merchant` price.** `MerchantRelicEntry.CalcCost` is
  `round(MerchantCost * Shops.NextFloat(0.85, 1.15))` per stocked entry, and
  every fake relic declares `MerchantCost => 50`. `FakeMerchant.relicCost = 50`
  is a **dead constant** (verified: `grep -rn relicCost src` returns only its own
  declaration) and is what the sim charges. Wrong price, wrong affordability
  lock, six missing Shops-stream draws. LIVE.
- **`crystal_sphere`** is a deferred stub forced `is_allowed = False`. Under
  rule 1 an unported side is a gap, and the gate (act 2+, 100 gold) is ordinary
  run state, so this is LIVE — the sim can never present a node the game can.
  The two effects *outside* the un-portable minigame (a 50 + `NextInt(1,50)`
  gold loss, and an added Debt curse) are portable on their own, so the deferral
  is wider than strictly required. Keeping the id in the pool is correct and
  costs no stream draws.
- **`brain_leech` RIP** force-takes a card (EV-4's first site).
- **`orobas` skips an RNG draw on the locked path.** `Orobas.cs:54-56` puts the
  null-onChosen `OPTION_POOL_3_LOCKED` option *into* the list and then calls
  `NextItem(OptionPool3)` unconditionally, so the game takes a draw over a
  one-element list. `events/orobas.py:76-81` branches instead and never calls
  `pick`, so the sim takes **one fewer draw** off the event stream. The offered
  options are identical, so this is invisible in legacy mode and desyncs the
  event stream in parity mode. LIVE for parity — the both-gates-fail state is
  ordinary run state.
- **`neow`'s run-modifier branch is unported** (`Neow.cs:116-129` plus
  `OnModifierOptionSelected` and the `InitialDescription` swap). Under rule 1
  that is a gap, not a waiver. **Dormant**, with the concrete unported thing
  named: `ModifierModel` has no sim port at all, so `RunState.Modifiers` is
  permanently empty and Neow always takes the relic branch.
- **`relic_trader` hides options the game would offer when the grab bag runs
  dry.** `RelicTrader.cs:79-90` gates each trade row on `OwnedRelics.Count`
  alone and `Trade` then indexes `NewRelics` at the same position;
  `events/relic_trader.py:51-53` gates on
  `min(len(self._owned), len(self._new))`, and its pull loop breaks on a
  `None` (`:44-46`). **Dormant**, trigger named: fewer than 3 relics left in
  the grab bag on entry. `IsAllowed` only guarantees the player *owns* 5
  tradables, so nothing structurally prevents it, but exhausting a 200+ relic
  bag inside one run does not happen with ported content. Recorded so the
  sim's defensive `min` is not mistaken for the source's shape (the game would
  offer the row and then dereference a null).
- **`tablet_of_truth` short-circuits its page flow on death.**
  `events/tablet_of_truth.py:51` adds `self.run.is_dead or` to the finish
  test; C# increments and presents the next DECIPHER page even after
  `CreatureCmd.Kill` (`TabletOfTruth.cs:62-73`). Recorded as a
  **deliberate-divergence**, not a gap: the run is over either way and Kill's
  own tail tears it down (`CreatureCmd.cs:450-464`), so the page the source
  builds is never read. The reachable trigger is a low-max-HP run (20/20:
  costs 3 then 6 leave max HP 11, and the third cost of 12 takes the kill
  branch) and it is executed by the `kill` probe.
- **`round_tea_party`'s `ThatWontSaveToChoiceHistory` is unmodelled.**
  Same shape as `morphic_grove`'s `GoldLossType.Stolen` and given the same
  **deliberate-divergence** verdict: the sim has no choice-history subsystem,
  grep shows only three call sites in the whole source (`RoundTeaParty.cs:50`,
  `TheArchitect.cs:334`, `:339`), all second-page "continue" buttons, and no
  gameplay reader. A future history/telemetry port would need it.
- **`hungry_for_mushrooms`**: BigMushroom's +20 Max HP pickup effect lives on
  the **event** instead of the relic, while its twin FragrantMushroom does it
  correctly via `after_obtained`. **Dormant** — verified by grep that the event
  is Big Mushroom's only grant path today. Named trigger: any second grant path
  (relic reward, shop, grab-bag pull) silently drops the 20 Max HP. The relic
  docstring justifies the placement with a false claim ("RunState has no
  run-level AfterObtained dispatch" — `run.py:552` is exactly that dispatch).

### Batch-5 unit-level gaps

- **`war_historian_repy` is NOT `crystal_sphere`'s shape** — and this is the one
  place a documented lead was wrong. `WarHistorianRepy.cs:30-33` is a bare
  `return false` **in the source**, so the sim's forced `is_allowed = False` is
  exactly faithful. The event is *injected*, not pooled: `LanternKey.cs:21-28`
  narrows every "?" node in act index 2 to `RoomType.Event` and
  `LanternKey.cs:30-36` swaps in Repy. Executed (`repy`): `lantern_key` is
  ported and granted, but there are **0** `ModifyNextEvent` implementations
  anywhere in `sts2_rl/`, and `LanternKeyCard` (`cards/event_cards.py:366-387`)
  does not override `modify_unknown_map_point_room_types` **even though the sim
  dispatches that hook** (`run.py:1045-1049`; `relics/golden_compass.py:42`
  implements it). LIVE. Body leg: the `history_course` relic is unported;
  everything else in the body is expressible with existing verbs.
- **`unrest_site`'s gate is decimal-vs-float.** `UnrestSite.cs:26-29` is
  `(decimal)CurrentHp <= (decimal)MaxHp * 0.70m` — exact base-10 arithmetic;
  `events/unrest_site.py:30` is binary float. Executed (`gate`): sweeping every
  `(max_hp, hp)` with `max_hp <= 400` gives **7 disagreements**, all sim-False /
  game-True at exactly 70% — 90/63, 170/119, 180/126, 330/231, 340/238, 350/245,
  360/252. LIVE (90 max HP is one relic above the Ironclad's 80), and because it
  is an `IsAllowed`, it removes the node from the pool and shifts every later
  event pick.
- **`trial` NONDESCRIPT_GUILTY is unmodelled.** `Trial.cs:177-187` offers two
  `CardReward(ForNonCombatWithDefaultOdds([Character.CardPool]), 3)` screens via
  `OfferCustom`; `events/trial.py:90-93` adds Doubt and nothing else. Executed:
  **0 cards offered vs 6.** Wider than EV-4 or EV-6 — screens, cards and draws
  are all absent — though `rewards.create_reward_cards` and
  `pending_reward_extras` both exist.
- **`the_legends_were_true` uses the wrong potion pool.** It uniquely calls
  `potions.random_potion` (the `CreateRandomPotionInCombat` port) where its three
  sibling sites call `run.random_potion()`. Executed: **45 ids vs 48** — the
  three it can never offer are `fruit_juice`, `regen_potion` and
  `fairy_in_a_bottle`, the potion EV-1 turns on.
- **`punch_off`'s `StartingHpReduction` hits the wrong value in the wrong slot.**
  `PunchConstruct.cs:71-78` spends it as
  `SetCurrentHpInternal(Math.Max(1, CurrentHp - reduction))` — **current HP
  only**, MaxHp untouched, *after* the Niche max-HP roll.
  `events/punch_off.py:26-28` subtracts it from `max_hp` inside
  `create_monsters`. Executed (`punchhp`): **legacy** → constructs come out
  `(50,50)` and `(49,49)` where the game has max 55 / current 46-53, i.e. **zero
  damaged constructs vs two**; **parity** → `_assign_parity_monster_hp` then
  overwrites with `creature.hp = creature.max_hp = hp` and the reduction is
  **erased entirely** (both `(55,55)`). The sim already has the right slot —
  `Monster.adjust_hp_after_added` (`monsters/base.py:69-77`) — which
  `PunchConstruct` does not implement.
- **`welcome_to_wongos` never grants the badge** (`WelcomeToWongos.cs:111-131`
  vs 0 grant sites). **Dormant**, with the blocker named: no port of
  `SaveManager.Progress`. A real profile at 1968+ points earns it on the next
  purchase, so a gap and not a waiver.
- **`vakuu` puts Distinguished Cape's −9 Max HP in the wrong place** —
  `DistinguishedCape.cs:29-31` has it in the relic's `AfterObtained`;
  `events/vakuu.py:52-63` puts it on the event option and
  `relics/distinguished_cape.py:21-26` omits it. Executed:
  `run.add_relic('distinguished_cape')` at 80/80 leaves the sim at 80/80 where
  the game gives 71/71; the Vakuu path itself coincides at 71/71. **Dormant** —
  the relic is Ancient rarity, out of the grab bag, and Vakuu is its only grant
  path. Same shape as the `hungry_for_mushrooms` / Big Mushroom finding.

## Blast radius of existing seam findings (rule 3 — recorded, not re-verdicted)

| seam finding | units in radius | note |
|---|---|---|
| `turn_structure` step 38a (rest-site heal) | **`event/dense_vegetation` only** | **100% of the event-side radius.** Executed (`event_probes.py heal`): it is the only event healing through the rest-site verb; the other 10 `run.heal` sites are plain `CreatureCmd.Heal`, which dispatches **no hooks in C# either** (`CreatureCmd.cs:691-703`), so they are faithful. |
| `turn_structure` G14 (bottom-of-draw-pile pass) | `enchantment/imbued` | **100% of G14's radius** — Imbued is the only `ShouldStartAtBottomOfDrawPile` implementer in the entire game source. |
| `turn_structure` G8 (missing AutoPrePlay phase) | `enchantment/imbued` | G8 already names `enchantments.py:261-267`. |
| `creature_card_cmds` G3 (deck transforms bypass deck-entry hooks) | 7 events: `aroma_of_chaos`, `endless_conveyor`, `morphic_grove`, `symbiote`, `trial`, `whispering_hollow`, `wood_carvings` | 24 events use `add_card`, which *does* run the hook. |
| `creature_card_cmds` step 52 (downgrade skips `ModifyCard`) | `enchantment/{souls, steady, goopy, tezcataras_ember}` | Tezcatara's Ember is the widest case — the only enchantment that changes a card's **cost**. |
| `creature_card_cmds` G1 (block dispatch gated on `is_powered_attack`) | `enchantment/{nimble, goopy}` | The two ported `EnchantBlockAdditive` implementers — the whole content-side radius of G1's enchantment clause. |
| `damage_pipeline` N3 / `creature_card_cmds` step 13(b) (enchantment pre-pass) | `enchantment/{corrupted, instinct}` | See the cross-record note below. |
| `hook_dispatch` G4 (per-Replay `CardPlay`) | `enchantment/{corrupted, goopy, swift, vigorous}` | G4's once-per-play shape is what makes EG1's replay leg observable. |

### Events that heal (step 38a's candidate set)

Rest-site verb (**step 38a applies**): `dense_vegetation`.
Plain `CreatureCmd.Heal` (faithful — no hooks on either side): `abyssal_baths`,
`endless_conveyor`, `round_tea_party`, `sapphire_seed`, `spiraling_whirlpool`,
`spirit_grafter`, `tablet_of_truth`, `trial`, `unrest_site`, plus the shared
Ancient full heal in `events/ancient.py:31`. Batch 4 audited five of those
(`round_tea_party`, `sapphire_seed`, `spiraling_whirlpool`, `spirit_grafter`,
`tablet_of_truth`) and confirmed each against `CreatureCmd.cs:691-703` — all
faithful, none in step 38a's radius.

### Batch-4 additions to the shared-mechanism site lists

| mechanism | new sites from batch 4 |
|---|---|
| EV-1 (no run-level death prevention) | `room_full_of_cheese` SEARCH, `round_tea_party` CONTINUE_FIGHT, `slippery_bridge` HOLD_ON (unbounded — the worst case), `spirit_grafter` REJECTION, `stone_of_all_time` PUSH, `sunken_statue` DIVE_INTO_WATER, **plus the second verb** `tablet_of_truth` DECIPHER via `run.kill` |
| EV-2 (`lose_max_hp` clamps) | `tablet_of_truth` DECIPHER (leg 2 stays dormant here — the source's own guard substitutes `MaxHp - 1`, so it never asks for more max HP than the player has) |
| EV-3 (shared run RNG) | `relic_trader` (owned-relic shuffle only), `room_full_of_cheese` GORGE, `slippery_bridge` (one draw per page), `stone_of_all_time` (potion pick + two throwaway `NextInt(100)`), `sunken_statue`, `sunken_treasury` (two draws), `symbiote` KILL_WITH_FIRE |
| EV-7 (uppercase sort key) | `relic_trader` |
| EV-8 (hand-rolled offer skips reward hooks) | `room_full_of_cheese` GORGE |
| `creature_card_cmds` G3 | `symbiote` (already listed) |

Four batch-4 units roll **nothing at all** and are outside EV-3 entirely —
`self_help_book`, `spiraling_whirlpool`, `spirit_grafter` and (for its two
non-random branches) `sapphire_seed`. `tablet_of_truth` is one of the six with
a parity branch and its branch is **clean**: correct stream, and the draw
count matches on every arm (zero on the whole-deck upgrade, zero on the
empty-list arm, zero on the kill arm, exactly one otherwise) — the check the
`orobas` lesson asked for.

### Events that transform or add cards (G3's candidate set)

`transform_card` (7, in G3's radius): `aroma_of_chaos`, `endless_conveyor`,
`morphic_grove`, `symbiote`, `trial`, `whispering_hollow`, `wood_carvings`.
`add_card` (24, **not** in G3's radius — `run.add_card` runs the hook):
`amalgamator`, `brain_leech`, `bugslayer`, `byrdonis_nest`, `endless_conveyor`,
`field_of_man_sized_holes`, `grave_of_the_forgotten`, `infested_automaton`,
`lost_wisp`, `luminous_choir`, `punch_off`, `reflections`, `room_full_of_cheese`,
`spirit_grafter`, `sunken_treasury`, `the_future_of_potions`,
`the_legends_were_true`, `this_or_that`, `tinker_time`, `trash_heap`, `trial`,
`unrest_site`, `wellspring`, `zen_weaver`.
`remove_cards` (7): `amalgamator`, `doors_of_light_and_dark`,
`field_of_man_sized_holes`, `luminous_choir`, `slippery_bridge`, `wellspring`,
`zen_weaver`.

## Cross-record disagreements (rule 3 signals)

**1. `creature_card_cmds` step 52 — its witness self-heals.** Step 52's LIVE
evidence is "attach Souls to Discovery, `upgrade()` then `downgrade()`, observe
`exhausts=True`". Executed here (`enchantment_probes.py souls-reset`):
`exhausts` is `False` after attach, `True` after upgrade+downgrade — **and
`False` again after the next combat's `Enchantment.reset()`**
(`enchantments.py:214-216`, called from `combat.py:131` for every deck card).
The sim's divergence window is bounded by the next combat setup. That keeps
step 52 LIVE on its **in-combat** leg (Dampen, `powers.py:3149-3183`) but not on
the **out-of-combat** leg its rationale also cites
(`events/reflections.py:36-41`), which self-heals before the card is next
played. **Recommend step 52's owner narrow the liveness argument to the
in-combat downgrade.** No verdict change.

**2. `damage_pipeline` N3 needs a sharper witness.** N3 mentions the enchantment
pre-pass only in passing ("This includes card-enchantment bonuses…") and rests
its LIVE label on the Shrink × Vulnerable **float** case. The enchantment leg is
a pure **phase-order** difference that needs no float at all:

- Instinct(×2) + Strength(+3) on a base-6 Strike: **sim 18, game 15**
- Corrupted(×1.5) + Strength(+3): **sim 13, game 12**
- Sharp(+2) + Strength(+3) (**additive-only control**): 11 in both

C# folds `(base + enchAdd) * enchMult` *before* either listener loop
(`Hook.cs:1490-1500`), then adds Strength; the sim pools the enchantment's
factor into the same product as everyone else's. The additive-only control
matching is what isolates the multiplicative phase as the cause. **Recommend
folding this witness into N3.** No verdict change — N3 and
`creature_card_cmds` step 13(b) already carry `gap`.

**3. Self-correction — `luminous_choir`'s EV-3 entry over-reaches (batch 3 vs
batch 4).** The `luminous_choir` record's EV-3 guard says
"`obtain_relic_from_grab_bag` is called with no `rarity_rng`, so
`run.pull_relic_from_front` rolls on the shared rng". That is **wrong**:
`pull_relic_from_front` falls back to `run.rewards_rng` (`run.py:588-589`),
and `rewards_rng` is `self.player_rng.rewards` whenever a parity `rng_set`
exists (`run.py:271-274`) — i.e. exactly the per-player Rewards stream the
source's one-argument `PullNextRelicFromFront(player)` rolls on
(`RelicFactory.cs:28`, `:82`). Batch 4 re-derived this for `round_tea_party`
(same verb) and `relic_trader` (three pulls) and recorded both legs as
**faithful**. Only the *shared-rng-in-legacy-mode* half of the claim is true,
and that is true of every parity accessor. **`luminous_choir`'s EV-3 entry
should be narrowed to its `NextInt(0, 50)` price roll**, which is a genuine
shared-rng site; the record's overall `gap` verdict is unaffected. Recorded
here rather than edited in place because the batch-3 record is already
committed and rule 3 asks for the disagreement to be surfaced.

**4. Consistency check, not a disagreement.** `turn_structure` G12/G14's Pael's
Eye leg uses "the Imbued card lands in the opening hand on seeds 0, 4 and 5" as
executed evidence. My `imbued` probe reproduces exactly that (7 of the first 20
seeds). Same measurement, noted so the two records are visibly consistent.

## Waivers, and why each is presentation-only or out of scope

The strict line the stream prompt asked for. Every waiver below is one of the
four categories the shared contract names — never "no ported content triggers
it", which is a dormant gap.

**Presentation / animation / SFX** — verified to have no game-state reader:

- Enchantments: `HasExtraCardText`, `ShowAmount`, `DisplayAmount`,
  `ExtraHoverTips`, `CanonicalVars` StringVars. Their only readers are
  `EnchantmentModel.DynamicExtraCardText` (`EnchantmentModel.cs:60-81`) and the
  card-UI nodes.
- `Slither.cs:51` `PlayRandomizeCostAnim`; `Slither.cs:12-29`
  `TestEnergyCostOverride` (a setter that **throws unless `TestMode.IsOn`** —
  test harness, not player-reachable).
- Events: `EventOption.ThatDoesDamage` / `.ThatDecreasesMaxHp` annotations,
  hover tips, `AmbientBgm` / `ButtonColor` / `DialogueColor` /
  `DefineDialogues`, `DollRoom`'s ambience handle, `Amalgamator`'s card-smith
  SFX and 300 ms delay, `FakeMerchant`'s `LayoutType` and `GameInfoOptions`,
  `NCardEnchantVfx`.
- `DenseVegetation.cs:68-82`'s slash VFX: waived **and** noted that
  `Rng.Chaotic` is the game's explicitly non-deterministic visual stream, not a
  run stream, so skipping it cannot shift parity.

**Multiplayer** — the `runState.Players.All(p => …)` quantifier. Waived as a
quantifier only; the inner clause is audited and implemented in every case
(`amalgamator`, `byrdonis_nest`, `colossal_flower`, `dense_vegetation`,
`endless_conveyor`, `field_of_man_sized_holes`, `grave_of_the_forgotten`).

**Other characters** — `event/colorful_philosophers`. The whole event is "take a
card reward from another character's colour"; its option list is built by
walking `CardPoolColorOrder` and keeping pools that are not the player's own, so
in an Ironclad-only sim the set is empty **by construction**, not merely
unsatisfiable today. Its RNG trim loop and three CardRewards are unreachable
behind the same waiver — and that is executed, not assumed: `is_allowed` is a
hard `return False` and `initial_options` returns `[]`.

**Deliberate divergences** (same observable, different shape) — 3 total:
`battleworn_dummy`'s returned-for-offer potion; `fake_merchant`'s stall rendered
as ordinary options instead of a custom merchant screen (price handled
separately as a gap); nothing else.

## Roster

**No unit was mis-resolved.** `harness.py roster event` → 65 sim units, 0
unmatched, 3 unported C# files (`DeprecatedAncientEvent.cs`, `DeprecatedEvent.cs`,
`TheArchitect.cs`). `roster enchantment` → 17 sim units, 0 unmatched, 6 unported
(`Adroit.cs`, `DeprecatedEnchantment.cs`, `Inky.cs`, `Momentum.cs`,
`RoyallyApproved.cs`, `SlumberingEssence.cs`). No `name_overrides.json` change
is needed from this stream.

Note `BugSlayer.cs` / `Bugslayer.cs` resolve to the same file on this
case-insensitive filesystem; the class is `Bugslayer` and the mapping is correct.

## Lessons for `tools/audit/PROMPT.md` (relic stream to fold in)

1. **`protected override` members are invisible to the harness.** `list_overrides`
   captures `public override` only, so `OnEnchant`, `GenerateInitialOptions`,
   `CanonicalVars`, `ExtraHoverTips` and `BeforeEventStarted` are never
   enumerated — and for enchantments and events those are *the substance*.
   `enchantment/steady` and `enchantment/clone` enumerate **zero** hooks;
   `event/*` enumerate `IsAllowed`/`CalculateVars`/`Resume` and nothing else.
   PROMPT.md should say outright: **for kinds whose behaviour lives in
   `protected override` members, the guards array is the record**, and step 2's
   "list every override" must mean every override, not every enumerated one.
2. **Add a bug class: "wrong RNG stream".** Three separate findings in this
   stream (Slither, EV-3, `fake_merchant`'s Shops draws) are the same shape — a
   port that takes the right *number of draws of the right shape* off the
   *wrong stream*. It is invisible in legacy mode and fatal in parity mode, and
   nothing in the current checklist points at it. Suggested wording: *"Which
   named `Rng.*` stream does the source draw from, and does the sim's call site
   use the matching accessor? Check `combat_rng.py` / `rng.py` for an existing
   accessor before concluding one does not exist."*
3. **Add a bug class: "aggregation primitive substitution".** EV-5 and EG1 are
   both "the port picked a *nearby* primitive": `random.sample` for
   `StableShuffle().Take(n)`, `before_card_played` for a direct in-loop call.
   Suggested wording: *"When a C# call is replaced by a sim primitive with a
   similar name, check the algorithm and the firing frequency, not just the
   result type — `StableShuffle` sorts first, and a hook fires once per card
   play where a direct call fires once per Replay."*
4. **Comments that assert a capability is missing are load-bearing and are
   often wrong.** Three in this stream: `enchantments.py:249`
   ("ShouldStartAtBottomOfDrawPile is cosmetic" — it reorders the draw pile),
   `endless_conveyor.py:100` ("ColorlessCardPool has no sim equivalent" — it
   does, and a sibling event uses it), `big_mushroom.py:18` ("RunState has no
   run-level AfterObtained dispatch" — `run.py:552` is one). Suggested wording:
   *"Grep for every capability a sim comment claims is absent before accepting
   it as the rationale for a divergence."*
5. **A "documented simplification" is not a verdict.** `enchantments.py:277-279`
   documents Goopy's growth as not persisting across combats; executed, it
   *does* persist and is faithful. The docstring was wrong in the safe
   direction, but the same phrase elsewhere would have hidden a gap. Treat
   in-code apologies as claims to verify, not as rationale to copy.
6. **Rule 5 has a cheap discharge for content kinds.** A one-line grep proving a
   grant path exists (`enchantment_probes.py grants`) turns 17 reachability
   claims from assertions into evidence. Worth naming in the procedure.
7. **Add a bug class: "wrong sort key" — the twin of the RNG-stream class.**
   EV-7 is a port that takes the *right draws off the right stream in the
   right order* and still lands on a different element, because the sort that
   precedes the shuffle used a different comparand. Suggested wording: *"When
   a C# call sorts before it samples, check WHAT it sorts on. `StableShuffle`
   sorts by the element's `IComparable` order, which for any `AbstractModel`
   is `ModelId.Entry` compared `Ordinal` — the UPPERCASE slug. A sim id is
   lowercase, and `'_'` (0x5F) sorts on the opposite side of the letters in
   the two cases."*
8. **A negative control is worth writing even when you expect zero.** Three
   batch-4 guards are "the hook the sim skips reaches nobody": `AfterRemoved`
   (0 relic overrides), `AfterPotionDiscarded` (1 implementer, gated on
   `IsInProgress`), `EnchantmentModel.IsStackable` (0 enchantment overrides).
   Each took one probe and converted a `faithful` verdict from an assertion
   into evidence — and the third one nearly went the other way, because
   `CanEnchant`'s stacking clause *reads* like a live divergence until you
   grep for the overrides.

### Flagged for the relic stream (not ours to fix)

- `relics/fragrant_mushroom.py:31-36` calls `actmap.stable_shuffle` with
  `key=lambda c: (c.id, c.upgrade_level)` — a **lowercase** card id, so EV-7
  applies, and the `upgrade_level` tiebreaker has no counterpart in
  `ModelId.CompareTo` at all. The report's earlier praise of this call site as
  "the pattern EV-5 says the event sites should have followed" is right about
  the *primitive* and wrong about the *key*.
- `relics/belt_buckle.py` implements `on_combat_start` and `on_potion_used`
  but has no potion-**discard** hook, where `BeltBuckle.cs:72-79` overrides
  `AfterPotionDiscarded`. Out of scope for the event stream (every event
  discard is out of combat, so the C# body's `IsInProgress` gate makes it a
  no-op there — see the `potiondiscard` probe), but the in-combat discard path
  is the relic record's business.

## Residual queue — none for this stream

All 82 units (65 events + 17 enchantments) are audited and validating. What
remains is work for *other* streams and for whoever converts findings into
fixes.

**Hand-offs to other streams** (found here, not ours to record or fix):

- **Relic stream.** EV-7's uppercase sort key reaches
  `relics/fragrant_mushroom.py`. EV-10's missing Quest clause reaches
  `relics/astrolabe.py:21` and `relics/new_leaf.py:16`.
  `relics/distinguished_cape.py` needs the −9 Max HP moved into
  `after_obtained`, and its docstring says the opposite of what the code does.
  `relics/wongo_customer_appreciation_badge.py`'s docstring claims 32+16+8 = 56
  points per run — false; each buy handler ends in `_finish` and the event is
  act-2-only, so the max is **32**.
- **Relic / run-machinery stream.** `run.pull_relic_from_front` applies no relic
  `IsAllowed(runState)` pre-filter, where C# has
  `RemoveDisallowedRelicsFromDeques`. **20** relics override it; 19 are
  `IsBeforeAct3TreasureChest` (`TotalFloor < 41`) and one is multiplayer. At
  `welcome_to_wongos` (act index 1) it is a no-op, which is why it was flagged
  rather than recorded — but **any pull after floor 41 diverges**.
- **Card stream.** `cards/event_cards.py:371`'s claim that Lantern Key is "an
  inert unplayable card because the sim has no map" is false twice over: the sim
  dispatches `modify_unknown_map_point_room_types`, and the card is what injects
  War Historian Repy.
- **Unported content named by this stream:** `circlet`
  (`RelicFactory.FallbackRelic`), `history_course`, `ModifierModel` (Neow's
  run-modifier branch), `SaveManager.Progress` (the Wongo badge), and
  `TheArchitect` (the third Combat-layout event).

**Four false docstrings** were found across the 82 units
(`relics/distinguished_cape.py`, `relics/wongo_customer_appreciation_badge.py`,
`cards/event_cards.py`, and `endless_conveyor`'s "no colourless pool exists").
Each asserted a *behavioural* claim that the source contradicts. That is a
recurring enough pattern to be worth a bug class of its own — a docstring
asserting behaviour is a claim to be checked, not context to be trusted.

**Retroactive edits made in this commit** to already-committed records:
`endless_conveyor`'s potion guard was relabelled EV-3 → EV-9, and
`the_lantern_key`'s `LayoutType` waiver was overturned to EV-12 (both explained
above). No other committed verdict changed.

## Cost

Two sessions. The first covered the machinery plus 17 enchantments and 20
events; machinery reading (EnchantmentModel/EventModel/CardModel/Hook/
CreatureCmd/HealRestSiteOption + the sim's `run.py`, `combat.py`, `hooks.py`,
`player.py`, `cmds.py`) was ≈ 35% of that budget and is amortised across all 82
units.

Measured per-unit cost, once the mechanisms were named:

| batch | units | tokens | notes |
|---|---|---|---|
| 4 | 13 | 258k | one agent, sequential |
| 5A | 8 | 314k | concurrent |
| 5B | 8 | 224k | concurrent |
| 5C | 7 | 234k | concurrent |

So ≈ 20-30k tokens per unit, and it did **not** fall as the shared mechanisms
accumulated — the later units were not cheaper to audit, they just produced
findings that cited existing mechanisms instead of minting new ones. Batch 5
still turned up four new mechanisms in its 23 units, which is the same discovery
rate as batch 4's two in 13. **The "it gets cheaper once the machinery is
mapped" prediction in the first cut of this report was wrong**, and a future
stream should budget flat per-unit rather than assuming a tail-off.

Running the last 23 as three concurrent slices cut wall-clock roughly threefold
(~27 min versus ~75 min sequential at batch-4's rate) for the same token spend,
at the cost of the id collision documented at the top of this file and one
duplicated discovery (two slices independently finding the two halves of EV-9).

## Review fix pass

Six review findings applied on `audit-pipeline`. No re-audit of the tier: only
the named defects were touched, plus the sites rule 3 forces along with them.

| kind | units | rollups after the pass | entries |
|---|---|---|---|
| `event` | 65 | 47 gap / 16 waiver / 2 deliberate-divergence | 350 faithful, 127 waiver, 103 gap, 10 dd |
| `enchantment` | 17 | **17 gap** (was 12 gap / 3 faithful / 2 waiver) | 56 faithful, 43 gap, 14 waiver |

Counts recomputed programmatically over the record files, not carried forward
from the first cut. Verification: `py audit/tools/harness.py validate` -> 428
records, 0 invalid; `py audit/tools/audit_status.py` -> `enchantment 17/17, 0
invalid, 0 stale, 17 gaps` and `event 65/65, 0 invalid, 0 stale, 47 gaps`;
`py -m pytest test/ -q` -> 2522 passed, 38 xfailed (the suite grew under
concurrent streams; this pass adds no executable code and changed no test);
`git diff --name-only main...audit-pipeline | grep ^sts2_rl/` -> empty.

Commits: `87a4cec5` (FIX 1+2), `d9bd3da1` (FIX 3), `d4f320d8` (FIX 5),
`e3737645` (FIX 6), `17345543` (FIX 4).

### FIX 1 + FIX 2 — the copy verb was a live gap, and the four-verb check is now closed

**EG2 (new mechanism, `gap`, recorded on all 17 enchantment records).** C#
`CardModel.CreateClone` -> `MutableClone` -> `DeepCloneFields`
(`CardModel.cs:1204-1209`) re-attaches the source card's enchantment onto the
copy — `ClonePreservingMutability()`, `Enchantment = null`,
`EnchantInternal(...)` — and does the same for the Affliction at 1210-1215.
`CreateClone` throws unless the card is in a **combat** pile
(`CardModel.cs:2170-2173`), so every site is a combat-pile copy.

**Five** ported sim copy sites drop it, each a `type(card)()` /
`make_card(card.id)` rebuild plus a re-upgrade loop with no `card.enchantment`
carry:

| sim | C# | trigger |
|---|---|---|
| `cards/trash_heap_cards.py:18-24` `_clone` | `DualWield.cs:35` | hand ATTACK or POWER |
| `powers.py:827-830` | `JugglingPower.cs:48` | every 3rd ATTACK played |
| `relics/music_box.py:46-48` | `MusicBox.cs:78` | first ATTACK played each turn |
| `cards/anger.py:36-38` | `Anger.cs:27` | Anger copies itself |
| `relics/burning_sticks.py:30-32` | `BurningSticks.cs:49` | first SKILL exhausted each combat |

The sim's *other* copy paths are correct, which is what makes this a bug rather
than a design choice: `relics/bing_bong.py:37`, `events/reflections.py:52` and
the per-combat deck copy `run.py:1136` all use `copy.deepcopy` (the enchantment
rides along), and `relics/paels_growth.py:39-46` re-attaches Clone by hand.

**Recorded on all 17, not the five the review named.** The review named
`sharp`/`vigorous`/`corrupted`/`instinct`/`goopy`, but an executed
`can_enchant` matrix over ATTACK/POWER/SKILL shows every one of the 17 reaches
at least one dropping site, and rule 3 puts one verdict at every site — the
same convention EV-1 ("all 18 `lose_hp` sites") and EV-3 already follow. Two
corrections fell out of that matrix:

- **Goopy is not Dual-Wield-reachable.** `Goopy.cs:16-21` requires
  `CardTag.Defend`, so the matrix reads False/False/True. Its reachable site is
  Burning Sticks — and it is a tight fit rather than luck, because Goopy is the
  enchantment that *adds* the Exhaust that fires Burning Sticks.
- **Souls is reachable**, which was not obvious: it needs a card with Exhaust
  and its own effect removes Exhaust. 36 ported cards qualify, 6 of them
  ATTACKs (`dramatic_entrance`, `feed`, `fiend_fire`, `molten_fist`,
  `neows_fury`, `whistle`), so it reaches the four attack sites as well as
  Burning Sticks.

**LIVE on 15, DORMANT on 2.** `clone` is dormant because its only reader is the
Clone rest-site option over the *deck* and every dropping site produces a
combat card; `imbued` is dormant because both its effects are combat-*setup*
effects (`ShouldStartAtBottomOfDrawPile`, the turn-1 auto-play) and a Burning
Sticks copy is minted after both windows close. Dormant, not waived — rule 1.
Three enchantments (`glam`, `sown`, `swift`) are live specifically *through*
Dual Wield: they fire once per combat, and C#'s `ClonePreservingMutability`
carries `Status = Disabled` from an already-played card, so the three
play-triggered sites are dormant for them and the unplayed-hand-card site is
not.

**FIX 2's transform finding: FAITHFUL, both engines drop it.**
`CardCmd.Transform` (`CardCmd.cs:369-451`) takes `item.GetReplacement(rng)`,
calls `RemoveFromCurrentPile()` on the original and adds the replacement; the
word `Enchantment` never appears in the method, and both `AfterTransformedFrom`
and `AfterTransformedTo` are empty virtuals (`CardModel.cs:1625-1631`;
`SovereignBlade` is the source's only override). The sim's `run.transform_card`
and `CardCmd.transform_to_random` build the replacement with `make_card(...)`.
Executed on all 17 ids, both engines drop the enchantment — so the review's
"presumably should not carry" is confirmed, and it is now *on the record*
instead of being nobody's assumption.

Each record now carries an explicit **four-verb coverage table** (enchant /
upgrade+downgrade / transform / copy). The upgrade+downgrade radius was
executed too, and it exactly matches the four units the `creature_card_cmds`
step-52 hand-off covered: only `goopy`, `souls`, `steady` and
`tezcataras_ember` override `attach()` to mutate a static card property, so
only those four can be undone by a card rebuild. The other 13 work through the
`modify_*` hooks, read live off the still-attached enchantment. That was
previously an unstated assumption; it is now a one-liner in every record.

**False docstring #5.** `_clone`'s "mirrors `CreateClone` for the sim's needs"
is false: `CreateClone` carries the enchantment *and* the affliction, `_clone`
carries neither. Same bug class as the four the first cut found — a docstring
asserting behaviour is a claim to be checked, not context to be trusted.

### FIX 3 — a waiver that admitted it was a gap

`event/jungle_maze_adventure` guard:4 stated outright that
`JungleMazeAdventure.cs:60`'s `_fx.ToList().StableShuffle(base.Rng)` "IS a real
stream draw the sim does not take" and then filed `waiver`. Re-verified at
source: it is the **first, unconditional statement** of `DontNeedHelp`, over
the static 3-entry `_fx` list. That is EV-3's exact mechanism, verdicted `gap`
at **28 other entries across 27 event records** — including the `CalculateVars`
guard two entries up in the same file. Re-verdicted `gap`, citing EV-3, with
EV-5/EV-7's StableShuffle shape noted (sort-then-Fisher-Yates makes it a
deterministic, countable stream advance, which is a second reason a *cosmetic*
shuffle cannot be waived). The presentation half (waits, SFX) stays in the same
guard because a guard carries max(verdict) of what it aggregates. Rollup was
already `gap`; nothing else moved.

### FIX 4 — 183 unrunnable probe citations

The `tools/audit/*` -> `audit/tools/*` restructure left every probe citation in
these records pointing at a path that no longer exists. Swept all 183 in scope
across 69 records: `event_probes` 87, `event_probes_a` 29,
`enchantment_probes` 28, `event_probes_b` 20, `event_probes_c` 19. Then
verified the citations actually *run*: all **45** distinct
(probe, subcommand) pairs the records name resolve against the probe modules'
`PROBES` tables. A citation that cannot be executed is not evidence, so the
check is worth keeping as a lint.

### FIX 5 — two rationale corrections

- `event/vakuu` hook:`CalculateVars` was waived "out of scope: profile
  metadata" — not one of the four permitted categories, so it read as a rule-3
  violation against `event/welcome_to_wongos`, which files the same unported
  `SaveManager.Progress` dependency as a dormant **gap**. Re-grounded on the
  presentation clause, with the negative narrowed to what is actually true:
  a grep for the `Visits` key returns only the three Vakuu.cs sites that
  *create* the var plus one unrelated serializer entry, and the dialogue
  *selection* does not read it either — `AncientDialogueSet.GetValidDialogues`
  (`AncientDialogueSet.cs:104-135`) matches `VisitIndex` against a `charVisits`
  argument its caller supplies. So it is a localization substitution token. The
  Wongos distinction is the **consequence**, not the dependency: there
  `Progress` feeds a relic grant, here a spoken line.
- The `AllPossibleOptions` "its only reader is the DebugOption swap" claim is
  false as written — `AncientConsoleCmd.cs:41,71` and
  `NRelicCollectionCategory.cs:116` also read it. Narrowed. The review named
  two sites; the same over-broad negative was at **four** (`tanx`,
  `tezcatara`, `vakuu`, `nonupeipe`). No verdict moves: the extra readers are
  dev console and compendium UI, and `NeowsBones.cs:33` reads
  `ModelDb.Event<Neow>().AllPossibleOptions` — hard-coded to *Neow's* list,
  which is exactly why `event/neow` records its `AllPossibleOptions` as a real
  faithful function and every other ancient waives it.

### FIX 6 — the eventsVisited hole, executed rather than noted

No record named `eventsVisited`, so two consequence claims rode on it unproven.
Both are now executed, and they came out differently:

- **`unrest_site`'s "shifts every later event pick" — PROVEN.**
  `RoomSet.EnsureNextEventIsValid` (`rooms.py:441-457`) increments
  `events_visited` past every event whose `IsAllowed` fails, and
  `mark_visited` (`rooms.py:431-439`) increments it again when the room is
  served, so a wrongly-refused event does not merely go missing — it advances
  the cursor and re-indexes the whole tail. Executed over the queue
  `[unrest_site, doll_room, tea_master, this_or_that]` at 90/63: the game
  serves `[unrest_site, doll_room, tea_master]`, the sim serves
  `[doll_room, tea_master, this_or_that]`. Recorded as a `faithful` guard —
  the ordering machinery itself matches the source; the divergence is the
  `IsAllowed` gap, not re-verdicted (rule 3).
- **`morphic_grove`'s "can make the sim offer a map node the game would not" —
  DISPROVEN.** The claim lived in `event/trial`'s EV-10 text.
  `MorphicGrove.cs:26` gates on `c.IsTransformable`, which for a Deck card is
  `!Eternal` (`CardModel.cs:739-750`) with **no Quest clause** — the Quest
  clause is only on the transform *screen* (`CardSelectCmd.cs:487`). Executed:
  deck `[strike, spoils_map]`, gold 100 — sim `is_allowed` True, game count
  2 -> True. **The gates agree.** EV-10's verdict is unaffected, because the
  real divergence is one step later and is still LIVE, with a sharper witness
  than the withdrawn one: the sim's screen offers 2 candidates where the game's
  offers 1, and since GROUP passes `CardSelectorPrefs(prompt, 2)` (MinSelect ==
  MaxSelect, so `RequireManualConfirmation` is false), the game auto-takes its
  1-card list (`CardSelectCmd.cs:493-495`) and transforms **one** card while
  the sim transforms **two** and destroys the Quest card. Recorded as an EV-10
  site on `event/morphic_grove`.

### Residual from this pass

`harness.py validate` now emits `WARN inherited overrides with no verdict` on
**8 event records** (`darv`, `neow`, `nonupeipe`, `orobas`, `pael`, `tanx`,
`tezcatara`, `vakuu` — `InitialDescription` / `LayoutType` / `LocTable`) and
**8 power records**. That check did not exist when these records were written;
it arrived mid-flight from the tooling stream, and the same warning spans a
tier this pass does not own. Left for whoever owns the check, since deciding
how inherited presentation overrides get recorded is a convention call, not a
correction. `invalid` is still 0.
