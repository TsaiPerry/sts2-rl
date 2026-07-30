"""Partition the queue's ``unlabelled`` gap entries into disjoint agent batches.

Round 11's work list is every gap entry whose record states neither LIVE nor
DORMANT.  ``gap_queue.py`` reports them; this splits them so that **no two
batches ever touch the same record file**, which is what makes the triage wave
safe to run as concurrent subagents.

Partition unit is the RECORD, never the entry: two entries in one file must go
to one agent or they race on the same JSON.

    py audit/tools/unlabelled_batches.py plan     # batch table
    py audit/tools/unlabelled_batches.py write    # emit the manifest files
"""

from __future__ import annotations

import collections
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / ".superpowers" / "sdd" / "unlabelled"

# (batch id, [record ids]) -- seams are one batch per record because a seam
# record is both the biggest and the one every content record binds back to.
SEAM_BATCHES = {
    "seam-ccc": ["creature_card_cmds"],
    "seam-power-cmd": ["power_cmd"],
    "seam-damage-turn": ["damage_pipeline", "turn_structure"],
}
# hook_dispatch is 3 entries; it rides with the two tiny content kinds.
MISC_BATCH = "misc"
MISC_RECORDS = ["hook_dispatch"]

POWER_BATCHES = 5
RELIC_BATCHES = 8


def load_entries() -> list[dict]:
    raw = subprocess.run(
        [sys.executable, str(ROOT / "audit" / "tools" / "gap_queue.py"), "json"],
        capture_output=True,
        text=True,
        check=True,
        cwd=ROOT,
    ).stdout
    return [e for e in json.loads(raw) if e["liveness"] == "unlabelled"]


def by_record(entries: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = collections.defaultdict(list)
    for e in entries:
        out[e["record"]].append(e)
    return out


def chunk(records: list[str], counts: dict[str, int], n: int) -> list[list[str]]:
    """Greedy balance on ENTRY count, not record count."""
    buckets: list[list[str]] = [[] for _ in range(n)]
    load = [0] * n
    for rec in sorted(records, key=lambda r: -counts[r]):
        i = load.index(min(load))
        buckets[i].append(rec)
        load[i] += counts[rec]
    return buckets


def build() -> dict[str, list[str]]:
    entries = load_entries()
    recs = by_record(entries)
    counts = {r: len(v) for r, v in recs.items()}

    batches: dict[str, list[str]] = {}
    claimed: set[str] = set()
    for bid, members in SEAM_BATCHES.items():
        batches[bid] = members
        claimed.update(members)

    misc = list(MISC_RECORDS)
    claimed.update(MISC_RECORDS)

    powers = sorted(r for r in recs if r.startswith("power/"))
    relics = sorted(r for r in recs if r.startswith("relic/"))
    leftovers = sorted(
        r for r in recs if r not in claimed and r not in powers and r not in relics
    )
    misc += leftovers
    batches[MISC_BATCH] = misc

    for i, group in enumerate(chunk(powers, counts, POWER_BATCHES), 1):
        batches[f"power-{i}"] = sorted(group)
    for i, group in enumerate(chunk(relics, counts, RELIC_BATCHES), 1):
        batches[f"relic-{i}"] = sorted(group)

    # Every record exactly once, every entry accounted for.
    flat = [r for group in batches.values() for r in group]
    assert len(flat) == len(set(flat)), "a record landed in two batches"
    assert set(flat) == set(recs), "a record with unlabelled entries has no batch"
    return batches


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "plan"
    entries = load_entries()
    recs = by_record(entries)
    batches = build()

    total = 0
    for bid in sorted(batches):
        n = sum(len(recs[r]) for r in batches[bid])
        total += n
        print(f"{bid:<18} {len(batches[bid]):>3} records  {n:>3} entries")
    print(f"{'TOTAL':<18} {len(recs):>3} records  {total:>3} entries")

    if cmd == "write":
        OUT.mkdir(parents=True, exist_ok=True)
        for bid in sorted(batches):
            lines = [f"# Batch `{bid}` — unlabelled gap entries to settle", ""]
            lines.append(
                f"{sum(len(recs[r]) for r in batches[bid])} entries across "
                f"{len(batches[bid])} record files. **These record files are "
                f"yours alone; no other agent writes them.**"
            )
            lines.append("")
            for rec in batches[bid]:
                kind = recs[rec][0]["kind"]
                path = (
                    f"audit/records/seam/{rec}.json"
                    if kind == "seam"
                    else f"audit/records/{rec}.json"
                )
                lines.append(f"## `{rec}`  → `{path}`")
                lines.append("")
                for e in recs[rec]:
                    lines.append(f"- **`{e['id']}`** (section `{e['section']}`, "
                                 f"key `{e['local_id']}`, mechanism `{e['mechanism']}`)")
                    lines.append(f"  - what: {e['what']}")
                    if e.get("issue"):
                        lines.append(f"  - issue: {e['issue']}")
                    if e.get("citations"):
                        lines.append(f"  - citations: {', '.join(e['citations'])}")
                lines.append("")
            (OUT / f"{bid}-brief.md").write_text("\n".join(lines), encoding="utf-8")
        print(f"\nwrote {len(batches)} manifests to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
