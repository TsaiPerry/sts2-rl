"""Tests for `tools/merge_distill.py` — merging parallel search-worker parts.

The bug class this tool exists to make impossible is the one caught in the
08-28 v26 diagnosis: an ad-hoc merge snippet built `merged_from` out of SHALLOW
copies of each part's provenance, so summing into the merged `stats` dict
mutated the very per-part records that were supposed to preserve what each
worker did. Half of these tests are about the arithmetic; the other half are
about independence and about refusing directories that must never be merged.
"""

import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import merge_distill as md              # noqa: E402
from tools.search_worker import SHARD_KEYS         # noqa: E402


# ════════════════════════════════════════════════════════════════════════════
# Fixture helpers — tiny synthetic part dirs
# ════════════════════════════════════════════════════════════════════════════

def test_shard_keys_duplicate_stays_in_sync():
    """`md._SHARD_KEYS` is a deliberate copy of search_worker's, kept local so
    importing merge_distill never drags in the sim. Nothing but this assert
    keeps the two from drifting apart."""
    assert md._SHARD_KEYS == tuple(SHARD_KEYS)


F_DIM, I_DIM, N_ACTIONS, K = 4, 3, 6, 2


def write_shard(path: Path, n: int, first: float = 0.0) -> None:
    """An `n`-record shard carrying all five contract arrays."""
    f = np.zeros((n, F_DIM), dtype=np.float16)
    f[:, 0] = first
    np.savez(
        path,
        f=f,
        i=np.zeros((n, I_DIM), dtype=np.int32),
        mask=np.ones((n, N_ACTIONS), dtype=np.int8),
        tgt_idx=np.zeros((n, K), dtype=np.int32),
        tgt_p=np.full((n, K), 0.5, dtype=np.float16),
    )


def make_part(root: Path, name: str, *, shards=(2, 2), seed=1, bank="bankA",
              ckpt="ckpt.pt", records=None, **prov_over) -> Path:
    """A synthetic part dir: `len(shards)` npz files + a provenance.json.

    `shards` is the per-shard record count. Shard filenames are the producer's
    (`shard_0000.npz`, ...) so every part collides with every other, which is
    what the rename has to survive.
    """
    part = root / name
    part.mkdir(parents=True)
    names = []
    for idx, n in enumerate(shards):
        fn = f"shard_{idx:04d}.npz"
        write_shard(part / fn, n, first=float(seed))
        names.append(fn)
    total = sum(shards)
    prov = {
        "distill_schema": 1,
        "ckpt": ckpt,
        "bank": bank,
        "k": K,
        "m": 8,
        "obs_schema": 13,
        "card_obs": "hybrid",
        "temperature": 0.5,
        "seed": seed,
        "shards": names,
        "records": total if records is None else records,
        "stats": {
            "fights": 2, "decisions": 10, "searched": total,
            "flips": 1, "collect_seconds": 1.5,
            "room_hist": {"combat": 3, "elite": 1},
        },
    }
    prov.update(prov_over)
    (part / "provenance.json").write_text(json.dumps(prov, indent=2),
                                          encoding="utf-8")
    return part


# ════════════════════════════════════════════════════════════════════════════
# Arithmetic
# ════════════════════════════════════════════════════════════════════════════


def test_merge_sums_records_stats_and_room_hist(tmp_path):
    a = make_part(tmp_path, "a", shards=(2, 2), seed=1)
    b = make_part(tmp_path, "b", shards=(2,), seed=2)
    out = tmp_path / "merged"

    prov = md.merge_distill([str(a), str(b)], str(out))

    assert prov["records"] == 6
    assert prov["stats"]["searched"] == 6
    assert prov["stats"]["fights"] == 4
    assert prov["stats"]["decisions"] == 20
    assert prov["stats"]["flips"] == 2
    assert prov["stats"]["collect_seconds"] == pytest.approx(3.0)
    assert prov["stats"]["room_hist"] == {"combat": 6, "elite": 2}


def test_merged_provenance_keeps_the_shared_generator_stamp(tmp_path):
    a = make_part(tmp_path, "a")
    b = make_part(tmp_path, "b", seed=2)
    prov = md.merge_distill([str(a), str(b)], str(tmp_path / "merged"))
    for key, want in (("obs_schema", 13), ("card_obs", "hybrid"),
                      ("k", K), ("temperature", 0.5), ("ckpt", "ckpt.pt")):
        assert prov[key] == want


def test_merged_bank_describes_every_distinct_source_bank(tmp_path):
    a = make_part(tmp_path, "a", bank="bankA")
    b = make_part(tmp_path, "b", bank="bankB", seed=2)
    prov = md.merge_distill([str(a), str(b)], str(tmp_path / "merged"))
    assert "bankA" in prov["bank"] and "bankB" in prov["bank"]


def test_merged_from_records_each_part(tmp_path):
    a = make_part(tmp_path, "a", seed=1, bank="bankA")
    b = make_part(tmp_path, "b", seed=2, bank="bankB")
    prov = md.merge_distill([str(a), str(b)], str(tmp_path / "merged"))

    assert len(prov["merged_from"]) == 2
    assert [e["seed"] for e in prov["merged_from"]] == [1, 2]
    assert [e["bank"] for e in prov["merged_from"]] == ["bankA", "bankB"]
    assert all(set(e) >= {"part", "bank", "seed", "stats"}
               for e in prov["merged_from"])
    assert prov["merged_from"][0]["stats"]["fights"] == 2


# ════════════════════════════════════════════════════════════════════════════
# Deep-copy independence — the exact 08-28 aliasing bug
# ════════════════════════════════════════════════════════════════════════════


def test_mutating_the_merged_stats_leaves_merged_from_intact(tmp_path):
    a = make_part(tmp_path, "a")
    b = make_part(tmp_path, "b", seed=2)
    prov = md.merge_distill([str(a), str(b)], str(tmp_path / "merged"))

    prov["stats"]["fights"] = 999999
    prov["stats"]["room_hist"]["combat"] = 999999
    prov["stats"]["room_hist"]["new_key"] = 1

    for entry in prov["merged_from"]:
        assert entry["stats"]["fights"] == 2
        assert entry["stats"]["room_hist"] == {"combat": 3, "elite": 1}


def test_merged_from_entries_are_independent_of_each_other(tmp_path):
    a = make_part(tmp_path, "a")
    b = make_part(tmp_path, "b", seed=2)
    prov = md.merge_distill([str(a), str(b)], str(tmp_path / "merged"))

    prov["merged_from"][0]["stats"]["room_hist"]["combat"] = -1
    assert prov["merged_from"][1]["stats"]["room_hist"]["combat"] == 3


def test_the_written_provenance_matches_the_returned_one(tmp_path):
    a = make_part(tmp_path, "a")
    b = make_part(tmp_path, "b", seed=2)
    out = tmp_path / "merged"
    prov = md.merge_distill([str(a), str(b)], str(out))
    on_disk = json.loads((out / "provenance.json").read_text(encoding="utf-8"))
    assert on_disk == prov


# ════════════════════════════════════════════════════════════════════════════
# Renaming
# ════════════════════════════════════════════════════════════════════════════


def test_rename_is_collision_free_across_identically_named_shards(tmp_path):
    a = make_part(tmp_path, "a", shards=(2, 2), seed=1)
    b = make_part(tmp_path, "b", shards=(2, 2), seed=2)
    out = tmp_path / "merged"

    prov = md.merge_distill([str(a), str(b)], str(out))

    on_disk = sorted(p.name for p in out.iterdir() if p.suffix == ".npz")
    assert on_disk == ["p0-shard_0000.npz", "p0-shard_0001.npz",
                       "p1-shard_0000.npz", "p1-shard_0001.npz"]
    assert sorted(prov["shards"]) == on_disk
    assert len(set(prov["shards"])) == 4


def test_the_merged_dir_loads_as_a_shard_set_with_every_record(tmp_path):
    from tools.search_worker import iter_shards

    a = make_part(tmp_path, "a", shards=(2, 2), seed=1)
    b = make_part(tmp_path, "b", shards=(2,), seed=2)
    out = tmp_path / "merged"
    md.merge_distill([str(a), str(b)], str(out))

    shards = list(iter_shards(out))
    assert len(shards) == 3
    assert sum(sh["f"].shape[0] for sh in shards) == 6
    assert all(set(SHARD_KEYS) <= set(sh) for sh in shards)


# ════════════════════════════════════════════════════════════════════════════
# Refusals
# ════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("key, bad", [
    ("ckpt", "other.pt"),
    ("obs_schema", 12),
    ("card_obs", "features"),
    ("k", 3),
    ("temperature", 1.0),
])
def test_a_generator_mismatch_is_fatal(tmp_path, key, bad):
    a = make_part(tmp_path, "a")
    b = make_part(tmp_path, "b", seed=2, **{key: bad})
    out = tmp_path / "merged"
    with pytest.raises(SystemExit) as exc:
        md.merge_distill([str(a), str(b)], str(out))
    assert key in str(exc.value)
    assert not (out / "provenance.json").exists()


def test_a_min_score_gap_mismatch_is_fatal(tmp_path):
    """A filtered part and an unfiltered one are not two halves of one dataset:
    the merged stamp could only claim one of the two, and the trainer would
    then be told a decisiveness distribution the records do not have."""
    a = make_part(tmp_path, "a", min_score_gap=0.05)
    b = make_part(tmp_path, "b", seed=2, min_score_gap=0.0)
    out = tmp_path / "merged"
    with pytest.raises(SystemExit) as exc:
        md.merge_distill([str(a), str(b)], str(out))
    assert "min_score_gap" in str(exc.value)
    assert not (out / "provenance.json").exists()


def test_a_missing_min_score_gap_reads_as_unfiltered(tmp_path):
    """Backward compat: parts written before Task 4b carry no `min_score_gap`
    key, and those runs kept every searched decision — i.e. 0.0. A pre-4b part
    must still merge with an explicitly unfiltered post-4b one."""
    a = make_part(tmp_path, "a")                            # key absent
    b = make_part(tmp_path, "b", seed=2, min_score_gap=0.0)  # key present, 0.0
    prov = md.merge_distill([str(a), str(b)], str(tmp_path / "merged"))
    assert prov["records"] == 8


def test_a_missing_min_score_gap_still_refuses_a_filtered_part(tmp_path):
    """Both orderings, because part 0 is the reference every other part is
    compared against."""
    a = make_part(tmp_path, "a")                             # absent -> 0.0
    b = make_part(tmp_path, "b", seed=2, min_score_gap=0.05)
    with pytest.raises(SystemExit) as exc:
        md.merge_distill([str(a), str(b)], str(tmp_path / "m1"))
    assert "min_score_gap" in str(exc.value)

    c = make_part(tmp_path, "c", min_score_gap=0.05)
    d = make_part(tmp_path, "d", seed=2)                     # absent -> 0.0
    with pytest.raises(SystemExit) as exc:
        md.merge_distill([str(c), str(d)], str(tmp_path / "m2"))
    assert "min_score_gap" in str(exc.value)


def test_matching_min_score_gaps_merge(tmp_path):
    a = make_part(tmp_path, "a", min_score_gap=0.05)
    b = make_part(tmp_path, "b", seed=2, min_score_gap=0.05)
    prov = md.merge_distill([str(a), str(b)], str(tmp_path / "merged"))
    assert prov["min_score_gap"] == 0.05


def test_a_record_count_mismatch_is_fatal(tmp_path):
    a = make_part(tmp_path, "a", shards=(2, 2))
    b = make_part(tmp_path, "b", shards=(2,), seed=2, records=99)
    with pytest.raises(SystemExit) as exc:
        md.merge_distill([str(a), str(b)], str(tmp_path / "merged"))
    msg = str(exc.value)
    assert "99" in msg and "records" in msg


def test_an_empty_part_list_is_fatal(tmp_path):
    with pytest.raises(SystemExit):
        md.merge_distill([], str(tmp_path / "merged"))


def test_a_missing_provenance_is_fatal(tmp_path):
    a = make_part(tmp_path, "a")
    (a / "provenance.json").unlink()
    with pytest.raises(SystemExit) as exc:
        md.merge_distill([str(a)], str(tmp_path / "merged"))
    assert "provenance.json" in str(exc.value)


def test_a_missing_shard_file_is_fatal(tmp_path):
    a = make_part(tmp_path, "a", shards=(2, 2))
    (a / "shard_0001.npz").unlink()
    with pytest.raises(SystemExit) as exc:
        md.merge_distill([str(a)], str(tmp_path / "merged"))
    assert "shard_0001.npz" in str(exc.value)


# ════════════════════════════════════════════════════════════════════════════
# CLI
# ════════════════════════════════════════════════════════════════════════════


def test_cli_merges_the_named_parts(tmp_path):
    a = make_part(tmp_path, "a", shards=(2,))
    b = make_part(tmp_path, "b", shards=(2,), seed=2)
    out = tmp_path / "merged"
    md.main([str(a), str(b), "--out", str(out)])
    prov = json.loads((out / "provenance.json").read_text(encoding="utf-8"))
    assert prov["records"] == 4
    assert len(prov["shards"]) == 2
