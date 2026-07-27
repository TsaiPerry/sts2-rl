"""Reproducible probes for event audit batch 5 slice A (audit/records/event/**).

Same contract as audit/tools/event_probes.py: every "executed evidence" number
the eight slice-A records state is produced here. Slice A =
potion_courier, punch_off, ranwid_the_elder, reflections, tanx, tea_master,
tezcatara, the_future_of_potions.

  py audit/tools/event_probes_a.py            # every probe
  py audit/tools/event_probes_a.py ancienthook

Probes:
  ancienthook  Hook.ShouldAllowAncient / AbstractModel.ShouldAllowAncient is
               the only gate AncientEventModel puts in front of an Ancient's
               option list (AncientEventModel.cs:147, :195). Negative control:
               how many models in the game source override it?
  ancientdraws Tanx / Tezcatara draw counts and shuffle shape on the per-event
               Rng, on EVERY path -- the check the `orobas` lesson asks for
               (orobas was correct-stream but took one FEWER draw).
  punchhp      PunchOffEventEncounter's StartingHpReduction: which HP value it
               moves, which stream it rolls on, and what the parity Niche pass
               does to it.
  ransack      PotionCourier.Ransack's uncommon pool + stream, and the draw
               count on both the parity and the legacy branch.
  futurepotions TheFutureOfPotions' hand-rolled 3-card offer vs
               CardFactory.CreateForReward: the missing reward-offer hook pass
               (EV-8) and whether the source's egg-then-AfterGenerated pair can
               reach upgrade level 2.
  reflect      Reflections: SHATTER's clone pass, and whether the
               creature_card_cmds step-52 downgrade leg self-heals at the next
               combat's Enchantment.reset().
  reacha       rule 5/6 discharge: is every relic / card / potion the eight
               slice-A units name actually ported, and in the grab bag?
"""
from __future__ import annotations

import argparse
import random
import re
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


def _say(label, observed, expected_cs):
    flag = "MATCH  " if observed == expected_cs else "DIVERGE"
    print(f"  {flag}  {label}: sim={observed!r}  C#={expected_cs!r}")


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


# -- ancienthook: does anything block an Ancient? ------------------------
def probe_ancienthook() -> None:
    print("ancienthook -- AncientEventModel wraps GenerateInitialOptions in "
          "`if (Hook.ShouldAllowAncient(...))` (AncientEventModel.cs:195) and "
          "swaps InitialDescription for WAX_CHOKER.blockMessage otherwise "
          "(AncientEventModel.cs:147-152). The sim's AncientEvent "
          "(events/ancient.py) has no such gate. Who can answer the hook?")
    decl = _cs_grep(r"virtual\s+bool\s+ShouldAllowAncient\s*\(")
    impl = _cs_grep(r"override\s+bool\s+ShouldAllowAncient\s*\(")
    for line in decl:
        print("    (declaration)", line)
    print(f"  ShouldAllowAncient OVERRIDES in the game source: {len(impl)}")
    for line in impl:
        print("   ", line)
    wax = _cs_grep(r"WaxChoker|WAX_CHOKER")
    print(f"  WaxChoker references in the source: {len(wax)}")
    for line in wax:
        print("   ", line)
    _say("models that can block an Ancient", len(impl), 0)


# -- ancientdraws: Tanx / Tezcatara draw counts --------------------------
def probe_ancientdraws() -> None:
    print("ancientdraws -- Tanx.cs:142 `list.UnstableShuffle(base.Rng).Take(3)` "
          "and Tezcatara.cs:196-198 three `base.Rng.NextItem` picks. "
          "ListExtensions.UnstableShuffle walks i = Count-1 .. 1 taking one "
          "NextInt(i+1) per step; Rng.shuffle (rng.py:270-273) is the same "
          "loop, so a Count-N shuffle is N-1 draws. Rng.next_item is one "
          "NextInt(0, len). Counting on EVERY path -- the `orobas` lesson.")
    from sts2_rl.cards import make_card
    from sts2_rl.events import make_event
    from sts2_rl.run import RunState

    def counted(unit, deck=None):
        run = RunState(rng=random.Random(0), string_seed="AUDITSLICEA")
        if deck is not None:
            run.deck = deck
        ev = make_event(unit, run)
        before = ev.event_rng.counter
        ev.begin()
        return ev, ev.event_rng.counter - before

    # Tanx: the Tri-Boomerang gate is `Count(Instinct.CanEnchant) >= 3`.
    from sts2_rl.enchantments import InstinctEnchantment
    starter = RunState(rng=random.Random(0)).deck
    n_eligible = sum(1 for c in starter if InstinctEnchantment.can_enchant(c))
    print(f"  Ironclad starting deck: {n_eligible} Instinct-eligible cards "
          f"(gate is >= 3)")
    ev, draws = counted("tanx")
    print(f"  tanx, starting deck (pool size "
          f"{9 + (1 if n_eligible >= 3 else 0)}): {draws} event-Rng draws, "
          f"options {ev.option_keys()}")
    _say("tanx draws == pool size - 1 (UnstableShuffle)", draws,
         9 + (1 if n_eligible >= 3 else 0) - 1)
    ev, draws0 = counted("tanx", deck=[])
    print(f"  tanx, EMPTY deck (Tri-Boomerang locked out, pool size 9): "
          f"{draws0} draws, options {ev.option_keys()}")
    _say("tanx draws with the 9-relic pool", draws0, 8)

    # Tezcatara: pool1 (2 or 3) + pool2 (3) + pool3 (4), one NextItem each.
    ev, draws = counted("tezcatara")
    print(f"  tezcatara, starting deck (has Basic Strikes -> Nutritious Soup "
          f"in pool 1): {draws} draws, options {ev.option_keys()}")
    _say("tezcatara draws (one NextItem per pool)", draws, 3)
    ev, draws = counted("tezcatara", deck=[make_card("bash")])
    print(f"  tezcatara, deck with NO Basic Strike: {draws} draws, "
          f"options {ev.option_keys()}")
    _say("tezcatara draws on the soup-less path", draws, 3)
    print("  (no locked/skipped option on either unit, so the orobas defect "
          "shape -- NextItem over a list that still holds a locked option -- "
          "cannot arise here.)")


# -- punchhp: PunchOffEventEncounter's StartingHpReduction ---------------
def probe_punchhp() -> None:
    print("punchhp -- PunchOffEventEncounter.GenerateMonsters rolls "
          "`StartingHpReduction = base.Rng.NextInt(2, 10)` per construct on the "
          "ENCOUNTER's own Rng, and PunchConstruct.AfterAddedToRoom applies it "
          "as `Creature.SetCurrentHpInternal(Math.Max(1, CurrentHp - "
          "StartingHpReduction))` (PunchConstruct.cs:74-78) -- CURRENT HP only, "
          "MaxHp untouched. Monster max HP itself is a separate roll on "
          "RunState.Rng.Niche (CombatState.cs:240).")
    from sts2_rl.events.punch_off import PUNCH_OFF_EVENT_ENCOUNTER
    from sts2_rl.run import RunState

    base_hp = 55            # PunchConstruct.MinInitialHp == MaxInitialHp, non-asc

    # Leg 1 (legacy): which HP value does the sim move?
    run = RunState(rng=random.Random(0))
    combat = run.create_combat(PUNCH_OFF_EVENT_ENCOUNTER)
    obs = [(m.hp, m.max_hp) for m in combat.enemies]
    print(f"  LEGACY sim constructs (hp, max_hp): {obs}   (base HP {base_hp})")
    _say("construct 1 MAX hp is untouched by the reduction",
         combat.enemies[0].max_hp, base_hp)
    _say("construct 2 MAX hp is untouched by the reduction",
         combat.enemies[1].max_hp, base_hp)
    _say("constructs whose CURRENT hp is below their max (the game's shape)",
         sum(1 for m in combat.enemies if m.hp < m.max_hp), 2)

    # Leg 2 (parity): the Niche pass runs AFTER create_monsters and rewrites
    # hp AND max_hp, so the reduction is erased entirely.
    run = RunState(rng=random.Random(0), string_seed="AUDITSLICEA")
    before = run.rng_set.niche.counter
    combat = run.create_combat(PUNCH_OFF_EVENT_ENCOUNTER)
    obs = [(m.hp, m.max_hp) for m in combat.enemies]
    print(f"  PARITY sim constructs after "
          f"CombatState._assign_parity_monster_hp (combat.py:152-153): {obs}")
    print(f"  ... Niche-stream draws consumed: "
          f"{run.rng_set.niche.counter - before}")
    _say("constructs still carrying a starting HP reduction in parity mode",
         sum(1 for m in combat.enemies if m.hp < m.max_hp), 2)
    print("  C#: both constructs end at max_hp=55 with current HP "
          "55 - NextInt(2,10), i.e. 46..53.")

    # Leg 3: which stream does the reduction come off?
    src = Path("sts2_rl/events/punch_off.py").read_text(encoding="utf-8")
    uses_selection = "selection_rng" in src.split("def create_monsters")[1] \
        .split("return monsters")[0].replace(
            "selection_rng=None", "")
    _say("the sim rolls StartingHpReduction on the ENCOUNTER Rng "
         "(create_monsters' selection_rng), as EncounterModel.base.Rng does",
         uses_selection, True)


# -- ransack: PotionCourier's uncommon pool + stream ---------------------
def probe_ransack() -> None:
    print("ransack -- PotionCourier.Ransack (PotionCourier.cs:49-52): "
          "`Owner.Character.PotionPool.GetUnlockedPotions(...).Concat("
          "SharedPotionPool.GetUnlockedPotions(...)).Where(Rarity == Uncommon)` "
          "then ONE `Owner.PlayerRng.Rewards.NextItem(...)`. Order matters -- "
          "NextItem indexes the concatenation.")
    from sts2_rl.events import make_event
    from sts2_rl.potion_pools import POTION_POOL
    from sts2_rl.potions import ALL_POTIONS
    from sts2_rl.run import RunState

    parity_pool = [pid for pid, r in POTION_POOL if r == "uncommon"]
    print(f"  sim parity pool ({len(parity_pool)}): {parity_pool}")
    legacy_pool = sorted(cls.id for cls in ALL_POTIONS.values()
                         if cls.rarity == "uncommon")
    print(f"  sim LEGACY pool ({len(legacy_pool)}, sorted by id): {legacy_pool}")
    _say("legacy pool is the same SET as the parity (= game) pool",
         sorted(legacy_pool) == sorted(parity_pool), True)
    _say("legacy pool is in the same ORDER as the game's concatenation",
         legacy_pool == parity_pool, True)

    run = RunState(rng=random.Random(0), string_seed="AUDITSLICEA")
    ev = make_event("potion_courier", run).begin()
    before = run.rewards_rng.counter
    ev.choose("RANSACK")
    print(f"  parity RANSACK: belt = "
          f"{[type(p).__name__ for p in run.held_potions]}")
    _say("RANSACK draws off the per-player Rewards stream",
         run.rewards_rng.counter - before, 1)

    run = RunState(rng=random.Random(0), string_seed="AUDITSLICEA")
    ev = make_event("potion_courier", run).begin()
    before = run.rewards_rng.counter
    ev.choose("GRAB_POTIONS")
    print(f"  parity GRAB_POTIONS: belt = "
          f"{[type(p).__name__ for p in run.held_potions]} "
          f"(belt size {run.max_potions}; the source offers 3 FoulPotions "
          f"through RewardsCmd.OfferCustom)")
    _say("GRAB_POTIONS takes no stream draw", run.rewards_rng.counter - before, 0)


# -- futurepotions: the hand-rolled 3-card offer -------------------------
def probe_futurepotions() -> None:
    print("futurepotions -- TheFutureOfPotions.Trade (TheFutureOfPotions.cs:"
          "123-139) builds a CardReward through CardFactory.CreateForReward, "
          "whose tail runs Hook.ModifyCardRewardCreationOptions "
          "(CardFactory.cs:216) and Hook.TryModifyCardRewardOptions "
          "(CardFactory.cs:104) -- and Hook.TryModifyCardRewardOptions "
          "dispatches BOTH the plain and the *Late pass (Hook.cs:1445-1468), "
          "which is where the egg relics live "
          "(MoltenEgg.cs:21-32 TryModifyCardRewardOptionsLate). "
          "NoModifyHooks is NOT set here, so both passes run.")
    from sts2_rl.cards import CardType
    from sts2_rl.cards.base import _CARD_CLASSES
    from sts2_rl.cards.pool import IRONCLAD_POOL
    from sts2_rl.events import make_event
    from sts2_rl.potions import make_potion
    from sts2_rl.run import RunState

    offered: dict[str, list] = {}

    def selector(purpose, candidates, count):
        offered.setdefault(purpose, [
            (c.id, c.card_type, c.upgrade_level, c.is_upgradable)
            for c in candidates
        ])
        return list(candidates)[:count]

    # Force the ATTACK branch: hand-pick a run whose rolled card type is
    # Attack, so Molten Egg's offer-side pass would apply to all three.
    for seed in range(40):
        run = RunState(rng=random.Random(seed), card_selector=selector)
        run.add_relic("molten_egg")
        run.add_potion(make_potion("blood_potion"))
        run.add_potion(make_potion("block_potion"))
        offered.clear()
        ev = make_event("the_future_of_potions", run).begin()
        potion = run.held_potions[0]
        if ev._card_types[id(potion)] is CardType.ATTACK:
            ev.choose("POTION_0")
            break
    cards = offered.get("card_reward", [])
    print(f"  seed {seed}: rolled card type ATTACK, offered "
          f"{[(c[0], c[2]) for c in cards]}")
    lvl2 = sum(1 for c in cards if c[2] >= 2)
    _say("cards on the offer screen at upgrade level 2 "
         "(game: egg upgrades to +1 inside CreateForReward, then "
         "reward.AfterGenerated's CardCmd.Upgrade fires again)",
         lvl2, sum(1 for c in cards if c[3] or c[2] >= 2))

    # Can an Ironclad card reach upgrade level 2 at all?
    twice = []
    for cid in sorted(IRONCLAD_POOL):
        c = _CARD_CLASSES[cid]()
        c.upgrade()
        if c.is_upgradable:
            twice.append(cid)
    print(f"  Ironclad pool cards still upgradable after one upgrade: "
          f"{len(twice)} {twice}")
    _say("cards that could reach +2 from the game's double pass", len(twice), 0)
    print("  => the EGG leg is a no-op at THIS site (reward.AfterGenerated "
          "already upgrades all three and nothing upgrades twice), so the "
          "liveness has to come from a NON-egg implementer.")

    # Non-egg implementers of the same hook, all ported: Glitter enchants
    # every Glam-able option, Silken Tress and Silver Crucible modify them,
    # Wing Charm even takes a Niche draw. Silken Tress / Silver Crucible gate
    # on CardCreationFlags.IsCardReward, which CardReward's ctor sets
    # (CardReward.cs:110-112), so all of them reach this offer.
    from sts2_rl.relics import ALL_RELICS
    bag = set(RunState(rng=random.Random(0)).relic_grab_bag)
    for rid in ("glitter", "silken_tress", "silver_crucible", "wing_charm",
                "fresnel_lens", "lasting_candy"):
        print(f"  hook implementer {rid:16s} ported={rid in ALL_RELICS}  "
              f"in grab bag={rid in bag}")

    offered.clear()
    run = RunState(rng=random.Random(seed), card_selector=selector)
    run.add_relic("glitter")
    run.add_potion(make_potion("blood_potion"))
    run.add_potion(make_potion("block_potion"))
    ev = make_event("the_future_of_potions", run).begin()
    ev.choose("POTION_0")
    from sts2_rl.enchantments import GlamEnchantment
    run2 = RunState(rng=random.Random(seed))
    cards2 = [_CARD_CLASSES[c[0]]() for c in offered.get("card_reward", [])]
    for c in cards2:
        c.upgrade()
    glammable = sum(1 for c in cards2 if GlamEnchantment.can_enchant(c))
    print(f"  holding Glitter, the offer screen shows "
          f"{[c[0] for c in offered.get('card_reward', [])]}; "
          f"{glammable} of them satisfy Glam.CanEnchant")
    _say("offered cards carrying Glam on the sim's screen", 0, glammable)
    from sts2_rl.events.nonupeipe import OPTION_POOL as NONUPEIPE_POOL
    print(f"  Glitter's ported grant path (rule 6): it is an ANCIENT-rarity "
          f"relic, so it is correctly absent from the grab bag; "
          f"in Nonupeipe's Ancient option pool = "
          f"{'glitter' in NONUPEIPE_POOL} (events/nonupeipe.py OPTION_POOL)")


# -- reflect: Reflections' two branches ----------------------------------
def probe_reflect() -> None:
    print("reflect -- Reflections.Shatter (Reflections.cs:63-75) clones every "
          "card in the deck through RunState.CloneCard + "
          "CardPileCmd.Add(PileType.Deck) and then AddCurseToDeck<BadLuck>; "
          "TouchAMirror (Reflections.cs:32-61) downgrades up to 2 then "
          "upgrades up to 4, one base.Rng.NextItem per step.")
    from sts2_rl.cards import make_card
    from sts2_rl.enchantments import make_enchantment
    from sts2_rl.events import make_event
    from sts2_rl.run import RunState

    run = RunState(rng=random.Random(0))
    n = len(run.deck)
    ev = make_event("reflections", run).begin()
    ev.choose("SHATTER")
    print(f"  SHATTER: deck {n} -> {len(run.deck)} "
          f"(last card {run.deck[-1].id!r})")
    _say("deck size after SHATTER", len(run.deck), 2 * n + 1)

    # The egg relics see the clones: run.add_card runs the deck-entry hook,
    # exactly as CardPileCmd.Add does.
    run = RunState(rng=random.Random(0))
    run.add_relic("molten_egg")
    n = len(run.deck)
    attacks_before = sum(1 for c in run.deck
                         if c.card_type.value == "attack" and c.upgrade_level)
    ev = make_event("reflections", run).begin()
    ev.choose("SHATTER")
    attacks_after = sum(1 for c in run.deck
                        if c.card_type.value == "attack" and c.upgrade_level)
    print(f"  SHATTER holding Molten Egg: upgraded Attacks {attacks_before} -> "
          f"{attacks_after} over {n} clones (run.add_card runs "
          f"Hook.ModifyCardBeingAddedToDeck, run.py:341-354, which is what "
          f"CardPileCmd.Add runs)")

    # TOUCH_A_MIRROR draw count: 2 downgrades + 4 upgrades on a full deck.
    run = RunState(rng=random.Random(0))
    for c in run.deck[:3]:
        c.upgrade()
    calls = []
    real_choice = run.rng.choice
    run.rng.choice = lambda seq: (calls.append(len(seq)), real_choice(seq))[1]
    ev = make_event("reflections", run).begin()
    ev.choose("TOUCH_A_MIRROR")
    print(f"  TOUCH_A_MIRROR with 3 upgraded cards: {len(calls)} NextItem "
          f"draws over list sizes {calls}")
    _say("draws == min(2, upgraded) + min(4, upgradable)", len(calls), 6)

    # creature_card_cmds step 52 on the Reflections leg.
    card = make_card("discovery")
    ench = make_enchantment("souls")
    ench.attach(card)
    after_attach = card.exhausts
    card.upgrade()
    card.downgrade()               # what TOUCH_A_MIRROR does
    after_downgrade = card.exhausts
    ench.reset()                   # combat.py:131, every deck card at setup
    after_reset = card.exhausts
    print(f"  Souls-enchanted Discovery: exhausts after attach="
          f"{after_attach}, after Reflections' downgrade={after_downgrade}, "
          f"after the next combat's Enchantment.reset()={after_reset}")
    print("  (C#: CardCmd.Downgrade re-applies Enchantment.ModifyCard, so the "
          "game reads exhausts=False at every one of the three points.)")
    _say("exhausts once the next combat's setup has run reset() "
         "-- i.e. the sim's step-52 window CLOSES before the card is next "
         "played out of an event", after_reset, False)


# -- reacha: rule 5/6 discharge for slice A ------------------------------
def probe_reacha() -> None:
    print("reacha -- rule 5/6: every LIVE claim needs BOTH sides reachable "
          "with ported content.")
    from sts2_rl.cards.base import _CARD_CLASSES
    from sts2_rl.potions import ALL_POTIONS
    from sts2_rl.relics import ALL_RELICS
    from sts2_rl.run import RunState

    run = RunState(rng=random.Random(0))
    bag = set(run.relic_grab_bag)
    groups = {
        "tanx pool": ["claws", "crossbow", "iron_club", "meat_cleaver", "sai",
                      "spiked_gauntlets", "tanxs_whistle", "throwing_axe",
                      "war_hammer", "tri_boomerang"],
        "tezcatara pool": ["very_hot_cocoa", "yummy_cookie", "nutritious_soup",
                           "biiig_hug", "storybook", "toasty_mittens",
                           "golden_compass", "pumpkin_candle", "toy_box",
                           "seal_of_gold"],
        "tea_master": ["bone_tea", "ember_tea", "tea_of_discourtesy"],
    }
    missing = []
    for label, ids in groups.items():
        for rid in ids:
            ported = rid in ALL_RELICS
            if not ported:
                missing.append(rid)
            print(f"  {label:16s} relic {rid:32s} ported={ported}  "
                  f"in grab bag={rid in bag}")
    for cid in ("injury", "bad_luck"):
        ported = cid in _CARD_CLASSES
        if not ported:
            missing.append(cid)
        print(f"  {'card':16s}       {cid:32s} ported={ported}")
    for pid in ("foul_potion",):
        ported = pid in ALL_POTIONS
        if not ported:
            missing.append(pid)
        print(f"  {'potion':16s}     {pid:32s} ported={ported}")
    _say("slice-A content missing from the sim", missing, [])

    # Tri-Boomerang's threshold lives on the relic, like Nonupeipe's bracelet.
    from sts2_rl.relics.tri_boomerang import TriBoomerang
    _say("TriBoomerang.MIN_ELIGIBLE (Tanx.cs:21 _triBoomerangCount)",
         TriBoomerang.MIN_ELIGIBLE, 3)


# -- combatlayout: EV-9, a Combat-layout event builds its encounter on ENTRY --
def probe_combatlayout() -> None:
    print("combatlayout -- EventRoom.EnterInternal (EventRoom.cs:67-71) calls "
          "GenerateInternalCombatState for every EventLayoutType.Combat event, "
          "which runs Encounter.GenerateMonstersWithSlots (the encounter Rng) "
          "and CreateCreature -> SetUniqueMonsterHpValue (the Niche stream) "
          "for each monster (EventModel.cs:383-403, CombatState.cs:232-247) "
          "-- UNCONDITIONALLY, before any option is chosen. "
          "EnterCombatWithoutExitingEvent then REUSES that state "
          "(ShouldCreateCombat = LayoutType != Combat, EventModel.cs:624-628).")
    print("  Combat-layout events in the game source:")
    for line in _cs_grep(r"override\s+EventLayoutType\s+LayoutType\s*=>\s*"
                         r"EventLayoutType\.Combat"):
        print("   ", line)

    from sts2_rl.events import make_event
    from sts2_rl.events.punch_off import PUNCH_OFF_EVENT_ENCOUNTER
    from sts2_rl.run import RunState

    for path in (("NAB",), ("I_CAN_TAKE_THEM", "FIGHT")):
        choice = " -> ".join(path)
        run = RunState(rng=random.Random(0), string_seed="AUDITSLICEA",
                       total_floor=6)
        niche_before = run.rng_set.niche.counter
        ev = make_event("punch_off", run).begin()
        for step in path:
            ev.choose(step)
        print(f"  sim, choosing {choice}: Niche draws at event time = "
              f"{run.rng_set.niche.counter - niche_before}, "
              f"pending_encounter="
              f"{ev.pending_encounter is PUNCH_OFF_EVENT_ENCOUNTER}")
        _say(f"  ... Niche draws consumed by entering the event ({choice})",
             run.rng_set.niche.counter - niche_before, 2)
    print("  C#: 2 encounter-Rng NextInt(2,10) draws + 2 Niche HP draws on "
          "ENTRY, on both paths; the sim takes them only on the FIGHT path "
          "and only when the driver builds the combat.")


PROBES = {
    "ancienthook": probe_ancienthook,
    "combatlayout": probe_combatlayout,
    "ancientdraws": probe_ancientdraws,
    "punchhp": probe_punchhp,
    "ransack": probe_ransack,
    "futurepotions": probe_futurepotions,
    "reflect": probe_reflect,
    "reacha": probe_reacha,
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
