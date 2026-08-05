"""Execution probes for relic audit batch 9 (lost_coffer .. mr_struggles).

Companion to `audit/tools/relic_probes.py` (batches 1-3 + the pool-wide
sweeps), which stays READ-ONLY to this batch per the concurrency contract.
Every reachability claim an `audit/records/relic/*.json` record from batch 9 makes is
produced here so a later auditor re-derives the number instead of trusting a
throwaway script (binding rules 5 and 6).

  py audit/tools/relic_probes_b09.py              # every probe
  py audit/tools/relic_probes_b09.py b09-pool     # one probe

Probes:
  b09-pool         obtainability of the 15 units + massive_scroll's UNreachability
  b09-isallowed    the IsBeforeAct3TreasureChest floor gate (lucky_fysh /
                   meal_ticket / molten_egg) -- sweep B cluster, confirmed live
  b09-fysh         lucky_fysh: 15 gold never granted (deck add AND transform)
  b09-meal-ticket  meal_ticket: 15 HP never healed on a shop room entry
  b09-membership   membership_card: shop prices are not halved
  b09-meat-bone    meat_on_the_bone: AfterCombatVictoryEarly vs one flat pass
  b09-wisp-replay  lost_wisp: per-Replay AfterCardPlayed (8 vs 16 damage)
  b09-struggles    mr_struggles: the missing _check_win() its sibling has
  b09-molten       molten_egg: transform drops the deck-add hook; NoHookUpgrades
                   has zero producers; multi-upgrade census
  b09-maw-bank     maw_bank: 12 gold per room entered, disabled after a purchase
  b09-simple       mango / meat_cleaver / miniature_tent / miniature_cannon /
                   mercury_hourglass / lost_coffer -- the confirmations
"""
from __future__ import annotations

import argparse
import random
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

BATCH9 = [
    "lost_coffer", "lost_wisp", "lucky_fysh", "mango", "massive_scroll",
    "maw_bank", "meal_ticket", "meat_cleaver", "meat_on_the_bone",
    "membership_card", "mercury_hourglass", "miniature_cannon",
    "miniature_tent", "molten_egg", "mr_struggles",
]

_GAME = Path(r"c:\Users\Perry\Desktop\Slay the Spire 2")


# ── b09-pool ──────────────────────────────────────────────────────────────
def probe_pool() -> None:
    """Where each batch-9 relic can come from (rule 6, first half).

    Grab-bag membership from the transcribed C# pools (relic_pools.py); every
    other grant path is a literal relic id somewhere under sts2_rl/.
    """
    from sts2_rl.relic_pools import IRONCLAD_RELIC_POOL, SHARED_RELIC_POOL
    from sts2_rl.relics import ALL_RELICS

    bag = {rid.removeprefix("RELIC.").lower(): rarity
           for rid, rarity in SHARED_RELIC_POOL + IRONCLAD_RELIC_POOL}
    for rid in BATCH9:
        srcs = subprocess.run(
            ["git", "grep", "-l", f'"{rid}"', "--", "sts2_rl"],
            capture_output=True, text=True, cwd=_REPO,
        ).stdout.split()
        srcs = [s for s in srcs if not s.endswith(f"relics/{rid}.py")]
        print(f"  {rid:<20} registered={rid in ALL_RELICS} "
              f"bag={bag.get(rid, '-'):<9} granted_by={srcs or ['(none)']}")

    # massive_scroll: the ONLY unit in the batch whose verdicts rest on
    # unreachability, so it gets an executed proof rather than a claim.
    print("\n  -- massive_scroll unreachability (rule 5) --")
    print(f"     in grab bag: {'massive_scroll' in bag}  "
          f"(rarity={ALL_RELICS['massive_scroll'].rarity.value}; "
          f"RelicGrabBag takes Common/Uncommon/Rare/Shop only)")
    from sts2_rl.events.neow import POSITIVE_RELICS, neow_relic_pool
    from sts2_rl.run import RunState
    run = RunState(rng=random.Random(0))
    pool = neow_relic_pool(run)
    print(f"     listed in Neow.PositiveOptions: "
          f"{'massive_scroll' in POSITIVE_RELICS}")
    print(f"     survives neow_relic_pool's IsAllowedAtNeow filter: "
          f"{'massive_scroll' in pool}  "
          f"(is_allowed_at_neow="
          f"{ALL_RELICS['massive_scroll'].is_allowed_at_neow})")
    # Neow's initial 3 options, over many seeds: it must never appear.
    from sts2_rl.events.base import make_event
    hits = 0
    for seed in range(400):
        r = RunState(rng=random.Random(seed))
        ev = make_event("neow", r)
        ev.begin()
        keys = [o.key for o in ev.options]
        if any("MASSIVE" in k.upper() for k in keys):
            hits += 1
    print(f"     Neow initial options over 400 seeds containing it: {hits}")
    from sts2_rl.relics import make_relic
    print(f"     merchant_cost="
          f"{make_relic('massive_scroll').merchant_cost} "
          f"(Ancient sentinel; shop relic stock is pulled from the grab bag, "
          f"which excludes it)")
    print("     C# NOTE: RelicModel.IsAllowedAtNeow(player) DEFAULTS to "
          "IsAllowed(player.RunState) (RelicModel.cs:443-446), so C#'s Neow\n"
          "     filter reaches MassiveScroll.IsAllowed's `Players.Count > 1` "
          "through the Neow flag -- the sim's separate is_allowed_at_neow=False\n"
          "     flag lands on the same answer for this relic.")


# ── b09-isallowed ─────────────────────────────────────────────────────────
def probe_isallowed() -> None:
    """The IsBeforeAct3TreasureChest floor gate, for this batch's 3 members.

    Sweep B (`relic_probes.py sweep-isallowed`) puts lucky_fysh,
    meal_ticket and molten_egg in the 17-relic `TotalFloor < 41` cluster.
    Confirmed here rather than re-derived: the sim's Relic base declares no
    is_allowed member at all, and the grab bag still yields all three well
    past floor 41.
    """
    from sts2_rl.relics.base import Relic
    from sts2_rl.run import RunState

    print(f"  hasattr(Relic, 'is_allowed'): {hasattr(Relic, 'is_allowed')}  "
          f"(C#: RelicModel.IsAllowed, MoltenEgg.cs:16-19, "
          f"MealTicket.cs:17-20, LuckyFysh.cs:19-22)")
    print(f"  IsBeforeAct3TreasureChest = TotalFloor < 41 single-player "
          f"(RelicModel.cs:452-456)")
    targets = {"lucky_fysh", "meal_ticket", "molten_egg"}
    for seed in (0, 1, 2):
        run = RunState(rng=random.Random(seed))
        run.total_floor = 60
        pulled: list[str] = []
        for _ in range(260):
            r = run.pull_relic_from_front()
            if r is None:
                break
            pulled.append(r.id)
        found = sorted(targets & set(pulled))
        print(f"  seed={seed} total_floor={run.total_floor}: bag still yields "
              f"{found or '(none)'}  of {len(pulled)} pulls")
    print("  C# stops offering all three from floor 41 (the act-3 treasure "
          "chest) onward. Pool composition diverges, and a wrong pull shifts "
          "every later pull.")


# ── b09-fysh ──────────────────────────────────────────────────────────────
def probe_fysh() -> None:
    """Lucky Fysh's 15 gold on a card entering the deck.

    LuckyFysh.cs:24-32 fires on AfterCardChangedPiles whenever the card's new
    pile is PileType.Deck and the card is the owner's, and calls
    PlayerCmd.GainGold(15). The port is a behaviourless stub whose docstring
    says "no gold system in the sim" -- RunState.gold, RunState.gain_gold and
    the after_card_added_to_deck dispatch at run.py:353 all exist (sweep C).
    """
    from sts2_rl.cards import make_card
    from sts2_rl.run import RunState

    for relics in ([], ["lucky_fysh"]):
        run = RunState(rng=random.Random(3))
        for rid in relics:
            run.add_relic(rid)
        before = run.gold
        run.add_card(make_card("strike"))
        run.add_card(make_card("defend"))
        print(f"  relics={relics or ['(none)']}: 2 cards added to deck -> "
              f"gold {before} -> {run.gold}  (C# with the relic: +30)")

    # Second half: the DECK TRANSFORM path also fires the deck-add hooks in C#
    # (CardCmd.cs:429 ModifyCardBeingAddedToDeck, :447 AfterCardChangedPiles)
    # and RunState.transform_card fires neither.
    run = RunState(rng=random.Random(3))
    run.add_relic("lucky_fysh")
    card = run.deck[0]
    before = run.gold
    run.transform_card(card)
    print(f"  transform_card: gold {before} -> {run.gold}  "
          f"(C#: +15, CardCmd.cs:447)")


# ── b09-meal-ticket ───────────────────────────────────────────────────────
def probe_meal_ticket() -> None:
    """Meal Ticket's 15 HP heal on entering a MerchantRoom.

    MealTicket.cs:22-29: AfterRoomEntered, `!Owner.Creature.IsDead && room is
    MerchantRoom` -> CreatureCmd.Heal(15). The port is a behaviourless stub;
    the sim dispatches after_room_entered at run.py:983 with the RoomType, and
    RoomType.SHOP is the MerchantRoom.
    """
    from sts2_rl.relics.base import Relic
    from sts2_rl.rooms import RoomType
    from sts2_rl.run import RunState

    for relics in ([], ["meal_ticket"]):
        run = RunState(rng=random.Random(11))
        for rid in relics:
            run.add_relic(rid)
        run.hp = 40
        for r in list(run.relics):
            r.after_room_entered(run, None, RoomType.SHOP)
        print(f"  relics={relics or ['(none)']}: hp 40 -> {run.hp} on a "
              f"RoomType.SHOP entry  (C# with the relic: 55)")
    print(f"  Relic.after_room_entered defined on the base: "
          f"{'after_room_entered' in vars(Relic)}; dispatched at run.py:983")


# ── b09-membership ────────────────────────────────────────────────────────
def probe_membership() -> None:
    """Membership Card's 50% shop discount.

    MembershipCard.cs:18-29 overrides ModifyMerchantPrice; MerchantEntry.Cost
    (MerchantEntry.cs:19-29) runs Hook.ModifyMerchantPrice on every read while
    the current room is a MerchantRoom. The sim's shop.py computes each entry's
    `cost` once in _calc_cost with NO relic hook anywhere.
    """
    from sts2_rl.shop import MerchantInventory
    from sts2_rl.run import RunState

    for relics in ([], ["membership_card"]):
        run = RunState(rng=random.Random(5))
        for rid in relics:
            run.add_relic(rid)
        inv = MerchantInventory.create(run)
        costs = [e.cost for e in inv.all_entries]
        print(f"  relics={relics or ['(none)']}: entry costs={costs}")
    print("  C# halves every one of them (and truncates). Identical lists = "
          "the gap. grep 'modify_merchant_price' over sts2_rl/:")
    out = subprocess.run(
        ["git", "grep", "-n", "modify_merchant_price", "--", "sts2_rl"],
        capture_output=True, text=True, cwd=_REPO,
    ).stdout.strip()
    print(f"    {out or '(zero hits -- no such hook exists)'}")


# ── b09-meat-bone ─────────────────────────────────────────────────────────
def probe_meat_bone() -> None:
    """Meat on the Bone's heal runs in a SEPARATE, EARLIER pass in C#.

    Hook.AfterCombatVictory (Hook.cs:340-351) makes TWO full passes over every
    listener: AfterCombatVictoryEarly first, then AfterCombatVictory. Meat on
    the Bone is the ONLY AfterCombatVictoryEarly implementer in the whole game,
    so its threshold test always sees the pre-heal HP. The sim has one flat
    on_combat_end pass in listener-registration order, and Burning Blood (the
    Ironclad starter, so relic index 0) heals first.
    """
    from sts2_rl import CombatState
    from sts2_rl.relics import make_relic

    for relics in (["meat_on_the_bone"],
                   ["burning_blood", "meat_on_the_bone"],
                   ["meat_on_the_bone", "burning_blood"]):
        cs = CombatState(rng=random.Random(0),
                         relics=[make_relic(r) for r in relics],
                         max_hp=80, current_hp=38)
        for e in cs.enemies:
            e.hp = 0
            e.retained_after_death = False
        cs._end_combat(player_won=True)
        print(f"  relics={relics}\n"
              f"    hp 38 (threshold 40) -> {cs.player.hp}")
    print("  C# order is fixed: Early (Meat +12) then AfterCombatVictory "
          "(Burning Blood +6) = 56 in every case.")
    print("  The sim's on_combat_end order is run.relics order; Burning Blood "
          "is granted at start_run so it is index 0 and always runs first.")


# ── b09-wisp-replay ───────────────────────────────────────────────────────
def probe_wisp_replay() -> None:
    """Lost Wisp x a Replay source: C# fires AfterCardPlayed per iteration.

    CardModel.cs:1904-1963 builds a fresh CardPlay inside the play-count loop
    and fires Hook.AfterCardPlayed INSIDE it, so a card played twice triggers
    Lost Wisp twice (8 + 8). The sim runs the whole play-count loop and calls
    hooks.on_card_played ONCE afterwards (combat.py:514). Same mechanism as
    unsettling_lamp G1 / audit/records/seam/hook_dispatch.json G4.
    """
    from sts2_rl import CombatState
    from sts2_rl.cards import CardType, make_card
    from sts2_rl.cards.base import _CARD_CLASSES
    from sts2_rl.relics import make_relic

    powers = sorted(cid for cid, c in _CARD_CLASSES.items()
                    if c.card_type == CardType.POWER)
    print(f"  ported Power cards: {len(powers)} (e.g. {powers[:6]})")
    pick = "inflame" if "inflame" in powers else powers[0]

    for relics in (["lost_wisp"], ["lost_wisp", "throwing_axe"]):
        cs = CombatState(rng=random.Random(0),
                         relics=[make_relic(r) for r in relics])
        enemy = cs.enemies[0]
        enemy.hp = enemy.max_hp = 200
        card = make_card(pick)
        cs.player.hand.clear()
        cs.player.hand.append(card)
        cs.player.energy = 9
        before = enemy.hp
        cs.play_card(0)
        print(f"  relics={relics}: playing '{pick}' -> enemy HP "
              f"{before} -> {enemy.hp} (damage {before - enemy.hp})")
    print("  C#: 8 alone, 8+8=16 with Throwing Axe (the first card of the "
          "combat is played twice).")


# ── b09-struggles ─────────────────────────────────────────────────────────
def probe_struggles() -> None:
    """Mr Struggles omits the _check_win() its sibling Mercury Hourglass has.

    Both relics deal turn-start AoE from on_player_turn_started. C# runs
    CheckWinCondition right after the player's turn setup
    (CombatManager.cs:573 -- audit/records/seam/turn_structure.json step 27, gap
    G13), so a lethal turn-start tick ends the fight there. The sim has no
    such check in two windows: the turn-1 construction path (combat.py:208-209)
    and the EXTRA-TURN path (combat.py:648-652). mercury_hourglass.py:29 calls
    Relic._check_win() to compensate; mr_struggles.py does not.
    """
    from sts2_rl import CombatState
    from sts2_rl.cards import make_card
    from sts2_rl.relics import make_relic

    for rid in ("mercury_hourglass", "mr_struggles"):
        cs = CombatState(rng=random.Random(0),
                         relics=[make_relic(rid), make_relic("paels_eye")])
        # End turn 1 with no cards played -> Pael's Eye grants an extra turn.
        enemy = cs.enemies[0]
        enemy.hp = 2
        cs.player.hand.clear()
        cs.end_turn()
        print(f"  {rid:<18} extra turn (turn={cs.turn}): enemy hp={enemy.hp} "
              f"all_dead={cs._all_enemies_dead()} phase={cs.phase.name} "
              f"result={cs.result}")
    print("  C# ends the combat in both rows (CheckWinCondition after "
          "SetupPlayerTurn). A sim run that continues hands the agent a turn "
          "with no living enemies, and the recorded turn count diverges.")
    # CONTROL: the ORDINARY end_turn path has its own post-setup win check
    # (combat.py:681-685), so the gap is confined to the two unchecked windows.
    for rid in ("mercury_hourglass", "mr_struggles"):
        cs = CombatState(rng=random.Random(0), relics=[make_relic(rid)])
        for e in cs.enemies:
            e.hp = 1
        cs.player.hand.clear()
        cs.end_turn()          # enemy side runs, then turn 2 setup
        print(f"  CONTROL {rid:<18} ordinary end_turn: phase={cs.phase.name} "
              f"(combat.py:681-685 covers this path for both relics)")
    print("  So the divergence needs one of the two UNCHECKED windows: the "
          "extra-turn path (combat.py:648-652) or turn-1 construction "
          "(combat.py:208-209).")
    from sts2_rl.monsters.base import Monster
    import sts2_rl.monsters as _M
    import inspect as _i
    hps = sorted(
        (getattr(o, "max_hp"), n) for n, o in vars(_M).items()
        if _i.isclass(o) and issubclass(o, Monster) and o is not Monster
        and isinstance(getattr(o, "max_hp", None), int)
    )
    print(f"  lowest ported enemy max HP: {hps[:3]} -> turn-1 window needs an "
          f"enemy already below the tick, so the extra-turn window is the "
          f"reachable one.")
    print(f"  _check_win call sites: "
          f"{subprocess.run(['git', 'grep', '-c', '_check_win()', '--', 'sts2_rl/relics'], capture_output=True, text=True, cwd=_REPO).stdout.count(chr(10))} "
          f"relic files call it")


# ── b09-molten ────────────────────────────────────────────────────────────
def probe_molten() -> None:
    """Molten Egg: three separate checks.

    (1) `CardCreationFlags.NoHookUpgrades` (MoltenEgg.cs:27) has ZERO
        producers in the game source, so the guard is dead code in C# itself.
    (2) EggRelicHelper.UpgradeValidCards (EggRelicHelper.cs:10-22) applies NO
        upgrade-LEVEL check, so C# upgrades an already-upgraded Attack on the
        reward/merchant paths; the sim's EggRelic._applies applies
        ONLY_UNUPGRADED to all three paths. Dormant iff no ported card can be
        upgradable at level >= 1.
    (3) A deck-level TRANSFORM fires Hook.ModifyCardBeingAddedToDeck
        (CardCmd.cs:429); RunState.transform_card fires no deck-add hook, so a
        transformed-in Attack arrives un-upgraded.
    """
    print("  (1) `Flags` is write-only through CardCreationOptions.WithFlags "
          "(Flags has a private setter, CardCreationOptions.cs:57, 212-214),\n"
          "      so every producer of a flag is a `WithFlags(...)` call. All "
          "29 of them in the game source:")
    out = subprocess.run(["grep", "-rho", r"WithFlags(CardCreationFlags[^;]*)",
                          "src/"],
                         capture_output=True, text=True, cwd=_GAME).stdout
    tally: dict[str, int] = {}
    for line in out.splitlines():
        tally[line.strip()] = tally.get(line.strip(), 0) + 1
    for expr, n in sorted(tally.items(), key=lambda kv: -kv[1]):
        print(f"      {n:>2}x {expr}")
    for flag in ("NoHookUpgrades", "NoUpgrades", "NoModifications"):
        producers = sum(n for e, n in tally.items() if flag in e)
        readers = subprocess.run(
            ["grep", "-rn", f"HasFlag(CardCreationFlags.{flag})", "src/"],
            capture_output=True, text=True, cwd=_GAME,
        ).stdout.strip().splitlines()
        print(f"      {flag:<16} producers={producers}  readers={len(readers)}")
    print("      -> NoHookUpgrades is read by the three egg relics and SET BY "
          "NOBODY: MoltenEgg.cs:27-30 is dead code in the shipping game.")

    from sts2_rl.cards.base import _CARD_CLASSES
    multi = sorted(cid for cid, c in _CARD_CLASSES.items()
                   if c.max_upgrade_level > 1)
    print(f"\n  (2) ported cards with max_upgrade_level > 1: "
          f"{len(multi)} {multi}")
    print("      -> a level-1 card is never IsUpgradable, so both sides skip "
          "it and ONLY_UNUPGRADED is unobservable on the reward path.")

    from sts2_rl.cards import CardType, make_card
    from sts2_rl.run import RunState
    run = RunState(rng=random.Random(0))
    run.add_relic("molten_egg")
    added = run.add_card(make_card("bash"))
    print(f"\n  (3) add_card(bash): upgrade_level={added.upgrade_level} "
          f"(egg fires via modify_card_being_added_to_deck)")
    run2 = RunState(rng=random.Random(0))
    run2.add_relic("molten_egg")
    victim = run2.deck[0]
    into = run2.transform_card(victim, into=make_card("bash"))
    print(f"      transform_card(-> bash): upgrade_level="
          f"{into.upgrade_level} card_type={into.card_type.name}  "
          f"(C#: CardCmd.cs:429 runs the hook, so +1)")


# ── b09-maw-bank ──────────────────────────────────────────────────────────
def probe_maw_bank() -> None:
    """Maw Bank's 12 gold per room and its one-shot disable.

    MawBank.cs:43-50 guards on `RunState.BaseRoom == room` -- the base of the
    room STACK, i.e. once per map point rather than once per nested room. The
    sim dispatches after_room_entered exactly once per enter_point
    (run.py:976-983), so the guard is structurally satisfied.
    """
    from sts2_rl.rooms import RoomType
    from sts2_rl.run import RunState
    from sts2_rl.shop import MerchantEntry

    run = RunState(rng=random.Random(0))
    run.add_relic("maw_bank")
    relic = run.relics[-1]
    for i in range(3):
        for r in list(run.relics):
            r.after_room_entered(run, None, RoomType.MONSTER)
        print(f"  room {i + 1}: gold={run.gold} is_used_up={relic.is_used_up}")
    entry = MerchantEntry(run)
    for r in list(run.relics):
        r.after_item_purchased(run, entry, 0)
    print(f"  after a 0-gold purchase: has_item_been_bought="
          f"{relic.has_item_been_bought} (C#: unchanged, goldSpent <= 0)")
    for r in list(run.relics):
        r.after_item_purchased(run, entry, 100)
    print(f"  after a 100-gold purchase: has_item_been_bought="
          f"{relic.has_item_been_bought} is_used_up={relic.is_used_up}")
    for r in list(run.relics):
        r.after_room_entered(run, None, RoomType.MONSTER)
    print(f"  room 4 (post-purchase): gold={run.gold} (must not grow)")
    print(f"  after_room_entered dispatch sites in the sim: "
          + subprocess.run(["git", "grep", "-c", "after_room_entered(self, point, room_type)",
                            "--", "sts2_rl/run.py"],
                           capture_output=True, text=True, cwd=_REPO).stdout.strip())


# ── b09-simple ────────────────────────────────────────────────────────────
def probe_simple() -> None:
    """The confirmations: mango, meat_cleaver, miniature_tent,
    miniature_cannon, mercury_hourglass, lost_coffer."""
    import random as _r

    from sts2_rl import CombatState
    from sts2_rl.cards import make_card
    from sts2_rl.relics import make_relic
    from sts2_rl.run import RunState

    # mango: GainMaxHp(14) raises the cap AND heals 14 (CreatureCmd.GainMaxHp).
    run = RunState(rng=_r.Random(0))
    run.hp = 50
    base_max = run.max_hp
    run.add_relic("mango")
    print(f"  mango:            max_hp {base_max} -> {run.max_hp}, "
          f"hp 50 -> {run.hp}")
    run.relics[-1].undo_after_obtained(run)
    print(f"                    after undo_after_obtained: max_hp="
          f"{run.max_hp} hp={run.hp}")

    # meat_cleaver: the COOK option is appended only with >= 2 removable cards.
    run = RunState(rng=_r.Random(0))
    run.add_relic("meat_cleaver")
    opts = [o.key for o in run.rest_site_options()]
    print(f"  meat_cleaver:     rest-site options={opts}")
    run2 = RunState(rng=_r.Random(0))
    run2.add_relic("meat_cleaver")
    run2.deck = [c for c in run2.deck[:1]]
    opts2 = [o.key for o in run2.rest_site_options()]
    print(f"                    with 1 deck card: {opts2}  "
          f"(C# ADDS a disabled CookRestSiteOption instead of omitting it)")
    run3 = RunState(rng=_r.Random(0))
    run3.add_relic("meat_cleaver")
    cook = [o for o in run3.rest_site_options() if o.key == "COOK"][0]
    n_before, max_before = len(run3.deck), run3.max_hp
    cook.on_select(run3)
    print(f"                    COOK: deck {n_before} -> {len(run3.deck)}, "
          f"max_hp {max_before} -> {run3.max_hp}  (C#: -2 cards, +9 max HP)")

    # miniature_tent
    run = RunState(rng=_r.Random(0))
    print(f"  miniature_tent:   disable_remaining (no relic)="
          f"{run.should_disable_remaining_rest_site_options()}")
    run.add_relic("miniature_tent")
    print(f"                    with the relic="
          f"{run.should_disable_remaining_rest_site_options()}  (C#: False)")

    # miniature_cannon: only powered attacks, only upgraded, only the owner's.
    print("  miniature_cannon: every modify_damage_additive dispatch site is "
          "inside an is_powered_attack() guard --")
    out = subprocess.run(
        ["git", "grep", "-n", "hooks.modify_damage_additive", "--", "sts2_rl"],
        capture_output=True, text=True, cwd=_REPO).stdout.strip()
    print("    " + out.replace("\n", "\n    "))
    cs = CombatState(rng=_r.Random(0), relics=[make_relic("miniature_cannon")])
    enemy = cs.enemies[0]
    enemy.hp = enemy.max_hp = 300
    from sts2_rl.cmds import DamageCmd
    from sts2_rl.valueprops import DamageProps
    plain, up = make_card("strike"), make_card("strike")
    up.upgrade()
    for label, card, props, dealer in (
        ("un-upgraded card", plain, DamageProps.CARD, cs.player),
        ("upgraded card", up, DamageProps.CARD, cs.player),
        ("upgraded, unpowered", up, DamageProps.NON_CARD_UNPOWERED, cs.player),
        ("upgraded, dealer=None", up, DamageProps.CARD, None),
        ("no card", None, DamageProps.CARD, cs.player),
    ):
        lost = DamageCmd.deal(cs.hooks, enemy, 10, dealer=dealer, card=card,
                              props=props)
        print(f"                    {label:<22} 10 -> {lost}")
    print("                    C# 'dealer=None' row: MiniatureCannon.cs:31 is "
          "`dealer != Owner && cardSource.Owner != Owner`, an AND, so a "
          "player-owned card with a null dealer STILL gets +3.")

    # mercury_hourglass: 3 damage at every turn start including turn 1.
    cs = CombatState(rng=_r.Random(0),
                     relics=[make_relic("mercury_hourglass")])
    hps = [(e.max_hp, e.hp) for e in cs.enemies]
    print(f"  mercury_hourglass: turn 1 enemy (max,hp)={hps}")

    # The two-pass turn-START collapse: C# runs EVERY AfterPlayerTurnStart
    # listener (Hook.cs step 22) before ANY AfterSideTurnStart listener (step
    # 23); the sim has one on_player_turn_started pass in relic order.
    import re as _re
    from sts2_rl.relics import ALL_RELICS

    def _snake(cs_name: str) -> str:
        return _re.sub(r"(?<!^)(?=[A-Z])", "_", cs_name).lower()

    relics_dir = _GAME / "src/Core/Models/Relics"
    pass1, pass2 = [], []
    for f in sorted(relics_dir.glob("*.cs")):
        text = f.read_text(errors="ignore")
        rid = _snake(f.stem)
        if rid not in ALL_RELICS:
            continue
        sim_has = hasattr(ALL_RELICS[rid], "on_player_turn_started")
        if _re.search(r"override[^\n]*Task AfterPlayerTurnStart\b", text):
            pass1.append((rid, sim_has))
        if _re.search(r"override[^\n]*AfterSideTurnStart\b", text):
            pass2.append((rid, sim_has))
    p1 = [r for r, h in pass1 if h]
    p2 = [r for r, h in pass2 if h]
    print(f"  turn-start passes: PORTED relics on C# AfterPlayerTurnStart "
          f"(step 22) that implement the sim's on_player_turn_started: "
          f"{len(p1)} {sorted(p1)}")
    print(f"                     PORTED relics on C# AfterSideTurnStart "
          f"(step 23) that implement the SAME sim method: {len(p2)} "
          f"{sorted(p2)}")
    print("                     Both sets share one flat pass in relic order "
          "(hooks.py:285-295), so a step-22 relic can run AFTER a step-23 "
          "relic.\n"
          "                     Same mechanism as audit/records/seam/turn_structure "
          "step 23 / guard G12 (LIVE on the turn-END side, Orichalcum x Cloak "
          "Clasp).")
    # LIVE demonstration of the turn-START half: GamblingChip is step 22
    # (GamblingChip.cs:16) and BoneTea is step 23 (BoneTea.cs), so C# ALWAYS
    # mulligans before Bone Tea upgrades the hand.
    for order in (["gambling_chip", "bone_tea"], ["bone_tea", "gambling_chip"]):
        cs = CombatState(
            rng=_r.Random(1), relics=[make_relic(r) for r in order],
            card_selector=lambda purpose, cands, n: list(cands),
        )
        levels = sorted(c.upgrade_level for c in cs.player.hand)
        tea = [r for r in cs.hooks._listeners
               if getattr(r, "id", None) == "bone_tea"][0]
        print(f"  turn-start LIVE  relic order={order}:\n"
              f"                     post-mulligan hand upgrade levels="
              f"{levels}  bone_tea charges left={tea.combats_left}")
    print("                     C# order is fixed (step 22 then step 23), so "
          "the post-mulligan hand is ALWAYS the upgraded one.")

    # lost_coffer: 3 options, 1 kept, plus a potion.
    run = RunState(rng=_r.Random(4))
    n_before = len(run.deck)
    pot_before = len(run.held_potions)
    run.add_relic("lost_coffer")
    print(f"  lost_coffer:      deck {n_before} -> {len(run.deck)}, "
          f"potions {pot_before} -> {len(run.held_potions)}  "
          f"(C#: a SKIPPABLE 3-card choice + a potion)")


PROBES = {
    "b09-pool": probe_pool,
    "b09-isallowed": probe_isallowed,
    "b09-fysh": probe_fysh,
    "b09-meal-ticket": probe_meal_ticket,
    "b09-membership": probe_membership,
    "b09-meat-bone": probe_meat_bone,
    "b09-wisp-replay": probe_wisp_replay,
    "b09-struggles": probe_struggles,
    "b09-molten": probe_molten,
    "b09-maw-bank": probe_maw_bank,
    "b09-simple": probe_simple,
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
