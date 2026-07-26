"""Reproducible probes for the event content audits (audits/event/**).

Same contract as tools/audit/dormancy_probes.py and enchantment_probes.py:
every "executed evidence" number an event record states is produced here.

  py tools/audit/event_probes.py              # every probe
  py tools/audit/event_probes.py lethal       # one probe

Probes:
  lethal    gap EV-1  RunState.lose_hp (run.py:294-302) subtracts HP directly.
                      C# event damage goes through CreatureCmd.Damage, whose
                      Hook.ShouldDie / AfterPreventingDeath pass reaches the
                      potion belt outside combat (RunState.IterateHookListeners,
                      RunState.cs:545-596), so a belt Fairy in a Bottle saves
                      the player. The sim's Fairy only listens inside a combat.
  maxhp     gap EV-2  RunState.lose_max_hp (run.py:316-321) clamps instead of
                      running the overflow through the damage pipeline
                      (CreatureCmd.LoseMaxHp), and floors max HP BEFORE
                      computing the loss instead of after.
  eventrng  gap EV-3  C# events roll on the per-event `base.Rng`; the sim's
                      Event exposes it as `self.event_rng` (events/base.py:85-88)
                      but most modules roll on the shared `self.rng`.
  heal      turn_structure step 38a blast radius: which events heal, and by
                      which C# verb.
  deckverbs which events add / transform / remove deck cards
                      (creature_card_cmds G3 blast radius).
"""
from __future__ import annotations

import argparse
import random
import re
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

EVENTS_DIR = _REPO / "sts2_rl" / "events"


def _say(label, observed, expected_cs):
    flag = "MATCH  " if observed == expected_cs else "DIVERGE"
    print(f"  {flag}  {label}: sim={observed!r}  C#={expected_cs!r}")


# -- lethal: no run-level death prevention -------------------------------
def probe_lethal() -> None:
    print("lethal -- CreatureCmd.Damage runs Hook.ShouldDie over "
          "RunState.IterateHookListeners, which yields the potion belt outside "
          "combat (RunState.cs:545-596); FairyInABottle.cs:33-45 answers it")
    from sts2_rl.potions import FairyInABottle
    from sts2_rl.run import RunState

    run = RunState(rng=random.Random(0))
    run.hp = 5
    run.add_potion(FairyInABottle())
    held = [type(p).__name__ for p in run.held_potions]
    run.lose_hp(15)                     # e.g. Doll Room's EXAMINE
    print(f"  belt before: {held}")
    _say("player alive after a lethal event HP loss with a belt Fairy",
         not run.is_dead, True)
    _say("  ... HP", run.hp, int(run.max_hp * 0.3))
    _say("  ... Fairy consumed", len(run.held_potions) == 0, True)


# -- maxhp: lose_max_hp does not route through the damage pipeline -------
def probe_maxhp() -> None:
    print("maxhp -- CreatureCmd.LoseMaxHp damages the overflow "
          "(Unblockable|Unpowered) BEFORE SetMaxHp(max(1, newMaxHp))")
    from sts2_rl.relics import make_relic
    from sts2_rl.run import RunState

    # Leg 1: Tungsten Rod (-1 to each HP loss) should soften the overflow chip.
    run = RunState(rng=random.Random(0))
    run.max_hp, run.hp = 80, 80
    run.add_relic(make_relic("tungsten_rod"))
    run.lose_max_hp(10)
    _say("max HP 80/80, lose 10 max HP with Tungsten Rod: current HP",
         run.hp, 71)               # C#: damage 10 -> Rod -1 -> 9 lost -> 71

    # Leg 2: losing more max HP than you have. C# computes the damage against
    # the UNFLOORED new max (80 - 100 = -20 -> 100 damage -> dead) and only
    # then floors max HP at 1.
    run = RunState(rng=random.Random(0))
    run.max_hp, run.hp = 80, 80
    run.lose_max_hp(100)
    _say("max HP 80/80, lose 100 max HP: player dead", run.is_dead, True)
    print(f"  INFO     sim ends at hp={run.hp}, max_hp={run.max_hp}")


# -- eventrng: which modules roll on the shared rng ----------------------
_RNG_CALL = re.compile(r"self\.rng\.\w+\(")


def probe_eventrng() -> None:
    print("eventrng -- C# events roll on the per-event `base.Rng`; "
          "Event.event_rng (events/base.py:85-88) is the sim's adapter for it")
    shared_only, both, none = [], [], []
    for p in sorted(EVENTS_DIR.glob("*.py")):
        if p.name in ("__init__.py", "base.py", "ancient.py"):
            continue
        src = p.read_text(encoding="utf-8")
        rolls = bool(_RNG_CALL.search(src)) or "run.transform_card(" in src
        has_parity = "event_rng" in src
        if rolls and has_parity:
            both.append(p.stem)
        elif rolls:
            shared_only.append(p.stem)
        else:
            none.append(p.stem)
    print(f"  {len(both)} modules have a parity branch: {both}")
    print(f"  {len(shared_only)} modules roll ONLY on the shared rng:")
    for name in shared_only:
        print(f"    {name}")
    print(f"  {len(none)} modules roll nothing.")
    _say("modules rolling only on the shared run rng", len(shared_only), 0)


# -- heal: step 38a blast radius -----------------------------------------
def probe_heal() -> None:
    print("heal -- turn_structure step 38a: run.heal() skips "
          "Hook.AfterRestSiteHeal + ModifyRestSiteHealRewards, which only "
          "HealRestSiteOption.ExecuteRestSiteHeal runs")
    out = subprocess.run(["git", "grep", "-n", "-E",
                          r"run\.heal\(|rest_site_heal_amount",
                          "--", "sts2_rl/events"],
                         cwd=_REPO, capture_output=True, text=True).stdout
    rest_site, plain = [], []
    for line in out.splitlines():
        (rest_site if "rest_site_heal_amount" in line else plain).append(line)
    print("  events healing through the REST-SITE verb (step 38a applies):")
    for line in rest_site:
        print("   ", line)
    print("  events healing through a plain CreatureCmd.Heal "
          "(no hooks in C# either -- CreatureCmd.cs:691-703):")
    for line in plain:
        print("   ", line)


# -- deckverbs: G3 blast radius ------------------------------------------
def probe_deckverbs() -> None:
    print("deckverbs -- creature_card_cmds G3: deck-pile transforms bypass the "
          "deck-entry hooks, so the egg relics never upgrade a transformed card")
    for verb in ("run.transform_card(", "run.add_card(", "run.remove_cards("):
        out = subprocess.run(["git", "grep", "-l", "-F", verb,
                              "--", "sts2_rl/events"],
                             cwd=_REPO, capture_output=True, text=True).stdout.split()
        names = sorted(Path(p).stem for p in out)
        print(f"  {verb:22s} {len(names)}: {names}")


PROBES = {
    "lethal": probe_lethal,
    "maxhp": probe_maxhp,
    "eventrng": probe_eventrng,
    "heal": probe_heal,
    "deckverbs": probe_deckverbs,
}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("probe", nargs="?", choices=sorted(PROBES))
    args = ap.parse_args(argv)
    for name in ([args.probe] if args.probe else list(PROBES)):
        print(f"\n=== {name} ===")
        PROBES[name]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
