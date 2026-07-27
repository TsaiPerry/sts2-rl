"""Executed evidence for monster content-audit batch 7 (Glory: Fabricator +
its four bots, the three Knights, Frog Knight, Globe Head, Owl Magistrate,
Queen + Torch Head Amalgam, Scroll of Biting, Slimed Berserker).

Every number any batch-7 record cites as "executed" is printed by one of these
probes. Run from the repo root:

    py audit/tools/monster_probes_b07.py <probe>

probes
    spawn-rng      Fabricator bot selection draws on the SHARED combat rng,
                   not on MonsterAi (Fabricator.cs:115).
    spawn-content  what a Fabricator spawn actually produces: class sequence,
                   the _last_spawned filter, MinionPower, slot/list order.
    fab-open       the Fabricator's opening roll runs through its
                   ConditionalBranchState (initial state is NOT a MoveState),
                   so _alive_count()'s combat.enemies fallback is load-bearing.
    queen-death    the Queen's intent after the amalgam dies mid-player-turn
                   (Queen.cs:221-241 AfterDeath -> SetMoveImmediate).
    scroll-rng     the Scrolls encounter's starter-move index source.
    branch-order   ConditionalBranchState first-true-wins order, both users.
    all            run them all.
"""
from __future__ import annotations

import random as _random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def _combat(monster_classes, seed=0, parity=False):
    from sts2_rl.combat import CombatState
    from sts2_rl.monsters import Encounter
    enc = Encounter(id="probe_b07", monster_classes=list(monster_classes))
    return CombatState(rng=_random.Random(seed), encounter=enc)


# ── spawn-rng ────────────────────────────────────────────────────────────────
def probe_spawn_rng():
    """Fabricator._spawn_bot draws from combat._rng; C# draws MonsterAi."""
    import inspect
    from sts2_rl.monsters.glory.fabricator import Fabricator
    src = inspect.getsource(Fabricator._spawn_bot)
    print("Fabricator._spawn_bot (sts2_rl/monsters/glory/fabricator.py:171-182):")
    for i, line in enumerate(src.splitlines()):
        if "rng" in line:
            print(f"    {line.strip()}")
    print("\nC#: Fabricator.cs:115 -> base.RunRng.MonsterAi.NextItem(items)")

    # are the two rngs the same OBJECT in each mode?
    cs = _combat([Fabricator], seed=1)
    shared = cs._rng
    ai = cs.combat_rng.monster_ai
    print(f"\nlegacy CombatRng: is_parity={cs.combat_rng.is_parity}  "
          f"combat._rng is combat_rng.monster_ai -> {shared is ai}")

    from sts2_rl.combat_rng import CombatRng
    from sts2_rl.rng import RunRngSet
    par = CombatRng.parity(RunRngSet("PROBE7"))
    print(f"parity CombatRng: is_parity={par.is_parity}  "
          f"monster_ai is a GameRandomAdapter -> "
          f"{type(par.monster_ai).__name__}")
    print("  => in a parity run the shared rng and MonsterAi are DIFFERENT "
          "streams, so the bot picked and the draws burned both diverge.")

    # how many shared-stream draws does one spawn burn, and how many MonsterAi?
    cs = _combat([Fabricator], seed=1)
    fab = cs.enemies[0]
    shared_n = _Counter(cs._rng)
    ai_n = _Counter(cs.combat_rng.monster_ai)
    cs._rng = shared_n
    cs.combat_rng._accessors["monster_ai"] = ai_n
    ctx = _ctx(cs)
    fab._spawn_bot(ctx, list(_defense()))
    print(f"\none _spawn_bot(defense): shared-rng draws={shared_n.n}  "
          f"MonsterAi draws={ai_n.n}")
    print("  C# burns exactly one MonsterAi draw (Rng.NextItem -> "
          "NextInt(0, count), Rng.cs:255-266) and zero shared-stream draws.")


class _Counter:
    """Wraps an rng and counts the calls that consume entropy."""

    def __init__(self, inner):
        object.__setattr__(self, "_inner", inner)
        object.__setattr__(self, "n", 0)

    def __getattr__(self, name):
        attr = getattr(self._inner, name)
        if callable(attr) and name in {
            "random", "randrange", "randint", "choice", "choices",
            "shuffle", "sample", "getrandbits", "uniform",
        }:
            def wrapped(*a, **k):
                object.__setattr__(self, "n", self.n + 1)
                return attr(*a, **k)
            return wrapped
        return attr


def _ctx(cs):
    from sts2_rl.combat import CombatCtx
    return CombatCtx(cs, cs.player, cs.enemies, cs.hooks)


def _defense():
    from sts2_rl.monsters.glory.fabricator import Guardbot, Noisebot
    return [Guardbot, Noisebot]


def _aggro():
    from sts2_rl.monsters.glory.fabricator import Stabbot, Zapbot
    return [Zapbot, Stabbot]


# ── spawn-content ────────────────────────────────────────────────────────────
def probe_spawn_content():
    from sts2_rl.monsters.glory.fabricator import Fabricator
    for seed in (0, 1, 2, 3):
        cs = _combat([Fabricator], seed=seed)
        fab = cs.enemies[0]
        ctx = _ctx(cs)
        fab._fabricate(ctx)          # defense then aggro, as FabricateMove does
        fab._strike_spawn = None
        fab._spawn_bot(ctx, _aggro())   # a FABRICATING_STRIKE spawn
        fab._spawn_bot(ctx, _aggro())   # and another: _last_spawned must filter
        names = [type(e).__name__ for e in cs.enemies]
        minions = ["minion" in e.powers for e in cs.enemies]
        hv = [e.powers["high_voltage"].amount if "high_voltage" in e.powers
              else None for e in cs.enemies]
        print(f"seed {seed}: enemies={names}")
        print(f"          minion={minions}  high_voltage={hv}")
        print(f"          net_ids={[getattr(e,'net_id',None) for e in cs.enemies]}")
        assert names[-1] != names[-2], "last two aggro spawns must differ"
    print("\nC# Fabricator.cs:110-118: options.Where(m => m != _lastSpawned), "
          "one shared _lastSpawned field across defense AND aggro; "
          "MinionPower 1 applied to each spawn; slot = Encounter.GetNextSlot.")
    print("C# CombatState.AddCreature (CombatState.cs:534-547) appends to "
          "_enemies REGARDLESS of slot, so slot order != list order and the "
          "sim's append is list-order faithful.")


# ── fab-open ─────────────────────────────────────────────────────────────────
def probe_fab_open():
    from sts2_rl.monsters.glory.fabricator import Fabricator
    from sts2_rl.monsters.state_machine import MoveState
    cs = _combat([Fabricator], seed=0)
    fab = cs.enemies[0]
    init = fab.machine._initial_state
    print(f"initial state: {getattr(init, 'id', '?')}  "
          f"is MoveState -> {isinstance(init, MoveState)}")
    print("  => step 30's sticky early-return does NOT fire; the opening roll "
          "walks the ConditionalBranchState and reads _can_fabricate().")
    print(f"opening move rolled: {fab._current_move.id}")
    print(f"state_log after construction: "
          f"{[s.id for s in fab.machine.state_log]}")
    print(f"_alive_count() now (enemies list present): {fab._alive_count()}")
    print("C#: CanFabricate = GetTeammatesOf(self).Count(IsAlive) < 4 and "
          "GetTeammatesOf INCLUDES the creature itself "
          "(CombatState.cs:394-400), so the fallback 1 == the true count for "
          "FabricatorNormal, whose GenerateMonsters yields exactly one monster "
          "(FabricatorNormal.cs:44-47).")


# ── queen-death ──────────────────────────────────────────────────────────────
def probe_queen_death():
    from sts2_rl.monsters.glory.queen import Queen, TorchHeadAmalgam
    cs = _combat([TorchHeadAmalgam, Queen], seed=0)
    amalgam, queen = cs.enemies[0], cs.enemies[1]
    ctx = _ctx(cs)
    # walk the Queen to the point where BURN_BRIGHT is telegraphed
    for _ in range(3):
        if queen._current_move.id == "BURN_BRIGHT_FOR_ME_MOVE":
            break
        queen.take_turn(ctx)
    print(f"queen telegraphs: {queen._current_move.id}  "
          f"intent={queen.current_intent.move_type}")
    amalgam.hp = 0                     # the amalgam dies during the player turn
    print(f"amalgam dead: is_gone={amalgam.is_gone}")
    print(f"queen STILL telegraphs: {queen._current_move.id}  "
          f"intent={queen.current_intent.move_type}")
    print("C# Queen.cs:230-232: NextMove == BurnBrightForMeState -> "
          "SetMoveImmediate(EnragedState), i.e. the telegraph flips to "
          "ENRAGE_MOVE (BuffIntent) the instant AfterDeath fires.")
    before = queen.strength
    queen.take_turn(ctx)
    print(f"resolved effect: strength {before} -> {queen.strength}  "
          f"block={queen.block}")
    print(f"next telegraph: {queen._current_move.id}")
    print("  => the EFFECT matches (Enrage: +2 Strength, no block) and the "
          "following move matches (OFF_WITH_YOUR_HEAD_MOVE); only the "
          "telegraphed intent for the intervening player turn diverges.")


# ── scroll-rng ───────────────────────────────────────────────────────────────
def probe_scroll_rng():
    import inspect
    from sts2_rl.monsters.glory.scroll_of_biting import _ScrollsEncounter
    print(inspect.getsource(_ScrollsEncounter.create_monsters))
    print("C# ScrollsOfBitingWeak.cs:20-25 / Normal.cs:20-27: "
          "base.Rng.NextInt(3), where EncounterModel._rng is seeded "
          "runState.Rng.Seed + runState.TotalFloor + hash(Id.Entry) "
          "(EncounterModel.cs:258-263) -- a per-encounter deterministic Rng, "
          "NOT the shared combat rng the sim draws from.")
    from sts2_rl.combat import CombatState
    for seed in (0, 1, 2):
        from sts2_rl.monsters.glory.scroll_of_biting import (
            SCROLLS_OF_BITING_NORMAL,
        )
        cs = CombatState(rng=_random.Random(seed),
                         encounter=SCROLLS_OF_BITING_NORMAL)
        print(f"seed {seed}: starter idxs = "
              f"{[m._starter_move_idx for m in cs.enemies]}  "
              f"opening moves = {[m._current_move.id for m in cs.enemies]}")


# ── branch-order ─────────────────────────────────────────────────────────────
def probe_branch_order():
    from sts2_rl.monsters.glory.fabricator import Fabricator
    from sts2_rl.monsters.glory.frog_knight import FrogKnight
    from sts2_rl.monsters.glory.queen import Queen, TorchHeadAmalgam
    from sts2_rl.monsters.state_machine import ConditionalBranchState
    for classes, who in (([Fabricator], "Fabricator"),
                         ([FrogKnight], "FrogKnight"),
                         ([TorchHeadAmalgam, Queen], "Queen")):
        cs = _combat(classes, seed=0)
        mon = cs.enemies[-1]
        for st in mon.machine.states.values():
            if isinstance(st, ConditionalBranchState):
                ids = [sid for sid, _c in st._branches]
                print(f"{who}.{st.id}: first-true-wins order {ids}")
    print("\nC# ConditionalBranchState.GetNextState returns the FIRST branch "
          "whose Evaluate() > 0 and THROWS if none match "
          "(ConditionalBranchState.cs:44-54).")
    print("C# add order: Fabricator.cs:63-64 [RAND, DISINTEGRATE_MOVE]; "
          "FrogKnight.cs:75-76 [TONGUE_LASH, BEETLE_CHARGE]; "
          "Queen.cs:145-149 [BURN_BRIGHT, OFF_WITH_YOUR_HEAD] twice.")


_PROBES = {
    "spawn-rng": probe_spawn_rng,
    "spawn-content": probe_spawn_content,
    "fab-open": probe_fab_open,
    "queen-death": probe_queen_death,
    "scroll-rng": probe_scroll_rng,
    "branch-order": probe_branch_order,
}


def main(argv):
    if len(argv) < 2 or argv[1] not in _PROBES and argv[1] != "all":
        print(__doc__)
        return 1
    names = list(_PROBES) if argv[1] == "all" else [argv[1]]
    for n in names:
        print(f"\n{'=' * 70}\n{n}\n{'=' * 70}")
        _PROBES[n]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
