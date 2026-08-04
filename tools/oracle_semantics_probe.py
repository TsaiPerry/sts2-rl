r"""Reconcile the three 933T player-state oracles floor by floor.

For each floor F with a backup save, print one row:

  F | backup hp/gold/Shuffle | history[F] hp/gold | history[F-1] hp/gold
    | entry-arith hp (history[F].current_hp + damage_taken - hp_healed)

Alignment verdicts this table settles, per floor:
  backup==history[F]      -> backup captured POST-room-resolve state
  backup==history[F-1]    -> backup captured room-ENTRY state
  backup==entry-arith[F]  -> backup captured room-ENTRY state (same thing,
                             derived when F-1 is a rest/shop that healed)
  none of the above       -> mid-room capture or a divergent recording; flag.

Run:  py tools/oracle_semantics_probe.py
"""
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))
_DESKTOP = _REPO.parent

from sts2_rl.conformance.save import parse_save

REC = _DESKTOP / "RunReplays" / "RunReplays" / "Resources"
BK = (_DESKTOP / "sts2-run-backups" / "20260723-125401"
      / "933T39V18D-recording")

end = parse_save(REC / "933T39V18D" / "floor_49" / "run.save")

# Flatten map_point_history to absolute floors. Points are per act in walk
# order; absolute floor = 1 + points resolved before this one (Neow seeds
# total_floor to 1 — verify the offset against the known series: act 0 point 0
# must land on the floor whose backup hp is 80/76/74...).
flat = {}
floor = 1
for act_row in end.room_stats_by_act:
    for st in act_row:
        flat[floor] = st
        floor += 1

from sts2_rl.rng import RunRngType

print(f"{'F':>3} | {'backup hp':>9} {'gold':>5} {'Shuffle':>7} | "
      f"{'hist[F] hp':>10} {'gold':>5} | {'hist[F-1] hp':>12} | {'entry-arith':>11} | verdict")
for p in sorted(BK.glob("floor_*")):
    f = int(p.name.split("_")[1])
    if not (p / "run.save").exists():
        continue
    b = parse_save(p / "run.save")
    cur, prev = flat.get(f), flat.get(f - 1)
    arith = (cur.current_hp + cur.damage_taken - cur.hp_healed) if cur else None
    verdict = []
    if cur and b.player_current_hp == cur.current_hp:
        verdict.append("POST")
    if prev and b.player_current_hp == prev.current_hp:
        verdict.append("ENTRY(prev)")
    if arith is not None and b.player_current_hp == arith:
        verdict.append("ENTRY(arith)")
    print(f"{f:>3} | {b.player_current_hp:>9} {b.gold:>5} "
          f"{b.run_counters[RunRngType.SHUFFLE]:>7} | "
          f"{cur.current_hp if cur else '-':>10} "
          f"{cur.current_gold if cur else '-':>5} | "
          f"{prev.current_hp if prev else '-':>12} | "
          f"{arith if arith is not None else '-':>11} | "
          f"{'+'.join(verdict) or 'NONE'}")
