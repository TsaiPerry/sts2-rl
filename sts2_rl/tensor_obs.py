"""``TensorObs`` -- the one place the v4 ``{"f", "i"}`` observation break
lives (OBS_SCHEMA.md §2.2, T6 brief §2).

Both training envs now emit ``{"f": float32 array, "i": int32 array}``
instead of a flat ``Box`` (``sts2_rl/obs.py``'s contract). Rather than thread
that pair through every line of ``train_torch.py``'s PPO loop, the whole
loop keeps operating on ONE object per "observation slot" -- ``obs_buf``,
``next_obs``, ``b_obs`` -- and this class is what that object is. The call
sites that matter (``obs_buf[t] = next_obs``, ``b_obs = obs_buf.reshape(-1,
obs_dim)``, ``b_obs[mb]``) read the same as they did against the old flat
tensor; only the type backing them changed, and it changed exactly here.

Deliberately minimal (T6 brief §2: "no speculative API") -- every method
exists because a real call site in ``train_torch.py`` or ``vec_env.py``
needs it:

* ``from_dict`` / ``__init__`` -- build from the env's own ``ObsBuffer.as_obs()``
  output (or from two already-batched arrays).
* ``__getitem__`` / ``__setitem__`` -- minibatch indexing (``b_obs[mb]``),
  timestep writes (``obs_buf[t] = next_obs``), and adding a batch axis with
  ``obs[None]`` (the truncation-bootstrap call site, mirroring plain
  numpy/torch's own ``arr[None]`` idiom -- no bespoke ``unsqueeze`` needed).
* ``reshape`` -- flattening the ``[n_steps, n_envs, ...]`` rollout buffer to
  ``[batch, ...]`` for the update.
* ``to`` -- the numpy (vec_env.py) -> torch (train_torch.py, on ``--device``)
  handoff. Casts ``f`` to float32 and ``i`` to int64 (torch embedding
  lookups require a Long/Int index tensor; float32 would silently destroy
  every id's exactness, exactly what OBS_SCHEMA.md §2's int/float split
  exists to prevent).
* ``copy`` -- an independent snapshot (vec_env's per-env truncation
  ``final_obs`` capture must survive the source buffer being overwritten).
* ``__array__`` -- lets ``np.array_equal(a, b)`` compare two ``TensorObs``
  without raising or needing special-casing in code that doesn't know about
  this class (a plain ``{"f": ..., "i": ...}`` dict can't do this: dict
  equality forces every value's ``==`` result to a bare ``bool``, and numpy
  arrays with more than one element raise on that -- ``ValueError: The
  truth value of an array with more than one element is ambiguous``).
"""
from __future__ import annotations

from typing import Any

import numpy as np


class TensorObs:
    """A paired ``(f, i)`` observation batch.

    ``.f``/``.i`` are either both numpy arrays (``vec_env.py``'s world,
    straight off the env) or both torch tensors (after ``.to(device)``,
    ``train_torch.py``'s world) -- every method just forwards to whichever
    backend it's holding, so the same class works on both sides of that
    handoff.
    """

    __slots__ = ("f", "i")

    def __init__(self, f: Any, i: Any) -> None:
        self.f = f
        self.i = i

    @classmethod
    def from_dict(cls, obs: dict, *, device: Any | None = None) -> "TensorObs":
        """Build from ``{"f": array, "i": array}`` (``ObsBuffer.as_obs()``'s
        shape). ``device=None`` keeps whatever arrays were passed in as-is;
        otherwise moves to ``device`` via :meth:`to`."""
        t = cls(obs["f"], obs["i"])
        return t if device is None else t.to(device)

    def __getitem__(self, key: Any) -> "TensorObs":
        return TensorObs(self.f[key], self.i[key])

    def __setitem__(self, key: Any, value: "TensorObs") -> None:
        self.f[key] = value.f
        self.i[key] = value.i

    def reshape(self, *shape: Any) -> "TensorObs":
        """``reshape(*lead, (f_width, i_width))``: every leading dim is
        shared by both halves; the trailing element is a ``(f_width,
        i_width)`` pair, because the two halves don't share a last
        dimension. This is exactly the shape
        ``obs_buf.reshape(-1, obs_dim)`` needs once ``obs_dim`` is that
        pair."""
        *lead, last = shape
        f_width, i_width = last
        return TensorObs(self.f.reshape(*lead, f_width), self.i.reshape(*lead, i_width))

    def to(self, device: Any) -> "TensorObs":
        """Move (or build) both halves as torch tensors on ``device``:
        float32 for ``f``, int64 for ``i``. ``torch.as_tensor`` accepts
        either a numpy array or an existing torch tensor, so this is the
        one method that bridges vec_env.py's numpy world and
        train_torch.py's torch world."""
        import torch

        f = torch.as_tensor(self.f, dtype=torch.float32, device=device)
        i = torch.as_tensor(self.i, dtype=torch.int64, device=device)
        return TensorObs(f, i)

    def copy(self) -> "TensorObs":
        """An independent snapshot -- callers that must survive the source
        buffer being overwritten in place (vec_env's truncation
        ``final_obs`` capture) copy each half."""
        return TensorObs(self.f.copy(), self.i.copy())

    def __array__(self, dtype: Any = None) -> np.ndarray:
        """Only for comparison purposes (``np.array_equal`` et al): the two
        halves concatenated along the last axis, ids upcast to float64. No
        path in the trainer ever reads this -- it exists purely so generic
        numpy comparisons work without a TensorObs-aware special case."""
        f = np.asarray(self.f)
        i = np.asarray(self.i)
        out = np.concatenate([f.astype(np.float64), i.astype(np.float64)], axis=-1)
        return out if dtype is None else out.astype(dtype)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"TensorObs(f={self.f!r}, i={self.i!r})"
