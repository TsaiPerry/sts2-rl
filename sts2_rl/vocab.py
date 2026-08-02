"""Frozen, capacity-padded vocabularies for the training environments.

Problem this solves: the env obs/action layouts are keyed to vocabulary
indices (card id -> one-hot position, select-action row, ...).  If those
lists were rebuilt with ``sorted(registry)`` at import time, porting a single
new card would (a) grow every ``N_*``-sized segment, changing layer shapes,
and (b) shift the index of every id sorting after it, scrambling what the
trained weights mean.  Either alone forces a from-scratch retrain.

Two mechanisms fix that:

* **Frozen, append-only ordering** — the first time a vocabulary is built it
  is persisted to ``vocab.json`` next to this module.  On later imports the
  persisted order is authoritative; ids registered since are *appended*
  (sorted among themselves for determinism) and the file is rewritten.  An id
  that enters the file never moves and is never dropped, even if the class is
  later deleted (its slot just goes dead) — so index *i* means the same thing
  to every checkpoint ever trained.

* **Reserved capacity** — every layout constant (``N_CARDS``, ...) is the
  *capacity* below, not the live count, so obs/action dims stay constant as
  content is ported.  Capacities are sized from the decompiled game source
  (full-game totals, counted 2026-07) plus ~10-15% headroom for patches:

  ==========  =========  ========
  kind        game total capacity
  ==========  =========  ========
  cards       577        640
  relics      298        336
  powers      260        288
  monsters    121        144
  potions     64         80
  events      68         96
  purposes    (sim: 18)  24
  afflictions 7          16
  enchantments 22        32
  ==========  =========  ========

  ``afflictions`` and ``enchantments`` are sized to the game total, not the
  ported count: 7 of 7 afflictions are ported, but only 19 of 22
  enchantments are (``Inky``, ``Momentum``, ``SlumberingEssence`` are not).
  Sizing to 19 would force a schema bump the day one of them lands, which is
  exactly the mistake this module exists to prevent.

  These are documentation, not the source of truth — the live counts are
  ``len(frozen_ids(kind, ...))`` and the capacities are ``CAPACITIES`` below.
  The purposes figure was stale at 14 (measured 18, 2026-08-01); re-measure
  before quoting any of them.

  Slots past the live count are permanently zero in the obs and masked in the
  action space until content lands in them; a policy checkpoint then only
  needs *fine-tuning*, not a retrain.  Exceeding a capacity raises at import
  with instructions (bump + schema bump + retrain — the escape hatch, not the
  norm).

``vocab.json`` is part of the trained-model contract: commit it, and never
hand-reorder it.  Deleting it re-seeds from the current registries, which
breaks index compatibility with existing checkpoints.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterable

VOCAB_PATH = Path(__file__).with_name("vocab.json")

CAPACITIES: dict[str, int] = {
    "cards": 640,
    "relics": 336,
    "powers": 288,
    "monsters": 144,
    "potions": 80,
    "events": 96,
    "purposes": 24,
    "afflictions": 16,
    "enchantments": 32,
}


def capacity(kind: str) -> int:
    return CAPACITIES[kind]


def merge_frozen(frozen: list[str], registered: Iterable[str]) -> tuple[list[str], list[str]]:
    """Merge a persisted (frozen) ordering with the live registry.

    Returns ``(merged, new_ids)`` where ``merged`` is the frozen order with
    ids absent from it appended (sorted among themselves), and ``new_ids``
    are the appended ids.  Frozen ids missing from the registry are *kept*
    (dead slots preserve every later index).
    """
    frozen_set = set(frozen)
    new_ids = sorted(set(registered) - frozen_set)
    return frozen + new_ids, new_ids


def _load(path: Path) -> dict[str, list[str]]:
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _save(path: Path, data: dict[str, list[str]]) -> None:
    # Atomic replace: concurrent vectorized-env workers may race here on a
    # fresh checkout, but the merged content is deterministic, so last-writer
    # -wins is harmless as long as no reader ever sees a half-written file.
    tmp = path.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)
        f.write("\n")
    os.replace(tmp, path)


def frozen_ids(kind: str, registered: Iterable[str], path: Path = VOCAB_PATH) -> list[str]:
    """The stable id list for ``kind``: persisted order + new ids appended.

    Persists any appends back to ``path``.  Raises if the result exceeds the
    reserved capacity.
    """
    data = _load(path)
    merged, new_ids = merge_frozen(data.get(kind, []), registered)
    cap = CAPACITIES[kind]
    if len(merged) > cap:
        raise RuntimeError(
            f"vocabulary '{kind}' has {len(merged)} ids, exceeding its reserved "
            f"capacity {cap}. Bump CAPACITIES['{kind}'] in sts2_rl/vocab.py, "
            f"bump the affected obs schema version(s), and retrain — existing "
            f"checkpoints cannot survive a capacity change.")
    if new_ids:
        data[kind] = merged
        _save(path, data)
    return merged
