"""Reproducible execution probes for relic content audit BATCH 12.

Batch 12 covers the roster's `pen_nib` … `preserved_fog` run:
  pen_nib pendulum permafrost petrified_toad phial_holster
  philosophers_stone planisphere pocketwatch pollinous_core pomander
  potion_belt prayer_wheel precarious_shears precise_scissors preserved_fog

Own module per the batch-12 concurrency contract (`audit/tools/relic_probes.py`
is READ-ONLY to this batch — re-use it, do not edit it; in particular
`py audit/tools/relic_probes.py turn-order` is the executed hook-order
reference these records cite for their turn-hook mappings, and
`sweep-reset` / `sweep-reset-exec` are the pool-wide inputs the
`pendulum` / `pocketwatch` / `pollinous_core` / `permafrost` / `pen_nib`
records confirm).

Binding rules 5 and 6: never justify `faithful` with an unreachability claim
you have not EXECUTED, and never label a gap LIVE without proving both sides
reachable with ported content. Everything an `audit/records/relic/*.json` record from
this batch asserts about reachability is produced here.

  py audit/tools/relic_probes_b12.py               # every probe
  py audit/tools/relic_probes_b12.py b12-pool      # one probe

Probes:
  b12-pool          obtainability of batch 12's 15 relics (rule 6, first half)
  b12-permafrost    LIVE: `_activated` is never reset, so Permafrost grants its
                    7 Block in the FIRST combat of a run only. Corrects the
                    shared sweep-reset row `permafrost  C# resets: NONE`, which
                    is wrong — Permafrost.cs:35-43 assigns
                    `ActivatedThisCombat = false` in **AfterRoomEntered**, a
                    hook the sweep's C#-side census does not look at.
  b12-roomreset     the sweep's C#-side reset census filtered to four hooks;
                    rescan every relic's AfterRoomEntered body for a
                    combat-boundary assignment the census cannot see.
  b12-pennib        Pen Nib: the replayed-attack under-count (hook_dispatch G4
                    at a site that record already names) and the missing
                    `AttacksPlayed == 9` out-of-Play branch in the damage
                    PREVIEW the RL env consumes.
  b12-pocketwatch   Pocketwatch: the stale `_played_last_turn` IS shadowed by
                    the turn-1 guard (bug class 13 reader-trace, executed), but
                    a replayed card is under-counted.
  b12-pendulum      Pendulum: `turns_seen` carries into combat 2 and that is
                    INTENDED on both sides ([SavedProperty]; the C#
                    AfterCombatEnd assigns only base.Status). Same family as
                    happy_flower / fake_happy_flower.
  b12-pollinous     Pollinous Core: the same intended carry, plus the
                    reset-inside-the-modifier vs AfterModifyingHandDraw
                    equivalence.
  b12-stone         Philosopher's Stone: +1 energy, 1 Strength on every
                    starting enemy, 1 Strength on a mid-combat spawn, and no
                    double-application.
  b12-planisphere   Planisphere: the 5 HP heal on an Unknown map node never
                    lands, and the `IsAllowed` floor gate has no counterpart.
  b12-toad          Petrified Toad: the combat-side procure bypasses BOTH
                    Hook.ShouldProcurePotion (Sozu) and Hook.AfterPotionProcured
                    (Belt Buckle's Dexterity removal).
  b12-potionbelt    Potion Belt grants no potion slots, where the sibling
                    Phial Holster's port calls the very helper it needs.
  b12-phial         Phial Holster does not consume the CombatPotionGeneration
                    stream its C# names, and rolls a flat pool instead of the
                    rarity-weighted one.
  b12-prayer        Prayer Wheel adds no second card reward to a Monster screen.
  b12-cutters       Pomander / Precise Scissors / Precarious Shears / Preserved
                    Fog: the deck edits, the upgrade guard, the 16 damage and
                    the Folly curse.
  b12-cardremoved   `Hook.BeforeCardRemoved` has no sim dispatch at all, so the
                    three removal relics leave a removed Spoils Map's map quest
                    armed and the treasure node still pays 600 gold.
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

_GAME_ROOT = Path(r"C:\Users\Perry\Desktop\Slay the Spire 2")

BATCH12 = [
    "pen_nib", "pendulum", "permafrost", "petrified_toad", "phial_holster",
    "philosophers_stone", "planisphere", "pocketwatch", "pollinous_core",
    "pomander", "potion_belt", "prayer_wheel", "precarious_shears",
    "precise_scissors", "preserved_fog",
]


# ── b12-pool ──────────────────────────────────────────────────────────────
def probe_b12_pool() -> None:
    """Where each batch-12 relic can come from (binding rule 6, first half).

    Same method as `relic_probes.py pool`: grab-bag membership comes from
    relic_pools.py (the transcribed C# pools); every other grant path is a
    literal relic id somewhere else under sts2_rl/, so grep for it.
    """
    import subprocess

    from sts2_rl.relic_pools import IRONCLAD_RELIC_POOL, SHARED_RELIC_POOL
    from sts2_rl.relics import ALL_RELICS

    bag = {rid.removeprefix("RELIC.").lower(): rarity
           for rid, rarity in SHARED_RELIC_POOL + IRONCLAD_RELIC_POOL}
    for rid in BATCH12:
        srcs = subprocess.run(
            ["git", "grep", "-l", f'"{rid}"', "--", "sts2_rl"],
            capture_output=True, text=True, cwd=_REPO,
        ).stdout.split()
        srcs = [s for s in srcs if not s.endswith(f"relics/{rid}.py")]
        print(f"  {rid:<20} registered={rid in ALL_RELICS} "
              f"bag={bag.get(rid, '-'):<9} granted_by={srcs or ['(none)']}")


# ── b12-permafrost ────────────────────────────────────────────────────────
def probe_b12_permafrost() -> None:
    """Permafrost works in the FIRST combat of a run only (belt_buckle shape).

    Permafrost.cs:35-43 resets `ActivatedThisCombat = false` in
    **AfterRoomEntered**, which for a CombatRoom runs at CombatRoom.cs:228 —
    i.e. after the monsters are on the board and BEFORE
    `Hook.BeforeCombatStart` (CombatManager.cs:403). permafrost.py resets
    `_activated` nowhere, and relic instances live on RunState.relics and are
    re-attached to every new CombatState (run.py:1153), so combat 2 enters
    on_card_played with `_activated` already True.

    The first READER of the stale field is on_card_played itself, and nothing
    shadows it — which is the trace PROMPT.md bug class 13 requires.
    """
    from sts2_rl import CombatState
    from sts2_rl.cards import make_card
    from sts2_rl.relics import make_relic

    def play_a_power(cs):
        cs.player.hand.clear()
        cs.player.energy = 30
        cs.player.hand.append(make_card("inflame"))     # a ported Power card
        before = cs.player.block
        cs.play_card(0, 0)
        return before, cs.player.block

    carried = make_relic("permafrost")
    cs1 = CombatState(rng=random.Random(0), relics=[carried])
    b0, b1 = play_a_power(cs1)
    print(f"  combat 1: block {b0} -> {b1}   _activated={carried._activated}")

    cs2 = CombatState(rng=random.Random(1), relics=[carried])
    b0, b1 = play_a_power(cs2)
    print(f"  combat 2 (SAME instance): block {b0} -> {b1}   "
          f"_activated={carried._activated}")

    fresh = make_relic("permafrost")
    cs3 = CombatState(rng=random.Random(1), relics=[fresh])
    b0, b1 = play_a_power(cs3)
    print(f"  combat 2 (fresh instance): block {b0} -> {b1}")
    print("  C# gives 7 Block in EVERY combat; the carried instance gives 0.")


# ── b12-roomreset ─────────────────────────────────────────────────────────
def probe_b12_roomreset() -> None:
    """The shared sweep's C#-side reset census cannot see AfterRoomEntered.

    `relic_probes.py sweep-reset` builds its "C# resets" column from
    `_cs_overrides(...)` filtered to
    {BeforeCombatStart, AfterCombatEnd, AfterCombatVictory, AfterCombatDefeat}
    (relic_probes.py:735-737). A CombatRoom's `AfterRoomEntered` is ALSO a
    combat-boundary hook — CombatRoom.cs:197-231 dispatches it once the
    encounter's creatures are on the board — so a relic that resets there is
    reported as `C# resets: NONE (may be per-run by design)` and lands in the
    "decent evidence the state is per-run on both sides" bucket.

    This rescans every ported relic's AfterRoomEntered body for an assignment
    and prints the hits, so the miss is a number rather than an assertion.
    """
    import json

    roster = _REPO / "audits" / "relic"
    if not roster.is_dir():
        print("  (no relic records yet)")
        return

    # Resolve id -> C# path from the audit records that exist, and fall back to
    # a CamelCase guess for the ones that do not.
    paths: dict[str, Path] = {}
    for rec in sorted(roster.glob("*.json")):
        d = json.loads(rec.read_text(encoding="utf-8"))
        gs = d.get("game_source") or {}
        if gs.get("path"):
            paths[rec.stem] = _GAME_ROOT / gs["path"].replace("\\", "/")
    rel_dir = _GAME_ROOT / "src" / "Core" / "Models" / "Relics"
    if rel_dir.is_dir():
        for p in rel_dir.glob("*.cs"):
            rid = re.sub(r"(?<!^)(?=[A-Z])", "_", p.stem).lower()
            paths.setdefault(rid, p)

    hits = []
    for rid, p in sorted(paths.items()):
        if not p.is_file():
            continue
        text = p.read_text(encoding="utf-8-sig", errors="replace")
        m = re.search(r"AfterRoomEntered\([^)]*\)\s*\{", text)
        if m is None:
            continue
        # Brace-match the body.
        i = text.index("{", m.start())
        depth, j = 0, i
        while j < len(text):
            if text[j] == "{":
                depth += 1
            elif text[j] == "}":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        body = text[i + 1:j]
        assigns = [ln.strip() for ln in body.splitlines()
                   if re.match(r"^\s*[A-Za-z_][\w.<>]*\s*=\s*[^=]", ln)
                   and "==" not in ln.split("=")[0]]
        if assigns:
            hits.append((rid, p.name, assigns))

    print(f"  {len(paths)} C# relic files scanned; "
          f"{len(hits)} assign state inside AfterRoomEntered:")
    for rid, fn, assigns in hits:
        print(f"    {rid:<20} {fn:<24} {assigns}")
    print("  Any of these that the sweep printed as `C# resets: NONE` is a "
          "combat-boundary reset the sweep could not see.")


# ── b12-pennib ────────────────────────────────────────────────────────────
def probe_b12_pennib() -> None:
    """Pen Nib: the replay under-count, and the missing preview branch.

    (a) hook_dispatch G4 at a site that record already names: CardModel.cs:1929
        fires Hook.BeforeCardPlayed INSIDE the play-count loop, so a
        Throwing-Axe-replayed Strike advances AttacksPlayed by 2 in the game
        and by 1 in the sim (combat.py:466 is outside the loop). C# also fires
        AfterCardPlayed per iteration (:1959), so the game's 10th attack is
        doubled on iteration 0 only while the sim doubles every iteration.

    (b) PenNib.cs:120-128: when AttackToDouble is null, the relic returns 2m for
        any cardSource that is NOT in PileType.Play once AttacksPlayed == 9 —
        i.e. the pending 10th Attack's *displayed* damage. The sim's
        previews.preview_card_damage (previews.py:149-158, consumed by
        full_env.py:510) runs the same multiplicative chain, and pen_nib's port
        keys only on `card is self._card_to_double`, which is set only during
        the play.
    """
    from sts2_rl import CombatState
    from sts2_rl.cards import make_card
    from sts2_rl.previews import preview_card_damage
    from sts2_rl.relics import make_relic

    # (a) replayed attack
    nib = make_relic("pen_nib")
    cs = CombatState(rng=random.Random(0),
                     relics=[nib, make_relic("throwing_axe")])
    cs.enemies[0].hp = cs.enemies[0].max_hp = 400
    cs.player.hand.clear()
    cs.player.energy = 30
    cs.player.hand.append(make_card("strike"))
    cs.play_card(0, 0)
    print(f"  (a) one Throwing-Axe-replayed Strike: sim _attacks_played="
          f"{nib._attacks_played}  (C#: 2 -- one CardPlay per iteration)")

    # (a2) the 10th attack under a replay: how many hits get doubled
    nib2 = make_relic("pen_nib")
    cs2 = CombatState(rng=random.Random(0),
                      relics=[nib2, make_relic("throwing_axe")])
    cs2.enemies[0].hp = cs2.enemies[0].max_hp = 400
    nib2._attacks_played = 9          # the next Attack is the 10th
    cs2.player.hand.clear()
    cs2.player.energy = 30
    cs2.player.hand.append(make_card("strike"))
    hp_before = cs2.enemies[0].hp
    cs2.play_card(0, 0)
    print(f"  (a2) 10th Attack replayed twice: enemy HP loss="
          f"{hp_before - cs2.enemies[0].hp} "
          f"(sim doubles both passes; C# doubles pass 0 only)")

    # (b) the preview branch
    nib3 = make_relic("pen_nib")
    cs3 = CombatState(rng=random.Random(0), relics=[nib3])
    cs3.enemies[0].hp = cs3.enemies[0].max_hp = 400
    cs3.player.hand.clear()
    strike = make_card("strike")
    cs3.player.hand.append(strike)
    nib3._attacks_played = 9
    prev = preview_card_damage(cs3, strike, cs3.enemies[0])
    print(f"  (b) _attacks_played=9, Strike in HAND: "
          f"preview_card_damage={prev} (C# shows it doubled)")
    cs3.player.energy = 30
    hp_before = cs3.enemies[0].hp
    cs3.play_card(0, 0)
    print(f"      the DEALT damage is correct: enemy HP loss="
          f"{hp_before - cs3.enemies[0].hp}")


# ── b12-pocketwatch ───────────────────────────────────────────────────────
def probe_b12_pocketwatch() -> None:
    """Pocketwatch: the dropped AfterCombatEnd reset is shadowed; replays are not.

    Pocketwatch.cs:100-107 zeroes BOTH counters at combat end; the sim zeroes
    only `_played_this_turn`, at on_player_turn_start, and *copies* the stale
    value into `_played_last_turn` on combat 2's first turn. PROMPT.md bug
    class 13 wants the reader-trace: the only reader is modify_hand_draw, whose
    `self.turn == 1` guard (pocketwatch.py:38) bails before it reads the field,
    and turn 2 onward reads a value produced inside combat 2. Executed here.

    The live half is hook_dispatch G4: AfterCardPlayed fires per replay
    iteration in C# (CardModel.cs:1959) and once per play in the sim, so a
    replayed card can leave the sim under the `<= 3` threshold when the game is
    over it.
    """
    from sts2_rl import CombatState
    from sts2_rl.cards import make_card
    from sts2_rl.relics import make_relic

    watch = make_relic("pocketwatch")
    cs1 = CombatState(rng=random.Random(0), relics=[watch])
    cs1.enemies[0].hp = cs1.enemies[0].max_hp = 400
    cs1.player.hand.clear()
    cs1.player.energy = 60
    for _ in range(5):                       # 5 > THRESHOLD 3
        cs1.player.hand.append(make_card("strike"))
        cs1.play_card(len(cs1.player.hand) - 1, 0)
    print(f"  combat 1 after 5 plays: _played_this_turn="
          f"{watch._played_this_turn} _played_last_turn={watch._played_last_turn}")

    cs2 = CombatState(rng=random.Random(1), relics=[watch])
    fresh = make_relic("pocketwatch")
    cs2f = CombatState(rng=random.Random(1), relics=[fresh])
    print(f"  combat 2 turn 1 (carried): turn={cs2.turn} hand={len(cs2.player.hand)} "
          f"_played_last_turn={watch._played_last_turn}")
    print(f"  combat 2 turn 1 (fresh):   turn={cs2f.turn} hand={len(cs2f.player.hand)} "
          f"_played_last_turn={fresh._played_last_turn}")
    print(f"  turn-1 hands equal={len(cs2.player.hand) == len(cs2f.player.hand)} "
          f"-> the stale field is unreadable (turn == 1 guard)")

    # turn 2 of combat 2: both instances have only combat-2 history
    for cs in (cs2, cs2f):
        cs.end_turn()
    print(f"  combat 2 turn 2 hands: carried={len(cs2.player.hand)} "
          f"fresh={len(cs2f.player.hand)} "
          f"equal={len(cs2.player.hand) == len(cs2f.player.hand)}")

    # replay under-count
    w2 = make_relic("pocketwatch")
    cs3 = CombatState(rng=random.Random(0),
                      relics=[w2, make_relic("throwing_axe")])
    cs3.enemies[0].hp = cs3.enemies[0].max_hp = 400
    cs3.player.hand.clear()
    cs3.player.energy = 60
    for _ in range(3):
        cs3.player.hand.append(make_card("strike"))
        cs3.play_card(len(cs3.player.hand) - 1, 0)
    print(f"  3 plays, the first replayed by Throwing Axe: sim "
          f"_played_this_turn={w2._played_this_turn} (C#: 4 -> over the "
          f"threshold of 3)")
    # modify_hand_draw is a pure read on this relic, so evaluate it at both
    # counts rather than depending on how many cards the draw pile can supply.
    sim_count = w2._played_this_turn
    cs3.end_turn()                        # turn 2: the turn == 1 guard is past
    w2._played_last_turn = sim_count                     # what the sim carries
    sim_draw = w2.modify_hand_draw(cs3.player, 5)
    w2._played_last_turn = 4                            # what C# carries
    cs_draw = w2.modify_hand_draw(cs3.player, 5)
    print(f"  turn {cs3.turn} modify_hand_draw(5): sim={sim_draw} C#={cs_draw} "
          f"-- 3 extra cards the game withholds")


# ── b12-pendulum ──────────────────────────────────────────────────────────
def probe_b12_pendulum() -> None:
    """Pendulum's cross-combat carry is INTENDED on both sides.

    `relic_probes.py sweep-reset-exec` reports `pendulum self.turns_seen:
    1 -> 2`. The rewritten sweep A explains why that is not a gap: TurnsSeen is
    a [SavedProperty] (Pendulum.cs:60-73) and the file's only AfterCombatEnd
    body is `base.Status = RelicStatus.Normal` (Pendulum.cs:97-101), a display
    flag. Same family as happy_flower N1 / fake_happy_flower N1, which batch 7
    and batch 5 recorded `faithful`.

    What this probe adds is the OBSERVABLE: the extra card lands on the third
    player turn SEEN, counted across a combat boundary — which is the game's
    behaviour and not what the port's own docstring claims.
    """
    from sts2_rl import CombatState
    from sts2_rl.relics import make_relic

    carried = make_relic("pendulum")
    hands = []
    for i in range(3):
        cs = CombatState(rng=random.Random(i), relics=[carried])
        hands.append((i + 1, carried.turns_seen, len(cs.player.hand)))
    for combat, seen, hand in hands:
        print(f"  combat {combat} turn 1: turns_seen={seen} hand={hand}")
    print("  -> the +1 card lands in combat 3, i.e. on the 3rd turn seen "
          "across combats. C#: identical ([SavedProperty] TurnsSeen).")
    print(f"  the port's docstring says 'the sim's resets each combat' -- "
          f"class members starting on_combat: "
          f"{[m for m in dir(carried) if m.startswith('on_combat')]}")

    # The phase collapse (hook_dispatch G3) at this relic's slot. Pendulum's C#
    # hook is the PLAIN AfterPlayerTurnStart pass (Pendulum.cs:75); Bone Tea's
    # is AfterSideTurnStart (BoneTea.cs:51), a LATER dispatcher, so the game
    # always draws Pendulum's card BEFORE Bone Tea upgrades the opening hand.
    # The sim collapses both onto on_player_turn_started, one walk in relic
    # order, so the outcome depends on pickup order. The carried counter is what
    # lets Pendulum fire on turn 1 at all.
    from sts2_rl.cards import make_card

    for order in (["pendulum", "bone_tea"], ["bone_tea", "pendulum"]):
        relics = [make_relic(r) for r in order]
        pend = next(r for r in relics if r.id == "pendulum")
        pend.turns_seen = 2          # as a carried instance entering combat 3
        cs = CombatState(rng=random.Random(0),
                         starting_deck=[make_card("strike") for _ in range(12)],
                         relics=relics)
        levels = sorted(c.upgrade_level for c in cs.player.hand)
        print(f"  order {order}: turn-1 hand={len(cs.player.hand)} "
              f"upgrade levels={levels}")
    print("  C# in BOTH orders: 6 cards, all 6 upgraded (Pendulum's plain "
          "AfterPlayerTurnStart pass completes before AfterSideTurnStart).")


# ── b12-pollinous ─────────────────────────────────────────────────────────
def probe_b12_pollinous() -> None:
    """Pollinous Core: the intended carry, and the reset-site equivalence.

    C# increments TurnsSeen in BeforeSideTurnStart, adds Cards(2) in
    ModifyHandDraw when TurnsSeen == Turns(4), and zeroes it in
    AfterModifyingHandDraw. Hook.AfterModifyingHandDraw (Hook.cs:739-749) is
    dispatched ONLY to listeners whose ModifyHandDraw actually changed the
    count (Hook.cs:1684-1696 collects them), so the reset happens exactly when
    the bonus was granted. The sim has no after_modifying_hand_draw hook at all
    and performs the reset inside modify_hand_draw under the same condition.
    """
    from sts2_rl import CombatState
    from sts2_rl.relics import make_relic

    core = make_relic("pollinous_core")
    cs = CombatState(rng=random.Random(0), relics=[core])
    cs.enemies[0].hp = cs.enemies[0].max_hp = 999
    for turn in range(1, 7):
        print(f"  combat 1 turn {turn}: turns_seen={core.turns_seen} "
              f"hand={len(cs.player.hand)}")
        cs.end_turn()

    # the carry: leave combat 1 mid-cycle and enter combat 2
    core2 = make_relic("pollinous_core")
    cs1 = CombatState(rng=random.Random(0), relics=[core2])
    cs1.enemies[0].hp = cs1.enemies[0].max_hp = 999
    cs1.end_turn()
    cs1.end_turn()                     # turns_seen == 3 after turn 3 starts
    left_with = core2.turns_seen
    cs2 = CombatState(rng=random.Random(1), relics=[core2])
    print(f"  left combat 1 with turns_seen={left_with}; combat 2 turn 1: "
          f"turns_seen={core2.turns_seen} hand={len(cs2.player.hand)}")
    fresh = make_relic("pollinous_core")
    csf = CombatState(rng=random.Random(1), relics=[fresh])
    print(f"  fresh instance combat 1 turn 1: hand={len(csf.player.hand)}  "
          f"-> carry changes WHICH turn draws, as the [SavedProperty] does")


# ── b12-stone ─────────────────────────────────────────────────────────────
def probe_b12_stone() -> None:
    """Philosopher's Stone: energy, starting-enemy Strength, spawn Strength.

    C# splits the work: AfterRoomEntered(CombatRoom) strengthens every living
    opponent already on the board, and AfterCreatureAddedToCombat strengthens
    each later joiner. The sim maps the first onto on_combat_start and the
    second onto on_creature_added. The two cannot double-apply on either side:
    CreatureCmd.AddCreature (CreatureCmd.cs:55-81) throws unless
    CombatManager.IsInProgress, so the starting creatures never reach
    Hook.AfterCreatureAddedToCombat, and the sim only dispatches
    on_creature_added from cmds.py:266 (the mid-combat spawn path).
    """
    from sts2_rl import CombatState
    from sts2_rl.cmds import CreatureCmd
    from sts2_rl.monsters import SpinyToad
    from sts2_rl.relics import make_relic

    cs = CombatState(rng=random.Random(0), relics=[make_relic("philosophers_stone")])
    print(f"  starting enemies: "
          f"{[(e.name, e.powers.get('strength')) for e in cs.enemies]}")
    print(f"  turn-1 energy: {cs.player.energy} (base "
          f"{cs.player.ENERGY_PER_TURN})")

    spawn = SpinyToad(cs.hooks, random.Random(0))
    CreatureCmd.add(cs.hooks, spawn)
    print(f"  mid-combat spawn {spawn.name}: "
          f"strength={spawn.powers.get('strength')} "
          f"(one application, not two)")

    cs_none = CombatState(rng=random.Random(0), relics=[])
    print(f"  without the relic: "
          f"{[(e.name, e.powers.get('strength')) for e in cs_none.enemies]} "
          f"energy={cs_none.player.energy}")


# ── b12-planisphere ───────────────────────────────────────────────────────
def probe_b12_planisphere() -> None:
    """Planisphere: no heal on an Unknown node, and no `IsAllowed` gate.

    Planisphere.cs:23-34 heals HealVar(5) whenever the owner enters a room
    while `RunState.CurrentMapPoint.PointType == MapPointType.Unknown`. The
    port is a behaviourless stub whose docstring calls it "an out-of-combat map
    effect" — but `Relic.after_room_entered(run, point, room_type)` exists
    (relics/base.py:194-195) and run.py:983 dispatches it with the map point
    itself, which carries `point_type`. Sweep C's premise test applies.

    Planisphere.cs:18-21 also overrides IsAllowed -> IsBeforeAct3TreasureChest
    (TotalFloor < 41); sweep B's 17-relic cluster. Executed here at floor 60.
    """
    from sts2_rl.run import RunState

    # (a) the heal
    run = RunState(rng=random.Random(3))
    run.add_relic("planisphere")
    run.hp = run.max_hp - 30
    hp0 = run.hp
    fired: list = []
    relic = run.relics[-1]
    orig = relic.after_room_entered
    relic.after_room_entered = lambda *a, **k: (fired.append(a), orig(*a, **k))[1]
    from sts2_rl.actmap import MapPointType

    entered_unknown = False
    for seed in range(30):
        run = RunState(rng=random.Random(seed))
        run.add_relic("planisphere")
        run.hp = run.max_hp - 30
        fired: list = []
        relic = run.relics[-1]
        orig = relic.after_room_entered
        relic.after_room_entered = (
            lambda *a, _o=orig, _f=fired, **k: (_f.append(a), _o(*a, **k))[1])
        run.start_act("overgrowth")
        walker = random.Random(seed)
        for _ in range(20):
            opts = run.travelable_points()
            if not opts:
                break
            nxt = next((p for p in opts
                        if p.point_type == MapPointType.UNKNOWN),
                       walker.choice(opts))
            hp0 = run.hp
            run.enter_point(nxt)
            if nxt.point_type == MapPointType.UNKNOWN:
                print(f"  seed {seed}: entered an UNKNOWN node at floor "
                      f"{run.total_floor}: hp {hp0} -> {run.hp}  (C#: +5)")
                print(f"  after_room_entered dispatched {len(fired)} time(s); "
                      f"last call point_type={fired[-1][1].point_type.name}, "
                      f"resolved room_type={fired[-1][2].name}")
                entered_unknown = True
                break
        if entered_unknown:
            break
    if not entered_unknown:
        print("  (no Unknown node reached in 30 seeds)")

    # (b) the IsAllowed floor gate
    from sts2_rl.relics.base import Relic
    print(f"  Relic base has is_allowed member: {hasattr(Relic, 'is_allowed')}")
    run2 = RunState(rng=random.Random(4))
    run2.total_floor = 60
    seen = 0
    for _ in range(400):
        r = run2.pull_relic_from_front()
        if r is None:
            break
        if r.id == "planisphere":
            seen += 1
            break
    print(f"  at total_floor=60 the grab bag still yields planisphere: "
          f"{bool(seen)} (C#: IsAllowed false from floor 41)")


def _first_unknown_point(run):
    from sts2_rl.actmap import MapPointType
    for p in run.travelable_points():
        if p.point_type == MapPointType.UNKNOWN:
            return p
    return None


# ── b12-toad ──────────────────────────────────────────────────────────────
def probe_b12_toad() -> None:
    """Petrified Toad's procure skips both hooks PotionCmd.TryToProcure runs.

    PotionCmd.TryToProcure (PotionCmd.cs:28-53) consults
    `Hook.ShouldProcurePotion` first and fires `Hook.AfterPotionProcured` on
    success. petrified_toad.py:20 calls PlayerCombatState.add_potion, whose own
    docstring (player.py:112-115) says the combat-side path runs neither.

    Sozu is ported (relics/sozu.py:26 returns False from
    should_procure_potion) and Belt Buckle's AfterPotionProcured is already
    recorded LIVE in audit/records/relic/belt_buckle.json, so both triggers exist.
    """
    from sts2_rl import CombatState
    from sts2_rl.relics import make_relic

    cs = CombatState(rng=random.Random(0),
                     relics=[make_relic("petrified_toad")])
    print(f"  toad alone: belt={[type(p).__name__ for p in cs.player.potions]}")

    cs2 = CombatState(rng=random.Random(0),
                      relics=[make_relic("petrified_toad"), make_relic("sozu")])
    print(f"  toad + SOZU: belt={[type(p).__name__ for p in cs2.player.potions]} "
          f"(C#: Hook.ShouldProcurePotion refuses it, belt stays empty)")

    # The Late phase is load-bearing here (hook_dispatch G3): C# runs EVERY
    # BeforeCombatStart listener, THEN every BeforeCombatStartLate one
    # (Hook.cs:311-323), so Belt Buckle always applies its Dexterity first and
    # the Toad's procure always strips it. The sim collapses both onto
    # on_combat_start, a single pass in relic-list order, so the outcome depends
    # on which relic was picked up first.
    for order in (["belt_buckle", "petrified_toad"],
                  ["petrified_toad", "belt_buckle"]):
        cs3 = CombatState(rng=random.Random(0),
                          relics=[make_relic(r) for r in order])
        print(f"  order {order}: dexterity="
              f"{cs3.player.powers.get('dexterity')} "
              f"held={len(cs3.player.held_potions)}")
    print("  C# in BOTH orders: 1 potion held and 0 Dexterity.")


# ── b12-potionbelt ────────────────────────────────────────────────────────
def probe_b12_potionbelt() -> None:
    """Potion Belt grants no slots; the sibling Phial Holster's port does.

    PotionBelt.cs:19-22 is a single PlayerCmd.GainMaxPotionCount(2). The port
    is a behaviourless stub calling it "an out-of-combat capacity change", but
    run.add_potion_slots exists (run.py:492-498) and phial_holster.py:18 calls
    it for the identical C# call — sweep C's premise test again.
    """
    from sts2_rl.run import RunState

    for rid in (None, "potion_belt", "phial_holster", "alchemical_coffer"):
        run = RunState(rng=random.Random(5))
        base = run.max_potions
        if rid:
            run.add_relic(rid)
        print(f"  relic={str(rid):<20} max_potions {base} -> {run.max_potions} "
              f"held={len(run.held_potions)}")
    print("  C#: potion_belt -> 5 slots.")


# ── b12-phial ─────────────────────────────────────────────────────────────
def probe_b12_phial() -> None:
    """Phial Holster does not consume the CombatPotionGeneration stream.

    PhialHolster.cs:29 names `RunState.Rng.CombatPotionGeneration` explicitly
    and goes through PotionFactory.CreateRandomPotionsOutOfCombat, which is a
    rarity roll (NextFloat) plus a NextItem inside that rarity's bucket, per
    potion (PotionFactory.cs:67-81). phial_holster.py:19 calls
    run.random_potions(2, distinct=True), which is a flat uniform pick on the
    LEGACY shared run.rng (run.py:522-540). The correct helper already exists
    and the sibling relic with the identical C# call uses it
    (alchemical_coffer.py:25-31 -> potion_pools.generate_random_potions).
    PROMPT.md bug class 16, second half.
    """
    from sts2_rl.run import RunState

    run = RunState(rng=random.Random(11), string_seed="B12PROBE")
    pos_before = _stream_pos(run, "combat_potion_generation")
    run.add_relic("phial_holster")
    pos_after = _stream_pos(run, "combat_potion_generation")
    print(f"  phial_holster: max_potions={run.max_potions} "
          f"potions={[type(p).__name__ for p in run.held_potions]}")
    print(f"  CombatPotionGeneration stream draws: {pos_before} -> {pos_after} "
          f"(C#: 4 -- two per potion)")

    run2 = RunState(rng=random.Random(11), string_seed="B12PROBE")
    p0 = _stream_pos(run2, "combat_potion_generation")
    run2.add_relic("alchemical_coffer")
    print(f"  alchemical_coffer (correct sibling, 4 potions): stream draws "
          f"{p0} -> {_stream_pos(run2, 'combat_potion_generation')}")


def _stream_pos(run, name: str):
    if getattr(run, "rng_set", None) is None:
        return "(no rng_set)"
    rng = getattr(run.rng_set, name)
    for attr in ("counter", "_counter", "draws", "_draws", "position"):
        if hasattr(rng, attr):
            return getattr(rng, attr)
    return "(no counter attr)"


# ── b12-prayer ────────────────────────────────────────────────────────────
def probe_b12_prayer() -> None:
    """Prayer Wheel adds no second card reward to a Monster reward screen.

    PrayerWheel.cs:14-26 appends `new CardReward(CardCreationOptions.ForRoom(
    player, RoomType.Monster), 3, player)` to every Monster room's reward list.
    The port is a behaviourless stub calling it "an out-of-combat reward
    modifier", but rewards.py:499-500 dispatches
    relic.modify_combat_rewards(run, rewards) over the run's relics — the exact
    hook, already used by five other relics.
    """
    from sts2_rl.rewards import generate_combat_rewards
    from sts2_rl.rooms import RoomType
    from sts2_rl.run import RunState

    for relics in ([], ["prayer_wheel"]):
        run = RunState(rng=random.Random(9))
        for rid in relics:
            run.add_relic(rid)
        rw = generate_combat_rewards(run, RoomType.MONSTER)
        print(f"  relics={relics or ['(none)']} cards={len(rw.cards)} "
              f"special_cards={len(rw.special_cards)} "
              f"ids={[c.id for c in rw.cards]}")
    # and the elite/boss guard
    run = RunState(rng=random.Random(9))
    run.add_relic("prayer_wheel")
    rw = generate_combat_rewards(run, RoomType.ELITE)
    print(f"  ELITE screen with the relic: cards={len(rw.cards)} "
          f"(C#: unchanged -- RoomType.Monster only)")
    print("  C# with the relic: a SECOND 3-card choice on Monster screens.")


# ── b12-cutters ───────────────────────────────────────────────────────────
def probe_b12_cutters() -> None:
    """The four deck-editing pickups: Pomander / Scissors / Shears / Fog.

    Checks the counts, the upgrade guard (PROMPT.md bug class 14: the sim's
    Card.upgrade() has no IsUpgradable guard, so the CANDIDATE LIST has to
    carry it -- run.upgradable_cards() does), the 16 HP damage, and that the
    Folly curse joins the deck through run.add_card's two deck hooks.
    """
    from sts2_rl.cards import make_card
    from sts2_rl.run import RunState

    # Pomander: never upgrades a max_upgrade_level == 0 card
    run = RunState(rng=random.Random(1))
    run.deck.append(make_card("curse_of_the_bell"))     # max_upgrade_level 0
    curse = run.deck[-1]
    n_upgradable = len(run.upgradable_cards())
    run.add_relic("pomander")
    ups = [(c.id, c.upgrade_level) for c in run.deck if c.upgrade_level > 0]
    print(f"  pomander: upgradable candidates={n_upgradable} "
          f"upgraded={ups} curse_level={curse.upgrade_level} "
          f"(C#: CardCmd.Upgrade skips !IsUpgradable)")

    # Precise Scissors: one removal
    run = RunState(rng=random.Random(1))
    n0 = len(run.deck)
    run.add_relic("precise_scissors")
    print(f"  precise_scissors: deck {n0} -> {len(run.deck)}")

    # Precarious Shears: two removals + 16 damage
    run = RunState(rng=random.Random(1))
    n0, hp0 = len(run.deck), run.hp
    run.add_relic("precarious_shears")
    print(f"  precarious_shears: deck {n0} -> {len(run.deck)}  "
          f"hp {hp0} -> {run.hp} (C#: -16)")

    # Preserved Fog: three removals + Folly
    run = RunState(rng=random.Random(1))
    n0 = len(run.deck)
    hooks_seen: list[str] = []

    from sts2_rl.relics.base import Relic, RelicRarity

    class _Spy(Relic):
        id = "_spy"
        name = "spy"
        rarity = RelicRarity.COMMON

        def after_card_added_to_deck(self, run, card):
            hooks_seen.append(card.id)

    run.relics.append(_Spy())
    run.add_relic("preserved_fog")
    print(f"  preserved_fog: deck {n0} -> {len(run.deck)} "
          f"folly_in_deck={'folly' in [c.id for c in run.deck]} "
          f"after_card_added_to_deck fired for={hooks_seen}")
    print("  C#: 3 removals via CardPileCmd.RemoveFromDeck then "
          "AddCurseToDeck<Folly>.")


# ── b12-cardremoved ───────────────────────────────────────────────────────
def probe_b12_cardremoved() -> None:
    """`Hook.BeforeCardRemoved` has no sim dispatch, and removing a Spoils Map
    therefore leaves its map quest live and still pays 600 gold.

    All four relics in this batch that edit the deck go through
    CardPileCmd.RemoveFromDeck, which fires
    `await Hook.BeforeCardRemoved(card.Owner.RunState, card)`
    (src/Core/Commands/CardPileCmd.cs:61) before unlinking the card. The whole
    game has exactly ONE implementer -- SpoilsMap.BeforeCardRemoved
    (src/Core/Models/Cards/SpoilsMap.cs:100-115), which calls
    `Map.GetPoint(SpoilsCoord)?.RemoveQuest(this)`. `grep -rn
    'before_card_removed' sts2_rl/` returns nothing, and RunState.remove_cards
    (run.py:356-358) is a bare `deck.remove`, so the quest marker survives.
    """
    from sts2_rl.cards import make_card
    from sts2_rl.run import RunState

    for remove in (False, True):
        run = RunState(rng=random.Random(2))
        smap = make_card("spoils_map")
        run.deck.append(smap)
        run.start_act("underdocks", act_index=1)
        point = None
        if smap.spoils_coord is not None and run.map is not None:
            point = run.map.get_point(*smap.spoils_coord)
        if remove:
            run.remove_cards([smap])
        in_deck = smap in run.deck
        marker = bool(point is not None and point.quests)
        gold0 = run.gold
        paid = run._complete_map_point_quests(point) if point is not None else None
        print(f"  removed_from_deck={remove!s:<5} in_deck={in_deck!s:<5} "
              f"quest marker on the treasure node BEFORE entering={marker!s:<5} "
              f"gold {gold0} -> {run.gold} (paid={paid})")
    print("  C# with the removal: Hook.BeforeCardRemoved clears the marker, so "
          "the node pays nothing.")


PROBES = {
    "b12-pool": probe_b12_pool,
    "b12-permafrost": probe_b12_permafrost,
    "b12-roomreset": probe_b12_roomreset,
    "b12-pennib": probe_b12_pennib,
    "b12-pocketwatch": probe_b12_pocketwatch,
    "b12-pendulum": probe_b12_pendulum,
    "b12-pollinous": probe_b12_pollinous,
    "b12-stone": probe_b12_stone,
    "b12-planisphere": probe_b12_planisphere,
    "b12-toad": probe_b12_toad,
    "b12-potionbelt": probe_b12_potionbelt,
    "b12-phial": probe_b12_phial,
    "b12-prayer": probe_b12_prayer,
    "b12-cutters": probe_b12_cutters,
    "b12-cardremoved": probe_b12_cardremoved,
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
