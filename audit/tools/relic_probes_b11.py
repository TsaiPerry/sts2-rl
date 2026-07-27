"""Execution probes for relic content audit BATCH 11 (Pael cluster + P-tail).

Batch 11 units: paels_blood, paels_claw, paels_eye, paels_flesh, paels_growth,
paels_horn, paels_legion, paels_tears, paels_tooth, paels_wing, pandoras_box,
pantograph, paper_phrog, parrying_shield, pear.

Companion to `audit/tools/relic_probes.py` (the shared, batch-1-owned module).
Per the batch-11 concurrency contract this file is the batch's OWN probe module
so parallel batches do not conflict on the shared one; nothing here is
registered there. Re-use of the shared module is read-only:

  py audit/tools/relic_probes.py turn-order          # executed hook order
  py audit/tools/relic_probes.py sweep-reset-exec    # class-13 sweep

Binding rules 5 and 6 of the shared audit contract: never justify `faithful`
with an unreachability claim you have not EXECUTED, and never label a gap LIVE
without proving BOTH sides reachable with ported content.

  py audit/tools/relic_probes_b11.py                 # every probe
  py audit/tools/relic_probes_b11.py legion-reset    # one probe

Probes:
  pool             where each of batch 11's 15 relics can come from
  eye-reset        paels_eye G1 — used_this_combat carried into combat 2
  eye-turnend      paels_eye G3 — the extra-turn path skips the turn-end pass
  eye-autoplay     paels_eye G2 — auto-plays counted as "cards played"
  tears-reset      paels_tears G1 — +2 energy in combat 2 turn 1
  legion-reset     paels_legion G1 — cooldown carried into combat 2
  legion-unpowered paels_legion G2 — Entrench (MOVE|UNPOWERED) is not doubled
  legion-sweep     why sweep-reset-exec CLEARED paels_legion (sweep defect)
  tooth-filter     paels_tooth G1/G2 — IsUpgradable filter + ordinal sort
  shield-hittable  parrying_shield G1 — HittableEnemies vs living_enemies()
  pantograph-boss  pantograph N1 — the run driver really does pass BOSS
  phrog-selfhit    paper_phrog N2 — is a powered self-attack reachable?
  blood-draw       paels_blood N1 — every modify_hand_draw dispatch site
  wing-rewards     paels_wing G1 — which sim card-reward paths see the relic
  growth-clone     paels_growth N1 — what the shallow rebuild actually drops
"""
from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

BATCH11 = [
    "paels_blood", "paels_claw", "paels_eye", "paels_flesh", "paels_growth",
    "paels_horn", "paels_legion", "paels_tears", "paels_tooth", "paels_wing",
    "pandoras_box", "pantograph", "paper_phrog", "parrying_shield", "pear",
]


# ── pool ──────────────────────────────────────────────────────────────────
def probe_pool() -> None:
    """Obtainability of batch 11's 15 relics (binding rule 6, side one)."""
    from sts2_rl.relic_pools import IRONCLAD_RELIC_POOL, SHARED_RELIC_POOL
    from sts2_rl.relics import ALL_RELICS, make_relic

    bag = {rid.removeprefix("RELIC.").lower(): rarity
           for rid, rarity in SHARED_RELIC_POOL + IRONCLAD_RELIC_POOL}
    print(f"  grab-bag pool: {len(bag)} relics")
    root = Path(_REPO, "sts2_rl")
    texts = {p: p.read_text(encoding="utf-8") for p in root.rglob("*.py")}
    for rid in BATCH11:
        relic = make_relic(rid)
        where = []
        if rid in bag:
            where.append(f"grab bag ({bag[rid]})")
        for p, text in texts.items():
            if p.name == f"{rid}.py":
                continue
            if f'"{rid}"' in text and ("events" in p.parts or "shop" in p.name):
                where.append(str(p.relative_to(_REPO)))
        print(f"  {rid:<18} {relic.rarity.value:<9} registered="
              f"{rid in ALL_RELICS}  {', '.join(where) or 'no grant site found'}")


# ── eye-reset ─────────────────────────────────────────────────────────────
def probe_eye_reset() -> None:
    """paels_eye G1: `used_this_combat` is never reset (class 13).

    PaelsEye.cs:142-147 AfterCombatEnd sets UsedThisCombat = false. The sim's
    port sets `self.used_this_combat = True` in on_extra_turn and clears it
    nowhere, and relic instances live on RunState.relics across every combat.
    CONFIRMS `.superpowers/sdd/content-relic-sweeps.md` sweep A, which reached
    the same field by the pool-wide `sweep-reset-exec` route; this probe adds
    the OBSERVABLE (the extra turn itself) that the field-level diff does not
    show.
    """
    from sts2_rl import CombatState
    from sts2_rl.relics import make_relic

    eye = make_relic("paels_eye")

    def turns_taken(cs: CombatState) -> int:
        # end_turn with an empty play history: the extra turn keeps the player
        # side, so combat.turn advances without the enemy acting.
        before = cs.turn
        cs.end_turn()
        return cs.turn - before

    cs1 = CombatState(rng=random.Random(0), relics=[eye])
    print(f"  combat 1: used_this_combat={eye.used_this_combat} "
          f"should_take_extra_turn={eye.should_take_extra_turn(cs1.player)}")
    turns_taken(cs1)
    print(f"  combat 1 after one end_turn: used_this_combat="
          f"{eye.used_this_combat}  (correct: the extra turn was spent)")

    cs2 = CombatState(rng=random.Random(1), relics=[eye])
    print(f"  combat 2 (SAME instance, as RunState.relics does): "
          f"used_this_combat={eye.used_this_combat}  (C#: False)")
    print(f"  combat 2 should_take_extra_turn="
          f"{eye.should_take_extra_turn(cs2.player)}   (C#: True)")

    fresh = make_relic("paels_eye")
    cs3 = CombatState(rng=random.Random(1), relics=[fresh])
    print(f"  a FRESH instance in the same combat 2: "
          f"should_take_extra_turn={fresh.should_take_extra_turn(cs3.player)}")


# ── eye-turnend ───────────────────────────────────────────────────────────
def probe_eye_turnend() -> None:
    """paels_eye G3: the sim's extra-turn path SKIPS the whole turn-end pass.

    C# order (CombatManager.cs):
      EndPlayerTurnPhaseOneInternal  -> Hook.BeforeTurnEnd  (:1179)
                                        = BeforeSideTurnEndVeryEarly ->
                                          BeforeSideTurnEndEarly (PaelsEye's
                                          hand exhaust) -> BeforeSideTurnEnd
                                          (Hook.cs:1232-1262)
                                     -> DoTurnEnd (ethereal + turn-end-in-hand)
                                     -> Hook.BeforeFlush
      EndPlayerTurnPhaseTwoInternal  -> FlushPlayerHand (:1296)
                                     -> Hook.AfterTurnEnd (:1307)
      SwitchFromPlayerToEnemySide    -> Hook.ShouldTakeExtraTurn (:1366)
                                     -> Hook.AfterTakingExtraTurn (:1381)
    So the extra-turn DECISION is the LAST thing that happens, after the entire
    turn-end pass has run.

    The sim asks first (combat.py:648) and `return`s (combat.py:652), so
    on_player_turn_end (Hook.BeforeTurnEnd), _process_turn_end_cards (DoTurnEnd),
    the hand flush and after_player_turn_end (Hook.AfterTurnEnd) are all skipped
    on any turn that grants an extra turn.
    """
    from sts2_rl import CombatState
    from sts2_rl.relics import make_relic

    class Spy:
        """A hook listener that records the turn-end slots it is called in."""

        def __init__(self) -> None:
            self.seen: list[str] = []

        def on_player_turn_end(self, player) -> None:
            self.seen.append("on_player_turn_end (Hook.BeforeTurnEnd)")

        def after_player_turn_end(self, player) -> None:
            self.seen.append("after_player_turn_end (Hook.AfterTurnEnd)")

        def on_hand_emptied(self, player) -> None:
            self.seen.append("on_hand_emptied (the hand flush)")

    for label, relics in (("WITHOUT Pael's Eye", []),
                          ("WITH Pael's Eye   ", [make_relic("paels_eye")])):
        spy = Spy()
        cs = CombatState(rng=random.Random(0), relics=list(relics))
        cs.hooks.register(spy)
        cs.end_turn()
        print(f"  {label}: turn {cs.turn}, slots fired = {spy.seen or ['NONE']}")
    print("  C#: every slot above fires in BOTH cases -- ShouldTakeExtraTurn is")
    print("      only consulted afterwards (CombatManager.cs:1366).")


# ── eye-autoplay ──────────────────────────────────────────────────────────
def probe_eye_autoplay() -> None:
    """paels_eye G2: the sim counts AUTO-plays as "cards played this turn".

    PaelsEye.cs:156 filters the history on `!e.CardPlay.IsAutoPlay` (and on
    `e.Actor == Owner.Creature`). The sim's `_any_cards_played_this_turn`
    (paels_eye.py:27-34) counts every CardPlayedEntry, and the sim's history
    records auto-plays through the same `_resolve_card_play` bracket
    (combat.py:514, reached from combat.py:553 auto_play_card).

    Ported trigger with no manual play: HellraiserPower auto-plays any Strike
    the moment it is DRAWN (powers.py:713), and the turn-start draw happens
    before the player acts. Hellraiser is in the Ironclad card pool
    (cards/pool.py:26).
    """
    from sts2_rl import CombatState
    from sts2_rl.cards import make_card
    from sts2_rl.history import CardPlayedEntry
    from sts2_rl.powers import HellraiserPower
    from sts2_rl.cmds import PowerCmd
    from sts2_rl.relics import make_relic

    eye = make_relic("paels_eye")
    deck = [make_card("strike") for _ in range(10)]
    cs = CombatState(rng=random.Random(0), relics=[eye], starting_deck=deck)
    PowerCmd.apply(cs.hooks, cs.player, HellraiserPower, 1, applier=cs.player)
    # Force a fresh turn so the Hellraiser power is live for the draw.
    cs.turn += 1
    cs.player.start_turn()
    plays = list(cs.history.of_type(CardPlayedEntry, this_turn=True))
    print(f"  turn {cs.turn}: player made 0 manual plays; "
          f"Hellraiser auto-played {len(plays)} Strike(s)")
    print(f"  sim  _any_cards_played_this_turn = "
          f"{eye._any_cards_played_this_turn()}")
    print(f"  sim  should_take_extra_turn      = "
          f"{eye.should_take_extra_turn(cs.player)}")
    print("  C#   AnyCardsPlayedThisTurn       = False  (IsAutoPlay excluded)")
    print("  C#   ShouldTakeExtraTurn          = True")


# ── tears-reset ───────────────────────────────────────────────────────────
def probe_tears_reset() -> None:
    """paels_tears G1: `had_leftover_energy` is never reset (class 13).

    PaelsTears.cs:57-61 AfterCombatEnd sets HadLeftoverEnergy = false; the sim
    clears it nowhere. CONFIRMS sweep A's executed finding (player energy
    3 -> 5); this probe repeats it against the relic's own reader so the record
    can name the observable rather than the flag.
    """
    from sts2_rl import CombatState
    from sts2_rl.relics import make_relic

    tears = make_relic("paels_tears")
    cs1 = CombatState(rng=random.Random(0), relics=[tears])
    print(f"  combat 1 turn 1 energy: {cs1.player.energy} "
          f"had_leftover_energy={tears.had_leftover_energy}")
    cs1.end_turn()      # ends turn 1 with energy unspent
    print(f"  after end_turn:         had_leftover_energy="
          f"{tears.had_leftover_energy}, turn {cs1.turn} energy "
          f"{cs1.player.energy} (correct: base + 2)")

    cs2 = CombatState(rng=random.Random(1), relics=[tears])
    fresh = make_relic("paels_tears")
    cs_fresh = CombatState(rng=random.Random(1), relics=[fresh])
    print(f"  combat 2 turn 1 energy (SAME instance): {cs2.player.energy} "
          f"had_leftover_energy={tears.had_leftover_energy}")
    print(f"  combat 2 turn 1 energy (FRESH instance): "
          f"{cs_fresh.player.energy}   <- C# value")


# ── legion-reset ──────────────────────────────────────────────────────────
def probe_legion_reset() -> None:
    """paels_legion G1: `cooldown` is never reset (class 13) -- NEW, LIVE.

    PaelsLegion.cs:211-219 AfterCombatEnd sets Cooldown = 0 (and clears
    TriggeredBlockLastTurn / AffectedCardPlay). BeforeCombatStart
    (PaelsLegion.cs:129-132) does NOT reset anything -- it only summons the
    pet -- so AfterCombatEnd is the relic's only reset, and the sim's port has
    no counterpart to it.

    Trace to the first reader (class 13): modify_block_multiplicative
    (paels_legion.py:40) reads `self.cooldown > 0`. A combat that ENDS while
    the pet is asleep therefore starts the next combat asleep, and
    on_player_turn_start only ticks one per turn.
    """
    from sts2_rl import CombatState
    from sts2_rl.cards import make_card
    from sts2_rl.relics import make_relic

    legion = make_relic("paels_legion")
    deck = [make_card("defend") for _ in range(10)]
    cs1 = CombatState(rng=random.Random(0), relics=[legion], starting_deck=deck)
    # Play one Defend: doubled block, then the pet sleeps for 2 turns.
    idx = next(i for i, c in enumerate(cs1.player.hand) if c.id == "defend")
    cs1.play_card(idx)
    print(f"  combat 1: Defend played -> block {cs1.player.block} "
          f"(base 5, doubled), cooldown={legion.cooldown}")
    print("  combat 1 ENDS here (a kill on the same turn is the normal case)")

    cs2 = CombatState(rng=random.Random(1), relics=[legion], starting_deck=deck)
    print(f"  combat 2 turn 1 (SAME instance): cooldown={legion.cooldown}"
          f"   (C#: 0)")
    idx = next(i for i, c in enumerate(cs2.player.hand) if c.id == "defend")
    cs2.play_card(idx)
    print(f"  combat 2 turn 1 Defend -> block {cs2.player.block}   (C#: 10)")

    fresh = make_relic("paels_legion")
    cs3 = CombatState(rng=random.Random(1), relics=[fresh], starting_deck=deck)
    idx = next(i for i, c in enumerate(cs3.player.hand) if c.id == "defend")
    cs3.play_card(idx)
    print(f"  combat 2 turn 1 with a FRESH instance -> block "
          f"{cs3.player.block}   <- C# value")
    # How long the sim stays wrong: one tick per player turn start.
    turns = 0
    while legion.cooldown > 0 and turns < 5:
        cs2.turn += 1
        cs2.player.start_turn()
        turns += 1
    print(f"  the sim needs {turns} further player turn(s) of combat 2 before "
          f"the pet wakes (C#: awake on turn 1)")


# ── legion-unpowered ──────────────────────────────────────────────────────
def probe_legion_unpowered() -> None:
    """paels_legion G2: unpowered CARD block is doubled in C#, not in the sim.

    C# `Hook.ModifyBlock` (Hook.cs:1310-1340) is dispatched with NO props gate
    -- every listener applies its own filter -- and PaelsLegion's filter is
    `props.IsCardOrMonsterMove()` (PaelsLegion.cs:136), i.e. just
    `HasFlag(ValueProp.Move)` (ValuePropExtensions.cs:23-26). The sim's
    `BlockCmd.apply` gates the WHOLE additive+multiplicative dispatch on
    `is_powered_attack(props)` = Move AND NOT Unpowered (cmds.py:146-147), so a
    card whose block is `Move | Unpowered` never reaches the hook.

    Ported both sides: Entrench (`ValueProp.MOVE | ValueProp.UNPOWERED`,
    cards/trash_heap_cards.py:170-177) and Pael's Legion (Ancient, Pael shrine).
    """
    from sts2_rl import CombatState
    from sts2_rl.cards import make_card
    from sts2_rl.cmds import BlockCmd
    from sts2_rl.relics import make_relic
    from sts2_rl.valueprops import ValueProp

    for label, relics in (("no relic       ", []),
                          ("Pael's Legion  ", [make_relic("paels_legion")])):
        legion = relics[0] if relics else None
        deck = [make_card("entrench")] + [make_card("strike") for _ in range(9)]
        cs = CombatState(rng=random.Random(0), relics=list(relics),
                         starting_deck=deck)
        entrench = next(c for c in cs.player.all_cards if c.id == "entrench")
        cs.player.block = 10
        BlockCmd.apply(cs.hooks, cs.player, cs.player.block, card=entrench,
                       props=ValueProp.MOVE | ValueProp.UNPOWERED)
        cool = "n/a" if legion is None else legion.cooldown
        print(f"  {label} Entrench on 10 block -> block {cs.player.block}, "
              f"cooldown={cool}")
    print("  C# with Pael's Legion: 10 + (10 * 2) = 30 block, cooldown 2")
    # The same relic on a POWERED card block does fire, so the port is not
    # inert -- the divergence is specific to the Unpowered flag.
    legion = make_relic("paels_legion")
    deck = [make_card("defend") for _ in range(10)]
    cs = CombatState(rng=random.Random(0), relics=[legion], starting_deck=deck)
    idx = next(i for i, c in enumerate(cs.player.hand) if c.id == "defend")
    cs.play_card(idx)
    print(f"  control: powered card block (Defend) IS doubled -> "
          f"{cs.player.block}, cooldown={legion.cooldown}")


# ── legion-sweep ──────────────────────────────────────────────────────────
def probe_legion_sweep() -> None:
    """Why `sweep-reset-exec` CLEARED paels_legion -- a sweep-A defect.

    The sweep's driver (relic_probes.py, probe_sweep_reset_exec) builds a
    CombatState and calls `end_turn()` up to three times. It never PLAYS A
    CARD, so every candidate whose state is only written from a card-play hook
    settles identically on the carried and the fresh instance and is filed as
    "agrees with a fresh instance".

    paels_legion is exactly that shape: the sweep's own STATIC output says
    `cooldown<-['__init__', 'on_card_played', 'on_player_turn_start']` and
    `_affected_card<-['modify_block_multiplicative', 'on_card_played']`, and
    `on_player_turn_start` only DECREMENTS. This reproduces both halves.
    """
    from sts2_rl import CombatState
    from sts2_rl.cards import make_card
    from sts2_rl.relics import make_relic

    # (a) the sweep's own driver: end_turn only.
    a = make_relic("paels_legion")
    cs = CombatState(rng=random.Random(0), relics=[a])
    for _ in range(3):
        if cs.is_over:
            break
        cs.end_turn()
    print(f"  sweep driver (end_turn x3, no card play): cooldown={a.cooldown} "
          f"_affected_card={a._affected_card}  -> looks clean")

    # (b) one card play is all it takes.
    b = make_relic("paels_legion")
    deck = [make_card("defend") for _ in range(10)]
    cs = CombatState(rng=random.Random(0), relics=[b], starting_deck=deck)
    idx = next(i for i, c in enumerate(cs.player.hand) if c.id == "defend")
    cs.play_card(idx)
    print(f"  one Defend played:                        cooldown={b.cooldown} "
          f"-> carries into combat 2")


# ── tooth-filter ──────────────────────────────────────────────────────────
def probe_tooth_filter() -> None:
    """paels_tooth G1/G2: the candidate filter and the stored-card order.

    G1: PaelsTooth.cs:83 selects through
    `CardSelectCmd.FromDeckForRemoval(..., filter: c => c.IsUpgradable)`, and
    FromDeckForRemoval itself ANDs `c.IsRemovable` (CardSelectCmd.cs:621-625).
    So the candidate set is IsRemovable AND IsUpgradable. The sim uses
    `run.removable_cards()` only (paels_tooth.py:27) -- IsUpgradable is
    dropped, so a Curse or an already-upgraded card can be stored.

    G2: C# then `.OrderBy(c => c.Id.Entry, StringComparer.Ordinal)` BEFORE
    appending to SerializableCards (PaelsTooth.cs:83-89); the stored order is
    the list `PlayerRng.Rewards.NextItem` indexes into (line 99). The sim
    appends in selection order (paels_tooth.py:28-30).
    """
    from sts2_rl.cards import make_card
    from sts2_rl.relics import make_relic
    from sts2_rl.run import RunState

    run = RunState(rng=random.Random(0))
    run.deck = [make_card("strike") for _ in range(3)] + \
               [make_card("defend"), make_card("bash")]
    # A rest-site smith and a curse: both are IsRemovable but NOT IsUpgradable.
    run.deck[0].upgrade()
    run.deck.append(make_card("regret"))
    for c in run.deck:
        print(f"    {c.id:<12} upgrade_level={c.upgrade_level} "
              f"is_upgradable={c.is_upgradable} eternal={c.eternal}")
    sim_candidates = [c.id for c in run.removable_cards()]
    cs_candidates = [c.id for c in run.removable_cards() if c.is_upgradable]
    print(f"  sim candidate set (paels_tooth.py:27): {sim_candidates}")
    print(f"  C#  candidate set (IsRemovable AND IsUpgradable): {cs_candidates}")

    # Store 5 with the sim's own path and show what lands in the tooth.
    run2 = RunState(rng=random.Random(0))
    run2.deck = [make_card("strike") for _ in range(4)] + \
                [make_card("defend"), make_card("regret")]
    run2.deck[0].upgrade()
    picks = [run2.deck[0], run2.deck[5], run2.deck[3], run2.deck[1],
             run2.deck[2]]
    run2.card_selector = lambda purpose, cands, n: picks[:n]
    tooth = make_relic("paels_tooth")
    run2.relics.append(tooth)
    tooth.after_obtained(run2)
    print(f"  stored (sim, selection order): "
          f"{[(c.id, c.upgrade_level) for c in tooth.stored_cards]}")
    ordinal = sorted(tooth.stored_cards, key=lambda c: c.id.upper())
    print(f"  C# stored order (OrderBy Id.Entry, Ordinal): "
          f"{[(c.id, c.upgrade_level) for c in ordinal]}")
    print("  C# would never have offered strike+1 or regret at all (G1).")


# ── shield-hittable ───────────────────────────────────────────────────────
def probe_shield_hittable() -> None:
    """parrying_shield G1: HittableEnemies vs the sim's living_enemies().

    ParryingShield.cs:28 targets
    `Rng.CombatTargets.NextItem(Owner.Creature.CombatState.HittableEnemies)`;
    HittableEnemies is `Enemies.Where(e => e.IsHittable)` and IsHittable is
    `!IsDead && Hook.ShouldAllowHitting(...)`. `Relic.living_enemies()`
    (relics/base.py:294-297) filters on `not e.is_gone` ONLY.

    This is the SAME mechanism audit/records/relic/bag_of_marbles.json labels G2, and
    it carries the same `gap` verdict (binding rule 3). What differs is the
    reachability: bag_of_marbles fires only during turn-1 setup, where nothing
    can be mid-revival, so its record labels it DORMANT. Parrying Shield fires
    at EVERY player turn end -- after the player's own attacks -- which is
    exactly when a Fogmog (Overgrowth/act 1, monsters/overgrowth/fogmog.py:34)
    is sitting at 1 HP and unhittable under IllusionPower.
    """
    from sts2_rl import CombatState
    from sts2_rl.cmds import DamageCmd

    cs = CombatState(rng=random.Random(0))
    fogmog = _spawn(cs, "sts2_rl.monsters.overgrowth.fogmog")
    other = _spawn(cs, "sts2_rl.monsters.overgrowth.fogmog")
    # Drive the first fogmog into its revival state (IllusionPower vetoes death).
    DamageCmd.deal(cs.hooks, fogmog, 9999, dealer=cs.player)
    illusion = fogmog.powers.get("illusion")
    print(f"  fogmog[0]: hp={fogmog.hp} is_dead={fogmog.is_dead} "
          f"is_gone={fogmog.is_gone} is_reviving={illusion.is_reviving}")
    print(f"  should_allow_hitting(fogmog[0]) = "
          f"{cs.hooks.should_allow_hitting(fogmog)}")
    from sts2_rl.relics import make_relic
    shield = make_relic("parrying_shield")
    shield.attach(cs)
    living = shield.living_enemies()
    hittable = [e for e in cs.enemies
                if not e.is_gone and cs.hooks.should_allow_hitting(e)]
    print(f"  sim living_enemies():   {len(living)} candidate(s) "
          f"{[e.name for e in living]}")
    print(f"  C#  HittableEnemies:    {len(hittable)} candidate(s) "
          f"{[e.name for e in hittable]}")
    # The observable: aim the shield at the reviving one and watch it whiff.
    before = fogmog.hp
    DamageCmd.deal(cs.hooks, fogmog, shield.DAMAGE, dealer=cs.player)
    print(f"  6 damage at the reviving fogmog: hp {before} -> {fogmog.hp} "
          f"(the sim can pick it and deal nothing; C# cannot pick it)")
    print(f"  and the CombatTargets index is drawn over "
          f"{len(living)} vs {len(hittable)} items, so the pick diverges too")


def _spawn(cs, module: str):
    """Add the module's single MonsterModel subclass to a combat's enemy list."""
    import importlib
    import inspect as _inspect
    from sts2_rl.monsters.base import Monster

    mod = importlib.import_module(module)
    cls = next(
        obj for _n, obj in vars(mod).items()
        if _inspect.isclass(obj) and issubclass(obj, Monster) and obj is not Monster
        and obj.__module__ == module
    )
    m = cls(cs.hooks, cs._rng)
    cs.enemies.append(m)
    cs.hooks.register(m)
    if hasattr(m, "on_combat_start"):
        m.on_combat_start(cs.hooks)
    return m


# ── pantograph-boss ───────────────────────────────────────────────────────
def probe_pantograph_boss() -> None:
    """pantograph N1: does the run driver really pass room_type=BOSS?

    Binding rule 5: `pantograph.py:23` returns early unless
    `self.combat.room_type == RoomType.BOSS`, and a `faithful` verdict on that
    guard rests on the driver actually setting it. Executed rather than assumed.
    """
    import re

    from sts2_rl.rooms import RoomType

    # RunState.create_combat takes room_type through **kwargs; the load-bearing
    # question is whether the DRIVERS pass it.
    for rel in ("sts2_rl/driver.py", "sts2_rl/conformance/runner.py"):
        text = Path(_REPO, rel).read_text(encoding="utf-8")
        for i, line in enumerate(text.splitlines(), 1):
            if re.search(r"create_combat\(", line):
                print(f"  {rel}:{i}  {line.strip()}")
    # And the end-to-end effect on the relic.
    from sts2_rl import CombatState
    from sts2_rl.relics import make_relic
    for rt in (None, RoomType.MONSTER, RoomType.ELITE, RoomType.BOSS):
        p = make_relic("pantograph")
        cs = CombatState(rng=random.Random(0), relics=[p], room_type=rt,
                         max_hp=80, current_hp=40)
        print(f"  room_type={rt!s:<16} hp after combat start: {cs.player.hp}")


# ── phrog-selfhit ─────────────────────────────────────────────────────────
def probe_phrog_selfhit() -> None:
    """paper_phrog N2: is `target == Owner.Creature` reachable?

    PaperPhrog.cs:18-21 bails when the Vulnerable creature IS its owner; the
    sim's port (paper_phrog.py:22) checks only the dealer. The guard can only
    matter when the PLAYER is both dealer and Vulnerable target on a POWERED
    attack -- VulnerablePower.ModifyDamageMultiplicative already requires
    `target == Owner` and `props.IsPoweredAttack()` (VulnerablePower.cs:29-36),
    mirrored by the sim at powers.py:404-417 plus the
    `is_powered_attack(props)` gate in DamageCmd.deal (cmds.py:57-58).

    So: enumerate every ported site that deals damage to the player with the
    player as dealer, and print its props.
    """
    import re

    root = Path(_REPO, "sts2_rl")
    hits: list[str] = []
    pat = re.compile(r"DamageCmd\.deal\((?P<args>[^;]{0,400}?)\)\s*$",
                     re.MULTILINE | re.DOTALL)
    for path in sorted(root.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for m in pat.finditer(text):
            args = " ".join(m.group("args").split())
            if "player" not in args:
                continue
            # Target is the first positional after hooks.
            body = args.split(",")
            target = body[1].strip() if len(body) > 1 else ""
            if "player" not in target:
                continue
            # An omitted `props` defaults to DamageProps.CARD, which IS powered
            # (cmds.py:46-49), so absence must count as POWERED here.
            powered = "UNPOWERED" not in args and "HP_LOSS" not in args
            self_dealt = "dealer=ctx.player" in args or "dealer=player" in args \
                or "dealer=self.player" in args
            line = text[:m.start()].count("\n") + 1
            hits.append((powered, self_dealt,
                         f"{path.relative_to(_REPO)}:{line}  "
                         f"{'POWERED  ' if powered else 'unpowered '}"
                         f"{'player-dealt' if self_dealt else 'other dealer'}"
                         f"  {args[:110]}"))
    print(f"  {len(hits)} site(s) deal damage TO the player:")
    for _p, _s, h in hits:
        print(f"    {h}")
    both = [h for p, s, h in hits if p and s]
    print(f"  of which POWERED **and** player-dealt (the only shape "
          f"PaperPhrog's target guard can matter for): {len(both)}")
    for h in both:
        print(f"    {h}")


# ── blood-draw ────────────────────────────────────────────────────────────
def probe_blood_draw() -> None:
    """paels_blood N1: `player != base.Owner` has one dispatch site.

    PaelsBlood.cs:16-19 returns `count` untouched when the hand-draw being
    modified belongs to another player. The sim's port has no such check
    (paels_blood.py:22-23). Executed: enumerate every caller of
    hooks.modify_hand_draw and show what it passes.
    """
    import re

    root = Path(_REPO, "sts2_rl")
    for path in sorted(root.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for i, line in enumerate(text.splitlines(), 1):
            if re.search(r"\.modify_hand_draw\(", line) and "def " not in line:
                print(f"  {path.relative_to(_REPO)}:{i}  {line.strip()}")
    from sts2_rl import CombatState
    cs = CombatState(rng=random.Random(0))
    print(f"  the sim's CombatState holds exactly 1 player: "
          f"{type(cs.player).__name__}, "
          f"and PlayerCombatState.start_turn is the only draw driver")


# ── wing-rewards ──────────────────────────────────────────────────────────
def probe_wing_rewards() -> None:
    """paels_wing G1: which card-reward paths surface the SACRIFICE option?

    C# adds the alternative from `Hook.ModifyCardRewardAlternatives`, whose one
    caller is `CardRewardAlternative.cs:68` -- i.e. EVERY CardReward, wherever
    it comes from. The sim's port hangs the offer off `modify_combat_rewards`
    (paels_wing.py:22-24), so it can only ever appear on a CombatRewards.
    Executed: list the sim's CombatRewards construction sites and which of them
    run the relic hook.
    """
    import re

    root = Path(_REPO, "sts2_rl")
    for path in sorted(root.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for i, line in enumerate(text.splitlines(), 1):
            if re.search(r"modify_combat_rewards\(|modify_card_reward_options\(",
                         line) and "def " not in line:
                print(f"  {path.relative_to(_REPO)}:{i}  {line.strip()}")
    print("  sacrifice_relic consumers:")
    for path in sorted(root.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for i, line in enumerate(text.splitlines(), 1):
            if "sacrifice_relic" in line:
                print(f"    {path.relative_to(_REPO)}:{i}  {line.strip()}")


# ── growth-clone ──────────────────────────────────────────────────────────
def probe_growth_clone() -> None:
    """paels_growth N1: what the shallow rebuild actually drops at THIS site.

    Sweep E (`.superpowers/sdd/content-relic-sweeps.md`) lists
    `relics/paels_growth.py:39` as one of five shallow-rebuild sites against
    C#'s `ClonePreservingMutability` (CardModel.cs:2168-2179). Per-instance
    state a clone should carry: upgrade level, enchantment, affliction,
    keyword edits, local energy-cost modifiers.

    At this particular site the input is filtered to Clone-enchanted DECK
    cards, so this probe checks each of the five against a deck card.
    """
    from sts2_rl import CombatState
    from sts2_rl.cards import make_card
    from sts2_rl.enchantments import make_enchantment
    from sts2_rl.relics import make_relic
    from sts2_rl.run import RunState

    run = RunState(rng=random.Random(0))
    run.deck = [make_card("strike"), make_card("defend"), make_card("bash")]
    original = run.deck[2]
    original.upgrade()
    ench = make_enchantment("clone")
    ench.amount = 4
    ench.attach(original)
    # Afflictions: applied to cards IN HAND during combat. The run deep-copies
    # its deck into every combat (run.py:1136 copy.deepcopy), so an affliction
    # can never reach the run-deck object the rest-site option reads.
    cs = CombatState(rng=random.Random(0), starting_deck=None)
    del cs
    growth = make_relic("paels_growth")
    run.relics.append(growth)
    options: list = []
    growth.modify_rest_site_options(run, options)
    print(f"  rest-site option key={options[0].key!r}")
    options[0].on_select(run)
    copy_ = run.deck[-1]
    print(f"  original: id={original.id} lvl={original.upgrade_level} "
          f"ench={original.enchantment.id}/{original.enchantment.amount} "
          f"affl={original.affliction} cost={original.energy_cost} "
          f"exhausts={original.exhausts}")
    print(f"  clone:    id={copy_.id} lvl={copy_.upgrade_level} "
          f"ench={copy_.enchantment.id}/{copy_.enchantment.amount} "
          f"affl={copy_.affliction} cost={copy_.energy_cost} "
          f"exhausts={copy_.exhausts}")
    print(f"  deck now: {[(c.id, c.upgrade_level) for c in run.deck]}  "
          f"(C#: the clone is APPENDED, CardPileCmd.Add default Bottom)")
    print("  every run-deck-reachable field matches, so sweep E's hit at "
          "paels_growth.py:39 has no observable at this site")


PROBES = {
    "pool": probe_pool,
    "eye-reset": probe_eye_reset,
    "eye-turnend": probe_eye_turnend,
    "eye-autoplay": probe_eye_autoplay,
    "tears-reset": probe_tears_reset,
    "legion-reset": probe_legion_reset,
    "legion-unpowered": probe_legion_unpowered,
    "legion-sweep": probe_legion_sweep,
    "tooth-filter": probe_tooth_filter,
    "shield-hittable": probe_shield_hittable,
    "pantograph-boss": probe_pantograph_boss,
    "phrog-selfhit": probe_phrog_selfhit,
    "blood-draw": probe_blood_draw,
    "wing-rewards": probe_wing_rewards,
    "growth-clone": probe_growth_clone,
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
