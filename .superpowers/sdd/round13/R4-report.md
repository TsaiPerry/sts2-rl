# R4 report — settling unlabelled batch `relic-1` (14 entries, 13 records)

Footprint: `sts2_rl/relics/<name>.py` for the 13 relics named in the manifest,
plus `test/test_r13_relic1.py` (new). No production code was touched — every
entry settled as DORMANT-ENUMERATED or STALE-ALREADY-FIXED; none needed a
FIXED verdict. All 14 hook-level entries were re-verified by reading the
current C# and the current sim source, not by trusting the JSON records'
2026-07-26/27 prose, and by running fresh probes/tests where feasible.

**Headline finding**: this worktree already carries substantial, *committed*
fixes from other lanes earlier in round 13 (git log: `c9bc337 second round of
bug fixes`, `e7c009a another bug fix wave`, `650c320 character port + more
bug fixes`, `ffa1024 first round of bug fixes` — all ancestors of the current
`tier2-round13` branch tip, not concurrent live edits). Two of my 14 entries
(`pen_nib/AfterCardPlayed`'s G3, and both `lizard_tail` entries) describe
mechanisms those commits already fixed; the JSON audit records were never
revisited to match. `unsettling_lamp` was reworked most heavily (`seam/
power_cmd.json`'s own guards G2-G6, dated "Closed 2026-07-31" — today —
confirm this): its hook-level entry's `maps_to` citation names a method,
`modify_power_amount`, that no longer exists in `unsettling_lamp.py` at all.

---

## Per-entry verdicts

### 1. `relic/archaic_tooth/AfterObtained` — DORMANT-ENUMERATED (re-confirmed)

**Fix-pass correction (R4-review.md §1, F2):** the paragraph below originally
characterised G2 as "the sim adds a `can_enchant(transformed)` condition C#
lacks." That is wrong — C# does not lack the condition. `CardCmd.Enchant`
(`CardCmd.cs:532-538`) opens `if (!enchantment.CanEnchant(card)) throw new
InvalidOperationException(...)`. The real divergence is **silent skip vs.
hard throw**: the sim's `can_enchant` guard quietly declines where C# would
raise. Dormancy is unaffected either way — nothing in ported content
discriminates Bash from Break, so neither branch is ever reached — but the
guard text is corrected here rather than repeated.

Guards G1 (C# grants exactly one upgrade level; the sim's `for _ in
range(original.upgrade_level)` loop over-grants for `upgrade_level > 1`) and
G2 (the sim silently skips the enchant on a failed `can_enchant` check where
C# throws `InvalidOperationException` — `CardCmd.cs:532-538` — and MOVES
rather than CLONES the enchantment) are both still real divergences in
today's `sts2_rl/relics/archaic_tooth.py:23-38`, and both are still
unreachable:

- **G1 re-executed**: `test/test_r13_relic1.py::
  test_no_ported_card_has_an_upgrade_level_above_one` — census over
  `sts2_rl.cards.base._CARD_CLASSES` finds 0 cards with
  `max_upgrade_level > 1` (168 at 1, 35 at 0), and the only transcendable
  Ironclad card (Bash) tops out at 1.
- **G2 re-executed**: `test/test_r13_relic1.py::
  test_no_enchantment_discriminates_bash_from_break` — every currently
  registered `Enchantment.can_enchant` (`sts2_rl/enchantments.py`) agrees on
  Bash and Break (both `CardType.ATTACK`) or excludes both. Bash carries no
  tags at all (`sts2_rl/cards/bash.py`), so Swift's `BASIC rarity AND
  (strike/defend tag)` predicate still excludes it exactly as the prior audit
  found — but there are now *more* `can_enchant` predicates than the record's
  2026-07-26 pass considered (an X-cost exclusion, an exhausts-based one, a
  `card_type == SKILL` one, a `"defend" in tags` one, three `card_type ==
  ATTACK` ones, a `gains_block` one). None of the new ones discriminate Bash
  from Break, because both are plain, non-X-cost, non-exhausting `ATTACK`
  cards with no `gains_block`/tags — confirmed by iterating every
  `_ENCHANTMENT_CLASSES` entry, not by inspection of Swift alone.

Citations: `ArchaicTooth.cs:146-166`, `CardCmd.cs:532-538`,
`sts2_rl/relics/archaic_tooth.py:23-38`,
`sts2_rl/cards/bash.py`, `sts2_rl/cards/break_card.py`,
`sts2_rl/enchantments.py`.

### 2. `relic/booming_conch/AfterSideTurnStart` — DORMANT-ENUMERATED (re-confirmed)

G1 (hook slot) is already closed. G2 (the energy grant bypasses
`hooks.modify_energy_gain`) is still real in
`sts2_rl/relics/booming_conch.py:34` (`player.energy += self.ENERGY`,
no chain) against `EnergyCmd.gain` (`sts2_rl/cmds.py:1563-1594`), which DOES
carry the chain (`amount = hooks.modify_energy_gain(player, amount)`) plus an
`is_ending` guard. Still dormant: `NoEnergyGainPower`
(`sts2_rl/powers.py:794-809`) still expires via `after_player_turn_end`
(removed at the OWNER's own turn end), and Booming Conch only fires on
`turn <= 1`, before any card — including `expect_a_fight`, the power's only
applier — can have been played. Re-executed:
`test/test_r13_relic1.py::test_booming_conch_energy_grant_bypasses_modify_energy_gain_chain`
applies `NoEnergyGainPower` directly to the player and shows the relic's
grant is unaffected (a real `EnergyCmd.gain` would have clamped to 0).

Citations: `BoomingConch.cs:45`, `CombatManager.cs:522`,
`sts2_rl/relics/booming_conch.py:31-34`, `sts2_rl/cmds.py:1563-1594`,
`sts2_rl/powers.py:794-809`.

### 3. `relic/fake_strike_dummy/ModifyDamageAdditive` (mechanism `damage_pipeline/G3`) — DORMANT-ENUMERATED (re-confirmed)

G1 (`dealer is self.player` narrows C#'s `dealer != Owner.Creature &&
cardSource.Owner != Owner` — an AND of negatives, so either disjunct alone
suffices) is still real in `sts2_rl/relics/fake_strike_dummy.py:35`. Re-ran
the reachability census against TODAY's card list: all 8 Strike-tagged cards
(`ashen_strike`, `perfected_strike`, `pommel_strike`, `seeker_strike` [in
`colorless_attacks.py`/`event_cards.py`], `setup_strike`, `strike`,
`twin_strike`, `ultimate_strike`) pass `dealer=ctx.player` on every
`DamageCmd.deal` call. The `card=` sites with no `dealer=player` are all
self-damage drawbacks (`blood_wall`, `bloodletting`, `burn`, `decay`,
`hemokinesis`, `infection`, `offering`, `toxic`, `wither`), none of which
carries the `strike` tag. Re-executed:
`test/test_r13_relic1.py::test_fake_strike_dummy_and_strike_dummy_miss_a_null_dealer_strike`
shows a synthetic `dealer=None` Strike getting +0 instead of +1.

Citations: `FakeStrikeDummy.cs:23-38`, `sts2_rl/relics/fake_strike_dummy.py:25-37`,
`sts2_rl/cards/*.py` (strike-tag + `DamageCmd.deal` census).

### 4. `relic/fur_coat/AfterCreatureAddedToCombat` — NARROWED (citation error found; net verdict unchanged)

**The record's divergence (a) does not exist — it is a citation error, not a
narrowed-but-real gap.** The record reads `CombatManager.StartCombatInternal`'s
loop `foreach (Creature creature in _state.Creatures) await
AfterCreatureAdded(creature)` (`CombatManager.cs:394-398`) as dispatching
`Hook.AfterCreatureAddedToCombat`. It does not: `CombatManager.
AfterCreatureAdded` (`CombatManager.cs:860-867`, confirmed by reading it in
full) only calls `creature.AfterAddedToRoom()` and rolls the creature's
opening move — it never calls `Hook.AfterCreatureAddedToCombat`. Grepping the
whole decompiled source for `AfterCreatureAddedToCombat` finds exactly one
dispatch site in the entire game: `CreatureCmd.cs:81`, inside
`CreatureCmd.Add` — the **mid-combat** path. That is exactly where the sim's
`hooks.on_creature_added` already lives (`sts2_rl/cmds.py`'s
`CreatureCmd.add`, confirmed by reading the method: `combat.
after_creature_added(creature)` — a *different*, correctly-ported method
mirroring the C# bookkeeping method of the same name — runs first, then
`hooks.on_creature_added(creature)` second). There is no "shadowing" to
explain: **both codebases dispatch this hook only for mid-combat joiners,
never for the starting roster**, by identical architecture. Pinned:
`test/test_r13_relic1.py::test_on_creature_added_hook_never_fires_for_starting_enemies`
(a spy listener sees zero calls during `CombatState` construction and exactly
one call after `CreatureCmd.add`).

(b) is unchanged and still open: G3 (`CreatureCmd.SetCurrentHp` vs the raw
`enemy.hp = 1` in `sts2_rl/relics/fur_coat.py:98,102`) is the same guard
`BeforeCombatStart` already carries as `gap`/dormant (binding rule 3 — same
mechanism, same verdict). Re-confirmed `on_hp_changed`'s only sim listener is
still `sts2_rl/relics/red_skull.py:51` (reads the *player's* HP only), so
there is still no listener that would notice Fur Coat's missing
`AfterCurrentHpChanged` notification on an enemy.

**Verdict: DORMANT-ENUMERATED** (the entry still nets a real, dormant gap via
(b)), but the entry's own "(a)" reasoning should be struck, not merely
narrowed — it was never a divergence.

Citations: `CombatManager.cs:394-398,860-867`, `CreatureCmd.cs:81`,
`sts2_rl/cmds.py` (`CreatureCmd.add`), `sts2_rl/combat.py:445-471`
(`after_creature_added`), `sts2_rl/relics/fur_coat.py:92-102`,
`sts2_rl/relics/red_skull.py:51`.

### 5. `relic/gremlin_horn/AfterDeath` — DORMANT-ENUMERATED (re-confirmed; citation update needed)

G1 already closed. G2 (the sim resolves death, and fires `on_death`, INSIDE
`_resolve_death` — before `on_damage_dealt`/`on_damage_received` — where C#
defers `Kill()` until after `AfterDamageGiven`+`AfterDamageReceived`) is
still architecturally real in `sts2_rl/cmds.py:126-177` (`_resolve_death`),
same mechanism/verdict as `seam/damage_pipeline` G6/N2 (binding rule 3).

**Citation needs updating, conclusion unchanged**: the record's dormancy
argument says "no sim power implements `on_damage_dealt` at all" — this is
now stale. `grep -n "def on_damage_dealt" sts2_rl/` finds TWO implementers:
`ImbalancedPower` (Bowlbug Rock) and `PaperCutsPower` (Scroll of Biting).

**Fix-pass correction (R4-review.md §1, entry 5 / F4):** the prior version of
this paragraph cited these by line number (`sts2_rl/powers.py:2486-2500`,
`:3580-3608`). Those lines are wrong — they land on `SteamEruptionPower` and
`BattlewornDummyTimeLimitPower` — because `powers.py` is being edited by a
concurrent lane in this same wave and line numbers taken mid-wave drift
(confirmed again just now: a fresh `grep -n "^class ImbalancedPower\|^class
PaperCutsPower\|def on_damage_dealt" sts2_rl/powers.py` returns yet another
set of line numbers than the reviewer's own pass reported). Cited by symbol
only, per the review's F4 finding; do not re-add line numbers to this record
while `powers.py` is under concurrent edit. Read both bodies in full: each
gates on `dealer is self.owner`, where `self.owner`
is the *enemy* holding the power — i.e. each only fires when that enemy is
the one dealing damage (to the player), never when the *player* deals a
killing blow to an enemy, which is Gremlin Horn's own trigger shape. So the
window whose ordering changed (a player's killing blow) still has zero
listeners on either side of it. Dormancy conclusion unchanged; only the "zero
implementers" phrasing is wrong and should read "two implementers, neither
reachable from the player-kills-enemy direction Gremlin Horn cares about."

Citations: `CreatureCmd.cs:388-409`, `sts2_rl/cmds.py:126-177`,
`sts2_rl/powers.py` (`ImbalancedPower.on_damage_dealt`,
`PaperCutsPower.on_damage_dealt` — symbol only, see the fix-pass note above).

### 6. `relic/kusarigama/AfterCardPlayed` — DORMANT-ENUMERATED (re-confirmed; reasoning + citation corrected)

G1 already closed. G2 is real, and it is a **draw-site** divergence, not a
hit-site one: `Kusarigama.cs:115` draws with
`Rng.CombatTargets.NextItem(CombatState.HittableEnemies)`;
`sts2_rl/relics/kusarigama.py:46` draws over `self.living_enemies()` — same
mechanism as `bag_of_marbles` G2 (binding rule 3).

**Fix-pass correction (R4-review.md §1, entry 6, item 1 of "Required fixes"):**
the prior version of this paragraph gave the dormancy reason as "`DamageCmd.
deal` applies its own `should_allow_hitting` backstop before any hook fires."
That is a **red herring, and would be wrong if the two lists ever did
diverge**: the divergence is in the *draw* (which enemy `CombatTargets`
selects, and which RNG index gets burned against which list length), not in
the *hit*. A downstream refusal at the hit does not repair a mis-targeted,
mis-indexed draw. The only argument that actually defends dormancy is that
`living_enemies()` and `hittable_enemies()` provably return the SAME set for
every creature reachable in ported content today — restated below on that
basis alone, with the backstop clause dropped.

`should_allow_hitting` has **three** implementers — `IllusionPower`,
`ReattachPower` (the Decimillipede-segment power), and `AdaptablePower`. All
three gate their `False` case on `target is self.owner and self.is_reviving`,
and `is_reviving` is armed only from `on_death` (so `hp <= 0`, i.e.
`is_dead`) and always coincides with `is_dead=True` until the owner's own
revive/reattach move clears it — so `living_enemies()`'s `is_gone` filter
(`is_dead or escaped`) already excludes every creature `hittable_enemies()`
would additionally exclude through any of the three. The two enemy-list
builders therefore cannot disagree through any currently-reachable path, and
that — not the `DamageCmd` backstop — is why the draw-site divergence stays
dormant. Re-executed for real (R4-review.md defect D2 fix — the previous
version of this test never called `should_allow_hitting` or the two list
builders at all):
`test/test_r13_relic1.py::test_should_allow_hitting_false_always_coincides_with_is_dead`
now drives each of the three implementers to `is_reviving` through a real
lethal `DamageCmd.deal`, calls `cs.hooks.should_allow_hitting` directly, and
compares `{e for e in cs.enemies if not e.is_gone}` against
`cs.hittable_enemies` for each. Dormancy conclusion unchanged.

Citations: `Kusarigama.cs:115`, `CombatState.cs:142`, `Creature.cs:285-299`,
`sts2_rl/relics/kusarigama.py:46`, `sts2_rl/relics/base.py`
(`living_enemies`, `hittable_enemies`), `sts2_rl/hooks.py`
(`HookSystem.should_allow_hitting`), `sts2_rl/powers.py`
(`IllusionPower.should_allow_hitting`, `ReattachPower.should_allow_hitting`,
`AdaptablePower.should_allow_hitting` — symbol only, `powers.py` is under
concurrent edit this wave, see entry 5's fix-pass note).

### 7 & 8. `relic/lizard_tail/ShouldDieLate` and `relic/lizard_tail/AfterPreventingDeath` — STALE-ALREADY-FIXED

**Both hook-level entries are ledger staleness, not open gaps.** Each
entry's `issue` text reads "WHAT REMAINS is guard G3: the port still sets
`self._used = True` and `self._heal_pending = True` INSIDE `should_die_late`"
— but G3's *own* guard entry, in the very same `lizard_tail.json`, already
reads **"Closed 2026-07-29 (round 8)"**, with the fix (mark spent in
`after_preventing_death`, predicate left pure) already landed and pinned by
`test/test_tier1_last_five.py`. The hook-level summary text was simply never
updated after the guard closed — a copy that outlived its guard.

Re-verified against TODAY's `sts2_rl/relics/lizard_tail.py` and
`sts2_rl/cmds.py._resolve_death` (round 12 touched killing-blow ordering, and
a later, unrelated "tier-2 Task 19" pass added a `target.max_hp <= 0`
short-circuit to the same function — neither touches Lizard Tail's ordinary
damage-driven path): `should_die_late` (lines 32-52) is a pure predicate —
`if creature is not self.player: return True; return bool(self._used)` —
with no mutation. `after_preventing_death` (lines 54-71) is the sole place
`self._used = True` is set, and it heals `max(1, max_hp * 50 // 100)` from a
genuine 0 HP (the prevented-death arm no longer floors at 1,
`cmds.py:164-177`). All of G1, G2, G3, G4 and N1 read `faithful`/closed in
the record already; there is nothing left open under either hook.

Executed:
- `test/test_r13_relic1.py::test_lizard_tail_should_die_late_is_a_pure_predicate`
  — three bare queries never spend the charge.
- `test/test_r13_relic1.py::test_lizard_tail_charge_spent_and_healed_only_in_after_preventing_death`
  — a real lethal hit spends the relic, heals from 0 to exactly 50% max HP,
  and leaves the player alive.

Citations: `LizardTail.cs:40-59`, `CreatureCmd.cs:565-570`,
`sts2_rl/relics/lizard_tail.py:32-71`, `sts2_rl/cmds.py:126-177`.

### 9. `relic/miniature_cannon/ModifyDamageAdditive` — DORMANT-ENUMERATED (re-confirmed; reasoning corrected)

G1 (`dealer is self.player` alone, dropping C#'s `cardSource.Owner ==
Owner` alternative) is still real in
`sts2_rl/relics/miniature_cannon.py:35`. The sim's `Card` model has no
"owner" concept for this hook at all, so the missing disjunct cannot even be
represented, let alone reached; the only demonstrable direction is the
null-dealer one. Re-executed:
`test/test_r13_relic1.py::test_miniature_cannon_misses_a_null_dealer_upgraded_attack`
— an upgraded Strike with `dealer=None` gets +0 instead of the game's +3.

**Fix-pass correction (R4-review.md §1, entry 9):** the prior version of this
paragraph closed with "every ported `card=`-but-no-`dealer=player` site is
still a non-Strike, non-upgrade-relevant self-damage card." That does not
hold as written — Miniature Cannon does not care about the Strike tag at
all, only about `card.upgrade_level > 0`, and four of the nine self-damage
sites (`blood_wall`, `bloodletting`, `hemokinesis`, `offering`) ARE
upgradable (`max_upgrade_level == 1`). The real reason dormancy holds is the
relic's own `is_powered_attack` guard, not card content:
- Those four pass `props=DamageProps.CARD_HP_LOSS`, and
  `is_powered_attack(CARD_HP_LOSS)` is `False` — the relic's own first guard
  (and `cmds.py`'s stage gate) rejects them before the dealer check is ever
  reached.
- The other five self-damage sites (`burn`, `decay`, `infection`, `toxic`,
  `wither`) pass no `props` at all, but each has `is_unpowered = True` (so
  `DamageCmd.deal` infers `CARD_UNPOWERED`) **and** `max_upgrade_level == 0`,
  failing the guard twice over.

Citations: `MiniatureCannon.cs:31-34`, `sts2_rl/relics/miniature_cannon.py:23-37`,
`sts2_rl/cards/blood_wall.py`, `bloodletting.py`, `hemokinesis.py`,
`offering.py` (props census), `sts2_rl/cards/burn.py`, `decay.py`,
`infection.py`, `toxic.py`, `wither.py` (is_unpowered + upgrade-level census).

### 10. `relic/pen_nib/AfterCardPlayed` — STALE-ALREADY-FIXED for G3 (propose closing the hook-level entry)

G1 already closed. **G3 (the entry's remaining subject) is also now closed
by a fix already committed to this branch, elsewhere in round 13.**
`sts2_rl/combat.py`'s `_resolve_card_play` now reads:

```python
# Hook.AfterCardPlayed, per iteration and gated on the combat still
# being in progress (CardModel.cs:1957-1959).
#
# The gate is `IsInProgress`, NOT `IsOverOrEnding`: Hook.
# AfterCardPlayed (Hook.cs:278-294) is one of the dispatchers that
# deliberately BYPASS IterateCombatHookListeners... IsInProgress stays
# true between the killing blow and the teardown (it is cleared only
# from CheckWinCondition ... which runs after the whole play action),
# so C# DOES dispatch on the lethal iteration.
if not self.is_over:
    self.hooks.on_card_played(card, is_auto_play)
```

This is the *correct* reading of `CardModel.cs:1957-1959` and
`Hook.cs:275-276` (its own comment: "it completes resolution of the card
that caused the kill") — a strictly better analysis than the G3 guard's
original premise, which assumed C# *skips* `AfterCardPlayed` on the killing
iteration. It does not; C# fires it on that very iteration, because
`CheckWinCondition` (which would flip `IsInProgress`) does not run until
*after* the whole play action, in the OUTER `play_card`/`auto_play`. Verified
this holds for the sim too: `_check_win_condition()`/`_end_combat()` is
called only from the outer `play_card` (`combat.py:863`) and `auto_play`
(`:880`) — *after* `_resolve_card_play` returns — never from inside
`DamageCmd.deal` or `card.on_play()` for an ordinary attack. So on Pen Nib's
own killing 10th Attack, `self.is_over` is still `False` when
`on_card_played` fires, the mark clears correctly, and the relic does not
leak into the next combat. Pinned:
`test/test_r13_relic1.py::test_pen_nib_tenth_attack_that_ends_combat_still_unmarks`
— primes `_attacks_played = 9`, sets the enemy to 1 HP, plays a Strike that
ends the combat, and asserts `_card_to_double is None` afterward.

Citations: `CardModel.cs:1904-1965,1957-1959`, `Hook.cs:275-294`,
`sts2_rl/combat.py:883-996` (`_resolve_card_play`), `:822-865` (`play_card`),
`sts2_rl/relics/pen_nib.py:74-77`.

### 11. `relic/silver_crucible/ShouldGenerateTreasure` — DORMANT-ENUMERATED (re-confirmed, one leg not re-executed)

G3 (a suppressed treasure room still pays Spoils Map's gold) is still real:
`sts2_rl/run.py:1302` gates the chest relic+gold behind
`if all(r.should_generate_treasure(self) for r in self.relics):`, but
`resolution.gold += self._complete_map_point_quests(point)` at
`run.py:1320` sits **outside** that `if` block, unconditional. Re-confirmed
`cards/spoils_map.py:35` still pins `SPOILS_ACT_INDEX = 1`, consistent with
the prior reachability argument (Silver Crucible only suppresses the FIRST
treasure room, and Spoils Map targets act 2's, so the two can only meet if
act 1's unavoidable treasure node is skippable). I did **not** re-verify
from scratch that act 1's generated map always has exactly one all-TREASURE
row (that claim rests on `actmap.py` generation logic I did not re-derive
this round) — flagged here rather than silently inherited, per the brief's
instruction to enumerate what was actually checked.

Citations: `OneOffSynchronizer.cs:130-168`, `sts2_rl/run.py:1297-1320`,
`sts2_rl/cards/spoils_map.py:35`.

### 12. `relic/stone_calendar/BeforeSideTurnEnd` — DORMANT-ENUMERATED (re-confirmed; same census + reasoning correction as entry 6)

G1 already closed. G2 (`living_enemies()` vs `HittableEnemies`) is the same
mechanism as `bag_of_marbles` G2 and `kusarigama` G2 (binding rule 3).

**Fix-pass correction (R4-review.md §1, entry 6, carried here since it is the
same guard):** dormancy is NOT because of a `DamageCmd` backstop (that clause
defended a hit-site refusal, and stone_calendar's divergence, like
kusarigama's, is in the *draw* over `living_enemies()`, not the hit) — it is
because `living_enemies()` and `hittable_enemies()` provably return the same
set for every creature reachable in ported content: all three
`should_allow_hitting` implementers (`IllusionPower`, `ReattachPower`,
`AdaptablePower`) gate their `False` case on `is_reviving`, which never holds
without `is_dead` also holding, so `living_enemies()`'s `is_gone` filter
already excludes anything the extra `hittable_enemies()` check would. Covered
by the same re-executed test (R4-review.md defect D2 fix — now actually
calls `should_allow_hitting` and both list builders instead of asserting a
value it assigned itself):
`test_should_allow_hitting_false_always_coincides_with_is_dead`.

Citations: `StoneCalendar.cs:96`, `CombatState.cs:142`,
`sts2_rl/relics/stone_calendar.py:27`, `sts2_rl/relics/base.py`
(`living_enemies`, `hittable_enemies`), `sts2_rl/hooks.py`
(`HookSystem.should_allow_hitting`).

### 13. `relic/strike_dummy/ModifyDamageAdditive` (mechanism `damage_pipeline/G3`) — DORMANT-ENUMERATED (re-confirmed)

Identical shape and identical census to entry 3 (`fake_strike_dummy`). G1
already closed. G2 (`dealer is self.player` alone, missing C#'s
`cardSource.Owner == Owner` disjunct) is still real in
`sts2_rl/relics/strike_dummy.py:34`. Re-executed:
`test/test_r13_relic1.py::test_strike_dummy_misses_a_null_dealer_strike`.

Citations: `StrikeDummy.cs:21-36`, `sts2_rl/relics/strike_dummy.py:24-36`.

### 14. `relic/unsettling_lamp/BeforePowerAmountChanged` — NARROWED (G2 closed by a concurrent lane's fix; G3+G4 stay open)

**The relic was substantially rewritten since this record's 2026-07-26
audit.** `sts2_rl/relics/unsettling_lamp.py` no longer has a `modify_power_
amount` method at all — the hook entry's own `maps_to` citation
(`"modify_power_amount (unsettling_lamp.py:44-53)"`) is stale. The current
file implements `on_combat_start` (clears `_in_flight`/`_triggering`/
`_finished`), `before_card_played`/`on_card_played` (the ambient card
bracket, C#'s `TriggeringCard`/`AfterCardPlayed` analogue), and a single
`modify_power_amount_given_multiplicative` — matching `seam/power_cmd.json`'s
own description of its concurrent "Task 17/18" rework, which split the
sim's power-amount pipeline into given-additive / given-multiplicative /
received chains mirroring C#'s three separately-sequenced calls. That record's
own guards (`power_cmd` G2, G3, G4, G5, G6) all read **"Closed 2026-07-31"**
(today's date) — confirmed by reading the actual code, not by trusting the
date stamp.

**G2 (sign-aware `GetTypeForAmount`, plus a spurious `amount <= 0` bail) is
CLOSED.** Read `UnsettlingLamp.cs:71-129` in full: neither the latch
(`BeforePowerAmountChanged`) nor the double
(`ModifyPowerAmountGivenMultiplicative`) has an `amount <= 0` guard anywhere
— both gate purely on `power.GetTypeForAmount(amount) != PowerType.Debuff`.
The sim's current `modify_power_amount_given_multiplicative` (lines 45-80)
does the same: `power_cls.type_for_amount(amount) != PowerType.DEBUFF`, no
`<= 0` bail. Malaise/Resonance (the two C# cards this would matter for) are
still unported (`grep -rli "malaise\|resonance" sts2_rl/cards/` — nothing),
so the fix is dormant-on-content but genuinely present. Pinned:
`test/test_r13_relic1.py::test_unsettling_lamp_doubles_a_negative_amount_buff_sign_aware`
— a synthetic `-3 Strength` (AllowNegative, sign-flips to Debuff) applied to
an enemy during the latch window doubles to `-6`.

**G3 (no target-side/applier check on C#'s multiplicative pass — only the
latch has one) is STILL OPEN, still dormant.** `UnsettlingLamp.cs:106-129`
(`ModifyPowerAmountGivenMultiplicative`) checks only `TriggeringCard`,
`IsFinishedTriggering`, `HasDoubledTemporaryPowerSource` and
`GetTypeForAmount` — no applier, no target side. Only the LATCH
(`BeforePowerAmountChanged`, lines 85 `applier != Owner.Creature`, 89
`target.Side == Owner.Creature.Side`) has those checks, and it only runs
once, to *set* `TriggeringCard`. So once a card has latched (an
owner-applied, enemy-targeted debuff), C# doubles *every subsequent* debuff
from that same card regardless of who it targets. The sim's
`modify_power_amount_given_multiplicative` re-applies `applier is not
self.player or target is self.player` on **every** call, including
subsequent ones from an already-triggering card — so a card that debuffs an
enemy and then the player in one play would be under-doubled in the sim.
Re-confirmed unreachable: the 6 ported player-only-debuffing cards
(`battle_trance`, `doubt`, `expect_a_fight`, `panic_button`, `shame`,
`the_gambit` — read all four non-Curse ones in full) apply nothing to an
enemy at all. Pinned:
`test/test_r13_relic1.py::test_unsettling_lamp_g3_same_card_self_debuff_not_doubled_dormant`
— demonstrates the sim's refusal directly against the mechanism.

**G4 (ambient `_in_flight` card-tracking substitutes for C#'s explicit
`cardSource` parameter) is STILL OPEN, still dormant.**

**Fix-pass replacement (R4-review.md §1, entry 14 / §2 miss 1 / §5 item 2 —
the protocol's dormancy-enumeration rule was not met by the prior version of
this paragraph, and the review's own re-derivation is reproduced here in
full, per the fix-pass brief's instruction to carry it into this
record-closing text nearly verbatim):**

The prior version of this paragraph checked whether the previously-recorded
3-site `auto_play_card` census had grown by one (`howl_from_beyond.py`) and
stopped. Re-grepping the whole package (`grep -rn "auto_play_card(" sts2_rl/`,
re-run again during this fix pass and unchanged) finds **ten** call sites,
not three or four:

```
cards/cascade.py:58            cmds.py:1552 (CardPileCmd.auto_play_from_draw_pile)
cards/colorless_skills.py:134  enchantments.py:401 (Imbued)
cards/colorless_skills.py:187  potions.py:1050
cards/howl_from_beyond.py:51   powers.py:999  (HellraiserPower)
                                powers.py:1355 (StampedePower)
                                relics/whispering_earring.py:86
```

Two of the six previously-omitted sites are not mere bookkeeping — they
widen the class G4's reachability argument has to cover:

- **`cards/havoc.py:53`** calls `CardPileCmd.auto_play_from_draw_pile`
  (`cmds.py:1498-1552`, which itself calls `auto_play_card` at `cmds.py:1552`
  — confirmed by reading `havoc.py`'s `on_play` directly) from inside its
  own `on_play`. That is a **fifth card-level nested auto-play** the
  "3 sites"/"4 sites" figure never included, and other records (queue
  annotations, `seam/hook_dispatch`-adjacent notes) cite that stale figure.
- **`HellraiserPower`** (`powers.py:979-999`, applied by `cards/hellraiser.py:36`
  via `PowerCmd.apply(ctx.hooks, ctx.player, HellraiserPower, 1,
  applier=ctx.player)`) auto-plays from `on_card_drawn_early` whenever a
  Strike-tagged card is drawn — not from inside another card's `on_play` at
  all. That turns **every card that draws mid-resolution** into a potential
  nested-auto-play site, which is a strictly larger reachable class than
  "cards that call `auto_play_card` themselves." G4's prior reachability
  argument was never stated against that larger set.

Re-derived the verdict against the CORRECT set rather than trusting either
the old 3/4-site figure or a re-count alone: an AST census over
`sts2_rl/cards/` for classes that both draw (`DrawCmd.draw` /
`auto_play_from_draw_pile` / `draw_cards`) **and** apply a power to a
non-player target yields exactly **one** class, `MadScienceCard`
(`sts2_rl/cards/mad_science.py`). Read its `on_play` dispatch in full
(`mad_science.py:101-107`): `tinker_type` is fixed once, per instance, by
`configure()` (`:80-89`), and `on_play` branches on it —
`_play_attack` (`:111-132`, the ATTACK branch: applies `sapping`/`choking`
enemy debuffs — Weak+Vulnerable or Strangle — via `PowerCmd.apply` at
`:124-132`) and `_play_skill` (`:134-141`, the SKILL branch: the `wisdom`
rider draws via `DrawCmd.draw` at `:140`) are **mutually exclusive
branches of the same `if/elif`** — a single card instance is configured as
one `CardType` and can never take both branches in the same play. So no
ported card can draw a card mid-resolution (arming Lamp's ambient
`_in_flight` latch via a nested auto-play, or via Hellraiser) AND apply a
debuff of its own in that same play: `havoc`/`cascade`/`colorless_skills`/
`howl_from_beyond` apply no debuff at all (confirmed by reading each
`on_play`), and Mad Science's own debuff and its own draw are on branches
that cannot both fire. **G4 stays DORMANT** — the verdict the prior version
of this paragraph reached is correct, but the enumeration behind it has been
replaced with the 10-site census plus the Hellraiser class-widening, and the
"3 sites"/"4 sites" figure other records may still cite needs re-checking
wherever it appears (R4-review.md F3).

**Verdict: NARROWED.** Propose closing G2 (`faithful`) and leaving the
hook-level rollup `gap`, now carrying only G3+G4.

**Fix-pass finding (R4-review.md §1, entry 14, final paragraph) — the
manifest is wrong about this rollup's membership.** The unlabelled-batch
manifest's issue text for this entry says the divergences are "verdicted at
its own guard (G2, G3, G4, **G5**)." `audit/records/relic/unsettling_lamp.json`
has no G5 — its guard-level entries are G1 (faithful), N1, G2, N2, G3, G4,
N3, N4, N5, and the only `gap`s are G2/G3/G4 (G2 now closes per this report).
This is a manifest-generator defect (the manifest is generated tooling, not
this record), not part of this hook's own reasoning — noted here rather than
silently followed, since a future pass reading the manifest alone would look
for a G5 that does not exist.

Citations: `UnsettlingLamp.cs:62-168` (read in full), `PowerModel.cs:460-471`,
`seam/power_cmd.json` guards G1-G6 (all "Closed 2026-07-31"),
`sts2_rl/relics/unsettling_lamp.py` (current, entire file — 80 lines, all
read), `sts2_rl/hooks.py:636-728` (given/received chain doc comments),
`sts2_rl/cards/battle_trance.py`, `doubt.py`, `expect_a_fight.py`,
`shame.py`, `colorless_skills.py:462,799` (`panic_button`, `the_gambit`),
`sts2_rl/cards/havoc.py:53`, `cascade.py:58`, `colorless_skills.py:134,187`,
`howl_from_beyond.py:51`, `sts2_rl/cmds.py:1498-1552`
(`CardPileCmd.auto_play_from_draw_pile`), `sts2_rl/enchantments.py:401`,
`sts2_rl/potions.py:1050`, `sts2_rl/powers.py:979-999` (`HellraiserPower`),
`:1355` (`StampedePower`), `sts2_rl/relics/whispering_earring.py:86`,
`sts2_rl/cards/hellraiser.py:36`, `sts2_rl/cards/mad_science.py:80-141`
(`MadScienceCard`, read in full).

---

## Record-close proposals

1. **`audit/records/relic/lizard_tail.json`**, entry key `hooks.ShouldDieLate`
   → verdict `faithful`. Close note: the `issue` text's "WHAT REMAINS is
   guard G3" is stale — G3 (and G1, G2, G4, N1) already read `faithful`/
   closed in this same file (G3: "Closed 2026-07-29 (round 8)"). Replace the
   hook-level `issue` with a short pointer to the closed guards; no
   reasoning survives that isn't already stated on the guards themselves.

2. **`audit/records/relic/lizard_tail.json`**, entry key
   `hooks.AfterPreventingDeath` → verdict `faithful`. Same close note as
   above (both hook entries carry byte-identical stale `issue` text).

3. **`audit/records/relic/pen_nib.json`**, entry key `hooks.AfterCardPlayed`
   → verdict `faithful`. Close note: replaces "C# skips Hook.AfterCardPlayed
   entirely when the play ended the combat (CardModel.cs:1957 gates on
   CombatManager.IsInProgress) while combat.py:514 always fires it" — this
   was a **misreading** of the C# gate (see Hook.cs:275-276's own comment:
   the hook is a deliberate bypass specifically so it "completes resolution
   of the card that caused the kill", i.e. C# still fires it on the killing
   iteration). `sts2_rl/combat.py`'s current `if not self.is_over:` gate,
   already committed elsewhere in round 13, gets this right — it does not
   suppress the killing iteration (win-check runs later, in the outer
   caller) but does suppress genuinely-later dispatches against an
   already-over combat. Pinned by
   `test/test_r13_relic1.py::test_pen_nib_tenth_attack_that_ends_combat_still_unmarks`.

4. **`audit/records/relic/unsettling_lamp.json`**, guard key `G2` (the
   sign-aware `GetTypeForAmount` + spurious `amount<=0` bail) → verdict
   `faithful`. Close note: **this guard was already independently closed by
   `seam/power_cmd.json`'s own `G2`** ("Closed 2026-07-31 (tier-2
   campaign): (Task 17.)") — this record's copy of the same guard was never
   flipped to match. Re-verified directly against `UnsettlingLamp.cs:71-129`
   (no `amount<=0` bail anywhere in the file) and today's
   `unsettling_lamp.py` (sign-aware `type_for_amount`, no bail). Pinned by
   `test/test_r13_relic1.py::test_unsettling_lamp_doubles_a_negative_amount_buff_sign_aware`.
   The hook-level entry `hooks.BeforePowerAmountChanged` stays `gap`
   (G3+G4 remain open) but its `maps_to`/`issue` text should be rewritten:
   the method it names, `modify_power_amount (unsettling_lamp.py:44-53)`,
   no longer exists — the relic now implements
   `modify_power_amount_given_multiplicative` plus the
   `before_card_played`/`on_card_played` latch bracket, and G3/G4 should be
   restated against that shape (their own guard-level text already
   describes it correctly; only the hook-level rollup's prose is stale).
   **G4's own guard-level enumeration must ALSO be replaced** (this is the
   fix R4-review.md required — the protocol's dormancy-enumeration rule
   "ask what else reads this, not does the recorded consumer still hold"
   was not met by the 3-/4-site `auto_play_card` census the guard
   previously carried): `grep -rn "auto_play_card(" sts2_rl/` finds **ten**
   call sites — `cards/cascade.py:58`, `colorless_skills.py:134`, `:187`,
   `howl_from_beyond.py:51`, `cmds.py:1552`
   (inside `CardPileCmd.auto_play_from_draw_pile`, itself called from
   `cards/havoc.py:53` — a fifth card-level nested auto-play the old figure
   never counted), `enchantments.py:401` (Imbued), `potions.py:1050`,
   `powers.py:999` (`HellraiserPower`), `powers.py:1355` (`StampedePower`),
   `relics/whispering_earring.py:86`. `HellraiserPower` (applied by
   `cards/hellraiser.py:36`) auto-plays from `on_card_drawn_early` on ANY
   Strike-tagged draw, which widens the reachable class from "cards that
   call `auto_play_card`" to "any card that draws mid-resolution." The
   verdict still survives: an AST census over `sts2_rl/cards/` for classes
   that both draw and apply a power to a non-player target yields exactly
   one class, `MadScienceCard` (`sts2_rl/cards/mad_science.py:80-141`), whose
   `on_play` (`:101-107`) dispatches to `_play_attack` (`:111-132`, the
   enemy-debuffing branch: `sapping`/`choking` via `PowerCmd.apply`) and
   `_play_skill` (`:134-141`, the drawing branch: `wisdom`'s `DrawCmd.draw`)
   as MUTUALLY EXCLUSIVE branches of one `if/elif` keyed on a per-instance
   `tinker_type` fixed by `configure()` — so no single card instance can
   both draw mid-resolution and debuff an enemy of its own. The other nine
   sites (`havoc`, `cascade`, `colorless_skills` ×2, `howl_from_beyond`,
   `enchantments.py`'s Imbued, `potions.py`, `StampedePower`,
   `whispering_earring`) apply no debuff of their own at all. G4 stays
   `gap`/dormant; only its enumeration changes.

5. **`audit/records/relic/fur_coat.json`**, hook entry
   `hooks.AfterCreatureAddedToCombat` — **no verdict change** (stays `gap`
   via inherited G3), but propose rewriting divergence "(a)" out of the
   `issue` text entirely: it is not a narrowed-but-real "shadowed"
   divergence, it is a citation error (`CombatManager.AfterCreatureAdded` at
   `CombatManager.cs:860-867` is not `Hook.AfterCreatureAddedToCombat`; the
   latter's only C# dispatch is `CreatureCmd.cs:81`, matching the sim's
   `CreatureCmd.add` exactly). Pinned by
   `test/test_r13_relic1.py::test_on_creature_added_hook_never_fires_for_starting_enemies`.

No other entry's verdict changes; the remaining 8
(`archaic_tooth/AfterObtained`, `booming_conch/AfterSideTurnStart`,
`fake_strike_dummy/ModifyDamageAdditive`, `gremlin_horn/AfterDeath`,
`kusarigama/AfterCardPlayed`, `miniature_cannon/ModifyDamageAdditive`,
`silver_crucible/ShouldGenerateTreasure`, `stone_calendar/BeforeSideTurnEnd`,
`strike_dummy/ModifyDamageAdditive`) stay `gap`/dormant, now backed by
fresh 2026-07-31 execution instead of inherited 2026-07-26/27 prose. Two of
those (`gremlin_horn/AfterDeath`, `kusarigama/AfterCardPlayed`) have a
guard-level citation that has gone stale in COUNT (not conclusion) — see
entries 5 and 6 above — worth a text-only correction whenever those guards
are next touched.

---

## Queue-annotation proposals (for `audit/GAP-QUEUE.md`, terse style)

- `relic/archaic_tooth/AfterObtained` — dormant — re-executed 2026-07-31: 0 of
  203 registered cards exceed `max_upgrade_level` 1, and no
  `Enchantment.can_enchant` (now 9 predicates, up from the ~3 the 2026-07-26
  audit considered) discriminates Bash from Break; both guards' reachability
  premise still holds.
- `relic/booming_conch/AfterSideTurnStart` — dormant — re-executed
  2026-07-31: the grant still bypasses `hooks.modify_energy_gain`;
  `NoEnergyGainPower` still expires at the owner's own turn end, before the
  relic's turn-1-only window can ever see it applied.
- `relic/fake_strike_dummy/ModifyDamageAdditive` — dormant — re-executed
  2026-07-31: all 8 Strike-tagged cards still pass `dealer=player`; no
  self-damage `card=`-no-`dealer` site carries the tag.
- `relic/fur_coat/AfterCreatureAddedToCombat` — dormant — CITATION FIX:
  divergence (a) was a misreading (`CombatManager.AfterCreatureAdded` !=
  `Hook.AfterCreatureAddedToCombat`; the latter dispatches only from
  `CreatureCmd.Add`/`CreatureCmd.add` on both sides, always). Only G3
  (SetCurrentHp notification) remains, unchanged, still dormant.
- `relic/gremlin_horn/AfterDeath` — dormant — re-executed 2026-07-31: the
  ordering divergence (G2) is unchanged, but the sim now HAS two
  `on_damage_dealt` implementers (`ImbalancedPower`, `PaperCutsPower`) —
  both gate on the enemy owner being the dealer, so neither reaches the
  player-kills-enemy window Gremlin Horn's own timing depends on.
- `relic/kusarigama/AfterCardPlayed` — dormant — re-executed 2026-07-31:
  `should_allow_hitting` now has 3 implementers (was 2: a Decimillipede
  segment power joined Illusion/Adaptable), all gating on `is_reviving`,
  which always coincides with `is_dead` — `living_enemies()` still cannot
  diverge from `hittable_enemies()` through any of them.
- `relic/lizard_tail/ShouldDieLate` and `relic/lizard_tail/AfterPreventingDeath`
  — CLOSED 2026-07-31: stale ledger only. Guards G1-G4 and N1 were already
  `faithful` (G3 since round 8); the hook-level `issue` text just never
  caught up. Nothing left open on either hook.
- `relic/miniature_cannon/ModifyDamageAdditive` — dormant — re-executed
  2026-07-31: `dealer=None` on an upgraded card still gets +0, not +3; the
  missing `cardSource.Owner == Owner` disjunct has no sim representation to
  even attempt.
- `relic/pen_nib/AfterCardPlayed` — CLOSED 2026-07-31: G3's premise
  misread the C# gate (Hook.AfterCardPlayed is a deliberate IsOverOrEnding
  bypass specifically so it fires on the killing iteration; C# does NOT skip
  it there). The sim's `if not self.is_over:` gate (already committed
  elsewhere in round 13) gets this right; a combat-ending 10th Attack still
  clears the mark.
- `relic/silver_crucible/ShouldGenerateTreasure` — dormant — re-confirmed
  2026-07-31: `_complete_map_point_quests` still pays outside the
  `should_generate_treasure` gate; `SPOILS_ACT_INDEX` still 1. The
  act-1-treasure-row-is-unavoidable leg was inherited, not re-derived, this
  round.
- `relic/stone_calendar/BeforeSideTurnEnd` — dormant — same
  `should_allow_hitting` census update as kusarigama; conclusion unchanged.
- `relic/strike_dummy/ModifyDamageAdditive` — dormant — re-executed
  2026-07-31, same census as fake_strike_dummy.
- `relic/unsettling_lamp/BeforePowerAmountChanged` — NARROWED 2026-07-31:
  the relic was rewritten by a concurrent Task 17/18 already committed to
  this branch (see `seam/power_cmd.json` G2-G6, "Closed 2026-07-31"). G2
  (sign-aware typing) is closed; G3 (no target/applier check on C#'s
  multiplicative pass) and G4 (ambient card-tracking) remain open, still
  dormant — re-censused against the FULL 10-site `auto_play_card` census
  (`cascade`, `colorless_skills` ×2, `howl_from_beyond`, `havoc` [via
  `auto_play_from_draw_pile`], `enchantments.py` Imbued, `potions.py`,
  `HellraiserPower`, `StampedePower`, `whispering_earring`) PLUS
  `HellraiserPower`'s class-widening (any Strike-tagged draw auto-plays, not
  just cards that call `auto_play_card` themselves — so the reachable class
  is "any card that draws mid-resolution"). Verdict survives on
  `MadScienceCard`'s mutually-exclusive ATTACK/SKILL branches (its own
  enemy-debuff and its own draw can never both fire from one instance) — the
  only ported class that both draws and debuffs an enemy. The prior 3-/4-site
  figure was wrong by ~2.5x and several other records still cite it; any
  reachability argument resting on that figure needs re-checking, not just
  this one (R4-review.md F3).

---

## Tests

**Added**: `test/test_r13_relic1.py` (new, 14 tests, all passing).

**Commands run**:

```
py -m pytest test/test_r13_relic1.py -v
  -> 14 passed

py -m pytest test/test_r13_relic1.py test/test_relics.py test/test_relic_live_tail.py \
  test/test_relic_residue_gaps.py test/test_relic_tier1_gaps.py test/test_tier1_last_five.py \
  test/test_hook_order.py test/test_power_type_for_amount.py test/test_power_modifier_phases.py \
  test/test_combat_over_hook_gate.py test/test_powers.py -q
  -> 516 passed
```

No production file was edited, so no regression risk beyond the new test
file itself; the broader run above covers every existing test file whose
subject matter overlaps what I verified (relic tests, hook-dispatch-order
tests, the power-amount-chain tests `seam/power_cmd`'s Task 17/18 pinned, and
the combat-over-hook-gate tests `pen_nib`'s fix rides on).

---

## Findings not in the brief (outrank the fixes above per the protocol)

1. **`fur_coat` citation error**: the record's "(a)" divergence
   (`CombatManager.StartCombatInternal` firing `Hook.AfterCreatureAddedToCombat`
   for starting creatures) conflates two same-named-but-different C# methods
   — `CombatManager.AfterCreatureAdded` (engine bookkeeping: room-added
   fixup + move roll, never calls the hook) and `Hook.
   AfterCreatureAddedToCombat` (the relic/power hook, dispatched only from
   `CreatureCmd.Add`). Grepped the whole decompiled source to confirm the
   hook has exactly one dispatch site game-wide. Not a narrowing — the
   claimed divergence never existed.

2. **`pen_nib` G3's premise was backwards**: it assumed C# *skips*
   `Hook.AfterCardPlayed` on a combat-ending play. Read `Hook.cs:275-294` in
   full — the opposite is explicitly documented in the source's own comment
   ("Dispatched directly, not through the IterateCombatHookListeners guard:
   it completes resolution of the card that caused the kill"). Worth a
   pattern check elsewhere in the ledger: any other entry reasoning from "C#
   gates X on IsInProgress/IsOverOrEnding" for one of the ten deliberate
   `IterateCombatHookListeners` bypasses (`AfterCardPlayed`,
   `AfterDamageGiven`, `AfterBlockBroken`, `AfterCreatureAddedToCombat`,
   `AfterDiedToDoom`, `ModifyKeywordsInCombat`,
   `ModifyUnblockedDamageTarget`,
   `ShouldCreatureBeRemovedFromCombatAfterDeath`,
   `ShouldStopCombatFromEnding`, `ShouldPowerBeRemovedOnDeath` —
   `sts2_rl/hooks.py:59-69`'s own enumeration) should be re-checked against
   the SAME caller-level gate this entry needed (`CardModel.cs:1957`'s own
   `IsInProgress` test), not against the generic dispatcher gate.

3. **`unsettling_lamp.py` was substantially rewritten by already-committed,
   concurrent round-13 work** (not live-concurrent — already merged into
   this branch's history under commits predating my task). The relic's
   `audit/records/relic/unsettling_lamp.json` hook-level `maps_to` citation
   names a method (`modify_power_amount`) that no longer exists in the file.
   Its sibling record `seam/power_cmd.json` already reflects the rework in
   full (guards G1-G6 all closed 2026-07-28..31) but `relic/
   unsettling_lamp.json`'s own G2 (a literal duplicate of `power_cmd`'s G2)
   was never flipped to match. Given the manifest's own note that this
   batch's `relic/ruined_helmet/*` entries "likely predate" round 12's Task
   18 rework — the SAME staleness reaches `unsettling_lamp`, one hop further
   than the brief anticipated (Task 17/18, not Task 18 alone, and it landed
   in round 13, not round 12).

4. **Fix-pass correction (R4-review.md F3): the `auto_play_card` census this
   batch (and other records) cited is wrong by a factor of ~2.5.** The prior
   version of this finding reported only a fourth site
   (`sts2_rl/cards/howl_from_beyond.py:51`) against a remembered "3 sites"
   baseline (cascade, colorless_skills ×2) and stopped there. A full re-grep
   (`grep -rn "auto_play_card(" sts2_rl/`) finds **ten** call sites: the four
   already known, plus `cmds.py:1552` (inside
   `CardPileCmd.auto_play_from_draw_pile`, itself called from
   `cards/havoc.py:53` — a fifth CARD-level nested auto-play the old figure
   never counted), `enchantments.py:401` (Imbued), `potions.py:1050`,
   `powers.py:999` (`HellraiserPower`), `powers.py:1355` (`StampedePower`),
   and `relics/whispering_earring.py:86`. `HellraiserPower`
   (`powers.py:979-999`, applied by `cards/hellraiser.py:36`) auto-plays from
   `on_card_drawn_early` on any Strike-tagged draw — not by calling
   `auto_play_card` from inside another card's `on_play` at all — which makes
   the truly reachable class "any card that draws mid-resolution," not
   "cards that call `auto_play_card`." Checked against `unsettling_lamp` G4's
   shape and the verdict still holds (see entry 14 above and the record-close
   proposal for the full `MadScienceCard` argument), but **any record whose
   reachability argument rests on the old "3 sites"/"4 sites" figure needs
   re-checking, not just `unsettling_lamp` G4** — this is the pattern-level
   finding, not a single-record fix.

5. **New gap, not in any record found by search (R4-review.md F1): the sim's
   card-play loop is missing C#'s `Owner.Creature.IsDead` early return before
   `Hook.AfterCardPlayed`.** `CardModel.cs:1904-1965` checks
   `if (Owner.Creature.IsDead) return;` at **:1932** (after `OnPlay`),
   **:1940** (after the enchantment's `OnPlay`), and **:1950** (after the
   affliction's) — all *before* the `IsInProgress`-gated `Hook.AfterCardPlayed`
   at `:1957-1959` — and again at `:1960` after it.
   `sts2_rl/combat.py:940-996`(`_resolve_card_play`) has no such check: it
   runs `card.on_play`, `after_attack`, `card.enchantment.on_play`, then
   `if not self.is_over: self.hooks.on_card_played(...)` at `:986`, and only
   *then* `if self.player.is_dead: break` at `:995` (that check breaks the
   ALL_ENEMIES routing loop, not the play itself). So a card play that kills
   its OWN player — Offering / Bloodletting / Hemokinesis / Blood Wall at low
   HP, or a self-damage curse — dispatches `AfterCardPlayed` to every
   listener in the sim where C# would have already returned. `combat.py` is
   outside this lane's footprint (`sts2_rl/relics/*.py` and `test/` only), so
   this is filed as a queue item, not fixed here. Likely unobservable in a
   single-player run that is over anyway (both the player's own subsequent
   actions and any AI decisions are moot once the player is dead), but it is
   a real ordering divergence sitting inside the very hook two of this
   batch's entries (`pen_nib`, `kusarigama`) own, and should be reasoned
   about under `seam/hook_dispatch` or a `seam/card_play` mechanism rather
   than left undiscovered. **Queue-annotation proposal:**
   `seam/hook_dispatch` (or a new `seam/card_play` mechanism) — new gap,
   found 2026-08-01 (R4 fix pass, from R4-review.md F1): the sim's
   `_resolve_card_play` dispatches `hooks.on_card_played` even when the
   card's own play just killed the PLAYER, where `CardModel.cs:1932,1940,
   1950,1960`'s `Owner.Creature.IsDead` early-returns would have skipped it
   (C#'s equivalent gate is on the CARD OWNER's death, not the enemy's — this
   is a different creature than the one `pen_nib`/`kusarigama`'s own
   killing-blow analysis covers). Unreached in practice (self-damage cards
   that also carry hook-relevant follow-up content are rare/unported and a
   dead player ends the combat regardless), but unreasoned-about; needs a
   fix in `sts2_rl/combat.py`'s `_resolve_card_play`, outside every current
   lane's footprint.

## Status summary

- 2 entries CLOSED (both `lizard_tail`) — ledger staleness, no code change.
- 1 entry CLOSED (`pen_nib/AfterCardPlayed`) — mechanism already fixed by
  other round-13 work; ledger staleness, no code change from me.
- 1 entry NARROWED (`unsettling_lamp/BeforePowerAmountChanged`) — one guard
  (G2) closed by other round-13 work; two (G3, G4) remain open, re-confirmed
  dormant.
- 1 entry NARROWED with a citation correction (`fur_coat/
  AfterCreatureAddedToCombat`) — net verdict unchanged (still `gap` via G3),
  but its own "(a)" reasoning was wrong and should be struck.
- 9 entries DORMANT-ENUMERATED, verdict unchanged, all re-executed against
  today's code and ported-content census (not inherited from the 2026-07-26
  audit date).
- 0 entries required a production code fix.

---

## Fix pass (2026-08-01)

Applied `.superpowers/sdd/round13/R4-review.md`'s NEEDS-FIXES items. All 14
verdicts stand unchanged, per the review's own finding and the fix-pass
brief's instruction not to re-litigate them. Footprint respected:
`test/test_r13_relic1.py` and this report only; no `sts2_rl/` production
edits, no `audit/**` edits, no git index mutations.

### Test repairs (review §3, defects D1/D2/D3)

All three defective tests were repaired by making them execute the real code
path the report claims they pin, confirmed RED-then-GREEN by temporarily
inverting the corrected assertion (never by touching production code), then
restoring the correct assertion:

1. **D1 — `test_on_creature_added_hook_never_fires_for_starting_enemies`
   (`fur_coat`).** The spy was registered AFTER `_combat(...)` had already
   built the `CombatState`, so `assert calls == []` could never fail — the
   spy did not exist yet to observe anything. Fixed by monkeypatching
   `sts2_rl.hooks.HookSystem.on_creature_added` at the class level BEFORE
   calling `_combat(...)`, so the counter is live for the entire
   starting-roster build, then restoring the original method in a `finally`.
   **RED evidence:** inverted the first assertion to
   `assert calls != []` and re-ran — failed with `assert [] != []` (i.e. the
   test now genuinely observes that zero calls fire during construction,
   where the old version would have passed either way).

2. **D2 — `test_should_allow_hitting_false_always_coincides_with_is_dead`
   (`kusarigama`, `stone_calendar`).** The original never called
   `should_allow_hitting`, `hittable_enemies`, or a `living_enemies`
   equivalent, exercised only 1 of the 3 implementers (`AdaptablePower` was
   imported and unused), and its two assertions restated a value the test
   itself had just assigned (`enemy.hp = 0` then `assert enemy.is_dead`).
   Rewritten to drive all three implementers — `IllusionPower` (applied
   directly to a plain monster), `AdaptablePower` (via `TEST_SUBJECT_BOSS`,
   which self-applies it in `TestSubject.__init__`), and `ReattachPower` (via
   `DECIMILLIPEDE_ELITE`, whose three segments self-apply it and need an
   OTHER live segment present or `on_death`'s `_all_others_down()`
   short-circuits before `is_reviving` is armed at all) — to `is_reviving`
   through a REAL lethal `DamageCmd.deal` (not a hand-set hp + direct
   `on_death` call), then call `cs.hooks.should_allow_hitting` directly and
   compare `{e for e in cs.enemies if not e.is_gone}` against
   `cs.hittable_enemies` for each. **RED evidence:** (a) inverted
   `should_allow_hitting(reviver) is False` to `is True` for the
   IllusionPower leg — failed with `assert False is True`; (b) inverted the
   ReattachPower leg's set-equality to include the reviving `victim` —
   failed with a set-membership mismatch showing `victim` genuinely absent
   from both `living` and `hittable_enemies`. Both confirm the assertions
   are live, not vacuous.

3. **D3 — `test_strike_tagged_cards_all_deal_damage_with_the_player_as_dealer`
   (`fake_strike_dummy`/`strike_dummy`/`miniature_cannon`'s shared census).**
   The name and docstring promised a dealer census; the body asserted only
   `len(strike_tagged) == 8`. Rewritten to actually PLAY each of the 8
   Strike-tagged cards through `cs.play_card(0)` (the public API, same path
   `pen_nib`'s test uses) with `DamageCmd.deal` wrapped (a `staticmethod`
   monkeypatch on `sts2_rl.cmds.DamageCmd`, restored in `finally`) to record
   every `dealer=` argument it is called with, then assert every recorded
   dealer for every card is the acting player. Draw-pile padding
   (`cs.player.draw_pile.extend(...)`) was added because `_combat`'s helper
   clears the initial hand without returning it to the draw pile, and
   `pommel_strike`/`seeker_strike` each draw or offer cards mid-resolution.
   **RED evidence:** inverted the final assertion to
   `assert all(d is not cs.player for d in recorded_dealers)` — failed on
   the very first card (`strike`) with `assert False`, showing the recorded
   dealer really is the player, for real play traffic.

All three fixes were verified against the current worktree, not assumed from
the review's prose (constructor signatures, `should_power_be_removed_after_
owner_death`/`should_power_be_removed_on_death` strip semantics for
`IllusionPower`/`AdaptablePower`/`ReattachPower`, and all 8 strike-tagged
cards' `on_play` bodies were read directly before writing the new
assertions).

### Report repairs (review §1 entries 1/5/6/9/12/14, §2, §4, §5)

- **Entry 1 (`archaic_tooth`), F2**: corrected G2's characterisation from "the
  sim adds a `can_enchant` condition C# lacks" to the accurate "silent skip
  vs. hard throw" (`CardCmd.cs:532-538` throws `InvalidOperationException` on
  `!CanEnchant`; C# does not lack the condition). Dormancy unaffected.
- **Entry 5 (`gremlin_horn`), F4**: dropped the stale `powers.py` line-number
  citations (verified independently that a fresh `grep`/read of
  `ImbalancedPower`/`PaperCutsPower` today gives yet a THIRD set of line
  numbers, different again from the review's own pass — `powers.py` is under
  live concurrent edit this wave) and cited both by symbol only, per the
  review's own recommendation.
- **Entries 6 & 12 (`kusarigama`, `stone_calendar`)**: replaced the "dormant
  because `DamageCmd.deal`'s `should_allow_hitting` backstop" reasoning
  (a red herring that would not defend a draw-site divergence — the
  divergence is in which enemy `CombatTargets` draws, not in whether a hit
  lands) with the load-bearing list-coincidence argument: all three
  `should_allow_hitting` implementers gate `False` on `is_reviving`, which
  never holds without `is_dead`, so `living_enemies()` and
  `hittable_enemies()` cannot diverge through any of them.
- **Entry 9 (`miniature_cannon`)**: replaced "every ported self-damage site is
  non-upgrade-relevant" (false as stated — 4 of the 9 self-damage sites ARE
  upgradable) with the real reason: those 4 pass `DamageProps.CARD_HP_LOSS`
  and fail the relic's own `is_powered_attack` guard; the other 5 have
  `is_unpowered = True` AND `max_upgrade_level == 0`, failing it twice over.
  Verified directly (`grep -n "CARD_HP_LOSS\|max_upgrade_level"` /
  `"is_unpowered"` against the actual card files).
- **Entry 14 (`unsettling_lamp`) G4**: replaced the 3-/4-site
  `auto_play_card` census with the reviewer's complete 10-site census (the
  6 previously-known/found sites plus `cmds.py:1552` inside
  `CardPileCmd.auto_play_from_draw_pile`, itself reached from
  `cards/havoc.py:53`; `enchantments.py:401`; `potions.py:1050`;
  `powers.py:1355` `StampedePower`; `relics/whispering_earring.py:86`) plus
  the `HellraiserPower` class-widening (reachable class = "any card that
  draws mid-resolution," not just cards that call `auto_play_card`
  themselves). Reproduced the review's `MadScienceCard`
  mutually-exclusive-branches argument (re-verified independently by reading
  `mad_science.py:80-141` directly: `tinker_type` is fixed once per instance
  by `configure()`, and `on_play`'s ATTACK branch — the enemy debuff — and
  SKILL branch — the `wisdom` draw — are `if/elif` siblings that can never
  both fire) as the reason the verdict survives. Carried the corrected
  enumeration into BOTH the per-entry section and the record-close proposal
  text (item 4), since the controller applies the close-proposal text nearly
  verbatim. Also flagged the manifest's phantom `G5` (the record has no G5;
  only G2/G3/G4 are gaps) as a manifest-generator defect, not part of this
  hook's own reasoning.
- **Finding #4 → replaced with the corrected 10-site count**, and **added
  finding #5 filing R4-review.md's F1** (the sim's `_resolve_card_play`
  misses C#'s `Owner.Creature.IsDead` early-return before
  `Hook.AfterCardPlayed`, `CardModel.cs:1932,1940,1950,1960`) as a new
  `seam/hook_dispatch`/`seam/card_play` queue item — `combat.py` is outside
  this lane's footprint, so this is filed, not fixed.

### Test output after the fix pass

```
py -m pytest test/test_r13_relic1.py -v
  -> 14 passed in 0.79s

py -m pytest test/test_r13_relic1.py test/test_relics.py test/test_relic_live_tail.py \
  test/test_relic_residue_gaps.py test/test_relic_tier1_gaps.py test/test_tier1_last_five.py \
  test/test_hook_order.py test/test_power_type_for_amount.py test/test_power_modifier_phases.py \
  test/test_combat_over_hook_gate.py test/test_powers.py -q
  -> 516 passed
```

No regressions: the broader-suite count (516) is unchanged before and after
the fix pass — the three repaired tests replaced the three defective ones
1-for-1, and every other test file the report's original run covered is
still green.
