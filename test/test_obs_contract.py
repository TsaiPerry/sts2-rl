"""Contract tests for ``sts2_rl.obs`` — entity-obs-schema phase 1, task T1.

Pins the shared int/float ``Dict`` observation contract (OBS_SCHEMA.md
Sec.2) before anything else in the repo depends on it: ``oid``'s PAD
convention (Sec.2.1), ``ObsLayout``'s segment-slice arithmetic, ``space()``'s
shapes/dtypes, ``ObsBuffer.write_rows``'s padding + truncate-never-assert
behavior (Sec.2.3) and its ``sort=True`` hidden-information non-leak
property (Sec.5.3).

Run with:  py -m pytest test/test_obs_contract.py -v
"""
from __future__ import annotations

import itertools
import uuid
import warnings

import numpy as np
import pytest

from sts2_rl.obs import PAD, ObsBuffer, ObsLayout, oid


def _unique_name(prefix: str) -> str:
    """A segment name unique to this call, so tests don't share the
    module-level once-per-process warn state with each other."""
    return f"{prefix}.{uuid.uuid4().hex}"


# ---------------------------------------------------------------------------
# 1. oid round-trips
# ---------------------------------------------------------------------------


def test_oid_zero_maps_to_one():
    assert oid(0) == 1


def test_oid_none_maps_to_pad():
    assert oid(None) == PAD == 0


def test_oid_never_maps_a_real_index_to_pad():
    for index in range(0, 10_000):
        assert oid(index) != PAD


def test_oid_is_index_plus_one():
    for index in (0, 1, 2, 41, 999):
        assert oid(index) == index + 1


# ---------------------------------------------------------------------------
# 2. ObsLayout slice arithmetic
# ---------------------------------------------------------------------------


def _sample_layout() -> ObsLayout:
    f_segments = [
        ("player.vitals", 5),
        ("block.f", 4 * 2),  # cap=4, n_float=2
        ("tail.f", 3),
    ]
    i_segments = [
        ("player.identity", 1),
        ("block.ids", 4 * 3),  # cap=4, n_int=3
        ("tail.ids", 2),
    ]
    return ObsLayout(f_segments, i_segments)


def _assert_contiguous_nonoverlapping_and_covers(
    slices: dict[str, slice], segments: list[tuple[str, int]], total: int
) -> None:
    # In segment-declaration order, slices must exactly tile [0, total).
    cursor = 0
    for name, width in segments:
        sl = slices[name]
        assert sl.start == cursor
        assert sl.stop == cursor + width
        cursor += width
    assert cursor == total

    # Non-overlap, checked pairwise as an independent cross-check.
    spans = [(sl.start, sl.stop) for sl in slices.values()]
    for (a_start, a_stop), (b_start, b_stop) in itertools.combinations(spans, 2):
        assert a_stop <= b_start or b_stop <= a_start


def test_layout_f_slices_contiguous_nonoverlapping_and_sum_to_f_dim():
    layout = _sample_layout()
    _assert_contiguous_nonoverlapping_and_covers(
        layout.f_slices, layout.f_segments, layout.f_dim)
    assert layout.f_dim == 5 + 8 + 3


def test_layout_i_slices_contiguous_nonoverlapping_and_sum_to_i_dim():
    layout = _sample_layout()
    _assert_contiguous_nonoverlapping_and_covers(
        layout.i_slices, layout.i_segments, layout.i_dim)
    assert layout.i_dim == 1 + 12 + 2


# ---------------------------------------------------------------------------
# 3. space()
# ---------------------------------------------------------------------------


def test_space_shapes_and_dtypes():
    layout = _sample_layout()
    space = layout.space(max_id=999)
    assert set(space.spaces.keys()) == {"f", "i"}

    f_box = space["f"]
    i_box = space["i"]

    assert f_box.shape == (layout.f_dim,)
    assert f_box.dtype == np.float32
    assert float(f_box.low.flat[0]) == pytest.approx(0.0)
    assert float(f_box.high.flat[0]) == pytest.approx(1.0)

    assert i_box.shape == (layout.i_dim,)
    assert i_box.dtype == np.int32
    assert int(i_box.low.flat[0]) == 0
    assert int(i_box.high.flat[0]) == 999


# ---------------------------------------------------------------------------
# 4. short row list leaves the tail padded
# ---------------------------------------------------------------------------


def test_write_rows_pads_the_tail():
    name = _unique_name("padtest")
    layout = ObsLayout(
        f_segments=[(f"{name}.f", 4 * 2)],
        i_segments=[(f"{name}.ids", 4 * 3)],
    )
    buf = ObsBuffer(layout)
    buf.reset()

    rows = [
        ((10, 20, 30), (0.5, 0.25)),
        ((11, 21, 31), (0.75, 0.125)),
    ]
    truncated = buf.write_rows(name, rows, cap=4, n_int=3, n_float=2)
    assert truncated is False

    i_block = buf.i[layout.i_slices[f"{name}.ids"]].reshape(4, 3)
    f_block = buf.f[layout.f_slices[f"{name}.f"]].reshape(4, 2)

    np.testing.assert_array_equal(i_block[0], [10, 20, 30])
    np.testing.assert_array_equal(i_block[1], [11, 21, 31])
    # Unwritten tail rows (2, 3) stay PAD / 0.0.
    for r in (2, 3):
        np.testing.assert_array_equal(i_block[r], [PAD, PAD, PAD])
        np.testing.assert_array_equal(f_block[r], [0.0, 0.0])


# ---------------------------------------------------------------------------
# 5. truncation
# ---------------------------------------------------------------------------


def test_write_rows_truncates_to_cap_and_warns_once():
    name = _unique_name("trunctest")
    cap = 3
    layout = ObsLayout(
        f_segments=[(f"{name}.f", cap * 1)],
        i_segments=[(f"{name}.ids", cap * 1)],
    )
    buf = ObsBuffer(layout)
    buf.reset()

    rows = [((i,), (float(i),)) for i in range(cap + 5)]  # 8 rows, cap 3

    with pytest.warns(UserWarning):
        truncated = buf.write_rows(name, rows, cap=cap, n_int=1, n_float=1)
    assert truncated is True

    i_block = buf.i[layout.i_slices[f"{name}.ids"]]
    np.testing.assert_array_equal(i_block, [0, 1, 2])  # first `cap`, in order

    # Second overflow of the SAME segment name must not warn again.
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        buf.reset()
        truncated_again = buf.write_rows(
            name, rows, cap=cap, n_int=1, n_float=1)
    assert truncated_again is True
    assert len(caught) == 0


def test_write_rows_at_exactly_cap_does_not_truncate_or_warn():
    name = _unique_name("exacttest")
    cap = 4
    layout = ObsLayout(
        f_segments=[(f"{name}.f", cap * 1)],
        i_segments=[(f"{name}.ids", cap * 1)],
    )
    buf = ObsBuffer(layout)
    buf.reset()

    rows = [((i,), (float(i),)) for i in range(cap)]  # exactly `cap` rows

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        truncated = buf.write_rows(name, rows, cap=cap, n_int=1, n_float=1)

    assert truncated is False
    assert len(caught) == 0


# ---------------------------------------------------------------------------
# 6. the non-leak property (sort=True is order-independent; sort=False isn't)
# ---------------------------------------------------------------------------


def _multiset_rows():
    # Distinct int tuples so every permutation is a genuinely different
    # input order (no accidental ties).
    return [
        ((5, 1), (0.1,)),
        ((2, 9), (0.2,)),
        ((8, 3), (0.3,)),
        ((1, 7), (0.4,)),
    ]


def test_sorted_write_rows_is_byte_identical_across_input_orders():
    name = _unique_name("sortleak")
    cap = 4
    layout = ObsLayout(
        f_segments=[(f"{name}.f", cap * 1)],
        i_segments=[(f"{name}.ids", cap * 2)],
    )
    rows = _multiset_rows()

    reference_bytes = None
    for perm in itertools.permutations(rows):
        buf = ObsBuffer(layout)
        buf.reset()
        buf.write_rows(
            name, list(perm), cap=cap, n_int=2, n_float=1, sort=True)
        i_bytes = buf.i[layout.i_slices[f"{name}.ids"]].tobytes()
        f_bytes = buf.f[layout.f_slices[f"{name}.f"]].tobytes()
        if reference_bytes is None:
            reference_bytes = (i_bytes, f_bytes)
        else:
            assert (i_bytes, f_bytes) == reference_bytes


def test_unsorted_write_rows_is_order_dependent():
    name = _unique_name("noleakcontrol")
    cap = 4
    layout = ObsLayout(
        f_segments=[(f"{name}.f", cap * 1)],
        i_segments=[(f"{name}.ids", cap * 2)],
    )
    rows = _multiset_rows()

    def bytes_for(order):
        buf = ObsBuffer(layout)
        buf.reset()
        buf.write_rows(
            name, list(order), cap=cap, n_int=2, n_float=1, sort=False)
        return buf.i[layout.i_slices[f"{name}.ids"]].tobytes()

    original = bytes_for(rows)
    reversed_order = bytes_for(list(reversed(rows)))
    assert original != reversed_order


# ---------------------------------------------------------------------------
# 7. reset() clears both halves
# ---------------------------------------------------------------------------


def test_reset_clears_both_halves_between_uses():
    name = _unique_name("resettest")
    cap = 2
    layout = ObsLayout(
        f_segments=[(f"{name}.f", cap * 1)],
        i_segments=[(f"{name}.ids", cap * 1)],
    )
    buf = ObsBuffer(layout)
    buf.reset()
    buf.write_rows(
        name, [((7,), (0.9,))], cap=cap, n_int=1, n_float=1)

    assert buf.i.any()
    assert buf.f.any()

    buf.reset()
    assert not buf.i.any()
    assert not buf.f.any()
    np.testing.assert_array_equal(buf.i, np.zeros_like(buf.i))
    np.testing.assert_array_equal(buf.f, np.zeros_like(buf.f))


# ---------------------------------------------------------------------------
# Extra: as_obs() shape/dtype sanity, and the row-shape validation guards.
# ---------------------------------------------------------------------------


def test_as_obs_returns_the_two_arrays():
    layout = _sample_layout()
    buf = ObsBuffer(layout)
    obs = buf.as_obs()
    assert set(obs.keys()) == {"f", "i"}
    assert obs["f"] is buf.f
    assert obs["i"] is buf.i
    assert obs["f"].dtype == np.float32
    assert obs["i"].dtype == np.int32


def test_write_rows_rejects_wrong_row_shape():
    name = _unique_name("shapeguard")
    cap = 2
    layout = ObsLayout(
        f_segments=[(f"{name}.f", cap * 2)],
        i_segments=[(f"{name}.ids", cap * 3)],
    )
    buf = ObsBuffer(layout)
    buf.reset()

    with pytest.raises(ValueError):
        buf.write_rows(
            name, [((1, 2), (0.1, 0.2))],  # only 2 ints, n_int=3
            cap=cap, n_int=3, n_float=2)


def test_canonical_sort_survives_truncation():
    """The non-leak property must hold when the block OVERFLOWS, not only
    when it fits.

    `write_rows` originally truncated and then sorted, which left *which rows
    survive* a function of the caller's order: shuffling a pile that exceeds
    its cap produced a different observation for the same multiset — the exact
    draw-order leak the sort exists to prevent (OBS_SCHEMA.md Sec.5.3). A
    6-row multiset into a cap-4 block produced 5 distinct observations across
    6 input orders.

    Sorting before truncating makes the retained set a function of the
    multiset alone. This is the regression test for that.
    """
    import random
    import warnings as _warnings

    cap = 4
    layout = ObsLayout(f_segments=[("pile.f", cap)], i_segments=[("pile.ids", cap)])
    rows = [([i], [float(i)]) for i in (5, 1, 4, 2, 6, 3)]

    digests = set()
    with _warnings.catch_warnings():
        _warnings.simplefilter("ignore")
        for trial in range(8):
            shuffled = rows[:]
            random.Random(trial).shuffle(shuffled)
            buf = ObsBuffer(layout)
            buf.reset()
            assert buf.write_rows(
                "pile", shuffled, cap=cap, n_int=1, n_float=1, sort=True)
            digests.add((buf.i.tobytes(), buf.f.tobytes()))

    assert len(digests) == 1, (
        f"{len(digests)} distinct observations for one multiset — the "
        f"canonical sort does not survive truncation")
    # And it keeps the SMALLEST rows, i.e. a prefix of the sorted multiset.
    buf = ObsBuffer(layout)
    buf.reset()
    buf.write_rows("pile", rows, cap=cap, n_int=1, n_float=1, sort=True)
    assert list(buf.i) == [1, 2, 3, 4]


def test_unsorted_truncation_still_keeps_the_callers_prefix():
    """The opposite mode must NOT be reordered: with sort=False the prefix is
    the meaning. Powers arrive in C#'s application order and the first `cap`
    are the oldest instances (OBS_SCHEMA.md Sec.2.3), so truncation has to cut
    the caller's own sequence."""
    import warnings as _warnings

    cap = 3
    layout = ObsLayout(f_segments=[("pw.f", cap)], i_segments=[("pw.ids", cap)])
    rows = [([i], [0.0]) for i in (9, 7, 8, 1, 2)]
    buf = ObsBuffer(layout)
    buf.reset()
    with _warnings.catch_warnings():
        _warnings.simplefilter("ignore")
        assert buf.write_rows("pw", rows, cap=cap, n_int=1, n_float=1)
    assert list(buf.i) == [9, 7, 8]
