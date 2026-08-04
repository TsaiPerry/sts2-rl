r"""Convergence triage for SP3 Task 9: find monster-RNG divergences
*structurally*, then hand you the exact decompiled-source line to fix each
against — instead of eyeballing move-by-move divergences and bisecting.

Three signals, combined:

  DETECTOR 1  RNG TRIPWIRE (wrong-stream / unseeded draws)
      In a parity run every legitimate in-combat draw routes through a
      ``combat.combat_rng.<stream>`` (seeded RunRngSet). The run's shared
      ``run.rng`` (RunState.rng == ``combat._rng``) is UNSEEDED in the
      conformance runner, so any *in-combat* draw from it (a Thrash-class bug)
      is wrong by construction. We wrap it and record the offending file:line.
      "In-combat" is gated on a ``combat.py`` frame being on the stack (so
      legit run-level relic/map/event draws are ignored); the reported site is
      the innermost non-plumbing (rng/combat_rng/hooks excluded) sts2_rl frame,
      i.e. the code that *decided* to draw, not the dispatcher it went through.
      Constructor HP rolls (Monster.__init__ legacy randint, overwritten by the
      Niche parity roll) are bucketed separately as benign.

  DETECTOR 2  COUNTER DIFF (missing / extra draws)
      run.save stores each stream's final draw COUNT (ground truth,
      ``oracle.run_counters``). ``compare_counters`` already diffs the SP3
      combat streams at run end. A MonsterAi "expected 16 got 14" under-draw is
      a *missing* draw the tripwire can't see (e.g. the RandomBranchState
      forced-branch shortcut). Detector 2b lists the per-command Hand/Enemies
      mismatches so you can find the EARLIEST divergent room.

  REFERENCE  DECOMPILED SOURCE
      Each implicated stream/monster is mapped to its source-of-truth file so
      the correct stream and exact draw count are one Read away.

CASCADE CAVEAT: over a fully-diverged run the counter deltas and tripwire
counts are dominated by downstream cascade noise. Fix the EARLIEST divergent
room first (Detector 2b), re-run, and only trust the deltas once early rooms
converge.

Usage:  py tools/converge_triage.py [SEED] [FLOOR] [STOP_AFTER_ACT]
        (defaults: 89U21BV1TZ floor_18 0)

Paths: RunReplays recordings and the decompiled game source are expected as
siblings of the repo's parent dir; override REC/SRC below if your layout differs.
"""
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]          # sts2-rl/
sys.path.insert(0, str(_REPO))
_DESKTOP = _REPO.parent                                # .../Desktop/

from sts2_rl.conformance.recording import parse_recording
from sts2_rl.conformance.runner import ReplayRunner
from sts2_rl.conformance.save import parse_save
from sts2_rl.conformance.tripwire import Tripwire
from sts2_rl.conformance.triage import assess

REC = _DESKTOP / "RunReplays" / "RunReplays" / "Resources"
SRC = _DESKTOP / "Slay the Spire 2" / "src"
MON_SRC = SRC / "Core" / "Models" / "Monsters"

# Per-floor run.save directories (richer than Resources' 3 act boundaries).
# 933T has all 49 floors in the capture backup; other seeds fall back to
# whatever floor_N dirs exist under Resources (89U: 18/34/49).
_FLOOR_DIRS = {
    "933T39V18D": _DESKTOP / "sts2-run-backups" / "20260723-125401"
                  / "933T39V18D-recording",
}


def load_floor_saves(seed: str) -> dict:
    root = _FLOOR_DIRS.get(seed, REC / seed)
    out = {}
    for p in sorted(root.glob("floor_*")):
        f = p / "run.save"
        if f.exists():
            out[int(p.name.split("_")[1])] = parse_save(f)
    return out


# stream -> (source of truth, the invariant to check the sim against)
STREAM_SRC = {
    "MonsterAi": ("MonsterMoves/MonsterMoveStateMachine/RandomBranchState.cs",
                  "GetNextState ALWAYS draws one NextFloat per transition, even "
                  "when CannotRepeat forces a single branch."),
    "Niche": ("Entities/Creatures/Creature.cs",
              "SetUniqueMonsterHpValue rolls each creature's HP once at "
              "CreateCreature (unique among siblings), incl. mid-combat spawns."),
    "Shuffle": ("Commands/CardPileCmd.cs",
                "Deck reshuffle (StableShuffle) + random draw-pile insertion "
                "(CardPilePosition.Random => Rng.Shuffle.NextInt(Count+1))."),
    "CombatCardGeneration": ("(CardFactory.GetForCombat / GetDistinctForCombat)",
                             "One draw per generated card's random choice."),
    "CombatCardSelection": ("Cards/Thrash.cs, Commands/CardPileCmd.cs:946, etc.",
                            "Card AI picks (exhaust-an-Attack, random draw-pile "
                            "autoplay) draw here."),
    "CombatTargets": ("(auto-play random targeting)",
                      "Random ANY_ENEMY target for auto-played cards."),
}

def _mon_source(mon_name: str) -> str:
    if not mon_name:
        return ""
    for cand in (mon_name, mon_name.rstrip("SM"), mon_name[:-1]):  # LeafSlimeS->LeafSlime
        f = MON_SRC / f"{cand}.cs"
        if f.exists():
            return str(f.relative_to(SRC.parent))
    hits = list(MON_SRC.glob(f"{mon_name[:5]}*.cs"))
    return str(hits[0].relative_to(SRC.parent)) if hits else "(source not found)"


def fmt_hp_line(d) -> str:
    delta = (d.actual - d.expected) if isinstance(d.actual, int) else "?"
    hi = isinstance(delta, int) and delta > 0
    return (f"  act {d.command_index} {d.stream}: expected {d.expected} "
            f"got {d.actual} (sim {'high' if hi else 'low'} by "
            f"{abs(delta) if isinstance(delta, int) else delta})")


def fmt_floor_line(d) -> str:
    return f"      {d.stream}: expected {d.expected!r} got {d.actual!r}"


def main(seed: str, floor: str, stop_after_act: int) -> None:
    base = REC / seed / floor
    rec = parse_recording(base / "actions.sts2replay")
    oracle = parse_save(base / "run.save")

    runner = ReplayRunner(rec, oracle)
    tw = Tripwire()
    import sts2_rl.run as run_mod
    orig_init = run_mod.RunState.__init__

    def patched_init(self, *a, **kw):
        orig_init(self, *a, **kw)
        tw.install(self.rng)

    # DETECTOR 3: per-act HP checkpoints from the sibling truncation saves.
    _ACT_FLOORS = {0: "floor_18", 1: "floor_34", 2: "floor_49"}
    checkpoints = {}
    for act_index, fl in _ACT_FLOORS.items():
        f = REC / seed / fl / "run.save"
        if f.exists():
            o = parse_save(f)
            checkpoints[act_index] = (o.player_current_hp, o.player_max_hp)

    floor_saves = load_floor_saves(seed)
    run_mod.RunState.__init__ = patched_init
    try:
        result = runner.run(stop_after_act=stop_after_act,
                            player_checkpoints=checkpoints,
                            resync_player=True,
                            floor_saves=floor_saves,
                            resync_floors=True,
                            check_room_stats=True)
    finally:
        run_mod.RunState.__init__ = orig_init

    print(f"\n=== {seed}/{floor} (stop_after_act={stop_after_act}) ===")
    print(f"forced_combats={result.forced_combats}  "
          f"unresolved_play_card_ids={result.unresolved_play_card_ids}")

    # ---- DETECTOR 2: per-stream counter diff (missing/extra draws) ----
    stream_divs = [d for d in result.combat_divergences if d.command_index == -1]
    move_divs = [d for d in result.combat_divergences if d.command_index != -1]
    print(f"\n[DETECTOR 2] stream counter diffs: {len(stream_divs)}")
    for d in stream_divs:
        ref = STREAM_SRC.get(d.stream)
        delta = (d.actual - d.expected) if isinstance(d.actual, int) else "?"
        over = isinstance(delta, int) and delta > 0
        print(f"  {d.stream}: expected {d.expected} got {d.actual} "
              f"(sim {'over' if over else 'under'}-drew "
              f"{abs(delta) if isinstance(delta,int) else delta})")
        if ref:
            print(f"      -> source: {ref[0]}")
            print(f"         rule:   {ref[1]}")
    if move_divs:
        print(f"\n[DETECTOR 2b] per-command Hand/Enemies mismatches "
              f"(fix the EARLIEST first): {len(move_divs)} (first 3)")
        for d in move_divs[:3]:
            print(f"  {d}")

    # ---- DETECTOR 3: player-state deltas (HP / max-HP fidelity) ----
    hp_divs = [d for d in result.divergences
               if d.stream in ("player_hp", "player_max_hp")]
    print(f"\n[DETECTOR 3] player-state deltas at act boundaries "
          f"(oracle: run-END truncation saves "
          f"Resources/<seed>/floor_{{18,34,49}}/run.save): {len(hp_divs)}")
    _HP_SRC = {
        "player_hp": "damage/heal pipeline (DamageCmd/BlockCmd, relic heals "
                     "like BurningBlood on_combat_end, rest-site heal).",
        "player_max_hp": "max-HP-changing content (max-HP events, rest-site, "
                         "relics like Meat on the Bone / Black Blood).",
    }
    for d in hp_divs:
        print(fmt_hp_line(d))
        print(f"      -> {_HP_SRC[d.stream]}")

    # ---- DETECTOR 4: per-floor full-state deltas (resynced => independent) --
    floor_divs = [d for d in result.divergences
                  if d.stream.startswith("floor_")]
    by_floor: dict[int, list] = {}
    for d in floor_divs:
        by_floor.setdefault(d.command_index, []).append(d)
    print(f"\n[DETECTOR 4] per-floor state deltas "
          f"(oracle: per-floor backup saves; capture moment per "
          f"tools/oracle_semantics_probe.py) "
          f"({len(floor_saves)} checkpoints, resync ON — each floor's deltas "
          f"are INDEPENDENT bugs): {len(by_floor)} divergent floor(s)")
    for floor in sorted(by_floor):
        streams = ", ".join(d.stream.removeprefix("floor_")
                            for d in by_floor[floor])
        print(f"  floor {floor:2d}: {streams}")
        for d in by_floor[floor][:4]:
            print(fmt_floor_line(d))
        if len(by_floor[floor]) > 4:
            print(f"      ... +{len(by_floor[floor]) - 4} more (see streams above)")

    # ---- DETECTOR 1: tripwire (wrong-stream / unseeded in-combat draws) ----
    bugs = tw.bug_sites()
    benign = {k: v for k, v in tw.hits.items() if k[2] == "__init__"}
    print(f"\n[DETECTOR 1] in-combat draws from the UNSEEDED shared rng "
          f"(wrong-stream bugs): {len(bugs)} site(s)")
    for (short, line, func, owner), n in sorted(bugs.items(), key=lambda kv: -kv[1]):
        print(f"  {n:4d}x  {short}:{line} ({func})  near={owner or '?'}")
        if owner:
            print(f"        -> source: {_mon_source(owner)}")
    print(f"\n  (benign constructor HP rolls, overwritten by Niche parity roll: "
          f"{len(benign)} site(s) / {sum(benign.values())} draws)")

    # ---- DETECTOR 5: per-room player-state walk (map_point_history) --------
    room_divs = [d for d in result.divergences if d.stream.startswith("room_")]
    print(f"\n[DETECTOR 5] per-room state deltas vs map_point_history "
          f"(run-END capture, resync never applied): {len(room_divs)}")
    for d in room_divs[:12]:
        print(f"  floor {d.command_index:2d} {d.stream}: expected {d.expected} "
              f"got {d.actual}  ({d.detail})")
    if len(room_divs) > 12:
        print(f"  ... +{len(room_divs) - 12} more")

    verdict = assess(result, tripwire_bug_sites=bugs)
    print(f"\n=== {'FULLY CONVERGED' if verdict.clean else 'DIVERGENCES REMAIN'} ===")
    for r in verdict.reasons:
        print(f"    {r}")


if __name__ == "__main__":
    args = sys.argv[1:]
    seed = args[0] if len(args) > 0 else "89U21BV1TZ"
    floor = args[1] if len(args) > 1 else "floor_18"
    act = int(args[2]) if len(args) > 2 else 0
    main(seed, floor, act)
