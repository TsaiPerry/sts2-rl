"""Reproducible execution probes for relic content audit BATCH 6.

Batch 6 units: fiddle, fishing_rod, forgotten_soul, fragrant_mushroom,
fresnel_lens, frozen_egg, fur_coat, gambling_chip, game_piece, ghost_seed,
girya, glass_eye, glitter, gnarled_hammer, golden_compass.

Companion to `tools/audit/relic_probes.py`, which stays READ-ONLY to this
batch per the concurrency contract (up to five batches run in sibling
worktrees and merge afterwards; every batch that edited the shared module is
exactly what would conflict). Re-use it read-only —
`py tools/audit/relic_probes.py turn-order` is the executed hook-order
reference and `sweep-reset` / `sweep-reset-exec` / `sweep-isallowed` /
`sweep-stubs` produced the pre-diagnosed units this batch confirms.

Binding rules 5 and 6 of the shared audit contract: never justify `faithful`
with an unreachability claim you have not EXECUTED, and never label a gap LIVE
without proving BOTH sides reachable with ported content.

  py tools/audit/relic_probes_b06.py                # every probe
  py tools/audit/relic_probes_b06.py fiddle-draw    # one probe

Probes:
  b06-pool        obtainability of batch 6's 15 relics (rule 6, first half)
  fiddle-draw     fiddle: enemy-turn draws the sim blocks and C# allows
  mushroom-sort   fragrant_mushroom: lowercase StableShuffle key picks the
                  wrong card
  piece-replay    game_piece: one draw per PLAY where C# draws per Replay
  fur-coat-acts   fur_coat: marked coords leak across acts in C#, not in the
                  sim; and `_armed` is re-derived at every room entry
  b06-stubs       fresnel_lens / gnarled_hammer: Nimble and Sharp ARE ported
  glass-eye       glass_eye: 15 missing Rewards draws, no upgrade roll, no
                  reward-option hooks, wrong pool (Feed / Not Yet)
  b06-isallowed   frozen_egg / girya: the IsAllowed pool gate has no sim
                  counterpart (sweep B's 16-relic cluster)
  b06-misc        fishing_rod reset, forgotten_soul, ghost_seed, gambling_chip,
                  girya, glitter, golden_compass, frozen_egg spot checks
"""
from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

BATCH6 = [
    "fiddle", "fishing_rod", "forgotten_soul", "fragrant_mushroom",
    "fresnel_lens", "frozen_egg", "fur_coat", "gambling_chip", "game_piece",
    "ghost_seed", "girya", "glass_eye", "glitter", "gnarled_hammer",
    "golden_compass",
]


# ── b06-pool ──────────────────────────────────────────────────────────────
def probe_b06_pool() -> None:
    """Obtainability of batch 6's 15 relics (binding rule 6, first half).

    Same method as `relic_probes.py pool`: grab-bag membership from the
    transcribed C# pools, every other grant path is a literal relic id
    somewhere under sts2_rl/.
    """
    import subprocess

    from sts2_rl.relic_pools import IRONCLAD_RELIC_POOL, SHARED_RELIC_POOL
    from sts2_rl.relics import ALL_RELICS

    bag = {rid.removeprefix("RELIC.").lower(): rarity
           for rid, rarity in SHARED_RELIC_POOL + IRONCLAD_RELIC_POOL}
    for rid in BATCH6:
        srcs = subprocess.run(
            ["git", "grep", "-l", f'"{rid}"', "--", "sts2_rl"],
            capture_output=True, text=True, cwd=_REPO,
        ).stdout.split()
        srcs = [s for s in srcs if not s.endswith(f"relics/{rid}.py")]
        print(f"  {rid:<20} registered={rid in ALL_RELICS} "
              f"bag={bag.get(rid, '-'):<9} granted_by={srcs or ['(none)']}")


# ── fiddle-draw ───────────────────────────────────────────────────────────
def probe_fiddle_draw() -> None:
    """fiddle G1: the sim blocks EVERY non-hand-draw draw; C# allows draws
    taken while the ENEMY side has the turn.

    Fiddle.cs:24-39 has three bails, and the third is
    `player.Creature.Side != player.Creature.CombatState.CurrentSide -> return
    true`, i.e. the veto applies only during the relic owner's OWN turn.
    fiddle.py:26-29 is `return from_hand_draw` and consults no side at all,
    although the sim HAS the concept (`CombatState.current_side`, combat.py:170
    / :280, used by relics/unceasing_top.py:24 and relics/demon_tongue.py:38).

    Ported trigger: Centennial Puzzle draws 3 on the first HP loss of the
    combat (relics/centennial_puzzle.py:32-35) and the player loses HP on the
    ENEMY's turn, inside CombatState._execute_enemy_turn's
    `current_side = "enemy"` window (combat.py:279-284).
    """
    import sts2_rl.cards  # noqa: F401  (registration)
    from sts2_rl import CombatState
    from sts2_rl.relics import make_relic

    for label, ids in (("puzzle only", ["centennial_puzzle"]),
                       ("puzzle + fiddle", ["centennial_puzzle", "fiddle"])):
        cs = CombatState(rng=random.Random(3),
                         relics=[make_relic(r) for r in ids])
        seen: list[str] = []
        orig = cs.hooks.should_draw

        def spy(player, from_hand_draw=False, _o=orig, _s=seen, _cs=cs):
            allowed = _o(player, from_hand_draw)
            _s.append(f"{_cs.current_side}/{'hand' if from_hand_draw else 'mid'}"
                      f"={allowed}")
            return allowed

        cs.hooks.should_draw = spy  # type: ignore[method-assign]
        t1 = len(cs.player.hand)
        cs.end_turn()
        enemy_side = [s for s in seen if s.startswith("enemy/")]
        print(f"  {label:<16} turn-1 hand={t1}  after the enemy turn "
              f"hand={len(cs.player.hand)}")
        print(f"                   should_draw calls on the ENEMY side: "
              f"{enemy_side or '(none)'}")
    print("  C#: 3 (Centennial Puzzle) + 7 (hand draw 5 + Fiddle 2) = 10 in "
          "hand; the sim reports 7 -- the puzzle's 3 are silently vetoed.")


# ── mushroom-sort ─────────────────────────────────────────────────────────
def probe_mushroom_sort() -> None:
    """fragrant_mushroom G1: the StableShuffle sort key is the sim's LOWERCASE
    slug, and an ordinal compare orders `_` (0x5F) BEFORE lowercase letters and
    AFTER uppercase ones.

    ListExtensions.StableShuffle (ListExtensions.cs:22-31) sorts with
    CardModel.CompareTo (CardModel.cs:2242-2263) -> ModelId.CompareTo
    (ModelId.cs:42-50), an ORDINAL compare over the game's UPPERCASE Entry,
    then CurrentUpgradeLevel. fragrant_mushroom.py:35 passes
    `key=lambda c: (c.id, c.upgrade_level)` -- the lowercase slug.

    The sim already HAS the correct key: player.py:23-35's `_compare_to_key`
    returns `(card.id.upper(), card.upgrade_level)` and its docstring names the
    exact inverting pairs. This probe executes the difference.
    """
    import sts2_rl.cards  # noqa: F401
    from sts2_rl.actmap import stable_shuffle
    from sts2_rl.cards import make_card
    from sts2_rl.cards.base import _CARD_CLASSES
    from sts2_rl.cards.pool import pool_card_ids
    from sts2_rl.player import _compare_to_key
    from sts2_rl.rng import Rng

    ids = sorted(_CARD_CLASSES)
    inverting = [(a, b) for i, a in enumerate(ids) for b in ids[i + 1:]
                 if (a < b) != (a.upper() < b.upper())]
    pool = set(pool_card_ids())
    print(f"  ported card ids: {len(ids)}; pairs whose relative order INVERTS "
          f"between the lowercase and the uppercase key: {len(inverting)}")
    for a, b in inverting:
        print(f"    {a:<20} vs {b:<20} both in the Ironclad reward pool: "
              f"{a in pool and b in pool}")

    deck_ids = ["blood_wall", "bloodletting", "strike", "defend"]
    print(f"\n  deck {deck_ids}, FragrantMushroom takes 2 "
          f"(Rng.Niche StableShuffle + Take):")
    differ = 0
    for seed in range(8):
        sim = [c.id for c in stable_shuffle(
            [make_card(i) for i in deck_ids], Rng(seed=seed),
            key=lambda c: (c.id, c.upgrade_level))[:2]]
        game = [c.id for c in stable_shuffle(
            [make_card(i) for i in deck_ids], Rng(seed=seed),
            key=_compare_to_key)[:2]]
        differ += sim != game
        print(f"    niche seed {seed}: sim upgrades {sim}   game upgrades "
              f"{game}   {'DIFFER' if sim != game else 'same'}")
    print(f"  {differ}/8 seeds upgrade a different card.")


# ── piece-replay ──────────────────────────────────────────────────────────
def probe_piece_replay() -> None:
    """game_piece G1: `Hook.AfterCardPlayed` fires once per Replay iteration in
    C# and once per PLAY in the sim, so a replayed Power card draws 1 instead
    of 2.

    Mechanism recorded at audits/seam/hook_dispatch.json G4 and at
    audits/relic/unsettling_lamp.json G1 (CardModel.cs:1904-1963 builds a fresh
    CardPlay inside `for (int i = 0; i < playCount; i++)` and fires the hook at
    line 1961 INSIDE the loop; combat.py:514 calls hooks.on_card_played once
    after the whole loop). Same mechanism, same verdict -- binding rule 3.

    Ported trigger: Throwing Axe replays the first card of each combat
    (relics/throwing_axe.py:30-36), granted by the ported Tanx shrine.
    """
    import sts2_rl.cards  # noqa: F401
    from sts2_rl import CombatState
    from sts2_rl.cards import CardType, make_card
    from sts2_rl.cards.base import _CARD_CLASSES
    from sts2_rl.relics import make_relic

    n_powers = sum(1 for c in _CARD_CLASSES.values()
                   if c.card_type == CardType.POWER)
    print(f"  ported POWER cards: {n_powers}")
    for ids in (["game_piece"], ["game_piece", "throwing_axe"]):
        cs = CombatState(rng=random.Random(0),
                         relics=[make_relic(r) for r in ids])
        cs.player.hand.clear()
        cs.player.energy = 9
        cs.player.hand.append(make_card("inflame"))
        before = len(cs.player.draw_pile)
        cs.play_card(0, None)
        drawn = before - len(cs.player.draw_pile)
        st = cs.player.powers.get("strength")
        print(f"  {str(ids):<38} Inflame: strength={st}  cards drawn={drawn}")
    print("  Strength 4 proves the Power resolved TWICE, yet only 1 card was "
          "drawn; C# draws 1 per Replay iteration = 2.")


# ── fur-coat-acts ─────────────────────────────────────────────────────────
def probe_fur_coat_acts() -> None:
    """fur_coat: two findings, both executed.

    (a) FurCoat.BeforeCombatStart (FurCoat.cs:114-128) checks ONLY
        `markedCoords.Contains(RunState.CurrentMapPoint.coord)` -- no act
        check, where AddMarkedRooms has one (line 65). MapCoords repeat across
        acts, so in the GAME a later act's combat standing on a coord marked in
        the pickup act also drops every enemy to 1 HP. fur_coat.py:73-77 gates
        `_armed` on `self.act_index == run.act_index`, so the sim never fires.

    (b) sweep-reset flags `_armed` / `act_index` / `marked_coords` as
        never reset at a combat boundary (the belt_buckle shape). Settled by
        execution: `_armed` is UNCONDITIONALLY re-assigned by
        after_room_entered (fur_coat.py:74), which RunState.enter_room
        dispatches for every room before its contents resolve (run.py:982-983),
        so no reader can see a stale value.
    """
    from sts2_rl.run import RunState

    print("  (a) cross-act MapCoord collision:")
    for seed in (7, 11, 23, 42):
        run = RunState(rng=random.Random(seed))
        run.start_run()
        run.add_relic("fur_coat")
        fc = next(r for r in run.relics if r.id == "fur_coat")
        marked = set(fc.marked_coords)
        run.advance_act()
        pts = {p.coord: p.point_type for p in run.map.all_points()}
        overlap = {c: pts[c].name for c in sorted(marked) if c in pts}
        print(f"    seed {seed}: act {fc.act_index} marked {len(marked)} coords;"
              f" {len(overlap)} of them exist on the act-{run.act_index} map "
              f"-> {overlap}")
        print(f"      sim would arm there? "
              f"{fc.act_index == run.act_index}   (C#: yes, no act check)")

    print("\n  (b) `_armed` is re-derived at every room entry, so it cannot "
          "latch:")
    run = RunState(rng=random.Random(7))
    run.start_run()
    run.add_relic("fur_coat")
    fc = next(r for r in run.relics if r.id == "fur_coat")
    marked = sorted(fc.marked_coords)
    fc._armed = True  # pretend a previous combat left it set
    unmarked = next(p for p in run.map.all_points()
                    if p.coord not in fc.marked_coords)
    fc.after_room_entered(run, unmarked, None)
    print(f"    forced _armed=True, then entered UNMARKED {unmarked.coord}: "
          f"_armed={fc._armed}   (must be False)")
    first = run.map.get_point(*marked[0])
    fc.after_room_entered(run, first, None)
    print(f"    then entered MARKED {first.coord}: _armed={fc._armed}   "
          f"(must be True)")


# ── b06-stubs ─────────────────────────────────────────────────────────────
def probe_b06_stubs() -> None:
    """fresnel_lens and gnarled_hammer are behaviourless ports whose docstrings
    claim the sim has no enchantments. Bug class 12: check the claim.

    `sweep-stubs` / `sweep-stub-premises` already reported both premises FALSE.
    This probe executes the two relics' own effects.
    """
    import sts2_rl.cards  # noqa: F401
    from sts2_rl.cards import make_card
    from sts2_rl.enchantments import ALL_ENCHANTMENTS
    from sts2_rl.relics import make_relic
    from sts2_rl.run import RunState

    for eid in ("nimble", "sharp", "glam"):
        cls = ALL_ENCHANTMENTS.get(eid)
        print(f"  enchantment {eid!r} ported: {cls is not None}  ({cls})")

    print("\n  -- fresnel_lens: C# enchants Nimble onto every card entering the "
          "deck (TryModifyCardBeingAddedToDeck), every card reward option "
          "(TryModifyCardRewardOptionsLate) and every merchant card "
          "(ModifyMerchantCardCreationResults).")
    lens = make_relic("fresnel_lens")
    print(f"     port defines any of the three hooks: "
          f"{[h for h in ('modify_card_being_added_to_deck',
                          'modify_card_reward_options',
                          'modify_merchant_card_results')
              if h in type(lens).__dict__]}")
    run = RunState(rng=random.Random(0))
    run.add_relic("fresnel_lens")
    card = make_card("defend")
    run.add_card(card)
    nimble = ALL_ENCHANTMENTS["nimble"]
    print(f"     Defend added to the deck: enchantment={card.enchantment!r}   "
          f"(C#: Nimble 2)   Nimble.can_enchant(Defend)="
          f"{nimble.can_enchant(make_card('defend'))}")

    print("\n  -- gnarled_hammer: C# offers a pick-up-to-3 deck screen and "
          "enchants each pick with Sharp 3 (GnarledHammer.cs:28-40).")
    run2 = RunState(rng=random.Random(0))
    run2.card_selector = lambda purpose, cands, count: list(cands)[:count]
    run2.add_relic("gnarled_hammer")
    ench = [(c.id, c.enchantment) for c in run2.deck if c.enchantment]
    sharp = ALL_ENCHANTMENTS["sharp"]
    attacks = [c.id for c in run2.deck if sharp.can_enchant(c)]
    print(f"     enchanted deck cards after the pickup: {ench}   "
          f"(C#: 3 x Sharp 3)")
    print(f"     starting-deck cards Sharp CAN enchant: {attacks}")


# ── glass-eye ─────────────────────────────────────────────────────────────
def probe_glass_eye() -> None:
    """glass_eye: four executed findings on the five 3-card screens.

    C# path: RewardsCmd.OfferCustom -> RewardsSet.Offer -> GenerateWithoutOffering
    (RewardsSet.cs:125-147) populates ALL FIVE rewards up front, each via
    CardFactory.CreateForReward(player, 3, options) (CardFactory.cs:89-109).
    Per card that is (1) one `PlayerRng.Rewards.NextItem` draw
    (CardFactory.cs:235-236 -- Uniform odds means NO rarity roll) and (2) one
    unconditional `rng.NextFloat()` upgrade roll (CardFactory.cs:288-304; the
    draw precedes the IsUpgradable test), then (3) `Hook.
    TryModifyCardRewardOptions` over BOTH phases (CardFactory.cs:104,
    Hook.cs:1445-1468) because GlassEye sets only NoRarityModification.
    """
    import sts2_rl.cards  # noqa: F401
    from sts2_rl.cards import CardRarity
    from sts2_rl.cards.base import _CARD_CLASSES
    from sts2_rl.cards.pool import pool_card_ids, reward_pool_card_ids
    from sts2_rl.run import RunState

    run = RunState(rng=random.Random(0), string_seed="89U21BV1TZ")
    run.start_run()
    run.card_selector = lambda purpose, cands, count: list(cands)[:count]
    before = run.player_rng.rewards.counter
    run.add_relic("glass_eye")
    after = run.player_rng.rewards.counter
    print(f"  (1) PlayerRng.Rewards counter {before} -> {after} "
          f"(delta {after - before}); C# = 15 NextItem + 15 NextFloat upgrade "
          f"rolls = 30. Every later Rewards draw in the run is shifted.")
    print(f"  (2) upgraded cards among the 5 taken: "
          f"{[(c.id, c.upgrade_level) for c in run.deck if c.upgrade_level]}  "
          f"-- the port's docstring says 'never upgraded', but C# odds are "
          f"act_index * 0.125 for non-Rares "
          f"(CardFactory.UpgradedCardOddScaling, non-ascension arm), so from "
          f"act 1 on the game CAN upgrade them (run act_index={run.act_index}).")

    run2 = RunState(rng=random.Random(0), string_seed="89U21BV1TZ")
    run2.start_run()
    run2.card_selector = lambda purpose, cands, count: list(cands)[:count]
    run2.add_relic("glitter")
    run2.add_relic("glass_eye")
    got = [(c.id, c.enchantment) for c in run2.deck[10:]]
    print(f"  (3) with Glitter in the run, the 5 cards Glass Eye grants: {got}"
          f"   (C#: every Glam-eligible option carries Glam, because "
          f"CreateForReward fires TryModifyCardRewardOptions(+Late))")

    combat_pool = set(pool_card_ids())
    dropped = sorted(
        cid for cid in reward_pool_card_ids()
        if cid not in combat_pool
        and _CARD_CLASSES[cid].rarity in (CardRarity.COMMON,
                                          CardRarity.UNCOMMON,
                                          CardRarity.RARE))
    print(f"  (4) glass_eye.py:22 uses pool_card_ids() (FilterForCombat); the "
          f"reward pool is GetUnlockedCards. Reward-eligible ids it drops: "
          f"{[(d, _CARD_CLASSES[d].rarity.name) for d in dropped]}")


# ── b06-isallowed ─────────────────────────────────────────────────────────
def probe_b06_isallowed() -> None:
    """frozen_egg / girya: `RelicModel.IsAllowed` has no sim counterpart.

    Confirms sweep B's 16-relic `IsBeforeAct3TreasureChest` cluster at this
    batch's two members. `IsBeforeAct3TreasureChest` is `TotalFloor < 41`
    (RelicModel.cs:452-456).
    """
    from sts2_rl.relic_pools import IRONCLAD_RELIC_POOL, SHARED_RELIC_POOL
    from sts2_rl.relics import ALL_RELICS, base as relic_base
    from sts2_rl.run import RunState

    print(f"  Relic base defines 'is_allowed': "
          f"{'is_allowed' in dir(relic_base.Relic)}   "
          f"'is_allowed_at_neow': {'is_allowed_at_neow' in dir(relic_base.Relic)}")
    bag = {rid.removeprefix('RELIC.').lower(): rarity
           for rid, rarity in SHARED_RELIC_POOL + IRONCLAD_RELIC_POOL}
    for rid in ("frozen_egg", "girya"):
        print(f"  {rid:<12} registered={rid in ALL_RELICS} "
              f"grab-bag rarity={bag.get(rid, '-')}")
    run = RunState(rng=random.Random(0))
    print(f"  RunState tracks total_floor: {hasattr(run, 'total_floor')} "
          f"(= IRunState.TotalFloor, run.py:977)")
    import subprocess
    hits = subprocess.run(
        ["git", "grep", "-n", "is_allowed", "--", "sts2_rl/relic_pools.py",
         "sts2_rl/run.py"],
        capture_output=True, text=True, cwd=_REPO).stdout.strip()
    print(f"  any is_allowed filter in the pull path: {hits or '(none)'}")


# ── b06-misc ──────────────────────────────────────────────────────────────
def probe_b06_misc() -> None:
    """Spot checks that settle single guards elsewhere in the batch."""
    import sts2_rl.cards  # noqa: F401
    from sts2_rl import CombatState
    from sts2_rl.cards import make_card
    from sts2_rl.enchantments import ALL_ENCHANTMENTS
    from sts2_rl.relics import make_relic
    from sts2_rl.rooms import RoomType
    from sts2_rl.run import RunState

    print("  -- fishing_rod: `combats_seen` is a per-RUN counter on both sides "
          "(FishingRod.cs:48 increments in AfterCombatEnd, nothing resets it). "
          "sweep-reset flags it only because the AST sees an AfterCombatEnd "
          "override; sweep-reset-exec puts it in the 13 that agree with a "
          "fresh instance.")
    rod = make_relic("fishing_rod")
    run = RunState(rng=random.Random(0))
    run.relics.append(rod)
    for n in range(1, 5):
        rod.after_combat_end(run, RoomType.MONSTER)
        print(f"     monster combat {n}: combats_seen={rod.combats_seen} "
              f"upgraded deck cards="
              f"{sum(1 for c in run.deck if c.upgrade_level)}")
    rod2 = make_relic("fishing_rod")
    run2 = RunState(rng=random.Random(0))
    run2.relics.append(rod2)
    rod2.after_combat_end(run2, RoomType.ELITE)
    print(f"     an ELITE combat: combats_seen={rod2.combats_seen}   "
          f"(C#: unchanged -- RoomType.Monster only)")

    print("\n  -- forgotten_soul: exhausting a card damages a random living "
          "enemy for 1 unpowered.")
    cs = CombatState(rng=random.Random(0),
                     relics=[make_relic("forgotten_soul")])
    from sts2_rl.cmds import ExhaustCmd
    hp0 = [e.hp for e in cs.enemies]
    cs.player.hand.clear()
    card = make_card("defend")
    cs.player.hand.append(card)
    ExhaustCmd.exhaust(cs.hooks, cs.player, card)
    print(f"     enemy hp {hp0} -> {[e.hp for e in cs.enemies]}")
    from sts2_rl.powers import StrengthPower
    from sts2_rl.cmds import PowerCmd
    cs2 = CombatState(rng=random.Random(0),
                      relics=[make_relic("forgotten_soul")])
    PowerCmd.apply(cs2.hooks, cs2.player, StrengthPower, 5,
                   applier=cs2.player)
    hp0 = [e.hp for e in cs2.enemies]
    cs2.player.hand.clear()
    card = make_card("defend")
    cs2.player.hand.append(card)
    ExhaustCmd.exhaust(cs2.hooks, cs2.player, card)
    print(f"     with Strength 5: enemy hp {hp0} -> "
          f"{[e.hp for e in cs2.enemies]}   (Unpowered: still 1)")

    print("\n  -- ghost_seed: `card.is_ethereal = True` is a permanent mutation "
          "of the card object, so it is safe only because RunState.create_combat "
          "hands the combat a deepcopy of the deck (run.py:1136). Executed both "
          "ways:")
    import copy as _copy
    run3 = RunState(rng=random.Random(0))
    run3.add_relic("ghost_seed")
    cs3 = CombatState(rng=random.Random(0), relics=run3.relics,
                      starting_deck=_copy.deepcopy(run3.deck))
    print(f"     via a deepcopy (the create_combat path): ethereal in combat="
          f"{sum(1 for c in cs3.player.all_cards if c.is_ethereal)}  in the run "
          f"deck={sum(1 for c in run3.deck if c.is_ethereal)}   (C#: 9 / 0)")
    run3b = RunState(rng=random.Random(0))
    run3b.add_relic("ghost_seed")
    CombatState(rng=random.Random(0), relics=run3b.relics,
                starting_deck=list(run3b.deck))
    print(f"     if a caller passes the deck WITHOUT copying: run-deck ethereal="
          f"{sum(1 for c in run3b.deck if c.is_ethereal)}  (the mutation would "
          f"outlive the relic; C# scopes the keyword to the combat card)")

    print("\n  -- gambling_chip: CardCmd.DiscardAndDraw auto-plays every "
          "discarded card that IsSlyThisTurn after the draw (CardCmd.cs:188, "
          ":201-204). Sly is UNPORTED:")
    import subprocess
    hits = subprocess.run(
        ["git", "grep", "-in", "is_sly\\|IsSly\\|CardKeyword.Sly", "--",
         "sts2_rl"], capture_output=True, text=True, cwd=_REPO).stdout.strip()
    print(f"     grep is_sly over sts2_rl/: {hits or '(no hits)'}")
    chip = make_relic("gambling_chip")
    seen_discards: list[str] = []
    cs4 = CombatState(rng=random.Random(0), relics=[chip])
    print(f"     turn-1 hand={len(cs4.player.hand)} draw_pile="
          f"{len(cs4.player.draw_pile)} discard={len(cs4.player.discard_pile)}")
    chip2 = make_relic("gambling_chip")
    cs5b = CombatState(rng=random.Random(0), relics=[chip2],
                       starting_deck=[make_card("strike") for _ in range(20)])
    cs5b.hooks.on_card_discarded = (  # type: ignore[method-assign]
        lambda card, _s=seen_discards: _s.append(card.id))
    cs5b.player.hand.clear()
    cs5b.player.hand.extend(cs5b.player.draw_pile[:3])
    del cs5b.player.draw_pile[:3]
    chip2.on_player_turn_started(cs5b.player)
    print(f"     20-card deck, 3-card hand, default selector: discarded "
          f"{seen_discards} (all 3), hand refilled to {len(cs5b.player.hand)}. "
          f"C#'s CardSelectorPrefs min is 0, so the game lets the player keep "
          f"the hand; the sim's fallback always discards `count`.")

    print("\n  -- girya: on_combat_start applies Strength == times_lifted; C# "
          "applies it in AfterRoomEntered, which CombatRoom.cs:228 fires "
          "AFTER SetUpCombat but BEFORE StartCombatInternal's "
          "Hook.BeforeCombatStart (CombatManager.cs:403).")
    g = make_relic("girya")
    g.times_lifted = 3
    cs5 = CombatState(rng=random.Random(0), relics=[g])
    print(f"     3 lifts -> combat-start strength="
          f"{cs5.player.powers.get('strength')}")
    opts: list = []
    g2 = make_relic("girya")
    run4 = RunState(rng=random.Random(0))
    for lifts in (0, 3):
        g2.times_lifted = lifts
        opts.clear()
        g2.modify_rest_site_options(run4, opts)
        print(f"     times_lifted={lifts}: rest-site options offered="
              f"{[o.key for o in opts]}")

    print("\n  -- glitter: Glam attaches to reward options in place; C# clones "
          "the card first (CloneCard, Glitter.cs:30) -- class 17. Executed: "
          "one enchantment slot per card on both sides "
          "(EnchantmentModel.CanEnchant, :289: no ported enchantment is "
          "IsStackable).")
    glam = ALL_ENCHANTMENTS["glam"]
    swift = ALL_ENCHANTMENTS["swift"]
    c = make_card("strike")
    swift().attach(c)
    print(f"     Strike+Swift: Glam.can_enchant={glam.can_enchant(c)}   "
          f"(C#: false too -- Enchantment != null and !IsStackable)")
    opts2 = [make_card("strike"), make_card("dazed")]
    make_relic("glitter").modify_card_reward_options(
        RunState(rng=random.Random(0)), opts2)
    print(f"     reward options after Glitter: "
          f"{[(o.id, o.enchantment) for o in opts2]}")

    print("\n  -- golden_compass: GoldenPathActMap (GoldenPathActMap.cs:39-68) "
          "consumes NO rng; golden_path_map(actmap.py:1027-1057) stores the "
          "rng and draws nothing either.")
    run5 = RunState(rng=random.Random(5))
    run5.start_run()
    st0 = run5.rng.getstate()
    run5.add_relic("golden_compass")
    types = [p.point_type.name for p in run5.map.all_points()]
    print(f"     act map after the pickup: {len(types)} points -> {types}")
    print(f"     shared run rng advanced during regenerate_map: "
          f"{run5.rng.getstate() != st0}  (faithful: RunManager.GenerateMap "
          f"also builds State.Act.CreateMap FIRST, RunManager.cs:745, then lets "
          f"ModifyGeneratedMap replace it)")
    gc = next(r for r in run5.relics if r.id == "golden_compass")
    print(f"     golden_path_act={gc.golden_path_act} "
          f"modify_unknown_map_point_room_types(act {run5.act_index})="
          f"{gc.modify_unknown_map_point_room_types(run5, {'X'})}")

    print("\n  -- fur_coat x golden_compass: Hook.ModifyGeneratedMapLate has "
          "exactly ONE caller in the game -- RunManager.cs:740, inside the "
          "SavedActMap (save-load) branch of GenerateMap. The fresh-generation "
          "branch (RunManager.cs:745-747) runs ModifyGeneratedMap and "
          "AfterMapGenerated ONLY. run.py:857-860 runs the Late pass on every "
          "fresh generation, so the sim re-marks where the game does not:")
    run7 = RunState(rng=random.Random(11))
    run7.start_run()
    run7.add_relic("fur_coat")
    fc7 = next(r for r in run7.relics if r.id == "fur_coat")
    was = sorted(fc7.marked_coords)
    run7.add_relic("golden_compass")
    print(f"     marked before the Golden Compass regeneration: {was}")
    print(f"     marked after:                                  "
          f"{sorted(fc7.marked_coords)}   (C#: unchanged)")

    print("\n  -- frozen_egg: the sim upgrades the card IN PLACE where C# swaps "
          "in an upgraded CloneCard (FrozenEgg.cs:58-59, EggRelicHelper.cs:17). "
          "It also drops the CardCreationFlags.NoHookUpgrades guard "
          "(FrozenEgg.cs:27-30):")
    import sts2_rl.hooks as simhooks
    print(f"     sim has a card-creation-flags concept: "
          f"{'CardCreationFlags' in dir(simhooks)}")
    run6 = RunState(rng=random.Random(0))
    run6.add_relic("frozen_egg")
    power = make_card("inflame")
    run6.add_card(power)
    print(f"     Inflame added to the deck: upgrade_level="
          f"{power.upgrade_level}  same object in deck="
          f"{any(c is power for c in run6.deck)}")


PROBES = {
    "b06-pool": probe_b06_pool,
    "fiddle-draw": probe_fiddle_draw,
    "mushroom-sort": probe_mushroom_sort,
    "piece-replay": probe_piece_replay,
    "fur-coat-acts": probe_fur_coat_acts,
    "b06-stubs": probe_b06_stubs,
    "glass-eye": probe_glass_eye,
    "b06-isallowed": probe_b06_isallowed,
    "b06-misc": probe_b06_misc,
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
