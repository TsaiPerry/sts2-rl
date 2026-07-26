# Stream 4 report — event + enchantment content audits

Branch `audit-event`, worktree `C:\Users\Perry\Desktop\sts2-rl-event`.
Written 2026-07-26. Five commits on top of `8583546a`.

## Status

| kind | total | audited | invalid | gaps | unaudited |
|---|---|---|---|---|---|
| `enchantment` | 17 | **17** | 0 | 12 | **0** |
| `event` | 65 | 42 | 0 | 30 | 23 |

`py tools/audit/harness.py validate` → 64 records, 0 invalid.
`py -m pytest test/ -q` → 2476 passed, 31 xfailed, unchanged at every commit
(audits add no executable code; the two probe modules under `tools/audit/` are
not imported by the suite).

Commits:

- `3abf27d9` audit(enchantment): all 17 units, 12 gaps
- `c3c9f8de` audit(event): batch 1/5 — 13 units, 8 gaps
- `53b54670` audit(event): batch 2/5 — 7 units, 5 gaps
- `4432d5e1` docs(audit): stream 4 report (first cut)
- `c61f34c3` audit(event): batch 3 — 9 units, 7 gaps
- (this commit) audit(event): batch 4 — 13 units, 10 gaps

**The enchantment kind is complete — the status report's first `unaudited 0`
row.** The event kind is 42/65; the residual queue is at the bottom of this
file, with the shared machinery already established so a follow-up session is
mostly per-unit mapping.

## Reproducible evidence

Two probe modules, following `tools/audit/dormancy_probes.py`'s pattern — every
number any record states is produced by one of them:

- `tools/audit/enchantment_probes.py` — `order`, `onplay-slot`, `replay`,
  `imbued`, `goopy`, `eternal`, `slither-rng`, `souls-reset`, `grants`
- `tools/audit/event_probes.py` — `lethal`, `maxhp`, `eventrng`, `heal`,
  `deckverbs`, and (batch 4) `kill`, `sortkey`, `relictrade`, `enchantstack`,
  `potiondiscard`, `cheese`, `reach`

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

## Residual queue — 23 events

The shared machinery is done: EV-1…EV-8, the two heal verbs, the deck verbs, the
blast-radius tables and both probe modules are in place, so the remaining work
is per-unit mapping against known mechanisms.

Batch 3 is **partly done** — `infested_automaton`, `jungle_maze_adventure`,
`lost_wisp`, `luminous_choir`, `morphic_grove` and the four Ancients (`neow`,
`nonupeipe`, `orobas`, `pael`) are audited. Still open from it (4):
`potion_courier`, `punch_off`, `ranwid_the_elder`, `reflections`.

Batch 4 is **done** (13 units, 10 gaps): `relic_trader`,
`room_full_of_cheese`, `round_tea_party`, `sapphire_seed`, `self_help_book`,
`slippery_bridge`, `spiraling_whirlpool`, `spirit_grafter`,
`stone_of_all_time`, `sunken_statue`, `sunken_treasury`, `symbiote`,
`tablet_of_truth`. Non-gap rollups: `sapphire_seed`, `self_help_book` and
`spiraling_whirlpool` are `waiver` (presentation-only residue over an
otherwise faithful port).

Batch 5 (12): `tanx`, `tea_master`, `tezcatara`, `the_future_of_potions`,
`the_lantern_key`, `the_legends_were_true`, `this_or_that`, `tinker_time`,
`trash_heap`, `trial`, `unrest_site`, `vakuu`.
Batch 6 (7): `war_historian_repy`, `waterlogged_scriptorium`,
`welcome_to_wongos`, `wellspring`, `whispering_hollow`, `wood_carvings`,
`zen_weaver`.

Known leads not yet audited:

- `war_historian_repy` is the **second deferred shared-event stub** (named
  alongside `crystal_sphere` in `events/crystal_sphere.py:12`); expect the same
  gap shape.
- The six events with a parity RNG branch (`neow`, `orobas`, `pael`,
  `tablet_of_truth`, `tezcatara`, `whispering_hollow`) are the ones EV-3 does
  **not** apply to — check the branch, do not assume it. Four are now audited
  and three were clean; `orobas` was not, and its defect was a **missing** draw
  rather than a wrong stream. When auditing the remaining two, count the draws
  on every path, including the ones that offer a locked option.
- `nonupeipe`, `orobas` and `pael` are worked examples of the Ancient shape
  (`events/ancient.py`'s inherited full heal and `_relic_option`); `tanx`,
  `tezcatara` and `vakuu` are the same shape.
- `punch_off` and `the_lantern_key` both declare `CanonicalEncounter` and attach
  `pending_reward_extras`; `battleworn_dummy` and `fake_merchant` are the worked
  examples for that shape.
- `ranwid_the_elder` (batch-3 leftover) shares **two** shapes with batch-4
  units: `RanwidTheElder.cs:74`/`:94` uses the same `IsTradable` filter as
  `relic_trader` (so the `relictrade` probe's zero-`AfterRemoved` finding
  carries), and `RanwidTheElder.cs:42-48` sets `CanRemovePotions` (so
  `stone_of_all_time`'s grep-verified UI waiver carries). Same for
  `the_future_of_potions` in batch 5 (`TheFutureOfPotions.cs:92-98`).
- `the_future_of_potions` also uses `ForNonCombatWithUniformOdds` +
  `NoRarityModification` (`TheFutureOfPotions.cs:127`) — the same shape as
  `room_full_of_cheese`, so check it against **EV-8**, not EV-6.

## Cost

One session. Roughly: machinery reading (EnchantmentModel/EventModel/CardModel/
Hook/CreatureCmd/HealRestSiteOption + the sim's `run.py`, `combat.py`,
`hooks.py`, `player.py`, `cmds.py`) ≈ 35% of the budget and is amortised across
all 82 units; the 17 enchantments ≈ 25%; the 20 events ≈ 30%; validation, three
full suite runs (~4 min each) and this report ≈ 10%. The remaining 45 events
should run materially cheaper per unit now that the shared mechanisms are named
and the probes are written — the enchantment kind was expensive because it was
where EG1, EV-1's cousin and the RNG-stream class were discovered.
