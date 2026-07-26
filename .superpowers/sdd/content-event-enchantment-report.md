# Stream 4 report — event + enchantment content audits

Branch `audit-event`, worktree `C:\Users\Perry\Desktop\sts2-rl-event`.
Written 2026-07-26. Three commits on top of `8583546a`.

## Status

| kind | total | audited | invalid | gaps | unaudited |
|---|---|---|---|---|---|
| `enchantment` | 17 | **17** | 0 | 12 | **0** |
| `event` | 65 | 20 | 0 | 13 | 45 |

`py tools/audit/harness.py validate` → 42 records, 0 invalid.
`py -m pytest test/ -q` → 2476 passed, 31 xfailed, unchanged at every commit
(audits add no executable code; the two probe modules under `tools/audit/` are
not imported by the suite).

Commits:

- `3abf27d9` audit(enchantment): all 17 units, 12 gaps
- `c3c9f8de` audit(event): batch 1/5 — 13 units, 8 gaps
- `53b54670` audit(event): batch 2/5 — 7 units, 5 gaps

**The enchantment kind is complete — the status report's first `unaudited 0`
row.** The event kind is 20/65; the residual queue is at the bottom of this
file, with the shared machinery already established so a follow-up session is
mostly per-unit mapping.

## Reproducible evidence

Two probe modules, following `tools/audit/dormancy_probes.py`'s pattern — every
number any record states is produced by one of them:

- `tools/audit/enchantment_probes.py` — `order`, `onplay-slot`, `replay`,
  `imbued`, `goopy`, `eternal`, `slither-rng`, `souls-reset`, `grants`
- `tools/audit/event_probes.py` — `lethal`, `maxhp`, `eventrng`, `heal`,
  `deckverbs`

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
Ancient full heal in `events/ancient.py:31`.

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

**3. Consistency check, not a disagreement.** `turn_structure` G12/G14's Pael's
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

## Residual queue — 45 events

The shared machinery is done: EV-1…EV-5, the two heal verbs, the deck verbs, the
blast-radius tables and both probe modules are in place, so the remaining work
is per-unit mapping against known mechanisms.

Batch 3 (13): `infested_automaton`, `jungle_maze_adventure`, `lost_wisp`,
`luminous_choir`, `morphic_grove`, `neow`, `nonupeipe`, `orobas`, `pael`,
`potion_courier`, `punch_off`, `ranwid_the_elder`, `reflections`.
Batch 4 (13): `relic_trader`, `room_full_of_cheese`, `round_tea_party`,
`sapphire_seed`, `self_help_book`, `slippery_bridge`, `spiraling_whirlpool`,
`spirit_grafter`, `stone_of_all_time`, `sunken_statue`, `sunken_treasury`,
`symbiote`, `tablet_of_truth`.
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
  **not** apply to — check the branch, do not assume it.
- `punch_off` and `the_lantern_key` both declare `CanonicalEncounter` and attach
  `pending_reward_extras`; `battleworn_dummy` and `fake_merchant` are the worked
  examples for that shape.

## Cost

One session. Roughly: machinery reading (EnchantmentModel/EventModel/CardModel/
Hook/CreatureCmd/HealRestSiteOption + the sim's `run.py`, `combat.py`,
`hooks.py`, `player.py`, `cmds.py`) ≈ 35% of the budget and is amortised across
all 82 units; the 17 enchantments ≈ 25%; the 20 events ≈ 30%; validation, three
full suite runs (~4 min each) and this report ≈ 10%. The remaining 45 events
should run materially cheaper per unit now that the shared mechanisms are named
and the probes are written — the enchantment kind was expensive because it was
where EG1, EV-1's cousin and the RNG-stream class were discovered.
