"""Reproducible execution probes for relic content audit BATCH 8.

Batch 8 covers the roster's `kifuda` … `lords_parasol` run:
  kifuda kunai kusarigama lantern large_capsule lasting_candy lava_lamp
  lava_rock lead_paperweight leafy_poultice lees_waffle letter_opener
  lizard_tail looming_fruit lords_parasol

Own module per the batch-8 concurrency contract (`audit/tools/relic_probes.py`
is READ-ONLY to this batch — re-use it, do not edit it; in particular
`py audit/tools/relic_probes.py turn-order` is the executed hook-order
reference these records cite for their turn-hook mappings).

Binding rules 5 and 6: never justify `faithful` with an unreachability claim
you have not EXECUTED, and never label a gap LIVE without proving both sides
reachable with ported content. Everything an `audit/records/relic/*.json` record from
this batch asserts about reachability is produced here.

  py audit/tools/relic_probes_b08.py               # every probe
  py audit/tools/relic_probes_b08.py b08-pool      # one probe

Probes:
  b08-pool          obtainability of batch 8's 15 relics (rule 6, first half)
  b08-replay        kunai / kusarigama / letter_opener under-count replayed
                    cards (hook_dispatch G4 at three new sites)
  b08-turn-reset    kunai / letter_opener carry no per-turn state into
                    combat 2 (bug class 13 reader-trace, executed)
  b08-lantern       Lantern's turn-1 energy and its turn slot
  b08-kifuda        Kifuda grants no enchantment; Adroit is unported
  b08-candy         Lasting Candy: no card-reward change, and `IsAllowed`
                    has no sim counterpart at floor >= 41
  b08-isallowed     FULL-BRACE rescan of every C# relic IsAllowed body --
                    corrects the shared sweep-isallowed regex, which reads
                    only the FIRST statement and so under-reports
                    multi-clause bodies (lasting_candy)
  b08-lavalamp      Lava Lamp does not upgrade a damage-free combat's rewards
  b08-lavarock      Lava Rock's two act-1-boss relic rewards
  b08-paperweight   Lead Paperweight's colorless 1-of-2
  b08-poultice      Leafy Poultice: max HP, transform order, the skipped
                    deck-add hooks and the un-passed Transformations stream
  b08-maxhp         Lee's Waffle / Looming Fruit max HP + heal
  b08-capsule       Large Capsule's 2 relics + Strike + Defend
  b08-lizard        Lizard Tail: the heal is 1 HP too high, the
                    CreatureCmd.kill path loses it entirely, and the
                    ShouldDie/ShouldDieLate collapse
  b08-parasol       Lord's Parasol does not buy the card-removal service
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

BATCH8 = [
    "kifuda", "kunai", "kusarigama", "lantern", "large_capsule",
    "lasting_candy", "lava_lamp", "lava_rock", "lead_paperweight",
    "leafy_poultice", "lees_waffle", "letter_opener", "lizard_tail",
    "looming_fruit", "lords_parasol",
]


# ── b08-pool ──────────────────────────────────────────────────────────────
def probe_b08_pool() -> None:
    """Where each batch-8 relic can come from (binding rule 6, first half).

    Same method as the shared module's `pool`: grab-bag membership comes from
    relic_pools.py (the transcribed C# pools); every other grant path is a
    literal relic id somewhere under sts2_rl/, so grep for it.
    """
    import subprocess

    from sts2_rl.relic_pools import IRONCLAD_RELIC_POOL, SHARED_RELIC_POOL
    from sts2_rl.relics import ALL_RELICS

    bag = {rid.removeprefix("RELIC.").lower(): rarity
           for rid, rarity in SHARED_RELIC_POOL + IRONCLAD_RELIC_POOL}
    for rid in BATCH8:
        srcs = subprocess.run(
            ["git", "grep", "-l", f'"{rid}"', "--", "sts2_rl"],
            capture_output=True, text=True, cwd=_REPO,
        ).stdout.split()
        srcs = [s for s in srcs
                if not s.endswith(f"relics/{rid}.py") and "vocab.json" not in s]
        print(f"  {rid:<18} registered={rid in ALL_RELICS} "
              f"bag={bag.get(rid, '-'):<9} granted_by={srcs or ['(none)']}")


# ── b08-replay ────────────────────────────────────────────────────────────
def probe_b08_replay() -> None:
    """Kunai / Kusarigama / Letter Opener vs a Replay source.

    C# fires Hook.AfterCardPlayed once per Replay iteration, INSIDE
    CardModel.cs:1904-1963's `for (i = 0; i < playCount; i++)` loop, so a
    doubled Attack advances Kunai's AttacksPlayedThisTurn by TWO. The sim
    calls hooks.on_card_played once after the whole loop (combat.py:514), so
    the counter advances by one. All three relics count "every 3 cards of a
    type in a turn", so the divergence is not a rounding detail: a different
    card triggers the relic, one play later, for the rest of the turn.

    Throwing Axe (relics/throwing_axe.py:30-36, granted by the ported Tanx
    shrine) is the replay source; the Spiral and Glam enchantments, One-Two
    Punch and Duplication reach the same combat.py:469 play-count hook.
    """
    from sts2_rl import CombatState
    from sts2_rl.cards import make_card
    from sts2_rl.relics import make_relic

    for rid, cid, field, expect in (
        ("kunai", "strike", "_attacks_this_turn", "3 -> +1 Dexterity"),
        ("kusarigama", "strike", "_attacks_this_turn", "3 -> 6 damage"),
        ("letter_opener", "defend", "_skills_this_turn", "3 -> 5 AoE damage"),
    ):
        for with_axe in (False, True):
            relic = make_relic(rid)
            relics = [relic] + ([make_relic("throwing_axe")] if with_axe else [])
            cs = CombatState(rng=random.Random(0), relics=relics)
            cs.player.hand.clear()
            cs.player.energy = 30
            for _ in range(2):
                cs.player.hand.append(make_card(cid))
                cs.play_card(len(cs.player.hand) - 1, 0)
            dex = cs.player.powers.get("dexterity")
            print(f"  {rid:<14} axe={str(with_axe):<5} after 2 plays "
                  f"{field}={getattr(relic, field)}  "
                  f"player_dex={dex.amount if dex else 0}  "
                  f"enemy_hp={cs.enemy.hp}")
        print(f"  {'':<14} C# with the Axe counts 3 for those 2 plays "
              f"({expect}); the sim counts 2.\n")


# ── b08-turn-reset ────────────────────────────────────────────────────────
def probe_b08_turn_reset() -> None:
    """Kunai / Letter Opener: the dropped combat-boundary reset is shadowed.

    `py audit/tools/relic_probes.py sweep-reset` puts both in the "reset at a
    TURN boundary only" bucket (art_of_war shape) -- Kunai's C# clears
    AttacksPlayedThisTurn in AfterCombatEnd and Letter Opener's in BOTH
    BeforeCombatStart and AfterCombatEnd, while the sim clears each only at
    on_player_turn_start. PROMPT.md bug class 13 requires tracing to the first
    READER of the stale field before verdicting, and the only reader is
    on_card_played -- which cannot run before the play phase opens. This
    probe executes it: carry ONE instance into a second combat with the
    counter dirty and diff against a fresh instance.
    """
    from sts2_rl import CombatState
    from sts2_rl.cards import make_card
    from sts2_rl.relics import make_relic

    for rid, cid, field in (("kunai", "strike", "_attacks_this_turn"),
                            ("letter_opener", "defend", "_skills_this_turn")):
        carried = make_relic(rid)
        cs1 = CombatState(rng=random.Random(0), relics=[carried])
        cs1.player.hand.clear()
        cs1.player.energy = 30
        for _ in range(2):
            cs1.player.hand.append(make_card(cid))
            cs1.play_card(len(cs1.player.hand) - 1, 0)
        dirty = getattr(carried, field)
        # Combat 2 with the SAME instance, exactly as RunState.relics does.
        cs2 = CombatState(rng=random.Random(1), relics=[carried])
        fresh = make_relic(rid)
        CombatState(rng=random.Random(1), relics=[fresh])
        print(f"  {rid:<14} end of combat 1 {field}={dirty}; "
              f"combat 2 turn 1 carried={getattr(carried, field)} "
              f"fresh={getattr(fresh, field)}  "
              f"equal={getattr(carried, field) == getattr(fresh, field)}")
        _ = cs2


# ── b08-kusarigama ────────────────────────────────────────────────────────
def probe_b08_kusarigama() -> None:
    """Kusarigama's reset sits in the sim's BeforeTurnEnd slot, not AfterTurnEnd.

    Kusarigama.cs:94-103 resets AttacksPlayedThisTurn in **AfterSideTurnEnd**,
    which audit/records/seam/turn_structure.json step 64 places AFTER the hand flush
    -- and step 47 puts the auto-POST-play phase (Hook.
    AfterAutoPostPlayPhaseEntered) BEFORE it. So in C# the reset always runs
    after any turn-end auto-play. kusarigama.py:32-33 uses
    `on_player_turn_end`, which hooks.py:297-301 documents as Hook.
    BeforeTurnEnd (step 48) -- the SAME hook the ported StampedePower
    (powers.py:1023, from cards/stampede.py, whose C# home is
    StampedePower.cs:18 AfterAutoPostPlayPhaseEntered) uses to auto-play
    Attacks. Listener order therefore decides whether those Attacks are
    counted into the NEXT turn.
    """
    from sts2_rl import CombatState
    from sts2_rl.cards import make_card
    from sts2_rl.cmds import PowerCmd
    from sts2_rl.powers import StampedePower
    from sts2_rl.relics import make_relic

    kusa = make_relic("kusarigama")
    cs = CombatState(rng=random.Random(0), relics=[kusa])
    PowerCmd.apply(cs.hooks, cs.player, StampedePower, 2, applier=cs.player)
    cs.player.hand.clear()
    for _ in range(2):
        cs.player.hand.append(make_card("strike"))
    order = [type(l).__name__ for l in cs.hooks._listeners
             if type(l).__name__ in ("Kusarigama", "StampedePower")]
    print(f"  on_player_turn_end listener order: {order}")
    cs.end_turn()
    print(f"  after end_turn with Stampede(2): "
          f"_attacks_this_turn={kusa._attacks_this_turn}   "
          f"(C# resets at AfterSideTurnEnd, i.e. AFTER the auto-post-play "
          f"attacks -> 0)")
    print(f"  the sim DOES have the right slot: "
          f"HookSystem.after_player_turn_end exists="
          f"{hasattr(cs.hooks, 'after_player_turn_end')} "
          f"(relics/parrying_shield.py is the ported witness)")
    print(f"  combat-start reset also present (Kusarigama.cs:87-92 -> "
          f"kusarigama.py:29-30), so the stale value only survives to the "
          f"next TURN, not the next combat.")


# ── b08-lantern ───────────────────────────────────────────────────────────
def probe_b08_lantern() -> None:
    """Lantern's +1 energy on turn 1 and the slot it lands in.

    Lantern.cs:21-28 is AfterSideTurnStart (turn_structure step 23, POST-draw)
    gated on TurnNumber <= 1; lantern.py:18-21 is on_player_turn_started, which
    `py audit/tools/relic_probes.py turn-order` shows is the sim's post-draw
    slot. Both therefore land after the energy RESET (step 17/18), which is
    what makes the gain survive.
    """
    from sts2_rl import CombatState
    from sts2_rl.relics import make_relic

    for relics, label in (([], "no relic"), ([make_relic("lantern")], "Lantern")):
        cs = CombatState(rng=random.Random(0), relics=relics)
        t1 = cs.player.energy
        cs.end_turn()
        print(f"  {label:<10} turn 1 energy={t1} (base "
              f"{cs.player.ENERGY_PER_TURN})   turn 2 energy={cs.player.energy}")
    print("  C#: 4 on turn 1, 3 on turn 2 (TurnNumber <= 1).")


# ── b08-kifuda ────────────────────────────────────────────────────────────
def probe_b08_kifuda() -> None:
    """Kifuda enchants nothing, and the enchantment it needs is unported.

    Kifuda.cs:24-37 is AfterObtained: a not-cancelable up-to-3 deck selection
    that Enchants each pick with Adroit at amount 3. kifuda.py is a
    behaviourless stub whose docstring says "no enchantments in the sim",
    which the shared `sweep-stubs` already flags as false -- enchantments.py
    is ported and run.py:552 dispatches after_obtained. The half the sweep
    could not answer is whether ADROIT exists.
    """
    from sts2_rl.enchantments import ALL_ENCHANTMENTS
    from sts2_rl.relics import make_relic
    from sts2_rl.run import RunState

    print(f"  ported enchantments ({len(ALL_ENCHANTMENTS)}): "
          f"{sorted(ALL_ENCHANTMENTS)}")
    print(f"  'adroit' ported: {'adroit' in ALL_ENCHANTMENTS}   "
          f"(C#: src/Core/Models/Enchantments/Adroit.cs, OnPlay -> "
          f"CreatureCmd.GainBlock(Amount))")
    run = RunState(rng=random.Random(0))
    run.add_relic("kifuda")
    ench = {c.enchantment for c in run.deck}
    print(f"  after add_relic('kifuda'): deck={len(run.deck)} cards, "
          f"enchantments={ench}   (C#: 3 cards carry Adroit(3))")
    k = make_relic("kifuda")
    print(f"  sim has_upon_pickup_effect={k.has_upon_pickup_effect} "
          f"is_tradable={k.is_tradable}   (C# HasUponPickupEffect => true)")
    # The pipeline the port would need already exists and a sibling uses it.
    print("  pipeline present: relics/beautiful_bracelet.py attaches an "
          "enchantment from a relic, and run.select_cards('enchant', ...) is "
          "the CardSelectCmd.FromDeckForEnchantment counterpart:")
    import subprocess
    out = subprocess.run(
        ["git", "grep", "-n", "select_cards(\"enchant\"", "--", "sts2_rl"],
        capture_output=True, text=True, cwd=_REPO).stdout.strip()
    print("   ", out or "(no 'enchant' selector call site)")


# ── b08-candy ─────────────────────────────────────────────────────────────
def probe_b08_candy() -> None:
    """Lasting Candy: no extra Power option, and no IsAllowed concept.

    LastingCandy.cs:100-136 (TryModifyCardRewardOptions -- the EARLY pass, and
    the game's ONLY override of it) adds a Power card to every other combat's
    card reward. LastingCandy.cs:138-147 (AfterCombatEnd) is the counter that
    decides "every other". lasting_candy.py is a behaviourless stub.
    """
    from sts2_rl.relics import ALL_RELICS, base as relic_base
    from sts2_rl.rewards import generate_combat_rewards
    from sts2_rl.rooms import RoomType
    from sts2_rl.run import RunState

    for relics in ([], ["lasting_candy"]):
        run = RunState(rng=random.Random(11))
        for rid in relics:
            run.add_relic(rid)
        # Two combats, so C#'s CombatsSeen is 2 == IsInTriggeringCombat.
        for n in (1, 2):
            rewards = generate_combat_rewards(run, RoomType.MONSTER)
        types = [c.card_type.name for c in rewards.cards]
        print(f"  relics={relics or ['(none)']} combat 2 card reward: "
              f"{[c.id for c in rewards.cards]} types={types}")
    print("  C# adds a 4th option, always a Power. Equal lists = the gap.")

    print(f"\n  sim Relic base defines is_allowed: "
          f"{hasattr(relic_base.Relic, 'is_allowed')}   "
          f"(C# LastingCandy.IsAllowed has TWO clauses -- an Ironclad "
          f"UnlockState.NumberOfRuns == 0 veto AND "
          f"IsBeforeAct3TreasureChest = TotalFloor < 41)")
    run = RunState(rng=random.Random(3))
    run.total_floor = 60
    run.relic_grab_bag = ["lasting_candy"]
    pulled = run.pull_relic_from_front(rarity=ALL_RELICS["lasting_candy"].rarity)
    print(f"  at total_floor={run.total_floor} the bag still yields "
          f"{pulled.id if pulled else None!r}   (C#: removed from the deque by "
          f"RelicGrabBag.RemoveDisallowedRelicsFromDeques, RelicGrabBag.cs:250-271)")
    print(f"  run tracks total_floor: {hasattr(run, 'total_floor')} "
          f"-> the predicate is expressible today")


# ── b08-isallowed ─────────────────────────────────────────────────────────
def probe_b08_isallowed() -> None:
    """FULL-BRACE rescan of every C# relic IsAllowed body.

    Why: the shared `sweep-isallowed` matches
    `public override bool IsAllowed\\([^)]*\\)\\s*\\{\\s*(?:return\\s+)?([^\\n;]*)`
    -- i.e. only the FIRST statement of the body. Any relic whose IsAllowed
    has a guard clause BEFORE its main predicate is therefore mis-bucketed.
    `lasting_candy` is exactly that: an UnlockState veto first, then
    `return RelicModel.IsBeforeAct3TreasureChest(runState)`. The sweep filed it
    as bucket (c) "unlock gate" and left it OUT of bucket (a), the
    16-relic TotalFloor < 41 cluster. This probe brace-matches the whole body
    so the cluster membership is settled mechanically.
    """
    from sts2_rl.relics import ALL_RELICS
    from audit.tools.harness import DEFAULT_GAME_ROOT, roster

    rows = {r["unit"].split("/", 1)[1]: r for r in roster("relic")}
    act3, other, neow = [], [], []
    for rid in sorted(ALL_RELICS):
        row = rows.get(rid)
        if row is None:
            continue
        p = DEFAULT_GAME_ROOT / row["game_path"]
        if not p.is_file():
            continue
        text = p.read_text(encoding="utf-8-sig", errors="replace")
        for name, bucket in (("IsAllowed", None), ("IsAllowedAtNeow", neow)):
            m = re.search(rf"public override bool {name}\(", text)
            if not m:
                continue
            i = text.index("{", m.end())
            depth, j = 0, i
            while j < len(text):
                if text[j] == "{":
                    depth += 1
                elif text[j] == "}":
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            body = " ".join(text[i + 1:j].split())
            if bucket is neow:
                neow.append((rid, body[:110]))
            elif "IsBeforeAct3TreasureChest" in body:
                act3.append((rid, body[:150]))
            else:
                other.append((rid, body[:110]))
    print(f"  IsAllowed bodies containing IsBeforeAct3TreasureChest "
          f"({len(act3)}) -- the TotalFloor < 41 cluster:")
    for rid, body in act3:
        extra = "" if body.startswith("return") else "   <-- MULTI-CLAUSE"
        print(f"    {rid:<24} {body[:100]}{extra}")
    print(f"\n  other IsAllowed overrides ({len(other)}):")
    for rid, body in other:
        print(f"    {rid:<24} {body}")
    print(f"\n  IsAllowedAtNeow overrides ({len(neow)}):")
    for rid, body in neow:
        print(f"    {rid:<24} {body}  "
              f"sim is_allowed_at_neow={ALL_RELICS[rid].is_allowed_at_neow}")


# ── b08-lavalamp ──────────────────────────────────────────────────────────
def probe_b08_lavalamp() -> None:
    """Lava Lamp does not upgrade a damage-free combat's card rewards.

    LavaLamp.cs:64-89 (TryModifyCardRewardOptionsLate) clones and Upgrades
    every upgradable reward option when TookDamageThisCombat is false;
    :36-40 clears the flag in AfterRoomEntered and :42-62 sets it in
    AfterDamageReceived. lava_lamp.py is a behaviourless stub -- and all three
    sim pipelines exist (`sweep-stub-premises` already reports two of them).
    """
    from sts2_rl.relics import ALL_RELICS, base as relic_base
    from sts2_rl.rewards import generate_combat_rewards
    from sts2_rl.rooms import RoomType
    from sts2_rl.run import RunState

    for relics in ([], ["lava_lamp"], ["silver_crucible"]):
        run = RunState(rng=random.Random(5))
        for rid in relics:
            run.add_relic(rid)
        rewards = generate_combat_rewards(run, RoomType.MONSTER)
        print(f"  relics={str(relics or ['(none)']):<24} rewards="
              f"{[(c.id, c.upgrade_level) for c in rewards.cards]}")
    print("  silver_crucible is the ported witness that the SAME C# hook "
          "(TryModifyCardRewardOptionsLate -> modify_card_reward_options) "
          "does upgrade reward options in the sim today.")
    for hook in ("after_room_entered", "modify_card_reward_options"):
        print(f"  Relic.{hook} exists: {hasattr(relic_base.Relic, hook)}")
    print(f"  HookSystem.on_damage_received exists: "
          f"{hasattr(__import__('sts2_rl.hooks', fromlist=['HookSystem']).HookSystem, 'on_damage_received')}")
    print(f"  lava_lamp implements nothing: "
          f"{[n for n in vars(ALL_RELICS['lava_lamp']) if not n.startswith('__')]}")


# ── b08-lavarock ──────────────────────────────────────────────────────────
def probe_b08_lavarock() -> None:
    """Lava Rock adds two relic rewards to the act-1 boss screen.

    LavaRock.cs:38-64 (TryModifyRewards) appends `DynamicVars["Relics"]` == 2
    `new RelicReward(player)` to a Boss room's rewards while
    CurrentActIndex == 0 and HasTriggered is false, then latches.
    """
    from sts2_rl.rewards import generate_combat_rewards
    from sts2_rl.rooms import RoomType
    from sts2_rl.run import RunState

    for relics in ([], ["lava_rock"]):
        run = RunState(rng=random.Random(9))
        run.start_run()
        for rid in relics:
            run.add_relic(rid)
        before = len(run.relics)
        bag = len(run.relic_grab_bag)
        rewards = generate_combat_rewards(run, RoomType.BOSS)
        print(f"  relics={str(relics or ['(none)']):<18} act={run.act_index} BOSS: "
              f"rewards.relics={[r.id for r in rewards.relics]} "
              f"run.relics {before}->{len(run.relics)} bag {bag}->"
              f"{len(run.relic_grab_bag)}")
    # The latch and the non-act-0 / non-boss guards.
    run = RunState(rng=random.Random(9))
    run.start_run()
    rock = run.add_relic("lava_rock")
    generate_combat_rewards(run, RoomType.BOSS)
    n = len(run.relics)
    generate_combat_rewards(run, RoomType.BOSS)
    print(f"  second act-0 BOSS screen: has_triggered={rock.has_triggered} "
          f"run.relics {n}->{len(run.relics)}   (C#: HasTriggered latches)")
    run2 = RunState(rng=random.Random(9))
    run2.start_run()
    run2.add_relic("lava_rock")
    m = len(run2.relics)
    generate_combat_rewards(run2, RoomType.MONSTER)
    print(f"  MONSTER screen: run.relics {m}->{len(run2.relics)}  "
          f"(C#: room.RoomType != Boss -> no-op)")


# ── b08-paperweight ───────────────────────────────────────────────────────
def probe_b08_paperweight() -> None:
    """Lead Paperweight's 1-of-2 colorless choice.

    LeadPaperweight.cs:19-36: CardFactory.CreateForReward over the
    ColorlessCardPool with RegularEncounter odds and CardCreationSource.Other,
    then a SKIPPABLE choose-a-card screen (canSkip: true).
    """
    from sts2_rl.cards.pool import COLORLESS_POOL
    from sts2_rl.run import RunState

    seen = []
    for seed in (0, 4, 7):
        run = RunState(rng=random.Random(seed))
        offered: list = []
        run.card_selector = lambda purpose, cands, count: (
            offered.extend(cands) or cands[:count])
        n = len(run.deck)
        run.add_relic("lead_paperweight")
        added = [c.id for c in run.deck[n:]]
        seen.append(added)
        print(f"  seed={seed} offered={[c.id for c in offered]} added={added} "
              f"all_colorless={all(c.id in COLORLESS_POOL for c in offered)}")
    # canSkip: the sim's select_cards can return [] if the policy declines.
    run = RunState(rng=random.Random(0))
    run.card_selector = lambda purpose, cands, count: []
    n = len(run.deck)
    run.add_relic("lead_paperweight")
    print(f"  a declining selector adds {len(run.deck) - n} cards "
          f"(C# canSkip: true -> 0)")


# ── b08-poultice ──────────────────────────────────────────────────────────
def probe_b08_poultice() -> None:
    """Leafy Poultice: -12 max HP and two basic transforms.

    LeafyPoultice.cs:21-37: LoseMaxHp(12), then ONE
    `CardCmd.Transform(list, Owner.PlayerRng.Transformations)` carrying the
    first Basic Strike and the first Basic Defend.
    """
    from sts2_rl.run import RunState

    def _run(seed="89U21BV1TZ"):
        """A run in the SP2 PARITY path (rng_set present).

        transform_card's deck-end placement -- the branch C# matches -- only
        runs when run.rng_set is not None (run.py:459); the legacy RL path
        replaces in place on purpose. Probe the parity branch, or the ordering
        claim is untestable.
        """
        return RunState(rng=random.Random(0), string_seed=seed)

    run = _run()
    before = (run.hp, run.max_hp, [c.id for c in run.deck])
    run.add_relic("leafy_poultice")
    print(f"  hp/max {before[0]}/{before[1]} -> {run.hp}/{run.max_hp}   "
          f"(C#: 68/68 -- LoseMaxHp damages the excess then clamps)")
    print(f"  deck before: {before[2]}")
    print(f"  deck after:  {[c.id for c in run.deck]}")
    print("  C# CardCmd.Transform removes both originals, sorts by original "
          "pile index (Strike idx 0 < Defend idx 5 in the starting deck) and "
          "appends the replacements in that order; the sim's two sequential "
          "transform_card calls produce the SAME order, because a replacement "
          "is never Basic-rarity and so cannot be re-found by the second "
          "search.")

    # The deck-add hooks CardCmd.Transform runs and run.transform_card does not
    # (= audit/records/seam/creature_card_cmds.json G3, LIVE).
    from sts2_rl.cards import make_card
    for egg in ("frozen_egg", "toxic_egg", "molten_egg"):
        run2 = _run()
        run2.add_relic(egg)
        run2.add_relic("leafy_poultice")
        tail = run2.deck[-2:]
        ctl = _run()
        ctl.add_relic("leafy_poultice")
        print(f"\n  holding {egg:<11} transform tail="
              f"{[(c.id, c.card_type.name, c.upgrade_level) for c in tail]}")
        print(f"  {'':<19} same relic via add_card: "
              f"{[(c.id, run2.add_card(make_card(c.id)).upgrade_level) for c in tail]}"
              f"   <-- add_card DOES upgrade, transform_card does not")
        _ = ctl
    print("  (C# CardCmd.cs:430 runs Hook.ModifyCardBeingAddedToDeck on a "
          "Deck-pile transform, so an egg-matching replacement arrives "
          "upgraded; run.transform_card never calls add_card. = seam G3.)")
    run3 = _run()
    run3.add_relic("bing_bong")
    n3 = len(run3.deck)
    run3.add_relic("leafy_poultice")
    print(f"  holding Bing Bong, deck size {n3} -> {len(run3.deck)}  "
          f"(net 0 from 2 transforms; C# fires AfterCardChangedPiles twice)")

    # Bug class 16, second half: the named Transformations stream.
    import inspect
    from sts2_rl.relics import leafy_poultice as lp
    src = inspect.getsource(lp)
    print(f"\n  leafy_poultice passes pick_rng: {'pick_rng' in src}   "
          f"(C#: base.Owner.PlayerRng.Transformations; and "
          f"CardTransformation(original) sets NO Replacement, so "
          f"GetReplacement(rng) DOES draw -- unlike relic/claws)")
    r4 = _run()
    print(f"  the stream is available as run.player_rng.transformations: "
          f"{r4.player_rng is not None and r4.player_rng.transformations is not None}"
          f"  counter before={r4.player_rng.transformations.counter}")
    r4.add_relic("leafy_poultice")
    print(f"  counter after add_relic('leafy_poultice')="
          f"{r4.player_rng.transformations.counter}   (C#: 2 NextItem draws)")
    print("  sibling callers that DO pass it: relics/pandoras_box.py:32 "
          "(pick_rng=niche), events/whispering_hollow.py:66")


# ── b08-maxhp ─────────────────────────────────────────────────────────────
def probe_b08_maxhp() -> None:
    """Lee's Waffle (+7 then heal to full) and Looming Fruit (+31).

    LeesWaffle.cs:18-23: GainMaxHp(7) -- which itself Heals 7 -- then
    Heal(MaxHp - CurrentHp). LoomingFruit.cs:45-48: GainMaxHp(31) only.
    """
    from sts2_rl.run import RunState

    for rid, hp0, expect in (("lees_waffle", 40, "87/87"),
                             ("lees_waffle", 80, "87/87"),
                             ("looming_fruit", 40, "111 max / 71 hp"),
                             ("looming_fruit", 80, "111/111")):
        run = RunState(rng=random.Random(0), hp=hp0)
        b = (run.hp, run.max_hp)
        relic = run.add_relic(rid)
        after = (run.hp, run.max_hp)
        relic.undo_after_obtained(run)
        print(f"  {rid:<15} {b[0]}/{b[1]} -> {after[0]}/{after[1]}  "
              f"(C#: {expect})   undo -> {run.hp}/{run.max_hp}")
    print("  Looming Fruit's 50% cornucopia (LoomingFruit.cs:35-43, a hash of "
          "SaveManager.Progress.UniqueId) only picks the ICON variant.")


# ── b08-capsule ───────────────────────────────────────────────────────────
def probe_b08_capsule() -> None:
    """Large Capsule: two grab-bag relics plus a Strike and a Defend.

    LargeCapsule.cs:23-36 pulls `DynamicVars["Relics"]` == 2 relics with
    RelicFactory.PullNextRelicFromFront(Owner) -> RelicCmd.Obtain, then
    CardPileCmd.Add(Strike, Deck) and Add(Defend, Deck). GetStrikeForCharacter
    / GetDefendForCharacter fork on TestMode.IsOn (PROMPT.md bug class 18);
    the shipping arm takes the character pool's first Basic card carrying the
    Strike / Defend tag, which for the Ironclad is exactly `strike`/`defend`.
    """
    from sts2_rl.cards.base import _CARD_CLASSES
    from sts2_rl.run import RunState
    import sts2_rl.cards  # noqa: F401

    basics = [(cid, sorted(c.tags)) for cid, c in sorted(_CARD_CLASSES.items())
              if c.rarity.name == "BASIC"]
    print(f"  ported Basic-rarity cards: {basics}")
    run = RunState(rng=random.Random(2))
    n, bag = len(run.deck), len(run.relic_grab_bag)
    run.add_relic("large_capsule")
    print(f"  add_relic('large_capsule'): relics={[r.id for r in run.relics]}")
    print(f"  deck {n} -> {len(run.deck)}, tail={[c.id for c in run.deck[-2:]]}"
          f", grab bag {bag} -> {len(run.relic_grab_bag)}")
    print("  C#: 2 pulls (each a Rewards-stream RollRarity + a bag removal), "
          "then the two Basic cards appended at the deck end.")


# ── b08-lizard ────────────────────────────────────────────────────────────
def probe_b08_lizard() -> None:
    """Lizard Tail: the heal amount, the kill path, and the phase collapse.

    LizardTail.cs:40-59: ShouldDieLate vetoes the owner's first death, then
    AfterPreventingDeath heals `Math.Max(1, MaxHp * 50/100)`. C# heals from
    CurrentHp == 0 (Kill leaves it there), so the player lands on exactly 50%
    of Max HP. The sim's DamageCmd.deal floors a prevented death at 1 HP
    (cmds.py:110-113) and lizard_tail.py:53 then heals BY the same amount.
    """
    from sts2_rl import CombatState
    from sts2_rl.cmds import CreatureCmd, DamageCmd
    from sts2_rl.relics import make_relic
    from sts2_rl.valueprops import DamageProps

    # (a) the heal is one HP too high
    for max_hp in (80, 81, 1):
        tail = make_relic("lizard_tail")
        cs = CombatState(rng=random.Random(0), relics=[tail],
                         max_hp=max_hp, current_hp=max_hp)
        DamageCmd.deal(cs.hooks, cs.player, max_hp + 50,
                       dealer=cs.enemy, props=DamageProps.NON_CARD_UNPOWERED)
        print(f"  DamageCmd lethal hit, max_hp={max_hp:<3} -> hp={cs.player.hp}"
              f"  used={tail._used} heal_pending={tail._heal_pending}"
              f"   (C#: {max(1, max_hp * 50 // 100)})")
    print("  The sibling potion gets this right: potions/fairy_in_a_bottle "
          "heals `heal_to - creature.hp` (potions.py:1256), lizard_tail heals "
          "the raw amount.")

    # (b) CreatureCmd.kill never fires after_preventing_death OR
    #     on_damage_received, so the heal is lost / deferred
    tail = make_relic("lizard_tail")
    cs = CombatState(rng=random.Random(0), relics=[tail],
                     max_hp=80, current_hp=40)
    CreatureCmd.kill(cs.hooks, cs.player)
    print(f"\n  CreatureCmd.kill path: hp={cs.player.hp} used={tail._used} "
          f"heal_pending={tail._heal_pending}   (C# Kill -> ShouldDieLate -> "
          f"AfterPreventingDeath -> hp 40)")
    DamageCmd.deal(cs.hooks, cs.player, 1, dealer=cs.enemy,
                   props=DamageProps.NON_CARD_UNPOWERED)
    print(f"  ... and the pending heal lands on the NEXT damage instead: "
          f"hp={cs.player.hp}")
    print("  Ported callers of CreatureCmd.kill that target the player: "
          "powers.py:2619 SandpitPower (The Insatiable, monsters/hive/"
          "the_insatiable.py) and powers.py:3829 TheGambitPower "
          "(cards/colorless_skills.py:772, 'the_gambit' is in COLORLESS_POOL "
          "-- which relic/lead_paperweight itself offers from).")
    from sts2_rl.cards.pool import COLORLESS_POOL
    print(f"  'the_gambit' in COLORLESS_POOL: "
          f"{'the_gambit' in COLORLESS_POOL}")

    # (c) cards/breakthrough.py's ad-hoc should_die call
    import inspect
    from sts2_rl.cards import breakthrough, make_card
    from sts2_rl.cards.pool import IRONCLAD_POOL
    print("\n  cards/breakthrough.py:49 calls hooks.should_die(p) with NO "
          "preventer list and NO HP floor:")
    for ln in inspect.getsource(breakthrough).splitlines():
        if "should_die" in ln or "p.hp = max" in ln:
            print("   ", ln.strip())
    tail = make_relic("lizard_tail")
    cs = CombatState(rng=random.Random(0), relics=[tail],
                     max_hp=80, current_hp=1)
    cs.player.hand.clear()
    cs.player.energy = 10
    cs.player.hand.append(make_card("breakthrough"))
    cs.play_card(0, 0)
    print(f"  Breakthrough played at 1 HP: hp={cs.player.hp} "
          f"is_dead={cs.player.is_dead} tail_used={tail._used} "
          f"heal_pending={tail._heal_pending} phase={cs.phase.value}   "
          f"(C#: death prevented, hp 40, combat continues)")
    print(f"  'breakthrough' in IRONCLAD_POOL: "
          f"{'breakthrough' in IRONCLAD_POOL}")

    # (d) the ShouldDie / ShouldDieLate two-phase collapse
    from sts2_rl.potions import make_potion
    tail = make_relic("lizard_tail")
    cs = CombatState(rng=random.Random(0), relics=[tail],
                     max_hp=80, current_hp=80)
    cs.player.add_potion(make_potion("fairy_in_a_bottle"))
    order = [type(l).__name__ for l in cs.hooks._listeners
             if type(l).__name__ in ("LizardTail", "FairyInABottlePotion",
                                     "FairyInABottle")]
    DamageCmd.deal(cs.hooks, cs.player, 200, dealer=cs.enemy,
                   props=DamageProps.NON_CARD_UNPOWERED)
    print(f"\n  Lizard Tail + Fairy in a Bottle: listener order={order}, "
          f"tail used={tail._used}, hp={cs.player.hp}, "
          f"belt={[p.id for p in cs.player.held_potions]}")
    print("  C# runs the whole ShouldDie pass (FairyInABottle.cs:33, the "
          "game's ONLY non-mock override) BEFORE the ShouldDieLate pass "
          "(LizardTail is the game's ONLY override), so the Fairy is always "
          "spent first and the Tail is preserved.")


# ── b08-parasol ───────────────────────────────────────────────────────────
def probe_b08_parasol() -> None:
    """Lord's Parasol does not buy the card-removal service.

    LordsParasol.cs:102-107, AFTER the four purchase loops:
        if (inventory.CardRemovalEntry != null) { ...
            await inventory.CardRemovalEntry.OnTryPurchaseWrapper(
                inventory, ignoreCost: true, cancelable: false); ... }
    lords_parasol.py:21-22 explicitly `continue`s past
    MerchantCardRemovalEntry, and the port's docstring asserts "the
    card-removal service is not an item and is not bought".
    """
    from sts2_rl.shop import MerchantCardRemovalEntry, MerchantInventory
    from sts2_rl.run import RunState

    for relics in ([], ["lords_parasol"]):
        run = RunState(rng=random.Random(6))
        run.start_run()
        for rid in relics:
            run.add_relic(rid)
        run.card_selector = lambda purpose, cands, count: list(cands)[:count]
        inv = MerchantInventory.create(run)
        deck0, gold0 = len(run.deck), run.gold
        for relic in list(run.relics):
            relic.after_shop_entered(run, inv)
        rem = inv.card_removal_entry
        print(f"  relics={str(relics or ['(none)']):<20} gold {gold0}->{run.gold} "
              f"deck {deck0}->{len(run.deck)} relics={len(run.relics)} "
              f"potions={[p.id for p in run.held_potions]} "
              f"removal_used={rem.used}   (C#: removal_used=True)")
    print("  removal entry class the port skips: "
          f"{MerchantCardRemovalEntry.__name__}; C# buys it last, "
          "cancelable:false, ignoreCost:true -- one free card removal per "
          "merchant visit, every visit.")


PROBES = {
    "b08-pool": probe_b08_pool,
    "b08-replay": probe_b08_replay,
    "b08-turn-reset": probe_b08_turn_reset,
    "b08-kusarigama": probe_b08_kusarigama,
    "b08-lantern": probe_b08_lantern,
    "b08-kifuda": probe_b08_kifuda,
    "b08-candy": probe_b08_candy,
    "b08-isallowed": probe_b08_isallowed,
    "b08-lavalamp": probe_b08_lavalamp,
    "b08-lavarock": probe_b08_lavarock,
    "b08-paperweight": probe_b08_paperweight,
    "b08-poultice": probe_b08_poultice,
    "b08-maxhp": probe_b08_maxhp,
    "b08-capsule": probe_b08_capsule,
    "b08-lizard": probe_b08_lizard,
    "b08-parasol": probe_b08_parasol,
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
