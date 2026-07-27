"""Reproducible execution probes for relic content audit batch 13.

Batch 13's units: prismatic_gem, pumpkin_candle, punch_dagger, radiant_pearl,
rainbow_ring, razor_tooth, red_mask, red_skull, regal_pillow, reptile_trinket,
ringing_triangle, ripple_basin, royal_poison, royal_stamp, ruined_helmet.

Own module per the batch-13 concurrency contract (`audit/tools/relic_probes.py`
is read-only to this batch); the shared module is still the reference for
`turn-order` and the pool-wide sweeps and should be re-used, not re-implemented.

  py audit/tools/relic_probes_b13.py                 # every probe
  py audit/tools/relic_probes_b13.py red-skull       # one probe

Probes:
  pool             obtainability of batch 13's 15 relics
  red-skull        the missing per-combat reset, BOTH directions (LIVE)
  ruined-helmet    the missing per-combat reset (LIVE)
  ripple-basin     turn_structure G12's two-phase collapse at its own site
  ringing-triangle turn_structure G4's skipped flush tail at its own site
  royal-poison     turn_structure G13's missing turn-1 CheckWinCondition
  regal-pillow     the +15 rest-site heal that no sim hook can deliver (LIVE)
  pumpkin-candle   the kindle lifecycle end to end (confirms faithful)
  stub-premises    what punch_dagger / royal_stamp / regal_pillow actually need
  red-mask         the hook slot the Weak lands in
  razor-tooth      deck isolation + the IsUpgradable guard
  radiant-pearl    the turn-1 Luminesce
  prismatic-gem    the +1 max Energy
  rainbow-ring     activation gate, auto-play counting, boundary safety
  reptile-trinket  the temporary Strength on a potion use
  sweep-exec-blind why sweep-reset-exec cleared three of this batch's relics
"""
from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

BATCH13 = [
    "prismatic_gem", "pumpkin_candle", "punch_dagger", "radiant_pearl",
    "rainbow_ring", "razor_tooth", "red_mask", "red_skull", "regal_pillow",
    "reptile_trinket", "ringing_triangle", "ripple_basin", "royal_poison",
    "royal_stamp", "ruined_helmet",
]


# ── pool ──────────────────────────────────────────────────────────────────
def probe_pool() -> None:
    """Where each batch-13 relic can come from (binding rule 6)."""
    import subprocess

    from sts2_rl.relic_pools import IRONCLAD_RELIC_POOL, SHARED_RELIC_POOL
    from sts2_rl.relics import ALL_RELICS

    bag = {rid.removeprefix("RELIC.").lower(): rarity
           for rid, rarity in list(SHARED_RELIC_POOL) + list(IRONCLAD_RELIC_POOL)}
    for rid in BATCH13:
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


# ── red-skull ─────────────────────────────────────────────────────────────
def probe_red_skull() -> None:
    """red_skull: `_applied` is never reset, and C# resets it at AfterCombatEnd.

    RedSkull.cs:52-57 `AfterCombatEnd` sets `StrengthApplied = false`;
    relics/red_skull.py writes `_applied` only in `_update`. Relic instances
    live on RunState.relics and are re-attached to each CombatState, so the
    flag crosses the boundary while the StrengthPower it describes does not.
    Two independent wrong outcomes follow, so both are executed.
    """
    from sts2_rl import CombatState
    from sts2_rl.relics import make_relic

    def strength(cs) -> int:
        p = cs.player.powers.get("strength")
        return 0 if p is None else p.amount

    print("  -- direction 1: still below the threshold in combat 2 -> no "
          "Strength at all (C#: 3)")
    skull = make_relic("red_skull")
    cs1 = CombatState(rng=random.Random(0), relics=[skull],
                      max_hp=80, current_hp=30)
    print(f"     combat 1: hp={cs1.player.hp}/{cs1.player.max_hp} "
          f"_applied={skull._applied} strength={strength(cs1)}")
    cs2 = CombatState(rng=random.Random(1), relics=[skull],
                      max_hp=80, current_hp=30)
    fresh = make_relic("red_skull")
    cs_f = CombatState(rng=random.Random(1), relics=[fresh],
                       max_hp=80, current_hp=30)
    print(f"     combat 2 (carried instance): _applied={skull._applied} "
          f"strength={strength(cs2)}   <-- C# gives 3")
    print(f"     combat 2 (fresh instance):   _applied={fresh._applied} "
          f"strength={strength(cs_f)}   <-- the correct answer")

    print("\n  -- direction 2: healed ABOVE the threshold between combats -> "
          "the sim applies -3 Strength to a player who has none")
    skull2 = make_relic("red_skull")
    csa = CombatState(rng=random.Random(0), relics=[skull2],
                      max_hp=80, current_hp=30)
    print(f"     combat 1: _applied={skull2._applied} "
          f"strength={strength(csa)}")
    csb = CombatState(rng=random.Random(1), relics=[skull2],
                      max_hp=80, current_hp=80)
    print(f"     combat 2 at full HP: _applied={skull2._applied} "
          f"strength={strength(csb)}   <-- C# gives 0 Strength, no power")

    print("\n  -- the threshold arithmetic (C# `CurrentHp > MaxHp * 50/100` as "
          "decimal vs the sim's `hp <= max_hp*50//100`)")
    for mhp in (74, 75, 80, 81):
        thr = mhp * 50 // 100
        cs_hi = CombatState(rng=random.Random(2), relics=[make_relic("red_skull")],
                            max_hp=mhp, current_hp=thr)
        cs_lo = CombatState(rng=random.Random(2), relics=[make_relic("red_skull")],
                            max_hp=mhp, current_hp=thr + 1)
        print(f"     max_hp={mhp:<3} sim threshold={thr:<3} "
              f"hp={thr} -> str {strength(cs_hi)}   hp={thr + 1} -> "
              f"str {strength(cs_lo)}   (C# boundary {mhp * 0.5})")

    print("\n  -- C#'s AfterCurrentHpChanged has NO `creature == Owner` check "
          "(RedSkull.cs:59-65); the sim gates on it (red_skull.py:41).")
    cs3 = CombatState(rng=random.Random(3), relics=[make_relic("red_skull")],
                      max_hp=80, current_hp=41)
    before = strength(cs3)
    from sts2_rl.cmds import DamageCmd
    from sts2_rl.valueprops import DamageProps
    DamageCmd.deal(cs3.hooks, cs3.enemy, 1, props=DamageProps.NON_CARD_HP_LOSS)
    print(f"     player hp={cs3.player.hp}/{cs3.player.max_hp} "
          f"strength {before} -> {strength(cs3)} after damaging the ENEMY "
          f"(both sides: 0 -- the re-evaluation is idempotent)")


# ── ruined-helmet ─────────────────────────────────────────────────────────
def probe_ruined_helmet() -> None:
    """ruined_helmet: `_used` is never reset; C# clears it at AfterCombatEnd."""
    from sts2_rl import CombatState
    from sts2_rl.cmds import PowerCmd
    from sts2_rl.powers import StrengthPower
    from sts2_rl.relics import make_relic

    helmet = make_relic("ruined_helmet")
    for n, seed in enumerate((0, 1), start=1):
        cs = CombatState(rng=random.Random(seed), relics=[helmet])
        PowerCmd.apply(cs.hooks, cs.player, StrengthPower, 2,
                       applier=cs.player)
        print(f"     combat {n} (carried): _used={helmet._used} "
              f"strength={cs.player.powers['strength'].amount}   "
              f"(C# combat 2: 4)")
    fresh = make_relic("ruined_helmet")
    cs = CombatState(rng=random.Random(1), relics=[fresh])
    PowerCmd.apply(cs.hooks, cs.player, StrengthPower, 2, applier=cs.player)
    print(f"     combat 2 (fresh):    _used={fresh._used} "
          f"strength={cs.player.powers['strength'].amount}   "
          f"<-- the correct answer")

    print("\n  -- the doubling itself, and the once-per-combat gate")
    h2 = make_relic("ruined_helmet")
    cs = CombatState(rng=random.Random(0), relics=[h2])
    PowerCmd.apply(cs.hooks, cs.player, StrengthPower, 2, applier=cs.player)
    first = cs.player.powers["strength"].amount
    PowerCmd.apply(cs.hooks, cs.player, StrengthPower, 2, applier=cs.player)
    print(f"     first +2 -> {first} (C#: 4);  second +2 -> "
          f"{cs.player.powers['strength'].amount} (C#: 6)")

    print("\n  -- applier is NOT part of C#'s received-side guard set "
          "(RuinedHelmet.cs:32-53 checks power/target/amount/used only)")
    h3 = make_relic("ruined_helmet")
    cs = CombatState(rng=random.Random(0), relics=[h3])
    PowerCmd.apply(cs.hooks, cs.player, StrengthPower, 2, applier=None)
    print(f"     applier=None, +2 -> {cs.player.powers['strength'].amount} "
          f"(C#: 4 -- the sim agrees, no applier clause on either side)")


# ── ripple-basin ──────────────────────────────────────────────────────────
def probe_ripple_basin() -> None:
    """turn_structure G12 executed at ripple_basin's own site.

    Orichalcum's C# is deliberately two-phase: BeforeSideTurnEndVeryEarly
    snapshots `Block > 0` into ShouldTrigger (Orichalcum.cs:44-56) and plain
    BeforeSideTurnEnd then grants the 6 Block. Ripple Basin's C# hook is plain
    BeforeSideTurnEnd (RippleBasin.cs:26-34). The sim folds both onto
    on_player_turn_end, so the answer becomes listener-registration order --
    which is relic PICKUP order on RunState.relics.
    """
    from sts2_rl import CombatState
    from sts2_rl.relics import make_relic

    for order in (["ripple_basin", "orichalcum"], ["orichalcum", "ripple_basin"]):
        cs = CombatState(rng=random.Random(0),
                         relics=[make_relic(r) for r in order])
        cs.player.hand.clear()          # no attack can be played
        cs.player.block = 0
        cs.hooks.on_player_turn_end(cs.player)
        print(f"     relics={order} -> player block {cs.player.block}")
    print("     C# ALWAYS gives 10: Orichalcum's VeryEarly pass snapshots "
          "block==0 before any plain BeforeSideTurnEnd listener runs.")
    print("     Both are ported Uncommon relics in the transcribed grab bag.")


# ── ringing-triangle ──────────────────────────────────────────────────────
def probe_ringing_triangle() -> None:
    """turn_structure G4 executed at ringing_triangle's own site.

    C#'s FlushPlayerHand treats ShouldFlush == false as "every card retained"
    but still runs Hook.AfterFlush and PlayerCombatState.EndOfTurnCleanup
    (CombatManager.cs:1327-1346). The sim gates the whole call:
    `if self.hooks.should_flush_hand(): self.player.discard_hand()`
    (combat.py:661-662), and discard_hand is the ONLY caller of
    on_hand_emptied (player.py:197) -- which is the sim's Joss Paper trigger.
    """
    from sts2_rl import CombatState
    from sts2_rl.cards import make_card
    from sts2_rl.cmds import ExhaustCmd
    from sts2_rl.relics import make_relic

    print("  -- the retain itself (turn 1 keeps the hand, turn 2 does not)")
    cs = CombatState(rng=random.Random(0), relics=[make_relic("ringing_triangle")])
    print(f"     turn={cs.turn} should_flush_hand()="
          f"{cs.hooks.should_flush_hand()} hand={len(cs.player.hand)}")
    cs.end_turn()
    print(f"     turn={cs.turn} hand={len(cs.player.hand)} "
          f"should_flush_hand()={cs.hooks.should_flush_hand()}   "
          f"(C#: whole hand retained on turn 1)")

    print("\n  -- the skipped flush tail: Joss Paper's ethereal credit "
          "(on_hand_emptied has ONE caller, player.discard_hand)")
    for relics in (["joss_paper"], ["joss_paper", "ringing_triangle"]):
        cs = CombatState(rng=random.Random(0),
                         relics=[make_relic(r) for r in relics])
        joss = cs.combat_relic = next(r for r in cs.relics if r.id == "joss_paper")
        cs.player.hand.clear()
        for _ in range(5):
            eth = make_card("apparition")
            cs.player.hand.append(eth)
            ExhaustCmd.exhaust(cs.hooks, cs.player, eth)
        cs.player.hand.append(make_card("strike"))
        hand_before, draw_before = len(cs.player.hand), len(cs.player.draw_pile)
        # The sim's own turn-end flush gate, verbatim (combat.py:661-662).
        if cs.hooks.should_flush_hand():
            cs.player.discard_hand()
        print(f"     relics={relics}: 5 Ethereal exhausts -> "
              f"cards_exhausted={joss.cards_exhausted} "
              f"_ethereal_pending={joss._ethereal_pending} "
              f"hand {hand_before}->{len(cs.player.hand)} "
              f"draw_pile {draw_before}->{len(cs.player.draw_pile)}")
    print("     C# credits from AfterSideTurnEnd (JossPaper.cs:116), which "
          "fires unconditionally, so the second row should draw the card too.")


# ── royal-poison ──────────────────────────────────────────────────────────
def probe_royal_poison() -> None:
    """turn_structure G13 re-executed at royal_poison's own site."""
    from sts2_rl import CombatState
    from sts2_rl.relics import make_relic

    cs = CombatState(rng=random.Random(0), relics=[make_relic("royal_poison")],
                     max_hp=80, current_hp=4)
    print(f"     hp={cs.player.hp} is_dead={cs.player.is_dead} "
          f"phase={cs.phase} is_over={cs.is_over} "
          f"actions={len(cs.valid_actions())}")
    print("     C# runs CheckWinCondition immediately after the turn-1 setup "
          "(CombatManager.cs:573) and ends the fight there.")

    print("\n  -- the damage itself, and the turn-1 gate")
    cs = CombatState(rng=random.Random(0), relics=[make_relic("royal_poison")],
                     max_hp=80, current_hp=80)
    print(f"     turn 1: hp={cs.player.hp} (C#: 76)")
    cs.player.block = 99
    cs.end_turn()
    print(f"     turn {cs.turn}: hp={cs.player.hp} block={cs.player.block} "
          f"(C#: no further loss; Unblockable so block never applies)")


# ── regal-pillow ──────────────────────────────────────────────────────────
def probe_regal_pillow() -> None:
    """regal_pillow: the +15 has no sim hook to live in.

    RegalPillow.cs:19-26 overrides ModifyRestSiteHealAmount, dispatched by
    HealRestSiteOption.GetHealAmount (HealRestSiteOption.cs:60-63) over
    Hook.ModifyRestSiteHealAmount (Hook.cs:1936-1944). `Relic` declares no
    such method at all, and RunState.rest_site_heal_amount (run.py:307-309)
    returns `max_hp * 3 // 10` with no hook loop.
    """
    from sts2_rl.relics.base import Relic
    from sts2_rl.run import RunState

    print(f"     Relic has modify_rest_site_heal_amount: "
          f"{hasattr(Relic, 'modify_rest_site_heal_amount')}")
    for relics in ([], ["regal_pillow"]):
        run = RunState(rng=random.Random(0))
        for rid in relics:
            run.add_relic(rid)
        run.hp = 1
        base = run.rest_site_heal_amount()
        healed = run.rest_heal()
        print(f"     relics={relics}: rest_site_heal_amount()={base} "
              f"rest_heal()={healed} hp={run.hp}   "
              f"(C# with the relic: {base} + 15)")


# ── pumpkin-candle ────────────────────────────────────────────────────────
def probe_pumpkin_candle() -> None:
    """pumpkin_candle: the whole kindle lifecycle, end to end."""
    from sts2_rl.relics import make_relic
    from sts2_rl.rooms import RoomType
    from sts2_rl.run import RunState

    run = RunState(rng=random.Random(0))
    run.add_relic("pumpkin_candle")
    candle = next(r for r in run.relics if r.id == "pumpkin_candle")
    print(f"     after_obtained -> kindle_count={candle.kindle_count} (C#: 5)")

    from sts2_rl import CombatState
    for n in range(1, 8):
        cs = CombatState(rng=random.Random(n), relics=run.relics,
                         max_hp=run.max_hp, current_hp=run.hp)
        energy = cs.player.energy
        run.finish_combat(cs, room_type=RoomType.MONSTER)
        print(f"     combat {n}: turn-1 energy={energy} "
              f"-> kindle_count={candle.kindle_count}")
    print("     C#: energy 4 while KindleCount > 0, 3 once it hits 0; "
          "KindleCount = max(KindleCount-1, 0) at AfterCombatEnd.")

    opts = run.rest_site_options()
    print(f"\n     rest_site_options() -> {[o.key for o in opts]}")
    kindle = next(o for o in opts if o.key == "KINDLE")
    kindle.on_select(run)
    print(f"     after KINDLE: kindle_count={candle.kindle_count} "
          f"(C# KindleRestSiteOption.OnSelect -> Rekindle(), +5)")


# ── stub-premises ─────────────────────────────────────────────────────────
def probe_stub_premises() -> None:
    """What the three behaviourless ports in this batch actually need."""
    from sts2_rl.enchantments import ALL_ENCHANTMENTS
    from sts2_rl.relics import make_relic
    from sts2_rl.relics.base import Relic
    from sts2_rl.run import RunState

    print(f"     ported enchantments ({len(ALL_ENCHANTMENTS)}): "
          f"{sorted(ALL_ENCHANTMENTS)}")
    for name in ("momentum", "royally_approved"):
        print(f"     {name!r} ported: {name in ALL_ENCHANTMENTS}")
    print("     -> punch_dagger / royal_stamp docstrings say 'the sim has no "
          "enchantments', which is FALSE; the ENCHANTMENT MODEL each needs is "
          "what is unported.")

    print("\n     the sibling that does do it: relics/beautiful_bracelet.py:23-30 "
          "uses after_obtained + run.select_cards + Enchantment.attach")
    for rid in ("punch_dagger", "royal_stamp", "regal_pillow"):
        run = RunState(rng=random.Random(0))
        deck_before = [(c.id, c.enchantment) for c in run.deck]
        run.add_relic(rid)
        deck_after = [(c.id, c.enchantment) for c in run.deck]
        print(f"     {rid:<16} after_obtained changed the deck: "
              f"{deck_before != deck_after}")

    print("\n     royal_stamp additionally UnstableShuffles the candidate list "
          "on Rng.Niche (RoyalStamp.cs:36); the port draws nothing.")
    print(f"     Relic base has: modify_rest_site_heal_amount="
          f"{hasattr(Relic, 'modify_rest_site_heal_amount')} "
          f"after_rest_site_heal={hasattr(Relic, 'after_rest_site_heal')} "
          f"modify_card_reward_creation_options="
          f"{hasattr(Relic, 'modify_card_reward_creation_options')}")


# ── red-mask ──────────────────────────────────────────────────────────────
def probe_red_mask() -> None:
    """red_mask: which slot the Weak lands in, and which enemies get it."""
    from sts2_rl import CombatState
    from sts2_rl.relics import make_relic

    cs = CombatState(rng=random.Random(0), relics=[make_relic("red_mask")])
    print(f"     turn 1: enemy powers={sorted((p, w.amount) for p, w in cs.enemy.powers.items())} "
          f"hand={len(cs.player.hand)}")
    print("     the sim's port sits on on_player_turn_started (the post-DRAW "
          "slot, turn_structure step 23); C#'s hook is BeforeSideTurnStart "
          "(step 9, before the block clear and before PrepareForNextTurn).")

    weak_before_draw = []
    trace: list[str] = []

    class Spy:
        def on_player_turn_start(self, player):
            trace.append(f"on_player_turn_start enemy_weak="
                         f"{'weak' in player._hooks.combat.enemy.powers}")

        def modify_hand_draw(self, player, amount):
            trace.append(f"modify_hand_draw enemy_weak="
                         f"{'weak' in player._hooks.combat.enemy.powers}")
            return amount

        def on_player_turn_started(self, player):
            trace.append(f"on_player_turn_started enemy_weak="
                         f"{'weak' in player._hooks.combat.enemy.powers}")

    cs = CombatState(rng=random.Random(0), relics=[make_relic("red_mask")])
    cs.hooks.register(Spy())
    cs.player.start_turn()
    print(f"     turn-2 trace with a spy listener: {trace}")
    print(f"     (weak_before_draw={weak_before_draw})")

    print("\n     enemy set: C# uses combatState.HittableEnemies "
          "(RedMask.cs:28), the sim Relic.living_enemies() -- `not is_gone` "
          "only. Same as bag_of_marbles G2.")


# ── razor-tooth ───────────────────────────────────────────────────────────
def probe_razor_tooth() -> None:
    """razor_tooth: the upgrade is combat-local, and the guard is present."""
    from sts2_rl.cards import make_card
    from sts2_rl.relics import make_relic
    from sts2_rl.rooms import RoomType
    from sts2_rl.run import RunState

    from sts2_rl import CombatState
    run = RunState(rng=random.Random(0))
    run.add_relic("razor_tooth")
    import copy
    cs = CombatState(rng=random.Random(0), relics=run.relics,
                     starting_deck=copy.deepcopy(run.deck))
    cs.player.hand.clear()
    strike = make_card("strike")
    cs.player.hand.append(strike)
    cs.hooks.on_card_played(strike)
    print(f"     an Attack played twice: level "
          f"{strike.upgrade_level} after one play", end="")
    cs.hooks.on_card_played(strike)
    print(f", {strike.upgrade_level} after two "
          f"(max_upgrade_level={strike.max_upgrade_level})")
    run.finish_combat(cs, room_type=RoomType.MONSTER)
    print(f"     run deck upgrade levels after the combat: "
          f"{sorted({(c.id, c.upgrade_level) for c in run.deck})}")

    print("\n     the class-14 guard: C# checks IsUpgradable "
          "(RazorTooth.cs:24-27) and the port checks card.is_upgradable")
    from sts2_rl import CombatState
    cs = CombatState(rng=random.Random(0), relics=[make_relic("razor_tooth")])
    for cid in ("dazed", "burn", "strike"):
        card = make_card(cid)
        cs.hooks.on_card_played(card)
        print(f"     {cid:<8} type={card.card_type.name:<6} "
              f"max_level={card.max_upgrade_level} -> "
              f"upgrade_level={card.upgrade_level}")

    print("\n     C# has NO IsAutoPlay exclusion here (contrast "
          "BrilliantScarf.cs:84-87), so the sim counting auto-plays matches.")


# ── radiant-pearl ─────────────────────────────────────────────────────────
def probe_radiant_pearl() -> None:
    """radiant_pearl: one Luminesce into the turn-1 hand, and only turn 1."""
    from sts2_rl import CombatState
    from sts2_rl.relics import make_relic

    cs = CombatState(rng=random.Random(0), relics=[make_relic("radiant_pearl")])
    print(f"     turn 1 hand ({len(cs.player.hand)}): "
          f"{[c.id for c in cs.player.hand]}")
    print("     C#'s BeforeHandDraw adds the card BEFORE the 5-card draw "
          "(turn_structure step 19 -> the sim's on_player_turn_start, "
          "which the seam record verdicts faithful).")
    cs.end_turn()
    print(f"     turn {cs.turn} hand ({len(cs.player.hand)}): "
          f"{[c.id for c in cs.player.hand]}  -- the Luminesce is RETAINED "
          f"(cards/luminesce.py retain=True), not re-added: "
          f"luminesce count={sum(c.id == 'luminesce' for c in cs.player.hand)}")


# ── prismatic-gem ─────────────────────────────────────────────────────────
def probe_prismatic_gem() -> None:
    """prismatic_gem: +1 max Energy; the card-pool half needs a 2nd character."""
    from sts2_rl import CombatState
    from sts2_rl.relics import make_relic
    from sts2_rl.relics.base import Relic

    for relics in ([], ["prismatic_gem"]):
        cs = CombatState(rng=random.Random(0),
                         relics=[make_relic(r) for r in relics])
        print(f"     relics={relics}: ENERGY_PER_TURN="
              f"{cs.player.ENERGY_PER_TURN} modify_max_energy -> "
              f"{cs.hooks.modify_max_energy(cs.player, cs.player.ENERGY_PER_TURN)} "
              f"turn-1 energy={cs.player.energy}")
    print(f"     Relic has modify_card_reward_creation_options: "
          f"{hasattr(Relic, 'modify_card_reward_creation_options')} "
          f"(C# PrismaticGem.cs:28-52 unions every unlocked CHARACTER's card "
          f"pool into the reward options)")


# ── rainbow-ring ──────────────────────────────────────────────────────────
def probe_rainbow_ring() -> None:
    """rainbow_ring: the activation gate, auto-plays, and boundary safety."""
    from sts2_rl import CombatState
    from sts2_rl.cards import make_card
    from sts2_rl.relics import make_relic

    ring = make_relic("rainbow_ring")
    cs = CombatState(rng=random.Random(0), relics=[ring])
    for cid in ("strike", "defend", "inflame"):
        cs.hooks.on_card_played(make_card(cid))
    st = cs.player.powers.get("strength")
    dx = cs.player.powers.get("dexterity")
    print(f"     Attack+Skill+Power played: strength="
          f"{0 if st is None else st.amount} dexterity="
          f"{0 if dx is None else dx.amount} _activated={ring._activated} "
          f"(C#: 1 and 1 from the relic; the hook is fired directly "
          f"here, so Inflame's own +2 Strength is not included)")
    for cid in ("strike", "defend", "inflame"):
        cs.hooks.on_card_played(make_card(cid))
    st = cs.player.powers.get("strength")
    print(f"     a second full set the same turn: strength="
          f"{0 if st is None else st.amount} (C#: unchanged -- "
          f"ActivationCountThisTurn < 1)")

    print("\n     the dropped AfterCombatEnd reset is shadowed by the "
          "turn-start reset (art_of_war shape) -- traced to the first READER")
    print(f"     carried out of combat 1: _attack={ring._attack} "
          f"_skill={ring._skill} _power={ring._power} "
          f"_activated={ring._activated}")
    CombatState(rng=random.Random(1), relics=[ring])
    print(f"     combat 2 turn 1, after CombatState.__init__'s start_turn: "
          f"_attack={ring._attack} _skill={ring._skill} "
          f"_power={ring._power} _activated={ring._activated}")
    print("     The reset fires at combat 2's turn-1 start (combat.py's "
          "__init__ -> player.start_turn -> on_player_turn_start), and the "
          "first READER is on_card_played, which cannot run before the play "
          "phase opens. So the missing AfterCombatEnd reset is unobservable.")


# ── reptile-trinket ───────────────────────────────────────────────────────
def probe_reptile_trinket() -> None:
    """reptile_trinket: 3 temporary Strength per potion use."""
    from sts2_rl import CombatState
    from sts2_rl.relics import make_relic

    cs = CombatState(rng=random.Random(0), relics=[make_relic("reptile_trinket")])
    cs.hooks.on_potion_used(None, None)
    powers = sorted((p, w.amount) for p, w in cs.player.powers.items())
    print(f"     one potion use -> player powers={powers} "
          f"(C#: ReptileTrinketPower 3, which grants 3 Strength and reverts "
          f"it at the owner's side-turn end)")
    cs.hooks.on_potion_used(None, None)
    powers = sorted((p, w.amount) for p, w in cs.player.powers.items())
    print(f"     a second use  -> player powers={powers} (C#: stacks to 6)")
    cs.hooks.on_player_turn_end(cs.player)
    cs.hooks.after_player_turn_end(cs.player)
    powers = sorted((p, w.amount) for p, w in cs.player.powers.items())
    print(f"     after the turn end -> {powers}")
    print("     on_potion_used has ONE dispatch site, combat.py:610, so C#'s "
          "`CombatManager.Instance.IsInProgress` guard is structural.")


# ── sweep-exec-blind ──────────────────────────────────────────────────────
def probe_sweep_exec_blind() -> None:
    """Why `sweep-reset-exec` cleared three of this batch's relics.

    The executed arm of sweep A drives a DEFAULT combat -- full HP, no cards
    played, no run context -- and then diffs the two instances. Any field whose
    write is gated on a stimulus the driver never produces is identical on both
    instances and lands in the "agree with a fresh instance" bucket. That is a
    FALSE CLEAR, not evidence of safety, and it is a different blind spot from
    the FROZEN CONSTRUCTOR STATE bucket (a field nothing ever writes).
    """
    import contextlib
    import io

    from sts2_rl import CombatState
    from sts2_rl.relics import make_relic

    print("     stimulus each relic's field needs, and whether the "
          "sweep-reset-exec driver supplies it:")
    rows = [
        ("red_skull", "_applied", "player HP <= 50% of max", "no (full HP)"),
        ("ruined_helmet", "_used", "a positive StrengthPower on the player",
         "no (no cards played)"),
        ("pumpkin_candle", "kindle_count",
         "after_obtained / after_combat_end (RUN hooks)",
         "no (CombatState only)"),
    ]
    for rid, field, stimulus, supplied in rows:
        relic = make_relic(rid)
        with contextlib.redirect_stdout(io.StringIO()):
            cs1 = CombatState(rng=random.Random(0), relics=[relic])
            for _ in range(3):
                if cs1.is_over:
                    break
                cs1.end_turn()
        print(f"     {rid:<16} {field:<14} value after the sweep's own combat "
              f"1: {getattr(relic, field)!r}")
        print(f"     {'':<16} needs: {stimulus};  driver supplies it: {supplied}")
    print("\n     Consequence: sweep A's static bucket flagged all three "
          "correctly and its EXECUTED bucket cleared all three. Two of the "
          "three (red_skull, ruined_helmet) are live gaps.")


PROBES = {
    "pool": probe_pool,
    "red-skull": probe_red_skull,
    "ruined-helmet": probe_ruined_helmet,
    "ripple-basin": probe_ripple_basin,
    "ringing-triangle": probe_ringing_triangle,
    "royal-poison": probe_royal_poison,
    "regal-pillow": probe_regal_pillow,
    "pumpkin-candle": probe_pumpkin_candle,
    "stub-premises": probe_stub_premises,
    "red-mask": probe_red_mask,
    "razor-tooth": probe_razor_tooth,
    "radiant-pearl": probe_radiant_pearl,
    "prismatic-gem": probe_prismatic_gem,
    "rainbow-ring": probe_rainbow_ring,
    "reptile-trinket": probe_reptile_trinket,
    "sweep-exec-blind": probe_sweep_exec_blind,
}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("probe", nargs="*", choices=sorted(PROBES) or None,
                    help="probe(s) to run (default: all)")
    args = ap.parse_args(argv)
    for name in (args.probe or sorted(PROBES)):
        print(f"== {name} ==")
        PROBES[name]()
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
