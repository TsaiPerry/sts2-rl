# Prompt: Pay down known fidelity debts vs the real game

Copy everything below into a fresh session. Scope is large; it splits into
independent workstreams — you can run this prompt several times, telling the
session which workstream(s) to take, or let it go in the listed order.

---

In `c:\Users\Perry\Desktop\sts2-rl` (pure-Python Slay the Spire 2 simulator +
RL envs). The decompiled game source at `c:\Users\Perry\Desktop\Slay the
Spire 2` is the fidelity source of truth: where the sim disagrees with the
source, fix the sim and update legacy tests — never preserve old sim
semantics.

## Situation

`CLAUDE.md`'s "Known gaps vs. the real game" section lists deliberate
approximations and stubs. Many were stubbed because the run layer didn't
exist yet — it does now (`run.py`: act sequencing, gold, map, deck edits,
rewards, rest, shops), so a batch of them are newly implementable. Work
through them source-first: for each item, read the game's implementation,
port the behavior, add behavior tests, and strike the item from `CLAUDE.md`'s
gap list.

## Workstream A — out-of-combat relic stubs (highest value)

The run layer can now support these. For each relic, find its class in the
game source (`src/Core/Models/Relics/`) and port the hook. Known stubs
(from `CLAUDE.md` — re-check the current list, it may have moved):

- **Maw Bank** — gold on floor climb (and its deactivation condition).
- **Dream Catcher** — card reward when resting.
- **Sword of Stone** — elite-kill counter and payoff.
- **Darkstone Periapt** — Max HP on gaining a curse.
- **Tungsten Rod** — reduce HP loss (must also apply to *event* HP loss:
  requires the run-level HP-loss path to dispatch relic hooks; check how
  events currently deduct HP in `run.py`/`events/`).
- **Hand Drill**, **Petrified Toad** (potion behavior), **Unsettling Lamp**,
  **Fragrant Mushroom**, **Pollinous Core** — check each against source.
- **Sling of Courage / Pantograph** — room-type gating (needs the current
  room type visible to combat hooks; the run layer knows it).

Pattern to follow: run-level hooks dispatch duck-typed over `run.relics` (see
`_map_listeners()` in `run.py` and the reward/room hooks in `rewards.py`).
Combat-side hooks live in `hooks.py` / relic classes.

## Workstream B — combat↔run reward plumbing

These need a channel for a combat (or combat event) to add post-fight
rewards:

- **Punch-Off** (relic/potion), **The Lantern Key** (Lantern Key card),
  **Battleworn Dummy** (potion/upgrade/relic) — combat events whose rewards
  are currently unmodeled. Source: their event classes + how the game queues
  extra rewards onto the reward screen (`RewardsSet.cs` /
  `src/Core/Rewards/`).
- **Thieving Hopper** — killing the hopper must return the stolen card as a
  post-combat reward (source: the Hopper monster model + reward plumbing).
- **Gremlin Merc gold theft** (Thievery/Heist) — the run has gold now; decide
  and implement how combat-side theft debits `run.gold` (the game removes
  gold during combat and returns stolen gold if the thief is killed —
  verify exact behavior in source).

Design once: a small "pending post-combat extras" mechanism on the combat or
run (list of reward entries appended during combat, consumed by
`rewards.py::generate_combat_rewards` / the driver's REWARD phase), then port
all four onto it. `run_env.py`'s REWARD decision phase must surface the extra
entries (check its reward-slot capacity; bump `RUN_OBS_SCHEMA_VERSION` only
if the layout must grow).

## Workstream C — combat-engine boundary fixes

- **Kaiser Crab (Surrounded)** — facing must flip on *targeted card plays*,
  not single-target card damage. Requires the card-play hook to carry the
  target; thread it through `CombatState._resolve_card_play` and update the
  Crab + any other hook users.
- **Attack-command boundary** — `hooks.before_attack`/`after_attack`
  currently brackets monster attacks and player Attack-card plays only;
  non-Attack cards that deal damage bypass it (affects Vigor-style
  consumption). Check the game's definition of an "attack" boundary and align.
- **history.py coverage** — the game's `CombatHistory` records more entry
  types than card plays/exhausts/damage received. Enumerate what powers/
  relics in the ported pools actually query, and add only those (don't build
  speculative plumbing).

## Workstream D — systems consciously deferred (confirm before starting)

Bigger items; each is its own project and may be better left until the
content that needs it is ported: orbs (Defect), character resources (Stars /
Forge / Osty / Doom / summons), the full enchantment system (shop catalogue),
`Sly` and remaining card keywords, separate named RNG streams, Early/Late
hook phases. If told to take one of these, first write a short plan against
the source before coding.

## Constraints (all workstreams)

- Every fix cites its source anchor (file under the decompiled repo) in the
  test or docstring, and gets behavior tests (`test/test_powers.py`,
  `test_new_features.py`, or a new file that fits the suite's layout).
- RNG discipline: one shared `random.Random`; adding draws to combat *setup*
  paths breaks seeded tests — check before reordering rolls.
- Obs/action layout changes require schema-version bumps (`OBS_SCHEMA_VERSION`
  in `full_env.py`, `RUN_OBS_SCHEMA_VERSION` in `run_env.py`) and invalidate
  checkpoints — avoid unless the fix genuinely needs new observation surface.
- `sts2_rl/vocab.json` is frozen/append-only (see `sts2_rl/vocab.py`); new
  cards/relics/events register and append automatically. Never hand-edit.
- After each item: strike it from `CLAUDE.md`'s gap list (or amend it to the
  remaining approximation). Full suite green: `py -m pytest test/ -q`.
