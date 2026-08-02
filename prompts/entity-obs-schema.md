# Entity observation schema — env-side integer obs, set-encoded powers, tied action head

You are the **controller** of a subagent-driven project on `sts2-rl`, a Slay
the Spire 2 combat simulator with a PPO training stack. This is the
long-deferred **strategy (b)** of the retired embedding-model prompt, named in
`prompts/parallel-envs.md` as *"the real fix for obs size … a separate,
schema-bumping project."*

**The user has explicitly accepted restructuring the RL environment and
training from scratch.** Checkpoint weight-compatibility is NOT a constraint on
this project. That is the whole reason it is finally tractable — do not
reintroduce the constraint by trying to migrate weights.

Read first, in this order:
1. `prompts/obs-vectorization.md` and `prompts/parallel-envs.md` — the two
   prior passes over this surface, and where each stopped.
2. `sts2_rl/models.py` module docstring — what strategy (a) built and why the
   env/PPO loop stayed untouched.
3. `sts2_rl/checkpoints.py` — arch stamping, `obs_schema_version`, and the
   v3→v4 migration (read it for the parameter-ORDER trap it documents, not to
   copy it — you are not migrating weights).
4. `CLAUDE.md` — especially §4. **Never `git commit` or `git push` unless the
   user explicitly asks. Stage only.**

## Ground truth

- Use the `py` launcher; there is no `python` on PATH.
- Never trust a count stated in prose, including in this file. Re-measure.
- Measured 2026-08-01, combat env (`py -c` over `full_env.obs_segments()`):
  **17,873 floats total**, of which hand card one-hots 6,400 (35.8%), powers
  6,048 (33.8%), pile histograms 3,840 (21.6%), enemy identity one-hots 864
  (4.8%). **~4% of the observation is genuinely numeric; ~96% is sparse
  categorical.** The run env is larger (~29k per `parallel-envs.md`).
- Vocab capacities: `N_CARDS 640`, `N_POWERS 288`, `MAX_HAND 10`,
  `MAX_ENEMIES 6`. Current schema versions: combat **3**, run **6**.
- Baseline suite (2026-08-01, after round 14): **4091 passed / 6 xfailed / 0
  failed** with `--ignore=test/test_conformance_floor_state.py`. That file's 2
  failures are a missing `933T39V18D/floor_49` fixture — an environment gap.
  **Never "fix" them, never count them as regressions.**

## Why this project exists (do not lose the thread)

Three separate problems share one root cause — the observation encodes
categoricals as wide one-hot float blocks:

1. **Throughput.** Obs are ~117 KB/env/step. The trainer is inference-bound
   (act-time inference 46% / PPO 39% / envs 15%), and subprocess env workers
   bought only ~4% because transport dominates.
2. **Expressiveness.** `creature.powers` is a dict keyed by power id and the
   encoder writes one 3-float triple per id, so a creature cannot hold two
   instances of one power. This is a **live, filed fidelity gap**:
   `power_cmd/G5` / `power/the_bomb/InstanceType` in `audit/GAP-QUEUE.md`. C#
   dispatches on `PowerInstanceType` (`PowerCmd.cs:165-174`); 21 C# powers
   declare an override, 11 ported.
3. **Generalization.** Actions are positional (`MAX_HAND × MAX_ENEMIES`), so
   the policy learns per-slot rather than per-card over a 640-card vocabulary.

A design that fixes only one of these is the wrong design.

## Phase 0 — do this first, and ship it independently

**Make `creature.powers` hold instances** (a list, or a dict of id → list),
so a creature can carry N powers sharing an id, matching C#'s `Instanced` /
`InstancedPerApplier` dispatch.

This is required under every later phase, and its value does **not** depend on
the RL work: the replay/conformance exporter reads sim *state*, never the
observation. So this alone closes real fidelity debt and improves seed
convergence.

- Keep the existing encoder collapsing instances to today's lossy triple. The
  observation stays byte-identical; the schema does not bump; checkpoints keep
  working. Verify that byte-identity with a test.
- `cmds.py:308`'s `if power_cls.id in target.powers` and every reader of
  `creature.powers[id]` is in the blast radius. Enumerate them before editing.
- `TheBombPower` (`powers.py:~4691`) keeps an internal `bombs` fuse list as a
  workaround, and its docstring explains that switching to `INSTANCED`
  dispatch naively **silences `on_stack` and loses correct damage tracking**.
  Read that docstring before touching it; the workaround must be retired *as
  part of* the state fix, not before it.
- Then fold the record + queue closes for `power_cmd/G5` /
  `power/the_bomb/InstanceType` — or narrow them explicitly if observation
  residue remains (it will, until phase 2). **Close conservatively.**

Stop here and let the user review before starting phase 1. Phase 0 is
shippable on its own.

> The riders below (phase 1 rider, phase 2 rider, phase 3, evaluation) were
> added 2026-08-01 from a full review of the env stack (`full_env.py`,
> `run_env.py`, `curriculum_env.py`, `driver.py`, `models.py`,
> `train_torch.py`, RL.md, RL_ARCHITECTURE.md). The organizing principle:
> **the from-scratch retrain is paid exactly once.** Any observation or
> action change that would force another schema bump later is cheapest
> shipped inside this one; anything with no schema impact is explicitly
> deferred to phase 3 so the riders cannot balloon phases 1–2.
>
> Added constraint (2026-08-01, from the user; tightened same day):
> **live-bot gameplay through an STS2 mod is planned**, and the observation
> space is bounded by the INTERSECTION of what the player and a mod can
> see. A field is admissible only if BOTH hold:
>
> 1. **Player-visible.** Either displayed in the game UI right now (HP,
>    intents, relic-icon counters, prices, hand contents), or an exact
>    function of things that were displayed earlier in the run and merely
>    remembered (watched history — e.g. intents already shown). Information
>    the UI never surfaces is banned outright, even though a mod can read
>    it from the game's model layer: draw-pile order, un-telegraphed
>    move rolls, internal-only counters (reward pity), RNG state. This is a
>    fairness rule, not a feasibility one — "the mod could read it" is
>    never an argument for inclusion.
> 2. **Mod-suppliable at any time.** Readable off displayed/model state at
>    the moment the observation is built, or maintainable by the runner
>    accumulating rows it already built on earlier turns. A field the
>    deployment runner cannot supply is a distribution shift trained in on
>    purpose — the policy meets out-of-distribution zeros exactly when
>    deployed. Watched-history fields (R3, R7) are admissible under rule 1
>    but carry this deployment risk; each needs an explicit story for how
>    the mod maintains its accumulator, and gets cut if it has none.
>
> The sim engine can compute more than rule 1 allows, so every NEW field
> added in phase 1 extends the hidden-information non-leak test, not just
> the draw pile. This rule demoted R3's original move-id design, cut R7's
> pity item, and contributed to cutting R5; apply it during the R1 census
> too (a relic counter the icon doesn't display stays out).

## Phase 1 — the integer observation schema

Replace the sparse one-hot blocks with **env-side integers plus a mask**:

- **Powers**: per creature, a padded list of `(power_id, amount, aux…)` with a
  presence mask. This is where multi-instance falls out for free — the list
  simply holds `the_bomb` twice. Carry **per-instance aux fields**: The Bomb's
  real state is `(turns_left, damage)` per fuse, which no vocabulary scheme
  can express. Choose `MAX_POWERS_PER_CREATURE` from a measured census of the
  worst case across ported content, not a guess, and **log overflow loudly**
  rather than silently truncating.
- **Hand**: card ids as integers + the existing per-card scalars.
- **Enemies**: identity as an integer per row.
- **Piles**: ⚠️ **do not leak hidden information.** The draw pile is a
  histogram today, which correctly hides draw *order* — the player cannot see
  it either. An integer list would preserve order for free and hand the agent
  information the real game never gives it. Keep piles as sorted multisets or
  counts, and write a test that pins the non-leak.
- The genuinely numeric ~4% stays as floats.

Mechanics:
- The observation space stops being a flat float `Box`. Decide and document
  the new contract (a `Dict` space, or a float array plus a parallel int
  array). This breaks the property `models.py` calls out — that envs and the
  PPO loop are untouched by arch changes. That break is the point of this
  project, but it must be deliberate and documented, not incidental.
- Bump `OBS_SCHEMA_VERSION` (combat 3 → 4) and `RUN_OBS_SCHEMA_VERSION`
  (6 → 7). **Do not write a weight migration.** Make `checkpoints.py` fail
  loudly with a message telling the user to start `--fresh`.
- Add the new arch as a third `--arch` value rather than mutating `entity`, so
  an arch-stamped checkpoint from the old path is refused on a name it no
  longer matches instead of failing on a shape mismatch deep inside loading.

## Phase 1 rider — observation gaps to close in the SAME schema bump

Each item is independent; they are ordered by value. If one drags, cut it and
say so — but cutting one means its schema bump is paid again later, so record
the decision in the report.

**R1 — a relic block, with per-relic mutable state.** The combat observation
has NO relic segment at all (`full_env.obs_segments()` — verified 2026-08-01),
and the run observation is presence-only (`run.relics` multi-hot). Relic
internal counters are invisible everywhere: `relics/pen_nib.py:28` keeps
`_attacks_played` as a private attribute — state the game surfaces on the
relic icon — and the agent cannot see 9-of-10 attacks vs 0-of-10. Integer
schema: a padded list of `(relic_id, counter, flag)` rows shared by the
combat and run blocks. **Census the `relics/` package first** for which
relics carry mutable state and what shape it is (counters, booleans,
per-combat vs per-run) — size the aux fields from the census, not a guess,
and log overflow loudly. The census must also apply the admissibility rule:
for each stateful relic, check the game source for whether that state is
surfaced on the relic icon (RelicModel's counter/display path) — a counter
the UI never shows stays OUT of the observation even though the sim tracks
it. This item is also a prerequisite for R11 (phase 3):
a combat env that can't see relics can't train on realistic mid-run states.

**R2 — card-instance aux fields everywhere a card appears.**
`card_features` (`full_env.py:456`) folds afflictions into `is_playable` and
effective cost only — the agent cannot tell Ringing from Smog from Tainted,
and enchantments (Sown, Sharp, Nimble, …) are entirely invisible. Pile
histograms collapse every copy to `(id, upgraded>0)`, so an enchanted Strike
and a plain one are the same observation. Integer schema: the per-card row
is `(card_id, upgrade, effective_cost, affliction ids, enchantment id,
flags)`, used identically for hand slots, pile multisets, and select
candidates. Afflictions and enchantments need small new frozen vocabularies
in `vocab.py` (reserved capacity, append-only, same rules as the others).
Piles stay order-hidden: sort instance rows canonically (id, then aux)
before writing, and extend the phase-1 non-leak test to pin that.

**R3 — per-enemy intent history** (redesigned 2026-08-01 for the live-bot
constraint). Monster move state machines are hidden state the real player
infers by *watching the moves happen*; the observation shows only the
current intent, so the sim is partially observable where the game
practically is not (a Byrdonis two moves into a cooldown looks identical to
a fresh one). The original design — last-K *move identities* over a
sim-side move vocabulary — fails the live-bot constraint: the mod would
need a game-move → sim-vocabulary mapping plus never-miss instrumentation
of move resolution. Redesign: a per-enemy ring buffer of the last K
**intent rows the observation already contains** (the intent-type flags +
previewed damage of `enemy{e}.intent_flags` / `intent_preview`), i.e. a
pure function of the past display stream. Any runner — the sim env or the
mod — maintains it by remembering rows it already built on earlier turns;
zero extra game introspection. Define the sampling point once ("the intent
displayed when the enemy acted") and apply it identically sim-side and
mod-side; track per-creature identity so the history survives slot shifts
from deaths/summons; choose K from a census of the longest
cooldown/`CAN_REPEAT_X_TIMES` window across `monsters/` (the state machines
key off `state_log`, so the census is mechanical). This is less precise
than move ids — distinct moves can share an intent face — but it is
exactly the information a human player has. **If the live-bot runner ends
up unable to supply even this, cut R3 entirely**: a partially-observed
deployment must be matched by partially-observed training; never train
with a history field the runner will zero. Alternative considered and
rejected as the first move: a recurrent policy (LSTM) — it touches the PPO
loop and rollout buffers, costs throughput, and has the same
deployment-parity problem in worse form (hidden state accumulated over a
whole episode).

**R4 — select candidates as instance rows + true candidate actions.** The
run env's SELECT block answers with a `(card id, upgraded)` pair over
`2·N_CARDS` actions and gives the driver the FIRST matching candidate
(`run_env.py:_translate`) — copies differing by enchantment or cost
modifier are collapsed, a documented approximation that R2's aux fields
turn into an outright wrong answer (the agent could see two different
candidates but not address them). Replace with padded per-candidate rows
(the R2 instance-row type) plus a candidate-index action block. **Measure
the worst-case candidate count before sizing** — `from_discard` /
`from_draw` purposes can offer a whole pile — and log overflow rather than
silently truncating. This block is also where the phase-2 pointer head
plugs in naturally.

**R5 — character id + ascension: CUT (2026-08-01, on review).** The
original argument — pay the schema bump now because a second character
forces it later — double-counts. A character port lands a card pool's
worth of unseen content at once; PPO is on-policy, and a fine-tune across
untrained embedding rows, new mechanics, and a stale critic is close to
scratch in practice — so the bump is equally free *at that moment*. Until
then both fields are constants, i.e. dead inputs. Recorded per this file's
own rule: add character id with the first multi-character training run and
ascension with the first mixed-ascension one; both arrive bundled with
their own retrain.

**R6 — log-compress unbounded scalars instead of clip-saturating.**
`run.gold` saturates at 1000 (`run_env.py:604` writes `gold/100` and
`gold/1000` clipped); shop costs clip at `_COST_SCALE = 500` while the
removal price climbs `75 + 25k` unboundedly (`run_env.py:207`) — a late-run
800g removal is observationally identical to a 500g one, and a 1500g
treasury to a 1000g one. For genuinely unbounded quantities (gold, prices),
switch to `log1p`-scaled encodings; keep the shared dual absolute scale for
HP-like quantities (bounded in practice). Pin the new encodings with tests.

**R7 — (optional, watched-history) player-memory statistics.** Narrowed
2026-08-01 by the admissibility rule. **Pity is CUT**: the card-reward pity
counter lives on `RunState` but the UI never displays it — it is hidden
information under rule 1, regardless of being approximately inferable.
What remains are true watched-history items — exact functions of things
the game displayed earlier: (a) "events already seen this run" (the player
sat through those screens); (b) known draw-pile placements — after
Headbutt's `to_draw_top` the player KNOWS the top card, and the histogram
hides it. Both are admissible but tier-2 (deployment rule 2): each needs a
mod-side accumulator story before being built, (b) additionally needs
engine-side knowledge tracking that resets on shuffle. **Defer both
without guilt if they drag on phase 1** — they are the lowest-value rider
items and exist mainly so the partial-observability trade-off is recorded,
not silent.

## Phase 2 — the encoder and the tied action head

- **Encoder**: `nn.Embedding` per vocabulary kind (rows = frozen vocab
  *capacity*, as today, so porting content appends rows), then masked pooling
  over each entity set. **Start with masked sum/mean plus per-field
  projections** — the current `einsum` is already the right set operation, and
  you are inference-bound. Consider attention only over the enemy set, where
  relational reasoning actually pays, and only with a measured win.
- **Tied action head**: score `(card_entity, target_entity)` pairs against the
  same card/monster embedding tables the observation uses, instead of the
  positional `MAX_HAND × MAX_ENEMIES` index space. This is the "select-head
  tying" deferred alongside strategy (b). Keep the masked-categorical contract
  (`get_value` / `get_action_and_value`) so the PPO loop is unchanged.
- Preserve the illegal-action masking semantics exactly (`_MASK_FILL`, and the
  guarantee of at least one legal action per row).

## Phase 2 rider — head and encoder extensions

**R8 — extend the pointer head to every run-env decision.** The tied
`(card, target)` head is one instance of a general mechanism: score an
option by the embedding of its *content*, not its slot index. The run env's
generic CHOICE slots are positional — the policy currently learns "option 2
of event X" through the event-identity embedding, and a shop entry's
identity reaches the head only through the flat obs. Score reward cards by
their card embedding, shop entries by item embedding + price feature,
select candidates by their R4 instance row, map nodes by their node
features. One shared scoring module, per decision-kind projections where
needed. Keep the flat `Discrete` + mask contract so the PPO loop is
untouched — the head computes logits for the same action indices, it just
computes them from content instead of position.

**R9 — pair features in the tied head.** The damage matrix is aligned 1:1
with the play actions and the post-block incoming previews exist per enemy
— feed them into the `(card, enemy)` pair score directly instead of only
through the flat trunk. The head that picks the action should see the
number that decides it.

**R10 — measure a shared encoder.** Actor and critic currently duplicate
the entire `_SegmentEncoder` (`models.py:263-264`, mirroring the
separate-trunk baseline). After phase 2 the encoder is most of the compute.
Try one shared encoder (or shared embedding tables with separate trunks) as
a measured A/B: keep it only with a throughput win and no
stability/sample-efficiency regression. Separate trunks stay regardless —
only the encoder/tables are candidates for sharing. (Both arms live in the
new stack, one variable apart — a controlled within-project comparison, the
only kind this project runs. It is not an old-env delta; see Measurement.)

## Phase 3 — training and curriculum (no schema impact; after phase 2)

Nothing here bumps a schema — sequence it after the restructure lands, as
separate shippable pieces.

**R11 — mid-run start-state distribution for the combat env.** Every combat
episode today starts from the fixed 13-card default deck, zero relics, and
the Act-1 non-boss pool (`DEFAULT_DECK_IDS` / `DEFAULT_ENCOUNTERS`,
`full_env.py:274`) — the combat policy never trains on the decks, relics,
HP levels, or Act-2/3 encounters it actually pilots inside a run. Harvest
`(deck, relics, hp/max_hp, potions, act, encounter)` snapshots from run-env
episodes into a dataset; `reset()` samples from it. Requires R1 (a combat
env that can't see relics can't use them). This is the highest-leverage
sample-efficiency idea in this file: it turns the cheap env (combat) into
training on the hard env's (run) state distribution.

**R12 — subprocess env workers, now that the payload shrank.**
`prompts/parallel-envs.md` stalled because transport dominated: obs were
~117 KB/env/step and workers bought ~4%. The integer schema cuts the
payload by roughly the measured sparse fraction (~96%). Re-measure the
serial trainer first (that prompt's own instruction), then re-run its
design. Do not start this before phases 1–2 land — parallelizing the old
payload is parallelizing waste.

**R13 — (optional, measured) auxiliary prediction heads.** Critic-side
auxiliary losses — predict next-turn post-block incoming damage, or
terminal win probability — are cheap to add and sometimes buy sample
efficiency in sparse-ish reward settings. Keep only with a measured win on
identical seeds; delete on a null result and record the number.

Existing knobs, for the record, so nobody re-invents them: column→run map
annealing already exists as `--branch-prob` (per-episode regime mix,
`curriculum_env.ColumnRunState`); an in-run schedule for it is a small
trainer change if manual staging across resumes proves clumsy. HP shaping
stays off by design — the curriculum docstring's argument (the critic
learns "low HP → fewer future floors" from the observation) held up under
review; do not reintroduce hand-coded HP reward terms without an A/B.

## Evaluation rider — run-scale probes and paired seeds

`probes.py` covers lethal arithmetic in combat; nothing analogous exists at
run scale, and run-scale win rates near zero can't rank checkpoints (floors
can, but coarsely). Two additions, buildable any time:

- **Run-scale micro-probes**: fixed scenarios with one clearly-right
  decision — take the rest at low HP vs fight the elite, buy the removal
  vs hoard gold at a known shop, pick the on-curve card vs a trap reward.
  Same pattern as `evaluate_probes`: paired scenarios, score = fraction
  where the policy picks the dominant option.
- **Paired-seed A/B**: `evaluate_run` is already deterministic per `--seed`
  — formalize a fixed evaluation seed set (a few hundred), always compare
  two checkpoints on the same set, and report per-seed deltas, not just
  aggregate means. Two arms on different seeds is how a real regression
  hides inside run-to-run variance.

## Entry gate — the run-env hang, before any destructive edit

`env.step()` on the run env has been observed hanging **indefinitely**
(>45 min, undiagnosed, killed two census configs). This is a blocker for the
whole project, not just for unattended runs: it can hang `evaluate_run`, it
can hang R11's snapshot harvesting, and it makes every training-derived
measurement unreliable.

`max_steps` structurally cannot catch it: `_steps` increments once per
`step()` call (`run_env.py`), so the budget bounds the number of
**decisions**, never the engine work *between* two decisions. Anything
looping inside a single `_switch()` is unbounded by construction. Nor can
anything in-process stop it — during the hang the env greenlet is not
running, so `_kill_driver`'s `glet.throw(GreenletExit)` (which only lands on
a *parked* greenlet) is inert.

- Diagnose with an external stack dump (`py-spy dump --pid`, or a
  `faulthandler.dump_traceback_later` watchdog thread — both show the
  spinning greenlet's frames). Log `(seed, episode index, decision count)`
  before each step so it becomes reproducible; the run env is deterministic
  per seed, and once replayable it is an ordinary bug.
- Priors on the culprit, in order: a monster state machine that cannot reach
  a `MoveState` (a `RandomBranchState` whose options are all excluded by
  cooldown/repeat rules; a `ConditionalBranchState` with no true condition),
  a draw/reshuffle loop, a replay/auto-play recursion.
- **Fix it; do not paper over it with a timeout-and-truncate.** If the real
  game cannot reproduce the loop it is a fidelity bug and belongs in the
  audit queue. Truncating would also bias training twice: the hanging states
  vanish from the distribution, and the truncation bootstrap folds
  `gamma * V(hang_obs)` — a garbage value — into GAE.

## Measurement — validate against ground truth, never against the old env

**Decision (2026-08-01, from the user): there is no old-vs-new comparison in
this project, in any form.** Earlier drafts asked for a pre-teardown
checkpoint score, a trainer-sps baseline, and before/after deltas. All of it
is struck. Two independent reasons, and the second is the load-bearing one:

- The user is retraining from scratch regardless, so the old checkpoint's
  score is not a target and the one sps figure taken so far (measured under
  CPU contention) is not worth re-taking.
- **The two environments are not comparable.** The phase-1 riders change the
  action layout (R4's candidate-index block), the observation contents (R1
  relics, R2 card instances, R3 intent history) and the encodings (R6), and
  phase 2 changes how actions are scored (R8/R9). A delta across that many
  simultaneous changes attributes nothing — and it does not even hold for
  policy-free measurements, since a random policy over a *different action
  space* samples a different distribution. There is no controlled
  comparison to be had, so do not manufacture one.

Do not re-introduce any before/after figure as a blocker, a deliverable, or
a success criterion. Validation is against **engine ground truth**, which is
stable across the restructure and does not care what the old encoding was:

1. **Observation-content assertions** — the check that actually pins the new
   representation. For seeded states, decode the new integer observation back
   to facts and assert them against direct reads off `CombatState` /
   `RunState`: this creature's power instances and their aux fields, this
   hand slot's card and afflictions, this pile's multiset, this relic's
   displayed counter. Deterministic and immediate; a wrong offset or a lossy
   field fails a test at once instead of surfacing weeks later as a
   slightly-worse training curve.
2. **Random-policy sanity floors** — `masked_random_policy` /
   `play_random_run` over a fixed seed set, read as **absolute** sanity
   thresholds, not as a delta: runs complete, no hangs, floors reached and
   death-floor distribution are in a plausible band, every decision kind is
   actually reachable, no mask ever offers a single forced action where the
   game offers several. This catches gross breakage (a dead mask, a zeroed
   reward, an unreachable phase) for the price of no training and no GPU.
   (Blocked by the hang gate above.)

Record obs bytes/env/step for the new schema as an absolute figure — free,
deterministic, contention-immune, and it documents the payload the design
carries without implying a comparison.

After phase 2, report the new stack's own numbers — sps, and win rate / run
depth / floors from the fresh training run — as absolutes, and state plainly
what they do and do not establish. **Do not narrate improvement over the old
environment**; with this many simultaneous changes, any such claim would be
unfounded, and the report is more useful without it.

## Subagent execution

Waves of 2–4 concurrent implementers with **disjoint file footprints**, each
followed by an independent reviewer. Contended files here are
`sts2_rl/full_env.py`, `sts2_rl/run_env.py`, `sts2_rl/models.py`,
`sts2_rl/checkpoints.py`, `train_torch.py` — one lane owns each.

- Forbid in every dispatch: `git commit`, `push`, `add`, `stash`, `checkout`,
  `reset`, `restore`, and "temporarily revert the fix to see RED, then
  restore" (another agent is live in the tree — get RED by writing the test
  first).
- **Reviewers must not defer to the brief or the report.** For fidelity claims
  the decompiled C# at `c:\Users\Perry\Desktop\Slay the Spire 2` decides; for
  performance claims a measurement decides. A green suite is not evidence.
- ~20 test files touch the observation surface (`obs_segments`, `OBS_*`,
  `power_triples`, `pile_composition`); `test/test_models.py` has 10 tests.
  Expect to rewrite, not delete — a test deleted because it pinned the old
  schema is how a real regression gets laundered.

## Deliverables

Per phase: working tree staged (never committed), suite green against the
4091 baseline, and a written report. The phase 1/2 riders ship inside their
phase (same schema bump, same report); each cut rider is recorded as a
decision, since cutting one re-prices its schema bump later. Phase 3 items
are independent projects — one report each, never bundled. For phase 1/2
additionally: the schema document (what each segment is, what is int vs
float, what the mask means), the hidden-information non-leak test, the
observation-content assertions, and the new stack's own absolute figures.
No before/after table — see Measurement.

Update a progress ledger as you go — it survives context compaction and is
authoritative over your own recollection.
