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

REC = _DESKTOP / "RunReplays" / "RunReplays" / "Resources"
SRC = _DESKTOP / "Slay the Spire 2" / "src"
MON_SRC = SRC / "Core" / "Models" / "Monsters"

# Public draw methods combat code calls directly (skip getrandbits/randbytes —
# those are randint/randrange internals; a reentrancy guard counts top-level).
_PUBLIC = ("random", "choice", "choices", "sample", "shuffle",
           "randint", "randrange", "uniform")
# Plumbing frames to skip so we name the code that *decided* to draw.
_PLUMBING = ("\\rng.py", "\\combat_rng.py", "\\hooks.py",
             "/rng.py", "/combat_rng.py", "/hooks.py")

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

_hits: dict[tuple, int] = {}          # (short_path, line, func, owner) -> n
_depth = [0]                           # reentrancy guard


def _innermost_combat_site():
    """Innermost sts2_rl frame that isn't RNG/hook plumbing — the code that
    actually decided to draw — but only when a combat.py frame is on the stack.
    Also grabs the nearest monster/card `self` for the source cross-reference."""
    import traceback
    site = None
    owner = ""
    in_combat = False
    for frame, lineno in traceback.walk_stack(None):
        fn = frame.f_code.co_filename
        if "\\combat.py" in fn or "/combat.py" in fn:
            in_combat = True
        if "sts2_rl" not in fn or any(p in fn for p in _PLUMBING):
            continue
        short = "sts2_rl" + fn.split("sts2_rl")[-1]
        if site is None:
            site = (short, lineno, frame.f_code.co_name)
        this = frame.f_locals.get("self")
        if not owner and this is not None:
            if "sts2_rl\\monsters" in short or "sts2_rl/monsters" in short \
               or "sts2_rl\\cards" in short or "sts2_rl/cards" in short:
                owner = type(this).__name__
    if site is None or not in_combat:
        return None
    return (*site, owner)


def _wrap(rng):
    for meth in _PUBLIC:
        orig = getattr(rng, meth, None)
        if orig is None:
            continue

        def make(orig):
            def wrapper(*a, **kw):
                if _depth[0] == 0:
                    site = _innermost_combat_site()
                    if site is not None:
                        _hits[site] = _hits.get(site, 0) + 1
                _depth[0] += 1
                try:
                    return orig(*a, **kw)
                finally:
                    _depth[0] -= 1
            return wrapper
        setattr(rng, meth, make(orig))


def _mon_source(mon_name: str) -> str:
    if not mon_name:
        return ""
    for cand in (mon_name, mon_name.rstrip("SM"), mon_name[:-1]):  # LeafSlimeS->LeafSlime
        f = MON_SRC / f"{cand}.cs"
        if f.exists():
            return str(f.relative_to(SRC.parent))
    hits = list(MON_SRC.glob(f"{mon_name[:5]}*.cs"))
    return str(hits[0].relative_to(SRC.parent)) if hits else "(source not found)"


def main(seed: str, floor: str, stop_after_act: int) -> None:
    base = REC / seed / floor
    rec = parse_recording(base / "actions.sts2replay")
    oracle = parse_save(base / "run.save")

    runner = ReplayRunner(rec, oracle)
    import sts2_rl.run as run_mod
    orig_init = run_mod.RunState.__init__

    def patched_init(self, *a, **kw):
        orig_init(self, *a, **kw)
        _wrap(self.rng)

    run_mod.RunState.__init__ = patched_init
    try:
        result = runner.run(stop_after_act=stop_after_act)
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

    # ---- DETECTOR 1: tripwire (wrong-stream / unseeded in-combat draws) ----
    bugs = {k: v for k, v in _hits.items() if k[2] != "__init__"}
    benign = {k: v for k, v in _hits.items() if k[2] == "__init__"}
    print(f"\n[DETECTOR 1] in-combat draws from the UNSEEDED shared rng "
          f"(wrong-stream bugs): {len(bugs)} site(s)")
    for (short, line, func, owner), n in sorted(bugs.items(), key=lambda kv: -kv[1]):
        print(f"  {n:4d}x  {short}:{line} ({func})  near={owner or '?'}")
        if owner:
            print(f"        -> source: {_mon_source(owner)}")
    print(f"\n  (benign constructor HP rolls, overwritten by Niche parity roll: "
          f"{len(benign)} site(s) / {sum(benign.values())} draws)")

    clean = (not bugs and not stream_divs and not move_divs
             and result.forced_combats == 0
             and not result.unresolved_play_card_ids)
    print(f"\n=== {'FULLY CONVERGED' if clean else 'DIVERGENCES REMAIN'} ===")


if __name__ == "__main__":
    args = sys.argv[1:]
    seed = args[0] if len(args) > 0 else "89U21BV1TZ"
    floor = args[1] if len(args) > 1 else "floor_18"
    act = int(args[2]) if len(args) > 2 else 0
    main(seed, floor, act)
