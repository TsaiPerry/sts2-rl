"""Reproducible execution probes for relic audit batch 16.

Batch 16's own probe module (the concurrency contract gives each parallel batch
its own file; `audit/tools/relic_probes.py` is read-only here and is still the
place to get the shared sweeps and the executed `turn-order` reference).

Binding rules 5 and 6: never justify `faithful` with an unreachability claim
you have not EXECUTED, and never label a gap LIVE without proving both sides
reachable with ported content.

  py audit/tools/relic_probes_b16.py              # every probe
  py audit/tools/relic_probes_b16.py boot-order   # one probe

Probes:
  pool            obtainability of batch 16's 15 relics
  boot-order      the_boot G1 -- ModifyHpLostAfterOstyLate is a SECOND C# pass;
                  the sim's flat list runs the relic BEFORE every power
  tea-position    tea_of_discourtesy G1 -- the hand-rolled random draw-pile
                  insert is mirrored vs CardPileCmd.add_to_draw, and skips
                  CardPileCmd._enter_combat
  mittens-power   toasty_mittens G1 -- the +1 Strength is missing entirely
  mailbox-rest    tiny_mailbox G1 -- the rest-heal reward hook is live and the
                  stub contributes nothing
  courier-price   the_courier G1 -- merchant prices are unchanged by the relic
  axe-tuning      tuning_fork G1 -- a replayed Skill counts once, not twice
  toolbox-stream  toolbox G1 -- the CombatCardGeneration stream is untouched
  top-empty       unceasing_top -- the potion route to an empty hand
  toybox-melt     toy_box -- melt removes the relic instead of disabling it,
                  and the 4 wax relics are granted rather than offered
  orobas-replace  touch_of_orobas -- the starter swap, executed
  egg-floor       toxic_egg -- still pullable past floor 41 (sweep B cluster)
  abacus-shuffle  the_abacus -- block on a mid-combat reshuffle
"""
from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

BATCH16 = [
    "tea_of_discourtesy", "the_abacus", "the_boot", "the_courier",
    "throwing_axe", "tiny_mailbox", "toasty_mittens", "toolbox",
    "touch_of_orobas", "toxic_egg", "toy_box", "tri_boomerang",
    "tungsten_rod", "tuning_fork", "unceasing_top",
]


# ── obtainability ────────────────────────────────────────────────────────

def probe_pool() -> None:
    """Which of batch 16's relics a run can actually obtain (binding rule 6)."""
    from sts2_rl.relic_pools import IRONCLAD_RELIC_POOL, SHARED_RELIC_POOL
    from sts2_rl.relics import make_relic

    bag = {rid.removeprefix("RELIC.").lower(): rarity
           for rid, rarity in SHARED_RELIC_POOL + IRONCLAD_RELIC_POOL}
    # Event/shrine grant paths, grepped out of sts2_rl/events/.
    event_paths = {
        "tea_of_discourtesy": "events/tea_master.py:60 (add_relic)",
        "the_boot": "events/trash_heap.py:15 (_RELICS)",
        "throwing_axe": "events/tanx.py:13 (relic pool)",
        "toasty_mittens": "events/tezcatara.py:17 (OPTION_POOL_2)",
        "touch_of_orobas": "events/orobas.py:72 (pool3)",
        "toy_box": "events/tezcatara.py:19 (OPTION_POOL_3)",
        "tri_boomerang": "events/tanx.py:31 (pool)",
    }
    for rid in BATCH16:
        r = make_relic(rid)
        where = (f"grab bag [{bag[rid]}]" if rid in bag
                 else event_paths.get(rid, "!! NO PORTED GRANT PATH"))
        print(f"  {rid:22s} {r.rarity.value:9s} {where}")


# ── the_boot ─────────────────────────────────────────────────────────────

def probe_boot_order() -> None:
    """the_boot G1: ModifyHpLostAfterOstyLate is C#'s SECOND HP-loss pass.

    Hook.ModifyHpLost (Hook.cs:1742-1762) runs `ModifyHpLostAfterOsty` over
    every listener and THEN `ModifyHpLostAfterOstyLate` over every listener.
    The Boot is one of only two Late implementers (the other is BufferPower),
    so in the game it always runs AFTER SlipperyPower/IntangiblePower. The sim
    has one flat registration-order pass (hooks.py:142-146) in which relics are
    registered at CombatState setup (combat.py:159) and powers only when
    applied, so a power gained mid-combat runs AFTER The Boot.
    """
    from sts2_rl import CombatState
    from sts2_rl.cmds import DamageCmd, PowerCmd
    from sts2_rl.monsters.base import Encounter
    from sts2_rl.monsters.overgrowth.inklets import Inklet
    from sts2_rl.monsters.underdocks.soul_fysh import SoulFysh
    from sts2_rl.powers import IntangiblePower, SlipperyPower
    from sts2_rl.relics import make_relic
    from sts2_rl.valueprops import DamageProps

    cases = (
        # Soul Fysh gains Intangible from its own FADE move (soul_fysh.py:76-79),
        # i.e. MID-combat -> registered after the relics.
        (SoulFysh, IntangiblePower, "SoulFysh + Intangible from its FADE move"),
        # Inklet/Vantom apply Slippery in __init__ (inklets.py:33-34,
        # vantom.py:34-35), which runs at combat.py:134 -- BEFORE the relics are
        # attached, so the sim happens to agree there. Included to show the
        # divergence turns on registration order, not on the relic.
        (Inklet, SlipperyPower, "Inklet + Slippery from its constructor"),
    )
    for monster_cls, power_cls, label in cases:
        cs = CombatState(
            rng=random.Random(0),
            relics=[make_relic("the_boot")],
            encounter=Encounter("probe", [monster_cls]),
        )
        enemy = cs.enemies[0]
        enemy.block = 0
        PowerCmd.apply(cs.hooks, enemy, power_cls, 1, applier=enemy)
        order = [type(l).__name__ for l in cs.hooks._listeners
                 if hasattr(l, "modify_hp_lost")]
        before = enemy.hp
        DamageCmd.deal(cs.hooks, enemy, 4, dealer=cs.player,
                       card=_powered_attack(), props=DamageProps.CARD)
        lost = before - enemy.hp
        print(f"  {label}")
        print(f"     sim modify_hp_lost listener order: {order}")
        print(f"     4 powered unblocked damage -> enemy loses {lost} HP"
              f"   (C#: pass 1 {power_cls.__name__} 4 -> 1, "
              f"pass 2 TheBoot 1 -> 5  ==>  5)")
    print("  Co-occurrence: The Boot is granted by the Trash Heap event, which "
          "is in the ACT-2 Underdocks pool (events/__init__.py:81), and Soul "
          "Fysh is an Underdocks monster -- same act.")


def _powered_attack():
    from sts2_rl.cards import make_card
    return make_card("strike")


def probe_boot_props() -> None:
    """the_boot N: `props.IsPoweredAttack()` vs the port's `card is not None
    and not card.is_unpowered`. Enumerate every ported damage site that could
    tell the two apart."""
    import re
    root = _REPO / "sts2_rl"
    card_nonmove = []
    noncard_move = []
    for path in sorted(root.rglob("*.py")):
        text = path.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r"DamageCmd\.deal\((.{0,320}?)\)\n", text,
                             re.DOTALL):
            call = " ".join(m.group(1).split())
            line = text[:m.start()].count("\n") + 1
            has_card = "card=" in call
            props = ("CARD_HP_LOSS" in call or "NON_CARD" in call
                     or "UNPOWERED" in call)
            if has_card and props:
                card_nonmove.append(f"{path.relative_to(_REPO)}:{line}  {call[:90]}")
            if not has_card and ("DamageProps.CARD\b" in call
                                 or "MONSTER_MOVE" in call):
                noncard_move.append(f"{path.relative_to(_REPO)}:{line}")
    print("  (a) card-sourced damage whose props are NOT a powered Move "
          "(sim would raise it to 5, C# would not):")
    for s in card_nonmove:
        print(f"      {s}")
    print("  (b) card-less powered-Move damage (C# would raise it, sim "
          f"bails): {noncard_move or 'NONE'}")

    # Executed: Omnislice's splash leg is Unpowered|Move with card=self.
    from sts2_rl import CombatState
    from sts2_rl.cards import make_card
    from sts2_rl.monsters.base import Encounter
    from sts2_rl.monsters.overgrowth.fuzzy_wurm_crawler import FuzzyWurmCrawler
    from sts2_rl.relics import make_relic
    print("  EXECUTED (a): Omnislice (cards/colorless_attacks.py:320-325) "
          "splashes with DamageProps.CARD_UNPOWERED and card=self, so "
          "IsPoweredAttack() is False in C# but the port's proxy "
          "`card is None or card.is_unpowered` passes (Omnislice.is_unpowered "
          "is False).")
    for relics in ([], ["the_boot"]):
        cs = CombatState(
            rng=random.Random(0),
            relics=[make_relic(r) for r in relics],
            encounter=Encounter("probe", [FuzzyWurmCrawler, FuzzyWurmCrawler]),
        )
        for e in cs.enemies:
            e.block = 0
            e.hp = 40
        card = make_card("omnislice")
        card._damage = 3           # so the splash leg lands in the 1..4 window
        cs.player.hand.clear()
        cs.player.hand.append(card)
        hp_before = [e.hp for e in cs.enemies]
        cs.play_card(0, target_idx=0)
        lost = [b - e.hp for b, e in zip(hp_before, cs.enemies)]
        print(f"     relics={relics}: HP lost per enemy {lost}")
    print("     ...and the two sides AGREE anyway: the splash amount is the "
          "FIRST leg's returned `dealt`, which The Boot has already floored at "
          "5 (its first leg is DamageProps.CARD, a powered Move). So while the "
          "port's proxy does let The Boot through on an unpowered card leg, no "
          "ported caller can present it with an amount in 1..4 -- the divergence "
          "is DORMANT, not live.")


# ── tea_of_discourtesy ───────────────────────────────────────────────────

def probe_tea_position() -> None:
    """tea_of_discourtesy G1: the relic hand-rolls the random draw-pile insert
    instead of calling CardPileCmd.add_to_draw, and drops the pile-orientation
    bridge that helper exists for (cmds.py:490-495)."""
    from sts2_rl import CombatState
    from sts2_rl.cards import make_card
    from sts2_rl.cmds import CardPileCmd
    from sts2_rl.relics import make_relic

    cs = CombatState(rng=random.Random(0), relics=[])
    pile = [make_card("strike") for _ in range(5)]
    cs.player.draw_pile = list(pile)

    class _R:
        def __init__(self, v): self.v = v
        def randrange(self, n): return self.v

    # Same RNG value through both code paths, with a stub that pins the draw.
    cs.combat_rng._accessors["shuffle"] = _R(1)
    cs.combat_rng.is_parity = True
    relic = make_relic("tea_of_discourtesy")
    relic.attach(cs)
    relic.on_combat_start()
    tea_idx = [i for i, c in enumerate(cs.player.draw_pile) if c.id == "dazed"]

    cs2 = CombatState(rng=random.Random(0), relics=[])
    cs2.player.draw_pile = list(pile)
    cs2.combat_rng._accessors["shuffle"] = _R(1)
    cs2.combat_rng.is_parity = True
    for _ in range(2):
        CardPileCmd.add_to_draw(cs2.hooks, cs2.player, make_card("dazed"))
    ref_idx = [i for i, c in enumerate(cs2.player.draw_pile) if c.id == "dazed"]

    print("  5-card draw pile, shuffle stream pinned to NextInt -> 1 "
          "(game index 1 = second from the TOP)")
    print(f"     tea_of_discourtesy.py:35-39 puts Dazed at sim indices {tea_idx}")
    print(f"     CardPileCmd.add_to_draw     puts Dazed at sim indices {ref_idx}"
          "   <- the correct orientation (count - p)")
    print(f"     agree: {tea_idx == ref_idx}")

    dazed = [c for c in cs.player.draw_pile if c.id == "dazed"]
    print(f"     _enter_combat skipped: card.combat={dazed[0].combat!r}, "
          f"registered as a hook listener="
          f"{any(c is dazed[0] for c in cs.hooks._listeners)}")
    print("     (CardPileCmd._enter_combat, cmds.py:455-461, sets card.combat, "
          "registers the listener and fires on_card_entered_combat)")


# ── toasty_mittens ───────────────────────────────────────────────────────

def probe_mittens_power() -> None:
    """toasty_mittens G1: ToastyMittens.cs:50 applies 1 Strength on EVERY
    BeforeHandDraw, outside the `if (cardModel != null)` branch. The port has
    no PowerCmd call at all."""
    from sts2_rl import CombatState
    from sts2_rl.relics import make_relic

    cs = CombatState(rng=random.Random(0), relics=[make_relic("toasty_mittens")])
    for turn in (1, 2, 3):
        print(f"  turn {turn}: player powers "
              f"{[(p, pw.amount) for p, pw in cs.player.powers.items()]}   "
              f"exhaust pile {len(cs.player.exhaust_pile)}   "
              f"(C#: strength {turn})")
        if turn < 3:
            cs.end_turn()


# ── tiny_mailbox ─────────────────────────────────────────────────────────

def probe_mailbox_rest() -> None:
    """tiny_mailbox G1: the stub's premise ("out-of-combat rest-site reward")
    is false -- RunState.rest_heal_rewards (run.py:1097-1110) dispatches
    modify_rest_site_heal_rewards over every relic, a sibling EVENT relic uses
    it, driver.py:388 surfaces `special_potions`, and run.random_potion exists.
    """
    from sts2_rl.relics import make_relic
    from sts2_rl.run import RunState

    for rid in (None, "tiny_mailbox", "dream_catcher"):
        run = RunState(rng=random.Random(4))
        if rid:
            run.add_relic(rid)
        rw = run.rest_heal_rewards()
        print(f"  relics={[r.id for r in run.relics]}")
        print(f"     cards={[c.id for c in rw.cards]}  "
              f"special_potions={[p.id for p in rw.special_potions]}   "
              f"(C# tiny_mailbox: 2 PotionRewards)")
    run = RunState(rng=random.Random(4))
    print(f"  run.random_potion() works: {run.random_potion().id}")


# ── the_courier ──────────────────────────────────────────────────────────

def probe_courier_price() -> None:
    """the_courier G1/G2: ModifyMerchantPrice and ShouldRefillMerchantEntry
    have no `Relic` base member and no dispatch site in shop.py, so a stocked
    entry costs the same with and without the relic and never restocks."""
    from sts2_rl.relics import Relic, make_relic
    from sts2_rl.run import RunState
    from sts2_rl.shop import MerchantInventory

    for rid in (None, "the_courier", "membership_card"):
        run = RunState(rng=random.Random(11))
        run.gold = 5000
        if rid:
            run.add_relic(rid)
        inv = MerchantInventory.create(run)
        costs = [e.cost for e in inv.all_entries]
        print(f"  relics={[r.id for r in run.relics]}  entry costs={costs}")
        if rid == "the_courier":
            print("     C#: every one of these x 0.8 (TheCourier.cs:19-26)")
        if rid == "membership_card":
            print("     C#: every one of these x 0.5 (MembershipCard.cs:18-29)")
    print(f"  Relic base has modify_merchant_price: "
          f"{hasattr(Relic, 'modify_merchant_price')}")
    print(f"  Relic base has should_refill_merchant_entry: "
          f"{hasattr(Relic, 'should_refill_merchant_entry')}")
    # Restock: buy one entry and see whether the slot refills.
    run = RunState(rng=random.Random(11))
    run.gold = 5000
    run.add_relic("the_courier")
    inv = MerchantInventory.create(run)
    entry = next(e for e in inv.all_entries if e.is_stocked)
    entry.purchase()
    print(f"  after purchase: is_stocked={entry.is_stocked}   "
          f"(C# with The Courier: RestockAfterPurchase, still stocked)")


# ── throwing_axe x tuning_fork ───────────────────────────────────────────

def probe_axe_tuning() -> None:
    """tuning_fork G1: C# fires Hook.AfterCardPlayed once per Replay iteration
    (CardModel.cs:1961, inside the play-count loop); the sim fires
    on_card_played once per play (combat.py:514). Throwing Axe is in this same
    batch and is the executed replay source."""
    from sts2_rl import CombatState
    from sts2_rl.cards import make_card
    from sts2_rl.relics import make_relic

    for relics in (["tuning_fork"], ["tuning_fork", "throwing_axe"]):
        fork = make_relic("tuning_fork")
        fork._skills_played = 9          # one Skill short of the 10 threshold
        rl = [fork] + [make_relic(r) for r in relics[1:]]
        cs = CombatState(rng=random.Random(0), relics=rl)
        cs.player.block = 0
        card = make_card("defend")       # a Skill
        cs.player.hand.clear()
        cs.player.hand.append(card)
        cs.play_card(0)
        print(f"  relics={relics}: skills_played 9 -> {fork._skills_played}, "
              f"block={cs.player.block}")
    print("     C# with Throwing Axe: AfterCardPlayed fires ONCE PER REPLAY "
          "ITERATION, so the Defend counts twice -- 9 -> 10 (7 Block, -10 -> 0) "
          "on iteration 0, then 0 -> 1 on iteration 1. Block total is 17 both "
          "ways, but the counter ends at 1 in the game and 0 in the sim, so "
          "every later Tuning Fork trigger in the run is one Skill late. This "
          "is audit/records/seam/hook_dispatch.json G4 at this relic's own site.")


# ── toolbox ──────────────────────────────────────────────────────────────

def probe_toolbox_stream() -> None:
    """toolbox G1: Toolbox.cs:27 names `RunState.Rng.CombatCardGeneration`.
    toolbox.py:25-27 calls random_pool_cards(combat._rng, ...) with NO parity
    branch, so a parity run draws from the legacy shared Random and the
    CombatCardGeneration stream never advances. relics/vexing_puzzlebox.py:29-33
    is the ported sibling that does it correctly."""
    import inspect

    from sts2_rl.relics import toolbox as tb
    from sts2_rl.relics import vexing_puzzlebox as vp

    for mod, name in ((tb, "toolbox"), (vp, "vexing_puzzlebox")):
        src = inspect.getsource(mod)
        print(f"  {name:18s} is_parity branch: {'is_parity' in src:<5} "
              f"card_gen stream: {'card_gen' in src:<5} "
              f"legacy shared rng: {'_rng' in src}")
    print("  -> toolbox is the only one of the two with no parity branch; its "
          "3 colorless options come off the shared Random in every mode.")


# ── unceasing_top ────────────────────────────────────────────────────────

def probe_top_empty() -> None:
    """unceasing_top: C#'s CheckForEmptyHand is called from TWO sites --
    CardModel.cs:1992 (after a card play) and PotionModel.cs:340 (after a
    potion use). The port only listens on on_card_played."""
    from sts2_rl import CombatState
    from sts2_rl.cards import make_card
    from sts2_rl.potions import make_potion
    from sts2_rl.relics import make_relic

    # (a) the card-play route -- ported and working.
    cs = CombatState(rng=random.Random(0), relics=[make_relic("unceasing_top")])
    cs.player.hand.clear()
    cs.player.hand.append(make_card("defend"))
    cs.player.draw_pile = [make_card("strike") for _ in range(3)]
    cs.play_card(0)
    print(f"  after playing the last hand card: hand={len(cs.player.hand)}  "
          "(C#: 1) -- the ported route")

    # (b) the potion route -- Ashwater exhausts the whole hand.
    cs2 = CombatState(rng=random.Random(0), relics=[make_relic("unceasing_top")])
    cs2.player.hand = [make_card("defend"), make_card("strike")]
    cs2.player.draw_pile = [make_card("strike") for _ in range(3)]
    potion = make_potion("ashwater")
    cs2.player.potions = [potion, None, None]
    cs2.use_potion(0)
    print(f"  after Ashwater exhausts the whole hand: hand={len(cs2.player.hand)}"
          "   (C#: 1 -- PotionModel.cs:340 CheckForEmptyHand -> "
          "UnceasingTop.AfterHandEmptied)")


# ── toy_box ──────────────────────────────────────────────────────────────

def probe_toybox_melt() -> None:
    """toy_box: (a) AfterObtained OFFERS 4 wax relics (RewardsCmd.OfferCustom)
    where the port grants them; (b) RelicCmd.Melt (RelicCmd.cs:89-93) leaves
    the relic in Player.Relics and only excludes it from the hook-listener walk
    (RunState.cs:569, CombatState.cs:431), where the port deletes it."""
    from sts2_rl.relics import Relic, make_relic
    from sts2_rl.run import RunState

    run = RunState(rng=random.Random(2))
    bag_before = len(run.relic_grab_bag)
    run.add_relic("toy_box")
    print(f"  after add_relic('toy_box'): relics="
          f"{[(r.id, r.is_wax) for r in run.relics]}")
    print(f"     grab bag {bag_before} -> {len(run.relic_grab_bag)}  "
          "(C#: 4 pulls too, but offered as a skippable RelicReward screen)")
    print(f"  Relic base has is_melted: {hasattr(Relic, 'is_melted')}   "
          f"(C# RelicModel.IsMelted gates BOTH listener walks and IsTradable)")

    tb = next(r for r in run.relics if r.id == "toy_box")
    for combat in range(1, 7):
        tb.after_combat_end(run, None)
        print(f"     combat {combat}: combats_seen={tb.combats_seen} "
              f"relic count={len(run.relics)} "
              f"wax={sum(1 for r in run.relics if r.is_wax)}")
    print("     C#: relic count stays 5 for the whole run; the melted ones sit "
          "in Relics as inert entries.")
    print(f"  is_used_up threshold: "
          f"{tb.COMBATS_PER_MELT * tb.RELICS} combats (C#: Combats*Relics = 12)")


# ── touch_of_orobas ──────────────────────────────────────────────────────

def probe_orobas_replace() -> None:
    """touch_of_orobas: RelicCmd.Replace (RelicCmd.cs:74-82) = Remove(original)
    -> AfterRemoved -> Obtain(replace, player, indexOfOriginal), which ALSO
    strips the replacement from both grab bags and stamps FloorAddedToDeck."""
    from sts2_rl.relics import Relic, make_relic
    from sts2_rl.run import RunState

    run = RunState(rng=random.Random(5))
    run.add_relic("burning_blood")   # RunState.start_run:659, the Ironclad starter
    print(f"  start relics={[(r.id, r.rarity.value) for r in run.relics]}")
    in_bag = [x for x in run.relic_grab_bag
              if (getattr(x, "id", None) or x) == "black_blood"]
    run.add_relic("touch_of_orobas")
    print(f"  after touch_of_orobas: {[r.id for r in run.relics]}"
          "   (C#: [black_blood, touch_of_orobas] -- Replace keeps the index)")
    print(f"     black_blood in the grab bag beforehand: {in_bag or 'no'}   "
          "(C# Obtain would strip it from both bags)")
    print(f"  Relic base has after_removed: {hasattr(Relic, 'after_removed')}"
          "   (C# RelicModel.AfterRemoved, called by RelicCmd.Remove)")
    r = make_relic("touch_of_orobas")
    print(f"  REFINEMENTS={r.REFINEMENTS}   (C# RefinementUpgrades has 5 "
          "entries; the other 4 starters are other characters')")
    # Circlet fallback: what happens with an unknown starter.
    print(f"  circlet is a registered sim relic: "
          f"{'circlet' in __import__('sts2_rl.relics', fromlist=['x'])._RELIC_CLASSES}")


# ── toxic_egg ────────────────────────────────────────────────────────────

def probe_egg_floor() -> None:
    """toxic_egg: `IsAllowed => IsBeforeAct3TreasureChest(runState)` (TotalFloor
    < 41). Confirms sweep B's 17-relic cluster at this unit's own site."""
    from sts2_rl.relics import Relic
    from sts2_rl.run import RunState

    print(f"  Relic base has is_allowed: {hasattr(Relic, 'is_allowed')}")
    run = RunState(rng=random.Random(9))
    run.total_floor = 60
    hits = 0
    for _ in range(len(run.relic_grab_bag)):
        r = run.pull_relic_from_front()
        if r is None:
            break
        if r.id == "toxic_egg":
            hits += 1
    print(f"  at total_floor=60 the grab bag still yields toxic_egg: "
          f"{bool(hits)}   (C#: IsAllowed False from floor 41)")

    # The reward path, and the NoHookUpgrades gate.
    from sts2_rl.cards import make_card
    from sts2_rl.relics import make_relic
    egg = make_relic("toxic_egg")
    cards = [make_card("defend"), make_card("strike"), make_card("dazed")]
    egg.modify_card_reward_options(run, cards)
    print(f"  reward offer upgrade levels: "
          f"{[(c.id, c.upgrade_level) for c in cards]}   "
          "(Skill upgraded, Attack and Status untouched)")
    print("  the `options.Flags.HasFlag(NoHookUpgrades)` gate has NO setter "
          "anywhere in the source: `grep -rn NoHookUpgrades src/` returns only "
          "the 3 egg relics reading it + the enum declaration.")


# ── the_abacus ───────────────────────────────────────────────────────────

def probe_abacus_shuffle() -> None:
    """the_abacus: AfterShuffle fires only from CardPileCmd.Shuffle
    (CardPileCmd.cs:917) -- i.e. from ShuffleIfNecessary and the explicit
    Shuffle command, NOT from the combat-start randomise."""
    from sts2_rl import CombatState
    from sts2_rl.cards import make_card
    from sts2_rl.relics import make_relic

    cs = CombatState(rng=random.Random(0), relics=[make_relic("the_abacus")])
    print(f"  block after combat start (no shuffle yet): {cs.player.block}  "
          "(C#: 0 -- the initial RandomizeOrderInternal is not a Shuffle)")
    cs.player.draw_pile = []
    cs.player.discard_pile = [make_card("strike") for _ in range(3)]
    cs.player.reshuffle_discard_into_draw()
    print(f"  block after a ShuffleIfNecessary reshuffle: {cs.player.block}  "
          "(C#: 6)")


PROBES = {
    "pool": probe_pool,
    "boot-order": probe_boot_order,
    "boot-props": probe_boot_props,
    "tea-position": probe_tea_position,
    "mittens-power": probe_mittens_power,
    "mailbox-rest": probe_mailbox_rest,
    "courier-price": probe_courier_price,
    "axe-tuning": probe_axe_tuning,
    "toolbox-stream": probe_toolbox_stream,
    "top-empty": probe_top_empty,
    "toybox-melt": probe_toybox_melt,
    "orobas-replace": probe_orobas_replace,
    "egg-floor": probe_egg_floor,
    "abacus-shuffle": probe_abacus_shuffle,
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
