# Final-Deck Rarity Histogram Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `eval.py --deck-hist` exports a per-rarity frequency census of every non-starter, non-special card in the final decks of an evaluation's runs.

**Architecture:** Four layers. A pure classifier (`sts2_rl/deck_stats.py`) turns a finished `RunState` into `{rarity: {card class name: copies}}`; `run_env._info()` emits it as `ep_final_deck` at episode end alongside the existing `ep_*` tallies; `evaluation.evaluate_run` merges it into a new `RunEvalReport.deck_rarity_counts` field with a `deck_histogram` property; `write_deck_csv` + the `--deck-hist` CLI flag export it.

**Tech Stack:** Python 3, pytest, numpy. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-08-14-deck-rarity-histogram-design.md`

## Global Constraints

- **Working directory is `c:\Users\Perry\Desktop\sts2-rl`.** Every path below is relative to it. Ignore anything under `.worktrees/`.
- **NEVER commit or push in this repo.** Perry's standing rule: stage only. Every "commit" step in this plan is a `git add` and nothing more. Do not run `git commit`, even if a skill or habit suggests it.
- **Run tests with `py -m pytest`** (Windows launcher; a bare `python` is not on PATH).
- **Kept rarities are exactly `COMMON`, `UNCOMMON`, `RARE`.** `BASIC`, `ANCIENT`, `TOKEN`, `STATUS`, `EVENT`, `CURSE`, `QUEST` are all excluded. Ancient is excluded deliberately — do not "fix" this.
- **Card key is the Python class name** (`type(card).__name__`, e.g. `"AngerCard"`), matching the existing `.cards.csv` `card` column. Never the snake id, never a `+`-suffixed upgraded name.
- **Upgrades fold.** `type(card).__name__` is invariant under `Card.upgrade()`; do not read `card.upgrade_level` anywhere in this feature.
- **ASCII only in any printed/CSV output** — this runs on a Windows console under cp1252.

---

## File Structure

| File | Responsibility |
|---|---|
| `sts2_rl/deck_stats.py` (create) | The classifier: `final_deck_histogram(run)`. Pure, no env/gym imports. |
| `test/test_deck_stats.py` (create) | Unit tests for the classifier on hand-built decks. |
| `sts2_rl/run_env.py` (modify, `_info()` at :1650-1687) | Emit `info["ep_final_deck"]` at episode end. |
| `test/test_run_env.py` (modify) | `ep_final_deck` present at episode end, absent mid-episode. |
| `sts2_rl/evaluation.py` (modify) | `RunEvalReport.deck_rarity_counts` field, merge in `evaluate_run`, `deck_histogram` property, `DECK_CSV_FIELDS`, `write_deck_csv`. |
| `test/test_v7_rewards.py` (modify) | Report aggregation + CSV writer tests, next to the existing `write_cards_csv` test. |
| `eval.py` (modify) | `--deck-hist` flag, validation, the extra write, docstring line. |

---

### Task 1: The classifier

**Files:**
- Create: `sts2_rl/deck_stats.py`
- Test: `test/test_deck_stats.py` (create)

**Interfaces:**
- Consumes: nothing from earlier tasks. Uses `sts2_rl.cards` (`CardRarity`, `CardType`), `sts2_rl.cards.pool.COLORLESS_POOL`, and a `RunState`-shaped object exposing `.deck: list[Card]` and `.character.starting_deck: tuple[str, ...]`.
- Produces: `final_deck_histogram(run) -> dict[str, dict[str, int]]` and the module constant `KEPT_RARITIES: tuple[CardRarity, ...]`. Task 2 calls the function; Task 3's tests reuse the shape.

Facts you need (already verified — do not re-derive):
- `make_card(card_id)` is importable from `sts2_rl.cards` and builds a card by snake id.
- Fixture ids and their class names / rarities: `strike`→`StrikeCard`/basic, `anger`→`AngerCard`/common, `inflame`→`InflameCard`/uncommon, `demon_form`→`DemonFormCard`/rare, `break`→`BreakCard`/ancient, `finesse`→`FinesseCard`/uncommon **but colorless**, `clumsy`→`ClumsyCard`/curse, `byrdonis_egg`→`ByrdonisEggCard`/quest, `burn`→`BurnCard`/status.
- `Card` exposes class attributes `id` (snake), `rarity: CardRarity`, `card_type: CardType`, and `upgrade()` which mutates only `upgrade_level`.
- Ironclad's `starting_deck` is `("strike",)*5 + ("defend",)*4 + ("bash",)`.

- [ ] **Step 1: Write the failing test**

Create `test/test_deck_stats.py`:

```python
"""final_deck_histogram: the end-of-run deck census behind eval.py --deck-hist.

The exclusions (starter / colorless / curse / quest) and the kept-rarity set
are the whole contract, so each one gets its own assertion here rather than
being inferred from a full-run integration test.
"""
from types import SimpleNamespace

from sts2_rl.cards import make_card
from sts2_rl.characters import get_character
from sts2_rl.deck_stats import final_deck_histogram


def _run(*card_ids, character="ironclad"):
    """A RunState-shaped double: the classifier only reads .deck/.character."""
    return SimpleNamespace(
        deck=[make_card(cid) for cid in card_ids],
        character=get_character(character),
    )


def test_counts_kept_rarities_by_class_name():
    hist = final_deck_histogram(_run("anger", "anger", "inflame", "demon_form"))
    assert hist == {
        "common": {"AngerCard": 2},
        "uncommon": {"InflameCard": 1},
        "rare": {"DemonFormCard": 1},
    }


def test_upgraded_copies_fold_into_one_entry():
    run = _run("anger", "anger")
    run.deck[0].upgrade()
    hist = final_deck_histogram(run)
    assert hist == {"common": {"AngerCard": 2}}


def test_starter_cards_excluded():
    # Every id in the character's starting deck, plus one real card.
    hist = final_deck_histogram(_run("strike", "defend", "bash", "anger"))
    assert hist == {"common": {"AngerCard": 1}}


def test_colorless_curse_quest_and_off_rarity_excluded():
    # finesse is uncommon BUT colorless, so rarity alone would let it through.
    hist = final_deck_histogram(
        _run("finesse", "clumsy", "byrdonis_egg", "burn", "break", "anger"))
    assert hist == {"common": {"AngerCard": 1}}


def test_all_excluded_deck_is_empty_not_padded():
    # No empty-rarity keys: a rarity with nothing in it is omitted entirely.
    assert final_deck_histogram(_run("strike", "clumsy")) == {}


def test_empty_deck():
    assert final_deck_histogram(_run()) == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -m pytest test/test_deck_stats.py -q`
Expected: collection error — `ModuleNotFoundError: No module named 'sts2_rl.deck_stats'`.

- [ ] **Step 3: Write minimal implementation**

Create `sts2_rl/deck_stats.py`:

```python
"""End-of-run deck census — the data behind eval.py's ``--deck-hist``.

Kept deliberately out of ``run_env.py`` (already large) and out of
``evaluation.py`` (which imports no card content): this is the one place that
decides what counts as a "card the policy chose to run", and it is the file
that needs editing when a new character lands.
"""
from __future__ import annotations

from typing import Any

from .cards import CardRarity, CardType
from .cards.pool import COLORLESS_POOL

#: The rarities that get a histogram block. BASIC (the starting Strike/
#: Defend/Bash), ANCIENT, TOKEN, STATUS, EVENT, CURSE and QUEST are all
#: excluded: none of them is a card the policy picked out of a reward screen.
KEPT_RARITIES: tuple[CardRarity, ...] = (
    CardRarity.COMMON, CardRarity.UNCOMMON, CardRarity.RARE,
)

_COLORLESS_IDS = frozenset(COLORLESS_POOL)


def final_deck_histogram(run: Any) -> dict[str, dict[str, int]]:
    """``{rarity value: {card class name: copies}}`` for a finished run's deck.

    Excludes starter cards (the character's own ``starting_deck`` ids —
    character-general, unlike a ``CardRarity.BASIC`` test), colorless cards,
    curses and quest cards, then keeps only ``KEPT_RARITIES``. That last
    filter would already catch curses and quests today; the explicit
    ``card_type`` check is kept because they are the *stated* exclusions and
    must not rest on a rarity coincidence.

    The card key is the Python class name, matching the ``card`` column of
    the offer/take ``.cards.csv``, so the two exports join. It is invariant
    under ``Card.upgrade()``, so upgraded and un-upgraded copies fold into one
    count.

    Returns plain nested dicts (rarity keys are ``CardRarity`` *values*), so
    the result crosses the vec-env ``info`` boundary like the existing
    ``ep_card_offer_ids`` counters. A rarity with no surviving cards is
    omitted rather than emitted empty.
    """
    starter_ids = frozenset(run.character.starting_deck)
    hist: dict[str, dict[str, int]] = {}
    for card in run.deck:
        if card.id in starter_ids or card.id in _COLORLESS_IDS:
            continue
        if card.card_type in (CardType.CURSE, CardType.QUEST):
            continue
        if card.rarity not in KEPT_RARITIES:
            continue
        bucket = hist.setdefault(card.rarity.value, {})
        name = type(card).__name__
        bucket[name] = bucket.get(name, 0) + 1
    return hist
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -m pytest test/test_deck_stats.py -q`
Expected: `6 passed`.

- [ ] **Step 5: Stage (NO COMMIT — see Global Constraints)**

```bash
git add sts2_rl/deck_stats.py test/test_deck_stats.py
```

---

### Task 2: Emit `ep_final_deck` from the run env

**Files:**
- Modify: `sts2_rl/run_env.py` (imports near the top; `_info()` at :1650-1687)
- Test: `test/test_run_env.py` (append)

**Interfaces:**
- Consumes: `final_deck_histogram` from Task 1.
- Produces: `info["ep_final_deck"]: dict[str, dict[str, int]]`, present only on the episode's last step (termination or `_steps >= _max_steps`), consumed by Task 3.

Facts you need: `_info()` binds `run = self._run` on its first line and `self._run` is never cleared on termination, so the deck is intact. The episode-end block already ends with `info["ep_card_take_ids"] = dict(self._ep_card_take_ids)` at :1686, immediately before `return info`.

- [ ] **Step 1: Write the failing test**

Append to `test/test_run_env.py` (it already imports `STS2RunEnv` and `numpy as np`; add imports only if the file lacks them):

```python
def test_ep_final_deck_reported_at_episode_end_only():
    """The deck census rides the same episode-end block as the ep_* tallies."""
    env = STS2RunEnv()
    env.reset(seed=0)
    mid_info = {}
    term = trunc = False
    for _ in range(20_000):
        mask = env.action_masks()
        a = int(np.flatnonzero(mask)[0])
        _, _, term, trunc, info = env.step(a)
        if term or trunc:
            break
        mid_info = info
    assert term or trunc, "episode never ended in 20k steps -- repin"
    # Mid-episode steps carry no census (it is an end-of-run measurement).
    assert "ep_final_deck" not in mid_info
    deck = info["ep_final_deck"]
    assert isinstance(deck, dict)
    assert set(deck) <= {"common", "uncommon", "rare"}
    for cards in deck.values():
        assert cards, "an emitted rarity must not be empty"
        assert all(isinstance(k, str) and isinstance(v, int)
                   for k, v in cards.items())
    # Starters are excluded, so a first-legal run that dies early is empty.
    assert "StrikeCard" not in {c for cards in deck.values() for c in cards}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -m pytest test/test_run_env.py::test_ep_final_deck_reported_at_episode_end_only -q`
Expected: FAIL with `KeyError: 'ep_final_deck'`.

- [ ] **Step 3: Write minimal implementation**

In `sts2_rl/run_env.py`, add to the existing relative imports near the top of the file (keep the block's existing ordering style):

```python
from .deck_stats import final_deck_histogram
```

Then in `_info()`, insert one line immediately after `info["ep_card_take_ids"] = dict(self._ep_card_take_ids)` (:1686) and before `return info`:

```python
            # The end-of-run deck census (eval.py --deck-hist). `run` is
            # bound at the top of this method and `self._run` is never
            # cleared on termination, so the deck here is the deck the
            # episode finished with.
            info["ep_final_deck"] = final_deck_histogram(run)
```

Mind the indentation: it belongs inside the `if self._result is not None or self._steps >= self._max_steps:` block (12 spaces).

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -m pytest test/test_run_env.py -q`
Expected: all pass, including the new test.

Then confirm nothing else broke: `py -m pytest test/test_v7_rewards.py test/test_behavior_metrics.py -q`
Expected: all pass.

- [ ] **Step 5: Stage (NO COMMIT)**

```bash
git add sts2_rl/run_env.py test/test_run_env.py
```

---

### Task 3: Aggregate it on `RunEvalReport`

**Files:**
- Modify: `sts2_rl/evaluation.py` (`RunEvalReport` fields at :265-266; the `deck_histogram` property near `card_take_counts` at :467-471; `evaluate_run`'s locals ~:536-537, merge loop :602-605, and constructor call :638-639)
- Test: `test/test_v7_rewards.py` (append)

**Interfaces:**
- Consumes: `info["ep_final_deck"]` from Task 2.
- Produces:
  - `RunEvalReport.deck_rarity_counts: dict[str, dict[str, int]]` (keyword field, defaults to `{}`)
  - `RunEvalReport.deck_histogram -> list[tuple[str, str, int, float, float]]` — rows of `(rarity, card, copies, share_of_rarity, copies_per_run)`.

  Task 4 consumes `deck_histogram` only.

- [ ] **Step 1: Write the failing test**

Append to `test/test_v7_rewards.py`:

```python
def test_run_eval_report_deck_histogram():
    from sts2_rl.evaluation import RunEvalReport

    report = RunEvalReport(
        episodes=2, floors=(5, 9), acts=(0, 0), victories=(False, False),
        truncations=(False, False), hp_left=(0, 0), decisions=(10, 12),
        deck_rarity_counts={
            "rare": {"DemonFormCard": 1},
            "common": {"AngerCard": 3, "ArmamentsCard": 1},
            "uncommon": {"InflameCard": 2},
        },
    )
    # Rarity blocks in COMMON/UNCOMMON/RARE order (not the dict's insertion
    # order, not alphabetical); cards descending by copies inside a block.
    assert report.deck_histogram == [
        ("common", "AngerCard", 3, 0.75, 1.5),
        ("common", "ArmamentsCard", 1, 0.25, 0.5),
        ("uncommon", "InflameCard", 2, 1.0, 1.0),
        ("rare", "DemonFormCard", 1, 1.0, 0.5),
    ]

    empty = RunEvalReport(
        episodes=1, floors=(1,), acts=(0,), victories=(False,),
        truncations=(False,), hp_left=(0,), decisions=(1,))
    assert empty.deck_histogram == []


def test_deck_histogram_ties_break_on_card_name():
    from sts2_rl.evaluation import RunEvalReport

    report = RunEvalReport(
        episodes=1, floors=(1,), acts=(0,), victories=(False,),
        truncations=(False,), hp_left=(0,), decisions=(1,),
        deck_rarity_counts={"common": {"ZzzCard": 2, "AaaCard": 2}},
    )
    assert [row[1] for row in report.deck_histogram] == ["AaaCard", "ZzzCard"]


def test_deck_histogram_zero_episodes_does_not_divide_by_zero():
    from sts2_rl.evaluation import RunEvalReport

    report = RunEvalReport(
        episodes=0, floors=(), acts=(), victories=(), truncations=(),
        hp_left=(), decisions=(),
        deck_rarity_counts={"common": {"AngerCard": 3}},
    )
    assert report.deck_histogram == [("common", "AngerCard", 3, 1.0, 0.0)]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -m pytest test/test_v7_rewards.py -q -k deck_histogram`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'deck_rarity_counts'`.

- [ ] **Step 3: Write minimal implementation**

**3a.** In `sts2_rl/evaluation.py`, add the field right after `card_take_counts_raw` (:266), inside `RunEvalReport`:

```python
    # Merged over all episodes: rarity value -> {card class name -> copies}
    # in the deck each run ENDED with (sts2_rl.deck_stats). Starter,
    # colorless, curse and quest cards are already filtered out upstream.
    deck_rarity_counts: dict[str, dict[str, int]] = field(default_factory=dict)
```

**3b.** Add the property next to `card_take_counts` (after :471):

```python
    @property
    def deck_histogram(self) -> list[tuple[str, str, int, float, float]]:
        """``(rarity, card, copies, share_of_rarity, copies_per_run)`` rows.

        Rarity blocks come out in COMMON/UNCOMMON/RARE order (the drop-tier
        order a reader expects, not the dict's insertion order); inside a
        block, cards descend by copies with ties broken on name so the export
        is deterministic.

        ``share_of_rarity`` is pooled over episodes like every other rate on
        this class — copies / that rarity's total copies. ``copies_per_run``
        divides by ``episodes``; 0.0 rather than a ZeroDivisionError on a
        report built with no episodes.
        """
        order = ("common", "uncommon", "rare")
        rows: list[tuple[str, str, int, float, float]] = []
        for rarity in order:
            cards = self.deck_rarity_counts.get(rarity)
            if not cards:
                continue
            total = sum(cards.values())
            for name, copies in sorted(cards.items(), key=lambda kv: (-kv[1], kv[0])):
                rows.append((
                    rarity,
                    name,
                    copies,
                    copies / total if total else 0.0,
                    copies / self.episodes if self.episodes else 0.0,
                ))
        return rows
```

**3c.** In `evaluate_run`, add a local next to `card_take_counts` (:537):

```python
    deck_rarity_counts: dict[str, dict[str, int]] = {}
```

**3d.** In `evaluate_run`'s per-episode merge, after the `ep_card_take_ids` loop (:604-605):

```python
        for rarity, cards in info.get("ep_final_deck", {}).items():
            bucket = deck_rarity_counts.setdefault(rarity, {})
            for name, count in cards.items():
                bucket[name] = bucket.get(name, 0) + int(count)
```

**3e.** In the `RunEvalReport(...)` construction, after `card_take_counts_raw=card_take_counts,` (:639):

```python
        deck_rarity_counts=deck_rarity_counts,
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -m pytest test/test_v7_rewards.py test/test_run_env.py -q`
Expected: all pass.

- [ ] **Step 5: Stage (NO COMMIT)**

```bash
git add sts2_rl/evaluation.py test/test_v7_rewards.py
```

---

### Task 4: The CSV writer

**Files:**
- Modify: `sts2_rl/evaluation.py` (`CARDS_CSV_FIELDS` at :660; `write_cards_csv` at :757-775)
- Test: `test/test_v7_rewards.py` (append)

**Interfaces:**
- Consumes: `RunEvalReport.deck_histogram` from Task 3.
- Produces: `DECK_CSV_FIELDS: tuple[str, ...]` and `write_deck_csv(path_or_file, rows) -> None`, where `rows: Sequence[tuple[str, RunEvalReport]]` — the same `(policy name, report)` pair list `write_cards_csv` takes. Task 5 calls `write_deck_csv`.

- [ ] **Step 1: Write the failing test**

Append to `test/test_v7_rewards.py`:

```python
def test_write_deck_csv():
    import io

    from sts2_rl.evaluation import RunEvalReport, write_deck_csv

    report = RunEvalReport(
        episodes=2, floors=(5, 9), acts=(0, 0), victories=(False, False),
        truncations=(False, False), hp_left=(0, 0), decisions=(10, 12),
        deck_rarity_counts={
            "common": {"AngerCard": 3, "ArmamentsCard": 1},
            "rare": {"DemonFormCard": 1},
        },
    )
    buf = io.StringIO()
    write_deck_csv(buf, [("p", report)])
    rows = buf.getvalue().strip().splitlines()
    assert rows[0] == "policy,rarity,card,copies,share_of_rarity,copies_per_run"
    assert rows[1] == "p,common,AngerCard,3,0.75,1.5"
    assert rows[2] == "p,common,ArmamentsCard,1,0.25,0.5"
    assert rows[3] == "p,rare,DemonFormCard,1,1.0,0.5"

    # A report with no census writes the header and nothing else.
    empty = RunEvalReport(
        episodes=1, floors=(1,), acts=(0,), victories=(False,),
        truncations=(False,), hp_left=(0,), decisions=(1,))
    buf2 = io.StringIO()
    write_deck_csv(buf2, [("p", empty)])
    assert buf2.getvalue().strip().splitlines() == [
        "policy,rarity,card,copies,share_of_rarity,copies_per_run"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -m pytest test/test_v7_rewards.py::test_write_deck_csv -q`
Expected: FAIL with `ImportError: cannot import name 'write_deck_csv'`.

- [ ] **Step 3: Write minimal implementation**

In `sts2_rl/evaluation.py`, add next to `CARDS_CSV_FIELDS` (:660):

```python
DECK_CSV_FIELDS = ("policy", "rarity", "card", "copies", "share_of_rarity",
                   "copies_per_run")
```

And add this function immediately after `write_cards_csv` (after :775):

```python
def write_deck_csv(
    path_or_file, rows: Sequence[tuple[str, RunEvalReport]]
) -> None:
    """Final-deck rarity census: one row per (policy, rarity, card).

    Rarity blocks in COMMON/UNCOMMON/RARE order, cards descending by copies
    inside each block (see `RunEvalReport.deck_histogram`) — so each block
    reads as its own histogram and the whole file pivots in a spreadsheet.
    Starter, colorless, curse and quest cards were filtered out upstream in
    `sts2_rl.deck_stats`, and upgraded copies are folded into their base card.

    ``path_or_file`` is a filesystem path or an open text file, matching
    `write_cards_csv`."""
    def _write(fh) -> None:
        writer = csv.writer(fh)
        writer.writerow(DECK_CSV_FIELDS)
        for name, report in rows:
            for rarity, card, copies, share, per_run in report.deck_histogram:
                writer.writerow([name, rarity, card, copies,
                                 round(share, 6), round(per_run, 6)])

    if hasattr(path_or_file, "write"):
        _write(path_or_file)
    else:
        with open(path_or_file, "w", newline="") as fh:
            _write(fh)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -m pytest test/test_v7_rewards.py -q`
Expected: all pass.

- [ ] **Step 5: Stage (NO COMMIT)**

```bash
git add sts2_rl/evaluation.py test/test_v7_rewards.py
```

---

### Task 5: The `--deck-hist` CLI flag

**Files:**
- Modify: `eval.py` (module docstring :28-37; `evaluate_run_scale` signature :354-366 and its CSV block :452-459; the argparse block :544-565; validation :570-574; the `evaluate_run_scale(...)` call :602-604)
- Test: `test/test_run_env.py` (append — this is where CLI-shaped checks on the eval harness live)

**Interfaces:**
- Consumes: `write_deck_csv` from Task 4.
- Produces: the user-facing flag. Nothing downstream consumes it.

Behavior: `--deck-hist` requires `--csv` and `--env run|column`, and is rejected with `--compare`. When on, `<stem>.deck.csv` is written next to the existing three CSVs and one `wrote <path>` line is printed. Nothing is added to the report table.

- [ ] **Step 1: Write the failing test**

Append to `test/test_run_env.py`:

```python
def test_deck_hist_writes_a_csv_next_to_the_others(tmp_path):
    """eval.py's --deck-hist path: the writer + naming, without a checkpoint.

    evaluate_run_scale needs a model to produce rows, so this exercises the
    naming/writing contract directly on the same helper the CLI calls."""
    from sts2_rl.evaluation import RunEvalReport, write_deck_csv

    report = RunEvalReport(
        episodes=1, floors=(3,), acts=(0,), victories=(False,),
        truncations=(False,), hp_left=(0,), decisions=(4,),
        deck_rarity_counts={"common": {"AngerCard": 2}},
    )
    path = tmp_path / "out.deck.csv"
    write_deck_csv(str(path), [("p", report)])
    text = path.read_text().strip().splitlines()
    assert text[0].startswith("policy,rarity,card")
    assert text[1] == "p,common,AngerCard,2,1.0,2.0"


def test_eval_cli_rejects_deck_hist_without_csv():
    """--deck-hist has no output of its own, so it must not silently no-op."""
    import subprocess
    import sys

    proc = subprocess.run(
        [sys.executable, "eval.py", "runs/nonexistent.pt", "--env", "run",
         "--deck-hist"],
        capture_output=True, text=True)
    assert proc.returncode != 0
    assert "--deck-hist" in proc.stderr and "--csv" in proc.stderr


def test_eval_cli_rejects_deck_hist_on_combat_env():
    import subprocess
    import sys

    # No --csv here on purpose: with it, the shared run-scale-only loop would
    # reject --csv first and this test would pass for the wrong reason.
    proc = subprocess.run(
        [sys.executable, "eval.py", "--env", "full", "--baselines",
         "--deck-hist"],
        capture_output=True, text=True)
    assert proc.returncode != 0
    assert "--deck-hist" in proc.stderr and "run/column" in proc.stderr
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -m pytest test/test_run_env.py -q -k deck_hist`
Expected: the two CLI tests FAIL — `eval.py` exits 2 with `unrecognized arguments: --deck-hist`, so the `"--csv" in proc.stderr` assertion fails.

- [ ] **Step 3: Write minimal implementation**

**5a.** Import the writer — extend the existing `from sts2_rl.evaluation import (...)` block in `eval.py` (:45-61) with `write_deck_csv` (keep the block alphabetically sorted: it goes after `write_cards_csv`).

**5b.** Add the argparse flag after `--csv` (:548-553):

```python
    parser.add_argument("--deck-hist", action="store_true",
                        help="run/column envs only, requires --csv: also export "
                             "PATH.deck.csv — the final-deck card-frequency "
                             "census, one histogram block per rarity "
                             "(common/uncommon/rare). Starter, colorless, curse "
                             "and quest cards are excluded and upgraded copies "
                             "fold into their base card")
```

**5c.** Extend the existing run-scale-only validation loop (:570-574) so `--deck-hist` is rejected on the combat envs and with `--compare` — add it to the tuple:

```python
        for flag, value in (("--reward-hist", args.reward_hist),
                            ("--csv", args.csv),
                            ("--deck-hist", args.deck_hist)):
```

**5d.** Add the requires-`--csv` check immediately after that loop:

```python
    # --deck-hist has no output of its own (no printed histogram), so without
    # --csv it would silently do nothing.
    if args.deck_hist and not args.csv:
        parser.error("--deck-hist writes PATH.deck.csv; pass --csv PATH too")
```

**5e.** Thread the flag into `evaluate_run_scale` — add a parameter at the end of its signature (:354-366):

```python
    deck_hist: bool = False,
```

and pass it at the call site (:602-604), appending `args.deck_hist` as the last argument.

**5f.** In `evaluate_run_scale`'s CSV block (:452-459), write the extra file and report it:

```python
    if csv_path is not None:
        ep_path, hist_path = write_run_csv(csv_path, rows)
        stem = csv_path[:-4] if csv_path.lower().endswith(".csv") else csv_path
        cards_path = f"{stem}.cards.csv"
        write_cards_csv(cards_path, rows)
        print(f"\nwrote {ep_path} ({sum(r.episodes for _, r in rows)} episode rows)"
              f"\nwrote {hist_path}"
              f"\nwrote {cards_path}")
        if deck_hist:
            deck_path = f"{stem}.deck.csv"
            write_deck_csv(deck_path, rows)
            print(f"wrote {deck_path}")
```

**5g.** Document it in the module docstring — add one usage line after the `--csv` line (:13):

```
    py eval.py runs/x.pt --env column --csv out --deck-hist  # + out.deck.csv
```

and a sentence at the end of the run-scale paragraph (after the `--csv` sentence, :36-37):

```
``--deck-hist`` (with ``--csv``) adds ``PATH.deck.csv``: how often every card
ended up in the deck, one histogram block per rarity, with starter, colorless,
curse and quest cards excluded.
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -m pytest test/test_run_env.py -q -k deck_hist`
Expected: 3 passed.

Then check the flag is wired: `py eval.py --help`
Expected: `--deck-hist` appears in the output with its help text.

- [ ] **Step 5: Run the full affected suite**

Run: `py -m pytest test/test_run_env.py test/test_v7_rewards.py test/test_deck_stats.py test/test_behavior_metrics.py -q`
Expected: all pass.

- [ ] **Step 6: Stage (NO COMMIT)**

```bash
git add eval.py test/test_run_env.py
```

---

### Task 6: End-to-end verification

**Files:** none modified. This task only runs things.

**Interfaces:** consumes everything above.

- [ ] **Step 1: Find a checkpoint to evaluate**

Run: `ls runs/*.pt`
If there is no `.pt` checkpoint, skip Step 2 and say so in the report rather than inventing a result.

- [ ] **Step 2: Run a real eval end to end**

Run (substituting the checkpoint found above):

```bash
py eval.py runs/<checkpoint>.pt --env run --episodes 5 --deck-hist --csv "C:/Users/Perry/AppData/Local/Temp/claude/c--Users-Perry-Desktop-Slay-the-Spire-2/70f488c4-c91b-42d4-8e88-0a33f0a43c5b/scratchpad/deckcheck"
```

Expected: the usual report table, then four `wrote ...` lines ending with `...deckcheck.deck.csv`. Open that file and confirm: the header matches `DECK_CSV_FIELDS`; rarity values are only `common`/`uncommon`/`rare`; no `StrikeCard`/`DefendCard`/`BashCard` row exists; each rarity block's `share_of_rarity` column sums to ~1.0.

If the census is entirely empty (an early-dying policy never picks up a card), re-run with `--episodes 20` before concluding anything is wrong.

- [ ] **Step 3: Run the full test suite**

Run: `py -m pytest test/ -q`
Expected: no NEW failures. Note: this repo has 4 pre-existing failures in `test_train_io` unrelated to this work — record the count and confirm it is unchanged, do not try to fix them.

- [ ] **Step 4: Stage anything outstanding (NO COMMIT)**

```bash
git status --short
git add -u sts2_rl/ test/ eval.py
```

---

## Self-Review Notes

Spec coverage check: classifier + exclusions (Task 1) · `ep_final_deck` emission (Task 2) · report field, merge, `deck_histogram` ordering/shares (Task 3) · `DECK_CSV_FIELDS` + `write_deck_csv` (Task 4) · `--deck-hist` flag, both validation rules, docstring (Task 5) · end-to-end (Task 6). The spec's five listed tests map onto Tasks 1-5. Non-goals (no per-episode rows, no printed histogram, no pick-rate column) are respected — nothing in this plan prints a histogram or retains per-episode deck data.
