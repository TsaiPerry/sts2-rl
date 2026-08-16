"""The shared observation-contract module — OBS_SCHEMA.md Sec.2.

Phase 1 (T1) of the entity-obs-schema work: the int/float ``Dict`` obs
contract, the named-segment-map idiom generalized from ``full_env.py``'s
``obs_segments()`` / ``obs_slices()``, and the padded-row writer three later
lanes (R1 relics, R2 card-instance rows, hand/enemy/pile blocks) build on.
Imported by both ``full_env.py`` and ``run_env.py``.

Contract (OBS_SCHEMA.md Sec.2)::

    observation_space = spaces.Dict({
        "f": spaces.Box(0.0, 1.0, shape=(F,), dtype=np.float32),
        "i": spaces.Box(0, MAX_ID, shape=(I,), dtype=np.int32),
    })

Padding (OBS_SCHEMA.md Sec.2.1): stored id = frozen-vocab index + 1; ``0`` is
reserved for "absent" (``PAD``).  ``oid()`` is the one place that ``+1``
lives — vocab.json itself is never renumbered.  A padded row is ``id == 0``
*and* all-zero floats, which is exactly what ``ObsBuffer.reset()`` leaves
untouched rows in, so ``write_rows`` never needs to clear a tail itself.

Segment-naming convention (this module's contract for the three later
lanes): a single logical block called ``name`` (e.g. ``"player.powers"``,
``"cards"``) is split into exactly two entries in the ``ObsLayout`` segment
lists:

* the int sub-block is registered under ``f"{name}.ids"`` in ``i_segments``,
  width ``cap * n_int``;
* the float sub-block is registered under ``f"{name}.f"`` in ``f_segments``,
  width ``cap * n_float``.

Row *r* of a block occupies ``i[r*n_int : (r+1)*n_int]`` within the
``.ids`` slice and ``f[r*n_float : (r+1)*n_float]`` within the ``.f`` slice
— i.e. rows are laid out contiguously, row-major, matching the ``(ints,
floats)`` pairing ``write_rows`` takes. This mirrors OBS_SCHEMA.md's own
``player.powers.id`` / ``player.powers.f`` and ``cards.ids`` / ``cards.f``
naming exactly, just made uniform (this module always uses the plural
``.ids`` suffix on the int side, even for one-int-per-row blocks, so the
lookup rule has no exceptions).

Overflow (OBS_SCHEMA.md Sec.2.3): ``write_rows`` truncates to the first
``cap`` rows of the caller's sequence — never asserts — and warns exactly
once per ``(process, segment name)`` so a hot loop cannot spam the log.

Non-leak sort (OBS_SCHEMA.md Sec.5.3): ``write_rows(..., sort=True)`` sorts
rows by ``(ints tuple, floats tuple)`` before writing, so the block is
order-independent — the mechanism that keeps pile order (hidden information
in the real game) out of the observation.
"""
from __future__ import annotations

import warnings
from typing import Sequence

import numpy as np
from gymnasium import spaces

PAD: int = 0

# Segment names already warned-about in this process, so a block that
# overflows every step logs once rather than spamming. Deliberately a
# module-level (process-wide) set, per OBS_SCHEMA.md Sec.2.3's "log loudly,
# once per process" — not per-ObsBuffer-instance, since a fresh buffer is
# constructed every reset() but the same overflow condition would otherwise
# re-warn every episode.
_WARNED_SEGMENTS: set[str] = set()


def reset_warned_segments() -> None:
    """Clear the warn-once latch (test-only affordance).

    The process-global latch makes ``pytest.warns`` order-dependent across
    the test process (whichever test overflows a segment first consumes the
    latch, later tests on that name see no warning); ``test/conftest.py``
    calls this from an autouse fixture before every test to avoid that.
    """
    _WARNED_SEGMENTS.clear()


def oid(index: int | None) -> int:
    """Vocab index -> observation id. ``None`` maps to ``PAD`` (0).

    Otherwise ``index + 1`` — id 0 is reserved for "absent" (OBS_SCHEMA.md
    Sec.2.1), so ``vocab.json``'s row 0 is never a real vocab entry and the
    table's ``padding_idx=0`` lines up for free.
    """
    if index is None:
        return PAD
    return index + 1


class ObsLayout:
    """A named ``(segment, width)`` map for each half, generalizing
    ``full_env.obs_segments()`` / ``obs_slices()`` to the two-half contract.
    """

    def __init__(
        self,
        f_segments: list[tuple[str, int]],
        i_segments: list[tuple[str, int]],
    ) -> None:
        self.f_segments = list(f_segments)
        self.i_segments = list(i_segments)

        self.f_slices: dict[str, slice] = {}
        offset = 0
        for name, width in self.f_segments:
            self.f_slices[name] = slice(offset, offset + width)
            offset += width
        self.f_dim = offset

        self.i_slices: dict[str, slice] = {}
        offset = 0
        for name, width in self.i_segments:
            self.i_slices[name] = slice(offset, offset + width)
            offset += width
        self.i_dim = offset

    def space(self, max_id: int) -> spaces.Dict:
        """The ``gymnasium.spaces.Dict`` OBS_SCHEMA.md Sec.2 describes."""
        return spaces.Dict({
            "f": spaces.Box(0.0, 1.0, shape=(self.f_dim,), dtype=np.float32),
            "i": spaces.Box(0, max_id, shape=(self.i_dim,), dtype=np.int32),
        })


class ObsBuffer:
    """Two preallocated arrays (``f``, ``i``) plus the padded-row writer.

    Construct once from an :class:`ObsLayout`; call :meth:`reset` at the
    start of each observation build to zero both halves for reuse, then
    populate segments with :meth:`write_rows` (or direct slice writes for
    non-row segments such as scalars), then hand out :meth:`as_obs`.
    """

    def __init__(self, layout: ObsLayout) -> None:
        self.layout = layout
        self.f = np.zeros(layout.f_dim, dtype=np.float32)
        self.i = np.zeros(layout.i_dim, dtype=np.int32)

    def reset(self) -> None:
        """Zero both halves. Establishes the padding invariant (id 0, floats
        0.0) that ``write_rows`` relies on for its unwritten tail rows."""
        self.f.fill(0.0)
        self.i.fill(PAD)

    def as_obs(self) -> dict[str, np.ndarray]:
        return {"f": self.f, "i": self.i}

    def write_rows(
        self,
        name: str,
        rows: Sequence[tuple[Sequence[int], Sequence[float]]],
        *,
        cap: int,
        n_int: int,
        n_float: int,
        sort: bool = False,
    ) -> bool:
        """Write ``rows`` into the ``name`` block, truncating to ``cap``.

        Each row is ``(ints, floats)`` with ``len(ints) == n_int`` and
        ``len(floats) == n_float``. Rows are written at row index 0, 1, 2,
        ... into ``f"{name}.ids"`` (int half) / ``f"{name}.f"`` (float half).

        Rows beyond ``cap`` are TRUNCATED, never asserted (OBS_SCHEMA.md
        Sec.2.3) — the first ``cap`` rows of ``rows``, in the caller's own
        order, are kept; that prefix property is load-bearing (powers keep
        C#'s application order this way). Returns ``True`` iff truncation
        occurred, and warns exactly once per ``(process, name)`` when it
        does, naming the segment, the cap and the observed row count.

        Rows past the end of what's written are left as ``reset()`` left
        them (PAD id, 0.0 floats) — this method never clears a tail.

        ``sort=True`` sorts rows canonically by ``(tuple(ints),
        tuple(floats))`` before writing, so the resulting block is independent
        of the input order — the hidden-information non-leak mechanism for card
        piles (OBS_SCHEMA.md Sec.5.3). The sort happens BEFORE the truncation,
        so the property survives overflow; see the comment at the call site.
        """
        ikey = f"{name}.ids"
        fkey = f"{name}.f"
        i_slice = self.layout.i_slices[ikey]
        f_slice = self.layout.f_slices[fkey]

        expected_i_width = cap * n_int
        expected_f_width = cap * n_float
        i_width = i_slice.stop - i_slice.start
        f_width = f_slice.stop - f_slice.start
        if i_width != expected_i_width:
            raise ValueError(
                f"obs segment {ikey!r} has width {i_width}, expected "
                f"cap * n_int = {cap} * {n_int} = {expected_i_width}")
        if f_width != expected_f_width:
            raise ValueError(
                f"obs segment {fkey!r} has width {f_width}, expected "
                f"cap * n_float = {cap} * {n_float} = {expected_f_width}")

        rows = list(rows)
        n_rows = len(rows)
        truncated = n_rows > cap

        # ORDER MATTERS, and the two modes need opposite orders.
        #
        # sort=True must sort BEFORE truncating. Sorting the survivors of a
        # positional truncation would leave *which rows survive* a function of
        # the caller's order — so shuffling a pile that overflows its cap would
        # change the observation, re-introducing the exact draw-order leak the
        # sort exists to prevent (OBS_SCHEMA.md Sec.5.3). Sorting first makes the
        # retained set a deterministic function of the multiset alone.
        #
        # sort=False must truncate the caller's sequence directly, because
        # there the prefix IS the meaning: powers arrive in C#'s application
        # order and the first `cap` are the oldest instances (Sec.2.3).
        if sort:
            rows = sorted(
                rows, key=lambda row: (tuple(row[0]), tuple(row[1])))
        if truncated:
            rows = rows[:cap]
            if name not in _WARNED_SEGMENTS:
                _WARNED_SEGMENTS.add(name)
                warnings.warn(
                    f"obs segment {name!r}: {n_rows} rows exceeds cap "
                    f"{cap}; truncating to {cap}",
                    stacklevel=2,
                )

        i_base = i_slice.start
        f_base = f_slice.start
        for r, (ints, floats) in enumerate(rows):
            ints = list(ints)
            floats = list(floats)
            if len(ints) != n_int:
                raise ValueError(
                    f"obs segment {name!r} row {r}: expected {n_int} ints, "
                    f"got {len(ints)}")
            if len(floats) != n_float:
                raise ValueError(
                    f"obs segment {name!r} row {r}: expected {n_float} "
                    f"floats, got {len(floats)}")
            io = i_base + r * n_int
            fo = f_base + r * n_float
            self.i[io:io + n_int] = ints
            self.f[fo:fo + n_float] = floats

        return truncated
