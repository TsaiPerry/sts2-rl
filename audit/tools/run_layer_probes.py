"""Reproducible probes for seam/run_layer (Phase 2).

Same contract as audit/tools/rng_stream_probes.py and relic_probes.py: every
"executed evidence" claim the record states is reproducible here.

  py audit/tools/run_layer_probes.py                     # every probe
  py audit/tools/run_layer_probes.py discovery-order      # one probe

Probes:
  discovery-order       RunManager.ShouldApplyTutorialModifications's guard
                         chain has no player-count/first-run check (reads the
                         body, not the name or the XML summary), and the sim
                         has zero references to ApplyDiscoveryOrderModifications
                         / ApplyActDiscoveryOrderModifications / BossDiscoveryOrder
                         / HasSeenEncounter anywhere -- guard G6's evidence.
  starting-relic-order  BurningBlood.cs (Ironclad's only, and the only
                         reachable, starting relic) has no AfterObtained
                         override -- guard G7's dormancy evidence.
  string-seed-default   RunState.__init__'s `string_seed` default is None,
                         and the RL training env files never pass one, while
                         the conformance driver does -- guard G8's evidence.
  profile-scope         enumerate every SaveManager.Instance.Progress read
                         reachable from RunManager.cs and report which sim
                         file (if any) references the analogous concept --
                         guard G10's evidence.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

_GAME_ROOT = Path(os.environ.get(
    "STS2_GAME_SRC", r"c:\Users\Perry\Desktop\Slay the Spire 2"))


def _say(label: str, observed, expected) -> None:
    flag = "MATCH  " if observed == expected else "DIVERGE"
    print(f"  {flag}  {label}: observed={observed!r}  expected={expected!r}")


def _grep(root: Path, pattern: str, globs: tuple[str, ...]) -> list[tuple[Path, int, str]]:
    rx = re.compile(pattern)
    hits: list[tuple[Path, int, str]] = []
    for g in globs:
        for p in root.rglob(g):
            try:
                text = p.read_text(encoding="utf-8-sig", errors="replace")
            except OSError:
                continue
            for i, line in enumerate(text.splitlines(), 1):
                if rx.search(line):
                    hits.append((p, i, line.strip()))
    return hits


# -- discovery-order --------------------------------------------------------
def probe_discovery_order() -> None:
    print("discovery-order -- RunManager.ShouldApplyTutorialModifications's "
          "guard chain vs the sim's discovery-order modeling")
    rm = _GAME_ROOT / "src/Core/Runs/RunManager.cs"
    text = rm.read_text(encoding="utf-8-sig", errors="replace")
    m = re.search(
        r"public bool ShouldApplyTutorialModifications\(\)\s*\{(.*?)\n\t\}",
        text, re.DOTALL)
    assert m, "ShouldApplyTutorialModifications not found in RunManager.cs"
    body = m.group(1)
    has_player_count_check = bool(re.search(r"Players\.Count", body))
    has_number_of_runs_check = bool(re.search(r"NumberOfRuns", body))
    print("  RunManager.cs ShouldApplyTutorialModifications() body:")
    for line in body.strip().splitlines():
        print("   ", line.strip())
    _say("body checks Players.Count (a multiplayer opt-out, as the XML "
         "summary implies)", has_player_count_check, False)
    _say("body checks Progress.NumberOfRuns (a first-run/tutorial gate, as "
         "the method's own NAME implies)", has_number_of_runs_check, False)
    print("  -> the method's only real gates are ForceDiscoveryOrderModifications "
          "(opt-in), TestMode.IsOn (off in real play) and GameMode != Standard "
          "(false for a Standard run) -- it defaults TRUE for ordinary solo play.")

    sim_hits = _grep(_REPO / "sts2_rl", r"ApplyDiscoveryOrderModifications|"
                      r"ApplyActDiscoveryOrderModifications|BossDiscoveryOrder|"
                      r"HasSeenEncounter", ("*.py",))
    print(f"  sim references to ApplyDiscoveryOrderModifications/"
          f"ApplyActDiscoveryOrderModifications/BossDiscoveryOrder/"
          f"HasSeenEncounter: {len(sim_hits)}")
    for p, i, line in sim_hits:
        print(f"    {p.relative_to(_REPO)}:{i}: {line}")
    functional = [h for h in sim_hits if not h[2].lstrip().startswith("#")]
    print(f"  of those, references in EXECUTABLE (non-comment) code: "
          f"{len(functional)}")
    if functional:
        print("  -> the mechanism is IMPLEMENTED: RoomSet.apply_discovery_"
              "order_modifications runs after every act's room generation, "
              "reading the run's UnlockState. It defaults to a profile that "
              "has seen everything (UnlockState.VETERAN), which makes the "
              "pass a no-op -- the omission is now a documented DEFAULT, not "
              "missing code.")
    else:
        print("  -> every hit is a comment DISCLOSING the omission, not an "
              "implementation of it; zero functional/executable code "
              "implements any of the four names on either grep.")

    # Executed: does a fresh profile actually change the act's boss?
    import random

    from sts2_rl.rooms import RoomSet, UnlockState, act_rooms

    rooms = act_rooms("overgrowth")
    veteran = RoomSet.generate(rooms, random.Random(3), 12, 3)
    fresh = RoomSet.generate(rooms, random.Random(3), 12, 3,
                             unlock_state=UnlockState.FRESH)
    print(f"  overgrowth boss, veteran profile: {veteran.boss_key!r} | "
          f"zero-run profile: {fresh.boss_key!r} "
          f"(BossDiscoveryOrder[0] = {rooms.boss_discovery_order[0]!r})")
    print(f"  overgrowth opening lineup, zero-run profile: "
          f"{fresh.normal_keys[:7]}")

    call_site = _grep(_GAME_ROOT / "src", r"ApplyDiscoveryOrderModifications\(",
                       ("*.cs",))
    print(f"  game call sites of ApplyDiscoveryOrderModifications(: {len(call_site)}")
    for p, i, line in call_site:
        print(f"    {p.relative_to(_GAME_ROOT)}:{i}: {line}")


# -- starting-relic-order ----------------------------------------------------
def probe_starting_relic_order() -> None:
    print("starting-relic-order -- does BurningBlood.cs override AfterObtained?")
    bb = _GAME_ROOT / "src/Core/Models/Relics/BurningBlood.cs"
    text = bb.read_text(encoding="utf-8-sig", errors="replace")
    overrides = re.findall(r"public override (?:async )?\S+ (\w+)\(", text)
    print(f"  BurningBlood.cs public override members: {overrides}")
    _say("AfterObtained overridden by BurningBlood.cs", "AfterObtained" in overrides,
         False)

    ironclad = _GAME_ROOT / "src/Core/Models/Characters/Ironclad.cs"
    itext = ironclad.read_text(encoding="utf-8-sig", errors="replace")
    m = re.search(r"StartingRelics =>.*?ModelDb\.Relic<(\w+)>\(\)", itext, re.DOTALL)
    relics = re.findall(r"ModelDb\.Relic<(\w+)>\(\)",
                         re.search(r"StartingRelics =>(.*?);", itext, re.DOTALL).group(1))
    _say("Ironclad.StartingRelics", relics, ["BurningBlood"])
    print("  -> the only starting relic reachable in this Ironclad-only sim has "
          "no AfterObtained override, so the AfterObtained-vs-GenerateRooms "
          "ordering swap (guard G7) is dormant today.")


# -- string-seed-default -----------------------------------------------------
def probe_string_seed_default() -> None:
    print("string-seed-default -- where does RunState.rng_set end up None?")
    run_py = _REPO / "sts2_rl/run.py"
    text = run_py.read_text(encoding="utf-8-sig", errors="replace")
    m = re.search(r"string_seed: str \| None = (\w+)", text)
    _say("RunState.__init__'s string_seed default", m.group(1) if m else None, "None")

    for name in ("env.py", "full_env.py"):
        p = _REPO / "sts2_rl" / name
        hits = _grep(p.parent, r"string_seed", (name,)) if p.is_file() else []
        _say(f"sts2_rl/{name} references to string_seed", len(hits), 0)

    driver_hits = _grep(_REPO / "sts2_rl", r"string_seed=", ("driver.py",))
    print(f"  sts2_rl/driver.py string_seed= call sites: {len(driver_hits)}")
    for p, i, line in driver_hits:
        print(f"    {p.relative_to(_REPO)}:{i}: {line}")


# -- profile-scope ------------------------------------------------------------
def probe_profile_scope() -> None:
    print("profile-scope -- every SaveManager.Instance.Progress read reachable "
          "from RunManager.cs, and the sim's analogue (if any)")
    hits = _grep(_GAME_ROOT / "src/Core/Runs", r"SaveManager\.Instance\.Progress",
                 ("*.cs",))
    for p, i, line in hits:
        print(f"    {p.relative_to(_GAME_ROOT)}:{i}: {line}")
    _say("sts2_rl references to a 'profile'/persistent-progress concept",
         len(_grep(_REPO / "sts2_rl", r"\bProgress\b|profile_scope|SaveManager",
                    ("*.py",))), 0)
    print("  -> the sim has no profile singleton at all (RunState() starts "
          "cold every time); see the record's G2/G9/G10 for the per-field "
          "consequence of each C# Progress read this seam's files reach.")


PROBES = {
    "discovery-order": probe_discovery_order,
    "starting-relic-order": probe_starting_relic_order,
    "string-seed-default": probe_string_seed_default,
    "profile-scope": probe_profile_scope,
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("name", nargs="?", choices=sorted(PROBES), default=None)
    args = ap.parse_args()
    names = [args.name] if args.name else sorted(PROBES)
    for name in names:
        PROBES[name]()
        print()


if __name__ == "__main__":
    main()
