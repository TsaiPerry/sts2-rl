"""Extract every ``verdict == "gap"`` entry from the seam audit records.

This is the generator behind ``docs/audit/GAP-QUEUE.md``.  Nothing here reads or
writes engine code; it only parses ``audits/seam/*.json`` plus the xfail pins in
``test/test_hook_order.py`` so the queue's counts are reproducible instead of
transcribed.

Commands
--------
``counts``       summary header numbers (total / live / dormant / mechanisms / pinned)
``list``         one line per gap entry: id, liveness, mechanism, head of ``what``
``mechanisms``   the mechanism groups, largest first
``pins``         the strict xfail pins in test/test_hook_order.py and what they pin
``unpinned``     mechanisms with no pin
``refs``         raw cross-references found in gap text (grouping evidence)
``json``         the full structured dump

Every gap entry is assigned to exactly one mechanism.  A step entry that names a
guard ("see guard G5", "gap G2 (cross-listener order)", "GAP G8 (clause a)")
joins that guard's mechanism; a guard entry anchors its own; the rest stand
alone.  ``_CROSS_RECORD`` then merges mechanism keys that the records themselves
declare to be the same mechanism recorded in two seams.

Usage:  py tools/audit/gap_queue.py <command>
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RECORD_DIR = ROOT / "audits" / "seam"
PIN_FILE = ROOT / "test" / "test_hook_order.py"

SEAMS = [
    "damage_pipeline",
    "power_cmd",
    "creature_card_cmds",
    "turn_structure",
    "hook_dispatch",
    "monster_state_machine",
]

# --- mechanism merges the records themselves declare -------------------------
# key: mechanism key as auto-derived, value: canonical mechanism key.
# Each merge is asserted by text in at least one of the two records.
_CROSS_RECORD = {
    # "the same mechanism as damage_pipeline's guard N3, raised to gap in the
    # same pass" -- test_hook_order.py pin for G9; damage_pipeline N3 says the
    # same.  creature_card_cmds step 13 is the block-side site of it.
    "damage_pipeline/N3": "hook_dispatch/G9",
    # damage_pipeline G2 and power_cmd G4 are both the AfterModifyingXxx
    # companion-event machinery; power_cmd G4 cites damage_pipeline's finding
    # explicitly ("2 of the 13 AfterModifying* variants Task 5's
    # damage_pipeline audit found the sim implements only 1 of").
    "power_cmd/G4": "damage_pipeline/G2",
    # creature_card_cmds G2 is AfterModifyingBlockAmount -- the same missing
    # machinery at the block site.
    "creature_card_cmds/G2": "damage_pipeline/G2",
    # hook_dispatch step 38 is the same modifier-notification-list mechanism.
    # (auto-derived key for that step is its own; merged here.)
    "hook_dispatch/step38": "damage_pipeline/G2",
    # the pipeline-level is_powered_attack gate: damage side (damage_pipeline
    # G3) and block side (creature_card_cmds G1) are one mechanism at two
    # dispatch sites.
    "creature_card_cmds/G1": "damage_pipeline/G3",
    # the IsEnding / combat-over guard family: creature_card_cmds G14,
    # power_cmd G6 and hook_dispatch G8 are the same missing gate recorded on
    # three seams (G14's own text calls it "the combat-over / IsEnding guard
    # family ... no sim counterpart anywhere").
    "creature_card_cmds/G14": "hook_dispatch/G8",
    "power_cmd/G6": "hook_dispatch/G8",
    # within turn_structure the record states the precedence itself:
    # N1 "Carries G8's precedence (same missing phase model)",
    # N4 "carrying G3's precedence", N5 "this guard carries G10's verdict".
    "turn_structure/N1": "turn_structure/G8",
    "turn_structure/N4": "turn_structure/G3",
    "turn_structure/N5": "turn_structure/G10",
}

# Entries whose FIRST guard reference is not the finding the entry is about.
# Each is justified by the entry's own text or by the pin that names it.
_PRIMARY_OVERRIDE = {
    # step 52's lead clause is the IsEnding guard, but the finding the step
    # carries (and the one its pin asserts) is DowngradeInternal re-deriving
    # the card from its canonical model -- a one-level drop in the sim.
    "creature_card_cmds/step52": "creature_card_cmds/step52",
    # step 67's issue says "Same mechanism and same verdict as step 32".
    "turn_structure/step67": "turn_structure/step32",
}

# Additional mechanisms an entry is ALSO a site of (does not affect counts;
# each entry is counted once, under its primary mechanism).
_ALSO = {
    # "(c) AGGREGATION SHAPE -- this is gap G9 of audits/seam/hook_dispatch.json
    #  (step 31), the same mechanism as ... damage_pipeline.json guard N3,
    #  carried here at the third and last of its three sites"
    "creature_card_cmds/step13": ["hook_dispatch/G9"],
    # "See guards G3 and G8."
    "creature_card_cmds/step59": ["creature_card_cmds/G8"],
    # "See guard G14 ... See guard N3."
    "creature_card_cmds/step72": ["creature_card_cmds/N3"],
    # step 89's tail is the AfterCardChangedPiles-on-every-draw hole
    "creature_card_cmds/step89": ["creature_card_cmds/G8"],
}

# Mechanism keys are auto-derived; these are the display names.
MECHANISM_TITLES = {
    "hook_dispatch/G9": "multiplicative modifier hooks: parallel product vs sequential chain",
    "monster_state_machine/G1": "AddBranch integer arguments read as weights",
    "turn_structure/G13": "no CheckWinCondition after turn-1 setup",
    "creature_card_cmds/G3": "deck transform bypasses the deck-entry pipeline",
    "hook_dispatch/G2": "cross-listener dispatch order (Powers->Relics->Potions->Orbs->Cards)",
    "hook_dispatch/G3": "no Early/VeryEarly/Late phase passes",
    "hook_dispatch/G4": "one hook bracket per logical play instead of per CardPlay",
    "hook_dispatch/G8": "no IsEnding / IsOverOrEnding dispatch gate",
    "damage_pipeline/G2": "no AfterModifyingXxx(modifiers) companion events",
    "damage_pipeline/G3": "pipeline-level is_powered_attack gate",
}

_ID_STEP = re.compile(r"^\s*(\d+(?:\.\d+)?[a-z]?)\s*[.:]")
_ID_GUARD = re.compile(r"^\s*([GN]\d+)\b")
# a step that names the guard/gap it belongs to
_REF = re.compile(r"\b(?:gap|guard)s?\s+([GN]\d+)\b", re.IGNORECASE)
_ANY_REF = re.compile(r"\b(?:gap|guard|note)s?\s+((?:[GN]\d+)(?:\s*(?:,|and|/|or)\s*[GN]\d+)*)", re.IGNORECASE)
_FILELINE = re.compile(r"([\w./\\-]+\.(?:py|cs)):(\d+(?:-\d+)?)")

_LIVE = re.compile(r"\b(LIVE(?:NESS)?|live and (?:executed|reachable)|LIVE AND REACHABLE)\b")
_DORMANT = re.compile(r"\b(DORMANT|dormant)\b")


def load_records():
    out = {}
    for seam in SEAMS:
        path = RECORD_DIR / f"{seam}.json"
        out[seam] = json.loads(path.read_text(encoding="utf-8"))
    return out


def _entry_id(section: str, what: str, ordinal: int) -> str:
    if section == "guards":
        m = _ID_GUARD.match(what)
        return m.group(1) if m else f"guard{ordinal}"
    m = _ID_STEP.match(what)
    return f"step{m.group(1)}" if m else f"step_i{ordinal}"


def _liveness(text: str) -> str:
    """LIVE / DORMANT read out of the record's own text.

    Records write the verdict in caps near the head of the issue, and the
    liveness argument later.  First explicit token wins; a guard headline like
    "G1 (LIVE) --" or "(dormant)" is authoritative.
    """
    head = text[:400]
    m_live = _LIVE.search(head)
    m_dorm = _DORMANT.search(head)
    if m_live and m_dorm:
        return "live" if m_live.start() < m_dorm.start() else "dormant"
    if m_live:
        return "live"
    if m_dorm:
        return "dormant"
    # fall back to a full-text scan
    m_live = _LIVE.search(text)
    m_dorm = _DORMANT.search(text)
    if m_live and m_dorm:
        return "live" if m_live.start() < m_dorm.start() else "dormant"
    if m_live:
        return "live"
    if m_dorm:
        return "dormant"
    return "unlabelled"


def extract():
    """Return the list of gap entries, each with id / liveness / mechanism."""
    records = load_records()
    entries = []
    for seam in SEAMS:
        rec = records[seam]
        for section in ("steps", "guards"):
            for i, e in enumerate(rec.get(section, [])):
                if e.get("verdict") != "gap":
                    continue
                what = e["what"]
                body = e.get("issue") or e.get("rationale") or ""
                eid = _entry_id(section, what, i)
                key = f"{seam}/{eid}"
                if key in _PRIMARY_OVERRIDE:
                    mech = _PRIMARY_OVERRIDE[key]
                elif section == "guards":
                    mech = key
                else:
                    m = _REF.search(body)
                    mech = f"{seam}/{m.group(1)}" if m else key
                mech = _CROSS_RECORD.get(mech, mech)
                entries.append(
                    {
                        "id": key,
                        "seam": seam,
                        "section": section,
                        "local_id": eid,
                        "liveness": _liveness(what + " || " + body),
                        "mechanism": mech,
                        "what": what,
                        "issue": body,
                        "citations": sorted(
                            {f"{a}:{b}" for a, b in _FILELINE.findall(what + " " + body)}
                        ),
                        "refs": sorted(
                            {
                                t
                                for g in _ANY_REF.findall(what + " " + body)
                                for t in re.findall(r"[GN]\d+", g)
                            }
                        ),
                        "also": [
                            _CROSS_RECORD.get(k, k) for k in _ALSO.get(key, [])
                        ],
                    }
                )
    # apply the cross-record merge to mechanism keys that are themselves gaps
    for e in entries:
        e["mechanism"] = _CROSS_RECORD.get(e["mechanism"], e["mechanism"])
    # an entry with no explicit liveness token inherits its mechanism's
    by_mech = {}
    for e in entries:
        by_mech.setdefault(e["mechanism"], []).append(e)
    for mech, es in by_mech.items():
        if any(x["liveness"] == "live" for x in es):
            group = "live"
        elif any(x["liveness"] == "dormant" for x in es):
            group = "dormant"
        else:
            group = "unlabelled"
        for e in es:
            e["mech_liveness"] = group
            if e["liveness"] == "unlabelled":
                e["liveness_effective"] = group + " (inherited)"
            else:
                e["liveness_effective"] = e["liveness"]
    return entries


# --- pins --------------------------------------------------------------------

_XFAIL = re.compile(r"@pytest\.mark\.xfail")


def pins():
    """Parse the strict xfail pins out of test/test_hook_order.py."""
    src = PIN_FILE.read_text(encoding="utf-8").splitlines()
    out = []
    cls = None
    i = 0
    while i < len(src):
        line = src[i]
        m = re.match(r"class (\w+)", line)
        if m:
            cls = m.group(1)
        if _XFAIL.search(line):
            j = i
            block = []
            while j < len(src) and not src[j].strip().startswith("def "):
                block.append(src[j].strip())
                j += 1
            fn = re.match(r"def (\w+)", src[j].strip()).group(1) if j < len(src) else "?"
            blob = " ".join(block)
            reason = re.sub(r'"\s+"', "", blob)
            strict = "strict=True" in blob
            # which record does this pin cite?  the EARLIEST seam name in the
            # reason -- pins open with "<seam> audit gap ..." and may name
            # other seams later in the prose.
            hits = [(reason.find(s), s) for s in SEAMS if s in reason]
            seam = min(hits)[1] if hits else None
            gid = None
            gm = re.search(r"\b(?:gap|guard) ([GN]\d+)", reason)
            if gm:
                gid = gm.group(1)
            # steps are only used to locate the mechanism when no gap id is named
            steps = (
                []
                if gid
                else re.findall(r"\bstep[s]? (\d+[a-z]?(?:\s*,\s*\d+[a-z]?)*)", reason)
            )
            out.append(
                {
                    "line": i + 1,
                    "test": f"test/test_hook_order.py::{cls}::{fn}",
                    "strict": strict,
                    "seam": seam,
                    "gap": gid,
                    "steps": steps,
                    "reason": reason[:400],
                }
            )
            i = j
        i += 1
    return out


def pin_map():
    """mechanism key -> list of pinning tests."""
    entries = extract()
    by_key = {}
    for e in entries:
        by_key.setdefault(e["id"], e["mechanism"])
    out = {}
    for p in pins():
        if not p["seam"]:
            continue
        keys = []
        if p["gap"]:
            keys.append(f"{p['seam']}/{p['gap']}")
        for s in p["steps"]:
            for tok in re.findall(r"\d+[a-z]?", s):
                keys.append(f"{p['seam']}/step{tok}")
        mechs = []
        for k in keys:
            k = _CROSS_RECORD.get(k, k)
            mechs.append(by_key.get(k, k))
        for m in dict.fromkeys(mechs):
            out.setdefault(m, []).append(p["test"])
    return out


# --- commands ----------------------------------------------------------------


def cmd_counts():
    entries = extract()
    mechs = {}
    for e in entries:
        mechs.setdefault(e["mechanism"], []).append(e)
    pm = pin_map()
    live_mechs = [m for m, es in mechs.items() if any(x["liveness"] == "live" for x in es)]
    eff_live = sum(1 for e in entries if e["mech_liveness"] == "live")
    print(f"gap entries        : {len(entries)}")
    print(f"  labelled live    : {sum(1 for e in entries if e['liveness'] == 'live')}")
    print(f"  labelled dormant : {sum(1 for e in entries if e['liveness'] == 'dormant')}")
    print(f"  unlabelled       : {sum(1 for e in entries if e['liveness'] == 'unlabelled')}"
          " (inherit their mechanism's liveness)")
    print(f"  in a LIVE mech   : {eff_live}")
    print(f"  in a dormant mech: {len(entries) - eff_live}")
    print(f"distinct mechanisms: {len(mechs)}")
    print(f"  with a live entry: {len(live_mechs)}")
    print(f"  pinned           : {sum(1 for m in mechs if m in pm)}")
    print(f"  unpinned         : {sum(1 for m in mechs if m not in pm)}")
    print(f"strict xfail pins  : {sum(1 for p in pins() if p['strict'])}"
          f" (of {len(pins())} xfail decorators in test/test_hook_order.py)")
    print()
    print("per seam (entries / mechanisms anchored there / live entries):")
    for seam in SEAMS:
        es = [e for e in entries if e["seam"] == seam]
        anchored = {m for m in mechs if m.startswith(seam + "/")}
        print(
            f"  {seam:24s} {len(es):3d} / {len(anchored):3d} / "
            f"{sum(1 for e in es if e['liveness'] == 'live'):3d}"
        )


def cmd_list():
    for e in extract():
        head = re.sub(r"\s+", " ", e["what"])[:110]
        print(f"{e['id']:38s} {e['liveness']:9s} {e['mechanism']:34s} {head}")


def cmd_mechanisms():
    entries = extract()
    mechs = {}
    for e in entries:
        mechs.setdefault(e["mechanism"], []).append(e)
    pm = pin_map()
    for m, es in sorted(mechs.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        live = "LIVE" if any(x["liveness"] == "live" for x in es) else "dormant"
        title = MECHANISM_TITLES.get(m, "")
        pinstr = ("PINNED: " + ", ".join(t.split("::")[-1] for t in pm[m])) if m in pm else "unpinned"
        print(f"{m:34s} n={len(es):2d} {live:8s} {pinstr}")
        if title:
            print(f"    {title}")
        print("    sites: " + ", ".join(x["id"].split("/")[1] + f"@{x['seam']}" for x in es))


def cmd_pins():
    for p in pins():
        print(
            f"{p['line']:5d} strict={p['strict']} {p['test'].split('::', 1)[1]:70s} "
            f"{p['seam']}/{p['gap']} steps={p['steps']}"
        )


def cmd_unpinned():
    entries = extract()
    mechs = {}
    for e in entries:
        mechs.setdefault(e["mechanism"], []).append(e)
    pm = pin_map()
    for m, es in sorted(mechs.items()):
        if m in pm:
            continue
        live = "LIVE" if any(x["liveness"] == "live" for x in es) else "dormant"
        print(f"{m:34s} n={len(es):2d} {live}")


def cmd_refs():
    for e in extract():
        if e["refs"]:
            print(f"{e['id']:38s} -> {','.join(e['refs'])}")


def cmd_json():
    json.dump(extract(), sys.stdout, indent=1)


GAME_ROOT = Path(r"c:\Users\Perry\Desktop\Slay the Spire 2")
QUEUE_DOC = ROOT / "docs" / "audit" / "GAP-QUEUE.md"
_CITE = re.compile(r"`?([\w][\w./-]*\.(?:py|cs)):(\d+)(?:-(\d+))?`?")


def _candidates(name: str):
    """Every file a citation could name, sim tree first.

    Citations are written the way the records write them: repo-relative for the
    sim (``sts2_rl/cmds.py``), often sim-relative (``relics/anchor.py``), and by
    bare filename or partial path for the game (``Hook.cs``,
    ``Events/DenseVegetation.cs``).  Some bare names are ambiguous -- the game
    has both ``Models/Monsters/PaelsLegion.cs`` and ``Models/Relics/PaelsLegion.cs``.
    """
    out = []
    for base, prefix in (
        (ROOT, ""),
        (ROOT, "sts2_rl/"),
        (GAME_ROOT, ""),
        (GAME_ROOT, "src/Core/"),
    ):
        p = base / (prefix + name)
        if p.exists():
            out.append(p)
    out += list(GAME_ROOT.glob(f"src/**/{name}"))
    out += list(ROOT.glob(f"sts2_rl/**/{name}"))
    return list(dict.fromkeys(out))


def cmd_cite_check():
    """Every file:line cited in GAP-QUEUE.md must resolve to a real line."""
    text = QUEUE_DOC.read_text(encoding="utf-8")
    seen = {}
    bad = []
    for name, a, b in _CITE.findall(text):
        lo, hi = int(a), int(b or a)
        cands = _candidates(name)
        if not cands:
            bad.append(f"UNRESOLVED FILE  {name}:{a}")
            continue
        for p in cands:
            if p not in seen:
                seen[p] = len(
                    p.read_text(encoding="utf-8", errors="replace").splitlines()
                )
        # a citation is good if ANY candidate file covers the range
        if not any(1 <= lo and hi <= seen[p] for p in cands):
            longest = max(seen[p] for p in cands)
            bad.append(f"OUT OF RANGE     {name}:{a}-{b} (longest candidate has {longest} lines)")
    total = len(_CITE.findall(text))
    print(f"citations in {QUEUE_DOC.name}: {total}, files resolved: {len(seen)}")
    for line in sorted(set(bad)):
        print("  " + line)
    print(f"{len(set(bad))} problem(s)")
    return 1 if bad else 0


COMMANDS = {
    "counts": cmd_counts,
    "list": cmd_list,
    "mechanisms": cmd_mechanisms,
    "pins": cmd_pins,
    "unpinned": cmd_unpinned,
    "refs": cmd_refs,
    "json": cmd_json,
    "cite-check": cmd_cite_check,
}


def main(argv):
    if len(argv) != 2 or argv[1] not in COMMANDS:
        print(__doc__)
        print("commands: " + ", ".join(COMMANDS))
        return 2
    COMMANDS[argv[1]]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
