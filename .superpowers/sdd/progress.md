# Tier-2 dormant-gap campaign — progress ledger

Plan: docs/superpowers/plans/2026-07-30-tier2-dormant-gaps.md
Worktree: c:\Users\Perry\Desktop\sts2-rl-tier2 (branch tier2-gaps)
Protocol: NO COMMITS anywhere — controller runs `git add -A` after each
approved task; a task's diff = unstaged working-tree diff at review time.
Closer: <scratchpad>/closer.py (round-trip proven 848/0 on 2026-07-30).
Suite floor: 2 failed (933T floor_49 fixture) / 3347 passed / 6 xfailed.

PARALLEL MODE (Perry, 2026-07-30, during T7): implementers now run in
concurrent waves with disjoint code footprints; they no longer edit
audit/records/** or GAP-QUEUE.md (they propose close notes; controller
applies via closer.py at fold time), and the controller runs the full
suite + gates per wave instead of per task. Per-task diffs are
generated with `git diff -- <task files>`.

Task list is the plan's table (T0–T28). One line per completed task below.

## Completed

T0: complete (queue coverage reconcile — 5 unlisted power_cmd sites + 2 phantom-key mechanism anchors filed in §3G; coverage 478/0 + 626/0, cite-check 0, validate 848/0; review clean)

T1: complete (power_cmd/G5 PowerInstanceType — dispatch mirrors FindExistingInstanceForStacking; 11/13 entries closed, the_bomb+swipe left open w/ reasons; FranticEscape companion fix; suite 3359/2/6; review clean after 1 fix loop)

T2: complete (damage_pipeline/G4+step17.5 killing-blow pre-death-prevention snapshot + G6+step17.4 dealer-before-victim swap; all 4 entries faithful; suite 3363/2/6; review clean, no fix loop)

T3: complete (creature_card_cmds/N10+step104/105 auto-select shortcut + card_selection stream + rarity/id pre-sort; 3/3 faithful; NeowsFury min_select=0 + has_shortcut gate for FromChooseACardScreen purposes after review; Choices Paradox=FromSimpleGrid correction; suite 3380/2/6; 1 fix loop)

T4: complete (creature_card_cmds/step55 — STALE: transform already on combat_rng.card_selection + mid-play search premise false; closed w/ enumeration + 3 pinning tests; suite 3383/2/6; review confirmed staleness independently; record typo fixed by controller)

T5: complete (creature_card_cmds/G10+step93+step102b — step93/102b stale-closed; real fix: detached-list shuffle so modify_shuffle_order sees pre-shuffle pile membership per CardPileCmd.cs, 40-seedx2x2 pin; suite 3385/2/6; review clean)

T6: complete (guard batch — A dmg/G5 target-dead guard fixed (dealer-half stale); B cc/N4 duplicate-instance asserts on 3 add helpers; C cc/N5+step31 stale-closed on verified max(0,..) equivalence; D cc/N2 should_afflict+CanAfflict+AfterApplied w/ Ringing test correction; suite 3396/2/6; review clean)

T7: complete (creature_card_cmds/N3 — dead-owner/IsEnding drop ALREADY modelled (_refuses_combat_add); result object confirmed-unbuilt (external readers = VFX only); step70 re-classified out of the rollup; +1 pin test; review Needs-fixes -> controller narrowed the VFX overclaim in record+queue per reviewer wording; suite +1)

T12: complete (residue verify — G11/G16/G10 confirmed closed as recorded; step14 STALE, flipped faithful w/ 4 pins; step63 AfterFlush stays open+dormant; docstring false-claim fixed by controller; 11 new tests; review approved)
T23: complete (card/_unplayable_cost — 29 cards -> -1 + energy_cost short-circuit; readers/spend/obs audit verified by reviewer; selectors.py to_draw_top finding filed in Named-work; 15 new tests; review approved; controller applied 29 record closes + queue annotation)

T22: complete (monster_state_machine G8+G7+G2 — rebind guard, overload-1 sentinel, C#-exact fall-through loop (also kills the Flyconid all-zero hazard), unreachable_states machinery + Inklet premise correction; 14 new tests; review approved; controller applied 4 closes + 3 queue annotations)

T8: complete (cc/G8 residue: Add/Draw/reshuffle sites wired [step81/89/96 closed], step61 closed, step70+G8 narrowed, step69 routed to T20; aeonglass moved onto real on_card_generated_for_combat + Entropy-Wither bug fixed; HookSystem per-hook listener-presence cache -> hot loop 50-63% FASTER than pre-task baseline; census 46->47/41->42; 41 new tests; review approved; controller applied 5 closes + 2 narrows + 4 queue edits + probe-defect filing)

SWEEP 2 (wave-1 boundary, 2026-07-30): suite 2 failed (933T env floor) / 3469 passed / 6 xfailed; validate 848/0; rehash re-pinned 548; audit_status 0 stale; counts 559 entries / 461 mechanisms / 5 live; cite-check 0; coverage 0/0; power_census 0. All folded. Wave 2 dispatched: T9, T10, T24, T28 (T13 moved to wave 3 to avoid monsters/base.py + powers.py overlap with T28).

T9: complete (cc/G12+step34 gold hooks — STALE: fix + record closes predate campaign, only queue prose had drifted; verified line-by-line vs PlayerCmd.cs/DragonFruit.cs by implementer AND reviewer; +8 pin tests; queue annotated by controller; review approved)

T28: complete (monster families — Intent.none()+MoveType.NONE, status_count at 3 sites, retained-corpse scans on is_removed_from_combat, knowledge-demon applier fixed (source half narrowed to power_cmd ownership), Dampen caster set; 15 new tests; review approved; controller applied 9 closes + 2 narrows + 5 queue annotations + Vantom 4th-site filing)

T24: complete (card/_printed_vars 23/23 — base vars wired incl. 3 live computed overrides + feel_no_pain wrong-value fix; behavior byte-identical; obs values move for 20 cards (checkpoint note in record+queue); 48 new tests; review approved; controller applied 23 closes + queue annotation)

T10: complete (cc/G11+step49 PREMISE REVERSED — FlushPlayerHand fires no AfterCardDiscarded, sim flush dispatch removed; G9+step84 should_draw hoisted + after_preventing_draw added, flip-divergence pinned 5/1 vs 1/2; legacy test_end_turn_hook_sequence updated w/ citations; 11 new tests; review approved after 1 fix loop; controller applied 4 closes + 2 queue annotations + combat.py turn-end-discard filing)

SWEEP 3 (wave-2 boundary, 2026-07-31): suite 2 failed (933T env floor) / 3551 passed / 6 xfailed; validate 848/0; rehash re-pinned 518; audit_status 0 stale; counts 522 entries / 454 mechanisms / 5 live; cite-check 0; coverage 0/0; power_census 0. Pytest collection warning from T28's TestSubject import fixed by controller (SubjectMonster alias). All folded. Wave 3 dispatched: T13, T25, T27.

T25: complete (power/_stack_type_single 16/16 — 15 on_stack no-ops deleted; all 16 C# StackType+InstanceType pairs re-verified by reviewer; dampen's StackType is None not Single (queue list wrong), hex genuinely reads Amount (real divergence closed, still dormant), illusion correct as-is; 39 new tests; review approved; controller applied 16 closes + queue annotation)

T27: complete (card/_is_dead_early_return — blood_wall/brand/hemokinesis returns DELETED (downstream commands self-gate exactly as C# does; guard provably redundant); bloodletting/offering kept, dependency CORRECTED from _death_prevention_branch to EnergyCmd.gain's missing IsEnding bail (= relic/lantern/g1); breakthrough filed as uncounted 6th site; 11 new tests; review approved; controller applied 3 closes + 2 narrows + queue annotation)

T13: complete (turn_structure/step8 AmountOnTurnStart snapshot + both readers incl. HelloWorld's snapshot-as-COUNT; step32/step67 SpawnedThisTurn — DORMANCY OVERTURNED, spawn-during-AfterSideTurnStart is reachable and CRASHES without the guard; 11 new tests; review Needs-fixes on record TEXT only -> controller wrote the corrected step-31 attribution itself; 3 closes + 2 queue annotations)

SWEEP 4 (wave-3 boundary, 2026-07-31): suite 2 failed (933T env floor) / 3612 passed / 6 xfailed; counts 500 entries / 451 mechanisms / 5 live. All folded. T11 dispatched solo against this base.

NOTE (2026-07-31, T11 review): `hook_dispatch/step37`'s RECORD PREMISE IS FALSE. C#'s
`flag = flag || item.ShouldX(...)` DOES short-circuit (verified by language spec, a compiled
reproduction, and Hook.cs:1451-1452 where the devs hoisted a call onto its own line to avoid
exactly that skip), so the sim's `any(...)` was already faithful. T11's 'fix' inverted it and
is being reverted; the entry closes as faithful-on-false-premise, not as a gap fixed.

T11: complete (6 dispatchers/orderings + 1 false-premise removal — A before_block_gained, B before_card_auto_played, C after_modifying_hand_draw (w/ C#-shape dedup after review), D before_flush, E energy-hook reorder, G turn-end-discard dispatch REMOVED; **F REVERTED: hook_dispatch/step37's premise was FALSE — C# short-circuits, the sim was already faithful**; 12 new tests; suite 3624/2/6; review approved after 1 fix loop; controller applied 6 closes + 6 queue annotations + Named-work update)

T26: complete (step8c — record was STALE+self-contradictory, hook/wiring/gate-exclusion already shipped, only SurprisePower's override missing (added, provably dormant); _after_damage_given_substitution — hp_lost>0 dropped from on_damage_dealt + was_fully_blocked mirroring CreatureCmd.cs, both powers moved onto the dealer-side hook, Imbalanced's two non-C# guards deleted (inert: BowlbugRock never self-hits); 15 new tests; suite 3639/2/6; review approved; controller applied 4 closes + imbalanced guard-prose revision + 2 queue annotations. Implementer's git-stash slip into the index was verified harmless by the controller (no unmerged entries, no conflict markers, staged blobs compile, unstaged delta = exactly this task's files).

T17: complete (power_cmd/G1 — already fixed, only sibling step13 prose was stale; power_cmd/G2+step10 — **the sim's docstring had the C# BACKWARDS**: UnsettlingLamp.cs has no amount<=0 bail, the sim's own bail was the divergence; deleted + sign-aware condition; duration ticks proven structurally unreachable from the Lamp; 933T Mecha Knight green; 14 new tests; suite 3653/2/6; review approved; controller applied 2 closes + 2 queue annotations + 3 citation fixes (Resonance steals Strength not Dexterity; SharedFate.cs:39 is a third trigger card)

NOTE (2026-07-31, T19 review): do NOT close `creature_card_cmds` step 25 (`SetMaxHp`,
currently `deliberate-divergence` with an empty issue field) as fully faithful — the
MaxHp<=0 unconditional-kill short-circuit was missing and is being fixed; re-judge after.
Also flagged for a later round: step 19's closure claims `is_over` == C#'s `IsEnding`,
but the sim's `is_over` (phase == COMBAT_OVER) and `is_ending` are genuinely distinct.

T19: complete (creature/card HP+block verbs, all 5 mechanisms REAL fixes, none stale). heal fires on the RAW amount incl. at full HP; lose_max_hp now computes unfloored -> full damage pipeline -> floors last, so a 10/10 losing 30 max HP DIES; new BlockCmd.lose_block (BurrowedPower migrated, Hand Drill now sees AfterBlockBroken); new CreatureCmd.set_current_hp; new set_max_and_current_hp (Decimillipede x2 + ToughEgg migrated). Reviewer caught a real omission -- set_max_hp's MaxHp<=0 kill must SHORT-CIRCUIT ShouldDie (CreatureCmd.cs:844-846 is `force || MaxHp<=0 || ShouldDie`); the fix agent landed the code but was cut off before the pin, so the CONTROLLER wrote TestMaxHpZeroKillBypassesShouldDie (a vetoing listener is never consulted and never spends its charge; an ordinary lethal hit still consults it). Record defect found: step23's cited ToricToughnessPower.block site is a FALSE POSITIVE (the power's own stored value, not a creature's). Suite 3680/2/6. Controller applied 9+5=14 closes (incl. step25, whose whole `deliberate-divergence` rationale was "there is no standalone set_max_hp verb" -- there now is) + 5 queue annotations. Queue 488->475 entries, 441->435 mechanisms.

SWEEP 5 (2026-07-31, post-T19): validate 848/0 invalid; cite-check 343 citations / 125 files / 0 problems; suite 2 failed (933T env) / 3680 passed / 6 xfailed.

T30: complete (card-GENERATION pool family, wave 5 lane B). Mechanism A -- cards/pool.py's FilterForCombat port was missing its Event-rarity clause; the record's 'three rarities' claim was verified CORRECT against CardFactory.cs:159-162 and the real bug source was pool.py's OWN docstring claiming two. Dormancy-preserving (both pools re-enumerated unchanged). Mechanism B -- 6 cards had TWO mismatched flags each (is_playable=False and can_be_generated_by_modifiers=False both wrong, can_be_generated_in_combat=False missing). **A DORMANCY VERDICT WAS OVERTURNED**: the recorded dormancy checked only pool_card_ids and curse_pool_ids, but transform_options_in_combat's STATUS branch (ported Entropy) is a third consumer that genuinely leaked all four bad cards pre-fix, incl. frantic_escape which The Insatiable really puts in piles -- reproduced by execution by BOTH the implementer and the reviewer (who monkeypatched the old flags rather than mutating source). Reviewer approved both verdicts. 36 new tests. Controller applied 20 closes + 1 bonus (relic/crossbow/g3, same root, found by the controller) + 2 queue annotations.

T31: complete (rewards dispatch + relic stubs, wave 5 lane C). Mostly a VERIFICATION task: 2 of 3 mechanism-A entries and 1 of 4 B entries were already fixed by pre-existing STAGED work (confirmed real via `git show HEAD:sts2_rl/run.py`, not asserted). royal_stamp premise-corrected from 'stub' to fully implemented + already pinned. bing_bong / massive_scroll / punch_dagger deliberately LEFT OPEN as genuine-but-dormant rather than closed. **SPUN OFF A NEW LIVE GAP, found by unit work and confirmed by the reviewer**: events/brain_leech.py + events/trial.py hand CombatRewards to driver.py._run_event's pending_rewards channel with no apply_reward_modifiers dispatch, so Driftwood's reroll is unavailable there though both events and Driftwood are ported -- dispatched as T32. Reviewer approved both verdicts. Controller applied 4 closes + 2 queue annotations.

NOTE (2026-07-31): T31's implementer used a 'temporarily revert the fix, see RED, restore' technique while another agent was live in the same worktree. Controller verified the tree (footprint exactly as declared, no conflict markers, reverts restored). All later dispatches now forbid it explicitly -- get RED by writing the test BEFORE the fix.

SWEEP 6 (2026-07-31, post-T30/T31): validate 848/0 invalid; cite-check 348 citations / 127 files / 0 problems. Queue 475->451 entries, 435->423 mechanisms.

T20: complete (exhaust/escape/RemoveFromCombat/EnergyCmd, wave 5 lane A). Four items, all real. A: exhaust now scans EVERY pile incl. exhaust. B: escape strips powers silently via Power._expire (no on_removed), mirroring RemoveAllPowersInternalExcept's deliberate contrast with death; on_creature_escaped KEPT after the reviewer traced the whole C# chain and found zero Hook.AfterX; a compensating SwipePower.hand_off_stolen_origins was needed because run.py's finish_combat reconciliation is sim-only architecture (C# steals from the deck immediately, SwipePower.cs:75). C: step69 wired = the 4th of G8's four dispatch sites. D: EnergyCmd.gain got its is_ending bail (PlayerCmd.cs:29-43), unblocking bloodletting+offering. **REVIEWER CAUGHT A REAL NEW DIVERGENCE THE FIX INTRODUCED**: item A's first pass raised ValueError on a re-exhaust, reasoning from CardPile.AddInternal's throw -- but CardPileCmd.Add removes (:494-496) BEFORE it adds (:510), so with oldPile==targetPile==Exhaust the contains-guard tests an emptied slot and never fires; re-exhausting is a legal no-throw reposition. THE CONTROLLER'S OWN BRIEF had suggested the raising behavior -- the C# overruled it. Controller fixed it directly (scan includes exhaust_pile, assert dropped) and rewrote the pin to assert the reposition-to-bottom. Controller applied 7 closes + 2 NARROWINGS (G8 keeps one unwired site, the manual play, pending N9/T21; relic/lantern g1 keeps its AfterModifyingEnergyGain clause) + 4 queue annotations.

SWEEP 7 (2026-07-31, post-T20): validate 848/0 invalid; cite-check 358 citations / 128 files / 0 problems. Queue 451->444 entries, 423->419 mechanisms. NOTE: full suite not yet re-run post-T20-fix -- T32 was mid-flight in driver.py/events. Run it before the round banner.

T32: complete (mid-event reward-modifier dispatch -- a LIVE gap this round FOUND rather than inherited, spun off by T31 and confirmed by its reviewer). Enumerated all 11 sim reward-offer sites: 2 missing the dispatch and FIXED (brain_leech._rip, trial._nondescript_guilty -- Driftwood's reroll now reaches both), 8 immune, 1 MORE live gap found and deliberately left open (events/base.py::Event.offer_card_reward via the_future_of_potions -- a take-or-skip protocol with no reroll surface, so it needs new capability, not a call). Fix is PER-SITE, not central: _offer_rewards's 3 other callers already dispatch at construction time, so a central call would double-dispatch and duplicate gold/relics (reviewer verified). That leaves the sim structurally unlike C#'s single choke point -- recorded as the real follow-up. Reviewer approved both verdicts but caught a FACTUAL ERROR baked into a permanent test comment: 'Driftwood is the only room-ungated hook of 8' is FALSE -- Midas.TryModifyRewardsLate (Midas.cs:12-29) takes a room param and never reads it. Controller verified against the C# and corrected the comment (Midas is irrelevant there for a different reason: those screens carry no GoldReward), plus two Minor prose fixes (Trial.cs:185 is ONE OfferCustom with a 2-item list, not two calls; BrainLeech batches RewardCount groups where C# loops -- dormant at RewardCount=1). Controller added 2 new FAITHFUL record entries (found+fixed) and 1 new LIVE GAP entry (event/the_future_of_potions/g15) + 1 queue annotation.

NEW OPEN WORK found this round, not yet owned:
- event/the_future_of_potions/g15 -- Event.offer_card_reward has no reroll surface (LIVE).
- run.reward_offer_selector is NEVER wired by driver.py (set only in test files) so take-or-skip screens AUTO-ACCEPT in real play. Pre-existing, LARGER than the reroll flag, needs its own task.
- Consolidating the sim's several construction-time reward dispatches onto one choke point (C# has exactly one: RewardsSet.GenerateWithoutOffering).

SWEEP 8 (2026-07-31, post-T32): validate 848/0 invalid; cite-check 362 citations / 129 files / 0 problems. Queue 444->445 entries (UP one: a new live gap recorded), 419->420 mechanisms. Full suite last seen 2 failed (933T env) / 3738 passed / 6 xfailed, which included the controller's exhaust correction.

T18: complete after a FIX PASS (power_cmd/G3 + G4 -> damage_pipeline/G2 -- the campaign's headline task). C#'s three ordered phases are now three real dispatches: given-additive then given-multiplicative (Hook.cs:1888-1912's sum-THEN-product, which a naive fold gets wrong) under a real applier/ContainsCreature gate, then the received chain unconditionally; both AfterModifyingPowerAmount* companion events exist with a modifiers out-list carrying only listeners that actually changed the value; Artifact and RuinedHelmet are REAL LISTENERS instead of hand-inlined. RESULT: **zero live entries across all six seam records** -- the engine tier has no live gap. damage_pipeline/G2 dropped live->dormant but stays an OPEN gap (7 of its 9 variants still uncovered). **THE REVIEWER CAUGHT A REAL DEFECT IN THE HEADLINE MECHANISM**: pass 1 fired both companions BEFORE the power was registered/stacked, where C# runs ApplyInternal (PowerCmd.cs:135) and SetAmount (:237) FIRST (:148-152, :238-242). The CONTROLLER found a third facet nobody had flagged: C#'s Apply wraps its ENTIRE tail incl. both companions inside `if (target.CanReceivePowers)` (:133-158), so a target failing that re-test must get NEITHER companion -- the sim fired them before its re-test. The controller also CLEARED one thing the reviewer had passed over: the sim's empty-list skip is equivalent to C#'s unconditional call, because both companion hooks iterate listeners and filter on modifiers.Contains(modifier) (Hook.cs:796-824). Fix pass handled all three plus the load-bearing trap: ApplyInternal's `if (!(amount == 0m))` is INTERNAL to it, so an Artifact-zeroed debuff attaches nothing but STILL fires both companions -- which is how Artifact spends its charge on a debuff it blocks. NOTE: full-suite green proved nothing here; both defects were invisible to current content and only visible against the C#. PERF: end_turn got 14.76% FASTER -- profiling found combat_is_over ran a live `import` STATEMENT per call (pre-existing, circular-import workaround), now cached in _PHASE_CLS. PowerCmd.apply itself is 28-42% slower (three _each() calls where there was one); reviewer notes 147 files call it, so watch it. Controller applied 6 closes + damage_pipeline/G2 live->dormant + 4 re-scopes/citation fixes (step21/step31 machinery-now-exists; N4/step4 cited step6 as dormant when it is now closed) + 3 queue annotations.

SWEEP 9 (2026-07-31, post-T18): validate 848/0 invalid; cite-check 367 citations / 129 files / 0 problems. Queue 445->439 entries, 420->416 mechanisms. LIVE: 6->5 mechanisms, ALL content-tier (power/skittish/AfterAttack; event/crystal_sphere x2 and event/war_historian_repy/g2, all deferred whole-event port stubs; event/the_future_of_potions/g15, NEW this round). SEAM LIVE ENTRIES: 0.

## Minor findings carried to final review

- T0: the two new §3G coverage-anchor rows are wordier than the table's terse norm (GAP-QUEUE.md ~2092, ~2099)
- T1: orphan-instance surfaces (PowerCmd.remove, _strip_powers_after_death) documented-unreachable, left for future work; full_env.py sees newest-instance amount for stacked Instanced powers (was a wrong sum)
- T3: card.id vs ModelId.Entry tie-break fidelity not exhaustively cross-checked (reviewer ⚠); shortcut path draw-pile ordering pinned by test
- T5: held-card branch keeps mid-play card physically in discard (N9 territory, disclosed); bottled-potential test doesn't race draw-vs-discard Perfect Fit copies
- T6: N4 closure text omits shuffle-re-add/transform pile-mutation sites from the old enumeration (different failure shape, unguarded); afflict's combatState==null non-mirror lives only in closure prose, no gap id
- T7: caller-enumeration phrasing slightly overstates per-file inspection (reviewer-verified no counter-example); step73 + HasBeenRemovedFromState + detached-card deferred with reasons
- T12: step71's N2 waiver may under-scope Player.AfterCombatEnd teardown (pre-existing, future round)
- T23: CardEnergyCost.cs true short-circuit lines are 101-104 (records carry 100-103 drift); selectors.py clamp is a 1-line follow-up
- T22: state_machine_probes.py zero_weight probe greps the OLD message text (stale, out of footprint); T22 reviewer transiently mutated state_machine.py mid-review (restored, verified byte-identical, disclosed)
- T8: step69 (thieving_hopper RemoveFromCombat dispatch) assigned to T20; manual-play site waits on N9 (T21); monster_probes_b06 grep blind spot filed in outstanding defects
- T9: hook_dispatch/N5 queue entry (~line 1348) carries a stale G12 cross-reference — T16's implementer to fix with N5
- T28: mechanism-D TDD covers Disintegration/MindRot only (shared code path with Sloth/WasteAway); Vantom status_count=3 one-liner pending an owner
- T24: Normality's live magic_number override does a linear history scan on the obs hot path (pre-existing cost pattern, flag if Normality-heavy decks train slow); report cited base.py:65-69 for text actually at :143-146
- T10: fiddle.py inline comment misidentifies which C# bail is missing (player!=owner, not the Side check) — hygiene, inert in single-player sim
- T25: hex's dormancy is content-dependent (a 2nd Hex applier makes it live); census no-op heuristic mirrors the audit tool's own fragile 'ends with pass' proxy
- T27: two more same-idiom sites (conflagration.py, tear_asunder.py) are the correct multi-hit loop-break idiom, not this mechanism; hemokinesis's 2026-07-26 record misquotes which AttackCommand line it cited
- T13: step31's own 'faithful' rationale is overbroad (true only for spawns after ExecuteEnemyTurn's ToList) — noted in its sibling closes, verdict stands; amount_on_turn_start uses getattr not a Power.__init__ field (normalize when powers.py is free)
- T11: after_modifying_hand_draw's dispatcher doesn't re-check _live (unreachable at its sole call site; matches after_preventing_draw's shape); before_flush note cites CombatManager where the NetId gate is in Hook.cs:534-538
- T17: cmds.py's PowerCmd.modify_amount docstring now misdescribes its own blocker (fix when next touched); G4 + damage_pipeline/G2's variants remain blocked on dispatch architecture (modify_power_amount has no modifiers out-list; Artifact hard-coded outside the listener system = power_cmd/G3)
