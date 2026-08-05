r"""Offline predicted-vs-realized diff for RunReplays auto-validation
(§4 of the autovalidation design).

The mod's autoplay loop (AutoplaySession) replays an exported ``actions.sts2replay``
on the real game and dumps, per command, the game's *realized* state:

  autoplay-out/{runId}/
    replayed.sts2replay   # each command re-emitted with the game's live
                          #   "|| Hand: [...] Enemies: [name hp/maxhp]" annotation
    annotations.jsonl     # one GameStateSnapshot JSON per command (richer:
                          #   relics, potions, powers, piles, gold, floor)
    result.json           # { target, commandsConsumed, lastFloor, stalled, ... }

The exported file carries the sim's *predicted* annotations (same grammar). This
tool diffs predicted vs realized per command and reports Hand/Enemies deltas in
the same shape converge_triage's DETECTOR 4 uses, so the two loops read alike.
The mod stays dumb; the divergence semantics live here beside the sim toolchain.

Usage:  py tools/validate_export.py PREDICTED.sts2replay AUTOPLAY_OUT_DIR
        py tools/validate_export.py PREDICTED.sts2replay --realized replayed.sts2replay --jsonl annotations.jsonl

Exit code 0 iff the realized run matched the prediction command-for-command with
no stall; 1 on any divergence, early stop, or stall (CI-friendly).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]          # sts2-rl/
sys.path.insert(0, str(_REPO))

from sts2_rl.conformance.comparators import Divergence
from sts2_rl.conformance.recording import EnemyState, parse_recording


def _fmt_hand(hand: list[str] | None) -> str:
    return "[" + ", ".join(hand) + "]" if hand is not None else "<none>"


def _fmt_enemies(enemies: list[EnemyState] | None) -> str:
    if enemies is None:
        return "<none>"
    return "[" + ", ".join(f"{e.name} {e.hp}/{e.max_hp}" for e in enemies) + "]"


def _show(d: Divergence) -> str:
    """Like Divergence.__str__ but labels the index a command, not a room."""
    where = f"cmd {d.command_index}" if d.command_index >= 0 else "run end"
    msg = f"[{d.stream}] {where}: expected {d.expected!r}, got {d.actual!r}"
    return f"{msg} ({d.detail})" if d.detail else msg


def _load_jsonl(path: Path) -> list[dict]:
    out: list[dict] = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def _enemies_from_snapshot(snap: dict) -> list[EnemyState] | None:
    """The realized JSONL Enemies -> the same EnemyState triple the text carries.
    Absent (out of combat) -> None, matching the text annotation's Enemies omission."""
    raw = snap.get("Enemies")
    if raw is None:
        return None
    return [EnemyState(e.get("Name", ""), e.get("CurrentHp", 0), e.get("MaxHp", 0))
            for e in raw]


def diff_annotations(predicted, realized) -> list[Divergence]:
    """Per-command predicted-vs-realized Hand/Enemies diff. Commands are the same
    scripted list on both sides, so index i aligns; a name/args mismatch means the
    realized run desynced and its downstream annotations are cascade noise."""
    out: list[Divergence] = []
    n = min(len(predicted.commands), len(realized.commands))
    if len(predicted.commands) != len(realized.commands):
        fewer = len(realized.commands) < len(predicted.commands)
        out.append(Divergence(
            "count", -1, len(predicted.commands), len(realized.commands),
            "realized stopped early (stall/divergence)" if fewer
            else "realized ran past the script (unexpected)"))

    desynced = False
    for i in range(n):
        pc, rc = predicted.commands[i], realized.commands[i]
        if (pc.name, pc.args) != (rc.name, rc.args):
            out.append(Divergence(
                "command", i, f"{pc.name} {' '.join(pc.args)}".strip(),
                f"{rc.name} {' '.join(rc.args)}".strip(),
                "command stream desynced here; later diffs are cascade"))
            desynced = True
            break

        pa, ra = pc.annotation, rc.annotation
        p_hand = pa.hand if pa else None
        r_hand = ra.hand if ra else None
        p_enem = pa.enemies if pa else None
        r_enem = ra.enemies if ra else None

        if (p_hand is not None or r_hand is not None) and p_hand != r_hand:
            out.append(Divergence("hand", i, _fmt_hand(p_hand), _fmt_hand(r_hand),
                                  f"{pc.name} {' '.join(pc.args)}".strip()))
        if (p_enem is not None or r_enem is not None) and p_enem != r_enem:
            out.append(Divergence("enemies", i, _fmt_enemies(p_enem),
                                  _fmt_enemies(r_enem),
                                  f"{pc.name} {' '.join(pc.args)}".strip()))

    return out


def crosscheck_jsonl(realized, snaps: list[dict]) -> list[Divergence]:
    """Free mod-integrity check: the realized text annotation and the JSONL
    snapshot come from the *same* pre-state, so their Enemies must agree and their
    Hand size must match. A mismatch is a mod dump bug, not a sim divergence.
    (Hand contents aren't compared: the text uses display names, the JSONL card
    ids — a different id space — so only the count is cross-checkable.)"""
    out: list[Divergence] = []
    n = min(len(realized.commands), len(snaps))
    for i in range(n):
        rc, snap = realized.commands[i], snaps[i]
        ra = rc.annotation
        text_enem = ra.enemies if ra else None
        snap_enem = _enemies_from_snapshot(snap)
        if (text_enem is not None or snap_enem is not None) and text_enem != snap_enem:
            out.append(Divergence("jsonl.enemies", i, _fmt_enemies(text_enem),
                                  _fmt_enemies(snap_enem), "text vs snapshot disagree"))

        text_hand = ra.hand if ra else None
        snap_hand = snap.get("Hand")
        if text_hand is not None and snap_hand is not None \
                and len(text_hand) != len(snap_hand):
            out.append(Divergence("jsonl.hand_size", i, len(text_hand),
                                  len(snap_hand), "text vs snapshot hand size"))
    return out


def main(predicted_path: Path, realized_path: Path,
         jsonl_path: Path | None, result_path: Path | None) -> int:
    predicted = parse_recording(predicted_path)
    realized = parse_recording(realized_path)

    print(f"=== validate_export ===")
    print(f"predicted: {predicted_path}  ({len(predicted.commands)} commands)")
    print(f"realized:  {realized_path}  ({len(realized.commands)} commands)")

    result = None
    if result_path and result_path.exists():
        result = json.loads(result_path.read_text(encoding="utf-8-sig"))
        print(f"\n[result.json] stalled={result.get('stalled')} "
              f"commandsConsumed={result.get('commandsConsumed')} "
              f"lastFloor={result.get('lastFloor')} "
              f"stateCheckDivergences={result.get('stateCheckDivergences')}")
        if result.get("stallReason"):
            print(f"             stallReason: {result['stallReason']}")

    # ---- primary: predicted-vs-realized Hand/Enemies per command ----
    divs = diff_annotations(predicted, realized)
    ann_divs = [d for d in divs if d.stream in ("hand", "enemies")]
    struct_divs = [d for d in divs if d.stream in ("count", "command")]
    print(f"\n[ANNOTATION DIFF] predicted-vs-realized Hand/Enemies: "
          f"{len(ann_divs)} divergent command(s)")
    for d in ann_divs[:20]:
        print(f"  {_show(d)}")
    if len(ann_divs) > 20:
        print(f"  ... +{len(ann_divs) - 20} more")
    for d in struct_divs:
        print(f"  [STRUCTURAL] {_show(d)}")

    # ---- free bonus: text-vs-snapshot integrity of the mod's own dumps ----
    xcheck: list[Divergence] = []
    if jsonl_path and jsonl_path.exists():
        snaps = _load_jsonl(jsonl_path)
        xcheck = crosscheck_jsonl(realized, snaps)
        print(f"\n[JSONL CROSS-CHECK] realized text vs snapshot ({len(snaps)} "
              f"snapshots): {len(xcheck)} disagreement(s) (mod dump bug if >0)")
        for d in xcheck[:10]:
            print(f"  {_show(d)}")
        if len(xcheck) > 10:
            print(f"  ... +{len(xcheck) - 10} more")
    else:
        print("\n[JSONL CROSS-CHECK] skipped (no annotations.jsonl)")

    stalled = bool(result and result.get("stalled"))
    clean = not divs and not xcheck and not stalled
    print(f"\n=== {'MATCH' if clean else 'DIVERGENCES REMAIN'} ===")
    return 0 if clean else 1


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Diff a predicted export against the "
                                            "mod's realized autoplay dump.")
    p.add_argument("predicted", type=Path,
                   help="exported (predicted) actions.sts2replay")
    p.add_argument("out_dir", type=Path, nargs="?",
                   help="autoplay-out/{runId}/ dir (holds replayed.sts2replay, "
                        "annotations.jsonl, result.json)")
    p.add_argument("--realized", type=Path,
                   help="explicit realized replayed.sts2replay (overrides out_dir)")
    p.add_argument("--jsonl", type=Path,
                   help="explicit annotations.jsonl (overrides out_dir)")
    p.add_argument("--result", type=Path,
                   help="explicit result.json (overrides out_dir)")
    return p.parse_args(argv)


if __name__ == "__main__":
    args = _parse_args(sys.argv[1:])
    d = args.out_dir
    realized = args.realized or (d / "replayed.sts2replay" if d else None)
    jsonl = args.jsonl or (d / "annotations.jsonl" if d else None)
    result = args.result or (d / "result.json" if d else None)
    if realized is None:
        sys.exit("error: give an out_dir or --realized")
    if not realized.exists():
        sys.exit(f"error: realized replay not found: {realized}")
    sys.exit(main(args.predicted, realized, jsonl, result))
