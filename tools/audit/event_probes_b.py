"""Reproducible probes for event audit batch 5, slice B (audits/event/**).

Companion to tools/audit/event_probes.py -- same contract: every "executed
evidence" number the slice-B records state is produced here. Kept in its own
module because three slices of batch 5 ran concurrently against one branch and
event_probes.py is shared/committed.

Units covered: the_lantern_key, the_legends_were_true, this_or_that,
tinker_time, trash_heap, trial, unrest_site, vakuu.

  py tools/audit/event_probes_b.py                # every probe
  py tools/audit/event_probes_b.py potionoffer    # one probe

Probes:
  potionoffer  gap EV-9  Four events share one C# idiom -- concat the
                         character + shared potion pools, NextItem on
                         `Owner.PlayerRng.Rewards`, hand the pick to
                         RewardsCmd.OfferCustom. The sim draws all four on the
                         shared run rng, and the_legends_were_true additionally
                         uses the IN-COMBAT pool helper, which drops the three
                         CanBeGeneratedInCombat == false potions.
  cape         Vakuu / Distinguished Cape: the -9 Max HP is implemented on the
                         EVENT OPTION, but DistinguishedCape.cs:29-31 puts it in
                         the relic's AfterObtained. `.ThatDecreasesMaxHp(9m)` is
                         only a red-flash predicate (EventOption.cs:194-197).
  trialoffer   Trial NONDESCRIPT_GUILTY drops two 3-card RewardsCmd.OfferCustom
                         screens entirely (Trial.cs:180-185).
  draws        Draw counts for the shuffles in vakuu / tinker_time, parity vs
                         legacy, against ListExtensions.UnstableShuffle.
  ids          rule 5/6 discharge: every card / relic id the eight units name
                         is ported, and Distinguished Cape's alternative grant
                         paths.
  rng5b        which of the eight modules roll only on the shared run rng
                         (EV-3's candidate set for this slice).
  quest        gap EV-10 CardSelectCmd.FromDeckForTransformation filters
                         `c.Type != CardType.Quest && c.IsTransformable`
                         (CardSelectCmd.cs:487); RunState.transformable_cards
                         (run.py:364-366) drops the Quest clause, so a Spoils
                         Map / Lantern Key / Byrdoni's Egg can be transformed
                         away.
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

SLICE_B = (
    "the_lantern_key", "the_legends_were_true", "this_or_that", "tinker_time",
    "trash_heap", "trial", "unrest_site", "vakuu",
)


def _say(label, observed, expected_cs):
    flag = "MATCH  " if observed == expected_cs else "DIVERGE"
    print(f"  {flag}  {label}: sim={observed!r}  C#={expected_cs!r}")


# -- potionoffer: EV-9, the reward-stream potion offer -------------------
def probe_potionoffer() -> None:
    print("potionoffer -- EV-9. TheLegendsWereTrue.cs:52-59 (and the identical "
          "BattlewornDummy.cs:84-90 / EndlessConveyor.cs:152-158 / "
          "Wellspring.cs:32-38): "
          "items = Character.PotionPool.GetUnlockedPotions(UnlockState)"
          ".Concat(SharedPotionPool.GetUnlockedPotions(UnlockState)); "
          "potion = Owner.PlayerRng.Rewards.NextItem(items); "
          "RewardsCmd.OfferCustom(PotionReward(potion)).")
    from sts2_rl.potion_pools import NOT_GENERATED_IN_COMBAT, POTION_POOL
    from sts2_rl.potions import _POTION_CLASSES

    game_pool = [pid for pid, _ in POTION_POOL]
    run_helper = sorted(c.id for c in _POTION_CLASSES.values() if c.in_reward_pool)
    legends = sorted(
        c.id for c in _POTION_CLASSES.values()
        if c.in_reward_pool and c.id not in NOT_GENERATED_IN_COMBAT
    )
    print(f"  C# pool (Character.PotionPool U SharedPotionPool, "
          f"potion_pools.POTION_POOL): {len(game_pool)} ids")
    print(f"  sim run.random_potion() pool (run.py:513-520, used by "
          f"battleworn_dummy / endless_conveyor / wellspring): "
          f"{len(run_helper)} ids")
    print(f"  sim potions.random_potion() pool (potions.py:1262-1277, used ONLY "
          f"by the_legends_were_true): {len(legends)} ids")
    _say("run.random_potion() pool size", len(run_helper), len(game_pool))
    _say("the_legends_were_true's pool size", len(legends), len(game_pool))
    missing = sorted(set(game_pool) - set(legends))
    print(f"  ids the_legends_were_true can NEVER offer but the game can: "
          f"{missing}")
    print("  (those three are exactly PotionModel.CanBeGeneratedInCombat == "
          "false -- potions.random_potion mirrors "
          "PotionFactory.CreateRandomPotionInCombat, which is the WRONG "
          "factory for an out-of-combat event offer. Note fairy_in_a_bottle is "
          "among them: the potion EV-1 turns on.)")
    _say("potions the sim's copy of this offer can never produce",
         len(missing), 0)

    # Stream. run.rewards_rng is player_rng.rewards under a parity rng_set
    # (run.py:271-274) and the shared rng otherwise; events/potion_courier.py:55
    # already draws its potion pick off it.
    src = (EVENTS_DIR / "the_legends_were_true.py").read_text(encoding="utf-8")
    _say("the_legends_were_true draws its potion off run.rewards_rng",
         "rewards_rng" in src, True)
    out = subprocess.run(["git", "grep", "-n", "-E",
                          r"random_potion\(|rewards_rng",
                          "--", "sts2_rl/events"],
                         cwd=_REPO, capture_output=True, text=True).stdout
    print("  every event-side potion draw in the sim:")
    for line in out.splitlines():
        print("   ", line)

    # Forced grant (EV-4's shape) at this site.
    from sts2_rl.events import make_event
    from sts2_rl.run import RunState
    run = RunState(rng=random.Random(0))
    run.max_hp, run.hp = 80, 80
    before = len(run.held_potions)
    event = make_event("the_legends_were_true", run).begin()
    event.choose("SLOWLY_FIND_AN_EXIT")
    print(f"  belt after SLOWLY_FIND_AN_EXIT: {before} -> "
          f"{len(run.held_potions)} potions, hp {run.hp}")
    _say("the potion is a take-or-skip offer the driver surfaces",
         len(event.pending_reward_extras), 1)


# -- cape: where Distinguished Cape's -9 Max HP lives --------------------
def probe_cape() -> None:
    print("cape -- DistinguishedCape.cs:29-31 AfterObtained() runs "
          "CreatureCmd.LoseMaxHp(DynamicVars.HpLoss = 9) and THEN adds 3 "
          "Apparitions. Vakuu.cs:38's `.ThatDecreasesMaxHp(9m)` is NOT the "
          "effect -- EventOption.cs:194-197 shows it only sets WillKillPlayer, "
          "the predicate that flashes the option red.")
    from sts2_rl.relics import ALL_RELICS
    from sts2_rl.run import RunState

    # Leg 1: grant the relic by the ordinary verb, as any non-Vakuu path would.
    run = RunState(rng=random.Random(0))
    run.max_hp, run.hp = 80, 80
    run.add_relic("distinguished_cape")
    apparitions = sum(1 for c in run.deck if c.id == "apparition")
    print(f"  run.add_relic('distinguished_cape') at 80/80 -> "
          f"max_hp/hp = {run.max_hp}/{run.hp}, apparitions added "
          f"{apparitions}")
    _say("max HP after obtaining the relic on its own", run.max_hp, 71)
    _say("  ... current HP", run.hp, 71)
    _say("  ... Apparitions added", apparitions, 3)

    # Leg 2: the Vakuu option path, where the event applies the loss itself.
    run2 = RunState(rng=random.Random(0))
    run2.max_hp, run2.hp = 80, 80
    from sts2_rl.events.vakuu import VakuuEvent
    ev = VakuuEvent(run2)
    ev._cape_option().on_chosen()
    app2 = sum(1 for c in run2.deck if c.id == "apparition")
    print(f"  the Vakuu CAPE OPTION at 80/80 -> max_hp/hp = "
          f"{run2.max_hp}/{run2.hp}, apparitions {app2}")
    _say("max HP on the Vakuu path", run2.max_hp, 71)
    _say("  ... current HP", run2.hp, 71)

    # Reachability of a second grant path (rule 6).
    run3 = RunState(rng=random.Random(0))
    in_bag = "distinguished_cape" in set(run3.relic_grab_bag)
    print(f"  distinguished_cape ported={'distinguished_cape' in ALL_RELICS}  "
          f"rarity={ALL_RELICS['distinguished_cape'].rarity}  "
          f"in relic grab bag={in_bag}")
    out = subprocess.run(["git", "grep", "-n", "-F", "distinguished_cape",
                          "--", "sts2_rl"],
                         cwd=_REPO, capture_output=True, text=True).stdout
    print("  every sim reference to the relic id:")
    for line in out.splitlines():
        print("   ", line)
    _say("grant paths for distinguished_cape other than the Vakuu option",
         int(in_bag), 0)


# -- trialoffer: Trial NONDESCRIPT_GUILTY's two dropped card screens -----
def probe_trialoffer() -> None:
    print("trialoffer -- Trial.cs:177-187 NondescriptGuilty(): AddCurseToDeck"
          "<Doubt>, then TWO CardReward(ForNonCombatWithDefaultOdds("
          "[Character.CardPool]), 3, owner) handed to RewardsCmd.OfferCustom. "
          "events/trial.py:90-93 adds Doubt and nothing else.")
    from sts2_rl.events import make_event
    from sts2_rl.run import RunState

    offers: list = []

    def selector(purpose, candidates, count):
        offers.append((purpose, len(candidates), count))
        return list(candidates)[:count]

    run = RunState(rng=random.Random(0), card_selector=selector)
    run.max_hp, run.hp = 80, 80
    deck_before = len(run.deck)
    event = make_event("trial", run).begin()
    event.choose("ACCEPT")
    # Drive the NONDESCRIPT page whatever the roll landed on: rebuild until we
    # get it, so the probe measures the branch and not the roll.
    tries = 0
    while event.page != "NONDESCRIPT" and tries < 50:
        tries += 1
        run = RunState(rng=random.Random(tries), card_selector=selector)
        run.max_hp, run.hp = 80, 80
        deck_before = len(run.deck)
        event = make_event("trial", run).begin()
        event.choose("ACCEPT")
    print(f"  reached page {event.page!r} after {tries} reseeds; "
          f"options {event.option_keys()}")
    event.choose("GUILTY")
    added = len(run.deck) - deck_before
    print(f"  deck grew by {added} card(s); card-selection screens raised: "
          f"{offers}")
    _say("cards the NONDESCRIPT_GUILTY reward screens offer", 0, 6)
    _say("deck delta (Doubt only vs Doubt + up to 2 taken)", added, added)
    print("  (the game offers 2 screens x 3 cards; the player may take 0, 1 or "
          "2 of them, so the deck delta is 1..3 there and always exactly 1 "
          "here)")


# -- draws: shuffle draw counts for vakuu / tinker_time ------------------
def probe_draws() -> None:
    print("draws -- ListExtensions.UnstableShuffle (ListExtensions.cs:44-60) is "
          "top-down Fisher-Yates taking NextInt(i+1) for i = n-1 .. 1, i.e. "
          "n-1 draws. rng.Rng.shuffle (rng.py:270-273) is the same loop, so "
          "the parity paths are draw-for-draw comparable. "
          "IEnumerableExtensions.cs:17-20: TakeRandom(n, rng) == "
          "ToList().UnstableShuffle(rng).Take(n).")
    from sts2_rl.rng import Rng

    # vakuu: three UnstableShuffles of 3 / 3 / 4 elements, then [0] of each.
    from sts2_rl.events.vakuu import POOL_1, POOL_2, POOL_3
    rng = Rng(seed=1234)
    for pool in (POOL_1, POOL_2, POOL_3):
        lst = list(pool)
        rng.shuffle(lst)
    expected = (len(POOL_1) - 1) + (len(POOL_2) - 1) + (len(POOL_3) - 1)
    print(f"  vakuu pool sizes {len(POOL_1)}/{len(POOL_2)}/{len(POOL_3)}")
    _say("vakuu parity-branch draws off the event Rng", rng.counter, expected)

    # The legacy branch takes rng.choice(...) three times instead: same
    # distribution, a different number of draws off a different stream.
    class _Counting(random.Random):
        n = 0

        def random(self):
            type(self).n += 1
            return super().random()

    legacy = _Counting(0)
    _Counting.n = 0
    for pool in (POOL_1, POOL_2, POOL_3):
        legacy.choice(list(pool))
    print(f"  vakuu LEGACY branch (events/vakuu.py:38-43, rng.choice x3): "
          f"{_Counting.n} underlying draws vs the game's {expected}")

    # tinker_time: TakeRandom(2, Rng) over a 3-list, twice.
    rng2 = Rng(seed=1234)
    for _ in range(2):
        lst = [0, 1, 2]
        rng2.shuffle(lst)
    _say("tinker_time's two TakeRandom(2) calls, draws off the event Rng",
         rng2.counter, 4)


# -- ids: rule 5/6 discharge ---------------------------------------------
def probe_ids() -> None:
    print("ids -- rule 5/6: every content id the eight slice-B units name has "
          "to be ported for a LIVE claim about that branch.")
    from sts2_rl.cards.base import _CARD_CLASSES
    from sts2_rl.relics import ALL_RELICS

    cards = {
        "the_lantern_key": ["lantern_key"],
        "the_legends_were_true": ["spoils_map"],
        "this_or_that": ["clumsy"],
        "tinker_time": ["mad_science"],
        "trash_heap": ["caltrops", "clash", "distraction", "dual_wield",
                       "entrench", "hello_world", "outmaneuver", "rebound",
                       "rip_and_tear", "stack"],
        "trial": ["regret", "shame", "doubt"],
        "unrest_site": ["poor_sleep"],
        "vakuu": ["apparition"],
    }
    relics = {
        "trash_heap": ["darkstone_periapt", "dream_catcher", "hand_drill",
                       "maw_bank", "the_boot"],
        "vakuu": ["blood_soaked_rose", "whispering_earring", "fiddle",
                  "preserved_fog", "sere_talon", "distinguished_cape",
                  "choices_paradox", "music_box", "lords_parasol",
                  "jeweled_mask"],
    }
    missing_c, missing_r = [], []
    for unit, ids in cards.items():
        bad = [i for i in ids if i not in _CARD_CLASSES]
        missing_c += bad
        print(f"  {unit:24s} cards  {len(ids):2d} named, missing {bad}")
    for unit, ids in relics.items():
        bad = [i for i in ids if i not in ALL_RELICS]
        missing_r += bad
        print(f"  {unit:24s} relics {len(ids):2d} named, missing {bad}")
    _say("slice-B cards missing from the sim", len(missing_c), 0)
    _say("slice-B relics missing from the sim", len(missing_r), 0)

    # The Mysterious Knight encounter the_lantern_key declares.
    from sts2_rl.monsters.hive.flail_knight import (
        MYSTERIOUS_KNIGHT_EVENT_ENCOUNTER,
    )
    names = [c.__name__ for c in MYSTERIOUS_KNIGHT_EVENT_ENCOUNTER.monster_classes]
    print(f"  the_lantern_key encounter monsters: {names}")
    _say("MysteriousKnightEventEncounter monster count", len(names), 1)


# -- rng5b: EV-3's candidate set inside this slice -----------------------
_RNG_CALL = re.compile(r"self\.rng\.\w+\(")


def probe_rng5b() -> None:
    print("rng5b -- EV-3: C# events roll on the per-event `base.Rng`; the sim "
          "exposes it as Event.event_rng (events/base.py:84-88). Which of the "
          "eight slice-B modules roll only on the shared run rng?")
    # `self.rng.x(` misses two shapes these eight use: a helper taking the rng
    # as an argument (random_potion(self.rng)) and a local alias
    # (`rng = self.rng; rng.choice(...)`), so match `self.rng` itself.
    shared_only, both, none = [], [], []
    for unit in SLICE_B:
        src = (EVENTS_DIR / f"{unit}.py").read_text(encoding="utf-8")
        rolls = ("self.rng" in src or "event_rng" in src
                 or "run.transform_card(" in src)
        has_parity = "event_rng" in src
        if rolls and has_parity:
            both.append(unit)
        elif rolls:
            shared_only.append(unit)
        else:
            none.append(unit)
    print(f"  parity branch present: {both}")
    print(f"  shared rng ONLY: {shared_only}")
    print(f"  no roll at all: {none}")
    print("  NOTE the_legends_were_true is in 'shared rng ONLY' but EV-3 does "
          "NOT apply to it: TheLegendsWereTrue.cs:53 draws on "
          "Owner.PlayerRng.Rewards, not base.Rng -- that is EV-9.")
    ev3 = [u for u in shared_only if u != "the_legends_were_true"]
    print(f"  EV-3's slice-B site list: {ev3}")
    _say("slice-B modules rolling only on the shared run rng",
         len(shared_only), 0)


# -- quest: EV-10, the missing Quest clause on the transform screen ------
def probe_quest() -> None:
    print("quest -- EV-10. CardSelectCmd.FromDeckForTransformation "
          "(CardSelectCmd.cs:485-489) builds its list as "
          "`Deck.Cards.Where(c => c.Type != CardType.Quest && "
          "c.IsTransformable)`. RunState.transformable_cards "
          "(run.py:364-366) returns removable_cards() -- 'not Eternal' -- and "
          "drops the Quest clause. (For DECK cards IsTransformable really does "
          "equal IsRemovable, CardModel.cs:737-750, so that half of the sim's "
          "comment is right; and FromDeckForRemoval, CardSelectCmd.cs:621-625, "
          "genuinely has no Quest clause, so removable_cards() is correct.)")
    from sts2_rl.cards import make_card
    from sts2_rl.cards.base import _CARD_CLASSES, CardType
    from sts2_rl.run import RunState

    quest_ids = sorted(c.id for c in _CARD_CLASSES.values()
                       if c.card_type == CardType.QUEST)
    print(f"  ported Quest cards: {quest_ids}")

    run = RunState(rng=random.Random(0))
    run.deck = [make_card("strike"), make_card("spoils_map"),
                make_card("lantern_key")]
    offered = sorted(c.id for c in run.transformable_cards())
    print(f"  deck {[c.id for c in run.deck]} -> transform screen offers "
          f"{offered}")
    quest_offered = [c for c in run.transformable_cards()
                     if c.card_type == CardType.QUEST]
    _say("Quest cards on the transform screen", len(quest_offered), 0)

    # What a transformed Quest card becomes, to show the outcome is material.
    victim = [c for c in run.deck if c.id == "spoils_map"][0]
    into = run.transform_card(victim)
    print(f"  transforming spoils_map yields {into.id!r} "
          f"(rarity {into.rarity}) -- the Quest card is gone from the deck")
    _say("spoils_map still in the deck after the sim transforms it",
         any(c.id == "spoils_map" for c in run.deck), True)

    # Blast radius: every sim caller of the transform screen.
    out = subprocess.run(["git", "grep", "-n", "-F", "transformable_cards()",
                          "--", "sts2_rl"],
                         cwd=_REPO, capture_output=True, text=True).stdout
    print("  every transform-screen call site in the sim:")
    for line in out.splitlines():
        print("   ", line)

    # Rule 6: both sides reachable? The three Quest cards' grant paths.
    grants = subprocess.run(
        ["git", "grep", "-n", "-E",
         r"make_card\(\"(spoils_map|lantern_key|byrdonis_egg)\"\)",
         "--", "sts2_rl"],
        cwd=_REPO, capture_output=True, text=True).stdout
    print("  Quest-card grant paths (rule 6):")
    for line in grants.splitlines():
        print("   ", line)


# -- gate: UnrestSite's decimal 0.70 threshold in float ------------------
def probe_gate() -> None:
    print("gate -- UnrestSite.cs:28 is "
          "`(decimal)p.Creature.CurrentHp <= (decimal)p.Creature.MaxHp * 0.70m` "
          "-- exact base-10 decimal arithmetic. "
          "events/unrest_site.py:30 is `run.hp <= run.max_hp * 0.70`, binary "
          "float. Rule 5: does the representation ever move the gate?")
    from decimal import Decimal

    from sts2_rl.events.unrest_site import UnrestSite
    from sts2_rl.run import RunState

    run = RunState(rng=random.Random(0))
    diffs = []
    for max_hp in range(1, 401):
        for hp in range(0, max_hp + 1):
            run.max_hp, run.hp = max_hp, hp
            sim = UnrestSite.is_allowed(run)
            game = Decimal(hp) <= Decimal(max_hp) * Decimal("0.70")
            if sim != game:
                diffs.append((max_hp, hp, sim, game))
    print(f"  swept every (max_hp, hp) with max_hp <= 400: "
          f"{len(diffs)} disagreements")
    for d in diffs[:10]:
        print(f"    max_hp={d[0]} hp={d[1]} sim={d[2]} game={d[3]}")
    _say("(max_hp, hp) pairs where the float gate differs from the decimal one",
         len(diffs), 0)


PROBES = {
    "potionoffer": probe_potionoffer,
    "cape": probe_cape,
    "trialoffer": probe_trialoffer,
    "draws": probe_draws,
    "ids": probe_ids,
    "rng5b": probe_rng5b,
    "quest": probe_quest,
    "gate": probe_gate,
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
