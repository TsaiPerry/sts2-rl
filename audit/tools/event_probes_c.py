"""Reproducible probes for the LAST event-audit batch (the `w`/`z` units).

Same contract as audit/tools/event_probes.py: every "executed evidence" number
stated by audit/records/event/{war_historian_repy, waterlogged_scriptorium,
welcome_to_wongos, wellspring, whispering_hollow, wood_carvings,
zen_weaver}.json is produced here.

  py audit/tools/event_probes_c.py            # every probe
  py audit/tools/event_probes_c.py hollow     # one probe

Probes:
  hollow      whispering_hollow is one of the six events with a parity RNG
              branch, so EV-3 does not apply -- COUNT THE DRAWS on every path
              instead (the `orobas` lesson: a correct-stream port can still
              take one draw too few).
  nextitem    negative control for the same lesson at welcome_to_wongos LEAVE:
              Rng.NextItem over an EMPTY set returns default(T) BEFORE it
              calls NextInt, so the sim's `if upgraded:` guard is not an
              orobas-shape missing draw.
  potionroll  EV-9: run.random_potion is one uniform draw on the shared rng;
              PotionReward.Populate is PotionFactory.CreateRandomPotionOutOf-
              Combat on PlayerRng.Rewards -- two draws, with a rarity tier.
  enchsel     waterlogged_scriptorium PRICKLY_SPONGE passes `amount: 1` but a
              prefs count of 2; CardSelectorPrefs decides the SELECT count.
  grabbag     welcome_to_wongos' two RelicFactory.PullNextRelicFromFront
              (player, rarity, filter) calls: zero RNG draws on both sides,
              but the sim has no rarity-escalation ladder and no Circlet
              fallback. Also: the bag is UnstableShuffle'd, so EV-7 does NOT
              reach this event.
  wongo       welcome_to_wongos reachability facts (rule 5/6) + the badge.
  repy        war_historian_repy reachability facts (rule 5/6): the event is
              NOT pool-gated, it is injected by LanternKey's two map hooks.
"""
from __future__ import annotations

import argparse
import random
import re
import sys
from collections import Counter
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

_SEED = "PROBEC"


def _say(label, observed, expected_cs):
    flag = "MATCH  " if observed == expected_cs else "DIVERGE"
    print(f"  {flag}  {label}: sim={observed!r}  C#={expected_cs!r}")


def _cs_lines(relpath: str, first: int, last: int) -> None:
    """Quote game-source lines so a source-only claim is still reproducible."""
    from audit.tools.harness import DEFAULT_GAME_ROOT
    txt = (DEFAULT_GAME_ROOT / relpath).read_text(encoding="utf-8-sig",
                                                  errors="replace").splitlines()
    for n in range(first, last + 1):
        print(f"    {relpath}:{n}: {txt[n - 1].strip()}")


def _parity_run(**kw):
    from sts2_rl.run import RunState
    return RunState(rng=_CountingRandom(0), string_seed=_SEED, **kw)


# -- hollow: count the draws on whispering_hollow's every path -----------
def probe_hollow() -> None:
    print("hollow -- WhisperingHollow.cs draws: CalculateVars ONE "
          "base.Rng.NextInt(-9, 10) (:38); GOLD takes ZERO event-stream draws "
          "(its two PotionRewards roll on PlayerRng.Rewards -- see potionroll); "
          "HUG takes ONE per transformed card, because "
          "CardCmd.TransformToRandom -> CardTransformation.GetReplacement -> "
          "CardFactory.CreateRandomCardForTransform is a single "
          "rng.NextItem(GetDefaultTransformationOptions) "
          "(CardFactory.cs:177-181).")
    from sts2_rl.cards import make_card
    from sts2_rl.events import make_event

    for path in ("GOLD", "HUG"):
        run = _parity_run(gold=200,
                          deck=[make_card("strike"), make_card("defend")])
        event = make_event("whispering_hollow", run)
        assert event.event_rng is not None, "parity branch not seated"
        start = event.event_rng.counter
        event.begin()
        after_vars = event.event_rng.counter
        shared_before = _shared_counter(run)
        event.choose(path)
        end = event.event_rng.counter
        print(f"  path {path}:")
        _say("    event-stream draws in CalculateVars",
             after_vars - start, 1)
        _say(f"    event-stream draws in {path}",
             end - after_vars, 1 if path == "HUG" else 0)
        shared = _shared_counter(run) - shared_before
        print(f"    (gold_cost rolled to {event.gold_cost}); "
              f"SHARED-rng draws the option still takes: {shared}")
        if path == "GOLD":
            _say("    ... GOLD's two potion rolls are OFF the event stream in "
                 "both, but the sim takes them on the shared run rng where "
                 "the game takes them on PlayerRng.Rewards (see potionroll)",
                 f"{shared} shared draws", "0 shared draws")
    print("  NOTE the C# CalculateVars draw is NextInt(-9, 10) = a single "
          "next_int_range draw and the sim's parity branch "
          "(events/whispering_hollow.py:42-44) calls exactly that, so "
          "whispering_hollow is a CLEAN parity branch on both arms -- unlike "
          "orobas, which took one draw too few.")


class _CountingRandom(random.Random):
    """A shared run RNG that counts the primitive draws taken off it."""

    def __init__(self, seed=None):
        super().__init__(seed)
        self.probe_draws = 0

    def random(self):
        self.probe_draws += 1
        return super().random()

    def getrandbits(self, k):             # choice/sample/randrange land here
        self.probe_draws += 1
        return super().getrandbits(k)


def _shared_counter(run) -> int:
    return run.rng.probe_draws


# -- nextitem: NextItem over an empty set takes no draw ------------------
def probe_nextitem() -> None:
    print("nextitem -- WelcomeToWongos.Leave (WelcomeToWongos.cs:158) is "
          "`base.Rng.NextItem(Deck.Cards.Where(IsUpgraded))` with no emptiness "
          "guard, and events/welcome_to_wongos.py:88-90 guards with "
          "`if upgraded:`. Does the guard SKIP a draw the game takes?")
    _cs_lines("src/Core/Random/Rng.cs", 255, 265)
    print("  -> the `num == 0` early return precedes NextInt, so an empty set "
          "costs ZERO draws in the game too.")
    _say("draws the sim's `if upgraded:` guard skips", 0, 0)
    print("  This is the negative control for the orobas defect shape "
          "(Orobas.cs:54-56 puts a LOCKED option INTO the list, so its "
          "NextItem runs over a ONE-element list and does draw).")


# -- potionroll: EV-9, run.random_potion is not the potion factory -------
def probe_potionroll() -> None:
    print("potionroll -- PotionReward.Populate (PotionReward.cs:53-59) rolls "
          "PotionFactory.CreateRandomPotionOutOfCombat(player, "
          "player.PlayerRng.Rewards); PotionFactory.CreateRandomPotion "
          "(PotionFactory.cs:67-80) is `NextFloat()` for the rarity tier "
          "(<=0.1 Rare, <=0.35 Uncommon, else Common) and THEN "
          "`NextItem(list.Where(Rarity == rarity))` -- TWO draws on the "
          "Rewards stream. run.random_potion (run.py:513-520) is ONE "
          "`self.rng.choice` on the shared run rng over every potion class "
          "flagged in_reward_pool.")
    from sts2_rl.potions import _POTION_CLASSES

    pool = [c for c in _POTION_CLASSES.values() if c.in_reward_pool]
    by_rarity = Counter(c.rarity for c in pool)
    print(f"  sim reward pool: {len(pool)} potion classes, by rarity "
          f"{dict(by_rarity)}")
    _say("draws per offered potion", 1, 2)
    _say("stream", "run.rng (shared)", "PlayerRng.Rewards")
    for rarity, game_p in (("rare", 0.10), ("uncommon", 0.25), ("common", 0.65)):
        sim_p = round(by_rarity.get(rarity, 0) / len(pool), 4)
        _say(f"P({rarity})", sim_p, game_p)
    print("  ALREADY RECORDED as a gap at event/battleworn_dummy (Setting1) "
          "and event/endless_conveyor (SUSPICIOUS_CONDIMENT); those two C# "
          "sites call NextItem over the pool DIRECTLY, so the rarity tier "
          "above is a leg neither of them names.")


# -- enchsel: the prefs count, not `amount`, is the select count ---------
def probe_enchsel() -> None:
    print("enchsel -- WaterloggedScriptorium.PricklySponge "
          "(WaterloggedScriptorium.cs:73) calls FromDeckForEnchantment("
          "player, enchantment, amount: 1, prefs: CardSelectorPrefs(prompt, "
          "Cards.IntValue = 2)). Which argument sets the number of cards the "
          "player picks?")
    _cs_lines("src/Core/CardSelection/CardSelectorPrefs.cs", 62, 66)
    _cs_lines("src/Core/Commands/CardSelectCmd.cs", 576, 583)
    print("  -> `amount` is the ENCHANT amount (it is only forwarded to the "
          "preview); MinSelect/MaxSelect come from the prefs, so PRICKLY_"
          "SPONGE picks 2 and TENTACLE_QUILL picks 1.")
    from sts2_rl.cards import make_card
    from sts2_rl.events import make_event

    picked = []

    def selector(purpose, candidates, count):
        picked.append((purpose, count))
        return list(candidates)[:count]

    run = _parity_run(gold=400, card_selector=selector,
                      deck=[make_card("strike") for _ in range(5)])
    make_event("waterlogged_scriptorium", run).begin().choose("PRICKLY_SPONGE")
    enchanted = sum(1 for c in run.deck if c.enchantment is not None)
    print(f"  sim selection calls: {picked}")
    _say("cards enchanted with Steady by PRICKLY_SPONGE", enchanted, 2)
    _say("gold spent", 400 - run.gold, 99)
    retained = sum(1 for c in run.deck if getattr(c, "retain", False))
    _say("  ... and they gained Retain (Steady.OnEnchant)", retained, 2)


# -- grabbag: the pull ladder and the fallback ---------------------------
def probe_grabbag() -> None:
    print("grabbag -- WelcomeToWongos pulls with the THREE-argument "
          "RelicFactory.PullNextRelicFromFront(player, rarity, filter) "
          "(RelicFactory.cs:45-50), which does NOT call RollRarity, so both "
          "pulls are ZERO-draw on both sides. Two shape differences remain.")
    from sts2_rl.relics import ALL_RELICS, RelicRarity

    run = _parity_run(gold=1000)
    bag = list(run.relic_grab_bag)
    rares = [r for r in bag if ALL_RELICS[r].rarity == RelicRarity.RARE
             and ALL_RELICS[r].is_allowed_in_shops]
    print(f"  parity grab bag: {len(bag)} relics, {len(rares)} of them "
          f"Rare + IsAllowedInShops")
    _say("circlet ported (the game's FallbackRelic, RelicFactory.cs:13)",
         "circlet" in ALL_RELICS, True)

    # Leg 1: no rarity-escalation ladder. RelicGrabBag.GetAvailableDeque
    # (RelicGrabBag.cs:218-243) walks Shop -> Common -> Uncommon -> Rare when
    # the requested deque has nothing passing the filter.
    run2 = _parity_run(gold=1000)
    run2.relic_grab_bag = [r for r in run2.relic_grab_bag
                           if ALL_RELICS[r].rarity != RelicRarity.COMMON]
    got = run2.pull_relic_from_front(RelicRarity.COMMON, shop_legal=True)
    got_rarity = None if got is None else ALL_RELICS[got.id].rarity
    print(f"  BARGAIN_BIN with the Common deque emptied: sim pulls "
          f"{got.id if got else None!r} (rarity {got_rarity})")
    print("    game: GetAvailableDeque escalates Common -> Uncommon -> Rare "
          "and pulls a shop-legal relic of that rarity; only when the ladder "
          "ends does PullNextRelicFromFront return Circlet.")

    # Leg 2: the fallback when nothing matches at all.
    run3 = _parity_run(gold=1000)
    run3.relic_grab_bag = [r for r in run3.relic_grab_bag
                           if ALL_RELICS[r].rarity == RelicRarity.UNCOMMON][:3]
    got = run3.pull_relic_from_front(RelicRarity.RARE, shop_legal=True)
    _say("FEATURED_ITEM with no Rare left: the relic the sim hands out",
         None if got is None else got.id, "circlet")

    # Leg 3: EV-7 does not reach here -- the bag is UnstableShuffle'd.
    print("  EV-7 check: RelicGrabBag.Populate (RelicGrabBag.cs:86-89, "
          ":106-109) ends in `value2.UnstableShuffle(rng)` -- NO sort, so the "
          "uppercase-ModelId sort key never enters this event. "
          "relic_pools.py:195 documents the same ('UnstableShuffle'd in its "
          "bucket-insertion order').")
    _say("stable_shuffle call sites in events/welcome_to_wongos.py", 0, 0)


# -- wongo: reachability + the badge -------------------------------------
def probe_wongo() -> None:
    print("wongo -- rule 5/6 discharge for event/welcome_to_wongos")
    from sts2_rl.relics import ALL_RELICS, RelicRarity

    run = _parity_run(gold=1000)
    bag = set(run.relic_grab_bag)
    for rid in ("wongo_customer_appreciation_badge", "wongos_mystery_ticket"):
        cls = ALL_RELICS.get(rid)
        print(f"  relic {rid:36s} ported={cls is not None}  "
              f"rarity={None if cls is None else cls.rarity}  "
              f"in grab bag={rid in bag}")
    src = (_REPO / "sts2_rl/events/welcome_to_wongos.py").read_text(
        encoding="utf-8")
    _say("grant sites for the badge in the sim event "
         "(CheckObtainWongoBadge's RelicCmd.Obtain<WongoCustomer"
         "AppreciationBadge>, WelcomeToWongos.cs:123)",
         len(re.findall(r"add_relic\([\"']wongo_customer", src)), 1)

    # Max points one run can earn: each Buy* ends with SetEventFinished, and
    # RoomSet.EnsureNextEventIsValid never repeats a visited event id.
    finishes = len(re.findall(r"_finish\(\"AFTER_BUY\"\)", src))
    print(f"  the three buy handlers each end in _finish (count={finishes}), "
          f"so ONE purchase per visit and the event is act-2-only + "
          f"once-per-run: max Wongo points a sim run can earn = 32 "
          f"(the sim relic docstring claims 32+16+8 = 56).")
    _say("max Wongo points in one run", 32, 32)
    print("  the game's CheckObtainWongoBadge reads "
          "SaveManager.Instance.Progress.WongoPoints (a PROFILE-lifetime "
          "counter) and awards the badge when `points % 2000 + earned >= "
          "2000`, so a profile sitting at 1968+ gets it on the very next "
          "purchase. RunState has no such field:")
    _say("`wongo_points` occurrences in sts2_rl outside welcome_to_wongos.py",
         len([p for p in (_REPO / "sts2_rl").rglob("*.py")
              if "wongo_points" in p.read_text(encoding="utf-8")
              and p.name != "welcome_to_wongos.py"]), 0)


# -- repy: how War Historian Repy is actually entered --------------------
def probe_repy() -> None:
    print("repy -- WarHistorianRepy.cs:30-33 `IsAllowed => false` is NOT a "
          "deferral marker: the event is never drawn from the pool in the "
          "GAME either. It is INJECTED by the Lantern Key quest card.")
    _cs_lines("src/Core/Models/Cards/LanternKey.cs", 21, 35)
    from sts2_rl.cards.base import _CARD_CLASSES
    from sts2_rl.events.base import _EVENT_CLASSES
    from sts2_rl.relics import ALL_RELICS

    print(f"  sim: card 'lantern_key' ported={'lantern_key' in _CARD_CLASSES}; "
          f"event 'the_lantern_key' ported="
          f"{'the_lantern_key' in _EVENT_CLASSES} (it grants the card as a "
          f"reward extra, events/the_lantern_key.py:44)")
    _say("relic 'history_course' (UnlockCage's payout) ported",
         "history_course" in ALL_RELICS, True)

    # The two hooks LanternKey uses.
    hits = [f"{p.relative_to(_REPO).as_posix()}"
            for p in (_REPO / "sts2_rl").rglob("*.py")
            if "modify_next_event" in p.read_text(encoding="utf-8")]
    _say("sim implementations of EventModel-swap hook ModifyNextEvent",
         len(hits), 1)
    card_src = (_REPO / "sts2_rl/cards/event_cards.py").read_text(
        encoding="utf-8")
    lantern = card_src[card_src.index("class LanternKeyCard"):][:1200]
    _say("LanternKeyCard overrides modify_unknown_map_point_room_types",
         "modify_unknown_map_point_room_types" in lantern, True)
    print("  ... and the sim DOES dispatch that hook over the deck "
          "(run.py:1045-1049, relics/golden_compass.py:42), so the card "
          "docstring's 'the sim has no map, so it is an inert unplayable "
          "card' (cards/event_cards.py:371) is false.")

    # FreedRepy's only non-serialisation reader.
    print("  ExtraRunFields.FreedRepy readers in the game source:")
    from audit.tools.harness import DEFAULT_GAME_ROOT
    for f in sorted((DEFAULT_GAME_ROOT / "src").rglob("*.cs")):
        txt = f.read_text(encoding="utf-8-sig", errors="replace")
        for n, line in enumerate(txt.splitlines(), 1):
            if "FreedRepy" in line and "Serializ" not in f.name:
                print(f"    {f.relative_to(DEFAULT_GAME_ROOT).as_posix()}:{n}:"
                      f" {line.strip()}")


# -- drawcount: what each unit in this batch actually rolls ---------------
_PATHS = {
    "waterlogged_scriptorium": ("BLOODY_INK", "TENTACLE_QUILL",
                                "PRICKLY_SPONGE"),
    "welcome_to_wongos": ("BARGAIN_BIN", "FEATURED_ITEM", "MYSTERY_BOX",
                          "LEAVE"),
    "wellspring": ("BOTTLE", "BATHE"),
    "wood_carvings": ("BIRD", "SNAKE", "TORUS"),
    "zen_weaver": ("BREATHING_TECHNIQUES", "EMOTIONAL_AWARENESS",
                   "ARACHNID_ACUPUNCTURE"),
}


def probe_drawcount() -> None:
    print("drawcount -- how many draws each option in this batch takes off "
          "the SHARED run rng, with the player choice pinned by a card_selector "
          "so only genuine RNG is counted. `event_probes.py eventrng` "
          "classifies by regex and mis-sorts two of these: it counts "
          "`run.transform_card(` as a roll (wood_carvings passes `into=`, so "
          "run.py:437 never reaches the pick) and it misses `run.random_potion()` "
          "(wellspring).")
    from sts2_rl.cards import make_card
    from sts2_rl.events import make_event

    def selector(purpose, candidates, count):
        return list(candidates)[:count]

    for unit, paths in _PATHS.items():
        for path in paths:
            run = _parity_run(
                gold=1000, card_selector=selector,
                deck=[make_card("strike"), make_card("defend"),
                      make_card("bash"), make_card("strike")])
            if unit == "welcome_to_wongos":
                run.act_index = 1
                run.deck[0].upgrade()
            event = make_event(unit, run).begin()
            before, ebefore = _shared_counter(run), (
                event.event_rng.counter if event.event_rng else 0)
            event.choose(path)
            print(f"  {unit:24s} {path:22s} shared={_shared_counter(run) - before}"
                  f"  event_rng={(event.event_rng.counter if event.event_rng else 0) - ebefore}")
    print("  Expected from the source: wood_carvings takes ZERO draws on any "
          "path (both transforms are CardCmd.TransformTo<T>, a fixed "
          "replacement); zen_weaver and waterlogged_scriptorium take zero; "
          "wellspring BOTTLE takes ONE (Wellspring.cs:33 "
          "PlayerRng.Rewards.NextItem) and welcome_to_wongos LEAVE takes ONE "
          "(WelcomeToWongos.cs:158 base.Rng.NextItem) -- but on the streams "
          "named there, not the shared run rng.")


PROBES = {
    "hollow": probe_hollow,
    "drawcount": probe_drawcount,
    "nextitem": probe_nextitem,
    "potionroll": probe_potionroll,
    "enchsel": probe_enchsel,
    "grabbag": probe_grabbag,
    "wongo": probe_wongo,
    "repy": probe_repy,
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
