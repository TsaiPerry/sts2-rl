"""Execution probes for relic audit batch 5 (the 15 `e*`/`fake_*`/`festive_*`
relics). Companion to `audit/tools/relic_probes.py`, which this module does NOT
modify (batches 4-8 run in parallel worktrees and share that file read-only).

Batch 5 is the only batch with no pre-diagnosed units, so every reachability
claim in `audit/records/relic/{electric_shrymp,ember_tea,empty_cage,eternal_feather,
fake_*,festive_popper}.json` is produced here rather than argued. Binding rules
5 and 6 of the shared audit contract: never justify `faithful` with an
unreachability claim you have not EXECUTED, and never label a gap LIVE without
proving both sides reachable with ported content.

  py audit/tools/relic_probes_b05.py                # every probe
  py audit/tools/relic_probes_b05.py b05-pool       # one probe

Probes:
  b05-pool          obtainability of all 15 batch-5 relics
  tea-set-rest      fake_venerable_tea_set G1 — nothing ever sets `_pending`
  injected-state    the same shape swept across all 258 relic ports
  orichalcum-order  fake_orichalcum G1 — the VeryEarly snapshot is collapsed
  strike-dummy      fake_strike_dummy — the IsPoweredAttack + dealer guards
  popper-win        festive_popper — the hand-rolled _check_win and its slot
  waffle-round      fake_lees_waffle — decimal-vs-int heal, exhaustively
  mango-hp          fake_mango — GainMaxHp's implicit heal
  shrymp-imbued     electric_shrymp — Imbued candidate filter + turn-1 draw
  ember-order       ember_tea — AfterRoomEntered runs BEFORE BeforeCombatStart
  flower-blood      fake_happy_flower / fake_blood_vial turn arithmetic
  cage-feather      empty_cage / eternal_feather out-of-combat effects
  snecko-confused   fake_snecko_eye — Confused amount, applier, mid-combat pickup
  anchor-window     fake_anchor — the block-clear slot vs BeforeCombatStart
"""
from __future__ import annotations

import argparse
import ast
import random
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

BATCH5 = [
    "electric_shrymp", "ember_tea", "empty_cage", "eternal_feather",
    "fake_anchor", "fake_blood_vial", "fake_happy_flower", "fake_lees_waffle",
    "fake_mango", "fake_merchants_rug", "fake_orichalcum", "fake_snecko_eye",
    "fake_strike_dummy", "fake_venerable_tea_set", "festive_popper",
]


# ── b05-pool ──────────────────────────────────────────────────────────────
def probe_b05_pool() -> None:
    """Where each batch-5 relic can come from (rule 6's "relic obtainable")."""
    from sts2_rl.relic_pools import IRONCLAD_RELIC_POOL, SHARED_RELIC_POOL
    from sts2_rl.relics import ALL_RELICS

    bag = {rid.removeprefix("RELIC.").lower(): rarity
           for rid, rarity in SHARED_RELIC_POOL + IRONCLAD_RELIC_POOL}
    print(f"grab-bag pool: {len(bag)} relics")
    for rid in BATCH5:
        srcs = subprocess.run(
            ["git", "grep", "-l", f'"{rid}"', "--", "sts2_rl"],
            capture_output=True, text=True, cwd=_REPO,
        ).stdout.split()
        srcs = [s for s in srcs if not s.endswith(f"relics/{rid}.py")]
        print(f"  {rid:<24} registered={rid in ALL_RELICS} "
              f"bag={bag.get(rid, '-'):<9} granted_by={srcs or ['(none)']}")


# ── tea-set-rest ──────────────────────────────────────────────────────────
def probe_tea_set_rest() -> None:
    """fake_venerable_tea_set: the rest-site latch has no sim counterpart.

    FakeVenerableTeaSet.cs:43-51 sets GainEnergyInNextCombat in
    AfterRoomEntered(RestSiteRoom); AfterEnergyReset then spends it. The sim's
    port implements only the spend half and takes `rested` through __init__,
    which nothing in the run flow ever passes.
    """
    from sts2_rl import CombatState
    from sts2_rl.relics import make_relic
    from sts2_rl.rooms import RoomType
    from sts2_rl.run import RunState

    relic = make_relic("fake_venerable_tea_set")
    print(f"  make_relic(...)._pending                = {relic._pending}")
    print(f"  has after_room_entered override          = "
          f"{'after_room_entered' in type(relic).__dict__}")

    run = RunState(rng=random.Random(0))
    r = run.add_relic("fake_venerable_tea_set")
    # The exact dispatch run.py:982-983 performs on entering any room.
    r.after_room_entered(run, None, RoomType.REST_SITE)
    print(f"  after a REST_SITE after_room_entered     = _pending={r._pending}"
          f"   (C#: GainEnergyInNextCombat=True)")
    cs = CombatState(rng=random.Random(0), relics=[r])
    print(f"  turn-1 energy in the next combat         = {cs.player.energy}"
          f"   (base {cs.player.ENERGY_PER_TURN}; C#: {cs.player.ENERGY_PER_TURN + 1})")

    forced = make_relic("fake_venerable_tea_set")
    forced._pending = True
    cs2 = CombatState(rng=random.Random(0), relics=[forced])
    print(f"  with _pending forced True                = {cs2.player.energy}"
          f"   -- the spend half works, only the latch is missing")


# ── injected-state ────────────────────────────────────────────────────────
def probe_injected_state() -> None:
    """Pool-wide: relic ports whose out-of-combat state is a constructor
    argument, and whether anything in sts2_rl/ ever supplies it.

    `fake_venerable_tea_set` (batch 5) is the founding example. The shape is
    NOT the belt_buckle missing-reset shape sweep-reset chases: the field is
    never *set* in the first place, so a field-diff across two combats sees
    nothing wrong.
    """
    import inspect

    from sts2_rl.relics import ALL_RELICS

    rows = []
    for rid, cls in sorted(ALL_RELICS.items()):
        init = cls.__dict__.get("__init__")
        if init is None:
            continue
        params = [p for p in inspect.signature(init).parameters
                  if p != "self"]
        if not params:
            continue
        # Does anything outside the relic's own module construct it with args?
        hits = subprocess.run(
            ["git", "grep", "-n", f"{cls.__name__}(", "--", "sts2_rl"],
            capture_output=True, text=True, cwd=_REPO,
        ).stdout.splitlines()
        hits = [h for h in hits if f"relics/{rid}.py" not in h
                and f"class {cls.__name__}" not in h
                and f"class Fake{cls.__name__}" not in h]
        rows.append((rid, params, hits))

    print(f"  {len(rows)} relic ports take constructor arguments:")
    for rid, params, hits in rows:
        print(f"    {rid:<26} params={params}  "
              f"constructed-with-args-in={hits or ['(nowhere)']}")
    print("\n  RunState.add_relic goes through make_relic(id) with no args"
          " (run.py:546-548), so every 'nowhere' row can only ever hold its"
          " default.")


# ── orichalcum-order ──────────────────────────────────────────────────────
def probe_orichalcum_order() -> None:
    """fake_orichalcum: C#'s VeryEarly Block snapshot vs the sim's single pass.

    FakeOrichalcum.cs:46-58 latches `ShouldTrigger` from
    BeforeSideTurnEndVeryEarly (a complete listener pass that runs before the
    plain one) so no later turn-end listener can suppress the Block; the sim
    reads player.block inline from the single on_player_turn_end slot.
    audit/records/seam/turn_structure.json G12 names Fake Orichalcum as the same
    shape as Orichalcum and this executes it for the fake.
    """
    from sts2_rl import CombatState
    from sts2_rl.cards import make_card
    from sts2_rl.relics import make_relic
    from sts2_rl.relics.base import Relic, RelicRarity

    for order in (["cloak_clasp", "fake_orichalcum"],
                  ["fake_orichalcum", "cloak_clasp"]):
        seen: list[int] = []

        class Tail(Relic):
            """Registered last, so its on_player_turn_end runs after both."""
            id, name, rarity = "_b05tail", "Tail", RelicRarity.COMMON

            def on_player_turn_end(self, player):
                seen.append(player.block)

        relics = [make_relic(r) for r in order] + [Tail()]
        cs = CombatState(rng=random.Random(0), relics=relics)
        cs.player.hand.clear()
        for _ in range(5):
            cs.player.hand.append(make_card("strike"))
        cs.hooks.on_player_turn_end(cs.player)
        print(f"  registration order {order} -> end-of-turn block {seen}")
    print("  C# always gives 5 (Cloak Clasp) + 3 (Fake Orichalcum) = 8:"
          " the VeryEarly pass snapshots Block==0 before Cloak Clasp runs.")


# ── strike-dummy ──────────────────────────────────────────────────────────
def probe_strike_dummy() -> None:
    """fake_strike_dummy: the two C# guards the port drops.

    (a) `!props.IsPoweredAttack()` — the sim's modify_damage_additive
        dispatcher carries no props argument at all, so the port cannot
        self-gate. Every sim caller gates the whole dispatch instead.
    (b) `dealer != Owner.Creature && cardSource.Owner != Owner` — an OR, so in
        single-player (cardSource.Owner is always the player) C# fires for ANY
        dealer; the sim requires `dealer is self.player`.
    """
    import inspect

    from sts2_rl import CombatState, cmds, previews
    from sts2_rl.cards import make_card
    from sts2_rl.cards import thrash as thrash_mod
    from sts2_rl.cards.base import _CARD_CLASSES as ALL_CARDS
    from sts2_rl.relics import make_relic
    from sts2_rl.valueprops import DamageProps

    print("  (a) every sim caller of hooks.modify_damage_additive:")
    for mod in (cmds, previews, thrash_mod):
        src = inspect.getsource(mod).splitlines()
        for i, line in enumerate(src):
            if "hooks.modify_damage_additive(" in line:
                guard = next((src[j] for j in range(i - 1, max(0, i - 4), -1)
                              if "is_powered_attack" in src[j]), None)
                print(f"      {mod.__name__}: gated={guard is not None}"
                      f"  -> {(guard or '').strip()}")

    dummy = make_relic("fake_strike_dummy")
    cs = CombatState(rng=random.Random(0), relics=[dummy])
    strike = make_card("strike")
    print(f"      strike.tags={sorted(strike.tags)}")
    enemy = cs.enemies[0]

    hp = enemy.hp
    cmds.DamageCmd.deal(cs.hooks, enemy, 6, dealer=cs.player, card=strike,
                        props=DamageProps.CARD)
    print(f"  powered   Strike for 6 -> {hp - enemy.hp} damage  (C#: 7)")

    hp = enemy.hp
    cmds.DamageCmd.deal(cs.hooks, enemy, 6, dealer=cs.player, card=strike,
                        props=DamageProps.CARD_UNPOWERED)
    print(f"  unpowered Strike for 6 -> {hp - enemy.hp} damage  (C#: 6 --"
          f" the pipeline gate reproduces the dropped self-gate exactly)")

    hp = enemy.hp
    cmds.DamageCmd.deal(cs.hooks, enemy, 6, dealer=None, card=strike,
                        props=DamageProps.CARD)
    print(f"  powered   Strike, dealer=None -> {hp - enemy.hp} damage"
          f"  (C#: 7, because cardSource.Owner == Owner)")

    # (b)'s reachability: which ported cards carry the Strike tag at all, and
    # does any code path deal their damage without dealer=the player?
    tagged = sorted(cid for cid in ALL_CARDS
                    if "strike" in make_card(cid).tags)
    print(f"  ported cards carrying CardTag.Strike ({len(tagged)}): {tagged}")

    bad = []
    for path in sorted((_REPO / "sts2_rl").rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:      # pragma: no cover
            continue
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "deal"
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "DamageCmd"):
                continue
            kw = {k.arg: k.value for k in node.keywords}
            has_card = "card" in kw or len(node.args) >= 5
            dealer = kw.get("dealer")
            no_dealer = ("dealer" not in kw and len(node.args) < 4)
            if has_card and (no_dealer or isinstance(dealer, ast.Constant)
                             and dealer.value is None):
                bad.append(f"{path.relative_to(_REPO)}:{node.lineno}")
    print(f"  DamageCmd.deal sites passing a card but no dealer: "
          f"{bad or '(none)'}")


# ── popper-win ────────────────────────────────────────────────────────────
def probe_popper_win() -> None:
    """festive_popper: the enemy set, the slot, and the hand-rolled win check.

    FestivePopper.cs:19-31 damages `combatState.HittableEnemies` from
    Hook.AfterPlayerTurnStart -- turn_structure step 22, immediately after the
    turn-1 draw -- and C# only reaches CheckWinCondition at step 27
    (CombatManager.cs:573), AFTER step 23's AfterSideTurnStart pass and step
    26's auto-pre-play phase. The sim fires from on_player_turn_started (the
    step-23 slot, executed by relic_probes.py turn-order) and ends the combat
    inline via Relic._check_win.
    """
    from sts2_rl import CombatState
    from sts2_rl.relics import make_relic
    from sts2_rl.relics.base import Relic, RelicRarity

    seen: list[str] = []

    class Spy(Relic):
        """Registered AFTER the popper, i.e. later in the same dispatch."""
        id, name, rarity = "_b05spy", "Spy", RelicRarity.COMMON

        def on_player_turn_started(self, player):
            seen.append(f"is_over={self.combat.is_over} "
                        f"phase={self.combat.phase.name} "
                        f"enemy_hp={[e.hp for e in self.combat.enemies]}")

    popper = make_relic("festive_popper")
    cs = CombatState(rng=random.Random(0), relics=[popper])
    print(f"  normal combat: enemy hp after turn-1 setup "
          f"{[(e.name, e.hp, e.max_hp) for e in cs.enemies]}")

    # Attach after construction so enemy HP can be lowered first; the hook is
    # then fired exactly as CombatState's turn-1 setup would.
    cs2 = CombatState(rng=random.Random(0))
    for e in cs2.enemies:
        e.hp = 1
    popper2 = make_relic("festive_popper")
    spy = Spy()
    popper2.attach(cs2)
    spy.attach(cs2)
    cs2.hooks.on_player_turn_started(cs2.player)
    print(f"  lethal turn-1 popper, later listener in the SAME dispatch sees:")
    for line in seen:
        print(f"    {line}")
    print("    (C# is still mid-step-23 here: CheckWinCondition is step 27,"
          " after the auto-pre-play phase.)")

    print(f"  Relic.living_enemies filters is_gone only "
          f"(relics/base.py:294-297): "
          f"{[e.name for e in popper.living_enemies()]}")
    print(f"  hooks.should_allow_hitting exists: "
          f"{hasattr(cs.hooks, 'should_allow_hitting')}"
          f" -- but living_enemies does not consult it (bag_of_marbles G2)")


# ── waffle-round ──────────────────────────────────────────────────────────
def probe_waffle_round() -> None:
    """fake_lees_waffle: `(int)Math.Min(hp + amount, MaxHp)` vs `int(...)`.

    C# heals a decimal (MaxHp * 10/100) and truncates the SUM
    (Creature.SetCurrentHpInternal, Creature.cs:488-491); the sim truncates the
    AMOUNT (fake_lees_waffle.py:21) and then caps (run.heal, run.py:288-292).
    Exhaustive check that the two agree.
    """
    from decimal import Decimal

    bad = []
    for max_hp in range(1, 400):
        heal_dec = Decimal(max_hp) * (Decimal(10) / Decimal(100))
        sim_amount = int(max_hp * 10 / 100)
        for hp in range(0, max_hp + 1):
            cs_hp = int(min(Decimal(hp) + heal_dec, Decimal(max_hp)))
            sim_hp = hp + max(0, min(sim_amount, max_hp - hp))
            if cs_hp != sim_hp:
                bad.append((max_hp, hp, cs_hp, sim_hp))
    print(f"  max_hp 1..399 x every current HP: {len(bad)} mismatches")
    if bad:
        for row in bad[:10]:
            print(f"    max_hp={row[0]} hp={row[1]} C#={row[2]} sim={row[3]}")


# ── mango-hp ──────────────────────────────────────────────────────────────
def probe_mango_hp() -> None:
    """fake_mango: CreatureCmd.GainMaxHp is SetMaxHp THEN Heal(delta)."""
    from sts2_rl.run import RunState

    run = RunState(rng=random.Random(0))
    run.hp = 40
    before = (run.hp, run.max_hp)
    run.add_relic("fake_mango")
    print(f"  add_relic('fake_mango'): hp/max {before} -> "
          f"({run.hp}, {run.max_hp})   (C#: +3 max AND +3 current)")


# ── shrymp-imbued ─────────────────────────────────────────────────────────
def probe_shrymp_imbued() -> None:
    """electric_shrymp: the Imbued candidate filter, and what Imbued then does.

    ElectricShrymp.cs:23 selects through CardSelectCmd.FromDeckForEnchantment,
    whose filter is exactly `enchantment.CanEnchant(c)`
    (CardSelectCmd.cs:549). The sim pre-filters with
    ImbuedEnchantment.can_enchant. Compare the two predicates over the whole
    ported card pool, then check turn-1 behaviour.
    """
    from sts2_rl import CombatState
    from sts2_rl.cards import CardType, make_card
    from sts2_rl.cards.base import _CARD_CLASSES as ALL_CARDS
    from sts2_rl.enchantments import ImbuedEnchantment
    from sts2_rl.relics import make_relic
    from sts2_rl.run import RunState

    disagree = []
    for cid in sorted(ALL_CARDS):
        card = make_card(cid)
        sim = ImbuedEnchantment.can_enchant(card)
        # C# CanEnchant: not Status/Curse/Quest, CanEnchantCardType == Skill,
        # not (deck-pile Unplayable), no existing enchantment (Imbued is not
        # IsStackable).
        cs_ok = (card.card_type not in (CardType.STATUS, CardType.CURSE,
                                        CardType.QUEST)
                 and card.card_type == CardType.SKILL
                 and card.is_playable
                 and card.enchantment is None)
        if sim != cs_ok:
            disagree.append((cid, sim, cs_ok))
    print(f"  {len(ALL_CARDS)} ported cards; can_enchant vs CanEnchant "
          f"disagreements: {len(disagree)} {disagree[:10]}")

    run = RunState(rng=random.Random(0))
    before = [(c.id, c.enchantment) for c in run.deck]
    run.add_relic("electric_shrymp")
    after = [(c.id, c.enchantment.name if c.enchantment else None)
             for c in run.deck]
    print(f"  enchanted after add_relic: "
          f"{[a for a in after if a[1]]}   (skills only: "
          f"{sorted({c.id for c in run.deck if c.card_type.name == 'SKILL'})})")
    del before

    # Imbued.ShouldStartAtBottomOfDrawPile is unmodelled by the sim's
    # enchantment port (enchantments.py:249 calls it "cosmetic"), which is
    # audit/records/seam/turn_structure.json G14. Electric Shrymp is the only ported
    # grantor of Imbued, so it is that gap's reachability witness.
    from sts2_rl.enchantments import make_enchantment

    played = drawn = 0
    n = 200
    for seed in range(n):
        run2 = RunState(rng=random.Random(seed))
        run2.add_relic("electric_shrymp")
        cs = CombatState(starting_deck=list(run2.deck),
                         rng=random.Random(seed))
        card = next(c for c in run2.deck if c.enchantment is not None)
        if card in cs.player.hand:
            drawn += 1
        if card in cs.player.discard_pile or card in cs.player.exhaust_pile:
            played += 1
    print(f"  {n} seeds: Imbued card auto-played on turn 1 in {played}"
          f" ({100 * played // n}%), still in the opening hand in {drawn}")
    print(f"    C#: ALWAYS auto-played (Imbued.cs:20-26 calls CardCmd.AutoPlay"
          f" unconditionally on turn <= 1, from the BOTTOM of the draw pile"
          f" where ShouldStartAtBottomOfDrawPile put it,"
          f" CombatManager.cs:657-672).")
    print(f"    The sim's port requires `self.card in player.hand`"
          f" (enchantments.py:261-267) and never bottoms the card"
          f" (turn_structure G14).")


# ── ember-order ───────────────────────────────────────────────────────────
def probe_ember_order() -> None:
    """ember_tea: AfterRoomEntered fires BEFORE every BeforeCombatStart.

    CombatRoom.cs:224-228 calls SetUpCombat then Hook.AfterRoomEntered;
    Hook.BeforeCombatStart is only reached later, from
    CombatManager.StartCombatInternal (CombatManager.cs:403). So C# has the
    +2 Strength in place before ANY BeforeCombatStart listener runs. The sim
    puts it in the on_combat_start slot, in relic registration order.
    """
    from sts2_rl import CombatState
    from sts2_rl.relics import ALL_RELICS, make_relic

    tea = make_relic("ember_tea")
    print(f"  combats_left starts at {tea.combats_left}")
    for i in range(1, 8):
        cs = CombatState(rng=random.Random(i), relics=[tea])
        st = cs.player.powers.get("strength")
        print(f"    combat {i}: strength={st.amount if st else 0} "
              f"combats_left={tea.combats_left} is_used_up={tea.is_used_up}")

    # Which other ported relics run at the same slot, and do any read Strength?
    same_slot = [rid for rid, cls in sorted(ALL_RELICS.items())
                 if any("on_combat_start" in c.__dict__ for c in cls.__mro__)]
    readers = []
    for rid in same_slot:
        import inspect
        cls = ALL_RELICS[rid]
        for c in cls.__mro__:
            fn = c.__dict__.get("on_combat_start")
            if fn is None:
                continue
            src = inspect.getsource(fn)
            if "strength" in src.lower():
                readers.append(rid)
            break
    print(f"  ported relics with on_combat_start: {len(same_slot)}")
    print(f"  ...of which mention Strength: {readers}")

    # The slot difference is observable only if something in the
    # BeforeCombatStart window READS the player's Strength. Scan every
    # on_combat_start body in the whole sim, not just relics.
    import inspect as _i
    reads = []
    for path in sorted((_REPO / "sts2_rl").rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:      # pragma: no cover
            continue
        for node in ast.walk(tree):
            if (isinstance(node, ast.FunctionDef)
                    and node.name == "on_combat_start"):
                body = ast.unparse(node)
                if "powers.get" in body or "get_power" in body:
                    reads.append(f"{path.relative_to(_REPO)}:{node.lineno}")
    print(f"  on_combat_start bodies anywhere in sts2_rl/ that READ a power: "
          f"{reads or '(none)'}")
    del _i


# ── flower-blood ──────────────────────────────────────────────────────────
def probe_flower_blood() -> None:
    """fake_happy_flower and fake_blood_vial turn arithmetic."""
    from sts2_rl import CombatState
    from sts2_rl.relics import make_relic

    flower = make_relic("fake_happy_flower")
    cs = CombatState(rng=random.Random(0), relics=[flower])
    seq = []
    for _ in range(11):
        seq.append((cs.turn, flower.turns_seen, cs.player.energy))
        cs.end_turn()
    print("  fake_happy_flower (turn, turns_seen, energy at turn start):")
    print(f"    {seq}")
    print(f"    carried into combat 2 with turns_seen={flower.turns_seen}:")
    cs2 = CombatState(rng=random.Random(1), relics=[flower])
    print(f"    combat 2 turn 1 -> turns_seen={flower.turns_seen} "
          f"energy={cs2.player.energy}"
          f"   (C#: TurnsSeen is [SavedProperty], also carries)")

    vial = make_relic("fake_blood_vial")
    cs3 = CombatState(rng=random.Random(0), relics=[vial], current_hp=40,
                      max_hp=80)
    print(f"  fake_blood_vial: turn 1 hp={cs3.player.hp}   (C#: 41)")
    cs3.end_turn()
    print(f"                   turn 2 hp={cs3.player.hp}   (C#: 41)")


# ── cage-feather ──────────────────────────────────────────────────────────
def probe_cage_feather() -> None:
    """empty_cage / eternal_feather out-of-combat effects."""
    from sts2_rl.rooms import RoomType
    from sts2_rl.run import RunState

    run = RunState(rng=random.Random(0))
    before = len(run.deck)
    eternal = [c.id for c in run.deck if c.eternal]
    run.add_relic("empty_cage")
    print(f"  empty_cage: deck {before} -> {len(run.deck)} "
          f"(eternal cards present: {eternal})")
    print(f"    IsRemovable == !Eternal (CardModel.cs:737); "
          f"run.removable_cards() == not c.eternal (run.py:360-362)")

    run2 = RunState(rng=random.Random(0))
    run2.hp = 30
    r = run2.add_relic("eternal_feather")
    r.after_room_entered(run2, None, RoomType.REST_SITE)
    print(f"  eternal_feather: deck={len(run2.deck)} -> heal "
          f"{30} -> {run2.hp}   (C#: 3 * (deck // 5) = "
          f"{3 * (len(run2.deck) // 5)})")
    r.after_room_entered(run2, None, RoomType.MONSTER)
    print(f"    non-rest room: hp stays {run2.hp}")


# ── snecko-confused ───────────────────────────────────────────────────────
def probe_snecko_confused() -> None:
    """fake_snecko_eye: Confused amount/applier, and the missing AfterObtained."""
    from sts2_rl import CombatState
    from sts2_rl.relics import make_relic
    from sts2_rl.run import RunState

    relic = make_relic("fake_snecko_eye")
    cs = CombatState(rng=random.Random(0), relics=[relic])
    p = cs.player.powers.get("confused")
    print(f"  combat start: confused={p.amount if p else 0} "
          f"applier_is_player={getattr(p, 'applier', None) is cs.player}"
          f"   (C#: 1, applier = Owner.Creature)")
    print(f"  hand costs: {[c.energy_cost for c in cs.player.hand]}")
    print(f"  after_obtained override present: "
          f"{'after_obtained' in type(relic).__dict__}"
          f"   (C# FakeSneckoEye.cs:23-29 applies the power on a mid-combat"
          f" pickup)")
    run = RunState(rng=random.Random(0))
    run.add_relic("fake_snecko_eye")
    print(f"  SetTestEnergyCostOverride ported: "
          f"{hasattr(relic, 'set_test_energy_cost_override')}"
          f"   (TestMode.AssertOn path -- correctly dropped, PROMPT class 18)")


# ── anchor-window ─────────────────────────────────────────────────────────
def probe_anchor_window() -> None:
    """fake_anchor: the sim grants its Block from the turn-1 block-clear event.

    Same port shape as relic/anchor (audit/records/relic/anchor.json, hook
    BeforeCombatStart = deliberate-divergence, guard N3 = dormant gap for the
    ordering window). Executed here for the fake's own numbers.
    """
    from sts2_rl import CombatState
    from sts2_rl.relics import make_relic

    cs = CombatState(rng=random.Random(0), relics=[make_relic("fake_anchor")])
    print(f"  turn 1 block = {cs.player.block}   (C#: 4)")
    cs.end_turn()
    print(f"  turn 2 block = {cs.player.block}   (C#: 0)")

    # Nothing between BeforeCombatStart and the block clear may read Block.
    from sts2_rl.relics import ALL_RELICS
    import inspect
    readers = []
    for rid, cls in sorted(ALL_RELICS.items()):
        for c in cls.__mro__:
            fn = c.__dict__.get("on_combat_start")
            if fn is None:
                continue
            if ".block" in inspect.getsource(fn):
                readers.append(rid)
            break
    print(f"  ported relics whose on_combat_start reads .block: {readers}")


PROBES = {
    "b05-pool": probe_b05_pool,
    "tea-set-rest": probe_tea_set_rest,
    "injected-state": probe_injected_state,
    "orichalcum-order": probe_orichalcum_order,
    "strike-dummy": probe_strike_dummy,
    "popper-win": probe_popper_win,
    "waffle-round": probe_waffle_round,
    "mango-hp": probe_mango_hp,
    "shrymp-imbued": probe_shrymp_imbued,
    "ember-order": probe_ember_order,
    "flower-blood": probe_flower_blood,
    "cage-feather": probe_cage_feather,
    "snecko-confused": probe_snecko_confused,
    "anchor-window": probe_anchor_window,
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
