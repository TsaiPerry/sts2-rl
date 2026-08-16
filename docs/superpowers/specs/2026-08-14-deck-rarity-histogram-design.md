# Final-deck rarity histogram (eval.py `--deck-hist`)

2026-08-14

## Problem

`eval.py`'s run-scale report says how *far* a policy gets and which cards it is
offered and takes (`.cards.csv`, plan v7 Task 8), but nothing says what the
policy's deck actually *looks like* when the run ends. Take-rate is exposure,
not composition: a card taken once and then never removed, a card taken four
times, and a card the policy is never offered all read differently in a deck
census than in an offer/take table.

This adds that census: over N evaluated runs, the frequency of every non-starter
card in the final deck, presented as one histogram per rarity.

## Scope

**In:** the run-scale envs (`--env run` / `--env column`), which are the only
ones that have a deck at all. CSV output only.

**Out:** the combat envs, the printed report table, `--compare`, and any
training-time (`train_torch.py`) logging.

## What is counted

One row per (policy, rarity, card). A row's `copies` is the total number of
copies of that card summed over every evaluated episode's final deck.

- **Upgrades fold.** `Bash` and `Bash+` are the same row; upgrade state is not
  recorded. The key is the card's Python class name (`type(card).__name__`),
  which is invariant under `Card.upgrade()` (`sts2_rl/cards/base.py:289-291`).
- **Class name, not snake id.** `"CleaveCard"`, matching the `card` column of
  the existing `.cards.csv` offer/take table, so the two files join in a
  spreadsheet.
- **Every terminal episode contributes**, whether it ended in a win, a death,
  or a step-limit truncation. The deck at the moment the run ended is the deck
  that gets counted.

### Exclusions

| Category | Predicate | Source |
|---|---|---|
| Starter cards | `card.id in set(run.character.starting_deck)` | `sts2_rl/characters.py:65` |
| Colorless | `card.id in set(COLORLESS_POOL)` | `sts2_rl/cards/pool.py:39-51` |
| Curse | `card.card_type is CardType.CURSE` | `sts2_rl/cards/base.py:15-21` |
| Quest | `card.card_type is CardType.QUEST` | same |
| Everything else | `card.rarity not in KEPT_RARITIES` | `sts2_rl/cards/base.py:24-34` |

`KEPT_RARITIES = (CardRarity.COMMON, CardRarity.UNCOMMON, CardRarity.RARE)` —
exactly three histogram blocks. `BASIC`, `ANCIENT`, `TOKEN`, `STATUS`, `EVENT`,
`CURSE` and `QUEST` all fall out on that last check; the curse/quest and
starter/colorless predicates above are kept anyway because they are the
*stated* exclusions and must not silently depend on a rarity coincidence.

The starter check reads `run.character.starting_deck` rather than testing for
`CardRarity.BASIC`. Both isolate Strike/Defend/Bash for the Ironclad today, but
only the id-set generalizes when another character is trained.

## Architecture

Four layers, each independently testable.

### 1. `sts2_rl/deck_stats.py` (new) — the classifier

```python
def final_deck_histogram(run) -> dict[str, dict[str, int]]:
    """rarity value -> {card class name -> copies} for a finished run's deck,
    excluding starter, colorless, curse and quest cards."""
```

Pure function of a `RunState`. Returns nested plain `dict`s (rarity keys are
the `CardRarity` *values*, i.e. `"common"`), so the result is picklable across
the vec-env boundary like the existing `ep_card_offer_ids` counters. A rarity
with no surviving cards is omitted rather than emitted empty.

A separate module rather than a `run_env.py` private: `run_env.py` is already
large, and the classification is the part most likely to need editing when a
new character lands.

### 2. `sts2_rl/run_env.py` — emit it

In `_info()` (`run_env.py:1624-1660`), inside the existing terminal-episode
block that already emits `ep_card_offer_ids` / `ep_card_take_ids`:

```python
info["ep_final_deck"] = final_deck_histogram(run)
```

`run` is already bound at the top of `_info()`, and `self._run` is never
cleared on termination, so the deck is intact at the moment the key is written.
Guarded for `run is None` the same way the surrounding code is.

### 3. `sts2_rl/evaluation.py` — aggregate it

`RunEvalReport` gains one field, alongside `card_offer_counts` /
`card_take_counts_raw` (`evaluation.py:265-266`):

```python
deck_rarity_counts: dict[str, dict[str, int]] = field(default_factory=dict)
```

`evaluate_run` merges `info.get("ep_final_deck", {})` per episode, at
`evaluation.py:602-605` where the other per-card dicts are merged. Defaulting
to `{}` keeps reports built from envs that emit no such key (hand-built test
doubles, the combat envs) constructible, matching every other optional field on
the class.

A `deck_histogram` property produces the export-ready rows:

```python
@property
def deck_histogram(self) -> list[tuple[str, str, int, float, float]]:
    """(rarity, card, copies, share_of_rarity, copies_per_run), rarity blocks
    in COMMON/UNCOMMON/RARE order, cards descending by copies then by name."""
```

`share_of_rarity` is `copies / (total copies in that rarity)` — pooled over
episodes like every other rate on the class, `0.0` on an empty rarity.
`copies_per_run` is `copies / report.episodes`, `0.0` when `episodes` is 0.
Ties break on card name so the output is deterministic.

### 4. `eval.py` — the CLI

`--deck-hist`, opt-in, no printed output:

- `parser.error` if given outside `--env run/column`, or with `--compare`,
  matching how `--reward-hist` / `--csv` are already validated
  (`eval.py:570-574`).
- `parser.error` if given without `--csv` — the flag has no output of its own.
- When on, `evaluate_run_scale` calls `write_deck_csv(f"{stem}.deck.csv", rows)`
  next to the existing `.episodes` / `.hist` / `.cards` writes, and adds one
  `wrote <path>` line.

`DECK_CSV_FIELDS = ("policy", "rarity", "card", "copies", "share_of_rarity",
"copies_per_run")`, named for the existing `CARDS_CSV_FIELDS` /
`HIST_CSV_FIELDS` convention. `write_deck_csv(path_or_file, rows)` mirrors
`write_cards_csv`'s signature exactly, including the "path or open file"
handling, so it is testable without touching disk.

Sample:

```
policy,rarity,card,copies,share_of_rarity,copies_per_run
runs/x.pt (entity, iter 700),common,CleaveCard,412,0.081,4.12
runs/x.pt (entity, iter 700),common,ClotheslineCard,388,0.076,3.88
runs/x.pt (entity, iter 700),uncommon,InflameCard,97,0.112,0.97
runs/x.pt (entity, iter 700),rare,DemonFormCard,14,0.203,0.14
```

## Testing

Following the patterns already in the suite:

1. **`test/test_deck_stats.py` (new)** — `final_deck_histogram` on hand-built
   decks: a starter card, a colorless card, a curse, a quest card and a token
   are each excluded; an upgraded and un-upgraded copy of the same card fold
   into one count of 2; rarities land in the right buckets; an all-excluded
   deck yields `{}`.
2. **`test/test_run_env.py`** — `ep_final_deck` is present in `info` on a
   terminal episode and absent mid-episode, mirroring
   `test_rest_tallies_are_reported_and_reset_per_episode` (`:277`).
3. **`test/test_v7_rewards.py`** — `RunEvalReport(deck_rarity_counts=...)`
   fixture drives `deck_histogram`: ordering, `share_of_rarity` summing to 1.0
   within a rarity, `copies_per_run`, and the zero-episode guard. Mirrors
   `test_run_eval_report_potion_rate_and_card_counts` (`:97`).
4. **Wherever `write_cards_csv` is currently covered** — `write_deck_csv` into
   a `StringIO`: header plus row content, mirroring that test.
5. **CLI validation** — `--deck-hist` without `--csv`, and with `--env full`,
   both `parser.error`.

## Non-goals

- No per-episode deck rows. The census is pooled over the evaluation; a
  per-episode deck dump would be a much larger file answering a different
  question, and can be added later from the same `ep_final_deck` key.
- No printed histogram. The report table is already long, and this data is
  wide enough that a spreadsheet is the right reader.
- No pick-rate ("share of runs containing at least one copy") column. Total
  copies is the requested metric; the raw per-episode data needed for pick-rate
  is not retained by the pooled aggregate.
