"""Executed evidence for monster content-audit batch 5.

Every number that batch 5's records assert about *behaviour at run time*
(rather than about two files sitting side by side) comes from one of these
probes.  Run with:

    py audit/tools/monster_probes_b05.py <probe>

Probes
------
reach          which of the 15 units' encounters sit in a ported pool
rocket-ctor    what exists when Rocket's __init__ applies SurroundedPower
                to the PLAYER (SHARED-FINDINGS section 2 escalation)
ovicopter-hp   whether creature_card_cmds step 26 (raw SetMaxAndCurrentHp)
                is LIVE through Ovicopter's ToughEgg hatch
beetle-wake    when the Slumbering Beetle loses PlatingPower on a damage wake
entomancer-hive whether PersonalHivePower can ever be absent when SpitMove runs
listeners      hooks the sim can dispatch for a power applied to the player at
                monster-construction time, and who implements them
"""
from __future__ import annotations

import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


def _combat(encounter):
    from sts2_rl.combat import CombatState
    return CombatState(encounter=encounter, rng=random.Random(7))


def reach() -> None:
    from sts2_rl import rooms  # noqa: F401
    from sts2_rl.rooms import _hive_rooms, _glory_rooms
    hive = _hive_rooms()
    glory = _glory_rooms()
    pools = {
        "hive.weak": hive.weak_keys, "hive.normal": hive.normal_keys,
        "hive.elite": hive.elite_keys, "hive.boss": hive.boss_keys,
        "glory.elite": glory.elite_keys,
    }
    want = {
        "chomper": "chompers", "entomancer": "entomancer",
        "exoskeleton": "exoskeletons_normal", "hunter_killer": "hunter_killer",
        "infested_prism": "infested_prisms", "crusher": "kaiser_crab",
        "rocket": "kaiser_crab", "knowledge_demon": "knowledge_demon",
        "louse_progenitor": "louse_progenitor", "myte": "mytes",
        "ovicopter": "ovicopter", "tough_egg": "ovicopter (spawned)",
        "slumbering_beetle": "slumbering_beetle", "flail_knight": "knights",
        "mysterious_knight": "the_lantern_key event",
    }
    for unit, key in sorted(want.items()):
        base = key.split(" ")[0]
        where = [name for name, keys in pools.items() if base in keys]
        print(f"  {unit:20s} encounter={key:24s} pools={where or 'EVENT/SPAWN'}")


def rocket_ctor() -> None:
    """SHARED-FINDINGS section 2 escalation: Rocket applies to the PLAYER."""
    from sts2_rl.monsters.hive.kaiser_crab import KAISER_CRAB_BOSS, Rocket
    import sts2_rl.monsters.hive.kaiser_crab as kc

    seen = {}
    orig = Rocket.__init__

    def spy(self, hooks, rng=None):
        combat = hooks.combat
        seen["hooks.combat is None"] = combat is None
        seen["combat.player exists"] = getattr(combat, "player", None) is not None
        seen["combat has .enemies"] = hasattr(combat, "enemies")
        seen["combat has .relics"] = hasattr(combat, "relics")
        seen["belt potions registered"] = any(
            type(l).__module__ == "sts2_rl.potions" for l in combat.hooks._listeners)
        seen["listener types"] = sorted(
            {type(l).__name__ for l in combat.hooks._listeners})
        orig(self, hooks, rng)

    kc.Rocket.__init__ = spy
    try:
        c = _combat(KAISER_CRAB_BOSS)
    finally:
        kc.Rocket.__init__ = orig
    for k, v in seen.items():
        print(f"  at Rocket.__init__: {k} = {v}")
    p = c.player
    print(f"  after create_monsters: player.powers = {sorted(p.powers)}")
    print(f"  surrounded.amount    = {p.powers['surrounded'].amount}")
    print(f"  surrounded.applier   = {type(p.powers['surrounded'].applier).__name__}")
    print(f"  surrounded.facing    = {p.powers['surrounded'].facing}")
    print(f"  enemy order          = {[type(e).__name__ for e in c.enemies]}")
    print(f"  player.powers artifact present at ctor time? "
          f"{'artifact' in p.powers}")


def ovicopter_hp() -> None:
    """creature_card_cmds step 26 liveness through Ovicopter."""
    from sts2_rl.monsters.hive.ovicopter import OVICOPTER_NORMAL, ToughEgg
    c = _combat(OVICOPTER_NORMAL)
    ovi = c.enemies[0]
    fired = []
    c.hooks.on_hp_changed = (
        lambda t, d, _o=c.hooks.on_hp_changed: (fired.append((type(t).__name__, d)),
                                                _o(t, d))[1])
    ovi._lay_eggs(c._ctx())
    eggs = [e for e in c.enemies if isinstance(e, ToughEgg)]
    print(f"  eggs laid: {len(eggs)}  order={[type(e).__name__ for e in c.enemies]}")
    lo, hi = 10**9, -(10**9)
    for _ in range(2000):
        e = ToughEgg(c.hooks, random.Random())
        e.hp, e.max_hp = 14, 18
        before = e.hp
        e._hatch(c._ctx())
        lo, hi = min(lo, e.max_hp), max(hi, e.max_hp)
        assert e.max_hp > 0 and e.hp > 0, (e.max_hp, e.hp)
        assert e.hp - before != 0
    print(f"  hatch max_hp over 2000 rolls: min={lo} max={hi}  "
          f"(<=0 never observed -> the MaxHp<=0->Kill arm is unreachable)")
    print(f"  hatch dispatches hooks.on_hp_changed: "
          f"{[f for f in fired][:1] or 'see next line'}")
    e = ToughEgg(c.hooks, random.Random())
    e.hp, e.max_hp = 14, 18
    fired.clear()
    e._hatch(c._ctx())
    print(f"  on_hp_changed fired at hatch: {fired}")


def beetle_wake() -> None:
    from sts2_rl.monsters.hive.slumbering_beetle import SLUMBERING_BEETLE_NORMAL
    from sts2_rl.monsters.hive.slumbering_beetle import SlumberingBeetle
    from sts2_rl.cmds import DamageCmd
    c = _combat(SLUMBERING_BEETLE_NORMAL)
    beetle = [e for e in c.enemies if isinstance(e, SlumberingBeetle)][0]
    print(f"  turn={c.turn} side={c.current_side} "
          f"powers={sorted(beetle.powers)} block={beetle.block}")
    for i in range(1, 4):
        DamageCmd.deal(c.hooks, beetle, 30, dealer=c.player)
        print(f"    hit {i} (still the PLAYER turn): powers={sorted(beetle.powers)} "
              f"stunned={beetle.stunned} move={beetle._current_move.id} "
              f"block={beetle.block} awake={beetle.is_awake}")
    print("  game (SlumberPower.cs:22-32 + SlumberingBeetle.cs:96-108): the third")
    print("  hit calls CreatureCmd.Stun(owner, WakeUpMove, 'ROLL_OUT_MOVE'); the")
    print("  Plating removal lives INSIDE WakeUpMove, which is the stun move's")
    print("  perform delegate, so it runs on the beetle's own (enemy-phase) turn.")


def entomancer_hive() -> None:
    from sts2_rl.monsters.hive.entomancer import ENTOMANCER_ELITE
    c = _combat(ENTOMANCER_ELITE)
    ent = c.enemies[0]
    print(f"  starting powers = {sorted(ent.powers)}")
    print(f"  hive amount     = {ent.powers['personal_hive'].amount}")
    import subprocess
    out = subprocess.run(
        ["git", "grep", "-n", "-e", "personal_hive"],
        capture_output=True, text=True,
        cwd=os.path.join(os.path.dirname(__file__), "..", ".."))
    for line in out.stdout.splitlines():
        if "audit/" not in line and ".pyc" not in line:
            print(f"    {line}")


def listeners() -> None:
    """Who could observe a power applied to the PLAYER at monster-ctor time."""
    import subprocess
    root = os.path.join(os.path.dirname(__file__), "..", "..")
    for hook in ("modify_power_amount", "on_power_applied"):
        out = subprocess.run(
            ["git", "grep", "-n", f"def {hook}"], capture_output=True,
            text=True, cwd=root)
        print(f"  {hook}:")
        for line in out.stdout.splitlines():
            if "audit/" in line or line.startswith("sts2_rl/hooks.py"):
                continue
            print(f"    {line}")


PROBES = {
    "reach": reach, "rocket-ctor": rocket_ctor, "ovicopter-hp": ovicopter_hp,
    "beetle-wake": beetle_wake, "entomancer-hive": entomancer_hive,
    "listeners": listeners,
}

if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else ""
    if name not in PROBES:
        print(__doc__)
        print("probes:", ", ".join(PROBES))
        raise SystemExit(1)
    PROBES[name]()
