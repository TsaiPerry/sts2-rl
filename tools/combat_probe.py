"""Boss+elite fight diagnostic (v20 read; extends the 2026-08-19 boss_probe).

Replays greedy episodes (seed 0+ep, same protocol as the eval CSVs) with a
wrapped step() that samples every BOSS and ELITE combat decision. Boss
aggregation is byte-identical in method to boss_probe.py so the v18_s21
baseline tables remain comparable; elites get their own table.

Usage: combat_probe.py CKPT [EPISODES] [ASC]
"""
import sys
from collections import Counter, defaultdict

sys.path.insert(0, r"c:\Users\Perry\Desktop\sts2-rl")
import numpy as np
from sts2_rl.run_env import STS2RunEnv
from sts2_rl.rooms import RoomType
from sts2_rl.evaluation import load_torch_policy

CKPT = sys.argv[1]
EPISODES = int(sys.argv[2]) if len(sys.argv) > 2 else 150
ASC = int(sys.argv[3]) if len(sys.argv) > 3 else 10

env = STS2RunEnv(ascension=ASC)
policy, ckpt = load_torch_policy(CKPT, env_kind="run", env=env, device="cpu",
                                 sample=False, seed=0)

TRACKED = (RoomType.BOSS, RoomType.ELITE)
fights = {}          # id(combat) -> record dict (tracked fights only)
fight_order = []
last_combat = [None]

orig_step = STS2RunEnv.step

def probed_step(self, action):
    req = self._request
    c = getattr(req, "combat", None)
    if c is not None:
        run = req.run
        ids = tuple(sorted(type(e).__name__ for e in c.enemies))
        last_combat[0] = {"room": c.room_type.name, "floor": run.total_floor,
                          "act": run.act_index, "ids": ids,
                          "hp_in": None, "combat_key": id(c)}
        if c.room_type in TRACKED:
            key = id(c)
            if key not in fights:
                fights[key] = {"room": c.room_type.name,
                               "floor": run.total_floor, "act": run.act_index,
                               "ids": ids, "hp_in": c.player.hp,
                               "max_hp": c.player.max_hp,
                               "samples": [], "won": None, "hp_out": None}
                fight_order.append(key)
            fights[key]["samples"].append((c.turn, c.player.hp, c.player.block))
    result = orig_step(self, action)
    if c is not None and c.room_type in TRACKED and c.result is not None:
        fights[id(c)]["won"] = bool(c.result.player_won)
        fights[id(c)]["hp_out"] = c.player.hp
    return result

STS2RunEnv.step = probed_step

death_rooms = Counter()
for ep in range(EPISODES):
    last_combat[0] = None
    obs, info = env.reset(seed=0 + ep)
    terminated = truncated = False
    while not (terminated or truncated):
        mask = env.action_masks()
        action = int(policy(env, obs, mask))
        if not mask[action]:
            action = int(np.flatnonzero(mask)[0])
        obs, reward, terminated, truncated, info = env.step(action)
    died = terminated and not info.get("is_success", False)
    if died and last_combat[0] is not None:
        death_rooms[last_combat[0]["room"]] += 1
    if (ep + 1) % 25 == 0:
        print(f"...ep {ep+1}/{EPISODES} done ({len(fights)} tracked fights)",
              flush=True)

print(f"\n=== {EPISODES} eps @ asc {ASC}, ckpt {CKPT}, greedy seed 0+ep ===")
print(f"deaths by last-combat room type: {dict(death_rooms)}")

def turn_table(rec):
    by_turn = {}
    for t, hp, blk in rec["samples"]:
        by_turn[t] = (hp, blk)
    return sorted((t, hp, blk) for t, (hp, blk) in by_turn.items())

rows = []
for key in fight_order:
    r = fights[key]
    tt = turn_table(r)
    dmg = []
    for (t0, hp0, b0), (t1, hp1, _b1) in zip(tt, tt[1:]):
        if t1 == t0 + 1:
            dmg.append(hp0 - hp1)
    blocks = [b for _t, _hp, b in tt[:-1]]
    rows.append({**r, "n_turns": tt[-1][0] if tt else 0,
                 "dmg_per_turn": (sum(dmg)/len(dmg)) if dmg else 0.0,
                 "block_per_turn": (sum(blocks)/len(blocks)) if blocks else 0.0,
                 "zero_block_turns": sum(1 for b in blocks if b == 0),
                 "end_turns": len(blocks),
                 "hp_lost": r["hp_in"] - (r["hp_out"] if r["hp_out"] is not None
                                          else 0)})

for room in ("BOSS", "ELITE"):
    rrows = [r for r in rows if r["room"] == room]
    print(f"\n{room} fights entered: {len(rrows)}")
    by_id = defaultdict(list)
    for r in rrows:
        by_id[(r['act'], r['ids'])].append(r)
    print(f"{'act':>3} {'enemies':<40} {'n':>3} {'won':>4} | {'hp_in%':>6} "
          f"{'dmg/t':>6} {'blk/t':>6} {'0blk%':>6} {'turns':>5}")
    for (act, ids), rs in sorted(by_id.items()):
        n = len(rs)
        won = sum(1 for r in rs if r["won"])
        hp_in = sum(r["hp_in"]/r["max_hp"] for r in rs)/n
        dmg = sum(r["dmg_per_turn"] for r in rs)/n
        blk = sum(r["block_per_turn"] for r in rs)/n
        zb = sum(r["zero_block_turns"] for r in rs)/max(1, sum(r["end_turns"] for r in rs))
        trn = sum(r["n_turns"] for r in rs)/n
        print(f"{act:>3} {','.join(ids)[:40]:<40} {n:>3} {won:>4} | {100*hp_in:>5.0f}% "
              f"{dmg:>6.1f} {blk:>6.1f} {100*zb:>5.0f}% {trn:>5.1f}")
    for label, cond in [("WON", lambda r: r["won"] is True),
                        ("LOST", lambda r: r["won"] is False),
                        ("unresolved", lambda r: r["won"] is None)]:
        rs = [r for r in rrows if cond(r)]
        if not rs:
            continue
        n = len(rs)
        hp_in = sum(r["hp_in"]/r["max_hp"] for r in rs)/n
        dmg = sum(r["dmg_per_turn"] for r in rs)/n
        blk = sum(r["block_per_turn"] for r in rs)/n
        zb = sum(r["zero_block_turns"] for r in rs)/max(1, sum(r["end_turns"] for r in rs))
        trn = sum(r["n_turns"] for r in rs)/n
        hpl = sum(r["hp_lost"]/r["max_hp"] for r in rs)/n
        print(f"{label:>10}: n={n} hp_in {100*hp_in:.0f}% dmg/turn {dmg:.1f} "
              f"block/turn {blk:.1f} zero-block-turns {100*zb:.0f}% "
              f"turns {trn:.1f} hp_lost {100*hpl:.0f}%max")

lost = [r for r in rows if r["room"] == "BOSS" and r["won"] is False]
if lost:
    ratios = sorted(r["hp_in"]/r["max_hp"] for r in lost)
    print(f"\nLOST boss fights entry-hp ratios: "
          f"p10 {ratios[int(0.1*len(ratios))]:.2f} "
          f"median {ratios[len(ratios)//2]:.2f} "
          f"p90 {ratios[min(len(ratios)-1, int(0.9*len(ratios)))]:.2f}")
    healthy = sum(1 for x in ratios if x >= 0.7)
    print(f"LOST fights entered at >=70% hp: {healthy}/{len(lost)}")
