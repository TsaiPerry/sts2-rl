"""Reproducible execution probes for relic content audit batch 14.

Batch 14's units: runic_pyramid, sai, sand_castle, screaming_flagon,
scroll_boxes, sea_glass, seal_of_gold, self_forming_clay, sere_talon, shovel,
shuriken, signet_ring, silken_tress, silver_crucible, sling_of_courage.

Own module per the batch-14 concurrency contract (`tools/audit/relic_probes.py`
is read-only to this batch); the shared module is still the reference for
`turn-order` and the pool-wide sweeps and is re-used, not re-implemented.

  py tools/audit/relic_probes_b14.py                  # every probe
  py tools/audit/relic_probes_b14.py sand-castle      # one probe

Probes:
  pool             obtainability of batch 14's 15 relics (binding rule 6)
  sand-castle      the missing `.Take(6)` -- the sim upgrades the whole deck
  clay-carry       self_forming_clay's _pending_block crosses combats
  clay-slot        where the deferred Block lands in the turn
  seal-gold        gold gained IN combat is invisible to Seal of Gold
  card-reward-flag silver_crucible / silken_tress drop the IsCardReward gate
  crucible-life    the 3-charge / chestless-treasure lifecycle
  scroll-boxes     the bundle pool is FilterForCombat, not GetUnlockedCards
  scroll-neow      CanGenerateBundles executed for the Ironclad pool
  sere-talon       the Niche stream is never consumed
  shovel           the IsAllowed floor gate and the empty-bag DIG option
  shuriken         the counter reset slot and its combat-boundary safety
  sai-seal-slot    AfterSideTurnStart vs the sim's single post-draw pass
  flagon           the empty-hand AoE and its turn-end pass
  sling            the Elite gate and the AfterRoomEntered -> combat-start move
  signet-ring      999 gold through the modify_gold_gained chain
  sea-glass        the stub grants nothing and burns no Rewards draws
  pyramid          should_flush_hand and the seam's G4 witness
"""
from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

BATCH14 = [
    "runic_pyramid", "sai", "sand_castle", "screaming_flagon", "scroll_boxes",
    "sea_glass", "seal_of_gold", "self_forming_clay", "sere_talon", "shovel",
    "shuriken", "signet_ring", "silken_tress", "silver_crucible",
    "sling_of_courage",
]


# ── pool ──────────────────────────────────────────────────────────────────
def probe_pool() -> None:
    """Where each batch-14 relic can come from (binding rule 6)."""
    import subprocess

    from sts2_rl.relic_pools import IRONCLAD_RELIC_POOL, SHARED_RELIC_POOL
    from sts2_rl.relics import ALL_RELICS

    bag = {rid.removeprefix("RELIC.").lower(): rarity
           for rid, rarity in list(SHARED_RELIC_POOL) + list(IRONCLAD_RELIC_POOL)}
    for rid in BATCH14:
        assert rid in ALL_RELICS, rid
        where = []
        if rid in bag:
            where.append(f"grab bag ({bag[rid]})")
        out = subprocess.run(
            ["git", "grep", "-l", "-e", f'"{rid}"', "--",
             "sts2_rl/events", "sts2_rl/rewards.py", "sts2_rl/shop.py"],
            cwd=_REPO, capture_output=True, text=True).stdout.split()
        where += [Path(p).name for p in out]
        print(f"  {rid:<18} {', '.join(where) or 'NO PORTED SOURCE'}")


# ── sand-castle ───────────────────────────────────────────────────────────
def probe_sand_castle() -> None:
    """sand_castle G1: SandCastle.cs:24-25 takes only CardsVar(6) cards.

    `PileType.Deck.GetPile(Owner).Cards.Where(IsUpgradable).ToList()
    .StableShuffle(Rng.Niche).Take(DynamicVars.Cards.IntValue)` -- six
    upgrades, chosen off the Niche stream. relics/sand_castle.py:15-18 loops
    the whole deck with no Take and no stream, so every upgradable card is
    upgraded and the Niche position never moves.

    The sibling relics/fragrant_mushroom.py:31-36 does it correctly
    (stable_shuffle over run.rng_set.niche, then [:count]), so the capability
    exists -- PROMPT.md bug class 12's "check whether a sibling already does
    the thing".
    """
    from sts2_rl.rng import RunRngSet
    from sts2_rl.run import RunState

    run = RunState(rng=random.Random(0), string_seed="B14PROBE")
    upgradable = [c for c in run.deck if c.is_upgradable]
    print(f"  starting deck: {len(run.deck)} cards, "
          f"{len(upgradable)} upgradable")
    run.add_relic("sand_castle")
    lvls = sorted({(c.id, c.upgrade_level) for c in run.deck})
    n_up = sum(1 for c in run.deck if c.upgrade_level > 0)
    print(f"  after add_relic('sand_castle'): {n_up} cards upgraded "
          f"(C# upgrades exactly 6)")
    print(f"  deck (id, upgrade_level): {lvls}")

    print("\n  -- the Niche stream is not consumed (CardsVar(6) + "
          "StableShuffle(Rng.Niche))")
    run2 = RunState(rng=random.Random(0), string_seed="B14PROBE")
    run2.rng_set = RunRngSet("B14PROBE")
    before = run2.rng_set.niche.counter
    run2.add_relic("sand_castle")
    after = run2.rng_set.niche.counter
    n_up2 = sum(1 for c in run2.deck if c.upgrade_level > 0)
    print(f"     rng_set present: niche counter {before} -> {after} "
          f"(C#: 1 StableShuffle == len-1 draws); upgraded={n_up2}")

    print("\n  -- the sibling that gets it right, for contrast")
    run3 = RunState(rng=random.Random(0), string_seed="B14PROBE")
    run3.rng_set = RunRngSet("B14PROBE")
    b = run3.rng_set.niche.counter
    run3.add_relic("fragrant_mushroom")
    print(f"     fragrant_mushroom (CardsVar(2)): niche {b} -> "
          f"{run3.rng_set.niche.counter}, upgraded="
          f"{sum(1 for c in run3.deck if c.upgrade_level > 0)}")


# ── clay-carry ────────────────────────────────────────────────────────────
def probe_clay_carry() -> None:
    """self_forming_clay G1: `_pending_block` outlives the combat.

    C# has no relic-side counter at all: SelfFormingClay.cs:25-31 applies a
    SelfFormingClayPower to the owner, and SelfFormingClayPower.cs:19-25 pays
    it out at AfterBlockCleared and removes itself. A power dies with the
    combat, so nothing can cross the boundary. The sim replaces the power with
    a field on the relic instance (self_forming_clay.py:27), and relic
    instances live on RunState.relics, so unspent Block carries into the next
    fight.

    sweep-reset files this relic in the "RESET AT TURN START, BEFORE ANY
    READER (genuinely safe)" bucket. It is NOT safe: the reset at
    self_forming_clay.py:46 happens AFTER the payout on line 43, so it is a
    consume-then-clear, not a clear-then-read.
    """
    from sts2_rl import CombatState
    from sts2_rl.cmds import DamageCmd
    from sts2_rl.relics import make_relic
    from sts2_rl.valueprops import DamageProps

    clay = make_relic("self_forming_clay")
    cs1 = CombatState(rng=random.Random(0), relics=[clay],
                      max_hp=80, current_hp=80)
    DamageCmd.deal(cs1.hooks, cs1.player, 5, dealer=cs1.enemy,
                   props=DamageProps.MONSTER_MOVE)
    print(f"  combat 1: player took 5 unblocked -> _pending_block="
          f"{clay._pending_block}, block={cs1.player.block}")
    print("  combat 1 ENDS before the player's next turn start "
          "(the killing blow / a won fight)")

    cs2 = CombatState(rng=random.Random(1), relics=[clay],
                      max_hp=80, current_hp=80)
    print(f"  combat 2 turn 1 (carried instance): block={cs2.player.block} "
          f"_pending_block={clay._pending_block}   <-- C# gives 0 block")
    fresh = make_relic("self_forming_clay")
    cs3 = CombatState(rng=random.Random(1), relics=[fresh],
                      max_hp=80, current_hp=80)
    print(f"  combat 2 turn 1 (fresh instance):   block={cs3.player.block} "
          f"_pending_block={fresh._pending_block}   <-- the correct answer")

    print("\n  -- the sweep's own bucket claim, tested: is the reset before "
          "the reader?")
    import inspect
    src = inspect.getsource(type(fresh).on_player_turn_started)
    print("     " + "\n     ".join(src.strip().splitlines()))

    print("\n  -- REACHABILITY with ported content only: Hemokinesis "
          "(cards/hemokinesis.py:37, CARD_HP_LOSS through DamageCmd) as the "
          "killing blow, so no player turn follows the HP loss")
    from sts2_rl.cards import make_card
    clay3 = make_relic("self_forming_clay")
    cs_a = CombatState(rng=random.Random(0), relics=[clay3],
                       starting_deck=[make_card("hemokinesis")],
                       max_hp=80, current_hp=80)
    for e in cs_a.enemies:
        e.hp = 10
    cs_a.player.hand.clear()
    cs_a.player.hand.append(make_card("hemokinesis"))
    cs_a.player.hand[-1].combat = cs_a
    cs_a.play_card(0, 0)
    print(f"     combat 1: enemies={[e.hp for e in cs_a.enemies]} "
          f"is_over={cs_a.is_over} player hp={cs_a.player.hp} "
          f"_pending_block={clay3._pending_block}")
    cs_b = CombatState(rng=random.Random(1), relics=[clay3],
                       max_hp=80, current_hp=78)
    print(f"     combat 2 turn 1: block={cs_b.player.block}   "
          f"<-- C# gives 0 (the SelfFormingClayPower died with combat 1)")

    print("\n  -- the C# guard is result.UnblockedDamage > 0; the sim passes "
          "hp_lost (cmds.py:122)")
    clay2 = make_relic("self_forming_clay")
    cs = CombatState(rng=random.Random(0), relics=[clay2])
    cs.player.block = 10
    DamageCmd.deal(cs.hooks, cs.player, 5, dealer=cs.enemy,
                   props=DamageProps.MONSTER_MOVE)
    print(f"     fully blocked 5 into 10 block -> _pending_block="
          f"{clay2._pending_block} (C#: 0, UnblockedDamage == 0)")
    DamageCmd.deal(cs.hooks, cs.player, 12, dealer=cs.enemy,
                   props=DamageProps.MONSTER_MOVE)
    print(f"     then 12 into 5 remaining block -> _pending_block="
          f"{clay2._pending_block} (C#: 3, one application of 3)")


def probe_clay_slot() -> None:
    """self_forming_clay N: the Block lands at on_player_turn_started (post-
    draw) where C#'s SelfFormingClayPower pays out at AfterBlockCleared."""
    from sts2_rl import CombatState
    from sts2_rl.cmds import DamageCmd
    from sts2_rl.relics import make_relic
    from sts2_rl.valueprops import DamageProps

    order: list[str] = []

    class Sentinel:
        """A listener recording the player's Block at each turn-start slot."""

        def on_block_cleared(self, creature) -> None:
            order.append(f"on_block_cleared block={creature.block}")

        def on_energy_reset(self, player) -> None:
            order.append(f"on_energy_reset block={player.block}")

        def on_player_turn_start(self, player) -> None:
            order.append(f"on_player_turn_start block={player.block}")

        def modify_hand_draw(self, player, amount):
            order.append(f"modify_hand_draw block={player.block}")
            return amount

        def on_player_turn_started(self, player) -> None:
            order.append(f"on_player_turn_started block={player.block}")

    clay = make_relic("self_forming_clay")
    cs = CombatState(rng=random.Random(0), relics=[clay],
                     max_hp=80, current_hp=80)
    cs.hooks.register(Sentinel())
    DamageCmd.deal(cs.hooks, cs.player, 5, dealer=cs.enemy,
                   props=DamageProps.MONSTER_MOVE)
    order.clear()
    cs.end_turn()
    print("  turn-2 start, with 3 Block pending:")
    for line in order:
        print(f"     {line}")
    print("  C# pays out inside AfterBlockCleared -- i.e. at "
          "`on_block_cleared`, two slots earlier than the sim's payout.")

    print("\n  -- the slot move is OBSERVABLE with ported content: Royal "
          "Poison damages the player from AfterPlayerTurnStart "
          "(RoyalPoison.cs:18, turn_structure step 22), which is AFTER the "
          "block clear. C# therefore banks the Clay power on turn 1 and pays "
          "it at turn 2's AfterBlockCleared; the sim can pay it on turn 1.")
    for order in (["royal_poison", "self_forming_clay"],
                  ["self_forming_clay", "royal_poison"]):
        relics = [make_relic(r) for r in order]
        cs = CombatState(rng=random.Random(0), relics=relics,
                         max_hp=80, current_hp=80)
        clay_i = next(r for r in relics if r.id == "self_forming_clay")
        print(f"     {order}: turn-1 block={cs.player.block} "
              f"hp={cs.player.hp} _pending_block={clay_i._pending_block}"
              f"   <-- C# always gives turn-1 block 0")


# ── seal-gold ─────────────────────────────────────────────────────────────
def probe_seal_gold() -> None:
    """seal_of_gold G1: in-combat gold GAINS are invisible to the relic.

    SealOfGold.cs:27 reads `base.Owner.Gold`, which PlayerCmd.GainGold updates
    live, so gold won during the fight is immediately spendable. The sim's
    balance is `combat.player_gold - combat.gold_stolen - combat.gold_spent`
    (seal_of_gold.py:25) and omits `combat.gold_gained`. The Thievery power at
    powers.py:1660 computes the same balance and DOES include gold_gained, so
    the sim already has the correct expression at another site.
    """
    from sts2_rl import CombatState
    from sts2_rl.relics import make_relic

    print("  -- baseline: 5 gold at entry is spent every turn")
    seal = make_relic("seal_of_gold")
    cs = CombatState(rng=random.Random(0), relics=[seal], player_gold=12)
    print(f"     turn 1: energy={cs.player.energy} "
          f"gold_spent={cs.gold_spent}")
    cs.end_turn()
    print(f"     turn 2: energy={cs.player.energy} "
          f"gold_spent={cs.gold_spent}")
    cs.end_turn()
    print(f"     turn 3: energy={cs.player.energy} "
          f"gold_spent={cs.gold_spent} (12 gold -> 2 charges)")

    print("\n  -- the gap: Hand of Greed banks 20 gold mid-combat")
    seal2 = make_relic("seal_of_gold")
    cs2 = CombatState(rng=random.Random(0), relics=[seal2], player_gold=4)
    print(f"     entry gold=4 -> turn 1 energy={cs2.player.energy} "
          f"(correct on both sides: nothing to spend)")
    cs2.gold_gained += 20          # cards/colorless_attacks.py:208
    cs2.end_turn()
    print(f"     after +20 gold_gained: turn 2 energy={cs2.player.energy} "
          f"gold_spent={cs2.gold_spent}   <-- C# gives 4 energy, 5 gold spent")
    print(f"     the sim's balance expression = "
          f"{cs2.player_gold} - {cs2.gold_stolen} - {cs2.gold_spent} = "
          f"{cs2.player_gold - cs2.gold_stolen - cs2.gold_spent} "
          f"(live balance is 24)")

    print("\n  -- the same expression at the OTHER site includes gold_gained")
    import inspect

    from sts2_rl.powers import ThieveryPower
    src = inspect.getsource(ThieveryPower.steal) if hasattr(
        ThieveryPower, "steal") else ""
    for line in src.splitlines():
        if "gold_gained" in line:
            print(f"     powers.py: {line.strip()}")


# ── card-reward-flag ──────────────────────────────────────────────────────
def probe_card_reward_flag() -> None:
    """silver_crucible / silken_tress: the IsCardReward gate is dropped.

    Both C# relics refuse unless
    `options.Flags.HasFlag(CardCreationFlags.IsCardReward)`
    (SilverCrucible.cs:104-107, SilkenTress.cs:53-56), and that flag is set by
    exactly two places in the game: `CardReward`'s two constructors
    (CardReward.cs:113-115, :134) and the SealedDeck modifier. Every other
    `CardFactory.CreateForReward` caller leaves it clear.

    The sim has no flag: rewards.py:299-301 dispatches
    modify_card_reward_options for every create_reward_cards call whose
    `modify_hooks` is True (that parameter is CardCreationFlags.NoModifyHooks,
    a DIFFERENT flag). Two ported callers are therefore wrong in one direction
    and one in the other.
    """
    from sts2_rl.cards.pool import COLORLESS_POOL
    from sts2_rl.rewards import RarityOddsType, create_reward_cards
    from sts2_rl.run import RunState

    def deck_state(cards):
        return [(c.id, c.upgrade_level,
                 None if c.enchantment is None else c.enchantment.id)
                for c in cards]

    print("  (a) lead_paperweight.after_obtained -- LeadPaperweight.cs:21-22 "
          "builds a bare CardCreationOptions and calls CreateForReward, so "
          "IsCardReward is CLEAR and C# skips both relics.")
    run = RunState(rng=random.Random(0), string_seed="B14PROBE")
    run.add_relic("silver_crucible")
    run.add_relic("silken_tress")
    sc = next(r for r in run.relics if r.id == "silver_crucible")
    st = next(r for r in run.relics if r.id == "silken_tress")
    print(f"      before: times_used={sc.times_used} is_used={st.is_used}")
    cards = create_reward_cards(
        run, RarityOddsType.REGULAR, count=2, mutate_pity=False,
        modify_hooks=True, pool=list(COLORLESS_POOL))
    print(f"      offered: {deck_state(cards)}")
    print(f"      after:  times_used={sc.times_used} is_used={st.is_used}   "
          f"<-- C#: 0 and False, and the cards unmodified")

    print("\n  (b) brain_leech SHARE_KNOWLEDGE -- BrainLeech.cs:66 is also a "
          "bare CreateForReward (ForNonCombatWithDefaultOdds), IsCardReward "
          "CLEAR; the sim's events/brain_leech.py:44 leaves modify_hooks at "
          "its True default.")
    run2 = RunState(rng=random.Random(0), string_seed="B14PROBE")
    run2.add_relic("silver_crucible")
    sc2 = next(r for r in run2.relics if r.id == "silver_crucible")
    cards2 = create_reward_cards(run2, RarityOddsType.REGULAR, count=6,
                                 mutate_pity=False)
    print(f"      offered: {deck_state(cards2)}")
    print(f"      times_used={sc2.times_used}   <-- C#: 0")

    print("\n  (c) the OTHER direction -- brain_leech RIP builds a real "
          "`new CardReward(options, 3, Owner)` (BrainLeech.cs:57), so "
          "IsCardReward IS set and C# upgrades the options; the sim passes "
          "modify_hooks=False (events/brain_leech.py:60), so nothing fires.")
    run3 = RunState(rng=random.Random(0), string_seed="B14PROBE")
    run3.add_relic("silver_crucible")
    sc3 = next(r for r in run3.relics if r.id == "silver_crucible")
    cards3 = create_reward_cards(run3, RarityOddsType.REGULAR, count=3,
                                 mutate_pity=False, modify_hooks=False,
                                 pool=list(COLORLESS_POOL))
    print(f"      offered: {deck_state(cards3)}")
    print(f"      times_used={sc3.times_used}   <-- C#: 1, and the three "
          f"options upgraded")

    print("\n  (d) the reference case -- a real combat card reward: both "
          "sides fire.")
    run4 = RunState(rng=random.Random(0), string_seed="B14PROBE")
    run4.add_relic("silver_crucible")
    sc4 = next(r for r in run4.relics if r.id == "silver_crucible")
    cards4 = create_reward_cards(run4, RarityOddsType.REGULAR)
    print(f"      offered: {deck_state(cards4)}  times_used={sc4.times_used}")

    print("\n  (e) which sim relics share the single collapsed pass")
    import subprocess
    out = subprocess.run(
        ["git", "grep", "-n", "def modify_card_reward_options", "--",
         "sts2_rl"], cwd=_REPO, capture_output=True, text=True).stdout
    print("     " + "\n     ".join(out.strip().splitlines()))
    print("     C# runs TryModifyCardRewardOptions and "
          "TryModifyCardRewardOptionsLate as TWO complete passes "
          "(Hook.cs:1445-1467). All four sim implementers are Late in C#; "
          "LastingCandy is the only non-Late implementer in the game and its "
          "port is a stub, so the collapse is dormant TODAY.")


def probe_crucible_life() -> None:
    """silver_crucible: the 3-charge / chestless-treasure lifecycle."""
    from sts2_rl.rewards import RarityOddsType, create_reward_cards
    from sts2_rl.rooms import RoomType
    from sts2_rl.run import RunState

    run = RunState(rng=random.Random(0), string_seed="B14PROBE")
    run.add_relic("silver_crucible")
    sc = next(r for r in run.relics if r.id == "silver_crucible")
    for n in range(1, 5):
        cards = create_reward_cards(run, RarityOddsType.REGULAR)
        print(f"  reward {n}: upgraded="
              f"{[c.upgrade_level for c in cards]} times_used={sc.times_used} "
              f"is_used_up={sc.is_used_up}")
    print(f"  treasure gate: should_generate_treasure="
          f"{sc.should_generate_treasure(run)} "
          f"(rooms entered={sc.treasure_rooms_entered})")
    sc.after_room_entered(run, None, RoomType.TREASURE)
    print(f"  after 1st treasure room: entered={sc.treasure_rooms_entered} "
          f"should_generate={sc.should_generate_treasure(run)} "
          f"is_used_up={sc.is_used_up}")
    sc.after_room_entered(run, None, RoomType.TREASURE)
    print(f"  after 2nd treasure room: entered={sc.treasure_rooms_entered} "
          f"should_generate={sc.should_generate_treasure(run)}")
    print("  C# IsAllowed(runState) is `Players.Count == 1` "
          "(SilverCrucible.cs:81-84) -- always true single-player "
          "(sweep B bucket (b)).")

    print("\n  -- the Spoils Map leak: C# reaches TryHandleSpoilsMap only "
          "INSIDE DoTreasureRoomRewards, i.e. after ShouldGenerateTreasure "
          "returns true (OneOffSynchronizer.cs:128-146). The sim runs "
          "_complete_map_point_quests OUTSIDE the gate (run.py:1019-1020).")
    from sts2_rl.actmap import MapPointType
    run2 = RunState(rng=random.Random(0), string_seed="B14PROBE")
    act_map = run2.start_run()
    rows: dict[int, list[str]] = {}
    for p in act_map.all_points():
        rows.setdefault(p.coord[1], []).append(p.point_type.name)
    treasure_rows = {r: v for r, v in rows.items()
                     if MapPointType.TREASURE.name in v}
    print(f"     act-1 treasure rows: {treasure_rows}")
    print(f"     every column on that row is TREASURE: "
          f"{all(set(v) == {MapPointType.TREASURE.name} for v in treasure_rows.values())}"
          f"  -> the act-1 treasure node is UNAVOIDABLE, so it always eats "
          f"the suppression and Spoils Map's act-2 node (SpoilsActIndex 1, "
          f"cards/spoils_map.py:36) is always the SECOND treasure room. "
          f"DORMANT.")


# ── scroll-boxes ──────────────────────────────────────────────────────────
def probe_scroll_boxes() -> None:
    """scroll_boxes G1: the bundle pool is the combat-filtered pool.

    ScrollBoxes.cs:76-77 draws from `options.GetPossibleCards(player)`, which
    is `CardPool.GetUnlockedCards(...)` with only the rarity filter applied
    (CardCreationOptions.cs:168-177) -- no FilterForCombat. scroll_boxes.py
    builds its candidate lists from `pool_card_ids()`, which drops every card
    with `can_be_generated_in_combat = False`.
    """
    from sts2_rl.cards import CardRarity
    from sts2_rl.cards.base import _CARD_CLASSES
    from sts2_rl.cards.pool import pool_card_ids, reward_pool_card_ids

    for rar in (CardRarity.COMMON, CardRarity.UNCOMMON):
        combat = {c for c in pool_card_ids()
                  if _CARD_CLASSES[c].rarity == rar}
        reward = {c for c in reward_pool_card_ids()
                  if _CARD_CLASSES[c].rarity == rar}
        print(f"  {rar.name:<9} FilterForCombat={len(combat):<3} "
              f"GetUnlockedCards={len(reward):<3} "
              f"missing from the sim's bundle pool: "
              f"{sorted(reward - combat)}")
    print("  ScrollBoxes has no NoCardPoolModifications flag either, so C# "
          "also runs Hook.ModifyCardRewardCreationOptions twice "
          "(ScrollBoxes.cs:73, :75); the sim has no such hook.")

    print("\n  -- the bundles the sim actually produces")
    from sts2_rl.run import RunState
    run = RunState(rng=random.Random(0), string_seed="B14PROBE")
    n_before = len(run.deck)
    run.add_relic("scroll_boxes")
    print(f"     deck {n_before} -> {len(run.deck)} "
          f"(added {[c.id for c in run.deck[n_before:]]})")


def probe_scroll_neow() -> None:
    """scroll_boxes IsAllowedAtNeow: CanGenerateBundles, executed.

    ScrollBoxes.cs:23-30 returns `CanGenerateBundles(player) &&
    base.IsAllowedAtNeow(player)`, and CanGenerateBundles (lines 50-60) needs
    >= 4 unlocked Commons AND >= 2 unlocked Uncommons in the CHARACTER's pool.
    `base.IsAllowedAtNeow` is `IsAllowed(runState)` (RelicModel.cs:443-446),
    which ScrollBoxes does not override, so it is the default `true`
    (RelicModel.cs:434-437). Sweep B flagged the sim's
    `is_allowed_at_neow = True` as a MISMATCH; this executes the predicate.
    """
    from sts2_rl.cards import CardRarity
    from sts2_rl.cards.base import _CARD_CLASSES
    from sts2_rl.cards.pool import IRONCLAD_POOL
    from sts2_rl.events.neow import POSITIVE_RELICS, neow_relic_pool
    from sts2_rl.run import RunState

    commons = [c for c in IRONCLAD_POOL
               if _CARD_CLASSES[c].rarity == CardRarity.COMMON]
    uncommons = [c for c in IRONCLAD_POOL
                 if _CARD_CLASSES[c].rarity == CardRarity.UNCOMMON]
    print(f"  Ironclad pool: {len(commons)} Common (need >= 4), "
          f"{len(uncommons)} Uncommon (need >= 2) -> "
          f"CanGenerateBundles = {len(commons) >= 4 and len(uncommons) >= 2}")
    print(f"  scroll_boxes in Neow's POSITIVE_RELICS: "
          f"{'scroll_boxes' in POSITIVE_RELICS}")
    run = RunState(rng=random.Random(0), string_seed="B14PROBE")
    pool = neow_relic_pool(run)
    print(f"  neow_relic_pool offers it: {'scroll_boxes' in pool}  "
          f"(both sides: yes)")
    print("  So the flag is CORRECT for the only character the sim has. "
          "The unlock half of the predicate is the waived part: "
          "`grep -rn UnlockState sts2_rl/` returns nothing.")
    import subprocess
    out = subprocess.run(["git", "grep", "-c", "UnlockState", "--", "sts2_rl"],
                         cwd=_REPO, capture_output=True, text=True).stdout
    print(f"     git grep -c UnlockState -- sts2_rl -> {out.strip() or '(no hits)'}")


# ── sere-talon ────────────────────────────────────────────────────────────
def probe_sere_talon() -> None:
    """sere_talon N1: `Rng.Niche` is named in C# and never consumed.

    SereTalon.cs:41 is `base.Owner.RunState.Rng.Niche.NextItem(availableCurses)`
    with `availableCurses.Remove(...)` after each pick (line 42).
    sere_talon.py:24 calls `random_curses(run.rng, 2, distinct=True)`, which is
    `rng.sample` on the legacy shared RNG (cards/pool.py:92-97) -- the stream
    argument is never even offered. The sibling relics/neows_bones.py:30-34
    does exactly the C# thing when `run.rng_set` is present.
    """
    from sts2_rl.rng import RunRngSet
    from sts2_rl.run import RunState

    for rid in ("sere_talon", "neows_bones"):
        run = RunState(rng=random.Random(0), string_seed="B14PROBE")
        run.rng_set = RunRngSet("B14PROBE")
        before = run.rng_set.niche.counter
        n_before = len(run.deck)
        run.add_relic(rid)
        print(f"  {rid:<13} niche counter {before} -> "
              f"{run.rng_set.niche.counter}   added="
              f"{[c.id for c in run.deck[n_before:]]}")
    print("  C# Sere Talon burns 2 Niche draws (one NextItem per curse); the "
          "3 Wishes are fixed and burn none.")

    print("\n  -- the draw PATTERN also differs on the legacy path: "
          "rng.sample(k=2) is not NextItem+Remove twice")
    from sts2_rl.cards.pool import curse_pool_ids
    opts = curse_pool_ids()
    print(f"     generatable curses ({len(opts)}), C# order is `orderby "
          f"c.Id`: {opts == sorted(opts)}")
    r1, r2 = random.Random(7), random.Random(7)
    print(f"     sample:        {r1.sample(opts, 2)}")
    seq, pool = [], list(opts)
    for _ in range(2):
        pick = pool[r2.randrange(len(pool))]
        seq.append(pick)
        pool.remove(pick)
    print(f"     NextItem+Remove: {seq}")


# ── shovel ────────────────────────────────────────────────────────────────
def probe_shovel() -> None:
    """shovel: the IsAllowed floor gate, and the empty-bag DIG option.

    Shovel.cs:13-16 is `IsBeforeAct3TreasureChest(runState)` == `TotalFloor <
    41` (RelicModel.cs:452-456). C# enforces it in the PULL path:
    RelicGrabBag.GetAvailableDeque calls RemoveDisallowedRelicsFromDeques
    (RelicGrabBag.cs:218-220) on every pull, so from floor 41 the relic is
    gone from the bag. The sim's `Relic` base declares no `is_allowed` member.
    Sweep B, cluster (a) -- 17 relics.

    Second, unrelated finding: Shovel.TryModifyRestSiteOptions adds
    DigRestSiteOption UNCONDITIONALLY and RestSiteOption.IsEnabled is not
    overridden (RestSiteOption.cs:37), while shovel.py:18-19 suppresses the
    option when the bag is empty.
    """
    from sts2_rl.relics.base import Relic
    from sts2_rl.run import RunState

    print(f"  Relic base has an is_allowed member: "
          f"{hasattr(Relic, 'is_allowed')}")
    run = RunState(rng=random.Random(0), string_seed="B14PROBE")
    run.total_floor = 60
    print(f"  total_floor={run.total_floor} (>= 41): shovel still in the grab "
          f"bag: {'shovel' in run.relic_grab_bag}")
    hits = 0
    for n in range(400):
        r = RunState(rng=random.Random(n), string_seed=f"B14SHOV{n:04d}")
        r.total_floor = 60
        pulled = r.pull_relic_from_front()
        if pulled is not None and pulled.id == "shovel":
            hits += 1
    print(f"  400 post-floor-41 pulls yielded shovel {hits} time(s) "
          f"(C#: 0 -- it is removed from the deque)")

    print("\n  -- the DIG option's availability gate")
    run2 = RunState(rng=random.Random(0), string_seed="B14PROBE")
    run2.add_relic("shovel")
    sh = next(r for r in run2.relics if r.id == "shovel")
    opts: list = []
    sh.modify_rest_site_options(run2, opts)
    print(f"  bag has {len(run2.relic_grab_bag)} relics -> options="
          f"{[o.key for o in opts]}")
    run2.relic_grab_bag.clear()
    opts2: list = []
    sh.modify_rest_site_options(run2, opts2)
    print(f"  bag EMPTY -> options={[o.key for o in opts2]}   "
          f"<-- C# still offers DIG and grants RelicFactory.FallbackRelic")

    print("\n  -- the DIG pull itself (PullNextRelicFromFront(player) -> "
          "RollRarity(player) -> PlayerRng.Rewards)")
    run3 = RunState(rng=random.Random(0), string_seed="B14PROBE")
    run3.add_relic("shovel")
    sh3 = next(r for r in run3.relics if r.id == "shovel")
    o: list = []
    sh3.modify_rest_site_options(run3, o)
    n_bag = len(run3.relic_grab_bag)
    o[0].on_select(run3)
    print(f"  DIG: bag {n_bag} -> {len(run3.relic_grab_bag)}, relics now "
          f"{[r.id for r in run3.relics]}")


# ── shuriken ──────────────────────────────────────────────────────────────
def probe_shuriken() -> None:
    """shuriken: the reset slot, the modulo, and boundary safety.

    Shuriken.cs:90-99 resets AttacksPlayedThisTurn from BeforeSideTurnStart
    (turn_structure step 9, before the block clear); shuriken.py:27-28 resets
    from on_player_turn_start, which the executed order puts after the block
    clear and the energy reset. Nothing reads the counter in that window --
    the play phase is later -- so it is the brilliant_scarf shape.

    Shuriken.cs:123-129 also resets at AfterCombatEnd; the sim does not, and
    this probe tests whether the turn-start reset really shadows it.
    """
    from sts2_rl import CombatState
    from sts2_rl.cards import make_card
    from sts2_rl.relics import make_relic

    def strength(cs):
        p = cs.player.powers.get("strength")
        return 0 if p is None else p.amount

    sh = make_relic("shuriken")
    cs = CombatState(rng=random.Random(0), relics=[sh],
                     starting_deck=[make_card("strike") for _ in range(10)])
    for n in range(1, 5):
        cs.hooks.on_card_played(make_card("strike"))
        print(f"  attack {n}: counter={sh._attacks_this_turn} "
              f"strength={strength(cs)}")
    print(f"  carried into combat 2 unreset: counter={sh._attacks_this_turn}")
    cs2 = CombatState(rng=random.Random(1), relics=[sh],
                      starting_deck=[make_card("strike") for _ in range(10)])
    print(f"  combat 2 after turn setup: counter={sh._attacks_this_turn} "
          f"strength={strength(cs2)}  (the turn-start reset shadows the "
          f"missing AfterCombatEnd reset)")

    print("\n  -- non-attacks do not count; C# has NO IsAutoPlay exclusion "
          "(Shuriken.cs:101-113), so counting auto-plays is CORRECT here "
          "(PROMPT.md class 29)")
    sh2 = make_relic("shuriken")
    cs3 = CombatState(rng=random.Random(0), relics=[sh2],
                      starting_deck=[make_card("strike") for _ in range(6)])
    cs3.hooks.on_card_played(make_card("defend"))
    print(f"     after a Defend: counter={sh2._attacks_this_turn}")
    cs3.player.hand.append(make_card("strike"))
    cs3.auto_play_card(cs3.player.hand[-1])
    print(f"     after an auto-played Strike: "
          f"counter={sh2._attacks_this_turn} (C#: 1 -- same)")

    print("\n  -- the owner check `cardPlay.Card.Owner == base.Owner` "
          "(Shuriken.cs:103): single-player, structurally satisfied.")


# ── sai-seal-slot ─────────────────────────────────────────────────────────
def probe_sai_seal_slot() -> None:
    """sai / seal_of_gold: AfterSideTurnStart vs the sim's one post-draw pass.

    Both relics implement C#'s AfterSideTurnStart (turn_structure step 23),
    which the game runs as a complete pass AFTER every AfterPlayerTurnStart
    listener (step 22) and then re-runs as AfterSideTurnStartLate. The sim has
    a single `on_player_turn_started` walk in relic-registration order --
    audits/seam/turn_structure.json guard G12, LIVE.
    """
    from sts2_rl import CombatState
    from sts2_rl.relics import make_relic

    print("  -- Sai's 7 Block is Unpowered: Dexterity and Frail do not "
          "touch it (BlockVar(7, Unpowered))")
    from sts2_rl.cmds import PowerCmd
    from sts2_rl.powers import DexterityPower
    sai = make_relic("sai")
    cs = CombatState(rng=random.Random(0), relics=[sai])
    print(f"     turn 1 block={cs.player.block}")
    PowerCmd.apply(cs.hooks, cs.player, DexterityPower, 5, applier=cs.player)
    cs.end_turn()
    print(f"     turn 2 with 5 Dexterity: block={cs.player.block} "
          f"(unpowered -> still 7)")

    print("\n  -- both relics land in the same sim pass as the step-22 "
          "relics; C# separates them")
    import subprocess
    out = subprocess.run(
        ["git", "grep", "-l", "def on_player_turn_started", "--",
         "sts2_rl/relics"], cwd=_REPO, capture_output=True, text=True).stdout
    names = sorted(Path(p).stem for p in out.split())
    print(f"     {len(names)} sim relics share on_player_turn_started: "
          f"{names}")
    print("     C# AfterPlayerTurnStart (step 22, earlier pass): bellows, "
          "blood_vial, choices_paradox, emotion_chip, fake_blood_vial, "
          "festive_popper, gambling_chip, mercury_hourglass, mr_struggles, "
          "pendulum, royal_poison, vexing_puzzlebox")
    print("     C# AfterSideTurnStart (step 23, later pass): sai, "
          "seal_of_gold, akabeko, bone_tea, ... -- so in C# Sai's Block and "
          "Seal of Gold's Energy always land AFTER all of the above.")


# ── flagon ────────────────────────────────────────────────────────────────
def probe_flagon() -> None:
    """screaming_flagon: the empty-hand AoE and which turn-end pass it is in.

    ScreamingFlagon.cs:21-28 is plain BeforeSideTurnEnd -- turn_structure step
    48, whose C# dispatcher runs BeforeSideTurnEndVeryEarly, then
    BeforeSideTurnEndEarly, then plain BeforeSideTurnEnd as three complete
    passes (Hook.cs:1238-1261). The sim's on_player_turn_end is one walk
    (combat.py:654): seam guard G12, LIVE.
    """
    from sts2_rl import CombatState
    from sts2_rl.cards import make_card
    from sts2_rl.relics import make_relic

    flagon = make_relic("screaming_flagon")
    cs = CombatState(rng=random.Random(0), relics=[flagon],
                     starting_deck=[make_card("strike") for _ in range(10)])
    for e in cs.enemies:
        e.max_hp, e.hp = 60, 60
    print(f"  turn 1 hand={len(cs.player.hand)} enemies="
          f"{[e.hp for e in cs.enemies]}")
    cs.end_turn()
    print(f"  end of turn 1 with a full hand: enemies="
          f"{[e.hp for e in cs.enemies]} (no damage -- correct)")
    cs.player.hand.clear()
    cs.end_turn()
    print(f"  end of turn 2 with an EMPTY hand: enemies="
          f"{[e.hp for e in cs.enemies]} (20 each, DamageVar(20, Unpowered))")

    print("\n  -- Unpowered: Strength does NOT scale it")
    from sts2_rl.cmds import PowerCmd
    from sts2_rl.powers import StrengthPower
    f2 = make_relic("screaming_flagon")
    cs2 = CombatState(rng=random.Random(0), relics=[f2],
                      starting_deck=[make_card("strike")])
    for e in cs2.enemies:
        e.max_hp, e.hp = 60, 60
    PowerCmd.apply(cs2.hooks, cs2.player, StrengthPower, 9, applier=cs2.player)
    cs2.player.hand.clear()
    cs2.end_turn()
    print(f"     with 9 Strength: enemy hp={[e.hp for e in cs2.enemies]} "
          f"(still 20 damage)")

    print("\n  -- the whole turn-end pass is skipped when Pael's Eye claims "
          "an extra turn: combat.py:648-652 asks ShouldTakeExtraTurn FIRST "
          "and returns, where C# asks it LAST (CombatManager.cs:1366, after "
          "BeforeTurnEnd / DoTurnEnd / the flush). PROMPT.md class 26 and "
          "turn_structure guard G3, at Screaming Flagon's own site.")
    for order in (["screaming_flagon"], ["paels_eye", "screaming_flagon"]):
        relics = [make_relic(r) for r in order]
        cs3 = CombatState(rng=random.Random(0), relics=relics,
                          starting_deck=[make_card("strike")])
        for e in cs3.enemies:
            e.max_hp, e.hp = 200, 200
        cs3.player.hand.clear()
        cs3.end_turn()
        print(f"     {order}: enemy={[e.hp for e in cs3.enemies]}   "
              f"(C# deals 20 in both cases)")


# ── sling ─────────────────────────────────────────────────────────────────
def probe_sling() -> None:
    """sling_of_courage: the Elite gate and the hook the port chose.

    SlingOfCourage.cs:21-28 is AfterRoomEntered, which for a CombatRoom fires
    after SetUpCombat and BEFORE Hook.BeforeCombatStart (CombatRoom.cs:225-229).
    The sim moves it onto on_combat_start (the BeforeCombatStart pass) and
    gates on combat.room_type -- the same re-hosting relics/girya.py:22 uses
    for the identical C# hook.
    """
    from sts2_rl import CombatState
    from sts2_rl.relics import make_relic
    from sts2_rl.rooms import RoomType

    def strength(cs):
        p = cs.player.powers.get("strength")
        return 0 if p is None else p.amount

    for rt in (RoomType.ELITE, RoomType.MONSTER, RoomType.BOSS, None):
        cs = CombatState(rng=random.Random(0),
                         relics=[make_relic("sling_of_courage")],
                         room_type=rt)
        label = rt.name if rt is not None else "None"
        print(f"  room_type={label:<8} strength={strength(cs)}")

    print("\n  -- is there a ported on_combat_start listener that READS the "
          "player's Strength (which C# guarantees is already +2)?")
    seen: list[str] = []

    class Sentinel:
        def on_combat_start(self) -> None:
            seen.append("sentinel-before-sling")

    cs = CombatState(rng=random.Random(0), relics=[], room_type=RoomType.ELITE)
    import subprocess
    out = subprocess.run(
        ["git", "grep", "-n", "-A6", "def on_combat_start", "--",
         "sts2_rl/relics"], cwd=_REPO, capture_output=True, text=True).stdout
    readers = [ln for ln in out.splitlines()
               if "powers.get" in ln or "powers[" in ln]
    print(f"     on_combat_start bodies reading a power: {readers or 'NONE'}")
    del cs, seen, Sentinel


# ── signet-ring ───────────────────────────────────────────────────────────
def probe_signet_ring() -> None:
    """signet_ring: GoldVar(999).BaseValue through PlayerCmd.GainGold."""
    from sts2_rl.run import RunState

    run = RunState(rng=random.Random(0), string_seed="B14PROBE")
    print(f"  gold {run.gold} -> ", end="")
    run.add_relic("signet_ring")
    print(f"{run.gold}")
    run2 = RunState(rng=random.Random(0), string_seed="B14PROBE")
    run2.add_relic("ectoplasm")
    g = run2.gold
    run2.add_relic("signet_ring")
    print(f"  with Ectoplasm (ModifyGoldGained -> 0): gold {g} -> {run2.gold} "
          f"(C#: unchanged -- the hook chain runs on both sides)")
    print("  Signet Ring does NOT declare HasUponPickupEffect in C# "
          "(SignetRing.cs has no such override) and the sim agrees.")


# ── sea-glass ─────────────────────────────────────────────────────────────
def probe_sea_glass() -> None:
    """sea_glass: the stub grants nothing and burns no Rewards draws.

    SeaGlass.cs:74-93 creates CardsVar(15)/3 == 5 cards per rarity from
    ANOTHER character's pool via CardFactory.CreateForReward -- 15 reward
    draws on the player's Rewards stream -- and offers them as a grid pick.
    Orobas.cs:186-206 assigns CharacterId to a random character OTHER than
    the player's, so the card half is genuinely other-character content.
    The stream consumption is not.
    """
    from sts2_rl.rng import RunRngSet
    from sts2_rl.run import RunState

    run = RunState(rng=random.Random(0), string_seed="B14PROBE")
    run.rng_set = RunRngSet("B14PROBE")
    n_deck, before = len(run.deck), run.player_rng.rewards.counter
    run.add_relic("sea_glass")
    print(f"  deck {n_deck} -> {len(run.deck)}; player Rewards counter "
          f"{before} -> {run.player_rng.rewards.counter}   "
          f"<-- C# burns 15 draws (5 per rarity) and offers a grid pick")
    print(f"  relic flags: has_upon_pickup_effect="
          f"{run.relics[-1].has_upon_pickup_effect}")
    print("  Orobas offers it: see events/orobas.py:58 "
          "(prismatic_gem 1/3, else sea_glass).")


# ── pyramid ───────────────────────────────────────────────────────────────
def probe_pyramid() -> None:
    """runic_pyramid: should_flush_hand, and the seam's named witness.

    audits/seam/turn_structure.json guard G4 already verdicts this mechanism a
    LIVE gap and names relics/runic_pyramid.py:16-17 as one of its two ported
    witnesses (the other is Ringing Triangle). Binding rule 3: cite and match,
    do not re-derive. This probe only confirms the port's own behaviour.
    """
    from sts2_rl import CombatState
    from sts2_rl.cards import make_card
    from sts2_rl.relics import make_relic

    for relics in ([], ["runic_pyramid"]):
        cs = CombatState(rng=random.Random(0),
                         relics=[make_relic(r) for r in relics],
                         starting_deck=[make_card("strike") for _ in range(10)])
        hand = len(cs.player.hand)
        cs.end_turn()
        print(f"  relics={relics or '[]'}: hand {hand} -> "
              f"{len(cs.player.hand)} after the turn, "
              f"should_flush={cs.hooks.should_flush_hand()}")
    print("  C# ShouldFlush has a `player != base.Owner -> true` clause "
          "(RunicPyramid.cs:10-16); the sim's zero-argument hook cannot "
          "express it -- single-player, so structurally satisfied.")


PROBES = {
    "pool": probe_pool,
    "sand-castle": probe_sand_castle,
    "clay-carry": probe_clay_carry,
    "clay-slot": probe_clay_slot,
    "seal-gold": probe_seal_gold,
    "card-reward-flag": probe_card_reward_flag,
    "crucible-life": probe_crucible_life,
    "scroll-boxes": probe_scroll_boxes,
    "scroll-neow": probe_scroll_neow,
    "sere-talon": probe_sere_talon,
    "shovel": probe_shovel,
    "shuriken": probe_shuriken,
    "sai-seal-slot": probe_sai_seal_slot,
    "flagon": probe_flagon,
    "sling": probe_sling,
    "signet-ring": probe_signet_ring,
    "sea-glass": probe_sea_glass,
    "pyramid": probe_pyramid,
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
