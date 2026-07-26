"""Reproducible execution probes for the relic content audits.

Companion to `tools/audit/dormancy_probes.py` (which serves the seam tier).
Every claim an `audits/relic/*.json` record makes about *reachability* — "this
gap is live", "this waiver's trigger cannot occur" — is produced here, so a
later auditor re-derives the number instead of trusting a throwaway script.
Binding rules 5 and 6 of the shared audit contract: never justify `faithful`
with an unreachability claim you have not EXECUTED, and never label a gap LIVE
without proving both sides reachable with ported content.

  py tools/audit/relic_probes.py                  # every probe
  py tools/audit/relic_probes.py lamp-replay      # one probe

Probes (batch 1 = the Tier 1 pilot):
  pool             obtainability of the pilot batch's 16 relics
  turn-order       the sim's actual relic-hook order across a turn boundary
  lamp-replay      unsettling_lamp G1 — doubling survives every Replay pass
  lamp-self-debuff unsettling_lamp G2 — ported cards that debuff the player
  lamp-temporary   unsettling_lamp N3 — ported ITemporaryPower counterparts
  aubergine-gold   amethyst_aubergine G1 — reward gold with vs without it
  mushroom-hp      big_mushroom G1 — +20 Max HP on the add_relic path
  buckle-potion    belt_buckle G1 — Dexterity when a potion is procured
"""
from __future__ import annotations

import argparse
import inspect
import random
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

# The pilot batch: the roster's first 15 relics alphabetically plus the
# design document's worked example.
BATCH1 = [
    "akabeko", "alchemical_coffer", "amethyst_aubergine", "anchor",
    "arcane_scroll", "archaic_tooth", "art_of_war", "astrolabe",
    "bag_of_marbles", "bag_of_preparation", "beating_remnant",
    "beautiful_bracelet", "bellows", "belt_buckle", "big_mushroom",
    "unsettling_lamp",
]


# ── pool ──────────────────────────────────────────────────────────────────
def probe_pool() -> None:
    """Where each pilot-batch relic can come from.

    Rule 6 wants "the relic obtainable" proved, not asserted. Grab-bag
    membership comes from relic_pools.py (the transcribed C# pools); every
    other source is a literal id somewhere in sts2_rl/, so grep for it.
    """
    import subprocess

    from sts2_rl.relic_pools import IRONCLAD_RELIC_POOL, SHARED_RELIC_POOL
    from sts2_rl.relics import ALL_RELICS

    bag = {rid.removeprefix("RELIC.").lower(): rarity
           for rid, rarity in SHARED_RELIC_POOL + IRONCLAD_RELIC_POOL}
    print(f"grab-bag pool: {len(bag)} relics "
          f"({len(SHARED_RELIC_POOL)} shared + {len(IRONCLAD_RELIC_POOL)} Ironclad)")
    for rid in BATCH1:
        registered = rid in ALL_RELICS
        srcs = subprocess.run(
            ["git", "grep", "-l", f'"{rid}"', "--", "sts2_rl"],
            capture_output=True, text=True, cwd=_REPO,
        ).stdout.split()
        srcs = [s for s in srcs if not s.endswith(f"relics/{rid}.py")]
        print(f"  {rid:<20} registered={registered} bag={bag.get(rid, '-'):<9} "
              f"granted_by={srcs or ['(none)']}")


# ── turn-order ────────────────────────────────────────────────────────────
def probe_turn_order() -> None:
    """The sim's relic-facing hook order across a turn boundary.

    Records for akabeko / anchor / art_of_war / bag_of_marbles /
    bag_of_preparation / beating_remnant / bellows map C# turn hooks onto sim
    ones; this prints what the sim actually fires, so the mapping claims are
    executed rather than read off relics/base.py's docstring (which states the
    order incorrectly for on_player_turn_start — see PROMPT.md bug class 11).
    """
    from sts2_rl import CombatState
    from sts2_rl.relics.base import Relic, RelicRarity

    seen: list[str] = []

    class Spy(Relic):
        id, name, rarity = "_spy", "Spy", RelicRarity.COMMON

        def on_combat_start(self):
            seen.append("on_combat_start")

        def on_block_cleared(self, target):
            seen.append(f"on_block_cleared(turn={self.turn})")

        def on_energy_reset(self, player):
            seen.append(f"on_energy_reset(turn={self.turn})")

        def on_player_turn_start(self, player):
            seen.append(f"on_player_turn_start(turn={self.turn})")

        def modify_hand_draw(self, player, count):
            seen.append(f"modify_hand_draw(turn={self.turn})")
            return count

        def on_player_turn_started(self, player):
            seen.append(f"on_player_turn_started(turn={self.turn}, "
                        f"hand={len(self.player.hand)})")
            return None

        def on_player_turn_end(self, player):
            seen.append(f"on_player_turn_end(turn={self.turn})")

    cs = CombatState(rng=random.Random(0), relics=[Spy()])
    cs.end_turn()
    for line in seen:
        print("  " + line)
    print("\n  C# order (audits/seam/turn_structure.json steps 9-23):")
    print("    BeforeSideTurnStart -> ClearBlock -> AfterBlockCleared -> "
          "energy -> AfterEnergyReset")
    print("    -> BeforeHandDraw -> ModifyHandDraw -> Draw "
          "-> AfterPlayerTurnStart -> AfterSideTurnStart")


# ── lamp-replay ───────────────────────────────────────────────────────────
def probe_lamp_replay() -> None:
    """Unsettling Lamp x a Replay source.

    C#: Hook.AfterCardPlayed fires once per Replay iteration inside the
    play-count loop (CardModel.cs:1904-1963), so UnsettlingLamp.AfterCardPlayed
    sets IsFinishedTriggering after iteration 0 and iteration 1 is NOT doubled.
    The sim fires on_card_played once, after the whole loop (combat.py:477-514),
    so the Lamp doubles every iteration. Throwing Axe is the ported replay
    source used here; Spiral/Glam enchantments and Hidden Gem reach the same
    play-count path.
    """
    from sts2_rl import CombatState
    from sts2_rl.cards import make_card
    from sts2_rl.relics import make_relic

    for relics, label in (
        ([make_relic("unsettling_lamp")], "Lamp alone"),
        ([make_relic("unsettling_lamp"), make_relic("throwing_axe")],
         "Lamp + Throwing Axe (first play is played twice)"),
    ):
        cs = CombatState(rng=random.Random(0), relics=relics)
        card = make_card("bash")
        cs.player.energy = 10
        cs.player.hand.append(card)
        cs.play_card(len(cs.player.hand) - 1, 0)
        vuln = cs.enemy.powers.get("vulnerable")
        print(f"  {label:<48} Vulnerable={vuln.amount if vuln else 0}")
    print("  Bash applies 2 Vulnerable. Expected: 4 alone; C# 4+2=6 with the "
          "Axe (iteration 1 already finished the relic).")


# ── lamp-self-debuff ──────────────────────────────────────────────────────
def probe_lamp_self_debuff() -> None:
    """Ported cards that apply a Debuff to the player.

    C#'s ModifyPowerAmountGivenMultiplicative (UnsettlingLamp.cs:106-129) has
    NO target-side guard — only the latch (BeforePowerAmountChanged) checks
    `target.Side == Owner.Creature.Side`. So a card that debuffs an enemy and
    then debuffs the PLAYER has BOTH doubled in C#. The sim's
    modify_power_amount bails on `target is self.player` (unsettling_lamp.py:47),
    so the self-debuff is never doubled. This probe lists the ported cards
    whose source applies a Debuff to the player, i.e. the reachability
    population for that divergence.
    """
    import re

    from sts2_rl.cards.base import _CARD_CLASSES
    from sts2_rl.powers import ALL_POWERS, PowerType
    import sts2_rl.cards  # noqa: F401  (registration)

    debuffs = {pid for pid, cls in ALL_POWERS.items()
               if getattr(cls, "power_type", None) == PowerType.DEBUFF}
    hits = []
    for cid, cls in sorted(_CARD_CLASSES.items()):
        try:
            src = inspect.getsource(cls)
        except OSError:                                  # pragma: no cover
            continue
        # PowerCmd.apply(..., <player-ish target>, SomePower, ...)
        for m in re.finditer(r"PowerCmd\.apply\(\s*[^,]+,\s*([^,]+),\s*(\w+)",
                             src):
            target, power = m.group(1).strip(), m.group(2)
            if "player" not in target and "self.owner" not in target:
                continue
            pid = re.sub(r"(?<!^)(?=[A-Z])", "_", power).lower()
            pid = pid.removesuffix("_power")
            if pid in debuffs:
                hits.append((cid, power))
    for cid, power in hits:
        print(f"  {cid:<28} applies {power} to the player")
    print(f"  {len(hits)} ported card(s) apply a Debuff to the player.")
    print("  A divergence needs ONE card doing both in a single play; a card "
          "that only self-debuffs never latches the Lamp.")


# ── lamp-temporary ────────────────────────────────────────────────────────
def probe_lamp_temporary() -> None:
    """The ported ITemporaryPower counterparts and their applier handling.

    audits/seam/power_cmd.json guard N2 verified by execution that the sim's
    TemporaryStrengthPower / TemporaryDexterityPower reach C#'s
    HasDoubledTemporaryPowerSource outcome by omitting `applier` on the
    internal application. That argument only covers the Lamp if it holds for
    EVERY ported ITemporaryPower — so enumerate both sides.
    """
    from sts2_rl import powers as sim_powers

    from tools.audit.harness import DEFAULT_GAME_ROOT

    print("  C# Powers/*.cs mentioning ITemporaryPower:")
    for path in sorted((DEFAULT_GAME_ROOT / "src/Core/Models/Powers").glob("*.cs")):
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        if "ITemporaryPower" not in text:
            continue
        internal = [ln.strip() for ln in text.splitlines()
                    if "InternallyAppliedPower =>" in ln]
        print(f"    {path.name:<30} "
              f"{internal[0] if internal else '(reference only, not an impl)'}")
    # PiercingWailPower extends TemporaryStrengthPower, so it inherits the
    # interface without naming it.
    for name in ("PiercingWailPower",):
        text = (DEFAULT_GAME_ROOT
                / f"src/Core/Models/Powers/{name}.cs").read_text(
                    encoding="utf-8-sig", errors="replace")
        base = next(ln.strip() for ln in text.splitlines() if "class " in ln)
        print(f"    {name + '.cs':<30} inherits: {base}")

    print("\n  sim counterparts and their internal application:")
    for cname in ("TemporaryStrengthPower", "TemporaryDexterityPower",
                  "PiercingWailPower", "TemporaryFocusPower"):
        cls = getattr(sim_powers, cname, None)
        if cls is None:
            print(f"    {cname:<24} NOT PORTED")
            continue
        applies = [ln.strip() for ln in inspect.getsource(cls).splitlines()
                   if "PowerCmd.apply" in ln]
        print(f"    {cname:<24} passes applier: "
              f"{any('applier' in ln for ln in applies)}   {applies}")


# ── aubergine-gold ────────────────────────────────────────────────────────
def probe_aubergine_gold() -> None:
    """Amethyst Aubergine's +15 gold on a combat reward screen.

    C#: TryModifyRewards adds a GoldReward(15) to every combat room's rewards
    (AmethystAubergine.cs:25-45). The sim registers the relic as a no-op stub
    whose docstring claims "the sim has no gold" — but rewards.py:462-500 rolls
    gold, grants it, and then runs relic.modify_combat_rewards over the run's
    relics, which is exactly the hook the port needs.
    """
    from sts2_rl.rewards import generate_combat_rewards
    from sts2_rl.rooms import RoomType
    from sts2_rl.run import RunState

    for relics in ([], ["amethyst_aubergine"]):
        run = RunState(rng=random.Random(7))
        for rid in relics:
            run.add_relic(rid)
        before = run.gold
        rewards = generate_combat_rewards(run, RoomType.MONSTER)
        print(f"  relics={relics or ['(none)']:} "
              f"rewards.gold={rewards.gold} run.gold delta={run.gold - before}")
    print("  C# grants 15 more with the relic; equal numbers = the gap.")


# ── mushroom-hp ───────────────────────────────────────────────────────────
def probe_mushroom_hp() -> None:
    """Big Mushroom's +20 Max HP when the relic is granted via add_relic.

    BigMushroom.cs:24-28 raises Max HP by 20 in AfterObtained. The sim's relic
    has no after_obtained; the Hungry for Mushrooms event applies the +20
    itself, so the event path matches. Every OTHER grant path — notably the
    conformance runner's relic resync (conformance/runner.py:465, 698, 751) —
    calls run.add_relic(id) and gets no Max HP.
    """
    from sts2_rl.run import RunState

    run = RunState(rng=random.Random(0))
    base = run.max_hp
    run.add_relic("big_mushroom")
    print(f"  add_relic('big_mushroom'):        max_hp {base} -> {run.max_hp}")

    run2 = RunState(rng=random.Random(0))
    base2 = run2.max_hp
    run2.add_relic("fragrant_mushroom")
    print(f"  add_relic('fragrant_mushroom'):   hp {run2.STARTING_HP} -> "
          f"{run2.hp}, max_hp {base2} -> {run2.max_hp}  "
          f"(sibling relic DOES use after_obtained)")

    from sts2_rl.events.base import make_event
    run3 = RunState(rng=random.Random(0))
    base3 = run3.max_hp
    ev = make_event("hungry_for_mushrooms", run3)
    ev.begin()
    ev.choose("BIG_MUSHROOM")
    print(f"  via HungryForMushrooms event:     max_hp {base3} -> {run3.max_hp}"
          f"  (the event applies the +20 itself, not the relic)")


# ── buckle-potion ─────────────────────────────────────────────────────────
def probe_buckle_potion() -> None:
    """Belt Buckle's Dexterity when a potion is procured mid-combat.

    BeltBuckle.cs:63-70 removes the 2 Dexterity on AfterPotionProcured while
    combat is in progress; the sim's port (belt_buckle.py) implements only
    on_combat_start and on_potion_used, so a potion picked up mid-combat leaves
    the Dexterity in place.
    """
    from sts2_rl import CombatState
    from sts2_rl.potions import make_potion
    from sts2_rl.relics import make_relic

    buckle = make_relic("belt_buckle")
    cs = CombatState(rng=random.Random(0), relics=[buckle])
    dex = cs.player.powers.get("dexterity")
    print(f"  combat 1 start, no potions:  Dexterity="
          f"{dex.amount if dex else 0}")
    cs.player.add_potion(make_potion("block_potion"))
    dex = cs.player.powers.get("dexterity")
    print(f"  after procuring a potion:    Dexterity="
          f"{dex.amount if dex else 0}   (C# AfterPotionProcured: 0)")

    # The same relic instance carries into the run's next combat, exactly as
    # RunState.relics does. C# clears DexterityApplied in BeforeCombatStart
    # (BeltBuckle.cs:49) and again in AfterCombatVictory (line 92).
    cs2 = CombatState(rng=random.Random(1), relics=[buckle])
    dex = cs2.player.powers.get("dexterity")
    print(f"  combat 2 start, no potions:  Dexterity="
          f"{dex.amount if dex else 0}   (C#: 2)  _applied="
          f"{buckle._applied}")


PROBES = {
    "pool": probe_pool,
    "turn-order": probe_turn_order,
    "lamp-replay": probe_lamp_replay,
    "lamp-self-debuff": probe_lamp_self_debuff,
    "lamp-temporary": probe_lamp_temporary,
    "aubergine-gold": probe_aubergine_gold,
    "mushroom-hp": probe_mushroom_hp,
    "buckle-potion": probe_buckle_potion,
}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("probe", nargs="?", choices=sorted(PROBES))
    args = ap.parse_args(argv)
    for name in ([args.probe] if args.probe else PROBES):
        print(f"\n== {name} ==")
        PROBES[name]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
