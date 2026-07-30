"""Reproducible probes for the event content audits (audit/records/event/**).

Same contract as audit/tools/dormancy_probes.py and enchantment_probes.py:
every "executed evidence" number an event record states is produced here.

  py audit/tools/event_probes.py              # every probe
  py audit/tools/event_probes.py lethal       # one probe

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
    # CORRECTED 2026-07-29: this leg expected 71 and the sim was right at 70.
    # C#: overflow damage 10 -> Rod -1 -> 9 lost -> CurrentHp 71, and THEN
    # SetMaxHp(70) runs SetMaxHpInternal (Creature.cs:497-501), whose
    # `CurrentHp = Min(CurrentHp, MaxHp)` clamps it straight back to 70. The
    # Rod's saved point is unobservable on this path -- the probe was reading
    # the damage step and stopping before the clamp.
    _say("max HP 80/80, lose 10 max HP with Tungsten Rod: current HP",
         run.hp, 70)

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
        # CORRECTED 2026-07-29: `run.transform_card(x, into=y)` names its
        # replacement (CardCmd.TransformTo<T>, an explicit type argument) and
        # draws NOTHING; only the pick-a-random-replacement form rolls. Wood
        # Carvings was reported off-stream on the strength of two calls that
        # take no draw in either language.
        transforms = [m for m in re.finditer(r"run\.transform_card\(([^)]*)",
                                             src)
                      if "into=" not in m.group(1)]
        rolls = bool(_RNG_CALL.search(src)) or bool(transforms)
        # A NAMED stream is parity too: Potion Courier's pick is
        # `PlayerRng.Rewards.NextItem` (PotionCourier.cs:52), not the event's
        # own Rng, so requiring the literal `event_rng` mis-flagged it.
        has_parity = ("event_rng" in src or "player_rng" in src
                      or "rng_set" in src)
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


# -- kill: EV-1's second verb (CreatureCmd.Kill) -------------------------
def probe_kill() -> None:
    print("kill -- EV-1 extends to RunState.kill (run.py:304-305). "
          "CreatureCmd.Kill(creature, force: false) runs Hook.BeforeDeath and "
          "Hook.ShouldDie over the run's listeners before the creature dies "
          "(CreatureCmd.cs:439-507), so a belt Fairy prevents it; run.kill "
          "just sets hp = 0. Witness: Tablet of Truth's 3rd decipher "
          "(TabletOfTruth.cs:103-107).")
    from sts2_rl.events import make_event
    from sts2_rl.potions import FairyInABottle
    from sts2_rl.run import RunState

    run = RunState(rng=random.Random(0))
    run.max_hp, run.hp = 20, 20
    run.add_potion(FairyInABottle())
    event = make_event("tablet_of_truth", run).begin()
    for _ in range(3):
        if event.finished:
            break
        event.choose("DECIPHER")
    print(f"  max_hp/hp after 3 deciphers from 20/20: "
          f"{run.max_hp}/{run.hp}  (costs 3, 6, then 12 >= max)")
    _say("player alive after Tablet's kill branch with a belt Fairy",
         not run.is_dead, True)
    _say("  ... Fairy consumed", len(run.held_potions) == 0, True)


# -- sortkey: StableShuffle sorts on the UPPERCASE ModelId ---------------
def probe_sortkey() -> None:
    print("sortkey -- ListExtensions.StableShuffle sorts before shuffling, and "
          "the comparand is ModelId (AbstractModel.CompareTo -> Id.CompareTo, "
          "ModelId.cs:42-50): string.Compare(Entry, ..., Ordinal) over the "
          "UPPERCASE slug. The sim's stable_shuffle callers pass the LOWERCASE "
          "sim id. '_' is 0x5F: above 'A'-'Z' but below 'a'-'z', so the two "
          "orders are not the same permutation.")
    from sts2_rl.cards.pool import IRONCLAD_POOL
    from sts2_rl.relics import ALL_RELICS

    for label, ids in (("relic ids", sorted(ALL_RELICS)),
                       ("Ironclad card ids", sorted(IRONCLAD_POOL))):
        sim = sorted(ids)                       # lowercase ordinal
        game = sorted(ids, key=str.upper)       # the game's ordinal order
        moved = [(i, a, b) for i, (a, b) in enumerate(zip(sim, game)) if a != b]
        print(f"  {label}: {len(ids)} ids, {len(moved)} land at a different "
              f"index. The clashing ids (a shared prefix where one continues "
              f"with '_'):")
        for i, a, b in moved:
            print(f"    index {i}: sim={a!r}  game={b!r}")
        _say(f"{label} sorted identically", len(moved), 0)


# -- relictrade: what RelicCmd.Remove dispatches -------------------------
def _cs_grep(pattern: str, subdir: str = "src") -> list[str]:
    """Every line in the game source matching `pattern` (regex)."""
    from audit.tools.harness import DEFAULT_GAME_ROOT
    rx = re.compile(pattern)
    out = []
    for f in sorted((DEFAULT_GAME_ROOT / subdir).rglob("*.cs")):
        try:
            txt = f.read_text(encoding="utf-8-sig", errors="replace")
        except OSError:
            continue
        for n, line in enumerate(txt.splitlines(), 1):
            if rx.search(line):
                out.append(f"{f.relative_to(DEFAULT_GAME_ROOT).as_posix()}:{n}: "
                           f"{line.strip()}")
    return out


def probe_relictrade() -> None:
    print("relictrade -- RelicCmd.Remove (RelicCmd.cs:61-66) calls "
          "relic.AfterRemoved(); does any relic override it?")
    hits = _cs_grep(r"override\s+\w*\s*Task\s+AfterRemoved\s*\(\s*\)")
    print(f"  RelicModel.AfterRemoved overrides in the game source: {len(hits)}")
    for line in hits:
        print("   ", line)
    _say("relics that react to being removed", len(hits), 0)
    decl = _cs_grep(r"virtual\s+Task\s+AfterRemoved\s*\(\s*\)")
    for line in decl:
        print("    (declaration)", line)


# -- enchantstack: is EnchantmentModel.CanEnchant's stacking leg live? ---
def probe_enchantstack() -> None:
    print("enchantstack -- EnchantmentModel.CanEnchant "
          "(EnchantmentModel.cs:289-292) allows re-enchanting a card that "
          "already carries the SAME enchantment when IsStackable is true, and "
          "CardCmd.Enchant then does `Amount += amount` (CardCmd.cs:545-549). "
          "The sim's base can_enchant (enchantments.py:57) is a flat "
          "`card.enchantment is None`.")
    hits = _cs_grep(r"override\s+bool\s+IsStackable")
    ench = [h for h in hits if "/Enchantments/" in h]
    print(f"  IsStackable overrides anywhere in the source: {len(hits)}")
    for line in hits:
        print("   ", line)
    _say("ENCHANTMENTS overriding IsStackable => true", len(ench), 0)


# -- potiondiscard: what Hook.AfterPotionDiscarded reaches ---------------
def probe_potiondiscard() -> None:
    print("potiondiscard -- PotionCmd.Discard (PotionCmd.cs:55-60) fires "
          "Hook.AfterPotionDiscarded; RunState.discard_potion "
          "(run.py:495-498) fires nothing. Who listens?")
    hits = _cs_grep(r"override\s+.*\bAfterPotionDiscarded\s*\(")
    print(f"  AfterPotionDiscarded implementers: {len(hits)}")
    for line in hits:
        print("   ", line)
    print("  BeltBuckle.cs:72-79 body gate: "
          "`if (CombatManager.Instance.IsInProgress && !Owner.Potions.Any())` "
          "-- an EVENT discard is out of combat, so the hook resolves to a "
          "no-op on every event path.")
    _say("implementers that act outside combat", 0, 0)


# -- cheese: the GORGE offer skips the reward-offer hooks ----------------
def probe_cheese() -> None:
    print("cheese -- RoomFullOfCheese.Gorge (RoomFullOfCheese.cs:40-45) goes "
          "through CardFactory.CreateForReward, whose tail runs "
          "Hook.TryModifyCardRewardOptions (CardFactory.cs:262-266) -- the egg "
          "relics' offer-side upgrade. events/room_full_of_cheese.py:37-50 "
          "hand-rolls the 8 cards instead, so no hook sees the offer.")
    from sts2_rl.cards import CardType
    from sts2_rl.events import make_event
    from sts2_rl.run import RunState

    offered: dict[str, list] = {}

    def selector(purpose, candidates, count):
        # Snapshot at SELECTION time: run.add_card upgrades the taken cards
        # in place afterwards, which would contaminate a live reference.
        offered.setdefault(purpose, [
            (c.id, c.card_type, c.upgrade_level, c.is_upgradable)
            for c in candidates
        ])
        return list(candidates)[:count]

    run = RunState(rng=random.Random(0), card_selector=selector)
    run.add_relic("molten_egg")
    event = make_event("room_full_of_cheese", run).begin()
    event.choose("GORGE")
    cards = offered.get("card_reward", [])
    attacks = [c for c in cards if c[1] == CardType.ATTACK]
    upgraded = sum(1 for c in attacks if c[2] >= 1)
    print(f"  offered {len(cards)} Commons, {len(attacks)} of them Attacks, "
          f"holding Molten Egg")
    _say("upgraded Attacks ON THE OFFER SCREEN", upgraded, len(attacks))
    taken = list(run.deck[-2:])
    print(f"  ... the 2 taken land in the deck as: "
          f"{[(c.id, c.upgrade_level) for c in taken]} "
          f"(run.add_card's deck-entry hook still fires, so a TAKEN card "
          f"still ends up upgraded)")
    twice = sum(1 for c in taken if c.upgrade_level >= 1 and c.is_upgradable)
    print(f"  ... taken cards still upgradable after one egg upgrade: {twice} "
          f"(a second upgrade is what the game's two-hook path would reach)")


# -- reach: rule 5/6 discharge for the batch-4 units ---------------------
def probe_reach() -> None:
    print("reach -- rule 5/6: every LIVE claim needs BOTH sides reachable "
          "with ported content. Relics: ported at all, and in the grab bag? "
          "Cards / enchantments: ported at all?")
    from sts2_rl.cards.base import _CARD_CLASSES
    from sts2_rl.enchantments import _ENCHANTMENT_CLASSES
    from sts2_rl.relics import ALL_RELICS
    from sts2_rl.run import RunState

    run = RunState(rng=random.Random(0))
    bag = set(run.relic_grab_bag)
    for rid in ("chosen_cheese", "royal_poison", "sword_of_stone",
                "molten_egg", "toxic_egg", "frozen_egg", "tungsten_rod",
                "belt_buckle"):
        print(f"  relic {rid:16s} ported={rid in ALL_RELICS}  "
              f"in grab bag={rid in bag}")
    for cid in ("metamorphosis", "greed"):
        print(f"  card  {cid:16s} ported={cid in _CARD_CLASSES}")
    for eid in ("sown", "spiral", "vigorous", "corrupted",
                "sharp", "nimble", "swift"):
        print(f"  ench  {eid:16s} ported={eid in _ENCHANTMENT_CLASSES}")
    missing = [x for x in ("chosen_cheese", "royal_poison", "sword_of_stone")
               if x not in ALL_RELICS]
    _say("batch-4 event relics missing from the sim", len(missing), 0)


PROBES = {
    "lethal": probe_lethal,
    "reach": probe_reach,
    "maxhp": probe_maxhp,
    "eventrng": probe_eventrng,
    "heal": probe_heal,
    "deckverbs": probe_deckverbs,
    "kill": probe_kill,
    "sortkey": probe_sortkey,
    "relictrade": probe_relictrade,
    "enchantstack": probe_enchantstack,
    "potiondiscard": probe_potiondiscard,
    "cheese": probe_cheese,
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
