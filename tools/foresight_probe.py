"""Foresight probe — the v25 gate suite (plan 2026-08-26-foresight-v25-v26).

Packages the 2026-08-26 scratchpad probes (`scenario.py`, `probe_foresight.py`,
`probe_history.py`) into a scenario registry with a CLI. The MECHANICS are a
verbatim port — the same scripted candidate turns, the same
`random.Random(1000 + trial)` draw-pile shuffles, the same greedy continuation
under the loaded policy — so the numbers stay comparable to that session's v23
baseline (line A 14.0% MC death, line B 8.7%, N=300). Only the packaging
(registry + CLI + gate lines) is new.

The scenario is the streamed turn-7 two-Wriggler elite: hand
Anger/Strike/Strike/Defend/Defend, a 20-card draw pile carrying 7 Infection +
1 Greed, enemies LEFT 10/19 Str2 (WRIGGLE now, bites NEXT turn) and RIGHT
16/22 Str4 (ATTACK 11 now), player 15/80 with 3 energy, relics burning_blood /
cursed_pearl / book_of_five_rings(cards_added=3) / festive_popper, ascension 10.

The two candidate lines, and which is which:

  A "kill RIGHT" — kills the enemy that is attacking THIS turn. Removes the
    visible 11 damage but leaves the LEFT Wriggler, whose bite lands next
    turn into a hand full of Infection. This is the TAIL-RISKY line
    (v23 baseline: 14.0% death).
  B "kill LEFT"  — kills the enemy that will attack NEXT turn, eating the
    visible 11 now behind Defends. This is the TAIL-SAFE line
    (v23 baseline: 8.7% death).

So tail-safe target index = 0 (left), tail-risky target index = 1 (right).

Gates (all three are expected to FAIL on v23 — flipping them is the point of
v25):
  GATE vgap  V(after the tail-safe first card) > V(after the tail-risky one)
  GATE mass  attack-mass(tail-safe target)     > attack-mass(tail-risky one)
  GATE mc    the policy's own greedy line is within 2pts of the best
             scripted line's Monte-Carlo death rate

Usage:
    foresight_probe.py CKPT [--mc N] [--pwin-calibration EPISODES]
"""
from __future__ import annotations

import argparse
import random
import sys
from collections import deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import torch

from sts2_rl import make_card, make_relic
from sts2_rl.cmds import PowerCmd
from sts2_rl.driver import DecisionKind
from sts2_rl.evaluation import load_torch_policy
from sts2_rl.full_env import decode_combat_action
from sts2_rl.monsters.base import (
    Intent,
    IntentHistoryEntry,
    MAX_INTENT_HISTORY,
    MoveType,
    Encounter,
    intent_flags,
)
from sts2_rl.monsters.overgrowth.phrog_parasite import Wriggler
from sts2_rl.powers import StrengthPower
from sts2_rl.rooms import RoomType
from sts2_rl.run_env import STS2RunEnv
from sts2_rl.tensor_obs import TensorObs

ASC = 10
DEVICE = "cpu"

HAND = ["anger", "strike", "strike", "defend", "defend"]
DRAW = (["bash", "defend", "defend", "strike", "strike", "strike",
         "anger", "anger", "pommel_strike", "pommel_strike",
         "inflame", "uppercut"] + ["infection"] * 7 + ["greed"])

#: enemy list index of the Wriggler that attacks NEXT turn (WRIGGLE now) —
#: killing it is the tail-safe play. Index 1 (ATTACK 11 now) is tail-risky.
TAIL_SAFE_TGT = 0
TAIL_RISKY_TGT = 1

#: the scripted candidate turns, first action first. Keys carry the baseline
#: session's own labels so old transcripts line up.
WRIGGLER_LINES = {
    "A kill-RIGHT (v23 greedy)": [("Strike", 1), ("Strike", 1), ("Anger", 1), ("Defend", None)],
    "B kill-LEFT  (user line) ": [("Strike", 0), ("Anger", 0), ("Defend", None), ("Defend", None)],
}


# ── scenario construction (port of probe_foresight.build) ───────────────────
def _build_wrigglers(shuffle_rng=None, *, history: bool = False):
    """The turn-7 two-Wriggler state. `shuffle_rng`, when given, shuffles the
    draw pile in place exactly as the scratchpad probe did.

    IN-COMBAT PREDICATE (applies to every loop in this file): this tool
    deliberately keeps the ported `request.kind == DecisionKind.COMBAT` test
    of the scratchpad probe, so the numbers stay comparable to the N=300 v23
    baseline. `forksim.in_combat(request)` is the stricter and better
    predicate — it is the one to use for any future scenario carrying
    selector cards or generator potions, whose sub-decisions are inside the
    combat but do not carry the COMBAT kind. Switching to it changes which
    steps the greedy/tail loops walk, so it requires re-running the N=300
    baseline before any gate read is comparable again."""
    env = STS2RunEnv(ascension=ASC)
    env.reset(seed=0)
    while env._request is None or env._request.kind != DecisionKind.COMBAT:
        env.step(int(np.flatnonzero(env.action_masks())[0]))
    c = env._request.combat
    run = env._request.run
    p = c.player

    def mint(cid):
        card = make_card(cid)
        card.reset_combat_state()
        card.combat = c
        c.hooks.register(card)
        return card

    p.hand = [mint(x) for x in HAND]
    p.draw_pile = [mint(x) for x in DRAW]
    if shuffle_rng is not None:
        shuffle_rng.shuffle(p.draw_pile)
    p.discard_pile = []
    p.block = 0
    p.energy = 3
    p.max_hp = 80
    p.hp = 15

    c.encounter = Encounter(id="scenario_wrigglers", monster_classes=[Wriggler, Wriggler])
    c.enemies = c.encounter.seat_in_slots(
        [Wriggler(c.hooks, start_stunned=False, slot=2),    # even slot -> WRIGGLE
         Wriggler(c.hooks, start_stunned=False, slot=1)])   # odd slot  -> NASTY_BITE
    for i, e in enumerate(c.enemies):
        e.net_id = i + 1
    left, right = c.enemies
    left.max_hp, left.hp = 19, 10
    right.max_hp, right.hp = 22, 16
    PowerCmd.apply(c.hooks, left, StrengthPower, 2)
    PowerCmd.apply(c.hooks, right, StrengthPower, 4)

    relics = [make_relic(r) for r in ("burning_blood", "cursed_pearl",
                                      "book_of_five_rings", "festive_popper")]
    for r in relics:
        if r.id == "book_of_five_rings":
            r.cards_added = 3
    run.relics = list(relics)
    c.relics = list(relics)
    for r in c.relics:
        r.attach(c)

    c.room_type = RoomType.ELITE
    c.turn = 7
    c.round_number = 7
    run.hp, run.max_hp, run.gold = 15, 80, 64

    if history:
        _populate_history(c)
    return env, c, run, p


def _bite_entry(dmg):
    it = Intent(MoveType.ATTACK, damage=dmg)
    return IntentHistoryEntry(intent_flags(it, False), dmg, 1, dmg, None)


def _wriggle_entry():
    it = Intent(MoveType.BUFF, also=(MoveType.STATUS_CARD,), status_count=1)
    return IntentHistoryEntry(intent_flags(it, False), None, None, None, 1)


def _populate_history(c):
    """The true alternation the overlay showed (port of probe_history):
    left (net 1) is BUFF now, history most-recent-first bite9/wriggle/bite9;
    right (net 2) is ATTACK 11 now, history wriggle/bite9/wriggle."""
    c._intent_history[1] = deque([_bite_entry(9), _wriggle_entry(), _bite_entry(9)],
                                 maxlen=MAX_INTENT_HISTORY)
    c._intent_history[2] = deque([_wriggle_entry(), _bite_entry(9), _wriggle_entry()],
                                 maxlen=MAX_INTENT_HISTORY)


def scenario_wrigglers(shuffle_rng=None):
    env, c, run, p = _build_wrigglers(shuffle_rng, history=False)
    return env, c, run, p, WRIGGLER_LINES


def scenario_wrigglers_history(shuffle_rng=None):
    env, c, run, p = _build_wrigglers(shuffle_rng, history=True)
    return env, c, run, p, WRIGGLER_LINES


SCENARIOS = {
    "wrigglers": scenario_wrigglers,
    "wrigglers_history": scenario_wrigglers_history,
}


# ── action helpers (port of probe_foresight.find_action) ────────────────────
def find_action(env, c, p, name, target):
    for a in np.flatnonzero(env.action_masks()):
        kind, slot, tgt = decode_combat_action(int(a))
        if kind != "play" or slot >= len(p.hand):
            continue
        if p.hand[slot].name != name:
            continue
        if target is None or tgt == target:
            return int(a)
    raise RuntimeError(f"no legal action for {name}->{target}")


def _probs(policy, env):
    obs = env._build_obs()
    mask = env.action_masks()
    obs_t = TensorObs.from_dict(obs, device=DEVICE)[None]
    mask_t = torch.as_tensor(mask, dtype=torch.bool, device=DEVICE).unsqueeze(0)
    with torch.no_grad():
        probs = torch.softmax(policy.model.action_logits(obs_t, mask_t), dim=-1)[0].numpy()
    return probs, mask


def attack_mass(policy, env, p):
    """(atk-mass on LEFT, atk-mass on RIGHT, Defend mass) — port of
    probe_history.dist."""
    probs, mask = _probs(policy, env)

    def mass(pred):
        s = 0.0
        for a in np.flatnonzero(mask):
            kind, slot, tgt = decode_combat_action(int(a))
            if kind == "play" and slot < len(p.hand) and pred(p.hand[slot].name, tgt):
                s += probs[a]
        return s

    atkL = mass(lambda nm, t: nm in ("Strike", "Anger") and t == 0)
    atkR = mass(lambda nm, t: nm in ("Strike", "Anger") and t == 1)
    dfn = mass(lambda nm, t: nm == "Defend")
    return atkL, atkR, dfn


def value_after(policy, builder, name, tgt):
    """Critic V of the post-state after playing one card (port of
    probe_foresight's critic block: the same `random.Random(7)` build)."""
    env, c, run, p = builder(random.Random(7))[:4]
    env.step(find_action(env, c, p, name, tgt))
    with torch.no_grad():
        v = policy.model.get_value(TensorObs.from_dict(env._build_obs(), device=DEVICE)[None])
    return float(v)


# ── Monte Carlo (port of probe_foresight.run_trial) ─────────────────────────
def run_trial(policy, builder, script, trial):
    """One continuation. `script=None` lets the policy play turn 7 greedily
    (the 'policy's own greedy line' the mc gate measures); otherwise the
    scripted cards are played and the turn is ended with `env.step(0)`,
    exactly as the scratchpad probe did.

    The greedy branch leaves turn 7 on ANY of three exits: it selects END
    TURN, the episode terminates, or the decision the env now wants is no
    longer a decision inside THIS combat (the policy killed the last enemy
    during turn 7, so no END TURN is ever offered). Truncation is NOT one of
    those exits: `trunc` is read from `env.step` but never breaks the loop,
    so this guard covers the leaving-THIS-combat case only.
    Without that third guard the loop would walk on through the post-combat
    map/reward decisions for 80 steps and then fall into a tail loop whose
    own `combat is c` condition is already false, reporting `died=False`
    unconditionally and silently false-PASSing GATE mc. Unreachable in the
    two shipped scenarios but the registry is built to grow.

    On the combat-won-during-turn-7 exit there is no turn 8, so the returned
    `hp_after_t8_start` is the player's HP at the moment the combat ended —
    still the right "HP the player carries out of this turn" quantity the
    column means, just measured one enemy phase earlier (there was none).
    The tail loop is then a no-op and `died` stays False, which is correct:
    a won combat with a live player."""
    env, c, run, p = builder(random.Random(1000 + trial))[:4]
    if script is None:
        for _ in range(80):
            if (env._request is None
                    or env._request.kind != DecisionKind.COMBAT
                    or getattr(env._request, "combat", None) is not c):
                break
            obs = env._build_obs()
            mask = env.action_masks()
            a = int(policy(env, obs, mask))
            if not mask[a]:
                a = int(np.flatnonzero(mask)[0])
            ended = decode_combat_action(a)[0] == "end"
            _, _, term, trunc, info = env.step(a)
            if term:
                return p.hp, run.hp, not info.get("is_success", False), c.turn
            if ended:
                break
    else:
        for name, tgt in script:
            env.step(find_action(env, c, p, name, tgt))
        env.step(0)   # end turn 7 -> enemies act -> turn 8 begins
    hp_after_t8_start = p.hp
    died = False
    steps = 0
    while (env._request is not None and env._request.kind == DecisionKind.COMBAT
           and getattr(env._request, "combat", None) is c and steps < 80):
        obs = env._build_obs()
        mask = env.action_masks()
        a = int(policy(env, obs, mask))
        if not mask[a]:
            a = int(np.flatnonzero(mask)[0])
        _, _, term, trunc, info = env.step(a)
        steps += 1
        if term:
            died = not info.get("is_success", False)
            break
    return hp_after_t8_start, run.hp, died, c.turn


def monte_carlo(policy, builder, script, n):
    t8, end, deaths, low, turns = [], [], 0, 0, []
    for t in range(n):
        h8, hend, died, tn = run_trial(policy, builder, script, t)
        t8.append(h8)
        end.append(0 if died else hend)
        deaths += died
        low += (died or hend <= 5)
        turns.append(tn)
    return {
        "hp_t8": float(np.mean(t8)),
        "hp_end": float(np.mean(end)),
        "p_low": low / n,
        "p_death": deaths / n,
        "turns": float(np.mean(turns)),
    }


# ── per-scenario report ─────────────────────────────────────────────────────
def _gate(name, ok, detail):
    print(f"GATE {name} {'PASS' if ok else 'FAIL'}  {detail}")
    return ok


def run_scenario(policy, sc_name, builder, mc_n):
    print(f"\n{'=' * 70}\n=== scenario: {sc_name} ===\n{'=' * 70}")
    env, c, run, p, lines = builder(random.Random(7))
    print(f"player {p.hp}/{p.max_hp}  energy {p.energy}  block {p.block}  "
          f"turn {c.turn}  asc {ASC}  room {c.room_type.name}")
    for i, e in enumerate(c.enemies):
        print(f"  enemy[{i}] {type(e).__name__} {e.hp}/{e.max_hp} str={e.strength} "
              f"intent={e.current_intent.move_type.name}")
    print("hand:", [f"{cd.name}({cd.energy_cost})" for cd in p.hand])
    print(f"draw {len(p.draw_pile)}  discard {len(p.discard_pile)}")

    # --- policy mass on each line's first action ---------------------------
    probs, mask = _probs(policy, env)
    print("\npolicy mass on each candidate line's first action:")
    first_mass = {}
    for nm, script in lines.items():
        cname, ctgt = script[0]
        a = find_action(env, c, p, cname, ctgt)
        first_mass[nm] = float(probs[a])
        print(f"  {nm:<28} {cname}->{ctgt}  a={a:<4} {probs[a] * 100:6.2f}%")
    greedy_a = int(np.flatnonzero(mask)[np.argmax(probs[np.flatnonzero(mask)])])
    gk, gslot, gtgt = decode_combat_action(greedy_a)
    gname = p.hand[gslot].name if gk == "play" and gslot < len(p.hand) else gk
    print(f"  GREEDY first action: a={greedy_a} {gk} {gname} -> {gtgt}")

    atkL, atkR, dfn = attack_mass(policy, env, p)
    print(f"\nattack-mass  LEFT(tail-safe)={atkL:6.1%}  "
          f"RIGHT(tail-risky)={atkR:6.1%}  defend={dfn:6.1%}")

    # --- critic V of each post-first-action state --------------------------
    print("\ncritic V(s') after the first card of each line:")
    v_by_line = {}
    for nm, script in lines.items():
        cname, ctgt = script[0]
        v_by_line[nm] = value_after(policy, builder, cname, ctgt)
        print(f"  {nm:<28} ({cname}->{ctgt}): V = {v_by_line[nm]:+.4f}")
    v_safe = value_after(policy, builder, "Strike", TAIL_SAFE_TGT)
    v_risky = value_after(policy, builder, "Strike", TAIL_RISKY_TGT)
    print(f"  tail-safe  Strike->LEFT (10hp): V = {v_safe:+.4f}")
    print(f"  tail-risky Strike->RIGHT(16hp): V = {v_risky:+.4f}")

    # --- Monte Carlo --------------------------------------------------------
    print(f"\nMonte Carlo, N={mc_n} continuations per line (greedy after turn 7):")
    print(f"{'line':<28} {'E[hp@t8]':>8} {'E[hp end]':>9} {'P(hp<=5)':>8} "
          f"{'P(death)':>8} {'E[turns]':>8}")
    mc = {}
    for nm, script in lines.items():
        mc[nm] = monte_carlo(policy, builder, script, mc_n)
        r = mc[nm]
        print(f"{nm:<28} {r['hp_t8']:8.2f} {r['hp_end']:9.2f} "
              f"{r['p_low']:8.1%} {r['p_death']:8.1%} {r['turns']:8.2f}")
    greedy_mc = monte_carlo(policy, builder, None, mc_n)
    print(f"{'GREEDY (policy plays t7)':<28} {greedy_mc['hp_t8']:8.2f} "
          f"{greedy_mc['hp_end']:9.2f} {greedy_mc['p_low']:8.1%} "
          f"{greedy_mc['p_death']:8.1%} {greedy_mc['turns']:8.2f}")

    # --- gates --------------------------------------------------------------
    print()
    ok = []
    ok.append(_gate("vgap", v_safe > v_risky,
                    f"V(tail-safe)={v_safe:+.4f} vs V(tail-risky)={v_risky:+.4f} "
                    f"(gap {v_safe - v_risky:+.4f})"))
    ok.append(_gate("mass", atkL > atkR,
                    f"attack-mass tail-safe={atkL:.1%} vs tail-risky={atkR:.1%}"))
    best_nm = min(mc, key=lambda k: mc[k]["p_death"])
    best = mc[best_nm]["p_death"]
    slack = greedy_mc["p_death"] - best
    ok.append(_gate("mc", slack <= 0.02 + 1e-12,
                    f"greedy P(death)={greedy_mc['p_death']:.1%} vs best "
                    f"({best_nm.strip()}) {best:.1%} -> +{slack * 100:.1f}pts "
                    f"(budget 2.0pts)"))
    return all(ok)


# ── P(win) head calibration ─────────────────────────────────────────────────
def pwin_calibration(ckpt_path, episodes):
    env = STS2RunEnv(ascension=ASC)
    policy, ckpt = load_torch_policy(ckpt_path, env_kind="run", env=env,
                                     device=DEVICE, sample=True, seed=0)
    if not any(k.startswith("aux_win_head") for k in ckpt["model"]):
        print("\n=== P(win) calibration ===")
        print("SKIP (no aux_win_head params)")
        return
    model = policy.model
    print(f"\n=== P(win) calibration — {episodes} sampled episodes, asc {ASC} ===")
    confs, labels = [], []
    for ep in range(episodes):
        obs, info = env.reset(seed=ep)
        ep_conf = []
        term = trunc = False
        success = False
        while not (term or trunc):
            mask = env.action_masks()
            with torch.no_grad():
                cf = model.critic_encoder(TensorObs.from_dict(obs, device=DEVICE)[None])
                ep_conf.append(float(torch.sigmoid(model.aux_win_head(cf).squeeze(-1))[0]))
            a = int(policy(env, obs, mask))
            if not mask[a]:
                a = int(np.flatnonzero(mask)[0])
            obs, r, term, trunc, info = env.step(a)
            success = bool(info.get("is_success", success))
        confs.extend(ep_conf)
        labels.extend([1.0 if success else 0.0] * len(ep_conf))
    confs = np.asarray(confs)
    labels = np.asarray(labels)
    n = len(confs)
    print(f"decisions {n}  base rate (win-labelled decisions) {labels.mean():.3%}  "
          f"mean P(win) {confs.mean():.3%}")
    print(f"{'bucket':<12} {'n':>7} {'mean P(win)':>12} {'actual':>9} {'gap':>8}")
    ece = 0.0
    edges = np.linspace(0.0, 1.0, 11)
    for lo, hi in zip(edges[:-1], edges[1:]):
        sel = (confs >= lo) & (confs < hi if hi < 1.0 else confs <= hi)
        k = int(sel.sum())
        if k == 0:
            print(f"[{lo:.1f},{hi:.1f})".ljust(12) + f"{0:>7}" + " " * 32)
            continue
        conf = float(confs[sel].mean())
        acc = float(labels[sel].mean())
        ece += (k / n) * abs(acc - conf)
        print(f"[{lo:.1f},{hi:.1f})".ljust(12) + f"{k:>7} {conf:>12.3f} "
              f"{acc:>9.3f} {acc - conf:>+8.3f}")
    print(f"ECE = {ece:.4f}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ckpt")
    ap.add_argument("--mc", type=int, default=300,
                    help="Monte-Carlo continuations per line (baseline: 300)")
    ap.add_argument("--pwin-calibration", type=int, default=0, metavar="EPISODES",
                    help="also run the aux_win_head reliability check over E "
                         "sampled episodes")
    ap.add_argument("--scenario", action="append", default=None,
                    choices=sorted(SCENARIOS),
                    help="restrict to these scenarios (default: all)")
    args = ap.parse_args(argv)

    env0 = STS2RunEnv(ascension=ASC)
    policy, ckpt = load_torch_policy(args.ckpt, env_kind="run", env=env0,
                                     device=DEVICE, sample=False, seed=0)
    print(f"ckpt {args.ckpt}")
    print(f"  schema {ckpt.get('obs_schema')}  arch {ckpt.get('arch')}  "
          f"aux_win_head in ckpt: "
          f"{any(k.startswith('aux_win_head') for k in ckpt['model'])}")

    names = args.scenario or list(SCENARIOS)
    results = {nm: run_scenario(policy, nm, SCENARIOS[nm], args.mc) for nm in names}

    if args.pwin_calibration:
        pwin_calibration(args.ckpt, args.pwin_calibration)

    print("\n=== summary ===")
    for nm, ok in results.items():
        print(f"  {nm:<20} {'ALL GATES PASS' if ok else 'GATES FAIL'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
