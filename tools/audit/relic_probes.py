"""Reproducible execution probes for the relic content audits.

Companion to `tools/audit/dormancy_probes.py` (which serves the seam tier).
Every claim an `audits/relic/*.json` record makes about *reachability* — "this
gap is live", "this waiver's trigger cannot occur" — is produced here, so a
later auditor re-derives the number instead of trusting a throwaway script.
Binding rules 5 and 6 of the shared audit contract: never justify `faithful`
with an unreachability claim you have not EXECUTED, and never label a gap LIVE
without proving both sides reachable with ported content.

  py tools/audit/relic_probes.py                  # every probe
  py tools/audit/relic_probes.py lamp-replay      # one probe

Probes (batch 1 = the Tier 1 pilot):
  pool             obtainability of the pilot batch's 16 relics
  turn-order       the sim's actual relic-hook order across a turn boundary
  lamp-replay      unsettling_lamp G1 — doubling survives every Replay pass
  lamp-self-debuff unsettling_lamp G2 — ported cards that debuff the player
  lamp-temporary   unsettling_lamp N3 — ported ITemporaryPower counterparts
  aubergine-gold   amethyst_aubergine G1 — reward gold with vs without it
  mushroom-hp      big_mushroom G1 — +20 Max HP on the add_relic path
  buckle-potion    belt_buckle G1 — Dexterity when a potion is procured

POOL-WIDE SWEEPS (all 258 relics at once). The pilot batch found that its live
gaps cluster into a few repeating SHAPES rather than sixteen unique bugs, so
each sweep chases one shape across the whole roster before the per-unit batches
run — the batches then confirm rather than discover. Findings are triaged in
`.superpowers/sdd/content-relic-sweeps.md`; these probes produce the raw hits.

  sweep-reset      per-combat state the sim never resets (belt_buckle shape)
  sweep-isallowed  C# IsAllowed/IsAllowedAtNeow pool gates vs the sim
  sweep-stubs      behaviourless relic ports whose C# has real hooks
  sweep-upgrade    unguarded Card.upgrade() call sites (class 14)
  sweep-clone      shallow card rebuilds vs CreateClone (class 17)

Per-batch probes:
  batch2           reachability evidence for batch 2's live gaps
  batch3           reachability evidence for batch 3's live gaps
  batch3-pool      obtainability of batch 3's 15 relics
"""
from __future__ import annotations

import argparse
import ast
import inspect
import random
import re
import sys
import textwrap
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

# The pilot batch: the roster's first 15 relics alphabetically plus the
# design document's worked example.
BATCH1 = [
    "akabeko", "alchemical_coffer", "amethyst_aubergine", "anchor",
    "arcane_scroll", "archaic_tooth", "art_of_war", "astrolabe",
    "bag_of_marbles", "bag_of_preparation", "beating_remnant",
    "beautiful_bracelet", "bellows", "belt_buckle", "big_mushroom",
    "unsettling_lamp",
]


# ── pool ──────────────────────────────────────────────────────────────────
def probe_pool() -> None:
    """Where each pilot-batch relic can come from.

    Rule 6 wants "the relic obtainable" proved, not asserted. Grab-bag
    membership comes from relic_pools.py (the transcribed C# pools); every
    other source is a literal id somewhere in sts2_rl/, so grep for it.
    """
    import subprocess

    from sts2_rl.relic_pools import IRONCLAD_RELIC_POOL, SHARED_RELIC_POOL
    from sts2_rl.relics import ALL_RELICS

    bag = {rid.removeprefix("RELIC.").lower(): rarity
           for rid, rarity in SHARED_RELIC_POOL + IRONCLAD_RELIC_POOL}
    print(f"grab-bag pool: {len(bag)} relics "
          f"({len(SHARED_RELIC_POOL)} shared + {len(IRONCLAD_RELIC_POOL)} Ironclad)")
    for rid in BATCH1:
        registered = rid in ALL_RELICS
        srcs = subprocess.run(
            ["git", "grep", "-l", f'"{rid}"', "--", "sts2_rl"],
            capture_output=True, text=True, cwd=_REPO,
        ).stdout.split()
        srcs = [s for s in srcs if not s.endswith(f"relics/{rid}.py")]
        print(f"  {rid:<20} registered={registered} bag={bag.get(rid, '-'):<9} "
              f"granted_by={srcs or ['(none)']}")


# ── turn-order ────────────────────────────────────────────────────────────
def probe_turn_order() -> None:
    """The sim's relic-facing hook order across a turn boundary.

    Records for akabeko / anchor / art_of_war / bag_of_marbles /
    bag_of_preparation / beating_remnant / bellows map C# turn hooks onto sim
    ones; this prints what the sim actually fires, so the mapping claims are
    executed rather than read off relics/base.py's docstring (which states the
    order incorrectly for on_player_turn_start — see PROMPT.md bug class 11).
    """
    from sts2_rl import CombatState
    from sts2_rl.relics.base import Relic, RelicRarity

    seen: list[str] = []

    class Spy(Relic):
        id, name, rarity = "_spy", "Spy", RelicRarity.COMMON

        def on_combat_start(self):
            seen.append("on_combat_start")

        def on_block_cleared(self, target):
            seen.append(f"on_block_cleared(turn={self.turn})")

        def on_energy_reset(self, player):
            seen.append(f"on_energy_reset(turn={self.turn})")

        def on_player_turn_start(self, player):
            seen.append(f"on_player_turn_start(turn={self.turn})")

        def modify_hand_draw(self, player, count):
            seen.append(f"modify_hand_draw(turn={self.turn})")
            return count

        def on_player_turn_started(self, player):
            seen.append(f"on_player_turn_started(turn={self.turn}, "
                        f"hand={len(self.player.hand)})")
            return None

        def on_player_turn_end(self, player):
            seen.append(f"on_player_turn_end(turn={self.turn})")

    cs = CombatState(rng=random.Random(0), relics=[Spy()])
    cs.end_turn()
    for line in seen:
        print("  " + line)
    print("\n  C# order (audits/seam/turn_structure.json steps 9-23):")
    print("    BeforeSideTurnStart -> ClearBlock -> AfterBlockCleared -> "
          "energy -> AfterEnergyReset")
    print("    -> BeforeHandDraw -> ModifyHandDraw -> Draw "
          "-> AfterPlayerTurnStart -> AfterSideTurnStart")


# ── lamp-replay ───────────────────────────────────────────────────────────
def probe_lamp_replay() -> None:
    """Unsettling Lamp x a Replay source.

    C#: Hook.AfterCardPlayed fires once per Replay iteration inside the
    play-count loop (CardModel.cs:1904-1963), so UnsettlingLamp.AfterCardPlayed
    sets IsFinishedTriggering after iteration 0 and iteration 1 is NOT doubled.
    The sim fires on_card_played once, after the whole loop (combat.py:477-514),
    so the Lamp doubles every iteration. Throwing Axe is the ported replay
    source used here; Spiral/Glam enchantments and Hidden Gem reach the same
    play-count path.
    """
    from sts2_rl import CombatState
    from sts2_rl.cards import make_card
    from sts2_rl.relics import make_relic

    for relics, label in (
        ([make_relic("unsettling_lamp")], "Lamp alone"),
        ([make_relic("unsettling_lamp"), make_relic("throwing_axe")],
         "Lamp + Throwing Axe (first play is played twice)"),
    ):
        cs = CombatState(rng=random.Random(0), relics=relics)
        card = make_card("bash")
        cs.player.energy = 10
        cs.player.hand.append(card)
        cs.play_card(len(cs.player.hand) - 1, 0)
        vuln = cs.enemy.powers.get("vulnerable")
        print(f"  {label:<48} Vulnerable={vuln.amount if vuln else 0}")
    print("  Bash applies 2 Vulnerable. Expected: 4 alone; C# 4+2=6 with the "
          "Axe (iteration 1 already finished the relic).")


# ── lamp-self-debuff ──────────────────────────────────────────────────────
def probe_lamp_self_debuff() -> None:
    """Ported cards that apply a Debuff to the player.

    C#'s ModifyPowerAmountGivenMultiplicative (UnsettlingLamp.cs:106-129) has
    NO target-side guard — only the latch (BeforePowerAmountChanged) checks
    `target.Side == Owner.Creature.Side`. So a card that debuffs an enemy and
    then debuffs the PLAYER has BOTH doubled in C#. The sim's
    modify_power_amount bails on `target is self.player` (unsettling_lamp.py:47),
    so the self-debuff is never doubled. This probe lists the ported cards
    whose source applies a Debuff to the player, i.e. the reachability
    population for that divergence.
    """
    import re

    from sts2_rl.cards.base import _CARD_CLASSES
    from sts2_rl.powers import ALL_POWERS, PowerType
    import sts2_rl.cards  # noqa: F401  (registration)

    debuffs = {pid for pid, cls in ALL_POWERS.items()
               if getattr(cls, "power_type", None) == PowerType.DEBUFF}
    hits = []
    for cid, cls in sorted(_CARD_CLASSES.items()):
        try:
            src = inspect.getsource(cls)
        except OSError:                                  # pragma: no cover
            continue
        # PowerCmd.apply(..., <player-ish target>, SomePower, ...)
        for m in re.finditer(r"PowerCmd\.apply\(\s*[^,]+,\s*([^,]+),\s*(\w+)",
                             src):
            target, power = m.group(1).strip(), m.group(2)
            if "player" not in target and "self.owner" not in target:
                continue
            pid = re.sub(r"(?<!^)(?=[A-Z])", "_", power).lower()
            pid = pid.removesuffix("_power")
            if pid in debuffs:
                hits.append((cid, power))
    for cid, power in hits:
        print(f"  {cid:<28} applies {power} to the player")
    print(f"  {len(hits)} ported card(s) apply a Debuff to the player.")
    print("  A divergence needs ONE card doing both in a single play; a card "
          "that only self-debuffs never latches the Lamp.")


# ── lamp-temporary ────────────────────────────────────────────────────────
def probe_lamp_temporary() -> None:
    """The ported ITemporaryPower counterparts and their applier handling.

    audits/seam/power_cmd.json guard N2 verified by execution that the sim's
    TemporaryStrengthPower / TemporaryDexterityPower reach C#'s
    HasDoubledTemporaryPowerSource outcome by omitting `applier` on the
    internal application. That argument only covers the Lamp if it holds for
    EVERY ported ITemporaryPower — so enumerate both sides.
    """
    from sts2_rl import powers as sim_powers

    from tools.audit.harness import DEFAULT_GAME_ROOT

    print("  C# Powers/*.cs mentioning ITemporaryPower:")
    for path in sorted((DEFAULT_GAME_ROOT / "src/Core/Models/Powers").glob("*.cs")):
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        if "ITemporaryPower" not in text:
            continue
        internal = [ln.strip() for ln in text.splitlines()
                    if "InternallyAppliedPower =>" in ln]
        print(f"    {path.name:<30} "
              f"{internal[0] if internal else '(reference only, not an impl)'}")
    # PiercingWailPower extends TemporaryStrengthPower, so it inherits the
    # interface without naming it.
    for name in ("PiercingWailPower",):
        text = (DEFAULT_GAME_ROOT
                / f"src/Core/Models/Powers/{name}.cs").read_text(
                    encoding="utf-8-sig", errors="replace")
        base = next(ln.strip() for ln in text.splitlines() if "class " in ln)
        print(f"    {name + '.cs':<30} inherits: {base}")

    print("\n  sim counterparts and their internal application:")
    for cname in ("TemporaryStrengthPower", "TemporaryDexterityPower",
                  "PiercingWailPower", "TemporaryFocusPower"):
        cls = getattr(sim_powers, cname, None)
        if cls is None:
            print(f"    {cname:<24} NOT PORTED")
            continue
        applies = [ln.strip() for ln in inspect.getsource(cls).splitlines()
                   if "PowerCmd.apply" in ln]
        print(f"    {cname:<24} passes applier: "
              f"{any('applier' in ln for ln in applies)}   {applies}")


# ── aubergine-gold ────────────────────────────────────────────────────────
def probe_aubergine_gold() -> None:
    """Amethyst Aubergine's +15 gold on a combat reward screen.

    C#: TryModifyRewards adds a GoldReward(15) to every combat room's rewards
    (AmethystAubergine.cs:25-45). The sim registers the relic as a no-op stub
    whose docstring claims "the sim has no gold" — but rewards.py:462-500 rolls
    gold, grants it, and then runs relic.modify_combat_rewards over the run's
    relics, which is exactly the hook the port needs.
    """
    from sts2_rl.rewards import generate_combat_rewards
    from sts2_rl.rooms import RoomType
    from sts2_rl.run import RunState

    for relics in ([], ["amethyst_aubergine"]):
        run = RunState(rng=random.Random(7))
        for rid in relics:
            run.add_relic(rid)
        before = run.gold
        rewards = generate_combat_rewards(run, RoomType.MONSTER)
        print(f"  relics={relics or ['(none)']:} "
              f"rewards.gold={rewards.gold} run.gold delta={run.gold - before}")
    print("  C# grants 15 more with the relic; equal numbers = the gap.")


# ── mushroom-hp ───────────────────────────────────────────────────────────
def probe_mushroom_hp() -> None:
    """Big Mushroom's +20 Max HP when the relic is granted via add_relic.

    BigMushroom.cs:24-28 raises Max HP by 20 in AfterObtained. The sim's relic
    has no after_obtained; the Hungry for Mushrooms event applies the +20
    itself, so the event path matches. Every OTHER grant path — notably the
    conformance runner's relic resync (conformance/runner.py:465, 698, 751) —
    calls run.add_relic(id) and gets no Max HP.
    """
    from sts2_rl.run import RunState

    run = RunState(rng=random.Random(0))
    base = run.max_hp
    run.add_relic("big_mushroom")
    print(f"  add_relic('big_mushroom'):        max_hp {base} -> {run.max_hp}")

    run2 = RunState(rng=random.Random(0))
    base2 = run2.max_hp
    run2.add_relic("fragrant_mushroom")
    print(f"  add_relic('fragrant_mushroom'):   hp {run2.STARTING_HP} -> "
          f"{run2.hp}, max_hp {base2} -> {run2.max_hp}  "
          f"(sibling relic DOES use after_obtained)")

    from sts2_rl.events.base import make_event
    run3 = RunState(rng=random.Random(0))
    base3 = run3.max_hp
    ev = make_event("hungry_for_mushrooms", run3)
    ev.begin()
    ev.choose("BIG_MUSHROOM")
    print(f"  via HungryForMushrooms event:     max_hp {base3} -> {run3.max_hp}"
          f"  (the event applies the +20 itself, not the relic)")


# ── buckle-potion ─────────────────────────────────────────────────────────
def probe_buckle_potion() -> None:
    """Belt Buckle's Dexterity when a potion is procured mid-combat.

    BeltBuckle.cs:63-70 removes the 2 Dexterity on AfterPotionProcured while
    combat is in progress; the sim's port (belt_buckle.py) implements only
    on_combat_start and on_potion_used, so a potion picked up mid-combat leaves
    the Dexterity in place.
    """
    from sts2_rl import CombatState
    from sts2_rl.potions import make_potion
    from sts2_rl.relics import make_relic

    buckle = make_relic("belt_buckle")
    cs = CombatState(rng=random.Random(0), relics=[buckle])
    dex = cs.player.powers.get("dexterity")
    print(f"  combat 1 start, no potions:  Dexterity="
          f"{dex.amount if dex else 0}")
    cs.player.add_potion(make_potion("block_potion"))
    dex = cs.player.powers.get("dexterity")
    print(f"  after procuring a potion:    Dexterity="
          f"{dex.amount if dex else 0}   (C# AfterPotionProcured: 0)")

    # The same relic instance carries into the run's next combat, exactly as
    # RunState.relics does. C# clears DexterityApplied in BeforeCombatStart
    # (BeltBuckle.cs:49) and again in AfterCombatVictory (line 92).
    cs2 = CombatState(rng=random.Random(1), relics=[buckle])
    dex = cs2.player.powers.get("dexterity")
    print(f"  combat 2 start, no potions:  Dexterity="
          f"{dex.amount if dex else 0}   (C#: 2)  _applied="
          f"{buckle._applied}")


# ══════════════════════════════════════════════════════════════════════════
# Pool-wide sweeps
# ══════════════════════════════════════════════════════════════════════════

# Attributes sts2_rl.relics.base.Relic.__init__ sets on every relic.
_BASE_ATTRS = {"combat", "is_wax"}

# The sim hooks that run at a COMBAT boundary, i.e. the places a per-combat
# field may legitimately be cleared. `attach` is included because CombatState
# calls it once per combat when wiring the listener.
#
# `__init__` is deliberately NOT here. It runs ONCE PER RUN, when
# RunState.add_relic constructs the relic -- treating it as a reset is exactly
# the mistake that makes relic/belt_buckle look clean when it is the pilot's
# highest-impact live gap.
_COMBAT_BOUNDARY = {"on_combat_start", "on_combat_end", "attach"}

# Hooks that run at the START of the player's turn. A field cleared here is
# not reset at the combat boundary, but the stale value is unreadable: combat
# 2's turn 1 runs these before any reader, so the relic self-heals.
# relic/art_of_war is the pilot's example.
_TURN_START = {
    "on_player_turn_start", "on_player_turn_started",
    "on_energy_reset", "on_block_cleared",
}

# Hooks that run at the END of a turn. A reset here is NOT equivalent to a
# turn-start reset and must never be treated as one.
#
# `CombatState.end_turn` opens with `if self.phase != Phase.PLAYER_TURN:
# return` (combat.py:639-642), so on the turn that WINS the fight the whole
# turn-end pass is skipped and the reset never runs. The field then crosses
# into combat 2 with combat 1's final value and is read at combat 2's turn 1,
# before any turn end. relic/diamond_diadem is the executed witness: its
# `cards_played_this_turn` arrives at 3 and its "played <= 2 cards" bonus is
# withheld in a fight where the game grants it.
#
# The first version of this sweep pooled these with _TURN_START and filed all
# 21 hits as "safe only if the turn reset runs before any reader" -- a
# condition it then never tested. Four of the five batch-4..8 audits faulted
# it. Splitting the two is the fix; `sweep-reset-exec` now executes both.
_TURN_END = {"on_player_turn_end", "on_enemy_side_end"}

# C# members that DECLARE a property rather than implement behaviour. A relic
# port that overrides only these is not thereby a no-op.
_DECLARATIVE_CS = {
    "Rarity", "IsAllowedInShops", "HasUponPickupEffect", "AddsPet",
    "SpawnsPets", "MerchantCost", "IsTradable", "IsUsedUp", "IsWax",
    "DisplayAmount", "HasDisplayAmount", "IsAllowedAtNeow", "IsAllowed",
    "CanonicalVars", "ExtraHoverTips", "Description", "Title",
}

# C# RUN-level hooks the sim's Relic base already provides a method for
# (sts2_rl/relics/base.py). A behaviourless port whose C# overrides one of
# these is claiming the sim cannot do something the sim demonstrably can.
_RUN_HOOK_MAP = {
    "AfterObtained": "after_obtained",
    "AfterRoomEntered": "after_room_entered",
    "AfterShopEntered": "after_shop_entered",
    "AfterItemPurchased": "after_item_purchased",
    "AfterCardChangedPiles": "after_card_added_to_deck",
    "ModifyGoldGained": "modify_gold_gained",
    "ShouldProcurePotion": "should_procure_potion",
    "AfterRestSiteHeal": "after_rest_site_heal",
    "TryModifyRestSiteOptions": "modify_rest_site_options",
    "ShouldDisableRemainingRestSiteOptions":
        "should_disable_remaining_rest_site_options",
    "TryModifyRestSiteHealRewards": "modify_rest_site_heal_rewards",
    "AfterCombatEnd": "after_combat_end",
    "ShouldAllowFreeTravel": "should_allow_free_travel",
    "ShouldForcePotionReward": "should_force_potion_reward",
    "ShouldGenerateTreasure": "should_generate_treasure",
    "TryModifyRewards": "modify_combat_rewards",
    "ModifyRewards": "modify_combat_rewards",
    "TryModifyRewardsLate": "modify_combat_rewards",
    "TryModifyCardRewardOptionsLate": "modify_card_reward_options",
    "ModifyMerchantCardCreationResults": "modify_merchant_card_results",
    "ModifyCardBeingAddedToDeck": "modify_card_being_added_to_deck",
    "ModifyGeneratedMap": "modify_generated_map",
    "ModifyGeneratedMapLate": "modify_generated_map_late",
    "AfterMapGenerated": "after_map_generated",
    "ModifyUnknownMapPointRoomTypes": "modify_unknown_map_point_room_types",
}


def _relic_roster() -> list[dict]:
    from tools.audit.harness import roster
    return roster("relic")


def _cs_overrides(game_path: str) -> list[str]:
    from tools.audit.harness import DEFAULT_GAME_ROOT, list_overrides
    p = DEFAULT_GAME_ROOT / game_path
    if not p.is_file():
        return []
    return list_overrides(p.read_text(encoding="utf-8-sig", errors="replace"))


def _snake(pascal: str) -> str:
    """`ModifyDamageAdditive` -> `modify_damage_additive`.

    Sweep C compared a PascalCase C# hook name against snake_case keys taken
    from `vars(HookSystem)`, so its "is this a HookSystem combat hook?" branch
    could never be true and every dropped combat hook outside `_RUN_HOOK_MAP`
    was silently skipped. `mystic_lighter`'s `ModifyDamageAdditive` was filed as
    "not a HookSystem hook, larger than a one-relic fix" when `hooks.py:52`
    defines it and `cmds.py:57` dispatches it. Found by batches 9 and 10
    independently; the third UNDER-report across the sweeps, which is the
    direction nothing downstream catches.
    """
    return re.sub(r"(?<!^)(?=[A-Z])", "_", pascal).lower()


def _cs_method_body(text: str, name: str) -> str | None:
    """The braced body of C# member `name`, brace-matched.

    Both sweeps used to read C# bodies with a `[^\\n;]*` capture, i.e. the
    first line only. That silently truncates every multi-clause body:
    LastingCandy.IsAllowed opens with a multi-line `runState.Players.Any(...)`
    unlock test and only RETURNS IsBeforeAct3TreasureChest at the end, so
    sweep-isallowed filed it as an unlock gate and under-reported the
    floor-gate cluster as 16 relics when it is 17. An under-report is worse
    than an over-report: nothing in the pipeline catches it.
    """
    m = re.search(
        r"(?:public|protected|private|internal)[\w\s]*?\b"
        + re.escape(name) + r"\s*(?:\([^)]*\))?\s*\{", text)
    if m is None:
        return None
    i = text.index("{", m.end() - 1)
    depth = 0
    for j in range(i, len(text)):
        if text[j] == "{":
            depth += 1
        elif text[j] == "}":
            depth -= 1
            if depth == 0:
                return text[i + 1:j]
    return None


def _cs_body_assignments(body: str) -> list[str]:
    """Assignment statements in a C# body, normalized to one line each.

    `sweep-reset`'s "C# resets" column was a *census of overrides* -- it proved
    only that the relic overrides BeforeCombatStart/AfterCombatEnd, never that
    the body assigns anything. It therefore credited relics that override a
    boundary hook for an unrelated reason (fishing_rod, fur_coat) with a reset
    they do not perform. This turns the column into evidence.
    """
    out = []
    for line in body.splitlines():
        s = line.strip().rstrip(";")
        if not s or s.startswith("//"):
            continue
        if re.match(r"^[\w.\[\]]+\s*(?:=|\+=|-=)\s*[^=]", s):
            out.append(s)
    return out


def _class_node(cls) -> ast.ClassDef | None:
    try:
        src = textwrap.dedent(inspect.getsource(cls))
    except OSError:                                      # pragma: no cover
        return None
    for node in ast.parse(src).body:
        if isinstance(node, ast.ClassDef):
            return node
    return None


def _own_classes(cls) -> list[type]:
    """`cls` and every ancestor BELOW sts2_rl.relics.base.Relic.

    Several relics implement their behaviour in a shared intermediate base --
    relics/_eggs.py's EggRelic serves frozen_egg / toxic_egg / molten_egg, and
    the Fake Merchant knock-offs subclass their originals. Reading only
    `cls`'s own body reports those as behaviourless stubs, which is wrong: an
    early version of this sweep flagged all three eggs, whose ports are
    complete. Walk the MRO instead.
    """
    from sts2_rl.relics.base import Relic
    return [c for c in cls.__mro__
            if issubclass(c, Relic) and c is not Relic]


def _own_methods(cls) -> dict[str, ast.FunctionDef]:
    """Every method `cls` defines or inherits from a non-`Relic` ancestor."""
    out: dict[str, ast.FunctionDef] = {}
    for klass in reversed(_own_classes(cls)):
        node = _class_node(klass)
        if node is None:
            continue
        for f in node.body:
            if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)):
                out[f.name] = f
    return out


def _is_reset_value(attr: str, value: ast.expr) -> bool:
    """Is `self.<attr> = value` a RESET rather than an accumulate?

    A reset stores a fresh zero-ish constant. `self.turns_seen =
    self.turns_seen + 1` is a plain ast.Assign too, and the first version of
    this sweep counted it as a reset -- so relic/happy_flower was filed as
    "reset at a turn boundary" when the write is an INCREMENT and the field
    never returns to 0. Batch 7 caught it.
    """
    if any(isinstance(n, ast.Attribute) and n.attr == attr
           for n in ast.walk(value)):
        return False                       # references itself: accumulate
    if isinstance(value, ast.Constant):
        return value.value in (0, False, None, "") or value.value == 0
    if isinstance(value, (ast.List, ast.Dict, ast.Set)):
        return not getattr(value, "elts", None) and not getattr(
            value, "keys", None)
    if isinstance(value, ast.Call):        # set(), list(), dict()
        return (isinstance(value.func, ast.Name)
                and value.func.id in ("set", "list", "dict")
                and not value.args)
    return False


def _ctor_param_fields(cls) -> dict[str, str]:
    """`self.X = <param>` fields in __init__, mapped to the parameter name.

    THE BLIND SPOT this closes: `sweep-reset` diffs a field across two combats,
    so a field that is NEVER WRITTEN anywhere looks identical on both instances
    and the sweep clears it. But `RunState.add_relic` builds relics with
    `make_relic(id)` -> `_RELIC_CLASSES[id]()` (relics/base.py:74) and passes no
    arguments, so such a field is frozen at its default for the whole run and
    the relic is inert. venerable_tea_set and fake_venerable_tea_set both hold
    their entire trigger in one of these; batch 5 executed the second and found
    the relic does nothing in any run that buys it.

    Girya is the near-miss that fixes the detector's shape: `times_lifted` is
    also a constructor parameter, but `_lift()` does `times_lifted += 1` from a
    rest-site option, so the field has a real in-run source and the relic works.
    The defect is specific to a field whose ONLY non-constructor writes are
    clears -- then no code path can ever make it truthy.
    """
    out: dict[str, str] = {}
    for klass in _own_classes(cls):
        node = _class_node(klass)
        if node is None:
            continue
        for f in node.body:
            if not isinstance(f, ast.FunctionDef) or f.name != "__init__":
                continue
            params = {a.arg for a in f.args.args} - {"self"}
            for stmt in ast.walk(f):
                if not isinstance(stmt, ast.Assign):
                    continue
                names = {n.id for n in ast.walk(stmt.value)
                         if isinstance(n, ast.Name)}
                if not (names & params):
                    continue
                for t in stmt.targets:
                    if (isinstance(t, ast.Attribute)
                            and isinstance(t.value, ast.Name)
                            and t.value.id == "self"):
                        out[t.attr] = sorted(names & params)[0]
    return out


def _only_ever_cleared(cls, attr: str) -> bool:
    """True if every write to `self.<attr>` outside __init__ is a reset.

    Such a field can never become truthy at runtime: its only non-clearing
    source is the constructor parameter, which nothing passes.
    """
    for name, fn in _own_methods(cls).items():
        if name == "__init__":
            continue
        for n in ast.walk(fn):
            if isinstance(n, ast.AugAssign):
                t = n.target
                if (isinstance(t, ast.Attribute) and t.attr == attr
                        and isinstance(t.value, ast.Name)
                        and t.value.id == "self"):
                    return False
            elif isinstance(n, ast.Assign):
                for t in n.targets:
                    if (isinstance(t, ast.Attribute) and t.attr == attr
                            and isinstance(t.value, ast.Name)
                            and t.value.id == "self"
                            and not _is_reset_value(attr, n.value)):
                        return False
    return True


def _self_writes(fn: ast.FunctionDef) -> tuple[set[str], set[str]]:
    """(plain-assigned, augmented-assigned) `self.X` names anywhere in fn."""
    plain: set[str] = set()
    aug: set[str] = set()
    for node in ast.walk(fn):
        targets = []
        if isinstance(node, ast.Assign):
            targets = [(t, plain) for t in node.targets]
        elif isinstance(node, ast.AugAssign):
            targets = [(node.target, aug)]
        for tgt, bucket in targets:
            if (isinstance(tgt, ast.Attribute)
                    and isinstance(tgt.value, ast.Name)
                    and tgt.value.id == "self"):
                bucket.add(tgt.attr)
    return plain, aug


# ── sweep-reset ───────────────────────────────────────────────────────────
def probe_sweep_reset() -> None:
    """Per-combat relic state the sim never clears at a combat boundary.

    THE SHAPE (relic/belt_buckle G2, the pilot's highest-impact live gap):
    sim relic instances live on RunState.relics and are re-attached to every
    new CombatState, so a field set during combat 1 and never cleared is still
    set in combat 2. C# clears such fields in BeforeCombatStart and/or
    AfterCombatEnd/AfterCombatVictory. Belt Buckle dropped BOTH and became a
    first-combat-only relic; Art of War and Unsettling Lamp dropped one and are
    safe because another reset runs before any reader.

    A hit is NOT automatically a gap -- PROMPT.md bug class 13 says trace to
    the first READER of the stale field. This sweep produces the candidate
    list; `.superpowers/sdd/content-relic-sweeps.md` carries the triage.
    """
    from sts2_rl.relics import ALL_RELICS

    from tools.audit.harness import DEFAULT_GAME_ROOT

    rows = {r["unit"].split("/", 1)[1]: r for r in _relic_roster()}
    hits, shadowed, frozen, clean, stateless = [], [], [], [], 0

    for rid, cls in sorted(ALL_RELICS.items()):
        methods = _own_methods(cls)
        if not methods and _class_node(cls) is None:
            continue
        writers: dict[str, set[str]] = {}
        reset_at_combat: set[str] = set()
        reset_at_turn_start: set[str] = set()
        reset_at_turn_end: set[str] = set()
        in_play: set[str] = set()
        for name, fn in methods.items():
            plain, aug = _self_writes(fn)
            for attr in plain | aug:
                writers.setdefault(attr, set()).add(name)
            # Only a write that stores a fresh zero-ish constant is a RESET;
            # `self.x = self.x + 1` is a plain Assign and an accumulate.
            resets = {a for a in plain if any(
                _is_reset_value(a, n.value) for n in ast.walk(fn)
                if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Attribute) and t.attr == a
                        for t in n.targets))}
            if name in _COMBAT_BOUNDARY:
                reset_at_combat |= resets
            if name in _TURN_START:
                reset_at_turn_start |= resets
            if name in _TURN_END:
                reset_at_turn_end |= resets
            if name not in _COMBAT_BOUNDARY and name != "__init__":
                in_play |= plain | aug

        # A field held ONLY in a constructor parameter is never written at all,
        # so no cross-combat diff can see it -- and make_relic passes no args,
        # so it is frozen at its default. Report it before the state test.
        ctor = _ctor_param_fields(cls)
        never_written = {a: p for a, p in ctor.items()
                         if _only_ever_cleared(cls, a)}
        if never_written:
            frozen.append((rid, never_written,
                           sorted(set(methods) - {"__init__"})))

        state = (in_play | set(writers)) - _BASE_ATTRS
        if not state:
            stateless += 1
            continue
        unreset = (in_play - _BASE_ATTRS) - reset_at_combat
        if not unreset:
            clean.append(rid)
            continue

        # 'C# resets' must be EVIDENCE, not a census of overrides. Show the
        # assignments the boundary override actually makes; an override with no
        # assignment in its body is not a reset.
        boundary: dict[str, list[str]] = {}
        row = rows.get(rid)
        if row is not None:
            p = DEFAULT_GAME_ROOT / row["game_path"]
            if p.is_file():
                text = p.read_text(encoding="utf-8-sig", errors="replace")
                for h in _cs_overrides(row["game_path"]):
                    # AfterRoomEntered belongs here: for a CombatRoom, C# fires
                    # it right after SetUpCombat and BEFORE Hook
                    # .BeforeCombatStart (CombatRoom.cs:228), so it is a
                    # combat-entry reset site like any other. Omitting it made
                    # the census print "C# resets: NONE (may be per-run by
                    # design)" for permafrost, whose AfterRoomEntered does
                    # exactly `ActivatedThisCombat = false` -- and the sweeps
                    # doc then filed it as evidence the state was per-run on
                    # both sides. It is a LIVE gap. Sixth sweep-A defect, found
                    # by batch 12; the third that produced a false CLEAR.
                    if h not in ("BeforeCombatStart", "AfterCombatEnd",
                                 "AfterCombatVictory", "AfterCombatDefeat",
                                 "AfterRoomEntered"):
                        continue
                    body = _cs_method_body(text, h)
                    if body is None:
                        continue
                    assigns = _cs_body_assignments(body)
                    if assigns:
                        boundary[h] = assigns

        entry = (rid, sorted(unreset), boundary,
                 sorted(unreset & reset_at_turn_start),
                 sorted(unreset & reset_at_turn_end),
                 {a: sorted(writers[a]) for a in sorted(unreset)})
        # SAFE only if every unreset field is cleared at turn START. A field
        # cleared only at turn END is NOT safe -- see _TURN_END. And a frozen
        # constructor field is not "safely reset", it is DEAD: reporting the
        # tea sets as safe was the misleading half of the old output.
        if never_written:
            pass                          # already reported under FROZEN
        elif unreset and unreset <= reset_at_turn_start:
            shadowed.append(entry)
        else:
            hits.append(entry)

    print(f"  {len(ALL_RELICS)} sim relics: {stateless} hold no state, "
          f"{len(clean)} reset every mid-combat field at a combat boundary, "
          f"{len(shadowed)} reset every one at TURN START (safe), "
          f"{len(hits)} do not")
    print("\n  NEVER RESET BEFORE A READER (candidate belt_buckle shape). "
          "'C# resets' now lists the ASSIGNMENTS the C# boundary\n"
          "  override actually makes -- an override with no assignment is not "
          "a reset, which the override-census version got wrong:")
    for rid, unreset, boundary, t_start, t_end, who in hits:
        print(f"    {rid:<26} {unreset}")
        print(f"    {'':<26} written by: "
              f"{'; '.join(f'{a}<-{w}' for a, w in who.items())}")
        if t_end:
            print(f"    {'':<26} !! reset at TURN END only: {t_end} -- "
                  f"end_turn early-returns on the winning turn, so this "
                  f"crosses into the next combat")
        if t_start:
            print(f"    {'':<26} (partly reset at turn start: {t_start})")
        print(f"    {'':<26} C# resets: "
              f"{boundary or 'NONE (may be per-run by design)'}")
    print("\n  RESET AT TURN START, BEFORE ANY READER (art_of_war shape -- "
          "genuinely safe: combat 2's turn 1 clears it first):")
    for rid, unreset, boundary, t_start, _t_end, _who in shadowed:
        # Batch 10 caught this: the brace-matched assignment evidence was wired
        # into the hits bucket only, so THIS bucket still printed a bare hook
        # name and implied a reset that may not exist -- ornamental_fan's
        # AfterCombatEnd assigns only `IsActivating = false`, a glow flag.
        ev = "; ".join(f"{h}: {a}" for h, a in sorted(boundary.items()))
        print(f"    {rid:<26} {unreset} turn-start-reset={t_start} "
              f"C# resets: {ev or 'NONE'}")
    print(f"\n  FROZEN CONSTRUCTOR STATE ({len(frozen)}): the field is written "
          f"ONLY in __init__ from a parameter, and make_relic\n"
          f"  (relics/base.py:74) passes no arguments -- so it holds its "
          f"default for the whole run and no\n"
          f"  cross-combat diff can see it. Check whether the relic can fire "
          f"at all:")
    for rid, nw, others in frozen:
        print(f"    {rid:<26} "
              f"{', '.join(f'self.{a} <- {p}' for a, p in sorted(nw.items()))}"
              f"   other methods: {others or 'NONE'}")

    graded = sorted({h[0] for h in hits if h[2]}
                    | {h[0] for h in hits if h[4]}
                    | {f[0] for f in frozen})
    print(f"\n  PRIORITISED for `sweep-reset-exec` ({len(graded)}): every "
          f"candidate whose C# counterpart really assigns at a combat\n"
          f"  boundary, PLUS every turn-END-only reset, PLUS every frozen "
          f"constructor field. The first version ran only\n"
          f"  the first group, which is why the turn-boundary bucket went "
          f"21-relics-unexecuted:")
    print(f"    {graded}")
    return graded


# ── sweep-reset-exec ──────────────────────────────────────────────────────
def probe_sweep_reset_exec() -> None:
    """Execute the sweep-reset candidates: does state survive a combat?

    `sweep-reset` is a static AST scan and cannot tell a genuine per-run
    counter (Girya's lifts) from a stale per-combat flag (Belt Buckle's
    `_applied`). This probe settles it the way the pilot settled belt_buckle,
    generically: run one relic instance through a combat, start a SECOND combat
    with the same instance, and diff its fields against a freshly-constructed
    instance entering its first combat. Any field that differs is state the sim
    carries across a combat boundary and C# does not.

    A difference is still not automatically a gap -- PROMPT.md bug class 13
    says trace to the first READER -- but it converts "read 32 relics" into
    "read the handful that actually diverge".
    """
    import contextlib
    import io

    from sts2_rl import CombatState
    from sts2_rl.relics import make_relic

    with contextlib.redirect_stdout(io.StringIO()):
        candidates = probe_sweep_reset()

    def _snapshot(relic, cs) -> dict:
        """The relic's own fields PLUS the combat state it can move.

        Belt Buckle is the reason the player half is here: its stale `_applied`
        settles at True on both instances, so a fields-only diff calls it clean
        while the OBSERVABLE -- 2 Dexterity granted or not -- diverges.
        """
        snap = {f"self.{k}": repr(v) for k, v in vars(relic).items()
                if k not in _BASE_ATTRS and not k.startswith("__")}
        p = cs.player
        snap["player.powers"] = repr(
            sorted((pid, pw.amount) for pid, pw in p.powers.items()))
        snap["player.block"] = repr(p.block)
        snap["player.energy"] = repr(p.energy)
        snap["player.hp"] = repr(p.hp)
        snap["player.hand"] = repr(len(p.hand))
        snap["enemy.powers"] = repr(
            sorted((pid, pw.amount) for pid, pw in cs.enemy.powers.items()))
        return snap

    def _stimulate(cs) -> None:
        """Give combat 1 enough stimulus to LATCH a trigger-gated field.

        THE FIFTH DEFECT, found by batch 13 and the dangerous kind: the original
        driver built a CombatState, called end_turn a few times, and applied no
        stimulus at all -- full HP, no card ever played, no Strength, no run
        context. A field whose write is gated on a trigger the driver never
        produces therefore reads identical on BOTH instances, so the executed
        pass filed it under "agrees with a fresh instance" and OVERRODE the
        static bucket's correct warning. It false-cleared red_skull,
        ruined_helmet and pumpkin_candle; the first two are live gaps, and
        red_skull's is severe (combat 2 at full HP opens with Strength -3,
        because the un-reset `_applied` makes the relic subtract a bonus it
        never granted).

        This is distinct from FROZEN CONSTRUCTOR STATE: that field is never
        written by anything, this one is written only under a condition. A
        false CLEAR is worse than a false hit -- nothing downstream re-checks it.
        """
        from sts2_rl.cmds import DamageCmd, PowerCmd
        from sts2_rl.powers import StrengthPower
        p = cs.player
        with contextlib.suppress(Exception):
            # Below the half-HP thresholds several relics gate on (red_skull).
            DamageCmd.deal(cs.hooks, p, max(1, int(p.max_hp * 0.62)), cs.enemy)
        with contextlib.suppress(Exception):
            # A positive Strength for the relics that consume or clamp one
            # (ruined_helmet).
            PowerCmd.apply(cs.hooks, p, StrengthPower, 2, applier=p)
        with contextlib.suppress(Exception):
            if p.hand:
                cs.play_card(0, 0)

    diverged, agreed, errored, blind = [], [], [], []
    for rid in candidates:
        try:
            carried = make_relic(rid)
            virgin = {k: repr(v) for k, v in vars(make_relic(rid)).items()
                      if k not in _BASE_ATTRS}
            def _fields():
                return {k: repr(v) for k, v in vars(carried).items()
                        if k not in _BASE_ATTRS}

            cs1 = CombatState(rng=random.Random(0), relics=[carried])
            _stimulate(cs1)
            # Sample EVERY step, not just the end. A per-turn field that the
            # stimulus writes and the next turn-start hook clears is back at its
            # virgin value by the end of the loop, so an end-only check calls it
            # unlatched -- which is how paels_legion's `cooldown` (0 -> 2 on a
            # card play, cleared each turn) stayed misreported after the first
            # attempt at this fix.
            latched = _fields() != virgin
            for _ in range(3):
                if cs1.is_over:
                    break
                cs1.end_turn()
                latched = latched or _fields() != virgin
            # Combat 2 with the SAME instance, exactly as RunState.relics does.
            cs2 = CombatState(rng=random.Random(1), relics=[carried])
            fresh = make_relic(rid)
            cs_fresh = CombatState(rng=random.Random(1), relics=[fresh])
            # Stimulate BOTH sides of combat 2 identically before snapshotting.
            # Comparing only the construction-time state misses every relic
            # whose stale field changes what a card DOES rather than what the
            # field reads: paels_legion enters combat 2 with cooldown 2 vs 0,
            # which is invisible until a Defend is played (block 5 vs 10, batch
            # 11's executed evidence). Same stimulus, same rng, so any delta is
            # attributable to the carried state.
            _stimulate(cs2)
            _stimulate(cs_fresh)
            a, b = _snapshot(carried, cs2), _snapshot(fresh, cs_fresh)
            delta = {k: (b.get(k), a.get(k)) for k in a | b.keys()
                     if a.get(k) != b.get(k)}
            if delta:
                diverged.append((rid, delta))
            elif not latched:
                blind.append(rid)
            else:
                agreed.append((rid, delta))
        except Exception as exc:                          # pragma: no cover
            errored.append((rid, f"{type(exc).__name__}: {exc}"))

    print(f"  {len(candidates)} candidate(s) executed: {len(diverged)} carry "
          f"state into combat 2, {len(agreed)} SHOW NO DELTA UNDER THIS "
          f"STIMULUS, {len(blind)} INCONCLUSIVE (driver never latched the "
          f"field), {len(errored)} could not be driven")
    if agreed:
        print("\n  NO DELTA UNDER THIS STIMULUS -- this is NOT a clean bill. "
              "This bucket is known to contain live gaps:\n"
              "  diamond_diadem (batch 4, LIVE: the stale count is read at "
              "combat 2's turn 1, which needs a WON combat 1 --\n"
              "  and the driver breaks out before end_turn when the fight is "
              "over, so it can never produce that) and\n"
              "  paels_legion (batch 11, LIVE: cooldown 2 vs 0 changes what a "
              "Defend DOES, block 5 vs 10). Treat every unit\n"
              "  here as UNAUDITED. The sweep generates candidates; only a "
              "purpose-built probe clears one:")
        for rid, _ in agreed:
            print(f"    {rid}")
    print("\n  CARRIES STATE ACROSS THE COMBAT BOUNDARY "
          "(field: fresh-instance value -> carried-instance value):")
    for rid, delta in diverged:
        for k, (fresh_v, carried_v) in delta.items():
            print(f"    {rid:<26} {k}: {fresh_v} -> {carried_v}")
    if blind:
        print("\n  INCONCLUSIVE -- combat 1 never wrote the field, so the diff "
              "proves NOTHING. Do NOT read this as clean:\n"
              "  the stimulus this driver supplies (damage to ~38% HP, +2 "
              "Strength, one card played) was not enough to latch it,\n"
              "  or the trigger is a RUN-level hook (after_obtained, "
              "after_combat_end) that a bare CombatState never fires.\n"
              "  Audit these by hand with a purpose-built probe:")
        for rid in blind:
            print(f"    {rid}")
    if errored:
        print("\n  NOT DRIVEN (needs a run/room context this probe does not "
              "build -- audit by hand):")
        for rid, err in errored:
            print(f"    {rid:<26} {err}")


# ── sweep-isallowed ───────────────────────────────────────────────────────
def probe_sweep_isallowed() -> None:
    """C# RelicModel.IsAllowed / IsAllowedAtNeow gates vs the sim.

    THE SHAPE (relic/amethyst_aubergine, a live gap): C# relics can refuse to
    spawn under run conditions (IsBeforeAct3TreasureChest, deck contents, ...).
    The sim's Relic base has `is_allowed_at_neow` (relics/base.py:159) but NO
    `is_allowed` member at all, and relic_pools.populate_relic_grab_bags
    shuffles the pool once at run init with no per-pull filter. So every
    IsAllowed override is unmodelled, and the pool composition diverges for the
    whole rest of the run once one is reached.
    """
    from sts2_rl.relics import ALL_RELICS, base as relic_base

    print(f"  sim Relic base defines is_allowed: "
          f"{hasattr(relic_base.Relic, 'is_allowed')}")
    print(f"  sim Relic base defines is_allowed_at_neow: "
          f"{hasattr(relic_base.Relic, 'is_allowed_at_neow')}")

    rows = {r["unit"].split("/", 1)[1]: r for r in _relic_roster()}
    from tools.audit.harness import DEFAULT_GAME_ROOT

    n_allowed, n_neow = [], []
    for rid in sorted(ALL_RELICS):
        row = rows.get(rid)
        if row is None:
            continue
        p = DEFAULT_GAME_ROOT / row["game_path"]
        if not p.is_file():
            continue
        text = p.read_text(encoding="utf-8-sig", errors="replace")
        body = {}
        for name in ("IsAllowed", "IsAllowedAtNeow"):
            if not re.search(r"public override bool " + name + r"\(", text):
                continue
            # Brace-matched, NOT first-line. The first-line capture missed every
            # clause after the opening statement and under-reported the
            # IsBeforeAct3TreasureChest cluster as 16 relics when it is 17.
            full = _cs_method_body(text, name)
            if full is None:
                continue
            clauses = [ln.strip().rstrip(";") for ln in full.splitlines()
                       if ln.strip() and not ln.strip().startswith("//")]
            body[name] = clauses
        if "IsAllowed" in body:
            n_allowed.append((rid, body["IsAllowed"]))
        if "IsAllowedAtNeow" in body:
            n_neow.append((rid, body["IsAllowedAtNeow"],
                           ALL_RELICS[rid].is_allowed_at_neow))

    def _summarize(clauses: list[str]) -> tuple[str, bool]:
        """(one-line gist, is_multi_clause). Names EVERY gate, not the first."""
        gates = []
        joined = " ".join(clauses)
        if "IsBeforeAct3TreasureChest" in joined:
            gates.append("IsBeforeAct3TreasureChest (TotalFloor < 41)")
        if "UnlockState" in joined or "NumberOfRuns" in joined:
            gates.append("UnlockState/NumberOfRuns gate")
        for m in re.finditer(r"\b([A-Z]\w+)\s*\(", joined):
            g = m.group(1)
            if g not in ("Any", "Where", "Select", "Count", "Contains",
                         "IsBeforeAct3TreasureChest") and g not in gates:
                gates.append(g + "(...)")
        n = len([c for c in clauses if c.startswith("return")])
        return ("; ".join(gates) or joined[:70]), n > 1

    print(f"\n  {len(n_allowed)} ported relic(s) override IsAllowed -- "
          f"ALL unmodelled (no sim concept exists). '**' marks a MULTI-CLAUSE\n"
          f"  body, where the first-line reader saw only the first gate:")
    floor_cluster = []
    for rid, clauses in n_allowed:
        gist, multi = _summarize(clauses)
        if "IsBeforeAct3TreasureChest" in " ".join(clauses):
            floor_cluster.append(rid)
        print(f"    {'**' if multi else '  '} {rid:<26} {gist}")
    print(f"\n  IsBeforeAct3TreasureChest cluster: {len(floor_cluster)} "
          f"relic(s) -- {floor_cluster}")
    print(f"\n  {len(n_neow)} ported relic(s) override IsAllowedAtNeow "
          f"(the sim HAS this flag -- check each value):")
    for rid, clauses, simval in n_neow:
        gist, _ = _summarize(clauses)
        print(f"    {rid:<28} C#: {gist:<52} sim is_allowed_at_neow={simval}")


# ── sweep-stubs ───────────────────────────────────────────────────────────
def probe_sweep_stubs() -> None:
    """Behaviourless relic ports whose C# counterpart has real hooks.

    THE SHAPE (relic/amethyst_aubergine and relic/big_mushroom, both live
    gaps): a port with no methods at all, justified by a docstring claim about
    what the sim cannot do -- "the sim has no gold", "RunState has no run-level
    AfterObtained dispatch" -- where the sim in fact has exactly the hook
    needed. PROMPT.md bug class 12. This sweep lists every behaviourless port
    beside the C# hooks it drops, and marks the ones the sim's Relic base
    already provides a method for, so a reader can check the premise instead of
    trusting it.
    """
    from sts2_rl.hooks import HookSystem
    from sts2_rl.relics import ALL_RELICS

    combat_hooks = {n for n, v in vars(HookSystem).items()
                    if callable(v) and not n.startswith("_")
                    and n not in ("register", "unregister")}
    rows = {r["unit"].split("/", 1)[1]: r for r in _relic_roster()}

    stubs = []
    for rid, cls in sorted(ALL_RELICS.items()):
        if _own_methods(cls):          # MRO-aware: EggRelic & friends count
            continue
        row = rows.get(rid)
        dropped = [h for h in _cs_overrides(row["game_path"] if row else "")
                   if h not in _DECLARATIVE_CS]
        stubs.append((rid, dropped, (cls.__doc__ or "").strip()))

    with_hooks = [s for s in stubs if s[1]]
    print(f"  {len(stubs)} behaviourless relic port(s) of {len(ALL_RELICS)}; "
          f"{len(with_hooks)} of them drop at least one C# behavioural hook")
    print(f"  (sim Relic base provides run-level methods for "
          f"{len(_RUN_HOOK_MAP)} C# hook names; HookSystem has "
          f"{len(combat_hooks)} combat hooks)\n")
    for rid, dropped, doc in with_hooks:
        marked = []
        for h in dropped:
            sim = _RUN_HOOK_MAP.get(h)
            if sim:
                marked.append(f"{h} -> Relic.{sim} EXISTS")
            elif _snake(h) in combat_hooks:
                marked.append(f"{h} -> HookSystem.{_snake(h)} EXISTS")
            else:
                marked.append(h)
        print(f"    {rid}")
        print(f"      drops: {'; '.join(marked)}")
        print(f"      premise: {(doc.splitlines() or [''])[0][:150]}")


# ── sweep-stub-premises ───────────────────────────────────────────────────
def probe_sweep_stub_premises() -> None:
    """Is each stub's "the sim cannot do this" premise actually true?

    Binding rule 1 turns on exactly this question: a waiver needs the behaviour
    to be GENUINELY out of scope, and "no ported content triggers this" or "the
    sim has no such system" is a dormant GAP, not a waiver. `sweep-stubs` lists
    the behaviourless ports and the C# hooks they drop; this probe answers the
    load-bearing half mechanically -- for every hook a stub drops, is there a
    live DISPATCH SITE in the sim outside sts2_rl/relics/?

    A dispatched hook means the sim already calls that method on every relic in
    the run and the stub simply declines to implement it: gap, not waiver. An
    undispatched one means the pipeline genuinely does not exist yet: still a
    gap by rule 1, but a much larger one, and honestly labelled.
    """
    import subprocess

    from sts2_rl.hooks import HookSystem
    from sts2_rl.relics import ALL_RELICS, base as relic_base

    combat_hooks = {n for n, v in vars(HookSystem).items()
                    if callable(v) and not n.startswith("_")
                    and n not in ("register", "unregister")}
    run_hooks = {n for n, v in vars(relic_base.Relic).items()
                 if callable(v) and not n.startswith("_")}

    def dispatched(name: str) -> list[str]:
        """Files outside relics/ that CALL this hook (i.e. the pipeline runs)."""
        out = subprocess.run(
            ["git", "grep", "-l", rf"\.{name}(", "--", "sts2_rl"],
            capture_output=True, text=True, cwd=_REPO,
        ).stdout.split()
        return [f for f in out if "/relics/" not in f and "/hooks.py" not in f]

    cache: dict[str, list[str]] = {}
    for name in sorted(run_hooks | combat_hooks):
        cache[name] = dispatched(name)

    rows = {r["unit"].split("/", 1)[1]: r for r in _relic_roster()}
    live_pipeline, no_pipeline = [], []
    for rid, cls in sorted(ALL_RELICS.items()):
        if _own_methods(cls):          # MRO-aware: EggRelic & friends count
            continue
        row = rows.get(rid)
        for h in _cs_overrides(row["game_path"] if row else ""):
            if h in _DECLARATIVE_CS:
                continue
            sim = (_RUN_HOOK_MAP.get(h)
                   or (_snake(h) if _snake(h) in combat_hooks else None))
            if sim is None:
                continue
            (live_pipeline if cache.get(sim) else no_pipeline).append(
                (rid, h, sim, cache.get(sim, [])))

    print(f"  Dropped C# hooks whose SIM PIPELINE IS LIVE -- the sim already "
          f"calls this method on every relic,\n  so the stub's premise is "
          f"FALSE and the verdict is a gap, not a waiver ({len(live_pipeline)}):")
    for rid, cs_hook, sim, sites in live_pipeline:
        print(f"    {rid:<24} {cs_hook:<34} -> {sim} "
              f"dispatched by {sites[:2]}")
    print(f"\n  Dropped C# hooks with NO sim dispatch site "
          f"({len(no_pipeline)}) -- still gaps under binding rule 1, but the "
          f"missing piece is the pipeline, not the relic:")
    for rid, cs_hook, sim, _ in no_pipeline:
        print(f"    {rid:<24} {cs_hook:<34} -> {sim} (never called)")


# ── sweep-upgrade ─────────────────────────────────────────────────────────
def probe_sweep_upgrade() -> None:
    """Unguarded `Card.upgrade()` calls across the relic pool (bug class 14).

    C#'s CardCmd.Upgrade skips any card whose IsUpgradable is false
    (`CurrentUpgradeLevel < MaxUpgradeLevel`, CardModel.cs:785-789). The sim's
    Card.upgrade() (cards/base.py:146-147) is a bare `upgrade_level += 1` with
    no guard, so a caller must add its own. relic/bellows does;
    relic/astrolabe (batch 1) and relic/bone_tea (batch 2) do not. Two
    instances in two batches is a shape, so sweep it.

    An executed census of the card registry supplies the population that makes
    it reachable: cards whose max_upgrade_level is 0.
    """
    import subprocess

    import sts2_rl.cards  # noqa: F401  (registration)
    from sts2_rl.cards.base import _CARD_CLASSES

    zero = sorted(cid for cid, c in _CARD_CLASSES.items()
                  if c.max_upgrade_level == 0)
    print(f"  {len(zero)} of {len(_CARD_CLASSES)} ported cards have "
          f"max_upgrade_level == 0 (upgrading them is a no-op in C#):")
    print(f"    {zero[:12]} ...")

    # Scope the guard search to the ENCLOSING FUNCTION, not a fixed window.
    # A line-window heuristic reported fishing_rod / pomander / yummy_cookie /
    # stone_cracker / fragrant_mushroom as unguarded; all five build a
    # pre-filtered candidate list several lines earlier. Same over-reporting
    # mistake as the egg relics in sweep-stubs -- see PROMPT.md's sweep section.
    GUARD_TOKENS = ("is_upgradable", "upgradable_cards", "upgradable")
    out = subprocess.run(
        ["git", "grep", "-ln", r"\.upgrade()", "--", "sts2_rl/relics"],
        capture_output=True, text=True, cwd=_REPO,
    ).stdout.split()
    findings = []
    for path in sorted(out):
        src = (_REPO / path).read_text(encoding="utf-8")
        tree = ast.parse(src)
        for fn in [n for n in ast.walk(tree)
                   if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
            body = ast.get_source_segment(src, fn) or ""
            if ".upgrade()" not in body:
                continue
            guarded = any(tok in body for tok in GUARD_TOKENS)
            findings.append((path, fn.name, fn.lineno, guarded))
    bad = [f for f in findings if not f[3]]
    print(f"\n  {len(findings)} function(s) under sts2_rl/relics/ call "
          f"`.upgrade()`; {len(bad)} do so with NO is_upgradable/upgradable "
          f"filter anywhere in the enclosing function:")
    for path, fn, lineno, guarded in findings:
        if not guarded:
            print(f"    UNGUARDED {path}:{lineno} in {fn}()")
    print(f"\n  guarded (for contrast): "
          f"{sorted({Path(p).stem for p, _, _, g in findings if g})}")


# ── sweep-clone ───────────────────────────────────────────────────────────
def probe_sweep_clone() -> None:
    """Shallow card "clones" that drop per-instance state (bug class 17).

    THE SHAPE (relic/burning_sticks G3, a live gap): C#'s
    `CardModel.CreateClone()` is `CardScope.CloneCard(this)` ->
    `ClonePreservingMutability()` (CardModel.cs:2168-2179; CombatState.cs:188-193)
    -- a full model clone carrying the card's upgrade level, its ENCHANTMENT,
    its AFFLICTION, its keyword edits and its local energy-cost modifiers. The
    sim has no clone helper at all. Every port reconstructs the card from its
    id or class and replays the upgrades, so only the upgrade level survives.

    This sweep lists both sides: the C# content files that clone a card, and
    every sim site using the shallow rebuild idiom. It then EXECUTES the
    difference on the three kinds of per-instance state the sim actually
    models, so the claim is not left as a reading.
    """
    import subprocess

    import sts2_rl.cards  # noqa: F401  (registration)
    from sts2_rl.cards import make_card
    from tools.audit.harness import DEFAULT_GAME_ROOT

    cs_hits: list[tuple[str, int, str]] = []
    for path in sorted((DEFAULT_GAME_ROOT / "src/Core/Models").rglob("*.cs")):
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        for i, line in enumerate(text.splitlines(), start=1):
            if "CreateClone()" in line or "CreateDupe()" in line:
                cs_hits.append((path.name, i, line.strip()[:70]))
    files = sorted({name for name, _, _ in cs_hits})
    print(f"  C# content files calling CreateClone()/CreateDupe(): "
          f"{len(files)} ({len(cs_hits)} sites)")
    for name in files:
        print(f"    {name}")

    out = subprocess.run(
        ["git", "grep", "-n",
         r"make_card(\(card\|c\|original\)\.id)\|type(card)()\|type(c)()",
         "--", "sts2_rl"],
        capture_output=True, text=True, cwd=_REPO,
    ).stdout.splitlines()
    sites = [ln for ln in out if "/pool.py" not in ln]
    print(f"\n  sim sites rebuilding a card instead of cloning it "
          f"({len(sites)}):")
    for ln in sites:
        print(f"    {ln.strip()[:110]}")
    print("  (cards/pool.py's make_card(card_id) calls are GENERATION from an "
          "id, not cloning, and are excluded.)")

    print("\n  EXECUTED -- what a rebuild drops. Per-instance state the sim "
          "models on a Card:")
    from sts2_rl.afflictions import RingingAffliction
    from sts2_rl.cmds import CardCmd
    from sts2_rl.enchantments import make_enchantment

    src = make_card("defend")
    ench = make_enchantment("swift")
    if ench.can_enchant(src):
        ench.attach(src)
    CardCmd.afflict(src, RingingAffliction, 1)
    src.set_cost_this_combat(0)
    clone = make_card(src.id)
    for _ in range(src.upgrade_level):
        clone.upgrade()
    for field in ("enchantment", "affliction"):
        print(f"    {field:<22} original={getattr(src, field)!r:<12} "
              f"clone={getattr(clone, field)!r}")
    print(f"    {'energy_cost':<22} original={src.energy_cost!r:<12} "
          f"clone={clone.energy_cost!r}")
    print("  C# ClonePreservingMutability carries all three.")


# ── batch3 ────────────────────────────────────────────────────────────────
# The third 15-unit relic batch, alphabetically after batch 2.
BATCH3 = [
    "burning_blood", "burning_sticks", "byrdpip", "calling_bell",
    "candelabra", "captains_wheel", "cauldron", "centennial_puzzle",
    "chandelier", "charons_ashes", "chemical_x", "choices_paradox",
    "chosen_cheese", "claws", "cloak_clasp",
]


def probe_batch3_pool() -> None:
    """Obtainability of batch 3's 15 relics (binding rule 6, first half).

    Same method as `pool`: grab-bag membership from the transcribed C# pools,
    every other grant path is a literal relic id somewhere in sts2_rl/.
    """
    import subprocess

    from sts2_rl.relic_pools import IRONCLAD_RELIC_POOL, SHARED_RELIC_POOL
    from sts2_rl.relics import ALL_RELICS

    bag = {rid.removeprefix("RELIC.").lower(): rarity
           for rid, rarity in SHARED_RELIC_POOL + IRONCLAD_RELIC_POOL}
    for rid in BATCH3:
        srcs = subprocess.run(
            ["git", "grep", "-l", f'"{rid}"', "--", "sts2_rl"],
            capture_output=True, text=True, cwd=_REPO,
        ).stdout.split()
        srcs = [s for s in srcs if not s.endswith(f"relics/{rid}.py")]
        print(f"  {rid:<20} registered={rid in ALL_RELICS} "
              f"bag={bag.get(rid, '-'):<9} granted_by={srcs or ['(none)']}")


def probe_batch3() -> None:
    """Reachability evidence for batch 3's live gaps."""
    import sts2_rl.cards  # noqa: F401  (registration)
    from sts2_rl import CombatState
    from sts2_rl.cards import CardType, make_card
    from sts2_rl.cards.base import _CARD_CLASSES
    from sts2_rl.cmds import ExhaustCmd
    from sts2_rl.relics import make_relic
    from sts2_rl.run import RunState

    # ── burning_sticks ────────────────────────────────────────────────────
    print("  -- burning_sticks (1/3): C# clears WasUsedThisCombat in BOTH "
          "AfterRoomEntered(CombatRoom) (BurningSticks.cs:33-42) and\n"
          "     AfterCombatEnd (:56-61); burning_sticks.py resets it nowhere. "
          "Same shape as belt_buckle G2 / centennial_puzzle.")
    sticks = make_relic("burning_sticks")
    for n, seed in enumerate((0, 1), start=1):
        cs = CombatState(rng=random.Random(seed), relics=[sticks])
        cs.player.hand.clear()
        skill = make_card("defend")
        cs.player.hand.append(skill)
        ExhaustCmd.exhaust(cs.hooks, cs.player, skill)
        print(f"     combat {n}: _used_this_combat={sticks._used_this_combat} "
              f"copy added to hand={len(cs.player.hand)}   "
              f"(C# combat 2: 1 copy)")

    print("\n  -- burning_sticks (2/3): sweep-upgrade flags "
          "burning_sticks.py:24 as an unguarded Card.upgrade() (class 14).\n"
          "     Settled by execution: the relic only clones SKILLs, and the "
          "max_upgrade_level==0 population is Curse/Status/Quest only.")
    zero_by_type: dict[str, list[str]] = {}
    for cid, cls in sorted(_CARD_CLASSES.items()):
        if cls.max_upgrade_level == 0:
            zero_by_type.setdefault(cls.card_type.name, []).append(cid)
    print(f"     max_upgrade_level==0 by card type: "
          f"{ {k: len(v) for k, v in sorted(zero_by_type.items())} }")
    print(f"     SKILL cards with max_upgrade_level==0: "
          f"{zero_by_type.get('SKILL', [])}  -> the class-14 hit is DORMANT")

    print("\n  -- burning_sticks (3/3): C# CardModel.CreateClone "
          "(CardModel.cs:2168-2179) is a full CardScope.CloneCard; the sim "
          "rebuilds\n     from make_card(id) + an upgrade loop, so per-instance "
          "state does not survive the clone.")
    from sts2_rl.enchantments import ALL_ENCHANTMENTS
    ench_cls = ALL_ENCHANTMENTS.get("swift")
    src = make_card("defend")
    if ench_cls is not None:
        e = ench_cls()
        if e.can_enchant(src):
            e.attach(src)
    clone = make_card(src.id)
    print(f"     original.enchantment={src.enchantment!r}  "
          f"clone.enchantment={clone.enchantment!r}   (C#: cloned)")

    # ── centennial_puzzle ─────────────────────────────────────────────────
    print("\n  -- centennial_puzzle: C# clears UsedThisCombat in AfterCombatEnd "
          "(CentennialPuzzle.cs:53-57); the sim never does.\n"
          "     (Also produced pool-wide by `sweep-reset-exec`.)")
    puz = make_relic("centennial_puzzle")
    for n, seed in enumerate((0, 1), start=1):
        cs = CombatState(rng=random.Random(seed), relics=[puz])
        before = len(cs.player.hand)
        cs.hooks.on_damage_received(cs.player, 5, None, None)
        print(f"     combat {n}: _used_this_combat={puz._used_this_combat} "
              f"hand {before} -> {len(cs.player.hand)}   (C# combat 2: +3)")

    # ── cauldron ──────────────────────────────────────────────────────────
    print("\n  -- cauldron: AfterObtained offers "
          "DynamicVars['Potions'].IntValue == 5 PotionRewards "
          "(Cauldron.cs:31-55).\n     The port is behaviourless; "
          "run.add_relic dispatches after_obtained at run.py:552.")
    run = RunState(rng=random.Random(3))
    before = list(run.potions)
    run.add_relic("cauldron")
    print(f"     potions {before} -> {list(run.potions)}   (C#: 5 offers)")
    print(f"     sim HAS the pipeline: run.random_potion() -> "
          f"{run.random_potion().id!r}, run.add_potion is "
          f"{callable(getattr(run, 'add_potion', None))}")

    # ── calling_bell ──────────────────────────────────────────────────────
    print("\n  -- calling_bell: CallingBell.GenerateRewards has TWO branches "
          "(CallingBell.cs:34-64). The fixed Anchor/Gremlin Horn/Mummified\n"
          "     Hand trio is the `TestMode.IsOn` branch; real play takes the "
          "RelicReward(Common) / (Uncommon) / (Rare) branch, each of which\n"
          "     Populates via RelicFactory.PullNextRelicFromFront "
          "(RelicReward.cs:75-96). The port implements the test branch.")
    run2 = RunState(rng=random.Random(3))
    bag_before = len(run2.relic_grab_bag)
    run2.add_relic("calling_bell")
    print(f"     relics granted: {[r.id for r in run2.relics]}")
    print(f"     grab bag {bag_before} -> {len(run2.relic_grab_bag)}   "
          f"(C#: three PullNextRelicFromFront pulls, one per rarity)")
    print(f"     curse added: "
          f"{[c.id for c in run2.deck if c.id == 'curse_of_the_bell']}")

    # ── claws ─────────────────────────────────────────────────────────────
    print("\n  -- claws: C# CardSelectCmd.FromDeckForTransformation offers "
          "`c.Type != CardType.Quest && c.IsTransformable` "
          "(CardSelectCmd.cs:487);\n     claws.py:25 offers "
          "run.removable_cards() (= not eternal), which INCLUDES Quest cards.")
    quest = sorted(cid for cid, c in _CARD_CLASSES.items()
                   if c.card_type == CardType.QUEST)
    print(f"     ported QUEST cards: {quest}")
    run3 = RunState(rng=random.Random(0))
    run3.add_card(make_card("byrdonis_egg"))
    run3.card_selector = lambda purpose, cands, count: [
        c for c in cands if c.card_type == CardType.QUEST][:count]
    run3.add_relic("claws")
    print(f"     byrdonis_egg still in the deck after Claws: "
          f"{any(c.id == 'byrdonis_egg' for c in run3.deck)}   (C#: True)")

    # ── choices_paradox ───────────────────────────────────────────────────
    print("\n  -- choices_paradox: C# draws on "
          "RunState.Rng.CombatCardGeneration (ChoicesParadox.cs:34) via "
          "CardFactory.\n     GetDistinctForCombat = FilterForCombat(...)"
          ".TakeRandom(count, rng) (UnstableShuffle + take-first). The port "
          "calls the\n     LEGACY random_pool_cards(self.combat._rng, ...) "
          "(rng.sample), which is a different stream AND a different draw.")
    from sts2_rl.combat_rng import CombatRng
    from sts2_rl.rng import RunRngSet
    parity = CombatRng.parity(RunRngSet("89U21BV1TZ"))
    shared = random.Random(0)
    legacy = CombatRng.legacy(shared)
    print(f"     legacy mode: combat._rng IS card_gen -> "
          f"{legacy.card_gen is shared}")
    print(f"     parity mode: combat._rng IS card_gen -> "
          f"{parity.card_gen is shared}  <-- wrong stream in a parity run")
    print("     the house-style parity branch already exists and is used by "
          "cards/infernal_blade.py:37-41 and potions.py:447-453:")
    print("       if crng.is_parity: get_distinct_for_combat_parity"
          "(crng.card_gen, n, ...)")

    # ── byrdpip ───────────────────────────────────────────────────────────
    print("\n  -- byrdpip: C# HasUponPickupEffect => true and SpawnsPets => "
          "true (Byrdpip.cs:24, 26); the port sets neither.")
    byrd = make_relic("byrdpip")
    print(f"     sim has_upon_pickup_effect={byrd.has_upon_pickup_effect} "
          f"spawns_pets={byrd.spawns_pets} adds_pet={byrd.adds_pet} "
          f"is_tradable={byrd.is_tradable}")
    print(f"     (rarity {byrd.rarity.name} is already excluded from "
          f"is_tradable, so the two dropped flags are shadowed today)")

    # ── chemical_x ────────────────────────────────────────────────────────
    print("\n  -- chemical_x: ModifyXValue +2 on the captured X, energy spent "
          "unchanged (ChemicalX.cs:31-38).")
    cs = CombatState(rng=random.Random(0), relics=[make_relic("chemical_x")])
    xs = sorted(cid for cid, c in _CARD_CLASSES.items()
                if getattr(c, "energy_cost_x", False))
    print(f"     ported X-cost cards: {xs}")
    if xs:
        cs.player.hand.clear()
        cs.player.energy = 3
        card = make_card(xs[0])
        cs.player.hand.append(card)
        cs.play_card(0, 0)
        print(f"     {xs[0]}: energy 3 -> {cs.player.energy}, "
              f"captured_x={card.captured_x}   (C#: X = 3 + 2 = 5)")

    # ── chosen_cheese ─────────────────────────────────────────────────────
    print("\n  -- chosen_cheese: +1 Max HP at combat end, and the run must see "
          "it (RunState.finish_combat syncs max_hp, run.py:1178).")
    run4 = RunState(rng=random.Random(0))
    run4.add_relic("chosen_cheese")
    before = (run4.max_hp, run4.hp)
    cs = CombatState(rng=random.Random(0), relics=run4.relics,
                     max_hp=run4.max_hp, current_hp=run4.hp)
    cs._end_combat(player_won=True)
    run4.finish_combat(cs)
    print(f"     run max_hp/hp {before} -> {(run4.max_hp, run4.hp)}   "
          f"(C#: 81/81)")
    # C# AfterCombatEnd fires ONLY on the victory path (EndCombatInternal,
    # CombatManager.cs:970-988); a loss goes through ProcessPendingLoss and
    # fires no hook at all. The sim fires on_combat_end on both, so the port's
    # `is_dead` guard is what stands in -- and every sim _end_combat(False)
    # site is itself gated on player.is_dead, so the two agree.


# ── batch2 ────────────────────────────────────────────────────────────────
def probe_batch2() -> None:
    """Reachability evidence for batch 2's live gaps."""
    from sts2_rl import CombatState
    from sts2_rl.cards import make_card
    from sts2_rl.relics import make_relic
    from sts2_rl.rooms import RoomType
    from sts2_rl.run import RunState

    print("  -- bone_tea: CardCmd.Upgrade skips !IsUpgradable; the sim's "
          "card.upgrade() does not (BoneTea.cs:53-56 vs bone_tea.py:34-35)")
    tea = make_relic("bone_tea")
    cs = CombatState(rng=random.Random(0), relics=[tea])
    cs.player.hand.clear()
    for cid in ("strike", "dazed", "burn"):
        cs.player.hand.append(make_card(cid))
    # CombatState.__init__ already ran turn 1, spending the single charge on
    # the real opening hand; re-arm it to fire against this crafted hand.
    tea.combats_left = tea.COMBATS
    tea.on_player_turn_started(cs.player)
    for c in cs.player.hand:
        print(f"     {c.id:<10} max_upgrade_level={c.max_upgrade_level} "
              f"-> upgrade_level={c.upgrade_level}"
              f"{'   <-- C# leaves this at 0' if c.max_upgrade_level == 0 else ''}")

    print("\n  -- bowler_hat: ModifyGoldGained x1.25 (BowlerHat.cs:18-25)")
    for relics in ([], ["bowler_hat"]):
        run = RunState(rng=random.Random(0))
        for rid in relics:
            run.add_relic(rid)
        before = run.gold
        run.gain_gold(100)
        print(f"     relics={relics or ['(none)']:} gain_gold(100) -> "
              f"+{run.gold - before}   (C# with the hat: +125)")

    print("\n  -- book_of_five_rings: heal 20 every 5 cards added to the deck "
          "(BookOfFiveRings.cs:67-83)")
    run = RunState(rng=random.Random(0), hp=50)
    run.add_relic("book_of_five_rings")
    for _ in range(5):
        run.add_card(make_card("strike"))
    print(f"     hp after 5 deck adds: {run.hp}   (C#: 70)")

    print("\n  -- brilliant_scarf: C# AfterCardPlayed SKIPS auto-plays "
          "(BrilliantScarf.cs:84-87); the sim's on_card_played counts them")
    scarf = make_relic("brilliant_scarf")
    cs = CombatState(rng=random.Random(0), relics=[scarf])
    cs.player.hand.append(make_card("strike"))
    cs.combat_auto = None
    cs.auto_play_card(cs.player.hand[-1], 0)
    print(f"     cards_played_this_turn after ONE auto-play: "
          f"{scarf.cards_played_this_turn}   (C#: 0)")

    print("\n  -- booming_conch: C# gains energy through PlayerCmd.GainEnergy "
          "(BoomingConch.cs:41); the sim assigns player.energy directly "
          "(booming_conch.py:34), bypassing the hook chain")
    seen = []
    from sts2_rl.hooks import HookSystem
    orig = HookSystem.on_energy_gained if hasattr(
        HookSystem, "on_energy_gained") else None
    print(f"     HookSystem defines on_energy_gained: {orig is not None}")
    conch = make_relic("booming_conch")
    cs = CombatState(rng=random.Random(0), relics=[conch],
                     room_type=RoomType.ELITE)
    print(f"     elite turn-1 energy: {cs.player.energy} "
          f"(base {cs.player.ENERGY_PER_TURN} + 1), hand={len(cs.player.hand)} "
          f"(base {cs.player.DRAW_PER_TURN} + 2)")
    del seen


PROBES = {
    "pool": probe_pool,
    "turn-order": probe_turn_order,
    "lamp-replay": probe_lamp_replay,
    "lamp-self-debuff": probe_lamp_self_debuff,
    "lamp-temporary": probe_lamp_temporary,
    "aubergine-gold": probe_aubergine_gold,
    "mushroom-hp": probe_mushroom_hp,
    "buckle-potion": probe_buckle_potion,
    "sweep-reset": probe_sweep_reset,
    "sweep-reset-exec": probe_sweep_reset_exec,
    "sweep-isallowed": probe_sweep_isallowed,
    "sweep-stubs": probe_sweep_stubs,
    "sweep-stub-premises": probe_sweep_stub_premises,
    "sweep-upgrade": probe_sweep_upgrade,
    "sweep-clone": probe_sweep_clone,
    "batch2": probe_batch2,
    "batch3": probe_batch3,
    "batch3-pool": probe_batch3_pool,
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
