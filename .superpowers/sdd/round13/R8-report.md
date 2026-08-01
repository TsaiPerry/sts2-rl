# R8 report — settling unlabelled batch `relic-2` (14 entries, 13 records)

> **READ §6 FIRST — "Fix pass (2026-08-01)".** Sections 1–5 below are the
> first pass. Where they conflict with §6, **§6 is authoritative**: it carries
> the corrected reasoning, the rewritten tests with mutation evidence, and the
> FINAL record-close and queue-annotation text the controller should apply.
> Individual sentences corrected in place are marked `[CORRECTED → §6]`.
> One verdict changed: `relic/hefty_tablet/AfterObtained` G2 is **LIVE**, not
> dormant (§6.7).

Footprint: `sts2_rl/relics/<name>.py` for the 13 relics in the manifest, plus
`test/test_r13_relic2.py` (new). One production file touched:
`sts2_rl/relics/vambrace.py` (docstring only, 6 lines). `relics/base.py` was
read (extensively) but not edited — it belongs to another lane this wave.

**Headline**: 12 of 14 entries are **DORMANT-ENUMERATED** (re-confirmed by
fresh execution/census against today's tree, several with materially
strengthened or corrected reasoning), 1 is **NARROWED**
(`spiked_gauntlets/TryModifyEnergyCostInCombat`: two of its three guards
close, one stays open), and 1 is **FIXED**
(`vambrace/g6`, a docstring-only correction). **Two guards under
`relic/ruined_helmet` flip from "cited an open seam gap" to
STALE-ALREADY-FIXED**: `seam/power_cmd.json`'s own G3/G4 closed 2026-07-31
(tier-2 campaign, Task 17/18) — three days after this batch's audit date —
and `ruined_helmet.py` has already been rewritten to the new machinery.
**One guard flips the same way inside `spiked_gauntlets`**: the plain/Late
two-pass phase machinery `hooks.py`'s `_each` generalized now covers
`modify_card_energy_cost` for free. `[CORRECTED → §6]` — that generalization
is **not** this round's work; `_PHASES`, `_phased` and `_each`'s phase loop are
all present unchanged at `HEAD`, as is `brilliant_scarf.modify_card_energy_
cost_late`. The guard closed in an earlier round and the record was never
revisited. See §6.4.

The R1-brief's warning was directly relevant: `bag_of_marbles/G2`'s citation
("PowerCmd.apply does not apply [should_allow_hitting] either... that
absence is power_cmd gap G6") is **stale in a way the brief's checklist did
not anticipate** — not because of R1's listener-*derivation* rework, but
because `power_cmd/G6` (the `CanReceivePowers` backstop inside `PowerCmd.
apply`) **was FIXED 2026-07-29 (round 5), three days AFTER this record's
2026-07-26 audit**; the record was never revisited. `[CORRECTED → §6]` — the
first pass said "round 4 (2026-07-28), before this record's audit" three
different ways and all three were incoherent (§6.1). Re-verified directly:
`cmds.py`'s `can_receive_powers` now backstops `PowerCmd.apply`.
`[CORRECTED → §6]` — the claim that `DamageCmd.deal` "already backstopped the
damage-dealing relics in this same batch" is **false**: that line is dead code,
dominated by the `is_dead` guard above it. See §6.1 for the executed proof and
the replacement reasoning.

---

## 1. Per-entry verdicts

### `relic/bag_of_marbles/BeforeSideTurnStart` (G2) — DORMANT-ENUMERATED (reasoning strengthened)

C#: `CombatState.HittableEnemies` (`CombatState.cs:142`) = `Enemies.Where(e
=> e.IsHittable)`, `IsHittable` = `!IsDead && Hook.ShouldAllowHitting`
(`Creature.cs:285-299`). Sim: `bag_of_marbles.py:22` still iterates
`self.living_enemies()` (`not e.is_gone` only, `relics/base.py:470-477`) and
calls `PowerCmd.apply` per enemy — the call-site divergence the record's G2
names is still real in the code.

**What changed since the 2026-07-26 audit**: `PowerCmd.apply`
(`sts2_rl/cmds.py:871`, was `:841` before this wave's concurrent edits) now
opens with `if not can_receive_powers(hooks, target): return`, and
`can_receive_powers` (`cmds.py:65-75`) is `not
target.is_removed_from_combat and hooks.should_allow_hitting(target)` — the
exact `CanReceivePowers`/`ShouldAllowHitting` backstop the record says is
absent (`"that absence is audit/records/seam/power_cmd.json gap G6"`).
`power_cmd.json`'s own guard G6 reads `verdict: faithful`, `"...
FIXED 2026-07-29 (round 5)"` `[CORRECTED → §6]` (the first pass wrote
"2026-07-28 (round 4)", which is the NARROWING date, not the close).

**Re-derived, not inherited**: `should_allow_hitting`'s only three
implementers (`IllusionPower`, `AdaptablePower`, the Decimillipede's
`ReattachPower`) all key their `False` case on `is_reviving`, which is armed
only from `on_death` and therefore never holds without `is_dead` (→
`is_gone`) also holding — so `living_enemies()` already excludes every
creature `hittable_enemies()` would additionally exclude, for every
currently-reachable creature. Executed directly with `IllusionPower`
(`test_should_allow_hitting_false_still_coincides_with_is_gone`): a reviving
enemy is provably absent from BOTH `living_enemies()` and
`hittable_enemies()`. Then, to demonstrate the NEW backstop specifically
(not just the pre-existing set-coincidence), a HAND-FED reviving enemy —
bypassing `living_enemies()`'s own exclusion entirely — is still refused by
`PowerCmd.apply` itself
(`test_power_cmd_apply_backstops_bag_of_marbles_against_an_unhittable_target`):
`PowerCmd.apply(hooks, enemy, VulnerablePower, 1, applier=player)` applies
nothing.

**Verdict unchanged (`gap`, dormant)**, matching binding rule 3's own
precedent at the sibling entry `charons_ashes/G1`, which stays `gap` even
though its backstop (`DamageCmd.deal`'s) is fully behaviour-closing: the
call site itself is still architecturally wrong (built from `living_enemies
()`, not `hittable_enemies()`), and would go live the instant a second
`should_allow_hitting` implementer with a non-`is_reviving`-gated `False`
case is ported. What changes is the STRENGTH of the dormancy argument: this
is no longer "no backstop exists," it is "a real, closed backstop exists on
the POWER side." `[CORRECTED → §6]` — the words "the same full backstop
`charons_ashes` already has" are wrong: the damage side has no such backstop.
See §6.1.

Citations: `BagOfMarbles.cs:19,23,28`, `CombatState.cs:142`,
`Creature.cs:285-299`, `sts2_rl/relics/bag_of_marbles.py:18-24`,
`sts2_rl/relics/base.py:470-481`, `sts2_rl/cmds.py:65-75,841-843`,
`sts2_rl/powers.py` (`IllusionPower.should_allow_hitting`,
`AdaptablePower.should_allow_hitting`, `ReattachPower.should_allow_hitting`
— symbol only, `powers.py` is under concurrent edit this wave).

### `relic/charons_ashes/AfterCardExhausted` (G1, G3) — DORMANT-ENUMERATED (re-confirmed, unaffected)

G1: same mechanism and same call-site shape as `bag_of_marbles/G2` (binding
rule 3), dormant on the **set-coincidence proof ALONE**. `[CORRECTED → §6]` —
the first pass claimed a second, independent leg, "the pre-existing
`DamageCmd.deal` backstop (`cmds.py:289: if not
hooks.should_allow_hitting(target): return 0`)". **That line is dead code**,
dominated by the `if target.is_dead: return 0` immediately above it, and the
test that "re-executed" it was a null test that passed with the mechanism
deleted. Re-derived and mutation-proved in §6.1; the replacement test is
`test_damage_cmd_deal_refuses_the_damage_relics_at_the_is_dead_guard`.

G3 (batched-vs-sequential damage, `CreatureCmd.cs:240-411`'s two-pass
resolution vs the sim's per-enemy `DamageCmd.deal` loop) is unrelated to
this round's engine changes (it is about `CreatureCmd.Damage`'s internal
resolution order, not listener derivation) — re-read `cmds.py`'s
`DamageCmd.deal` in full: still one call per enemy, still its own inline
death processing per call. `damage_pipeline.json` guard N2 (which this entry
cites and matches per binding rule 3) is unaffected by anything in
`hooks.py`. Verdict unchanged: `deliberate-divergence`.

Citations: `CharonsAshes.cs:19-27`, `CreatureCmd.cs:240-411`,
`sts2_rl/relics/charons_ashes.py:21-29`, `sts2_rl/cmds.py:245-289`.

### `relic/festive_popper/AfterPlayerTurnStart` (G2, G3) — DORMANT-ENUMERATED (re-confirmed)

G1 (hook slot) was already closed before this round and is untouched by
R1/R5's engine work — re-verified `festive_popper.py:21` is still
`on_player_turn_started` alone (confirmed via `hooks.py:1209-1223`'s own
docstring: `on_player_turn_started` is `Hook.AfterPlayerTurnStart` and
nothing else now). `[CORRECTED → §6]` — but the record's **guard G1 still
reads `verdict: gap`** and every clause of its text is now stale, and the
first pass's close proposal #3 did not ask the controller to flip it. That
is a THIRD instance of this report's own §5 headline pattern, inside its own
manifest. See §6.3.

G2 (enemy set): same mechanism as `bag_of_marbles`/`charons_ashes`, dormant
on the **set-coincidence proof alone**. `[CORRECTED → §6]` — the first pass
said "set-coincidence + `DamageCmd.deal` backstop" and read the record's own
"There is a partial backstop here that Bag of Marbles lacks" as now being
"the FULL story". Both halves are wrong: the `DamageCmd.deal` hook line is
dead code (§6.1), so the damage side has NO backstop leg at all — partial or
full — and the record's sentence should be replaced, not upgraded.

G3 (hand-rolled inline `_check_win()`, ending combat before C#'s real
`CheckWinCondition` call site) — **the record's own citation
(`turn_structure.json` gap `G13`) has gone stale in status, but the
underlying divergence at THIS site has not.** `turn_structure.json`'s G13
now reads `verdict: faithful`, `"FIXED 2026-07-29 (round 5)"` — all six C#
`CheckWinCondition` sites are now real recomputations in the sim, not cached
`Phase.COMBAT_OVER` reads. But every site G13 lists is at **turn END**
(after `Hook.BeforeTurnEnd`, closing `EndPlayerTurnPhaseOneInternal`,
`EndEnemyTurn`) — none of them recomputes win between the turn-start hook
dispatch and C#'s actual `CheckWinCondition` call
(`CombatManager.cs:573`, step 27, after `AfterSideTurnStart`/the orb
tick/the auto-pre-play phase). `[CORRECTED → §6]` — the first pass's stated
basis, *"Re-read `combat.py`'s `_start_player_turn` in full: it calls
`self.player.start_turn()` and nothing else — no `_check_win_condition()`
call sits between the turn-start dispatch and the method's return"*, is
technically true of the METHOD and substantively misleading: its CALLER
(`combat.py:339-340`) does exactly that recompute, with a comment naming
`CombatManager.cs:573`, and `turn_structure/G13`'s close note names that site.
The real, citable ground is `Hook.cs:30-45` (deferred teardown), restated in
§6.3. So `festive_popper.py`'s own `_check_win()` still ends
combat strictly earlier than C# would, inside `on_player_turn_started`'s own
dispatch. Re-executed
(`test_festive_popper_check_win_still_ends_combat_inside_its_own_dispatch`):
with a 1-HP enemy, calling `relic.on_player_turn_started(player)` directly
leaves `cs.is_over == True` on return — a hypothetical later-dispatched
listener in the same walk would already see `COMBAT_OVER`, where C# is
still mid `AfterPlayerTurnStart` (steps 22/23), long before step 27.

**Finding not in the brief**: the manifest's own G3 text names
`turn_structure.json`'s G13 as the seam gap this divergence depends on; that
citation is now WRONG (G13 is closed) even though the divergence it points
at is still real. The correct seam citation is simply "no site recomputes
win between the turn-start dispatch and the true `CheckWinCondition` call" —
which `turn_structure.json` does not currently name as its own open gap
anywhere I could find (grepped for "step 27" and "CombatManager.cs:573" —
no hit). Recommend the controller file this as a fresh, narrow
`turn_structure` gap rather than leave G3's citation dangling on a closed
guard.

Citations: `FestivePopper.cs:17-28`, `CombatManager.cs:573`,
`sts2_rl/relics/festive_popper.py:21-29`, `sts2_rl/combat.py:1360-1391`
(`_start_player_turn`), `sts2_rl/relics/base.py:483-488` (`_check_win`).

### `relic/gambling_chip/AfterPlayerTurnStart` (G1, G2) — DORMANT-ENUMERATED (G2 reasoning strengthened)

G3 (min-0 decline) is already `faithful`/closed — `"gambling_chip"` is in
`driver.py`'s `SKIPPABLE_PURPOSES` (`driver.py:98-101`, which contains both
it and `"obtain"`). Unaffected, not re-derived here. `[CORRECTED → §6]` — an
unedited self-correction fragment stood here in the first pass.

G1 (Sly auto-play): re-confirmed dormant, and the machinery has grown since
the 2026-07-26 audit without becoming reachable. `cards/base.py` now
declares a real `sly: bool = False` attribute plus `is_sly_this_turn`
(`:508-510`) and `give_single_turn_sly`/its clear
(`:517-530`) — genuine ported machinery, not merely absent. Executed
census (`test_is_sly_this_turn_and_give_single_turn_sly_have_zero_
consumers`): zero of the 203+ registered card classes set `sly = True`, and
a full-package text scan finds zero call sites for `give_single_turn_sly(`
outside its own definition. Nothing sets Sly, and nothing reads it as a
discard-then-auto-play trigger — the gap is unchanged in shape, only in how
much scaffolding sits around it unused.

G2 (raw list mutation vs `CardCmd.DiscardAndDraw`'s `CardPileCmd.Add`,
which fires `Hook.AfterCardChangedPiles`) — **STRONGER dormancy reason than
the 2026-07-26 audit found.** The record's own text says the one C# hook
with "ported implementers" is `AfterCardChangedPiles(Late)`; that is now
falsifiable directly: `hooks.py` gained a real, wired
`after_card_changed_piles` dispatcher this round (`hooks.py:1406-1455`),
fired from 6 real call sites including `CardPileCmd.add_to_discard` — the
exact verb `CardCmd.DiscardAndDraw` routes through in C#, and exactly what
`gambling_chip.py`'s raw `player.discard_pile.append(card)` bypasses.
Executed census
(`test_after_card_changed_piles_has_zero_ported_implementers`): scanning
every registered relic/power/card/potion/enchantment class
(`ALL_RELICS`/`ALL_POWERS`/`_CARD_CLASSES`/`ALL_POTIONS`/
`ALL_ENCHANTMENTS`), **zero** implement `after_card_changed_piles` or its
`_late` phase. The record's cited "ported implementers"
(`book_of_five_rings`, `bing_bong`, `darkstone_periapt`, `lucky_fysh`) are
confirmed, by reading `hooks.py`'s own docstring for the hook
(`:1443-1447`), to be listeners on a DIFFERENT, run-scoped hook
(`Relic.after_card_added_to_deck`, filtered to `PileType.Deck`) — not this
one. So the machinery this round wired for the hook gambling_chip's G2 is
about has, today, exactly as many listeners as it did before: zero.

Citations: `GamblingChip.cs:18-32`, `CardCmd.cs:186-204`,
`sts2_rl/relics/gambling_chip.py:23-37`, `sts2_rl/cards/base.py:165-169,
508-530`, `sts2_rl/hooks.py:1406-1455`, `sts2_rl/player.py:441,482,588`
(the three combat-side `after_card_changed_piles` call sites), `sts2_rl/
cmds.py:1346,1464`.

### `relic/hefty_tablet/AfterObtained` (G2) — ~~DORMANT-ENUMERATED~~ **LIVE** `[CORRECTED → §6.7]`

> **VERDICT OVERTURNED by the fix pass.** G2 is not dormant: the offer-time
> census below measured a bare `RunState` that holds no relics at all, so the
> loop asserted nothing. The state that matters is the one at the moment the
> screen opens, and a reward-options relic is reachable there. The census is
> also 10 implementers, not 7. Executed evidence and the file-ready write-up
> are in §6.7. Everything else in this entry (G1/G3 faithful, the spy
> demonstration of the mechanism) stands.

G1 (candidate pool) and G3 (declinable screen) are already `faithful`
(closed round 7/round-of-2026-07-27); re-verified both are still true today:
`hefty_tablet.py:35` still calls `reward_pool_card_ids(pool=run.card_pool)`
(the reward-stream helper, not the combat-filtered one), and `"obtain"` is
still in `driver.py`'s `SKIPPABLE_PURPOSES`
(`test_hefty_tablet_obtain_purpose_is_still_skippable`). No further work
needed on either.

G2 (dropped `Hook.TryModifyCardRewardOptions`/`Late` pass) stays `gap`,
dormant — **implementer count refreshed from 4 to 7**: `silver_crucible`,
`silken_tress`, `_eggs`, `glitter` (the record's original four) plus
`fresnel_lens`, `lava_lamp`, `wing_charm` now also implement
`modify_card_reward_options_late`. Direct mechanism demonstration
(`test_hefty_tablet_after_obtained_never_calls_modify_card_reward_options`):
a spy relic standing in for any of the seven, co-held with `hefty_tablet` in
a hand-built `RunState`, sees **zero** calls when `hefty_tablet.after_
obtained(run)` runs — the sim builds its three-Rare candidate list directly
and hands it to `run.select_cards`, never touching `run.relics`' reward-
options hooks.

Reachability re-confirmed, not inherited: `grep -rl hefty_tablet sts2_rl/`
still returns exactly two files, `relics/hefty_tablet.py` and
`events/neow.py` — the relic's only grant path remains the floor-0 Neow
event. A fresh `RunState()` at `total_floor == 0` holds no relic implementing
either reward-options hook
(`test_hefty_tablet_g2_reachability_floor0_holds_no_reward_modifying_relic`).

Citations: `HeftyTablet.cs:29`, `CardFactory.cs:104-107,214-217`,
`sts2_rl/relics/hefty_tablet.py:17-54`, `sts2_rl/relics/base.py:289-309`
(`modify_card_reward_options`/`_late`), `sts2_rl/relics/silver_crucible.py:28`,
`silken_tress.py:27`, `_eggs.py:46`, `glitter.py:16`, `fresnel_lens.py:37`,
`lava_lamp.py:58`, `wing_charm.py:19`, `sts2_rl/events/neow.py`,
`sts2_rl/driver.py:98-101`.

### `relic/letter_opener/AfterCardPlayed` (G2) — DORMANT-ENUMERATED (re-confirmed)

G1 (per-Replay bracket) already closed, unaffected. G2 (enemy set): same
mechanism, same dormancy proof as `bag_of_marbles`/`charons_ashes` above —
`letter_opener.py:40` still iterates `self.living_enemies()` then
`DamageCmd.deal`. `[CORRECTED → §6]` — "backstopped identically" is wrong,
for the same reason as `charons_ashes` (§6.1): the `DamageCmd.deal`
`should_allow_hitting` line is unreachable, so dormancy here rests on
set-coincidence alone. Verdict unchanged.

Citations: `LetterOpener.cs:109-121`, `CombatState.cs:142`,
`Creature.cs:285-299`, `sts2_rl/relics/letter_opener.py:33-45`,
`sts2_rl/cmds.py:245-289`.

### `relic/paper_phrog/ModifyVulnerableMultiplier` (G1, N2) — DORMANT-ENUMERATED (re-confirmed)

G1 (hook chain vs C#'s single direct lookup) is dormant iff `paper_phrog`
is the sim's only `modify_vulnerable_multiplier` implementer. Re-executed
census over `ALL_RELICS`
(`test_paper_phrog_is_still_the_sole_modify_vulnerable_multiplier_implementer`):
still exactly one. Unaffected by R1's listener-derivation rework
(`modify_vulnerable_multiplier` is still a single flat `_each` fold,
`hooks.py:1033-1041` — no phase, no per-creature grouping subtlety to
re-derive here).

N2 (target check: C# skips when the Vulnerable creature IS the phrog's own
owner; the sim checks only the dealer) is dormant iff no ported content
deals POWERED damage from the player to the player. Re-executed with real
play (`test_paper_phrog_n2_brand_self_damage_is_not_a_powered_attack`,
instrumented `DamageCmd.deal` spy, `cs.play_card(0)` on Brand — the one
self-damage card whose source explicitly names the player as BOTH dealer
and target with an explicit `props` argument): Brand's self-hit is real
(the census actually observed it) and is confirmed UNPOWERED
(`DamageProps.CARD_HP_LOSS` carries `UNPOWERED`). The other 12 self-damage
sites (read directly, not executed individually, given the 13th — Brand —
is the only one combining a REAL `dealer=ctx.player` with a target of the
player; the rest pass `dealer=None` or the same `CARD_HP_LOSS` shape):
`blood_wall`, `bloodletting`, `burn`, `decay`, `hemokinesis`, `infection`,
`offering`, `regret`, `toxic`, `wither`, `bad_luck`, `beckon` — none
combines a player dealer with powered props.

Citations: `PaperPhrog.cs:16-26`, `VulnerablePower.cs:22,40-44`,
`sts2_rl/relics/paper_phrog.py:21-24`, `sts2_rl/cards/brand.py:37-56`,
`sts2_rl/valueprops.py:36-49`.

### `relic/philosophers_stone/AfterCreatureAddedToCombat` (G1) — DORMANT-ENUMERATED (re-confirmed)

C# skips creatures on the OWNER's SIDE (`PhilosophersStone.cs:43`); the sim
skips only the player OBJECT (`philosophers_stone.py:39`). Re-confirmed the
sim models exactly one player-side creature: `CombatState.__init__` takes
no player-side-creature parameter and `CreatureCmd.add`'s only destination
is `combat.enemies` (`cmds.py`, unaffected by R1's rework — R1's own G5
closure made `Monster` a hook LISTENER, it did not add a second player-side
creature slot). Executed
(`test_on_creature_added_only_ever_reaches_combat_enemies`): a fresh
`LeafSlimeS` added via `CreatureCmd.add` lands in `cs.enemies`, receives
Philosopher's Stone's Strength(1) like any other joiner, and there is no
code path by which it — or anything else — could arrive as a player-side
non-player creature for the side-vs-identity distinction to bite on.

Citations: `PhilosophersStone.cs:43`, `sts2_rl/relics/philosophers_stone.py:34-41`,
`sts2_rl/cmds.py` (`CreatureCmd.add`), `sts2_rl/combat.py` (`CombatState.__init__`).

### `relic/ruined_helmet/TryModifyPowerAmountReceived` (G2, G3) — STALE-ALREADY-FIXED

**The record's own citations name the exact seam guards that closed 2026-07-31
(tier-2 campaign, Task 17/18) — five days after this record's 2026-07-26
audit and, notably, AFTER R4's sibling batch already flagged the same class
of staleness for `unsettling_lamp` in this same wave.** `seam/
power_cmd.json` guard G3 ("C#'s three ordered phases... collapsed into one
registration-order-dependent chain; Artifact bypasses the hook-listener
system entirely") now reads `verdict: faithful`, `"Closed 2026-07-31 (tier-2
campaign): C#'s three ordered phases are now three separate dispatches."`
Guard G4 ("No AfterModifyingPowerAmountGiven/Received companion-event
machinery") reads the same close date and status.

Read the current tree directly rather than trusting either date stamp:
`hooks.py` now declares `modify_power_amount_given_additive` (`:910-938`),
`modify_power_amount_given_multiplicative` (`:940-960`) and
`modify_power_amount_received` (`:962-992`) as three SEPARATE dispatchers —
not the one collapsed `modify_power_amount` the record's `maps_to` line
still names. `PowerCmd.apply` (`cmds.py:882-918`) calls them in C#'s own
order: the GIVEN chain gated on `applier is not None and
_combat_contains_creature(hooks, applier)` (`PowerCmd.cs:122-123`), THEN the
RECEIVED chain unconditionally (`Hook.cs:1917-1930` has no applier gate).
`ruined_helmet.py` has ALREADY been rewritten to match: it implements
`modify_power_amount_received` (a real single-pass override-or-decline
listener, `ruined_helmet.py:27-57`) — exactly the RECEIVED-side phase the
record's G2 said was "collapsed into the sim's single flat chain."

Re-executed (`test_ruined_helmet_doubles_once_via_the_real_received_chain`):
a first `PowerCmd.apply(hooks, player, StrengthPower, 2, applier=player)`
doubles to 4 and sets `relic._used`; a second application does NOT double
(the received chain now declines), landing at 6 total — the exact answer
the record's own already-executed probe names ("a first +2 Strength lands
as 4 and a second as +2 (total 6)").

Citations: `RuinedHelmet.cs:32-53`, `PowerCmd.cs:120-127,215-234`,
`Hook.cs:1884-1930`, `sts2_rl/relics/ruined_helmet.py:27-57`,
`sts2_rl/hooks.py:896-992`, `sts2_rl/cmds.py:882-936`,
`audit/records/seam/power_cmd.json` guards G3/G4 ("Closed 2026-07-31").

### `relic/ruined_helmet/AfterModifyingPowerAmountReceived` (G3) — STALE-ALREADY-FIXED

Same underlying fix as the entry above (`power_cmd/G4`). The record's G3
text: "the mark used side effect is hand-inlined into the modifier, so it
fires at a point C# would not have reached." That is no longer true:
`ruined_helmet.py:59-62` now implements `after_modify_power_amount_
received` as its OWN separate method — the real companion event
(`hooks.py:1012-1031`, dispatched from `cmds.py:934-936` and `:1024-1025`),
fired only for listeners whose modifier actually changed the amount, exactly
mirroring `RuinedHelmet.cs:55-60`/`Hook.cs:811-824`'s
`AfterModifyingPowerAmountReceived`.

Directly proved the mark-used effect no longer lives inside the modifier
(`test_ruined_helmet_mark_used_lives_in_the_companion_event_not_the_
modifier`): calling `relic.modify_power_amount_received(...)` alone (the
bare modifier, bypassing `PowerCmd.apply`'s own companion-event dispatch)
returns the doubled amount but leaves `relic._used` **False** — only a
subsequent, explicit call to `relic.after_modify_power_amount_received(...)`
sets it. This is the structural proof the record's own G3 divergence — the
side effect firing at a point C# would not have reached — is now
impossible: the two are separate methods, dispatched separately, exactly
where the guard says they should be.

Citations: `RuinedHelmet.cs:55-60`, `Hook.cs:811-824`, `PowerCmd.cs:148-152,
238-242`, `sts2_rl/relics/ruined_helmet.py:59-62`,
`sts2_rl/hooks.py:1012-1031`, `audit/records/seam/power_cmd.json` guard G4
("Closed 2026-07-31").

### `relic/spiked_gauntlets/TryModifyEnergyCostInCombat` (G1, G2, G3) — NARROWED (G1 already closed, G2 flips STALE-ALREADY-FIXED, G3 stays dormant)

G1 (cross-listener order, Powers before Relics) was already reconciled
`faithful` 2026-07-28 (Task 0, predating this round's audit entirely) — the
record's own guard text already carries this; nothing to re-derive, and the
manifest's hook-level rollup text ("Rollup of guards G1, G2 and G3") is
stale in NAMING G1 as still open. Re-confirmed live via the G2 test below
(CuriousPower still runs before SpikedGauntlets in the plain pass).

**G2 (the missing plain/Late two-pass structure) — STALE-ALREADY-FIXED,
closed BEFORE round 13.** `[CORRECTED → §6.4]` — the first pass called this
"a FRESH closure this round" and attributed it to `hooks.py`'s `_each`
"this round"; `git show HEAD` proves the machinery predates the round.
`hooks.py`'s `_each` generalized the phase
machinery: any hook with a registered listener defining a `_very_early`/
`_early`/`_late` variant now automatically gets the full multi-pass walk
(`_PHASES`, `hooks.py:600-679`) — not just the two hooks the sim used to
hand-roll before this round. `modify_card_energy_cost` gets this for free
the moment ANY listener defines `modify_card_energy_cost_late` — which
`BrilliantScarf` (this batch's own Late-side witness, cited by the record's
own G2 text) already does (`relics/brilliant_scarf.py:29-33`). Re-executed
the record's own worked example
(`test_spiked_gauntlets_g2_phase_machinery_now_generic_via_each`): with
`CuriousPower(2)` + `SpikedGauntlets` (both plain) + `BrilliantScarf` (late,
armed for the 5th card), a 1-cost Power card resolves to **0** — the plain
pass gives `1-2=0` (Curious) then `0+1=1` (Spiked), and the Late pass then
zeroes it regardless, matching the C# guard's own stated answer ("1-cost
Power: 1+1=2 in the plain pass and then Brilliant Scarf's Late pass zeroes
it to 0" — the sim's intermediate value differs by one arithmetic step
because Curious floors early, but the FINAL Late-pass-wins answer is
identical: 0). Isolated (no Scarf, no phase forcing), the same chain gives
1 (`0` then `+1`), confirming the plain pass alone is unaffected — the
phase machinery is additive, not a behaviour change to the un-phased case.

G3 (X-cost bail / owner guard / final clamp) stays `gap`, dormant, census
re-executed rather than inherited
(`test_spiked_gauntlets_g3_x_cost_cards_are_still_never_powers`): the three
X-cost cards remain `cascade`, `volley` (in `colorless_attacks.py`) and
`whirlwind` — a fresh scan over every registered card class for
`energy_cost_x`-truthy instances confirms none is `CardType.POWER`.

**Propose narrowing the hook-level rollup text** from "Rollup of guards G1,
G2 and G3" to "G3 only; G1 and G2 are both independently closed."

Citations: `SpikedGauntlets.cs:27-39`, `Hook.cs:1574-1590`,
`CuriousPower.cs`, `sts2_rl/relics/spiked_gauntlets.py:26-31`,
`sts2_rl/relics/brilliant_scarf.py:29-33`, `sts2_rl/powers.py:3557-3572`
(`CuriousPower`), `sts2_rl/hooks.py:48-50,600-679` (`_PHASES`, `_each`),
`sts2_rl/cards/inflame.py`, `sts2_rl/cards/base.py` (`energy_cost_x`
census).

### `relic/stone_cracker/AfterRoomEntered` (G2) — DORMANT-ENUMERATED (re-confirmed, order-independence proven live)

G1 (shuffle orientation) already closed, unaffected. G2 (hook slot:
`AfterRoomEntered` fires one full dispatch before `Hook.BeforeCombatStart`;
the sim's `on_combat_start` IS the `BeforeCombatStart` slot) is unrelated to
this round's listener-*derivation* rework — `combat.py:327`'s single
`hooks.on_combat_start()` call is unchanged, and this guard is about WHICH
dispatch fires when, not the order WITHIN one dispatch. Re-confirmed dormant
with fresh, direct execution rather than inheriting the record's census:
`test_stone_cracker_and_tea_of_discourtesy_are_order_independent` builds two
combats with `stone_cracker`/`tea_of_discourtesy` in each order and confirms
an IDENTICAL outcome (2 cards upgraded, 2 Dazed added, counted across
`player.all_cards` since both relics' `on_combat_start` fires before the
turn-1 opening draw and their cards can land in either the draw pile or the
opening hand). Confirms the record's reachability argument (Dazed is never
upgradable; the two relics draw from different RNG streams —
`CombatCardSelection` vs `Shuffle`) holds by direct demonstration, not
assertion.

Citations: `StoneCracker.cs:25-27`, `CombatRoom.cs:228`,
`CombatManager.cs:380-403`, `sts2_rl/relics/stone_cracker.py:17-39`,
`sts2_rl/relics/tea_of_discourtesy.py`, `sts2_rl/combat.py:327`.

### `relic/sword_of_jade/AfterRoomEntered` (G1) — DORMANT-ENUMERATED (re-confirmed)

Same hook-slot mechanism as `stone_cracker/G2` (binding rule 3, the record's
own "the same guard on relic/stone_cracker in this batch carries the same
verdict for the same census"). Re-executed the census fresh, not inherited:
`test_sword_of_jade_g1_no_other_combat_start_listener_reads_strength` scans
every `on_combat_start` implementer outside the twelve AfterRoomEntered-side
relics for a Strength READ (as opposed to a Strength GRANT, which is
order-independent) — zero found. `[CORRECTED → §6.6]` — as written that
overstated the first pass's own test, which iterated `ALL_RELICS` only. The
test has since been widened to walk the MRO and to scan the whole package
(it now also covers `powers.py`'s `vital_spark` and `galvanic`, neither of
which reads Strength), so the sentence is true of the CURRENT test.
`sling_of_courage` (an Elite-only +2
Strength grant) surfaces in a naive text search but is confirmed, by
reading it, to be a pure grant with no dependency on any existing Strength
value, so it does not expose the ordering gap either.

N1 (applier identity, `applier=None` in C# vs `applier=self.player` in the
sim) is already `faithful` — its own census (four applier-branching
listeners, all unreachable for a self-targeted positive Strength grant) is
unaffected by anything this round touched; re-read `unsettling_lamp.py`,
`ruined_helmet.py` and the Possess-family powers to confirm none of their
gates changed shape in a way that would matter here. Not re-derived in full
(N1 is not part of my manifest), flagged as re-checked in passing.

Citations: `SwordOfJade.cs:23-29`, `CombatRoom.cs:228`,
`sts2_rl/relics/sword_of_jade.py:17-29`, `sts2_rl/relics/sling_of_courage.py`.

### `relic/vambrace/g6` (N3) — FIXED

The docstring bug the entry names is real and — after a full file rewrite
elsewhere in round 13 that split the mechanism into `after_modify_block_
amount`/`on_card_played` (round 7, already closed as G3) — is **now doubly
wrong**: it still claims "The multiplier hook stays stateless (safe for
previews)" (false: `modify_block_multiplicative` reads `_triggering_card`/
`_used`) AND "the one-shot flag is set from the real on_block_gained event"
(false: **Vambrace** has no `on_block_gained` method and `Vambrace.cs`
overrides no `AfterBlockGained`; the flag is set by `on_card_played`).
`[CORRECTED → §6.5]` — the first pass wrote "there is no `on_block_gained`
method anywhere in the current file **or the game**", and shipped that same
unscoped claim into the replacement docstring. It is false: `AfterBlockGained`
is a real hook in BOTH engines.

**Fix**: rewrote the class docstring
(`sts2_rl/relics/vambrace.py:14-29` after the fix pass) to state what the
code actually does — the multiplier hook READS the two fields (safe for
previews because only `after_modify_block_amount`/`on_card_played` write
them **during a card play**; `__init__` and `reset_for_combat` also write
them, but only to clear) — and name
the real two-method split (`after_modify_block_amount` latches
`_triggering_card`, `on_card_played` spends `_used`) with their C# line
citations. No behaviour changed — G3, the guard this docstring used to
justify, has read `faithful`/"Closed 2026-07-29 (round 7)" the whole time;
this entry's own text already says so ("the verdict-carrying divergence is
G3's, not this entry's").

**RED evidence** (per the no-revert rule, verified by direct text
comparison rather than reverting the file): the OLD docstring text — "The
multiplier hook stays stateless (safe for previews); the one-shot flag is
set from the real on_block_gained event." — contains both banned phrases
the new test asserts against (`"stays stateless"`, `"set from the real
on_block_gained"`); the NEW docstring contains neither. **GREEN**:
`test_vambrace_docstring_no_longer_claims_statelessness_or_on_block_gained`
passes against the committed fix.

Citations: `Vambrace.cs:57-113`, `sts2_rl/relics/vambrace.py:14-21` (before
and after), `audit/records/relic/vambrace.json` guard G3
("Closed 2026-07-29 (round 7): STALE, not open").

---

## 2. Record-close proposals

> **SUPERSEDED — do not apply this section.** The controller should apply
> **§6.9** instead. Proposals 1, 2, 3, 5, 6, 11 and 13 ship errors the review
> caught; #5's verdict is overturned outright. §6.9 is the complete,
> corrected replacement for all fourteen.

Record files are `audit/records/relic/<name>.json` unless noted.

1. **`bag_of_marbles.json`, hook key `BeforeSideTurnStart`** → stays `gap`.
   Close note: no verdict change. Replace the `issue` text's premise ("the
   sim's living_enemies() filters on `not e.is_gone` ONLY... PowerCmd.apply
   does not apply [should_allow_hitting] either — that absence is
   `seam/power_cmd.json` gap G6") with: *`power_cmd/G6` closed 2026-07-28
   (round 4), before this record's own 2026-07-26 audit date was last
   revisited. `PowerCmd.apply` now backstops every application via
   `can_receive_powers` (`cmds.py:65-75,841`), exactly as `DamageCmd.deal`
   already backstops `charons_ashes`/`festive_popper`/`letter_opener` in
   this batch. Dormancy is unaffected (the call site itself is still built
   from `living_enemies()`, not `hittable_enemies()`), but the reason is now
   "a full, closed backstop", not "no backstop at all". Re-executed
   2026-08-01 (round 13, R8): `test_should_allow_hitting_false_still_
   coincides_with_is_gone`, `test_power_cmd_apply_backstops_bag_of_marbles_
   against_an_unhittable_target`.*

2. **`charons_ashes.json`, hook key `AfterCardExhausted`** → stays `gap`. No
   text change proposed (still accurate); re-executed 2026-08-01:
   `test_damage_cmd_deal_backstops_the_damage_relics_against_an_unhittable_
   target`.

3. **`festive_popper.json`, hook key `AfterPlayerTurnStart`** → stays `gap`.
   Close note: G3's citation of `turn_structure.json` gap `G13` is now
   **stale** — G13 closed 2026-07-29 (round 5), but every site it fixed is
   at turn END, none between the turn-start dispatch and C#'s real
   `CheckWinCondition` call (`CombatManager.cs:573`, step 27). *Recommend
   the controller either (a) retarget this citation at a fresh, narrowly-
   scoped `turn_structure` gap for the turn-START window specifically
   (grepped: no such gap currently named in that record), or (b) drop the
   citation and restate the divergence directly against `combat.py`'s
   `_start_player_turn`, which has no recompute call between `player.
   start_turn()`'s hooks and its return. Re-executed 2026-08-01: `test_
   festive_popper_check_win_still_ends_combat_inside_its_own_dispatch`.*

4. **`gambling_chip.json`, hook key `AfterPlayerTurnStart`** → stays `gap`.
   Close note for guard G2: *`hooks.after_card_changed_piles` is now real,
   wired machinery (6 call sites, round 13), but STILL has zero listeners
   anywhere in the package — re-executed full census over ALL_RELICS/
   ALL_POWERS/_CARD_CLASSES/ALL_POTIONS/ALL_ENCHANTMENTS. The record's
   cited "ported implementers" (book_of_five_rings/bing_bong/
   darkstone_periapt/lucky_fysh) are `after_card_added_to_deck` listeners —
   a different, run-deck-filtered hook — not this one; this is a citation
   correction, not new content. G1's Sly-keyword machinery has grown
   (`is_sly_this_turn`/`give_single_turn_sly` are now real methods, not
   absent) but remains fully unconsumed — re-executed a full-package
   call-site scan finds zero callers of `give_single_turn_sly(`. Re-executed
   2026-08-01: `test_is_sly_this_turn_and_give_single_turn_sly_have_zero_
   consumers`, `test_after_card_changed_piles_has_zero_ported_
   implementers`.*

5. **`hefty_tablet.json`, hook key `AfterObtained`** → stays `gap` (via G2
   alone; G1/G3 already `faithful`). Close note: *implementer count for the
   `modify_card_reward_options(_late)` census grew from 4 to 7
   (fresnel_lens, lava_lamp, wing_charm joined silver_crucible/silken_tress/
   _eggs/glitter). Reachability argument (Neow-only, floor 0) re-confirmed
   unchanged by grep and by a fresh `RunState()` check. Re-executed
   2026-08-01: `test_hefty_tablet_after_obtained_never_calls_modify_card_
   reward_options`, `test_hefty_tablet_g2_reachability_floor0_holds_no_
   reward_modifying_relic`, `test_hefty_tablet_obtain_purpose_is_still_
   skippable`.*

6. **`letter_opener.json`, hook key `AfterCardPlayed`** → stays `gap`. No
   text change; same mechanism as entries 1-3, matched under binding rule 3.

7. **`paper_phrog.json`, hook key `ModifyVulnerableMultiplier`** → stays
   `gap`. Close note for N2: *the record's dormancy census is re-executed
   with a real play (`Brand`, the one self-damage card combining a real
   `dealer=ctx.player` with an explicit `props` argument) rather than
   inherited; confirmed unpowered. Re-executed 2026-08-01: `test_paper_
   phrog_is_still_the_sole_modify_vulnerable_multiplier_implementer`, `test_
   paper_phrog_n2_brand_self_damage_is_not_a_powered_attack`.*

8. **`philosophers_stone.json`, hook key `AfterCreatureAddedToCombat`** →
   stays `gap`. No text change; re-executed 2026-08-01: `test_on_creature_
   added_only_ever_reaches_combat_enemies`.

9. **`ruined_helmet.json`, hook key `TryModifyPowerAmountReceived`** →
   verdict `faithful`. Close note: *replaces "the RECEIVED-side phase being
   collapsed into the sim's single flat chain (G2)" — `hooks.py` now
   dispatches `modify_power_amount_given_additive`/`_multiplicative`/
   `modify_power_amount_received` as three separate calls, matching
   `PowerCmd.cs:120-127`/`:227-234` exactly, and `ruined_helmet.py` is a
   real listener on the RECEIVED chain alone (`modify_power_amount_
   received`, `ruined_helmet.py:27-57`). `seam/power_cmd.json`'s own G3
   closed 2026-07-31 (Task 17), five days after this record's audit date;
   this record's copy of the same guard was never flipped to match.
   Pinned: test_r13_relic2.py::test_ruined_helmet_doubles_once_via_the_
   real_received_chain.* Also close **guard G2** in this record's own
   `guards` array with the same note.

10. **`ruined_helmet.json`, hook key `AfterModifyingPowerAmountReceived`** →
    verdict `faithful`. Close note: *replaces "the After-event's side effect
    being hand-inlined (G3)" — `after_modify_power_amount_received` is now
    ruined_helmet.py's OWN separate method (`:59-62`), dispatched by
    `hooks.py`'s real companion event (`:1012-1031`) only for listeners
    whose modifier actually fired, matching `RuinedHelmet.cs:55-60` exactly.
    `seam/power_cmd.json`'s own G4 closed the same day (2026-07-31, Task
    18). Proved structurally: calling the bare modifier does NOT itself set
    `_used`; only the companion event does. Pinned: test_r13_relic2.py::
    test_ruined_helmet_mark_used_lives_in_the_companion_event_not_the_
    modifier.* Also close **guard G3** in this record's own `guards` array
    with the same note.

11. **`spiked_gauntlets.json`, hook key `TryModifyEnergyCostInCombat`** →
    stays `gap` (via G3 alone; G1 already `faithful`, G2 now closes too).
    Close note for guard G2: *replaces "the sim has no phase structure and
    no per-creature listener grouping" — `hooks.py`'s `_each` generalized
    the plain/VeryEarly/Early/Late multi-pass shape to EVERY hook a
    registered listener phases into this round, not just the two hooks the
    sim hand-rolled before. `modify_card_energy_cost` inherits it for free
    once `BrilliantScarf` (this record's own cited Late-side witness) is
    registered. Re-executed the guard's own worked example (CuriousPower +
    SpikedGauntlets plain, BrilliantScarf Late, a 1-cost Power card): both
    engines now land on 0. Pinned: test_r13_relic2.py::test_spiked_
    gauntlets_g2_phase_machinery_now_generic_via_each.* Also propose
    rewriting the hook-level entry's `issue` text from "Rollup of guards
    G1, G2 and G3" to name G3 alone.

12. **`stone_cracker.json`, hook key `AfterRoomEntered`** → stays `gap`. No
    text change; the record's own reachability argument re-confirmed by
    DIRECT execution (order-independence with `tea_of_discourtesy`, both
    orders, identical outcome) rather than by census alone. Re-executed
    2026-08-01: `test_stone_cracker_and_tea_of_discourtesy_are_order_
    independent`.

13. **`sword_of_jade.json`, hook key `AfterRoomEntered`** → stays `gap`. No
    text change; re-executed the 12-relic AfterRoomEntered-side census
    fresh (source scan for a Strength READ, not merely a mention).
    Re-executed 2026-08-01: `test_sword_of_jade_g1_no_other_combat_start_
    listener_reads_strength`.

14. **`vambrace.json`, guard key `N3` (`g6` in the manifest)** → verdict
    `faithful`. Close note: *the docstring fix landed
    (`sts2_rl/relics/vambrace.py:14-21`). The underlying G3 divergence this
    entry warned readers not to mistake as intentional has been closed
    since round 7 (2026-07-29); this entry's own text already said so. No
    behavioural change; RED-then-GREEN via direct text comparison (see
    §1). Pinned: test_r13_relic2.py::test_vambrace_docstring_no_longer_
    claims_statelessness_or_on_block_gained.*

---

## 3. Queue-annotation proposals (`audit/GAP-QUEUE.md`, terse house style)

> **SUPERSEDED — do not apply this section.** Apply **§6.10** instead.

- `relic/bag_of_marbles/BeforeSideTurnStart` — dormant — re-executed
  2026-08-01: `power_cmd/G6`'s round-4 close backstops `PowerCmd.apply`
  against an unhittable target exactly like `DamageCmd.deal` already
  backstops the batch's damage relics; the record's "no backstop" premise
  was stale by three rounds. Call site still architecturally wrong
  (`living_enemies()` not `hittable_enemies()`); goes live on a second
  `should_allow_hitting` implementer not gated on `is_reviving`.
- `relic/charons_ashes/AfterCardExhausted` — dormant — re-executed
  2026-08-01, unaffected by this round's engine work; same coincidence
  proof as bag_of_marbles.
- `relic/festive_popper/AfterPlayerTurnStart` — dormant — re-executed
  2026-08-01: G3's own citation (`turn_structure/G13`) is now closed but
  fixed only turn-END sites; the turn-START gap this relic's inline
  `_check_win()` compensates for is still unaddressed anywhere else. Needs
  a fresh, correctly-scoped seam citation.
- `relic/gambling_chip/AfterPlayerTurnStart` — dormant — re-executed
  2026-08-01: `after_card_changed_piles` machinery landed this round (6
  wired call sites) but still has ZERO package-wide listeners; Sly
  machinery (`is_sly_this_turn`/`give_single_turn_sly`) similarly grew but
  stays fully unconsumed.
- `relic/hefty_tablet/AfterObtained` — dormant (G2 only; G1/G3 already
  closed) — re-executed 2026-08-01: `modify_card_reward_options(_late)`
  implementer count 4 -> 7; reachability (Neow-only, floor 0) unchanged.
- `relic/letter_opener/AfterCardPlayed` — dormant — re-executed 2026-08-01,
  same mechanism as bag_of_marbles/charons_ashes.
- `relic/paper_phrog/ModifyVulnerableMultiplier` — dormant — re-executed
  2026-08-01: still the sole `modify_vulnerable_multiplier` implementer;
  Brand's real self-hit confirmed unpowered by live execution.
- `relic/philosophers_stone/AfterCreatureAddedToCombat` — dormant —
  re-executed 2026-08-01: `CreatureCmd.add`'s only destination is
  `combat.enemies`, confirmed with a real mid-combat spawn.
- `relic/ruined_helmet/TryModifyPowerAmountReceived` and
  `/AfterModifyingPowerAmountReceived` — **CLOSED 2026-08-01**: `seam/
  power_cmd.json` G3+G4 closed 2026-07-31 (Task 17/18); ruined_helmet.py
  already rewritten to the new given/received-split machinery with a real
  companion event. No code change needed here — this record's copy of the
  guards was simply never flipped.
- `relic/spiked_gauntlets/TryModifyEnergyCostInCombat` — NARROWED
  2026-08-01: G1 (cross-listener order) already closed round 4; G2 (plain/
  Late phase structure) CLOSES this round — `_each`'s phase generalization
  covers it for free the moment BrilliantScarf is registered. G3 (X-cost
  bail) stays dormant, re-confirmed: cascade/volley/whirlwind still the
  only X-cost cards, still zero Powers among them.
- `relic/stone_cracker/AfterRoomEntered` — dormant — re-executed
  2026-08-01, with a direct order-independence demonstration (not just a
  census) against tea_of_discourtesy.
- `relic/sword_of_jade/AfterRoomEntered` — dormant — re-executed
  2026-08-01, same 12-relic census, sling_of_courage checked and cleared
  (grants Strength, does not read it).
- `relic/vambrace/g6` — **CLOSED 2026-08-01**: docstring fixed
  (`sts2_rl/relics/vambrace.py`); no behaviour change, G3 (the divergence
  it used to justify) has been closed since round 7.

---

## 4. Tests

**Added**: `test/test_r13_relic2.py` (new, 19 tests, all passing).

**Production edit**: `sts2_rl/relics/vambrace.py` (docstring only, entry 14
above).

**Commands run**:

```
py -m pytest test/test_r13_relic2.py -v
  -> 19 passed

py -m pytest test/test_r13_relic2.py test/test_r13_relic1.py test/test_relics.py \
  test/test_relic_live_tail.py test/test_relic_residue_gaps.py \
  test/test_relic_tier1_gaps.py test/test_tier1_last_five.py test/test_hook_order.py \
  test/test_power_type_for_amount.py test/test_power_modifier_phases.py \
  test/test_combat_over_hook_gate.py test/test_powers.py \
  test/test_round13_listener_derivation.py -q
  -> 557 passed

py -m pytest test/ -k vambrace -q
  -> 4 passed, 3859 deselected
```

No `audit/records/**` or `audit/GAP-QUEUE.md` file was edited. No git index
command was run. `git status --short sts2_rl/relics/ test/test_r13_relic2.py`
shows only `M sts2_rl/relics/vambrace.py` and the new untracked test file;
`relics/base.py`'s ` M` status belongs to another lane, unedited by me.

---

## 5. Findings not in the brief

1. **`bag_of_marbles/G2`'s dormancy citation was stale by THREE rounds, not
   by this round's engine work.** `power_cmd/G6` (the `CanReceivePowers`
   backstop in `PowerCmd.apply`) closed 2026-07-28 (round 4) — before this
   record's own 2026-07-26 audit date implies it should have been current.
   This is the R1-brief's warning materializing in a shape the brief did not
   name: not a listener-derivation change, but a plain missed-revisit on a
   fix from a different, earlier fix wave entirely. Worth a general sweep:
   any record whose dormancy argument leans on a *named, still-open* guard
   in another record should be re-checked whenever that OTHER record's
   guard closes, not just when the citing record's own subject file changes.

2. **`festive_popper/G3`'s seam citation (`turn_structure/G13`) is now
   pointing at a CLOSED guard while the divergence it names is still open.**
   G13 closed 2026-07-29 (round 5) by fixing six turn-END recompute sites;
   none of them touches the turn-START window between the hook dispatch and
   C#'s true `CheckWinCondition` call (`CombatManager.cs:573`, step 27).
   `turn_structure.json` does not appear to carry a gap for this specific
   window under any name I could find by grep. Recommend filing a narrow,
   correctly-scoped gap there rather than leaving festive_popper's own
   citation dangling.

3. **`seam/power_cmd.json`'s G3/G4 closures (2026-07-31, Task 17/18) left
   TWO downstream relic records stale**, not one: R4's batch already found
   this for `unsettling_lamp` (the GIVEN side); this batch finds the same
   pattern for `ruined_helmet` (the RECEIVED side) — the two relics power_
   cmd's own G3 close note names by name as "never on the same C# hook at
   all" once split. Worth a standing note for future waves: whenever
   `power_cmd`'s guards close, BOTH the given-side and received-side named
   witness relics need their own records re-checked, not just one.

4. **`spiked_gauntlets`'s hook-level rollup text ("Rollup of guards G1, G2
   and G3") is stale in naming G1 as open** — G1 closed 2026-07-28 (Task 0),
   predating even the batch's 2026-07-26 audit date by comparison (the audit
   date is when the record was LAST WRITTEN, not necessarily when guard-
   level text was refreshed against it). This is the same "hook-level
   rollup text lags its own guards" pattern R4 found in `unsettling_lamp`
   and `pen_nib`, now confirmed a third time in this batch.

5. **`sts2_rl/cards/base.py`'s Sly-keyword machinery
   (`sly`/`is_sly_this_turn`/`give_single_turn_sly`) exists but is entirely
   unwired** — not merely absent as `gambling_chip`'s 2026-07-26 audit
   found, but present-and-unconsumed. This is worth flagging distinctly
   from "not ported": the scaffolding for a future port already exists;
   what is missing is (a) a card or effect that calls `give_single_turn_
   sly`, and (b) a shared `DiscardCmd`-equivalent that both routes discards
   through `CardPileCmd.add_to_discard` (closing `gambling_chip/G2`) AND
   auto-plays newly-Sly cards after the draw (closing `gambling_chip/G1`) —
   `player.py:342-344`'s own comment already names `CardCmd.DiscardAndDraw`
   as the shape a shared helper should take, for exactly this relic among
   others (Concentrate, Gambler's Brew).

---

# 6. Fix pass (2026-08-01)

Responding to `R8-review.md` (verdict NEEDS-FIXES). All 14 substantive
verdicts were confirmed by the reviewer and are not re-litigated here — with
**one exception the fix pass itself forced**: rewriting the vacuous
`hefty_tablet` reachability test the review rejected turned up executed
evidence that G2 is **LIVE**, not dormant (§6.7). That is a finding, not a
re-litigation: the reviewer's own instruction ("assert against `cls.__dict__`
overrides on the relic the Neow event actually grants alongside
`hefty_tablet`") is what produced it.

**Files touched by this pass** (footprint respected):
`sts2_rl/relics/vambrace.py` (docstring only), `test/test_r13_relic2.py`,
this report. Nothing else. No `audit/**` edit, no git index command, no
working-tree revert — every RED was produced by in-memory mutation in a
scratch script (`r8fix_probe_a/b/c/d/e.py`, `r8fix_mutations.py`, session
scratchpad, not written into the repo).

Line numbers below are current-worktree; `cmds.py`, `hooks.py` and
`relics/base.py` are all under concurrent edit this wave, so every citation
also names the symbol and the code shape.

---

## 6.1 The shared dormancy reason for four entries rested on DEAD CODE

**What was wrong.** The first pass argued that `charons_ashes/G1`,
`festive_popper/G2` and `letter_opener/G2` were dormant for *two* reasons —
set-coincidence *plus* a `DamageCmd.deal` backstop — and used that same
"full backstop" framing to strengthen `bag_of_marbles/G2`'s note. The
backstop leg does not exist.

**Re-derived independently (not inherited from the review).**

`DamageCmd.deal` (`cmds.py`, `CreatureCmd.Damage`'s port) opens:

```python
if dealer is not None and dealer.is_dead:      # CreatureCmd.cs:242-245
    return 0
if target.is_dead:                             # CreatureCmd.cs:256-259  <- cmds.py:310
    return 0
if not hooks.should_allow_hitting(target):     # <- cmds.py:312
    return 0
```

`should_allow_hitting` returns False only from an implementer, and
`grep -rn "def should_allow_hitting" sts2_rl/` returns **exactly four** hits:
the dispatcher (`hooks.py:1982`) and three implementers — `IllusionPower`
(`powers.py:1996`), `ReattachPower` (`:2920`), `AdaptablePower` (`:4175`).
All three are byte-identical in shape:
`if target is self.owner and self.is_reviving: return False`.
`is_reviving` is written from **only** `on_death` (`powers.py:1994`, `:2917`,
`:4172`) and is cleared **before** HP is restored at all three revive sites —
`IllusionPower.revive` (`:2003` clears, `:2005` heals), `ReattachPower.
do_reattach` (`:2929` clears, `:2932` restores), `AdaptablePower.do_revive`
(`:4181` clears) whose only caller is `TestSubject._respawn`
(`monsters/glory/test_subject.py:137` calls `do_revive()` **then** `:139/:142`
`_revive(form_hp)`). `is_dead` is `hp <= 0` (`creatures.py:47-48`). So there
is no state in which `should_allow_hitting` is False and `is_dead` is not
already True — **`cmds.py:312` is dominated by `cmds.py:310` and can never
fire.**

**EXECUTED** (`r8fix_probe_a.py`), two-enemy combat so `is_ending` is false,
reviving target, `charons_ashes`' exact call shape:

```
baseline dealt: 0    hp: 0
HOOK NEUTERED (should_allow_hitting -> always True)  dealt: 0    hp: 0
restored                                            dealt: 0    hp: 0
```

and, deleting the *other* guard instead (plain corpse, no revive power):

```
is_dead: True   should_allow_hitting: True   baseline dealt: 0
is_dead GUARD NEUTERED                     -> dealt: 3
```

**What survives.** Dormancy on the damage side rests on the
**set-coincidence argument alone**: `is_gone = is_dead or escaped`
(`creatures.py:51-53`), `is_hittable = not is_gone and should_allow_hitting`
(`cmds.py:118-123`), so `hittable_enemies ⊆ living_enemies` unconditionally
and the two coincide for every reachable creature. `living_enemies()` already
excludes everything `hittable_enemies()` would additionally exclude. The gap
stays `gap`/dormant: the call site is still architecturally wrong (built from
`living_enemies()`, `relics/base.py:480-487`, where the C# reads
`CombatState.HittableEnemies`, `CombatState.cs:142` / `Creature.cs:285-299`),
and it goes live the instant a `should_allow_hitting` implementer with a
non-`is_reviving`-gated False case is ported.

**The POWER side is genuinely different, and that asymmetry is the point.**
`PowerCmd.apply` has **no** `is_dead` guard — `Creature.CanReceivePowers`
(`Creature.cs:308-322`) deliberately omits it ("dead creatures can still have
powers applied to them"), and the sim's `can_receive_powers` (`cmds.py:65-75`)
is `not is_removed_from_combat and hooks.should_allow_hitting(target)`. So
there the `should_allow_hitting` half really is load-bearing, and
`bag_of_marbles/G2`'s note keeps its backstop leg. That is why the two
entries' close notes must now say *different* things.

## 6.2 Three defective tests, rewritten and mutation-proved

Full harness: `r8fix_mutations.py` — **23 checks, 0 unexpected**. Each
"deleted" mechanism was removed in memory only.

### (a) `test_power_cmd_apply_backstops_bag_of_marbles_against_an_unhittable_target`

*Defect:* a ONE-enemy encounter. Killing that enemy to arm the revive makes
`is_ending(hooks)` true, so `PowerCmd.apply`'s first guard
(`if is_ending(hooks): return`, `PowerCmd.cs:69-72`) returns **before**
`can_receive_powers` is consulted.

*Fix:* `_combat(..., enemy_count=2)`, plus an explicit
`assert cs.is_ending is False` so the confound cannot silently return.

| run | mutation | result |
|---|---|---|
| rewritten (2 enemies) | none | PASS |
| rewritten (2 enemies) | `cmds.can_receive_powers -> lambda *_: True` | **FAIL** OK |
| old shape (1 enemy) | none | PASS |
| old shape (1 enemy) | `cmds.can_receive_powers -> lambda *_: True` | PASS — the defect |

### (b) `test_damage_cmd_deal_backstops_the_damage_relics_against_an_unhittable_target` → `test_damage_cmd_deal_refuses_the_damage_relics_at_the_is_dead_guard`

*Defect:* null test. It asserted `dealt == 0 and enemy.hp == hp_before` on a
target already at 0 HP, in a one-enemy combat, against a guard that is dead
code. It passed with every mechanism deleted.

*Fix:* rewritten against the guard that actually refuses — a **plain corpse**
(dead, `should_allow_hitting` **True**) in a two-enemy combat takes 0 from the
relic call shape — plus a second half that asserts the dead-code fact directly
(a reviving target is refused identically with the hook neutered). Note the
useful side-finding: `enemy.hp` is floored at 0, so `hp == hp_before` is NOT a
discriminating assertion; `dealt` is (the mutant deals 3 while hp stays 0).

The mutation deletes exactly the guard, not the concept: `Creature.is_dead` is
replaced by a property that returns False **only** when read from
`cmds.py:310` (frame filename + `f_lineno`), leaving death processing intact.

| run | mutation | result |
|---|---|---|
| rewritten | none | PASS |
| rewritten | `if target.is_dead` guard deleted at `cmds.py:310` | **FAIL** OK |
| old null test | none | PASS |
| old null test | `should_allow_hitting -> True` | PASS — the defect |
| old null test | `is_dead` guard deleted | PASS — the defect |

### (c) `test_hefty_tablet_g2_reachability_floor0_holds_no_reward_modifying_relic` → `test_hefty_tablet_g2_a_reward_options_relic_is_reachable_before_its_screen` (+ `test_reward_option_census_is_ten_relics_not_four_or_seven`)

*Defect:* `RunState(rng=...)` starts with `run.relics == []`, so the
`for r in run.relics` body never executed; the only live assertion was
`run.total_floor == 0`. And it was wrong-shaped: `Relic` **declares** both
methods on the base (`relics/base.py`), so `hasattr(type(r), ...)` is True for
all 258 relics — one relic of any kind would have failed it.

*Fix:* split into a real MRO-aware override census and a real reachability
test. Rewriting it is what overturned the verdict (§6.7).

| run | mutation | result |
|---|---|---|
| new reachability test | none | PASS |
| new reachability test | `RunState.obtain_relic_from_grab_bag -> no-op` | **FAIL** OK |
| new reachability test | `del LastingCandy.modify_card_reward_options` | **FAIL** OK |
| new census test | none | PASS |
| new census test | `del LastingCandy.modify_card_reward_options` | **FAIL** OK |
| old vacuous test | none | PASS |
| old vacuous test | grab-bag chain deleted | PASS — the defect |
| old vacuous test | ONE relic of any kind seeded into `run.relics` | FAIL — wrong-shaped, as the review said |

### (d) Also strengthened (review §1, advisory)

* `test_vambrace_docstring_…` was absence-only (would pass on an empty
  docstring). It now also asserts the text NAMES the two real writers and
  carries the Vambrace-scoped `AfterBlockGained` sentence, and checks both
  facts against the code (`Vambrace.__mro__` defines no `on_block_gained`;
  `HookSystem.on_block_gained` exists and some power implements it).
  Mutations: original buggy docstring → **FAIL**; R8's first-fix docstring
  with the false sentence → **FAIL**; empty docstring → **FAIL**.
* `test_paper_phrog_is_still_the_sole_…` scanned `ALL_RELICS` only. It now
  also runs the package-wide `def modify_vulnerable_multiplier` scan the
  report claimed (result: `hooks.py` + `relics/paper_phrog.py`, nothing else).
* `test_sword_of_jade_g1_…` scanned `ALL_RELICS` and read `cls.__dict__`. It
  now walks the MRO up to `Relic` (an inherited `on_combat_start` on an
  intermediate base is visible) and adds a package-wide source scan for every
  `on_combat_start` definition outside `relics/` (finds `powers.py`'s
  `vital_spark` and `galvanic`; neither reads Strength). Remaining narrowness
  is stated in the close note: `read_patterns` is four literal substrings.
* Test docstring citation `PowerCmd.cs:55-60` → **`RuinedHelmet.cs:55-60`**
  (review item 9), with `PowerCmd.cs:148-152`/`:238-242` named as the actual
  dispatch sites.

## 6.3 The third staleness instance, inside R8's own manifest: `festive_popper` G1

The first pass's §5 headline is that a dormancy argument leaning on another
record's guard goes stale when that guard closes. It found two. There is a
third, in the same record as the second, and the first pass asserted G1 was
"already closed" without asking the controller to flip it.

`relic/festive_popper.json` guard **G1** still reads `verdict: gap`. Verified
against the tree, every clause of its text is now false:

* *"the sim's `on_player_turn_started` is the step-23 AfterSideTurnStart slot
  … The sim has one post-draw slot for both"* — `hooks.py:1209-1223`:
  `on_player_turn_started` is `Hook.AfterPlayerTurnStart` **alone**, and its
  docstring says so ("This used to double as the player-side
  `Hook.AfterSideTurnStart`, which is a different hook at a different point …
  18 of the listeners parked here were really that one"). The record's own
  HOOK-level text already records the fix ("G1, the slot, is CLOSED"), so the
  record contradicts itself.
* *"the Imbued enchantment's auto-play fires from the SAME
  `on_player_turn_started` dispatch"* — the sim has a real
  `after_auto_pre_play_phase_entered` dispatcher (`hooks.py:1239-1245`,
  citing `CombatManager.cs:556-572`), which is where Imbued now lives.
* *"That is `seam/hook_dispatch.json` gap G2 … and `seam/turn_structure.json`
  gap G8"* — `turn_structure/G8` reads `faithful` ("CLOSED. The six-value
  PlayerTurnPhase model exists"), and `hook_dispatch.json` **has no G2 or G3
  guard at all** (its guards are N1–N7, G4, G6, G-R10) — neither in the
  worktree nor at `HEAD`.

**Also corrected: G3's stated basis.** The first pass justified G3 with
*"`combat.py`'s `_start_player_turn` … calls `self.player.start_turn()` and
nothing else — no `_check_win_condition()` call sits between the turn-start
dispatch and the method's return."* True of the method, misleading overall:
its CALLER does exactly that recompute (`combat.py:339-340`, with a comment
naming `CombatManager.cs:573`), and `turn_structure/G13`'s close note names
that very site as one of its fixes. The correct and stronger ground is
`Hook.cs:30-45`: *"The check is evaluated once, when enumeration begins, not
per listener… combat teardown is deferred to the next safe point
(CheckWinCondition), so the state stays intact for the rest of the
dispatch."* `CheckWinCondition` (`CombatManager.cs:1046-1058`) only
*dispatches* teardown. The sim's `Relic._check_win` → `_end_combat` →
`_end_combat_internal` (`combat.py:777-804`) performs it **immediately**,
firing `on_combat_end()` and `on_combat_victory()` inside the relic's own
call. That is the divergence, and it is citable without leaning on any seam
guard's status.

## 6.4 `spiked_gauntlets` G2 — attribution corrected

The first pass called G2's closure "a FRESH closure this round" and credited
`hooks.py`'s `_each` "this round". Verified against the committed tree:

```
git show HEAD:sts2_rl/hooks.py  | grep -n _PHASES
  36: _PHASES = ("_very_early", "_early", "", "_late")
  38: _PHASE_SUFFIXES = ...
 355: names = tuple(hook + suffix for suffix in _PHASES)
 401: for suffix in _PHASES:            <- the phase loop inside _each
git show HEAD:sts2_rl/relics/brilliant_scarf.py | grep -n modify_card_energy_cost
  29: def modify_card_energy_cost_late(self, card, cost) -> int:
```

`HEAD`'s `_each` already carries the generic walk *and* its "`_phased` is
recomputed with the order cache — the passes only run for hooks some current
listener actually phases" docstring. `seam/hook_dispatch.json` has no G2/G3
guard at `HEAD` either — the seam gaps this relic's G2 cites were closed and
pruned earlier. **The verdict (G2 closes) stands; the attribution does not.**
Note the worktree's `hooks.py` *is* modified this wave (380 insertions from
another lane), which is presumably what misled the first pass — but the
machinery G2 depends on is not part of that diff.

The guard's shape is still real and load-bearing (reviewer's mutation, which
I did not re-run: `_PHASES` intact → 0, forced to `("",)` → 1, restored → 0,
and order-independent), so `test_spiked_gauntlets_g2_phase_machinery_now_generic_via_each`
is kept as-is.

## 6.5 `vambrace.py` — the production edit's false sentence

The new docstring said: *"There is no `on_block_gained` method here or in the
game."* The second half is false. `AfterBlockGained` is real in **both**
engines:

* C#: `Hook.cs:143` declares it, `CreatureCmd.cs:662` dispatches it,
  `AbstractModel.cs:321` is the virtual, and `JuggernautPower.cs:17` and
  `BeaconOfHopePower.cs:36` override it.
* Sim: `hooks.py:138` maps `"on_block_gained" -> "AfterBlockGained"`,
  `hooks.py:1712` is the dispatcher, `cmds.py:502` fires it, `powers.py:1094`
  implements it.

What *is* true is the Vambrace-scoped claim: `Vambrace.cs`'s overrides are
`Rarity`, `BeforeCombatStart` (:49), `ModifyBlockMultiplicative` (:57),
`AfterModifyingBlockAmount` (:82), `AfterCardPlayed` (:98) and
`AfterCombatEnd` (:116) — no `AfterBlockGained` — and the port has none
either. Also fixed the review's minor (b): the "only … WRITE those fields"
clause omitted `__init__` (`:32-33`) and `reset_for_combat` (`:38-39`).

Current docstring (behaviour unchanged; `git diff HEAD -- sts2_rl/relics/vambrace.py`
is still docstring-only):

> `modify_block_multiplicative` READS `_triggering_card`/`_used` — a preview
> call is still safe because only `after_modify_block_amount`/
> `on_card_played` write them DURING a card play (`__init__` and
> `reset_for_combat` also write them, but only to clear).
>
> Vambrace overrides no `AfterBlockGained` hook — not in this port and not in
> `Vambrace.cs`, whose overrides are ModifyBlockMultiplicative,
> AfterModifyingBlockAmount, AfterCardPlayed, BeforeCombatStart and
> AfterCombatEnd. The hook itself is real on BOTH sides (Hook.cs:143,
> dispatched from CreatureCmd.cs:662, overridden by JuggernautPower.cs:17 and
> BeaconOfHopePower.cs:36; here `on_block_gained`, hooks.py:138/:1712, fired
> from cmds.py:502) — it is simply not one of Vambrace's. The state comes
> from the other pair instead: `after_modify_block_amount` latches
> `_triggering_card` (Vambrace.cs:82-96) and `on_card_played` spends `_used`
> at the END of that card's play (Vambrace.cs:98-113).

The lesson is worth recording next to PROMPT.md bug class 24: **the
replacement for a misdescribing docstring is itself a fidelity claim and
needs the same citation gate as a code change.** The pinning test now
enforces it.

## 6.6 Remaining review items

| review §5 | status |
|---|---|
| 1. vambrace docstring scoped (both clauses) | DONE (§6.5) |
| 2. two-enemy encounter for the PowerCmd backstop test | DONE (§6.2a) |
| 3. delete/rewrite the null damage test | DONE — rewritten (§6.2b) |
| 4. delete/rewrite the vacuous hefty_tablet test | DONE — rewritten; verdict overturned (§6.2c, §6.7) |
| 5. `spiked_gauntlets` G2 note: "STALE — closed before round 13" | DONE (§6.4, §6.9 #11) |
| 6. `bag_of_marbles` dating | DONE (§6.9 #1, §6.10) |
| 7. replace the "same full backstop" reasoning in #2/#6 | DONE (§6.1, §6.9 #2/#6) |
| 8. add `festive_popper` G1's flip to proposal #3 | DONE (§6.3, §6.9 #3) |
| 9. `PowerCmd.cs:55-60` → `RuinedHelmet.cs:55-60` | DONE |
| 10. remove the `gambling_chip` self-correction fragment | DONE (§1, in place) |
| 11. file the `Relic._check_win` gap | DONE — file-ready write-up at §6.8 |
| §1 advisory: widen paper_phrog / sword_of_jade censuses | DONE (§6.2d) |
| §1 advisory: vambrace test is absence-only | DONE (§6.2d) |

## 6.7 FINDING — `relic/hefty_tablet/AfterObtained` G2 is **LIVE**, not dormant

Found while rewriting the vacuous reachability test the review rejected.

**Why the dormancy argument failed.** It measured the wrong state. A bare
`RunState(rng=...)` holds no relics, so "a fresh `RunState` at floor 0 holds
no reward-modifying relic" is true of an empty list and says nothing about
the state when Hefty Tablet's screen opens. `run.add_relic`
(`run.py:827-834`) appends the relic and **then** calls `after_obtained`, so
every relic obtained EARLIER is co-held.

**The census was also short.** MRO-aware, the
`modify_card_reward_options(_late)` overriders are **ten relic ids across
eight defining classes**, not the record's 4 or the first pass's 7:

```
fresnel_lens  frozen_egg  glitter  lasting_candy  lava_lamp
molten_egg    silken_tress  silver_crucible  toxic_egg  wing_charm
```

The three eggs inherit theirs from the intermediate `EggRelic` base
(`_eggs.py:46`) — invisible to a `cls.__dict__` scan — and **`lasting_candy`
is the only PLAIN-pass implementer** (`lasting_candy.py:34`), which a
`_late`-only search misses entirely. (`hasattr` is useless here: `Relic`
declares both methods, so it is True for all 258.)

**The reachable co-hold, executed.** Neow hands out one option, but one of
the options is **Neow's Bones**, which shuffles the Neow pool and grants TWO
of it through `run.add_relic` in order (`neows_bones.py:22-38`,
`NeowsBones.cs`: `PlayerRng.Rewards.Shuffle(relics).Take(2)`, "their pickup
effects apply"). Both `hefty_tablet` and `large_capsule` are in that pool.
`large_capsule.after_obtained` calls `run.obtain_relic_from_grab_bag()` twice
(`run.py:930-935`), and four of the ten implementers are IN the grab bag:
`frozen_egg`, `molten_egg`, `toxic_egg`, `lasting_candy`.

`r8fix_probe_d.py`, 40 seeds of `RunState(rng=Random(seed))` +
`add_relic("large_capsule")`:

```
implementers in the Neow pool: ['silken_tress', 'silver_crucible']
implementers in the grab bag : ['frozen_egg','lasting_candy','molten_egg','toxic_egg']
seed 2: held after Large Capsule = ['large_capsule','toxic_egg','akabeko']
```

So a Neow's Bones draw of `[large_capsule, hefty_tablet]` hands Hefty Tablet
a live reward-options listener.

**Why the gates do not save it.** `silken_tress` and `silver_crucible` — the
two implementers already in the Neow pool — bail unless
`CardCreationFlags.IsCardReward` is set (`SilkenTress.cs:53-56`,
`SilverCrucible.cs:104-107`), and `HeftyTablet.cs:29` does not set it. But
the four grab-bag ones do **not** have that gate: `ToxicEgg.cs:21-32` bails
only on `CardCreationFlags.NoHookUpgrades`, and `HeftyTablet.cs:29` sets
`CardCreationFlags.NoUpgradeRoll` — a **different flag**
(`CardCreationFlags.cs:24` = 2 vs `:29` = 4). `Glitter.cs:18-36` has no flag
check at all beyond `player != Owner`. And `CardFactory.CreateForReward`
really does dispatch on this path: `CardFactory.cs:104-107` —
`if (!options.Flags.HasFlag(NoModifyHooks) && Hook.TryModifyCardRewardOptions(...))`.

**The observable, executed** (`r8fix_probe_e.py`, `RunState(rng=Random(2))`,
Toxic Egg held, Hefty Tablet's screen spied):

```
SIM offer as generated:      brand(SKILL, +0)  fiend_fire(ATTACK, +0)  thrash(ATTACK, +0)
same offer after the dropped TryModifyCardRewardOptionsLate pass:
                             brand(SKILL, +1)  fiend_fire(+0)          thrash(+0)
```

A Rare SKILL that the game offers **upgraded** and the sim offers plain —
a card-identity divergence at a reward screen, i.e. a conformance-visible one.

**BLOCKED-ON-FOOTPRINT.** The fix is in `sts2_rl/relics/hefty_tablet.py`,
which this lane may not touch. What it needs, for the controller to hand to
whoever owns that file: after building `options` and before
`run.select_cards("obtain", …)`, run the reward-options chain the way the
other `CreateForReward` callers already do — the plain pass then the `_late`
pass over the option list, then `after_modify_card_reward_options` for the
listeners that returned true — with a `CardCreationOptions` carrying
`NoUpgradeRoll` and **not** `IsCardReward`, so `silken_tress`/
`silver_crucible` still correctly decline. `relics/scroll_boxes.py`'s own
`after_obtained` is the in-tree precedent for building the options object and
running the hook (its docstring even spells out why `IsCardReward` is absent
there too).

The test added by this pass,
`test_hefty_tablet_g2_a_reward_options_relic_is_reachable_before_its_screen`,
pins the PRECONDITION (the reachable co-hold), not the wrong answer, so it
stays green through the fix.

**Method note.** This is the round-12 lesson landing again: the dormancy
verdict survived a full independent review, and what broke it was not a
better argument but *executing the enumeration the review asked for*. The
first pass's reachability leg had the right grep (`hefty_tablet` appears in
exactly two files) and drew the wrong inference from it — "Neow-only"
silently became "no other relic can be held", and no execution checked that.

## 6.8 FILE-READY: `Relic._check_win()` has the win/loss tie-break backwards

Handed over rather than fixed: it lives in `sts2_rl/relics/base.py`, another
lane's file this wave. Precise enough to file as a new record entry without
re-deriving. **Recommended home:** `audit/records/seam/turn_structure.json`,
a new guard (the record whose G13 owns the mechanism); verdict `gap`,
DORMANT-ENUMERATED.

### The divergence

`sts2_rl/relics/base.py:493-498` (`Relic._check_win`):

```python
def _check_win(self) -> None:
    """End combat if a relic effect just killed the last enemy (mirrors
    the CheckWinCondition that follows game commands). ..."""
    if not self.combat.is_over and self.combat._all_enemies_dead():
        self.combat._end_combat(player_won=True)
```

`CombatManager.CheckWinCondition` (`CombatManager.cs:1046-1058`) tests the
**pending loss FIRST**:

```csharp
public async Task<bool> CheckWinCondition()
{
    if (_pendingLoss != null) { ProcessPendingLoss(); return true; }
    if (IsEnding)            { await EndCombatInternal(); return true; }
    return false;
}
```

Supporting C#: `CombatManager.LoseCombat` (`:945-951`) only MARKS the loss —
its own comment (`:941-943`) says "the actual loss processing happens at the
next safe point (in CheckWinCondition) to avoid race conditions"; it is
called from `CreatureCmd.Kill` (`CreatureCmd.cs:450-455`) once every player is
dead. `ProcessPendingLoss` (`CombatManager.cs:956-965`) fires **no** hook and
performs **no** revive. `EndCombatInternal` (`:978-999`) does the opposite:
`SetPhaseForAllPlayers(None)`, every player's `ReviveBeforeCombatEnd` (`:986`,
`Player.cs:821-827` — heals a dead player to 1), then `Hook.AfterCombatEnd`
(`:988`) and `Hook.AfterCombatVictory` (`:999`).

The sim's own port of the method has it right —
`CombatState._check_win_condition` (`combat.py:726-741`):

```python
if self._has_pending_loss:
    self._process_pending_loss()
elif self._all_enemies_dead():
    self._end_combat_internal()
```

with the comment *"CombatManager.cs:1048 — the pending loss is tested FIRST,
so it wins a tie in which the player and the last enemy die together."*
**`Relic._check_win` never got that fix.** `seam/turn_structure.json` guard
**G13**'s close note claims the class was eliminated: *"The four inline
`_all_enemies_dead()/is_dead` pairs in play_card, auto_play, use_potion and
the turn tail were CheckWinCondition with the tie-break the wrong way round;
they call `_check_win_condition()` now."* There was a **fifth** site.

### Blast radius — ten relics route through it

`grep -rn "_check_win()" sts2_rl/` (excluding `.pyc`):

| relic | file:line | trigger hook |
|---|---|---|
| `charons_ashes` | `charons_ashes.py:29` | `on_card_exhausted` |
| `festive_popper` | `festive_popper.py:29` | `on_player_turn_started` (turn 1) |
| `forgotten_soul` | `forgotten_soul.py:40` | `on_card_exhausted` |
| `kusarigama` | `kusarigama.py:56` | `on_card_played` |
| `letter_opener` | `letter_opener.py:45` | `on_card_played` |
| `lost_wisp` | `lost_wisp.py:37` | `on_card_played` |
| `mercury_hourglass` | `mercury_hourglass.py:29` | `on_player_turn_started` |
| `parrying_shield` | `parrying_shield.py:45` | `after_player_turn_end` |
| `screaming_flagon` | `screaming_flagon.py:32` | `on_player_turn_end` |
| `stone_calendar` | `stone_calendar.py:32` | `on_player_turn_end` |

All ten pass `dealer=self.player` / `dealer=player` to `DamageCmd.deal`.

### The observable, executed

`r8fix_probe_b.py` — identical state (`player.hp = 0`, last enemy `hp = 0`)
fed to each method in a fresh combat:

```
combat._check_win_condition()  -> is_over=True result=(player_won=False) player_hp=0   # C#-correct
Relic._check_win()             -> is_over=True result=(player_won=True)  player_hp=1
```

The second line is not "a wrong result field": `_end_combat_internal`'s port
of `ReviveBeforeCombatEnd` heals the dead player to 1 and re-activates its
hooks, so **a lost run becomes a won combat with a live player.**

### The fix (exact shape)

```python
    def _check_win(self) -> None:
        """CheckWinCondition (CombatManager.cs:1046-1058) — the pending loss
        is tested FIRST, so a simultaneous death resolves as a LOSS."""
        self.combat._check_win_condition()
```

i.e. delegate, exactly as `turn_structure/G13` did at the other four sites.
`CombatState._check_win_condition` already opens with
`if self.phase == Phase.COMBAT_OVER: return`, which subsumes the
`not self.combat.is_over` half, and its `elif self._all_enemies_dead()`
branch calls `_end_combat_internal()` — the same victory path
`_end_combat(player_won=True)` reaches. No behaviour change on the win arm;
the loss arm becomes correct.

### Liveness — DORMANT today, established by execution

**Three independent closures, all executed.** (The first two are the
reviewer's; the third is new to this pass and is the general one.)

1. **A dead player's relic cannot kill the last enemy.** `DamageCmd.deal`'s
   dead-dealer guard (`cmds.py:295-296`, `CreatureCmd.cs:242-245`) returns 0
   whenever `dealer.is_dead`, and all ten relics pass the player as dealer.
   Executed (`r8fix_probe_b.py` §2): player at 0 HP, enemy at 1 HP →
   `dealt=0, enemy.hp=1, all_enemies_dead=False`. So
   `_all_enemies_dead()` cannot newly become true inside a relic's own loop.
2. **A card that kills the last enemy and the player together resolves as a
   loss before any exhaust-triggered relic runs.** Built for real
   (`r8fix_probe_b.py` §3): player at 1 HP, `charons_ashes` held,
   `molten_fist` (exhausts) into a Toadpole carrying `ThornsPower(50)`; both
   die. Result: `player_won=False`, and `enemy.hp=190` — card damage only,
   the relic's 3 never landed. The post-card `_check_win_condition()`
   processes the loss and the combat-over gate stops the exhaust hook. The
   probe is not inert: the same setup with a healthy player gives
   `enemy.hp=187` (card 10 + relic 3), so Charon's Ashes does fire normally.
3. **NEW — while a pending loss is outstanding, none of the ten relics is a
   listener at all.** `_resolve_death`'s player-only tail
   (`cmds.py:206`, `Player.DeactivateHooks`, `Player.cs:857-860`) sets
   `player.is_active_for_hooks = False` the moment the player dies, and the
   hook system's `_live` set drops every relic, potion, orb and card from the
   walk. Executed (`r8fix_probe_c.py`): after killing the player with real
   damage, with the last enemy also at 0 HP and `_all_enemies_dead()` True
   and `is_over` False —

   ```
   player.is_dead=True  is_active_for_hooks=False  phase=PLAYER_TURN  pending_loss=True
   hooks._each('on_card_exhausted')      -> ['CombatHistory']   # no relics
   hooks._each('on_player_turn_started') -> []
   ```

   and a DIRECT `_check_win()` on that same state does produce
   `player_won=True, player.hp=1` — so the bug is real and only the listener
   gate is holding it. The one reversal of `is_active_for_hooks`
   (`cmds.py:561-563`, `Creature.HealInternal`/`Player.ActivateHooks`)
   requires the heal to take the player back above 0, at which point
   `player.is_dead` is False and there is no pending loss; the only explicit
   `lose_combat()` caller (`combat.py:843`) fires under `player.is_dead` and
   returns immediately.

**Also checked and cleared:** no `on_death` implementer anywhere in the
package deals damage (source scan over every `def on_death` body:
zero `DamageCmd.deal`), so an enemy cannot kill the player as it dies inside
a relic's own loop; and `ThornsPower.before_damage_received` requires
`is_powered_attack(props)`, which relic damage (`NON_CARD_UNPOWERED`) never
is.

**What this contradicts.** Ten relic records give `_check_win` a `faithful`
verdict describing it as "the sim's stand-in for the CheckWinCondition that
follows the game's own commands" (`charons_ashes` N4, `parrying_shield` N3,
`mercury_hourglass` N4, `letter_opener` N1, …). That is true of the win arm
and **false of the loss arm**. Recommend the controller amend those N-guards
alongside filing the new one, or point them at it.

## 6.9 FINAL record-close proposals (replaces §2)

Record files are `audit/records/relic/<name>.json` unless noted. Where a note
says "replaces", the quoted text is the reasoning being retired.

1. **`bag_of_marbles.json`, hook key `BeforeSideTurnStart`** → stays `gap`
   (dormant). Close note:
   *Replaces the premise "PowerCmd.apply does not apply [should_allow_hitting]
   either — that absence is `seam/power_cmd.json` gap G6". `power_cmd/G6` was
   FIXED 2026-07-29 (round 5), three days AFTER this record's 2026-07-26
   audit; the record was never revisited. `PowerCmd.apply` now backstops every
   application through `can_receive_powers` (`cmds.py:65-75`, called at the
   method's head), the faithful port of `PowerCmd.cs:73-76`'s
   `!target.CanReceivePowers` — and that backstop is LOAD-BEARING here,
   because `PowerCmd.apply` has no `is_dead` guard (`Creature.cs:308-322`
   deliberately omits it: dead creatures can still take powers).
   Mutation-verified 2026-08-01: in a TWO-enemy combat (so `IsEnding` is
   false and `PowerCmd.cs:69-72` does not return first) a hand-fed reviving
   enemy is refused, and replacing `can_receive_powers` with always-True lets
   Vulnerable land. Dormancy itself is unchanged and rests on set-coincidence:
   the call site is still built from `living_enemies()`
   (`relics/base.py:480-487`, `not e.is_gone`) where `BagOfMarbles.cs:28`
   reads `CombatState.HittableEnemies` (`CombatState.cs:142`,
   `Creature.cs:285-299`), and it goes live on a `should_allow_hitting`
   implementer whose False case is not gated on `is_reviving`. Do NOT reuse
   this backstop wording for the damage relics — see #2. Re-executed
   2026-08-01 (round 13, R8 fix pass):
   `test_should_allow_hitting_false_still_coincides_with_is_gone`,
   `test_power_cmd_apply_backstops_bag_of_marbles_against_an_unhittable_target`.*

2. **`charons_ashes.json`, hook key `AfterCardExhausted`** → stays `gap`
   (dormant); guard G3 stays `deliberate-divergence`. Close note:
   *Replaces R8's first-pass reasoning "dormant for the SAME two reasons: the
   set-coincidence proof, plus the pre-existing `DamageCmd.deal` backstop
   (`if not hooks.should_allow_hitting(target): return 0`) — the same full
   backstop `charons_ashes` already has". **That backstop does not exist.**
   The line is DEAD CODE, dominated by the `if target.is_dead: return 0`
   immediately above it (`CreatureCmd.cs:256-259`): `should_allow_hitting`
   returns False only from `IllusionPower`/`ReattachPower`/`AdaptablePower`
   (`grep -rn "def should_allow_hitting" sts2_rl/` = dispatcher + those
   three), all gated on `is_reviving`, which is armed only from `on_death`
   and cleared before HP is restored at all three revive sites — so False
   implies `is_dead` and the earlier guard has already returned. Executed
   2026-08-01, two-enemy combat, reviving target: dealt 0 with the hook live
   AND 0 with `should_allow_hitting` neutered; deleting the `is_dead` guard
   instead lets 3 damage land. Dormancy therefore rests on the
   set-coincidence argument ALONE (`is_gone = is_dead or escaped`,
   `is_hittable = not is_gone and should_allow_hitting`, so
   `hittable_enemies ⊆ living_enemies` and the two coincide for every
   reachable creature) — one leg, not two. Verdict unchanged. The first
   pass's pinning test was a null test that passed with every mechanism
   deleted; it is replaced by
   `test_damage_cmd_deal_refuses_the_damage_relics_at_the_is_dead_guard`.*

3. **`festive_popper.json`, hook key `AfterPlayerTurnStart`** → stays `gap`;
   **and flip guard G1 to `faithful`.**
   * *Guard **G1** → `faithful`. Close note: replaces "C#'s hook is
     AfterPlayerTurnStart, turn_structure step 22; the sim's
     `on_player_turn_started` is the step-23 AfterSideTurnStart slot… The sim
     has one post-draw slot for both", and its residual observable "the Imbued
     enchantment's auto-play fires from the SAME `on_player_turn_started`
     dispatch… That is `seam/hook_dispatch.json` gap G2 and
     `seam/turn_structure.json` gap G8". All of it is stale.
     `hooks.py:1209-1223` — `on_player_turn_started` is
     `Hook.AfterPlayerTurnStart` ALONE; the AfterSideTurnStart listeners moved
     to `after_side_turn_start`. The sim has a real
     `after_auto_pre_play_phase_entered` dispatch (`hooks.py:1239-1245`,
     `CombatManager.cs:556-572`), which is where Imbued now lives.
     `turn_structure/G8` reads `faithful` ("CLOSED. The six-value
     PlayerTurnPhase model exists") and `seam/hook_dispatch.json` has NO G2 or
     G3 guard at all — not in the worktree and not at HEAD. This record's own
     hook-level text already said "G1, the slot, is CLOSED", so the record
     contradicted itself. Verified 2026-08-01 (round 13, R8 fix pass).*
   * *Guard **G2** → stays `gap`, dormant. Same correction as
     `charons_ashes` #2: replace "There is a partial backstop here that Bag of
     Marbles lacks" — the `DamageCmd.deal` `should_allow_hitting` line is dead
     code, so there is no backstop leg at all on the damage side; dormancy is
     set-coincidence alone.*
   * *Guard **G3** → stays `gap`, dormant, with a NEW basis. Replaces the
     citation of `turn_structure/G13` (closed 2026-07-29, round 5) and R8's
     first-pass justification ("`combat.py`'s `_start_player_turn` … calls
     `self.player.start_turn()` and nothing else"), which is true of the
     method and misleading overall — its CALLER (`combat.py:339-340`) does
     recompute, naming `CombatManager.cs:573`, and G13's own note lists that
     site. The correct ground needs no seam guard: `Hook.cs:30-45` — "The
     check is evaluated once, when enumeration begins, not per listener…
     combat teardown is DEFERRED to the next safe point (CheckWinCondition),
     so the state stays intact for the rest of the dispatch" — and
     `CheckWinCondition` (`CombatManager.cs:1046-1058`) only dispatches
     teardown. The sim's `Relic._check_win` → `_end_combat` →
     `_end_combat_internal` (`combat.py:777-804`) performs it IMMEDIATELY,
     firing `on_combat_end()`/`on_combat_victory()` inside the relic's own
     call. Re-executed 2026-08-01:
     `test_festive_popper_check_win_still_ends_combat_inside_its_own_dispatch`.
     See also the NEW `Relic._check_win` tie-break gap (R8-report §6.8),
     which is the same helper's other defect.*

4. **`gambling_chip.json`, hook key `AfterPlayerTurnStart`** → stays `gap`.
   Unchanged from §2 #4 (the reviewer confirmed it as the batch's best work):
   *`hooks.after_card_changed_piles` is now real, wired machinery (6 call
   sites) but STILL has zero listeners anywhere in the package — re-executed
   full census over ALL_RELICS/ALL_POWERS/_CARD_CLASSES/ALL_POTIONS/
   ALL_ENCHANTMENTS, and the wider `grep -rn "def after_card_changed_piles"
   sts2_rl/` finds only the dispatcher (`hooks.py:1426`), zero implementers
   package-wide including `monsters/**`. The record's cited "ported
   implementers" (book_of_five_rings/bing_bong/darkstone_periapt/lucky_fysh)
   are `after_card_added_to_deck` listeners — a different, run-deck-filtered
   hook — not this one; that is a citation correction, not new content. G1's
   Sly machinery (`is_sly_this_turn`/`give_single_turn_sly`) is now real but
   fully unconsumed: zero `sly = True` cards, zero callers. Re-executed
   2026-08-01:
   `test_is_sly_this_turn_and_give_single_turn_sly_have_zero_consumers`,
   `test_after_card_changed_piles_has_zero_ported_implementers`.*

5. **`hefty_tablet.json`, hook key `AfterObtained`** → stays `gap`;
   **guard G2's liveness flips DORMANT → LIVE.** Close note:
   *Replaces the dormancy argument "a fresh `RunState()` at floor 0 holds no
   relic implementing either reward-options hook" — that measured a RunState
   with NO relics, so the test asserted nothing, and `Relic` declares both
   methods on the base so `hasattr` would have been True for any relic
   anyway. The state that matters is the one at the moment the screen opens:
   `run.add_relic` (`run.py:827-834`) appends and THEN calls
   `after_obtained`, so anything obtained earlier is co-held. Neow's Bones
   grants TWO Neow-pool relics through `add_relic` in shuffled order
   (`neows_bones.py:22-38`, `NeowsBones.cs`), and `large_capsule` — also in
   that pool — pulls two arbitrary grab-bag relics in its own
   `after_obtained` (`run.py:930-935`). Executed 2026-08-01: seeds of
   `RunState + add_relic("large_capsule")` put `toxic_egg` in play. Four of
   the implementers are in the grab bag (`frozen_egg`, `molten_egg`,
   `toxic_egg`, `lasting_candy`) and NONE of the four carries the
   `CardCreationFlags.IsCardReward` gate that makes `silken_tress`/
   `silver_crucible` decline: `ToxicEgg.cs:21-32` bails only on
   `NoHookUpgrades`, and `HeftyTablet.cs:29` sets `NoUpgradeRoll` — a
   DIFFERENT flag (`CardCreationFlags.cs:24` vs `:29`).
   `CardFactory.CreateForReward` really does dispatch
   `Hook.TryModifyCardRewardOptions` on this path (`CardFactory.cs:104-107`).
   Observable, executed: with Toxic Egg held the sim offers
   `brand`/`fiend_fire`/`thrash` all un-upgraded where the dropped Late pass
   upgrades `brand` (a Rare SKILL) to +1. **Verdict liveness: LIVE.** Also
   correct the census: the MRO-aware override count is TEN relic ids across
   eight defining classes (fresnel_lens, frozen_egg, glitter, lasting_candy,
   lava_lamp, molten_egg, silken_tress, silver_crucible, toxic_egg,
   wing_charm) — the record said 4 and R8's first pass said 7; the eggs share
   the `EggRelic` base and `lasting_candy` is the only PLAIN-pass implementer.
   Fix BLOCKED-ON-FOOTPRINT for R8 (`relics/hefty_tablet.py` is another
   lane's file); shape given in R8-report §6.7. Pinned:
   `test_reward_option_census_is_ten_relics_not_four_or_seven`,
   `test_hefty_tablet_g2_a_reward_options_relic_is_reachable_before_its_screen`,
   `test_hefty_tablet_after_obtained_never_calls_modify_card_reward_options`.*
   **Also rewrite the hook-level `issue` rollup**, which still names G1 as a
   divergence ("G1: FilterForCombat instead of GetUnlockedCards") and implies
   G3 is open; both are `faithful`. Proposed: *"G2 only; G1 (candidate pool)
   and G3 (declinable screen) are both independently closed."* Same
   "hook-level rollup lags its own guards" pattern as #11 — the FOURTH
   instance in this batch.

6. **`letter_opener.json`, hook key `AfterCardPlayed`** → stays `gap`
   (dormant). Close note:
   *Same correction as #2, verbatim in substance: R8's first pass said this
   relic's target-set divergence was "backstopped identically" by
   `DamageCmd.deal`. It is not — that line is dead code, dominated by the
   `is_dead` guard (proof and execution in `charons_ashes`' note and in
   R8-report §6.1). Dormancy rests on set-coincidence alone.
   `letter_opener.py:40` still iterates `living_enemies()` where
   `LetterOpener.cs:118` reads `HittableEnemies`. Verdict unchanged.*

7. **`paper_phrog.json`, hook key `ModifyVulnerableMultiplier`** → stays
   `gap`. Close note: *G1's census is now the package-wide
   `grep -rn "def modify_vulnerable_multiplier" sts2_rl/` rather than an
   `ALL_RELICS` scan (which would have missed a power/card/potion/monster
   implementer): the dispatcher (`hooks.py:1053`) and `paper_phrog.py:21`,
   nothing else — so the sim's hook CHAIN cannot double-apply where
   `VulnerablePower.cs:40-44` does one direct `GetRelic<PaperPhrog>()` lookup.
   N2's dormancy census is re-executed with a real play (`Brand`, the one
   self-damage card combining a real `dealer=ctx.player` with an explicit
   `props`), confirmed unpowered, and the test asserts the self-hit was
   actually observed before asserting it is unpowered. Re-executed
   2026-08-01:
   `test_paper_phrog_is_still_the_sole_modify_vulnerable_multiplier_implementer`,
   `test_paper_phrog_n2_brand_self_damage_is_not_a_powered_attack`.*

8. **`philosophers_stone.json`, hook key `AfterCreatureAddedToCombat`** →
   stays `gap`. No text change; re-executed 2026-08-01:
   `test_on_creature_added_only_ever_reaches_combat_enemies`. (Worth adding
   to the enumeration if the controller wants it stronger:
   `Hook.AfterCreatureAddedToCombat` is dispatched from exactly ONE C# site,
   `CreatureCmd.cs:81`; `CombatManager.StartCombatInternal:394-397`'s
   `AfterCreatureAdded(creature)` loop is a different, private method that
   does NOT dispatch the hook, which is why the sim's `combat.py:325` matches.)

9. **`ruined_helmet.json`, hook key `TryModifyPowerAmountReceived`** →
   verdict `faithful`; also close **guard G2** with the same note. Unchanged
   from §2 #9 (the reviewer called it exemplary):
   *Replaces "the RECEIVED-side phase being collapsed into the sim's single
   flat chain (G2)" — `hooks.py` now dispatches
   `modify_power_amount_given_additive`/`_multiplicative`/
   `modify_power_amount_received` as three separate calls, matching
   `PowerCmd.cs:120-127`/`:227-234` exactly and `Hook.cs:1888-1912`
   (GIVEN = two passes, additive then multiplicative) vs `Hook.cs:1915-1930`
   (RECEIVED = one pass of full-value overrides), with C#'s applier gate at
   the call site. `ruined_helmet.py:27-57` is a real listener on the RECEIVED
   chain alone. `seam/power_cmd.json`'s own G3 closed 2026-07-31 (Task 17),
   five days after this record's audit date; this record's copy of the same
   guard was never flipped. Pinned:
   `test_r13_relic2.py::test_ruined_helmet_doubles_once_via_the_real_received_chain`.*

10. **`ruined_helmet.json`, hook key `AfterModifyingPowerAmountReceived`** →
    verdict `faithful`; also close **guard G3** with the same note. Unchanged
    from §2 #10:
    *Replaces "the mark-used side effect is hand-inlined into the modifier, so
    it fires at a point C# would not have reached" —
    `after_modify_power_amount_received` is now `ruined_helmet.py:59-62`'s OWN
    separate method, dispatched by `hooks.py`'s real companion event
    (`:1032-1049`, mirroring `Hook.cs:811-824`) only for listeners whose
    modifier actually changed the amount, exactly as `RuinedHelmet.cs:55-60`.
    `seam/power_cmd.json`'s G4 closed the same day (2026-07-31, Task 18).
    Proved structurally: calling the bare modifier returns the doubled amount
    and leaves `_used` False; only the companion event sets it. Pinned:
    `test_r13_relic2.py::test_ruined_helmet_mark_used_lives_in_the_companion_event_not_the_modifier`.*

11. **`spiked_gauntlets.json`, hook key `TryModifyEnergyCostInCombat`** →
    stays `gap` (via G3 alone; G1 already `faithful`, G2 now closes). Close
    note for guard **G2**:
    *Replaces "the hook has a PLAIN pass and a LATE pass and the sim has
    neither". `Hook.cs:1574-1590` is `if (originalCost < 0m) return` then TWO
    complete `IterateCombatHookListeners` passes — every
    `TryModifyEnergyCostInCombat`, then every `…Late`; there is no
    per-creature grouping in this dispatcher at all, so the rollup's
    "no per-creature listener grouping" phrase belongs to G1, which is
    already `faithful`. The sim has both passes: `hooks.py`'s `_each` runs
    the generic `_PHASES` walk for any hook a registered listener phases
    into, and `brilliant_scarf.modify_card_energy_cost_late` is that
    listener. **STALE — closed BEFORE round 13, and this record was never
    revisited; NOT a round-13 closure.** Evidence:
    `git show HEAD:sts2_rl/hooks.py` already has `_PHASES` at :36,
    `names = tuple(hook + suffix for suffix in _PHASES)` at :355 and the phase
    loop in `_each` at :401; `git show HEAD:sts2_rl/relics/brilliant_scarf.py:29`
    already defines `modify_card_energy_cost_late`; and
    `seam/hook_dispatch.json` had no G2 or G3 guard at HEAD either — the seam
    gaps this guard cites were closed and pruned earlier. (R8's first pass
    called it "a FRESH closure this round"; that is wrong and is corrected
    here.) Behaviour re-executed on the guard's own worked example
    (CuriousPower 2 + SpikedGauntlets plain + BrilliantScarf Late, 1-cost
    Power): both engines land on 0, and the answer is order-independent —
    which refutes the recorded observable "the sim gives 0 or 2 depending on
    which relic was obtained first". Pinned:
    `test_r13_relic2.py::test_spiked_gauntlets_g2_phase_machinery_now_generic_via_each`.*
    Guard **G3** stays `gap`, dormant: `energy_cost_x` is truthy on exactly
    `volley`/`whirlwind`/`cascade` (ATTACK/ATTACK/SKILL), census re-run.
    **Also rewrite the hook-level `issue`** from "Rollup of guards G1, G2 and
    G3" to *"G3 only; G1 and G2 are both independently closed."*

12. **`stone_cracker.json`, hook key `AfterRoomEntered`** → stays `gap`. No
    text change; the record's reachability argument re-confirmed by DIRECT
    execution (order-independence with `tea_of_discourtesy`, both orders,
    identical `(upgraded, dazed)`), not by census alone.
    `CombatRoom.cs:228` fires `AfterRoomEntered` one full dispatch before
    `Hook.BeforeCombatStart`; `combat.py:327` is the sim's single
    `hooks.on_combat_start()`. Re-executed 2026-08-01:
    `test_stone_cracker_and_tea_of_discourtesy_are_order_independent`.

13. **`sword_of_jade.json`, hook key `AfterRoomEntered`** → stays `gap`.
    Close note:
    *Re-executed 2026-08-01 with the census WIDENED twice over, because R8's
    first pass described its own test as scanning "every `on_combat_start`
    implementer" when it iterated `ALL_RELICS` and read `cls.__dict__`. It
    now walks the MRO up to `Relic` (an inherited `on_combat_start` on an
    intermediate base is visible) and adds a package-wide source scan of every
    `on_combat_start` definition outside `relics/` — which finds `powers.py`'s
    `vital_spark` and `galvanic`, neither of which reads Strength (both
    afflict cards). Zero Strength READS outside the twelve
    AfterRoomEntered-side relics; `sling_of_courage` is a pure grant and
    `unsettling_lamp` cannot bite (its multiplicative modifier requires
    `self._in_flight is not None`, i.e. a card play, and `target is not
    self.player`, while Sword of Jade's Strength is a non-card grant TO the
    player). Two narrownesses stated so the next reader does not over-read
    it: the scan's `read_patterns` are four literal substrings, so a Strength
    read through a helper or a `StrengthPower.id` constant would not match.
    Pinned:
    `test_sword_of_jade_g1_no_other_combat_start_listener_reads_strength`.*

14. **`vambrace.json`, guard key `N3` (`g6` in the manifest)** → verdict
    `faithful`. Close note:
    *The docstring fix landed (`sts2_rl/relics/vambrace.py:14-29`,
    docstring-only; `git diff HEAD` on that file is entirely inside the class
    docstring). Replaces the old text's two false claims — "The multiplier
    hook stays stateless (safe for previews)" (false:
    `modify_block_multiplicative` reads `_triggering_card`/`_used`) and "the
    one-shot flag is set from the real on_block_gained event" (false: the flag
    is set by `on_card_played`). NOTE for anyone reading the diff: R8's FIRST
    replacement introduced a third false sentence — "there is no
    `on_block_gained` method here or in the game" — which the review caught
    and this pass fixed. `AfterBlockGained` is real in BOTH engines
    (`Hook.cs:143`, dispatched `CreatureCmd.cs:662`, overridden by
    `JuggernautPower.cs:17` and `BeaconOfHopePower.cs:36`; sim `hooks.py:138`
    mapping, `:1712` dispatcher, `cmds.py:502` fire site, `powers.py:1094`
    implementer). The true claim is Vambrace-scoped: Vambrace overrides no
    `AfterBlockGained` — not in this port and not in `Vambrace.cs`, whose
    overrides are ModifyBlockMultiplicative (:57), AfterModifyingBlockAmount
    (:82), AfterCardPlayed (:98), BeforeCombatStart (:49) and AfterCombatEnd
    (:116). The underlying G3 divergence this entry warned readers not to
    mistake for intent has been closed since round 7 (2026-07-29). No
    behaviour change. Pinned:
    `test_r13_relic2.py::test_vambrace_docstring_names_the_two_real_methods_and_scopes_the_hook_claim`,
    which asserts the text NAMES the two real writers (an absence-only
    assertion would pass against an empty docstring) and cross-checks both
    claims against the code.*

**15. NEW ENTRY to file — `seam/turn_structure.json`, new guard,
verdict `gap`, DORMANT-ENUMERATED:** `Relic._check_win()`'s inverted
win/loss tie-break, the FIFTH site of the class G13's close note says it
eliminated at four. Full file-ready write-up — C# citations, the ten relics,
the exact fix shape, and the three executed dormancy closures — at §6.8.
Found by the reviewer; re-derived and extended by this pass.

## 6.10 FINAL queue annotations (replaces §3)

- `relic/bag_of_marbles/BeforeSideTurnStart` — dormant — re-executed
  2026-08-01: `power_cmd/G6` FIXED 2026-07-29 (round 5), three days AFTER
  this record's 2026-07-26 audit; never revisited. `PowerCmd.apply` now
  refuses an unhittable target via `can_receive_powers`, and that IS
  load-bearing (no `is_dead` guard on the power path) — mutation-verified in
  a two-enemy combat. Dormancy itself is set-coincidence: call site still
  `living_enemies()` not `hittable_enemies()`; goes live on a
  `should_allow_hitting` implementer not gated on `is_reviving`.
- `relic/charons_ashes/AfterCardExhausted` — dormant — re-executed
  2026-08-01. CORRECTION to R8's first pass: there is NO `DamageCmd.deal`
  backstop; that `should_allow_hitting` line is dead code, dominated by the
  `is_dead` guard (executed both ways). Dormancy is set-coincidence alone.
- `relic/festive_popper/AfterPlayerTurnStart` — dormant — re-executed
  2026-08-01. G1 CLOSES (the slot is `AfterPlayerTurnStart` alone; its cited
  `hook_dispatch` G2 and `turn_structure` G8 are gone/closed). G2 same
  dead-code correction as charons_ashes. G3 restated on `Hook.cs:30-45`
  (teardown deferred to the next safe point) instead of the closed
  `turn_structure/G13` — no seam guard needed.
- `relic/gambling_chip/AfterPlayerTurnStart` — dormant — re-executed
  2026-08-01: `after_card_changed_piles` machinery is wired (6 call sites)
  but has ZERO listeners package-wide including `monsters/**`; Sly machinery
  present and fully unconsumed.
- `relic/hefty_tablet/AfterObtained` — **LIVE (was reported dormant;
  OVERTURNED 2026-08-01)** — the co-hold the dormancy argument ruled out is
  reachable: Neow's Bones grants two Neow-pool relics through `add_relic`,
  and `large_capsule` pulls grab-bag relics in its own `after_obtained`
  (executed: `toxic_egg` in play). `ToxicEgg.cs` gates on `NoHookUpgrades`,
  `HeftyTablet.cs:29` sets `NoUpgradeRoll` — different flags — so the dropped
  `TryModifyCardRewardOptions` pass is observable: a Rare SKILL offered
  upgraded by the game and plain by the sim. Census also 4 -> **10** (eggs
  share `EggRelic`; `lasting_candy` is the only plain-pass implementer).
  Fix BLOCKED-ON-FOOTPRINT (R8 may not touch `relics/hefty_tablet.py`).
- `relic/letter_opener/AfterCardPlayed` — dormant — re-executed 2026-08-01;
  same dead-code correction as charons_ashes, set-coincidence alone.
- `relic/paper_phrog/ModifyVulnerableMultiplier` — dormant — re-executed
  2026-08-01: census widened from ALL_RELICS to the package-wide grep; still
  the sole implementer. Brand's real self-hit confirmed unpowered.
- `relic/philosophers_stone/AfterCreatureAddedToCombat` — dormant —
  re-executed 2026-08-01: `CreatureCmd.add`'s only destination is
  `combat.enemies`, confirmed with a real mid-combat spawn; C# dispatches the
  hook from one site (`CreatureCmd.cs:81`) and `StartCombatInternal`'s
  same-named private loop is not it.
- `relic/ruined_helmet/TryModifyPowerAmountReceived` and
  `/AfterModifyingPowerAmountReceived` — **CLOSED 2026-08-01**:
  `seam/power_cmd.json` G3+G4 closed 2026-07-31 (Task 17/18);
  ruined_helmet.py already rewritten to the given/received split with a real
  companion event. No code change needed — this record's copy of the guards
  was never flipped.
- `relic/spiked_gauntlets/TryModifyEnergyCostInCombat` — NARROWED
  2026-08-01: G1 already closed; G2 closes as **STALE — the plain/Late phase
  machinery is present unchanged at HEAD (`_PHASES`, `_each`'s phase loop,
  `brilliant_scarf.modify_card_energy_cost_late`), so it closed BEFORE round
  13**, correcting R8's first pass, which claimed a fresh round-13 closure.
  G3 (X-cost bail) stays dormant: cascade/volley/whirlwind still the only
  X-cost cards, still zero Powers. Hook-level rollup should name G3 alone.
- `relic/stone_cracker/AfterRoomEntered` — dormant — re-executed
  2026-08-01 with a direct order-independence demonstration against
  tea_of_discourtesy.
- `relic/sword_of_jade/AfterRoomEntered` — dormant — re-executed 2026-08-01
  with the census widened (MRO walk + package-wide `on_combat_start` scan;
  powers.py's vital_spark/galvanic checked and cleared). Narrowness recorded:
  four literal read-patterns, so a helper-mediated Strength read would slip.
- `relic/vambrace/g6` — **CLOSED 2026-08-01**: docstring fixed; no behaviour
  change. The first replacement itself shipped a false sentence
  ("no `on_block_gained` … in the game") — `AfterBlockGained` is real in both
  engines; the claim is now Vambrace-scoped and pinned by a test that
  asserts what the text SAYS, not only what it omits.
- `seam/turn_structure` — **NEW GAP to file**: `Relic._check_win()`
  (`relics/base.py:493-498`) ends combat as a WIN without testing the pending
  loss — the fifth site of the class G13 says it eliminated at four; ten
  relics route through it; converts a lost run into a won combat with a
  1-HP revive. Dormant today by three executed closures (dead-dealer guard;
  post-card `_check_win_condition`; and — new — a dead player's relics are
  dropped from the listener walk entirely). File-ready at R8-report §6.8.

## 6.11 Test-authoring bug caught by the wave's full-suite run

`test_paper_phrog_n2_brand_self_damage_is_not_a_powered_attack` did
`original_deal = cmds_mod.DamageCmd.__dict__["deal"].__func__`, which assumes
the class-dict entry is a `staticmethod` object. It is not, once a full-suite
run has passed through `test/test_r13_relic1.py`: that file's own spy restores
with `cmds_mod.DamageCmd.deal = original_deal` (`test_r13_relic1.py:301`)
where `original_deal` came from **class-attribute** access, i.e. the UNWRAPPED
function — so the class dict is left holding a plain function and `.__func__`
raises `AttributeError: 'function' object has no attribute '__func__'`.

Order-dependent, which is why the targeted run never saw it.

*Fix (mine, in my footprint):* take the callable via class-attribute access
(`cmds_mod.DamageCmd.deal` — correct for BOTH shapes) and save the RAW
class-dict entry for an exact, non-lossy restore. Verified:
`py -m pytest test/test_r13_relic1.py test/test_r13_relic2.py -q` → 34 passed
(this is the ordering that used to fail), and `py -m pytest test/ -q -k relic`
→ 387 passed (was 1 failed / 386 passed).

*Finding for the controller, not mine to fix:* `test_r13_relic1.py:301`'s
lossy restore is the root cause and will keep silently converting
`DamageCmd.deal` from a `staticmethod` to a plain function for every test
that runs after it. Benign for call sites (both shapes resolve the same
through the class) but it is a cross-test state leak. The one-line fix is to
restore `cmds_mod.DamageCmd.__dict__["deal"]` as saved, or to re-wrap:
`cmds_mod.DamageCmd.deal = staticmethod(original_deal)`.

## 6.12 Tests — files, commands, counts

**Changed**: `test/test_r13_relic2.py` — 19 tests → **20**.

* rewritten: `test_power_cmd_apply_backstops_bag_of_marbles_against_an_unhittable_target`
* rewritten + renamed: `test_damage_cmd_deal_backstops_the_damage_relics_against_an_unhittable_target`
  → `test_damage_cmd_deal_refuses_the_damage_relics_at_the_is_dead_guard`
* replaced by two: `test_hefty_tablet_g2_reachability_floor0_holds_no_reward_modifying_relic`
  → `test_reward_option_census_is_ten_relics_not_four_or_seven` +
  `test_hefty_tablet_g2_a_reward_options_relic_is_reachable_before_its_screen`
* strengthened + renamed: `test_vambrace_docstring_no_longer_claims_statelessness_or_on_block_gained`
  → `test_vambrace_docstring_names_the_two_real_methods_and_scopes_the_hook_claim`
* widened: `test_paper_phrog_is_still_the_sole_modify_vulnerable_multiplier_implementer`,
  `test_sword_of_jade_g1_no_other_combat_start_listener_reads_strength`
* fixed (order-dependent AttributeError): `test_paper_phrog_n2_brand_self_damage_is_not_a_powered_attack`
* citation fixed: `test_ruined_helmet_mark_used_lives_in_the_companion_event_not_the_modifier`

**Production edit**: `sts2_rl/relics/vambrace.py` — class docstring only.

**Commands run** (this pass):

```
py -m pytest test/test_r13_relic2.py -q
  -> 20 passed

py -m pytest test/test_r13_relic1.py test/test_r13_relic2.py -q
  -> 34 passed          # the ordering that reproduced the AttributeError

py -m pytest test/ -q -k relic
  -> 387 passed, 3490 deselected     # was 1 failed / 386 passed before the fix

py -m pytest test/test_r13_relic2.py test/test_r13_relic1.py test/test_relics.py \
  test/test_relic_live_tail.py test/test_relic_residue_gaps.py \
  test/test_relic_tier1_gaps.py test/test_tier1_last_five.py test/test_hook_order.py \
  test/test_power_type_for_amount.py test/test_power_modifier_phases.py \
  test/test_combat_over_hook_gate.py test/test_powers.py \
  test/test_round13_listener_derivation.py -q
  -> 567 passed

py -m pytest test/ -k "vambrace or hefty" -q
  -> 10 passed, 3867 deselected

py -m pytest test/ -q                     # requested by the controller (gate)
  -> 2 failed, 3869 passed, 6 xfailed in 341s
     the 2 are the known environment gap only
     (test_conformance_floor_state.py, missing 933T39V18D/floor_49 fixture)

py <scratchpad>/r8fix_mutations.py
  -> 23 checks, 0 unexpected
```

Scratch probes (session scratchpad, never written into the repo):
`r8fix_probe_a.py` (dead-code proof + `can_receive_powers` one-vs-two-enemy
confound), `r8fix_probe_b.py` (`Relic._check_win` tie-break + both of the
reviewer's reachability paths), `r8fix_probe_c.py` (the third closure: a dead
player's relics leave the listener walk), `r8fix_probe_d.py` (hefty_tablet
co-hold reachability), `r8fix_probe_e.py` (the hefty_tablet observable),
`r8fix_mutations.py` (all mutation evidence).

## 6.13 Findings from this pass, ranked

1. **`relic/hefty_tablet/AfterObtained` G2 is LIVE** (§6.7) — a dormancy
   verdict that survived a full independent review, broken by executing the
   enumeration rather than restating it. BLOCKED-ON-FOOTPRINT.
2. **`Relic._check_win`'s inverted tie-break** (§6.8) — the reviewer's find,
   re-derived and extended with a third, general dormancy closure. File-ready.
3. **A dormancy argument that leant on DEAD CODE** (§6.1) — the `is_reviving`
   implication that makes the set-coincidence argument work is the same fact
   that makes the "second leg" unreachable. Two arguments, one premise, and
   the first pass counted it twice.
4. **The reward-options census was wrong twice** (§6.7) — 4 → 7 → 10. Both
   undercounts came from the same two blind spots the reviewer named for
   `sword_of_jade`: `cls.__dict__` instead of an MRO walk (the eggs), and a
   `_late`-shaped search (missing `lasting_candy`'s plain pass).
5. **A fourth "hook-level rollup lags its own guards"** (§6.9 #5) —
   `hefty_tablet`'s rollup still names G1/G3 as divergences; both are
   `faithful`. R4 found it in `unsettling_lamp` and `pen_nib`, R8's first
   pass in `spiked_gauntlets`.
6. **A cross-test state leak in a sibling lane's file** (§6.11) —
   `test_r13_relic1.py:301` unwraps `DamageCmd.deal` permanently.
7. **Docstring replacements need the citation gate too** (§6.5) — the fix for
   a misdescribing docstring shipped its own misdescription, of the engine's
   hook surface, in the one entry whose entire subject is that bug class.
