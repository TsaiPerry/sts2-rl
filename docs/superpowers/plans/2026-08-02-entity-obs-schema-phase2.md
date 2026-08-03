# Entity obs schema — Phase 2: tied action head Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the positional `nn.Linear(256, n_actions)` action head with a pointer head that scores `(card_entity, target_entity)` pairs from the same per-row entity features the observation encoder already computes, for both envs' combat blocks — then extend it to the run env's content-carrying decisions (R8) and enrich the pair score (R9), and measure encoder sharing (R10).

**Architecture:** `_EntsetEncoder` already implements phase 2's "encoder" half (one `nn.Embedding(cap+1, dim, padding_idx=0)` per vocab kind, per-row `Linear(row_in, 32)+tanh` projections, masked sum-pool). Phase 2 exposes those per-row projections *before* pooling, adds a `PairPointerHead` that scores source-row × target-row pairs conditioned on the trunk context, and assembles the logit vector per an explicit per-env `ActionLayout` instead of one opaque Linear. The masked-categorical contract (`get_value` / `get_action_and_value`, `_MASK_FILL`, ≥1 legal action) is untouched; the PPO loop in `train_torch.py` does not change.

**Tech Stack:** PyTorch (2.13, CPU tests), gymnasium spaces.Dict obs, pytest.

## Global Constraints

- **NEVER `git commit` or `git push`. Stage only (`git add`).** This overrides every skill/workflow default, including the commit steps this plan template normally carries. (CLAUDE.md §4.)
- Subagent lanes are additionally forbidden: `git add`, `stash`, `checkout`, `reset`, `restore`, and "temporarily revert the fix to see RED". The controller stages.
- **No old-vs-new comparison in any form** (user decision 2026-08-01). R10's within-new-stack A/B — two arms one variable apart — is the only comparison this project runs.
- Full suite command (baseline **4399 passed / 6 xfailed / 0 failed**):
  `py -m pytest test -x -q --ignore=test/test_conformance_floor_state.py`
  That ignored file's 2 failures are a missing-fixture environment gap — never "fix", never count.
- Use the `py` launcher (no `python` on PATH); `cd c:\Users\Perry\Desktop\sts2-rl` explicitly.
- The decompiled game source (`c:\Users\Perry\Desktop\Slay the Spire 2`) is read-only authority; never edit it.
- **Mutation-check every invariant test** via throwaway scratchpad scripts (runtime monkeypatch, never editing tracked files).
- **The run-env `env.step()` hang is owned by the concurrent audit** — do not diagnose it, do not add timeout-and-truncate. Nothing in this plan requires long unattended run-env rollouts except R10's run-arm probe, which is explicitly best-effort.
- The observation schema does NOT change in phase 2 core / R8 / R9 as planned here (combat 6, run 9). If any task finds it must widen an obs block, STOP and report to the controller first — a bump is still cheap (nothing trained yet) but must propagate (run envs embed the combat block; bump `RUN_OBS_SCHEMA_VERSION` in the same change; `test_run_schema_version_matches_declared_dims` pins this).

## Decisions locked by the controller (do not re-litigate in lanes)

1. **Evolve `entset` in place; no fourth arch string.** Nothing has been trained for real, so the from-scratch retrain is already owed; a new arch string would duplicate `make_model`/`ARCHS`/guard/test surface for zero protection. Honest refusal of any stale scratch checkpoint is provided instead by a new `head_version` field (Task 5): `checkpoint_payload` stamps `head_version = models.ENTSET_HEAD_VERSION` (2); `check_checkpoint` treats a missing key as 1 and refuses a mismatch with a "predates the phase-2 tied action head, use --fresh" message. This is the same honesty argument as the round-2 gap-3 fix (a shape mismatch catching it is the *fallback*, not the gate).
2. **Phase 2 core ties the combat block only** — end-turn scalar head + play pairs (hand × enemies) + potion pairs (belt rows × enemies) — in BOTH envs (the run env's combat block reads the `combat.*` rows). CHOICE(16)/SELECT(96)/belt-POTION(10) stay positional Linear in core and are R8's work (Task 8), matching the prompt's own sequencing.
3. **Untargeted cards keep the fold-to-first-living-enemy convention** at the action level (that's the env's action space, not the model's choice). The pair head sees the folded enemy row; the card's own features carry target-type, so the MLP can learn to ignore the target half. No learned null-target vector in core; recorded so it isn't silently re-decided. R9 revisits if pair features make the dummy target actively misleading.
4. **Exposed row features are mask-multiplied** (`projected * present_mask`), so a PAD row is a zero *vector*, not `tanh(bias)`. This makes the equivariance tests exact and keeps PAD rows inert in every downstream head.
5. **`action_layout` is a required argument** of `EntitySetActorCritic` — no positional-fallback default. A silent fallback is the exact defect class round 2's gap 4 documented (a safety behavior that lapses without erroring). Existing direct-construction tests get updated deliberately.
6. **Critic is untouched in core** (separate encoder + pooled trunk → value). Encoder sharing is R10's measured question, not a default.

## File structure

- `sts2_rl/models.py` — encoder row exposure (Task 1); `ActionLayout` + entset head assembly (Task 3, 4); `ENTSET_HEAD_VERSION` constant (Task 5).
- `sts2_rl/action_heads.py` — **new**: `PairPointerHead`, `PointerHead` (single-set pointer, used by core for nothing but built for R8… NO — YAGNI: built in Task 8, not before). Task 2 creates the file with `PairPointerHead` only.
- `sts2_rl/checkpoints.py` — thread `action_layout` through `make_model`; `head_version` refusal (Task 5).
- `train_torch.py` (repo root) — `checkpoint_payload` gains `head_version` (Task 5). No other change.
- `test/test_action_heads.py` — new unit tests (Task 2).
- `test/test_entset_rows.py` — new encoder-row tests (Task 1).
- `test/test_tied_head_combat.py`, `test/test_tied_head_run.py` — integration/equivariance (Tasks 3, 4).
- Existing tests referencing entset construction/behavior — updated in the task that breaks them, never weakened.

Line numbers below were verified 2026-08-02 but drift; every lane must re-verify against the real file before editing.

---

### Task 1: Expose masked per-row features from `_EntsetEncoder`

**Files:**
- Modify: `sts2_rl/models.py` (`_EntsetEncoder.forward`, ~559-593)
- Test: `test/test_entset_rows.py` (new)

**Interfaces:**
- Produces: `_EntsetEncoder.encode(obs: TensorObs) -> tuple[torch.Tensor, dict[str, torch.Tensor]]` — `(pooled, rows)`. `pooled` is bit-identical to today's `forward` output. `rows` maps each row block's **logical name** (post `_entset_logical_name` stripping — e.g. `"hand"`, `"enemies"`, `"potions"`, `"select.candidates"`, `"run.potions"`, and per-slot `"enemy0.powers"`…) to a `(..., cap, block_dim)` tensor, already multiplied by the presence mask so PAD rows are exact zero vectors.
- `forward(obs)` becomes `return self.encode(obs)[0]` — callers unchanged.
- Consumes: nothing from other tasks.

- [ ] **Step 1: Write failing tests** in `test/test_entset_rows.py`:

```python
import numpy as np, torch
from sts2_rl import full_env, models
from sts2_rl.models import _EntsetEncoder, ENTSET_EMBED_DIMS, TensorObs

def _combat_encoder():
    layout = full_env.combat_obs_layout()
    return _EntsetEncoder(layout.segments_f, layout.segments_i, ENTSET_EMBED_DIMS), layout
    # NOTE: match the real constructor signature (verify in models.py — the
    # investigation map says (f_segments, i_segments, embed_dims)).

def _obs_from_env(seed=0):
    env = full_env.STS2FullCombatEnv()
    obs, _ = env.reset(seed=seed)
    return TensorObs(torch.as_tensor(obs["f"])[None], torch.as_tensor(obs["i"]).long()[None])

def test_encode_pooled_identical_to_forward():
    enc, _ = _combat_encoder()
    obs = _obs_from_env()
    with torch.no_grad():
        pooled, _rows = enc.encode(obs)
        fwd = enc.forward(obs)
    assert torch.equal(pooled, fwd)

def test_encode_row_block_shapes():
    enc, _ = _combat_encoder()
    obs = _obs_from_env()
    _, rows = enc.encode(obs)
    assert rows["hand"].shape == (1, full_env.MAX_HAND, enc.block_dim)
    assert rows["enemies"].shape == (1, full_env.MAX_ENEMIES, enc.block_dim)
    assert rows["potions"].shape == (1, full_env.MAX_POTION_ROWS, enc.block_dim)

def test_pad_rows_are_zero_vectors():
    enc, _ = _combat_encoder()
    obs = _obs_from_env()
    _, rows = enc.encode(obs)
    hand_ids = obs.i[..., ...]  # slice the hand.ids segment via the layout's obs_slices
    # For every hand slot whose primary id == 0 AND floats all zero, the row must be exactly 0.
    # Build the presence bool the same way OBS_SCHEMA §2.1 defines it, from the obs itself,
    # then assert rows["hand"][~present] == 0 exactly and rows["hand"][present] != 0 somewhere.
```

Fill the ellipses against the real `ObsLayout` slicing API (`obs_slices()` / segment lookups — read `sts2_rl/obs.py`); the assertions above are the contract, the slicing is plumbing. Add a fourth test: `rows` keys exactly equal the set of row-block logical names `entset_segment_plan` yields (no missing, no extra).

- [ ] **Step 2: Run to verify failure** — `py -m pytest test/test_entset_rows.py -q` → FAIL (`encode` does not exist).
- [ ] **Step 3: Implement.** Inside the existing forward loop, after `projected = torch.tanh(self.blocks[name](x))` and the mask computation, store `masked = projected * mask` in an ordered dict keyed by logical name; pooled part stays `masked.sum(dim=-2)` (algebraically identical to today's `(projected * mask).sum(-2)` — keep the multiply-then-sum order so `test_encode_pooled_identical_to_forward` passes bit-exactly). `encode` returns `(cat(pooled_parts + raw_parts, -1), rows_dict)`; `forward` delegates. Expose `self.block_dim`.
- [ ] **Step 4: Run task tests** → PASS.
- [ ] **Step 5: Mutation checks** (scratchpad script, runtime monkeypatch): (a) patch `encode` to return unmasked `projected` rows → `test_pad_rows_are_zero_vectors` must go RED; (b) patch pooling to `mean` → identity test must go RED. Record both in the lane report.
- [ ] **Step 6: Full suite** — controller reruns after lane lands.

### Task 2: `PairPointerHead` module

**Files:**
- Create: `sts2_rl/action_heads.py`
- Test: `test/test_action_heads.py`

**Interfaces:**
- Produces:

```python
class PairPointerHead(nn.Module):
    """Scores every (source_row, target_row) pair, row-major (src*T + tgt),
    matching decode_combat_action's h*MAX_ENEMIES + e ordering."""
    def __init__(self, src_dim: int, tgt_dim: int, ctx_dim: int,
                 pair_dim: int = 0, hidden: int = 64):
        super().__init__()
        self.ctx_proj = _layer_init(nn.Linear(ctx_dim, 32))
        self.mlp = nn.Sequential(
            _layer_init(nn.Linear(src_dim + tgt_dim + 32 + pair_dim, hidden)),
            nn.Tanh(),
            _layer_init(nn.Linear(hidden, 1), std=0.01),
        )

    def forward(self, src: Tensor, tgt: Tensor, ctx: Tensor,
                pair: Tensor | None = None) -> Tensor:
        # src (..., S, ds); tgt (..., T, dt); ctx (..., dc); pair (..., S, T, dp)
        # returns (..., S*T)
        S, T = src.shape[-2], tgt.shape[-2]
        s = src.unsqueeze(-2).expand(*src.shape[:-2], S, T, src.shape[-1])
        t = tgt.unsqueeze(-3).expand(*tgt.shape[:-2], S, T, tgt.shape[-1])
        c = torch.tanh(self.ctx_proj(ctx)).unsqueeze(-2).unsqueeze(-2) \
            .expand(*ctx.shape[:-1], S, T, 32)
        parts = [s, t, c] + ([pair] if pair is not None else [])
        return self.mlp(torch.cat(parts, dim=-1)).squeeze(-1).flatten(-2)
```

  (`_layer_init` imported from `models.py` — if that creates a circular import, move `_layer_init` into `action_heads.py` and have `models.py` import it from there; do NOT duplicate it.)
- Consumes: nothing (pure module; Task 3 wires it).

- [ ] **Step 1: Failing tests** in `test/test_action_heads.py`:

```python
def test_output_shape_and_row_major_order():
    head = PairPointerHead(8, 8, 16)
    src, tgt, ctx = torch.randn(2, 3, 8), torch.randn(2, 4, 8), torch.randn(2, 16)
    out = head(src, tgt, ctx)
    assert out.shape == (2, 12)
    # row-major check: recompute pair (s=1, t=2) alone and compare to out[:, 1*4+2]
    single = head(src[:, 1:2], tgt[:, 2:3], ctx)
    assert torch.allclose(out[:, 1*4+2], single[:, 0])

def test_source_permutation_equivariance():
    head = PairPointerHead(8, 8, 16)
    src, tgt, ctx = torch.randn(1, 3, 8), torch.randn(1, 4, 8), torch.randn(1, 16)
    perm = torch.tensor([2, 0, 1])
    out, out_p = head(src, tgt, ctx).view(1, 3, 4), head(src[:, perm], tgt, ctx).view(1, 3, 4)
    assert torch.allclose(out[:, perm], out_p, atol=1e-6)

def test_target_permutation_equivariance():  # analogous over tgt axis
def test_pair_features_change_scores():      # pair=zeros vs pair=randn differ
def test_gradients_reach_all_inputs():       # backward, assert src.grad/tgt.grad/ctx.grad all nonzero
```

- [ ] **Step 2: Verify failure** (module absent). **Step 3:** implement as specced. **Step 4:** PASS.
- [ ] **Step 5: Mutation check**: monkeypatch `flatten(-2)` order (transpose before flatten) → row-major test RED.

### Task 3: Combat-env tied head in `EntitySetActorCritic`

**Files:**
- Modify: `sts2_rl/models.py` (`EntitySetActorCritic`, ~595-650)
- Test: `test/test_tied_head_combat.py` (new); update any existing entset construction sites in `test/` (search `EntitySetActorCritic(`)

**Interfaces:**
- Produces:

```python
@dataclass(frozen=True)
class ActionLayout:
    """Declarative map from logit index ranges to scoring mechanisms."""
    n_actions: int
    end_turn_index: int | None          # 0 for combat block; None if absent
    play: tuple[str, str, int, int] | None    # (src_block, tgt_block, S, T) at base end_turn+1
    potion_pairs: tuple[str, str, int, int] | None  # (src_block, tgt_block, S_used, T); src rows sliced [:S_used]
    positional: tuple[tuple[int, int], ...] = ()    # (base, width) ranges scored by a plain Linear on ctx

def combat_action_layout(max_potions: int) -> ActionLayout   # 79 (=3) or the 121 embedded shape (=10)
```

  `EntitySetActorCritic.__init__(..., action_layout: ActionLayout)` — required, no default (controller decision 5). Actor trunk becomes a feature trunk (`Linear 256 → Tanh → Linear 256 → Tanh`, orthogonal init, same `hidden` attribute semantics); logits assembled: `end_turn = Linear(256,1)(ctx)`; play block = `PairPointerHead(block_dim, block_dim, 256)(rows[src], rows[tgt], ctx)`; potion block likewise with `rows[src][..., :S_used, :]`; each positional range = one `Linear(256, width)(ctx)`. Concatenate in index order; assert final width == `n_actions` at construction time. `_MASK_FILL` application, `get_value`, `get_action_and_value` signatures, and `obs_dim`/`n_actions`/`hidden` attributes unchanged.
- Consumes: Task 1's `encode` (actor path calls `self.actor_encoder.encode`; critic still calls `forward`), Task 2's `PairPointerHead`.

- [ ] **Step 1: Failing tests** in `test/test_tied_head_combat.py`:

```python
def _agent_and_env(seed=0):
    env = full_env.STS2FullCombatEnv()
    obs, _ = env.reset(seed=seed)
    layout = models.combat_action_layout(full_env.MAX_POTIONS)
    agent = models.EntitySetActorCritic(<real f/i segment args>, n_actions=79,
                                        action_layout=layout)
    return agent, env, obs

def test_contract_shapes():
    # get_value -> (batch,); get_action_and_value -> 4-tuple with correct shapes;
    # illegal logits == _MASK_FILL after masking path (probe via agent._dist internals
    # the same way existing entset tests do — mirror their access pattern).

def test_hand_swap_equivariance():
    # Reset env; find two hand slots h1,h2 holding DIFFERENT card ids.
    # Build obs tensor A. Build obs tensor B = A with hand.ids rows h1,h2 swapped
    # AND hand.f rows h1,h2 swapped (use full_env's obs slices; ints and floats both).
    # For every enemy e: logits_B[play(h1,e)] == logits_A[play(h2,e)] (atol 1e-5), and vice versa.
    # All non-play logits equal (pooled sum is permutation-invariant; positional ranges read ctx only).

def test_enemy_swap_equivariance():
    # Same over two enemy rows in a multi-enemy encounter — swap enemies.ids/enemies.f rows
    # e1,e2 AND the per-slot enemy{e}.powers + enemy{e}.intent_history segments, AND
    # the damage_matrix columns... NOTE: damage_matrix is raw floats fed to ctx via
    # pooled raw segments — swap its columns too so the whole obs is consistently permuted.
    # Then play/potion logits must permute in the target axis; others equal.

def test_positional_head_would_fail_equivariance():
    # Sanity on the test itself (anti "test that can't fail"): score the same swapped pair
    # through a plain Linear(ctx) baseline — assert the equivariance property does NOT hold
    # for it (guards against a test that trivially passes for any architecture).
```

- [ ] **Step 2: RED.** **Step 3:** implement `ActionLayout`, `combat_action_layout`, head assembly. **Step 4: task tests PASS.**
- [ ] **Step 5:** update existing entset tests that construct the class directly (add the layout arg); keep every behavioral assertion they carry.
- [ ] **Step 6: Mutation checks** (scratchpad monkeypatch): (a) swap the pair head's src/tgt argument order → hand-swap equivariance stays green but the row-major single-pair cross-check in Task 2 catches it — additionally assert here that changing ONLY hand slot h's card id changes play(h,·) logits *differently* than play(h',·); (b) feed unmasked rows → PAD-slot play logits shift, assert a dedicated test notices (empty hand slot's logits must be identical across two obs that differ only in another PAD row's floats… simpler: reuse Task 1's zero-vector guarantee). Record what each mutation tripped.
- [ ] **Step 7:** Controller: full suite.

### Task 4: Run-env wiring (combat block tied, rest positional)

**Files:**
- Modify: `sts2_rl/models.py` (`run_action_layout()`), `sts2_rl/checkpoints.py` (`make_model` threads layouts per env_kind)
- Test: `test/test_tied_head_run.py` (new)

**Interfaces:**
- Produces: `models.run_action_layout() -> ActionLayout` — `n_actions=run_env.N_ACTIONS` (243); end_turn 0; play `("hand","enemies",10,6)` base 1; potion_pairs `("potions","enemies",10,6)` base 61 (the embedded block is `combat_action_count(10)=121`); positional `((CHOICE_BASE,16), (SELECT_BASE,96), (POTION_BASE,10))`. Row-block names on the run env arrive prefixed (`combat.hand` etc.) — `_entset_logical_name` already strips to `"hand"`, so `rows` keys are IDENTICAL across envs; verify, don't assume (a lane premise to test). `checkpoints.make_model` passes `combat_action_layout(MAX_POTIONS)` for `env_kind=="combat"`, `run_action_layout()` for `"run"`/`"column"`.
- Consumes: Tasks 1-3.

- [ ] **Step 1: Failing tests**: construct via `checkpoints.make_model` for both env kinds (the real construction path, not hand-rolled args); assert 243-wide logits; repeat the hand-swap equivariance test on a run-env obs **in combat phase** (drive `STS2RunEnv` with masked-random actions until `request.kind == COMBAT` — seed-fixed, bounded steps, and if combat is not reached within the bound, fail loudly rather than skip); assert CHOICE/SELECT/POTION logits are unchanged under that swap.
- [ ] **Step 2: RED. Step 3: implement. Step 4: PASS.**
- [ ] **Step 5:** Verify-not-assume check from Interfaces: print/assert `set(rows)` for a run-env obs contains `"hand"`, `"enemies"`, `"potions"`, and also the run-native blocks (`"run.deck"`, `"select.candidates"`, …) under their own names.
- [ ] **Step 6:** Controller: full suite.

### Task 5: Honest checkpoint refusal (`head_version`)

**Files:**
- Modify: `sts2_rl/models.py` (`ENTSET_HEAD_VERSION = 2` with a docstring explaining version 1 = positional Linear era), `sts2_rl/checkpoints.py` (`check_checkpoint`), `train_torch.py` (`checkpoint_payload`)
- Test: extend the existing checkpoint-guard test file (find via `rg "_V4_GENERATION_MIN_SCHEMA" test/`)

**Interfaces:**
- Produces: payloads carry `head_version`; `check_checkpoint` refuses when `payload.get("head_version", 1) != models.ENTSET_HEAD_VERSION` for entset, with a message naming `--fresh`, BEFORE the shape-tuple fallback can fire.
- Consumes: nothing structural.

- [ ] **Step 1: Failing tests**: (a) a synthetic payload without `head_version` is refused with the honest message; (b) a payload with `head_version=2` and matching everything passes; (c) save→load round-trip through `checkpoint_payload` + `check_checkpoint` on a freshly built entset agent succeeds. Mirror the existing guard tests' fixture style (they already build minimal payloads for the schema-999 monkeypatch test).
- [ ] **Step 2: RED. Step 3: implement. Step 4: PASS. Step 5:** Controller: full suite.

### Task 6: PPO smoke — the whole stack trains

**Files:**
- Test: extend/add `test/test_train_smoke*.py` (find the existing smoke pattern via `rg "train_torch" test/` and mirror it; if none exists, add one that imports the update path rather than shelling out)

- [ ] **Step 1:** A CPU test per env kind: tiny config (2 envs, 8 steps, 1 iteration), run rollout + one PPO update end to end; assert losses finite, no NaN in grads, `get_action_and_value(obs, mask, action=stored)` path exercised (that's the ratio/clip path the head must serve). Combat env for real; run env bounded the same way as Task 4 (loud failure, no unattended long rollout — the hang gate).
- [ ] **Step 2:** PASS; controller full suite. This closes phase 2 core.

### Task 7: Docs + ledger for phase 2 core

**Files:**
- Modify: `RL_ARCHITECTURE.md` (the model-side doc OBS_SCHEMA.md names as companion), `docs/superpowers/plans/2026-08-01-entity-obs-schema.md` (append a phase-2 section: decisions 1-6 above, measured shapes, suite count), `prompts/entity-obs-schema-phase2-CONTINUE.md` gets a one-line pointer at top if it stays the entry point.
- No code. Controller may do this inline rather than dispatching.

### Task 8 (R8): Pointer head for content-carrying run decisions

Scope per the prompt's own list — **reward cards, shop entries, select candidates, map nodes**, plus the out-of-combat potion belt (same mechanism, rows exist). EVENT and REST are explicitly NOT in scope: their options carry no content rows in the observation (verified 2026-08-02, action-space map §3), the prompt's R8 list omits them, and adding content rows would be schema work — if a lane believes otherwise it must stop and report, not widen.

**Entry gate (read-only pre-task):** read `sts2_rl/driver.py` and pin, with a test, the CHOICE-slot index ↔ observation-row correspondence for SHOP (how option index maps onto `shop.cards`(7)/`shop.relics`(3)/`shop.potions`(3)/removal) and REWARD_* — the action-space map flagged this as unverified (its §6 item 6). Do not build the shop pointer before this is pinned.

**Files:**
- Modify: `sts2_rl/action_heads.py` (add `PointerHead` — single-set variant: `forward(rows (...,N,d), ctx) -> (...,N)`, same ctx-projection pattern), `sts2_rl/models.py` (`ActionLayout` gains `pointer: tuple[PointerSpec, ...]` where `PointerSpec = (base, width, row_block, projection_key)`; run layout maps SELECT→`select.candidates` rows, POTION belt→`run.potions`, and the CHOICE block becomes **decision-kind-routed**: map slots→a learned projection of the `map{m}` float rows, shop/reward slots→their id rows per the pinned correspondence; slots serving EVENT/REST keep the positional Linear as a fallback *within the same logit assembly* — one mechanism per slot-kind, selected by the phase one-hot… **Design note:** the model cannot switch weights on `request.kind` at runtime cheaply — score CHOICE slot i as `positional_logit_i + pointer_logit_i` where pointer_logit_i comes from whichever content row block is populated (all others are PAD → zero rows → the pointer term contributes its zero-row score). Lane must test that a shop obs leaves map/reward pointer terms inert and vice versa.)
- Test: `test/test_pointer_run_decisions.py`

Steps follow the same RED→GREEN→mutation→full-suite cycle as Tasks 2-4; the load-bearing new tests are per-decision equivariance (swap two shop card slots' rows → those two CHOICE logits swap; swap two select candidates → SELECT logits swap) and the cross-phase inertness test above. `MAX_SELECT_CANDIDATES` stays 96 (settled; do not re-open).

### Task 9 (R9): Pair features into the tied head

**Files:**
- Modify: `sts2_rl/models.py` (run/combat layout: play pairs gain `pair_dim` features), `test/test_tied_head_combat.py` (extend)

The damage matrix (`damage_matrix` segment, 60 floats, aligned 1:1 with play(h,e) — `full_env.py` ~999-1018) reshapes to `(...,10,6,1)` and feeds `PairPointerHead(pair=...)` for the play block. The per-enemy incoming previews (enemies.f fields 18-23) broadcast across the source axis as 6 more pair features → `pair_dim=7`. It is a single scalar per pair (per-hit, clipped) — the richer per-pair tuple does NOT exist and building it is out of scope (action-space map §6 item 7); do not compute new previews.
Tests: zeroing the damage-matrix slice of the obs changes play logits (pair path live, mutation-checked); non-play logits untouched; equivariance tests still pass with pair features on (the Task 3 enemy-swap test already swaps damage-matrix columns — verify it still holds).

### Task 10 (R10): Shared-encoder A/B — measured, within-stack

Two arms, one variable apart: (A) today's separate actor/critic `_EntsetEncoder`s; (B) one shared encoder instance (or shared embedding tables, separate row projections — pick ONE sharing granularity and state it), separate trunks in both arms.
- Add `--shared-encoder` flag to `train_torch.py`/`make_model`, stamped into the payload.
- Measure: throughput (sps, same machine, no CPU contention, both arms same seeds/config) on the COMBAT env; a short paired-seed stability check (loss curves finite/comparable over a small fixed budget). Run-env arm is best-effort only (the hang gate); absence of a run-env number is recorded, not papered over.
- Keep arm B **only** on a throughput win with no stability regression; otherwise delete the flag and record the numbers in the ledger. Either way the numbers go in the ledger. This is the only A/B this project runs; no old-env figures.

---

## Self-review notes (spec coverage)

- Prompt phase-2 encoder bullet: satisfied by Task 1 + the pre-existing entset encoder (the prompt's "current einsum" premise is stale — the live arch pools by multiply-sum, not einsum; recorded in the ledger, no einsum work needed). Attention over enemies: deliberately NOT built (prompt: "only with a measured win" — no measurement exists; note it as deferred).
- Tied head bullet: Tasks 2-4. Masking contract: Tasks 3, 6. R8: Task 8 (scoped to the prompt's own list). R9: Task 9. R10: Task 10. Checkpoint honesty: Task 5. Docs: Task 7.
- Known type-consistency seams: `ActionLayout` field set changes in Task 8 (`pointer` added) — Task 8 owns updating `combat_action_layout`/`run_action_layout` construction sites and Task 3/4 tests' fixtures.
