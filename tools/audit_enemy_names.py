r"""One-shot audit: every enemy display name in EVERY recording's
`|| ... Enemies: [...]` annotations vs the names the sim's monster classes
carry. A mismatch ('Corpse Slug' vs 'CorpseSlug') costs a force-win during
replay -- fix the sim class's `name` to the recorded spelling (the game's
localized Title is the ground truth the mod recorded).

Enemy names are character-independent, so ALL SIX recordings are usable
ground truth here -- including the four non-Ironclad seeds (DJDC/L081/QRWC/
TZEK) whose runs can never replay against this Ironclad-only sim.

Each seed's three floor_N recordings are NOT cumulative supersets of one
another: the `||` annotation only appears on the tail of commands nearest
that capture's floor (e.g. floor_49's annotations start partway through the
file, well past the early-run combats that floor_18's annotations cover).
So this script globs every floor under every seed, not just floor_49.

Usage: py tools/audit_enemy_names.py
"""
from __future__ import annotations

import difflib
import re
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))
REC = _REPO.parent / "RunReplays" / "RunReplays" / "Resources"

from sts2_rl.conformance.recording import parse_recording  # noqa: E402


def sim_names() -> dict[str, list[str]]:
    """Recorded-spelling-comparable name -> [class qualnames carrying it].

    Mirrors `combat_driver.enemy_display_name`: `getattr(monster, "name", None)
    or type(monster).__name__`. Walks the MRO to resolve inherited names
    (e.g. DecimillipedeSegmentFront inherits "Decimillipede" from parent).
    For a class with NO `name` override, the runtime fallback is the
    class's own `__name__` (several monsters rely on this coincidence rather
    than an explicit attr, e.g. `class Chomper` displaying as "Chomper"), so
    that is added too. A `name` implemented as a `@property` (Tough Egg /
    Hatchling's hatch-state toggle) can't be evaluated without a live
    instance; its literal string constants are pulled out of the property's
    source instead so both of its display states register as "known"."""
    import importlib
    import inspect
    import re as _re
    from sts2_rl.monsters.base import Monster

    names: dict[str, list[str]] = {}
    for act in ("overgrowth", "underdocks", "hive", "glory"):
        mod = importlib.import_module(f"sts2_rl.monsters.{act}")
        pkg = Path(mod.__file__).parent
        for py in pkg.glob("*.py"):
            if py.stem == "__init__":
                continue
            m = importlib.import_module(f"sts2_rl.monsters.{act}.{py.stem}")
            for _, cls in inspect.getmembers(m, inspect.isclass):
                if not (issubclass(cls, Monster) and cls is not Monster and cls.__module__ == m.__name__):
                    continue
                qual = f"{act}.{py.stem}.{cls.__name__}"
                raw = getattr(cls, "name", None)
                if isinstance(raw, str):
                    names.setdefault(raw, []).append(qual)
                elif isinstance(raw, property) and raw.fget is not None:
                    try:
                        src = inspect.getsource(raw.fget)
                    except OSError:
                        src = ""
                    for lit in _re.findall(r'"([^"\\]+)"|\'([^\'\\]+)\'', src):
                        s = lit[0] or lit[1]
                        if s and s[:1].isupper():  # skip stray non-name literals
                            names.setdefault(s, []).append(qual)
                else:
                    names.setdefault(cls.__name__, []).append(qual)
    return names


def recorded_names() -> tuple[dict[str, list[str]], dict[str, int]]:
    """Return (recorded_name -> seeds, per_seed_distinct_count).

    First return value: recorded name -> sorted set of "seed/floor_N" strings.
    Second return value: seed -> count of distinct names harvested from that seed.
    Asserts that every seed directory contributed at least one name (catches
    parse_recording format changes that silently yield zero data)."""
    out: dict[str, set[str]] = {}
    per_seed: dict[str, set[str]] = {}
    for log in sorted(REC.glob("*/floor_*/actions.sts2replay")):
        seed = log.parent.parent.name
        floor = log.parent.name
        rec = parse_recording(log)
        for cmd in rec.commands:
            ann = cmd.annotation
            if ann is None or ann.enemies is None:
                continue
            for entry in ann.enemies:  # EnemyState(name, hp, max_hp)
                name = re.sub(r" #\S+$", "", entry.name)  # Test Subject #C71 etc.
                out.setdefault(name, set()).add(f"{seed}/{floor}")
                per_seed.setdefault(seed, set()).add(name)
    per_seed_counts = {s: len(names) for s, names in per_seed.items()}
    return {n: sorted(seeds) for n, seeds in out.items()}, per_seed_counts


def main() -> None:
    have = sim_names()
    recorded, per_seed_counts = recorded_names()
    # Validate that every seed contributed at least one name (catch format changes).
    for seed in sorted(per_seed_counts.keys()):
        count = per_seed_counts[seed]
        assert count > 0, f"Seed {seed!r} contributed 0 distinct names; parse_recording silently failed?"
    missing = {n: seeds for n, seeds in recorded.items() if n not in have}
    print(f"sim monster names: {len(have)}   recorded distinct names: {len(recorded)}   "
          f"recorded names missing from sim: {len(missing)}")
    print("Per-seed distinct name counts:")
    for seed in sorted(per_seed_counts.keys()):
        print(f"  {seed}: {per_seed_counts[seed]}")
    if missing:
        print("Missing names:")
    for name, seeds in sorted(missing.items()):
        close = difflib.get_close_matches(name, have.keys(), n=1)
        hint = f"  (closest sim name: {close[0]!r} in {have[close[0]]})" if close else ""
        print(f"  {name!r}  [seen in {', '.join(seeds)}]{hint}")


if __name__ == "__main__":
    main()
