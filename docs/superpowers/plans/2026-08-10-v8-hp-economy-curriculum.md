# v8 Training Plan: HP Economy, Potion Timing, Early-Game Credit

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Checkbox (`- [ ]`) steps. Subagents on sonnet.

**Goal:** Supersede v7's Phase C with a curriculum that fixes the ROOT CAUSE of the rest-heal pathology (combat HP hemorrhage), teaches potion timing, and tightens early-game credit assignment — then runs the ascension ramp v7 built.

**Status of v7 (audited 2026-08-10):** Phases A and B are FULLY implemented and staged (ascension 1–10 plumbing + 100 monsters; all reward knobs `floor_rewards_by_act`/`reward_upgrade`/`reward_remove`/`reward_elite`; `deck_random_prob`; ep_* counters through EnvSpec/EP_METRIC_KEYS/train CSV; eval cards CSV, `potion_use_rate`, `--gimmick-probes`; `train_curriculum_v7.ps1`). Smoke-constructed clean. Only Task 12 (the training run) never launched. **v8 replaces that run**; v7's env work is the foundation and none of it is redone here.

## Why v7's Phase C is not enough (Perry, 2026-08-10)

The model rests at every rest site because it **always arrives low** — it bleeds unnecessary HP by misplaying combats — so healing genuinely dominates upgrading for the policy it currently is. A +0.5 upgrade reward will lose that argument: surviving longer is worth more return than the bonus. The fix must make combat cheaper in HP *first*, and only then does the upgrade incentive have room to win.

Eval evidence (`runs/eval_v6_iter1110.episodes.csv`, 150 eps): mean `hp_left` **0.8** (the agent lives at the floor of the HP bar); 726 rest-heals vs 2 upgrades; deaths walled at floor 31 (39) and floor 16 (35) — the act bosses; 9.8 energy unspent per episode.

## Design decisions (brainstormed alternatives and verdicts)

1. **Concave potential-based HP shaping (`hp_potential_scale`) — ADOPT.** (Revised 2026-08-10 after Perry's correction: HP loss is not inherently bad — high-level play SPENDS health on elites and keeps just enough to reach the act-end heal.) New env term: potential `Φ = C·φ(hp/max_hp)` with `φ` concave piecewise-linear — a `low_share` fraction of the potential is earned in `[0, knee]`, the rest in `[knee, 1]` (defaults `C` via `hp_potential_scale=0.0` OFF, `hp_potential_knee=0.35`, `hp_potential_low_share=0.7`); each step adds `C·(φ(after) − φ(before))`. Why this exact shape:
   - **Top-half HP is cheap currency:** −20% of the bar at high HP costs ~0.37 (C=4) — an elite (+0.5 elite +0.25 relic + card/gold) is clearly net-positive, so elite-greed is *paid*.
   - **Low HP is precious:** the same loss below the knee costs ~1.6 — stop tanking when short.
   - **Heals earn their restored potential:** rest-heal at 20% HP ≈ +1.5, at 85% ≈ +0.3 < the +0.5 upgrade term — heal-vs-smith flips with HP level automatically.
   - **Heals REFUND the act's spending** (the term telescopes on Φ). The big one is the act-entry Ancient heal — full missing HP, ×0.8 at asc 2+ (`events/ancient.py:24-41`; note `advance_act` itself has NO heal step, `run.py:1234` — the Ancient node IS the between-acts heal) — plus 30% rest heals. Intra-act HP spending is near-free iff the agent survives to collect — exactly the elite-greed loop. Death forfeits the refund, and WearyTraveler shaving the refund to 80% at asc 2+ tightens the HP economy exactly when the curriculum ramps.
   - Potential-based shaping (Ng et al.) — policy-optimum preserving, only densifies the signal.
   **Rest-heal subsidy analysis (Perry's question, 2026-08-10):** rest-heal shaping is a LOAN against the Ancient refund (telescoping — heal now +ΔΦ, refund later −ΔΦ), so the only permanent rest-site term is smith's +0.5. Under γ=0.999 with ~600 decisions to the next Ancient the repayment discounts to ~55%, leaving heal a net ~0.45·ΔΦ subsidy that scales with need (net +0.67 at 20% HP vs +0.13 at 85%, against smith's flat +0.5) and vanishes at the pre-boss rest — the correct shape. Zeroing rest-heal shaping entirely was CONSIDERED AND REJECTED: with the refund still shrinking, each heal would net −ΔΦ, punishing hardest at low HP → never-heal/die-at-elite collapse risk. **Contingency if s7 unmasked eval still shows comfortable-HP heals:** (preferred) pay no shaping on rest heals that START above the knee; or pay rest heals a 0.5 fraction of ΔΦ — both keep desperate heals positive, both one-line changes in Task 1's helper call site.
   REJECTED: flat asymmetric loss-only penalty (previous draft — punishes elite-greed, the behavior we want); the symmetric `hp_reward_scale` (`run_env.py:944`) as-is (linear ⇒ no danger-zone/currency distinction, and it telescopes the same way but pays heals at full HP as much as at 5%); room-conditional flat penalty (normal-rooms-only pricing — simpler FALLBACK if the critic finds concave shaping noisy, but it hard-codes "elites free at any HP", happily tanking an elite at 15%); per-encounter damage budgets (needs a calibrated table per encounter×act×asc, stale on every balance change, gameable at the boundary).
2. **Combat-env sharpening stages — ADOPT.** `STS2FullCombatEnv` already defaults to HP-delta reward and supports run-state snapshots (`--start-snapshots`, R11) so the policy drills combat efficiency on realistic mid-run decks, not just starter decks. One stage before the run curriculum (asc 0) and one before the asc-10 push. This attacks missed-lethal / wasted-energy directly — capability, not incentive. REJECTED alternative: only shaping inside the run env — combat decisions are ~1 of 40+ decisions/floor there; the gradient is too dilute to unlearn entrenched misplay quickly.
3. **Rest-heal masking curriculum knob (`rest_heal_mask_above`) — ADOPT.** When set, `REST_HEAL` is masked out whenever `hp_ratio ≥ threshold` (and another rest action is legal). At 0.8 this only forbids near-worthless heals (30% heal mostly overflows), forces the policy to actually *experience* upgrading — data it currently never generates (2 upgrades in 35M steps means the critic has no idea what upgrades are worth) — and is annealed OFF in the final stage so the shipped policy is unconstrained. REJECTED alternatives: behavior cloning / teacher forcing (no infrastructure exists in the repo, big build); bigger upgrade rewards (invites reward hacking and still loses to survival value while combat bleeds).
4. **Potion ledger (`potion_potential_scale`) — ADOPT, k=0.3 (Perry's design, 2026-08-10).** +k when a potion enters the belt, −k when it leaves for ANY reason (use, sell, full-belt discard — sell must charge the −k too, or pick-up-and-sell prints k+gold). **NO terminal zeroing**: an unused potion keeps its +k forever, so k is the *minimum effect a potion must deliver to be worth throwing away* — the model has to weigh the drink's value against a real bar, not just shuffle timing. Why this fixes v6's chug-on-pickup where "no potion reward" didn't: v6 priced neither holding (zero belt value + γ=0.999 ⇒ instant use was the discount-*optimal* policy) nor timing (linear HP term ⇒ a heal at 90% HP was worth the same as at 20%). Here the bar interacts with decision 1's concave shaping to define "key moment" *endogenously* — a potion effect saving ~10% max HP prices at ~0.8 shaping below the knee (0.8 > k ⇒ drink) but ~0.18 at high HP in a trivial fight (0.18 < k ⇒ hold), and a run-saving drink protects all remaining floor rewards + win 12, clearing any bar. A brutal hallway fight qualifies; a lazy elite turn doesn't; no room label is ever consulted. Split counters `ep_potions_used_elite`/`ep_potions_used_boss`/`ep_potions_used_normal` + `ep_potions_expired` (held at episode end) are kept as METRICS ONLY — they measure the timing distribution, they never shape it. Known failure mode is over-hoarding (holding pays k forever): tempered because dying forfeits far more than the belt's 3k, watched via `ep_potions_expired`, contingencies in Task 7. REJECTED: room-conditional use terms ±0.15/−0.10 (previous draft — hard-codes "elite = key moment", which is a label, not the game's; Perry: key moments can be hard hallway fights); potion curriculum masks, room- or danger-gated (Perry: no forbidding potion actions); terminal Φ_p=0 expiry payback (telescopes the ledger away and with it the weighing property); "reward drinking when it mattered" counterfactual — unspecifiable without solving the game (v7's original reasoning stands).
5. **Act-1-only stage (`--acts 1`) — ADOPT.** Early-game decisions (drafts, elite pathing, first rest) currently sit 30+ floors from the terminal signal. `RunDriver` already supports act restriction; an act-1-only stage makes the act-1 boss the episode terminal, so draft-quality credit lands ~15 floors away instead of ~45. Run at asc 4 so the 8-elite map and Bane pressure shape pathing. VERIFY in dry-run: `--acts 1` + boss kill pays `reward_win` (if it doesn't, the stage still works — floors + elite/upgrade terms carry it — but log it).
6. **Relic reward (`reward_relic`) — ADOPT, +0.25.** Relics are the purest long-term-power currency and today carry zero reward; elites/shops/events all become more attractive. Counted like the deck deltas: `len(run.relics)` growth between out-of-combat decisions.
7. **Keep from v7 unchanged:** act-scaled floors 1.0/1.5/2.0, win 12, upgrade 0.5, elite 0.5, remove 0.25, deck randomization schedule, fixed-asc stages, no obs change (schema stays 11), critic-warmup at every boundary, v6 checkpoint as seed.

## Global constraints

- All new env kwargs default OFF/None — default `STS2RunEnv()` bit-identical to today. Full suite green after every task (`.venv\Scripts\python.exe -m pytest -q`).
- No obs schema change (`RUN_OBS_SCHEMA_VERSION` = 11).
- Git: **stage only, never commit.**
- Subagents on sonnet. Venv `.venv\Scripts\python.exe`; stdlib csv only.

---

# Phase B′ — new env knobs (all small, all follow v7 Task 6/7 patterns)

### Task 1: `hp_potential_scale` (concave HP potential shaping)

- Modify `sts2_rl/run_env.py`: kwargs `hp_potential_scale: float = 0.0`, `hp_potential_knee: float = 0.35`, `hp_potential_low_share: float = 0.7`. Helper (module-level, unit-testable):

```python
def _hp_potential(ratio: float, knee: float, low_share: float) -> float:
    """Concave HP potential: `low_share` of the value lives in [0, knee]
    (danger zone — HP is precious), the rest in [knee, 1] (HP is currency
    to spend on elites). Piecewise-linear, phi(0)=0, phi(1)=1."""
    if ratio <= knee:
        return low_share * ratio / knee
    return low_share + (1.0 - low_share) * (ratio - knee) / (1.0 - knee)
```

  In `step()` next to the `hp_reward_scale` line (`run_env.py:944`), using the same clamped-HP convention: `reward += self._hp_potential_scale * (phi(after) - phi(before))` with each ratio computed against its own step's `max_hp` (max-HP gains shouldn't fire the term backwards). Death terminal: hp=0 ⇒ φ=0, no special case. Also tally `self._ep_hp_lost += max(0, hp_before - hp_now)` (new counter, reset in `reset`, emitted in `_info`'s episode block) so eval can trend combat sloppiness independently of the shaping.
- Tests in `test/test_v8_rewards.py` (new): φ unit tests (0/knee/1 anchors, concavity: marginal value below knee > above); a damage step at high HP costs less than the same absolute damage at low HP; a heal step at low HP earns more than at high HP; telescoping (damage then full heal nets ~0); default-off bit-identity vs a plain env on a fixed seed (mirror `test_default_env_reward_unchanged` in `test_v7_rewards.py`).
- Stage.

### Task 2: potion ledger + timing counters (metrics only)

- Modify `run_env.py`: kwarg `potion_potential_scale: float = 0.0` (decision 4). Per-step `reward += k · (potions_now − potions_before)` off the belt count the existing delta block (v7 Task 6c) already tracks — pickup +k; use, sell, or full-belt discard −k. **No terminal term** — potions still held at episode end keep their +k (that IS the weighing bar); just tally the held count as `ep_potions_expired` at terminal (hoarding/waste gauge, no reward attached).
- Same block: classify each USE by the current room context (elite/boss combat vs anything else — reuse the `rewards.room_type`/room-kind source `_count_behavior` uses for elites; boss detection mirrors it) into counters `ep_potions_used_elite/boss/normal` (their sum must equal `ep_potions_used`). Also `ep_potion_use_hp`: running sum of `hp/max_hp` at each use — eval divides by uses for mean hp-at-use, the direct "drinks happen in trouble, not on pickup" gauge. These carry NO reward — eval-visibility only, so the timing distribution is measurable without being shaped. A potion SOLD in a shop hits the ledger's −k but no use-counter (it wasn't drunk).
- Extend `EP_METRIC_KEYS` + train CSV + episodes-CSV columns for the five new counters (follow exactly how the five v7 keys flowed through `vec_env.py:142-148`, `train_torch.py`, `evaluation.py`).
- Tests: ledger fires +k on pickup and −k on use AND on sell; pickup-then-use nets 0 while pickup-then-episode-end nets +k with `ep_potions_expired` = 1 (the no-terminal-zeroing property, asserted explicitly); classification unit test with a scripted potion use in an elite vs normal combat; sum invariant; defaults-off identity.
- Stage.

### Task 3: `reward_relic`

- Modify `run_env.py`: kwarg `reward_relic: float = 0.0`; snapshot `len(run.relics)` alongside `_deck_len_base` (out-of-combat decisions only, same guard), reward the positive delta, tally `ep_relics`. Starting relic must not count (baseline taken after `_switch(None)`).
- Thread through EnvSpec/CLI/EP_METRIC_KEYS as above. Tests: relic pickup fires the term; defaults-off identity.
- Stage.

### Task 4: `rest_heal_mask_above` curriculum mask

(Potion actions are NEVER masked — decision 4; the rest mask stays because the upgrade-data-starvation argument in decision 3 is different in kind: `REST_HEAL` masked at high HP forces *generation of upgrade data*, it doesn't forbid a timing the policy should learn.)

- Modify `run_env.py` (or the mask assembly site — grep `action_masks` / rest handling): kwarg `rest_heal_mask_above: float | None = None`. When the pending decision is a rest-site choice, `run.hp / run.max_hp >= threshold`, AND at least one other rest action is legal: clear `REST_HEAL`'s bit (`driver.py:79`, `REST_HEAL=0` within the choice block). Never mask when it's the only legal action.
- Thread `EnvSpec.rest_heal_mask_above` + `--rest-heal-mask-above` CLI (run/column only). Checkpoint-independent (mask knob, not stamped).
- Tests: at threshold 0.8 with full HP, mask has REST_HEAL off and REST_SMITH on; below threshold unchanged; `None` defaults bit-identical masks on a fixed seed.
- Stage.

### Task 5: CLI flags for Tasks 1–2 + eval surfacing

- `train_torch.py`/`eval.py`: `--hp-potential-scale` (knee/low-share stay kwarg-only at their defaults unless tuning demands flags), `--potion-potential-scale`, `--reward-relic` (Task 3/4 flags land in their tasks if not already). Same run/column-only guard pattern.
- **Relax `train_torch.py`'s `--env combat` + `--ascension` rejection** (v7 Task 5 added it; v7 Task 10 relaxed only `eval.py`): the v8 script trains combat stages at asc 10, and `STS2FullCombatEnv` already takes the kwarg.
- `evaluation.py`/`eval.py`: episodes CSV + summary gain `hp_lost` mean, `potion elite-share` (= (elite+boss uses)/all uses, pooled — informational, no target), `potions_used` mean, `potions_expired` mean (hoarding gauge), `relics` mean.
- Smoke: 2-env 2048-step column run with all new flags; confirm CSV columns; delete scratch.
- Stage.

---

# Phase C′ — the v8 curriculum run

### Task 6: `train_curriculum_v8.ps1`

Created alongside this plan (same resume/handoff/`-Resume` semantics as v7's script). Stage table — base rewards on every RUN stage: `--floor-rewards 1.0 1.5 2.0 --reward-win 12 --reward-upgrade 0.5 --reward-elite 0.5 --reward-remove 0.25 --reward-relic 0.25 --hp-potential-scale 4.0 --potion-potential-scale 0.3` (potion actions are never masked; the only mask is the rest-heal one, per stage table):

| Stage | Env | Asc | Steps | deck-rand | rest-mask | Extra | Purpose |
|---|---|---|---|---|---|---|---|
| s0 | combat (snapshots) | 0 | 3M | — | — | lr 6e-4 | combat-efficiency drill on realistic decks (HP-delta reward native) |
| s1 | run | 0 | 4M | 0.50 | 0.80 | lr 6e-4, warmup 40 | reward re-baseline; upgrade data generation starts |
| s2 | run `--acts 1` | 4 | 3M | 0.50 | 0.80 | lr 6e-4, warmup 20 | early-game credit: act-1 boss is the terminal |
| s3 | run | 4 | 5M | 0.50 | 0.80 | lr 6e-4, warmup 15 | full runs, map/economy ascensions |
| s4 | run | 7 | 5M | 0.25 | 0.80 | lr 6e-4, warmup 15 | + inflation, scarcity |
| s5 | combat (snapshots) | 10 | 2M | — | — | lr 3e-4 | re-drill vs tough/deadly enemies before the wall |
| s6 | run | 10 | 8M | 0.25 | 0.85 | lr 3e-4, warmup 15 | + tough/deadly, double boss |
| s7 | run | 10 | 10M | 0.00 | **off** | lr 3e-4, ent 0.01→0.004, warmup 10 | polish, unconstrained policy |

40M steps total (~18h at v6 throughput). Design notes (encoded as script comments): critic-warmup at EVERY env-kind or reward-scale boundary — combat-env returns are ~±1.x vs run returns ~80, so s1/s3/s6 warmups are load-bearing, not optional; the rest mask is a training constraint annealed off before the artifact stage so eval'd behavior is the policy's own; combat stages save their own checkpoints but the shipping artifact is s7 (env_kind "run", the thing eval.py expects).

- [ ] **Step 1:** Snapshot corpus for s0/s5: generate/refresh run-state snapshots with the existing R11 tooling from v6-checkpoint rollouts (grep `start-snapshots` in `train_torch.py`/`full_env.py` for the expected file format and the generator entry point). Record the path; the script takes it as `-SnapshotPath` and SKIPS combat stages with a loud warning if missing.
- [ ] **Step 2: Dry-run gate** (script's `-Smoke` mode: 65k steps per stage, scratch tag): verify (a) v6→s0 combat resume loads (entset obs compatibility — gimmick probes already do run-ckpt-on-combat-env, but verify the TRAIN direction), (b) s0→s1 kind switch resumes, (c) `--acts 1` terminal pays `reward_win` (log if not), (d) new CSV columns present, (e) rest-mask stage shows REST_HEAL masked at full HP in a probe episode, (f) potion ledger fires in a probe episode: +0.3 on a pickup step, −0.3 on the use step, and potion actions LEGAL everywhere they'd normally be. Delete scratch files.
- [ ] **Step 3:** Stage the script.

### Task 7: Launch, gates, rollback (record in `docs/superpowers/plans/v8-run-log.md`)

Per-stage eval: `eval.py --env run --episodes 150 --baselines --ascension <asc> --load <ckpt> --csv runs/eval_v8_s<N> --gimmick-probes` (combat stages: eval the NEXT run stage instead; they're means, not artifacts).

- **s1:** `elites`/episode NOT below v6's (the shaping must not scare the policy off elite-greed — HP loss falling by avoiding elites is a FAILURE); `hp_lost`/floor falling vs v6 eval at similar elite counts; `rest_upgrade_rate ≥ 0.15` **with the mask off at eval time** (eval envs never set the mask — measure the policy, not the constraint); win ≥ 0.03; ≥60% of pool cards taken once (v7 gate kept).
- **s2:** act-1 boss (floor-16 wall) clear rate strictly above s1's.
- **s3–s6:** within-stage `ep_ret` recovery to ≥70% of the previous stage's final; `upgrades`/episode not declining; potion behavior watched on BOTH edges — `potions_used`/episode ≥ ~1 (the bar must not tip into never-drink) AND `potions_expired` NOT rising stage-over-stage (if uses collapse and expired climbs, the k=0.3 bar is too high: halve `potion_potential_scale` 0.3 → 0.15, or add a death-only expiry penalty of −k/2 per held potion — never on wins, holding potions you never needed on a winning run is fine play). Elite-share is reported but has no target — key moments are wherever the state says they are.
- **s7 (final, asc 10):** `rest_upgrade_rate ≥ 0.25` (unmasked!); `energy_unspent/turn ≤ 0.15`; elites/episode ≥ s1's with `hp_lost`/floor not higher than s1's at the harder difficulty (spending MORE total HP is fine if elites rose with it); potion timing (no elite-share target — decision 4): `potions_used`/episode ≥ 1 with `potions_expired` ≤ 1.5 on DEATHS specifically (dying with a full belt means the bar beat survival — that's the failure; expiring potions on wins is fine); mean hp-at-use trending BELOW mean hp overall in the episodes CSV (drinks happen in trouble, not on pickup); gimmick-probe wins > v6 on all three; win rate reported honestly (no target at asc 10).
- **Rollback (any stage):** `ep_ret` −50% from stage start, unrecovered in 100 iters → restart stage from previous checkpoint, warmup doubled, lr halved. **Mask-specific check:** if s7 (mask off) collapses rest behavior back to always-heal, the mask was doing all the work — extend s7 2M; if it persists, accept the finding and apply the decision-1 rest-heal contingency (no shaping on rest heals starting above the knee, or half-ΔΦ rest heals) and/or steepen the danger zone (`hp_potential_low_share` 0.7 → 0.8) in a follow-up stage rather than re-masking. **Potion-ledger contingencies:** instant chugging persists (mean hp-at-use ≈ hp overall, uses ≈ pickups) → the bar is too low, raise `potion_potential_scale` 0.3 → 0.5; never-drink hoarding (uses < 1/episode, deaths with full belts) → bar too high, halve to 0.15 or add the death-only −k/2 expiry penalty from the s3–s6 gate. No potion masks, no room terms, in any contingency.

## Out of scope (kept from v7, still right)

Ascension in the obs; missed-lethal detector; asc-10 conformance seed (capture-in-game still worth doing); "drink when it mattered" counterfactual potion reward.

## Execution order

Tasks 1→2→3→4→5 (independent enough to wave 1–4 on sonnet subagents after reading `test_v7_rewards.py` patterns; 5 last) → 6 → 7. Phase B′ is verifiable at asc 0 before any training.
