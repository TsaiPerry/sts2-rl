"""holdout_bank must (1) keep the snapshot_schema header on every part,
(2) drop exactly the first --skip snapshots of EACH input (the prefix the
batch-1 workers consumed), (3) round-robin the pooled remainder so the parts
are disjoint and exhaustive."""
import json

from tools.holdout_bank import holdout_bank

HDR = '{"snapshot_schema": 1}\n'


def _bank(tmp_path, name, n):
    p = tmp_path / name
    lines = [HDR] + [json.dumps({"bank": name, "idx": i}) + "\n" for i in range(n)]
    p.write_text("".join(lines), encoding="utf-8")
    return str(p)


def _snaps(path):
    with open(path, encoding="utf-8-sig") as fh:
        header = fh.readline()
        return header, [json.loads(ln) for ln in fh if ln.strip()]


def test_holdout_bank_skips_prefix_and_splits_disjoint(tmp_path):
    banks = [_bank(tmp_path, "a.jsonl", 7), _bank(tmp_path, "b.jsonl", 5)]
    outs = holdout_bank(banks, skip=3, parts=2,
                        out_stem=str(tmp_path / "hold"))
    assert outs == [str(tmp_path / "hold.p0.jsonl"),
                    str(tmp_path / "hold.p1.jsonl")]
    h0, s0 = _snaps(outs[0])
    h1, s1 = _snaps(outs[1])
    assert h0 == HDR and h1 == HDR
    got = [(s["bank"], s["idx"]) for s in s0 + s1]
    # survivors: a.jsonl idx 3..6, b.jsonl idx 3..4 - nothing consumed, nothing else
    assert sorted(got) == [("a.jsonl", 3), ("a.jsonl", 4), ("a.jsonl", 5),
                           ("a.jsonl", 6), ("b.jsonl", 3), ("b.jsonl", 4)]
    # round-robin over the pooled order (a's tail then b's tail)
    assert [(s["bank"], s["idx"]) for s in s0] == [("a.jsonl", 3), ("a.jsonl", 5),
                                                   ("b.jsonl", 3)]
    assert [(s["bank"], s["idx"]) for s in s1] == [("a.jsonl", 4), ("a.jsonl", 6),
                                                   ("b.jsonl", 4)]


def test_holdout_bank_refuses_missing_header(tmp_path):
    p = tmp_path / "bad.jsonl"
    p.write_text('{"not_a_header": 1}\n', encoding="utf-8")
    import pytest
    with pytest.raises(SystemExit):
        holdout_bank([str(p)], skip=0, parts=2,
                     out_stem=str(tmp_path / "hold"))


def test_holdout_bank_refuses_skip_swallowing_a_bank(tmp_path):
    banks = [_bank(tmp_path, "a.jsonl", 2)]
    import pytest
    with pytest.raises(SystemExit):
        holdout_bank(banks, skip=5, parts=2, out_stem=str(tmp_path / "hold"))
