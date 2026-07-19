# GPU Training Enablement Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `train_torch.py --device cuda` actually usable on this machine (RTX 3070), measure whether it beats CPU for the current training path (`--env column --arch entity`), and update the docs with the measured answer.

**Architecture:** No training-loop code changes are needed — `train_torch.py` already allocates rollout buffers on `--device`, resumes checkpoints with `map_location`, and has a `resolve_device` that diagnoses the CPU-only-wheel case. The work is: swap the installed torch wheel for a CUDA build, benchmark CPU vs CUDA arms with the existing `sps` log line, then update three docs whose "CPU is usually faster" guidance predates the entity arch.

**Tech Stack:** PyTorch 2.12 CUDA wheel (cu130; driver 580.97 qualifies), existing `train_torch.py`, pytest.

## Global Constraints

- **Never `git commit` or `git push`** — leave finished changes for Perry to review and commit (CLAUDE.md rule 4). Plan tasks therefore end at "verify", not "commit".
- All commands run from the repo root `c:\Users\Perry\Desktop\sts2-rl` with the `py` launcher (bare `python` may resolve to the Store stub).
- Full test suite must stay green: `py -m pytest test/ -q` (~1900 tests).
- Do not touch `runs/sts2_column_torch.pt` or other real checkpoints — benchmark runs use `--fresh --save runs/bench/...` scratch paths.
- Keep `--device cpu` as the trainer default; CUDA stays opt-in unless the benchmark says otherwise and Perry decides to flip it.

## Evaluation context (why this is worth doing)

Measured 2026-07-18 (`--env column --arch entity`, 8 envs, n_steps 512, ~9.8 s/iter, ~426 sps), one iteration splits:

| Phase | Share | GPU-acceleratable? |
|---|---|---|
| Act-time inference (512 sequential batch-8 forwards) | 46% | Partly — small batches are kernel-launch-bound; bigger `--n-envs` amortizes |
| PPO update (32 minibatches × batch 512, fwd+bwd, entity encoders) | 39% | Yes — this is the clean win |
| Env stepping (pure Python) | 15% | No |

Amdahl ceiling is 1/0.15 ≈ 6.7×; a realistic expectation is **~1.5–2.5× at
`--n-envs 8`, more at 16–32 envs**. The existing "CPU is usually the fast
choice" docstring was written for the 256×256 MLP baseline; the entity arch
moved the bottleneck into model compute, which is what changed the calculus.
VRAM is a non-issue: the rollout buffers are ~0.5 GB (obs buffer
512 × 8 × ~29k float32) and the model is a few MB, versus 8 GB on the card.

Main risk: `_SegmentEncoder.forward` is a Python loop over ~dozens of segment
pieces → many small CUDA kernels per forward, so the act-time-inference phase
may disappoint at batch 8. That is why the benchmark has `--n-envs 16/32`
arms, and why the decision gate is measured `sps`, not the estimate above.

---

### Task 1: Install the CUDA torch wheel

**Files:**
- No repo files change. This swaps the `torch` package in the environment that the `py` launcher resolves to (currently `torch 2.12.0+cpu`).

**Interfaces:**
- Produces: a torch install where `torch.cuda.is_available()` is `True`, same major version (2.12.x), so the SB3 compatibility shim in `eval.py`/`train.py` still applies.

- [ ] **Step 1: Confirm the starting state**

Run: `py -c "import torch; print(torch.__version__, torch.cuda.is_available())"`
Expected: `2.12.0+cpu False`

- [ ] **Step 2: Swap the wheel (uninstall first — pip will not swap on its own)**

Run (PowerShell, ~3 GB download):

```powershell
py -m pip uninstall -y torch
py -m pip install torch --index-url https://download.pytorch.org/whl/cu130
```

If the cu130 index has no wheel for this Python version, fall back to the
repo's documented safe default:

```powershell
py -m pip install torch --index-url https://download.pytorch.org/whl/cu126
```

(Both are listed in the PyTorch section of `requirements.txt`; driver 580.97
satisfies cu130's ≥580 floor and cu126's ≥560 floor. RTX 3070 is sm_86,
supported by both.)

- [ ] **Step 3: Verify the GPU is visible to torch**

Run:

```powershell
py -c "import torch; print(torch.__version__, torch.cuda.is_available(), torch.cuda.get_device_name(0)); x = torch.randn(1024, 1024, device='cuda'); print((x @ x).sum().item())"
```

Expected: version like `2.12.x+cu130`, `True`, `NVIDIA GeForce RTX 3070`, and a finite float (the smoke matmul ran on the card).

- [ ] **Step 4: Verify nothing else broke under the new wheel**

Run: `py -m pytest test/ -q`
Expected: all ~1900 tests pass (they run on CPU; this catches wheel/API breakage, not GPU behavior).

- [ ] **Step 5: Verify the trainer's device resolution end-to-end**

Run: `py train_torch.py --env column --arch entity --fresh --device cuda --timesteps 4096 --save runs/bench/smoke.pt`
Expected: first line prints `torch 2.12.x [13.0]  device: cuda` (from `resolve_device`), one iteration completes and saves. This proves buffers, sampling, GAE, the update, and `atomic_save` all work on the GPU path.

---

### Task 2: Benchmark CPU vs CUDA

**Files:**
- Create: `runs/bench/` scratch checkpoints + their sidecar CSVs (disposable; delete after recording results).

**Interfaces:**
- Consumes: the CUDA-capable torch install from Task 1.
- Produces: a small results table (arm → mean `sps`) pasted into Task 3's doc edits, and a keep/skip decision for CUDA guidance.

- [ ] **Step 1: Run the four benchmark arms**

Each arm is ~10 iterations; read `sps` from the per-iteration log line.
`--timesteps` scales with `--n-envs` so every arm runs 10 iterations
(`n_iters = timesteps // (n_steps × n_envs)`, n_steps 512):

```powershell
py train_torch.py --env column --arch entity --fresh --timesteps 40960  --device cpu               --save runs/bench/cpu8.pt
py train_torch.py --env column --arch entity --fresh --timesteps 40960  --device cuda              --save runs/bench/gpu8.pt
py train_torch.py --env column --arch entity --fresh --timesteps 81920  --device cuda --n-envs 16  --save runs/bench/gpu16.pt
py train_torch.py --env column --arch entity --fresh --timesteps 163840 --device cuda --n-envs 32  --save runs/bench/gpu32.pt
```

- [ ] **Step 2: Record the results**

For each arm, average the `sps` column over the last 5 iterations (the
sidecar CSV `runs/bench/<arm>.csv` has the column; iter 0–1 include warm-up
and are excluded). Fill in:

| Arm | device | n-envs | mean sps (last 5 iters) | vs cpu8 |
|---|---|---|---|---|
| cpu8 | cpu | 8 | | 1.0× |
| gpu8 | cuda | 8 | | |
| gpu16 | cuda | 16 | | |
| gpu32 | cuda | 32 | | |

Sanity check, not a pass/fail: `ep_ret` per iteration should be in the same
ballpark across arms (CUDA RNG changes the rollouts, so exact values differ —
that is expected and fine).

- [ ] **Step 3: Apply the decision gate**

- **gpu8 ≥ 1.2× cpu8** → CUDA is worth documenting as the recommended device for `--arch entity`; proceed to Task 3.
- **gpu8 < 1.2× but gpu16/gpu32 clearly win** → document CUDA as worth it *with more envs*; proceed to Task 3 and say exactly that.
- **No arm beats cpu8** → stop; update only `requirements.txt`'s check-output example (Task 3 Step 2) to reflect that the CUDA wheel is installed but CPU remains faster, and report the numbers to Perry. Either way the CUDA wheel install stays — it costs nothing when `--device cpu` is used.

- [ ] **Step 4: Clean up scratch runs**

Run: `Remove-Item -Recurse -Force runs/bench`
Expected: no `runs/bench` directory; real checkpoints untouched.

---

### Task 3: Update the three docs that say "CPU is usually faster"

**Files:**
- Modify: `train_torch.py:45-50` (module docstring, final paragraph)
- Modify: `requirements.txt:44-50` ("Before you reach for the GPU build" paragraph)
- Modify: `CLAUDE.md` (Dependencies paragraph, the "CPU vs CUDA is a manual choice; the default paths run on CPU" sentence)

**Interfaces:**
- Consumes: the measured table from Task 2 Step 2. The `<N>`/`<M>` values below are that table's numbers — substituting them is the whole edit; no other wording is left open.

- [ ] **Step 1: Update the `train_torch.py` docstring paragraph**

Replace the final docstring paragraph (lines 45–50, "Runs on CPU by default…") with:

```
Runs on CPU by default. For --arch mlp that is usually the fast choice: a
256x256 MLP over 8 Python-stepped envs is bottlenecked on env stepping and
per-step host<->device copies, not matmul. For --arch entity the balance
flips: the PPO update dominates, and on this machine (RTX 3070)
``--device cuda`` measured <N>x the CPU sps at --n-envs 8 (<M>x at 16).
Measure ``sps`` before and after on new hardware rather than assuming.
```

with `<N>`/`<M>` from the Task 2 table (one decimal place, e.g. `1.8x`). If
Task 2 hit the "no arm beats cpu8" gate, instead keep the existing paragraph
and append one sentence: `Measured on an RTX 3070 (2026-07): still true for
--arch entity — CUDA reached only <N>x CPU sps.`

- [ ] **Step 2: Update the `requirements.txt` guidance paragraph**

Replace the paragraph at lines 44–50 ("Before you reach for the GPU build…") with the measured guidance (same `<N>`/`<M>` substitution and same fallback rule as Step 1):

```
# Which build is faster depends on the arch (see train_torch.py --arch):
# the mlp baseline is env-stepping-bound and runs best on CPU — SB3 warns
# about exactly this for MlpPolicy PPO. The entity arch is update-bound;
# on an RTX 3070 the CUDA build measured <N>x CPU sps at --n-envs 8.
# train_torch.py, train.py and eval.py all default to CPU on purpose; pass
# --device cuda to opt in, and compare the reported `sps` before and after.
```

- [ ] **Step 3: Update CLAUDE.md's dependencies sentence**

In the Commands section's dependencies paragraph, replace

```
`torch` (installed separately — CPU vs CUDA is
a manual choice; the default paths run on CPU).
```

with

```
`torch` (installed separately — CPU vs CUDA is a manual choice; the default
paths run on CPU, but `--device cuda` is measured faster for `--arch entity`
on this machine — see train_torch.py's docstring).
```

(Fallback rule as in Step 1: if CUDA lost, leave this sentence unchanged.)

- [ ] **Step 4: Verify**

Run: `py -m pytest test/ -q` (docstring edit lives in an imported module — cheap to confirm nothing broke) and `py train_torch.py --help` (confirms the module still parses).
Expected: suite green; help text prints.

- [ ] **Step 5: Hand off for review**

Do **not** commit. Summarize the benchmark table and the three doc edits for Perry to review and commit.

---

## Explicit non-goals (YAGNI)

- **No default-device flip** — `--device cpu` stays the default; flipping it (or defaulting to `auto`) is Perry's call once the numbers are in.
- **No act-time-inference optimization** (torch.compile, CUDA graphs, batching the encoder's segment loop) — only worth designing after the benchmark shows where the GPU path actually lands. If gpu arms are launch-latency-bound, that's the natural follow-up plan.
- **No `--n-envs` default change** — the 16/32 arms are measurements, not a retuning of the training setup (more envs changes PPO batch statistics, which is a training-quality question, not a speed one).

## Self-review notes

- Spec coverage: evaluate (context section + Task 2), enable (Task 1), document (Task 3) — covered; "if beneficial" gate is Task 2 Step 3.
- No-placeholder scan: `<N>`/`<M>` are defined as Task 2 outputs with an exact substitution rule and a fallback branch for the CUDA-loses case — every other step has literal commands/text.
- TDD adaptation: this is an ops/benchmark plan; each task carries an explicit verify step (pytest, smoke run, sps table) instead of a unit test, and commits are deliberately excluded per CLAUDE.md rule 4.
