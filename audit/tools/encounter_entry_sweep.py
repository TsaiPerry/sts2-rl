"""Mechanical sweep: every sim `Encounter.entry` against the game's real
`ModelId.Entry`.

`encounter/_entry_slug_mismatch` was found unit by unit — five encounters
whose sim `id` is not their C# class name's slug, so `id.upper()` seeds
`make_encounter_rng` with a key the game never uses. The record's own fix note
asked for "a mechanical audit of every Encounter id against its C# class
name"; this is it, and it found two more (`fuzzy_wurm_crawler`,
`overgrowth_crawlers_normal`) that no batch had checked.

It walks every `Encounter` instance in `sts2_rl` and every
`src/Core/Models/Encounters/*.cs` class name, slugifies the latter with
`StringHelper.Slugify` (StringHelper.cs:74-79) and reports any sim entry that
is not a real game entry.

    py audit/tools/encounter_entry_sweep.py
"""
from __future__ import annotations

import importlib
import pkgutil
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

GAME_ENCOUNTERS = Path(
    r"c:/Users/Perry/Desktop/Slay the Spire 2/src/Core/Models/Encounters"
)


def slugify(class_name: str) -> str:
    """`StringHelper.Slugify` for a PascalCase type name."""
    return re.sub(r"(?<=[A-Za-z0-9])([A-Z])", r"_\1", class_name).upper()


def sim_encounters() -> dict[str, object]:
    import sts2_rl
    from sts2_rl.monsters.base import Encounter

    found: dict[str, object] = {}
    for mod in pkgutil.walk_packages(sts2_rl.__path__, "sts2_rl."):
        try:
            module = importlib.import_module(mod.name)
        except Exception:
            continue
        for obj in vars(module).values():
            if isinstance(obj, Encounter):
                found.setdefault(obj.id, obj)
    return found


def main() -> int:
    if not GAME_ENCOUNTERS.is_dir():
        print(f"game source not found at {GAME_ENCOUNTERS}")
        return 2
    game = {slugify(p.stem): p.stem for p in GAME_ENCOUNTERS.glob("*.cs")}
    sim = sim_encounters()
    print(f"sim encounters: {len(sim)}   C# encounter classes: {len(game)}")

    bad = []
    overridden = []
    for eid, enc in sorted(sim.items()):
        if enc.entry_slug is not None:
            overridden.append((eid, enc.entry_slug))
        if enc.entry not in game:
            bad.append((eid, enc.entry))

    print(f"\nencounters declaring an explicit entry_slug ({len(overridden)}):")
    for eid, slug in overridden:
        mark = "ok" if slug in game else "STILL NOT A GAME ENTRY"
        print(f"  {eid:34s} -> {slug:38s} {mark}")

    if bad:
        print(f"\nMISMATCH — {len(bad)} sim entries the game does not have:")
        for eid, entry in bad:
            print(f"  {eid:34s} entry={entry}")
        return 1
    print("\nMATCH: every sim Encounter.entry is a real game ModelId.Entry.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
