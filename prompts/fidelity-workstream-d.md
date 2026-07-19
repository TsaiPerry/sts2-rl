# Prompt: Fidelity Workstream D — consciously deferred systems

Copy everything below into a fresh session. **Confirm with the user which
item to take before starting** — each is its own project and may be better
left until the content that needs it is ported.

(This is the surviving workstream of the retired `prompts/fidelity-debts.md`;
Workstreams A/B/C were implemented and merged on 2026-07-17.)

---

In `c:\Users\Perry\Desktop\sts2-rl` (pure-Python Slay the Spire 2 simulator +
RL envs). The decompiled game source at `c:\Users\Perry\Desktop\Slay the
Spire 2` is the fidelity source of truth: where the sim disagrees with the
source, fix the sim and update legacy tests — never preserve old sim
semantics.

## Deferred systems (pick one; write a short plan against the source first)

- **Orbs** (Defect) — no orb system exists in the sim.
- **Character resources** — Stars, Forge / Sovereign Blade, Osty, Doom,
  summons; only matters once those characters' content is ported.
- **Full enchantment system** — the shop catalogue and general enchantment
  plumbing; the sim models only the event/Neow/Ancient-relic grants
  (`enchantments.py`).
- **`Sly` and remaining card keywords** — beyond
  ethereal/unplayable/exhaust/innate/retain.
- **Separate named RNG streams** — the game rolls monster moves from a
  dedicated seeded `MonsterAi` stream at intent-display time; the sim uses
  one shared `random.Random` per combat (documented convention). Migrating
  breaks every seeded test — plan the test migration explicitly.
- **Early/Late hook phases** — the game's hook dispatch has phase ordering
  the sim flattens.

## Constraints

- Every fix cites its source anchor (file under the decompiled repo) in the
  test or docstring, and gets behavior tests.
- Obs/action layout changes require schema-version bumps
  (`OBS_SCHEMA_VERSION` in `full_env.py`, `RUN_OBS_SCHEMA_VERSION` in
  `run_env.py`) and invalidate checkpoints — avoid unless genuinely needed.
- `sts2_rl/vocab.json` is frozen/append-only; never hand-edit or reorder.
- After each item: update `CLAUDE.md`'s gap list. Full suite green:
  `py -m pytest test/ -q` (1914 tests as of 2026-07-18).
