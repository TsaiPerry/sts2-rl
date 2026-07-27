"""Reproducible execution probes for relic audit BATCH 15.

Batch 15's units: small_capsule, snecko_eye, sozu, sparkling_rouge,
spiked_gauntlets, stone_calendar, stone_cracker, stone_humidifier, storybook,
strawberry, strike_dummy, sturdy_clamp, sword_of_jade, sword_of_stone,
tanxs_whistle.

Own module per the batch-15 concurrency contract: `audit/tools/relic_probes.py`
is read-only to this batch (re-use it read-only —
`py audit/tools/relic_probes.py turn-order` is the executed hook-order
reference). Binding rules 5 and 6: never justify `faithful` with an
unreachability claim you have not EXECUTED, and never label a gap LIVE without
proving both sides reachable with ported content.

  py audit/tools/relic_probes_b15.py                 # every probe
  py audit/tools/relic_probes_b15.py b15-cracker     # one probe

Probes:
  b15-pool          obtainability of the 15 units (rule 6, both sides)
  b15-cracker       stone_cracker -- the StableShuffle key and the pile
                    orientation the port gets wrong (LIVE)
  b15-rouge         sparkling_rouge -- AfterBlockCleared vs the post-draw slot,
                    plus the census of readers in the skipped window
  b15-clamp         sturdy_clamp -- preventer identity + cap timing
                    (reproduces audit/records/seam/turn_structure.json G1/G2)
  b15-sozu          sozu -- +1 max energy, and the in-combat procure path that
                    bypasses ShouldProcurePotion (LIVE)
  b15-strawberry    strawberry -- undo_after_obtained clamps instead of
                    subtracting (the mango G1 family)
  b15-swords        sword_of_stone's elite counter across combats and
                    sword_of_jade's applier / hook-site divergences
  b15-misc          snecko_eye, spiked_gauntlets, stone_calendar,
                    strike_dummy, stone_humidifier, storybook, tanxs_whistle,
                    small_capsule -- the numeric/behavioural spot checks
  b15-censuses      the static censuses the records lean on: C#
                    ModifyDamageAdditive implementers vs IsPoweredAttack,
                    strike-tagged card dealers, X-cost Power cards, and the
                    AfterRoomEntered-collapse shape across the whole pool
"""
from __future__ import annotations

import argparse
import random
import re
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

_GAME = Path(r"C:\Users\Perry\Desktop\Slay the Spire 2")

BATCH15 = [
    "small_capsule", "snecko_eye", "sozu", "sparkling_rouge",
    "spiked_gauntlets", "stone_calendar", "stone_cracker",
    "stone_humidifier", "storybook", "strawberry", "strike_dummy",
    "sturdy_clamp", "sword_of_jade", "sword_of_stone", "tanxs_whistle",
]


# ── b15-pool ──────────────────────────────────────────────────────────────
def probe_pool() -> None:
    """Where each batch-15 relic can come from (binding rule 6, side one)."""
    from sts2_rl.relic_pools import IRONCLAD_RELIC_POOL, SHARED_RELIC_POOL
    from sts2_rl.relics import ALL_RELICS

    bag = {rid.removeprefix("RELIC.").lower(): rarity
           for rid, rarity in SHARED_RELIC_POOL + IRONCLAD_RELIC_POOL}
    print(f"  grab-bag pool: {len(bag)} relics")
    for rid in BATCH15:
        srcs = subprocess.run(
            ["git", "grep", "-l", f'"{rid}"', "--", "sts2_rl"],
            capture_output=True, text=True, cwd=_REPO,
        ).stdout.split()
        srcs = [s for s in srcs if not s.endswith(f"relics/{rid}.py")]
        print(f"  {rid:<18} registered={rid in ALL_RELICS} "
              f"bag={bag.get(rid, '-'):<9} granted_by={srcs or ['(none)']}")


# ── b15-cracker ───────────────────────────────────────────────────────────
def probe_cracker() -> None:
    """stone_cracker: the port's StableShuffle key AND pile orientation.

    StoneCracker.cs:25-27 is
    `Draw.GetPile(Owner).Cards.Where(IsUpgradable).ToList()
        .StableShuffle(RunState.Rng.CombatCardSelection).Take(2)`.
    ListExtensions.StableShuffle (ListExtensions.cs:22-31) SORTS with
    `List.Sort()` -> CardModel.CompareTo (CardModel.cs:2242 -> AbstractModel
    .cs:87-98, `Id.CompareTo`, then CurrentUpgradeLevel) and THEN runs an
    order-dependent Fisher-Yates.

    Two things the sim's own canonical key already documents and the port
    does not do (player.py:23-34 `_compare_to_key`):
      1. the game's ModelId is the UPPERCASE entry compared ORDINALLY, where
         `_` (0x5F) sorts AFTER the letters; stone_cracker.py:29 keys on the
         lowercase slug, where `_` sorts BEFORE them.
      2. the sim stores the draw pile top-at-END (player.py:264-266 reverses
         after every parity shuffle), so passing `player.draw_pile` hands
         StableShuffle the pile BACKWARDS -- and equal-comparing cards keep
         their incoming order under both List.Sort and Python's sort.
    """
    from sts2_rl.combat import CombatState
    from sts2_rl.player import _compare_to_key
    from sts2_rl.cards import make_card
    from sts2_rl.cards.base import _CARD_CLASSES
    from sts2_rl.relics import make_relic
    from sts2_rl.rng import RunRngSet

    # (1) the key itself: which ported ids the two keys order differently.
    ids = sorted(_CARD_CLASSES)
    lower = sorted(ids)
    upper = sorted(ids, key=lambda i: i.upper())
    print(f"  ported card ids: {len(ids)}; lowercase order == uppercase order? "
          f"{lower == upper}")
    flips = [(a, b) for a, b in zip(lower, upper) if a != b]
    print(f"  first disagreeing positions: {flips[:6]}")
    # the adjacent pairs that actually swap
    pairs = []
    for i in range(len(lower) - 1):
        a, b = lower[i], lower[i + 1]
        if (a.upper() > b.upper()):
            pairs.append((a, b))
    print(f"  ordinal-vs-slug swapped adjacent pairs ({len(pairs)}): {pairs}")

    # (2) orientation: which draw-pile positions get the upgrade.
    def run(seed: str, port: bool):
        rs = RunRngSet(seed)
        deck = [make_card("strike") for _ in range(5)] + \
               [make_card("defend") for _ in range(4)]
        cs = CombatState(starting_deck=deck, rng_set=rs,
                         relics=[make_relic("stone_cracker")] if port else [])
        # the sim's pile is top-at-END; report in the GAME's orientation
        pile = list(reversed(cs.player.draw_pile))
        hand = [(c.id, c.upgrade_level) for c in cs.player.hand]
        ups = [i for i, c in enumerate(pile) if c.upgrade_level > 0]
        return ups, hand

    for seed in ("89U21BV1TZ", "933T39V18D"):
        ups, hand = run(seed, True)
        print(f"  seed {seed}: upgraded draw-pile positions (game orientation) "
              f"{ups}; opening hand {hand}")

    # (3) A/B the WHOLE relic: the shipped port vs a StoneCracker.cs-faithful
    #     variant (game orientation + the uppercase ordinal key), same seed,
    #     same stream. The observable is the opening hand.
    from sts2_rl.relics.base import Relic, RelicRarity

    class FaithfulCracker(Relic):
        """StoneCracker.cs verbatim: the DRAW PILE in the game's orientation
        (top at index 0) sorted on CardModel.CompareTo's UPPERCASE ordinal key,
        then UnstableShuffle, then Take(2)."""

        id, name, rarity = "_faithful_cracker", "F", RelicRarity.UNCOMMON

        def on_combat_start(self):
            pile = list(reversed(self.player.draw_pile))  # game orientation
            cand = [c for c in pile if c.is_upgradable]
            cand.sort(key=_compare_to_key)
            self.combat.combat_rng.card_selection.shuffle(cand)
            for c in cand[:2]:
                c.upgrade()

    def hand_and_pile(seed: str, relic):
        rs = RunRngSet(seed)
        deck = [make_card("strike") for _ in range(5)] + \
               [make_card("defend") for _ in range(4)]
        cs = CombatState(starting_deck=deck, rng_set=rs, relics=[relic])
        hand = [f"{c.id}{'+' if c.upgrade_level else ''}" for c in cs.player.hand]
        pile = [f"{c.id}{'+' if c.upgrade_level else ''}"
                for c in reversed(cs.player.draw_pile)]
        return hand, pile

    diffs = 0
    seeds = ["89U21BV1TZ", "933T39V18D", "DJDC1X0MHK", "L081ABCDEF",
             "QRWC12345X", "TZEK9876HJ", "AAAA111111", "ZZZZ999999"]
    for seed in seeds:
        h_port, p_port = hand_and_pile(seed, make_relic("stone_cracker"))
        h_game, p_game = hand_and_pile(seed, FaithfulCracker())
        same = (h_port == h_game and p_port == p_game)
        diffs += 0 if same else 1
        print(f"  seed {seed}: port hand {h_port}")
        print(f"  {'':>{len(seed) + 8}}game hand {h_game}   "
              f"{'MATCH' if same else 'DIVERGES'}")
        if not same:
            print(f"  {'':>{len(seed) + 8}}port pile {p_port}")
            print(f"  {'':>{len(seed) + 8}}game pile {p_game}")
    print(f"  -> {diffs}/{len(seeds)} seeds diverge in the observable "
          f"hand/draw-pile upgrade pattern")


# ── b15-rouge ─────────────────────────────────────────────────────────────
def probe_rouge() -> None:
    """sparkling_rouge: the C# hook is AfterBlockCleared; the port is post-draw.

    The two OTHER C# AfterBlockCleared relics (CaptainsWheel.cs:20-27,
    HornCleat.cs:20-27) are both ported onto the sim's `on_block_cleared`
    (relics/captains_wheel.py:19-22, relics/horn_cleat.py:19-22), so the
    correct slot exists and this port simply does not use it.
    """
    from sts2_rl.combat import CombatState
    from sts2_rl.relics import make_relic
    from sts2_rl.relics.base import Relic, RelicRarity

    seen: list[str] = []

    class Spy(Relic):
        id, name, rarity = "_spy_rouge", "Spy", RelicRarity.COMMON

        def on_block_cleared(self, target):
            seen.append(f"t{self.turn} on_block_cleared "
                        f"str={self.player.powers.get('strength')} "
                        f"dex={self.player.powers.get('dexterity')}")

        def on_energy_reset(self, player):
            seen.append(f"t{self.turn} on_energy_reset "
                        f"str={self.player.powers.get('strength')}")

        def on_player_turn_start(self, player):
            seen.append(f"t{self.turn} on_player_turn_start "
                        f"str={self.player.powers.get('strength')}")

        def on_card_drawn(self, card, from_hand_draw=False):
            if self.turn == 3:
                seen.append(f"t{self.turn} on_card_drawn({card.id}) "
                            f"str={self.player.powers.get('strength')}")

        def on_player_turn_started(self, player):
            seen.append(f"t{self.turn} on_player_turn_started(END) "
                        f"str={self.player.powers.get('strength')} "
                        f"dex={self.player.powers.get('dexterity')}")

    cs = CombatState(rng=random.Random(0),
                     relics=[Spy(), make_relic("sparkling_rouge")])
    for _ in range(3):
        cs.end_turn()
    for line in seen:
        if line.startswith("t3") or line.startswith("t2"):
            print("  " + line)
    print(f"  after turn-3 setup: str={cs.player.powers.get('strength')} "
          f"dex={cs.player.powers.get('dexterity')}")
    print("  -> C# applies the +1/+1 at AfterBlockCleared, i.e. BEFORE the "
          "energy reset, ModifyHandDraw, the draw and every AfterCardDrawn.")

    # registration order decides who sees it: spy AFTER the relic.
    seen.clear()
    cs = CombatState(rng=random.Random(0),
                     relics=[make_relic("sparkling_rouge"), Spy()])
    for _ in range(3):
        cs.end_turn()
    late = [l for l in seen if l.startswith("t3") and "END" in l]
    print(f"  spy registered AFTER the relic sees: {late}")

    # census: does anything in the skipped window READ Strength/Dexterity?
    import ast
    WINDOW = {"on_energy_reset", "on_player_turn_start", "modify_hand_draw",
              "on_card_drawn", "on_player_turn_started"}
    readers = []
    for p in sorted((_REPO / "sts2_rl").rglob("*.py")):
        text = p.read_text(encoding="utf-8")
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name in WINDOW:
                src = ast.get_source_segment(text, node) or ""
                low = src.lower()
                grants = "powercmd.apply" in low or "strengthcmd" in low
                reads = ("strength" in low or "dexterity" in low)
                powered = ("DamageProps.CARD" in src
                           or "DamageProps.MONSTER_MOVE" in src)
                if (reads and not grants) or powered:
                    readers.append(f"{p.relative_to(_REPO)}:{node.lineno} "
                                   f"{node.name}")
    print(f"  listeners in the skipped window that READ Strength/Dexterity or "
          f"deal POWERED damage: {readers or 'NONE'}")


# ── b15-clamp ─────────────────────────────────────────────────────────────
def probe_clamp() -> None:
    """sturdy_clamp: reproduce audit/records/seam/turn_structure.json G1 and G2."""
    from sts2_rl.combat import CombatState
    from sts2_rl.cmds import PowerCmd
    from sts2_rl.powers import BarricadePower
    from sts2_rl.relics import make_relic
    from sts2_rl.relics.base import Relic, RelicRarity

    fired: list[str] = []

    class Spy(Relic):
        id, name, rarity = "_spy_clamp", "Spy", RelicRarity.COMMON

        def should_clear_block(self, creature):
            fired.append(f"t{self.turn} should_clear_block")
            return True

        def on_block_cleared(self, target):
            fired.append(f"t{self.turn} on_block_cleared")

    # start_turn in isolation: end_turn would hand the enemy a move and its
    # attack would eat the block, confounding the read.
    def carried(block: int, relics, barricade: bool = False) -> int:
        cs = CombatState(rng=random.Random(0), relics=relics)
        if barricade:
            PowerCmd.apply(cs.hooks, cs.player, BarricadePower, 1)
        cs.player.block = block
        cs.player.start_turn()
        return cs.player.block

    clamp = [make_relic("sturdy_clamp")]
    print(f"  sturdy_clamp alone, 30 block -> next turn-start {carried(30, clamp)}"
          f" (C#: 10)")
    print(f"  sturdy_clamp alone, 4 block  -> next turn-start "
          f"{carried(4, [make_relic('sturdy_clamp')])} (C#: 4)")
    print(f"  no relic, 30 block           -> next turn-start "
          f"{carried(30, [])} (C#: 0)")
    # G2 leg: Barricade + Sturdy Clamp -- C#'s preventer is BarricadePower
    # (powers precede relics in CombatState.IterateHookListeners), so
    # SturdyClamp.AfterPreventingBlockClear bails and the full block survives.
    print(f"  barricade + sturdy_clamp, 30 -> next turn-start "
          f"{carried(30, [make_relic('sturdy_clamp')], barricade=True)} "
          f"(C#: 30 -- the preventer is BarricadePower, so the cap never runs)")

    # G1 leg: the block-clear EVENT when the clear was prevented.
    fired.clear()
    cs = CombatState(rng=random.Random(0),
                     relics=[Spy(), make_relic("sturdy_clamp")])
    cs.player.block = 12
    cs.player.start_turn()
    print(f"  with the clear PREVENTED, sim fires: {fired} "
          f"(C# fires AfterBlockCleared unconditionally -- turn_structure G1)")

    # the cap's own write path: player.block = 10 vs CreatureCmd.LoseBlock.
    broke: list[int] = []

    class BreakSpy(Relic):
        id, name, rarity = "_spy_break", "Spy", RelicRarity.COMMON

        def after_block_broken(self, creature):
            broke.append(self.turn)

    cs = CombatState(rng=random.Random(0),
                     relics=[BreakSpy(), make_relic("sturdy_clamp")])
    cs.player.block = 30
    cs.player.start_turn()
    print(f"  after_block_broken fired on turns {broke or 'NONE'} "
          f"(C# LoseBlock(block-10) leaves 10 > 0, so AfterBlockBroken never "
          f"fires from the cap either)")


# ── b15-sozu ──────────────────────────────────────────────────────────────
def probe_sozu() -> None:
    """sozu: the +1 max energy half, and the potion gate's two sim paths."""
    from sts2_rl.combat import CombatState
    from sts2_rl.relics import make_relic
    from sts2_rl.potions import make_potion
    from sts2_rl.run import RunState

    cs = CombatState(rng=random.Random(0))
    base = cs.player.energy
    cs2 = CombatState(rng=random.Random(0), relics=[make_relic("sozu")])
    print(f"  turn-1 energy: without sozu {base}, with sozu {cs2.player.energy}"
          f" (C#: ModifyMaxEnergy +EnergyVar(1))")

    # out-of-combat procure: the gate IS consulted (run.py:480-481).
    run = RunState(rng=random.Random(0))
    run.add_relic("sozu")
    kept = run.add_potion(make_potion("fire_potion"))
    print(f"  RunState.add_potion with sozu -> kept={kept} "
          f"belt={[p and p.id for p in run.potions]}  (C#: refused)")

    # in-combat procure: PlayerCombatState.add_potion has NO gate.
    cs3 = CombatState(rng=random.Random(0), relics=[make_relic("sozu")])
    kept2 = cs3.player.add_potion(make_potion("fire_potion"))
    print(f"  PlayerCombatState.add_potion with sozu -> kept={kept2} "
          f"belt={[p and p.id for p in cs3.player.potions]}  "
          f"(C#: PotionCmd.TryToProcure gates EVERY procure, PotionCmd.cs:31)")

    # ported in-combat procure sources
    hits = subprocess.run(
        ["git", "grep", "-n", "add_potion", "--", "sts2_rl"],
        capture_output=True, text=True, cwd=_REPO).stdout.strip().splitlines()
    print("  ported callers of the ungated in-combat path:")
    for h in hits:
        if "player.add_potion" in h or "player.add_potion(" in h:
            print("    " + h)


# ── b15-strawberry ────────────────────────────────────────────────────────
def probe_strawberry() -> None:
    """strawberry: undo_after_obtained CLAMPS where it should subtract.

    Same mechanism as relic/mango G1 (which names strawberry.py:24-25 in its
    own pool-wide list) -- one verdict per mechanism, binding rule 3.
    """
    from sts2_rl.run import RunState

    for hp in (80, 50, 40):
        run = RunState(rng=random.Random(0))
        run.max_hp, run.hp = 80, hp
        r = run.add_relic("strawberry")
        after = (run.hp, run.max_hp)
        r.undo_after_obtained(run)
        print(f"  {hp}/80 -> take {after} -> undo {(run.hp, run.max_hp)} "
              f"(exact undo would be {(hp, 80)})")


# ── b15-swords ────────────────────────────────────────────────────────────
def probe_swords() -> None:
    """sword_of_stone's per-run counter, and sword_of_jade's applier/slot."""
    from sts2_rl.combat import CombatState
    from sts2_rl.relics import make_relic
    from sts2_rl.rooms import RoomType
    from sts2_rl.run import RunState

    run = RunState(rng=random.Random(0))
    stone = run.add_relic("sword_of_stone")
    for i in range(5):
        cs = CombatState(rng=random.Random(i), relics=[stone])
        for e in cs.enemies:
            e.hp = 0
        run.finish_combat(cs, room_type=RoomType.ELITE)
        print(f"  elite {i + 1}: relics={[r.id for r in run.relics]} "
              f"counter={getattr(stone, 'elites_defeated', None)}")
    # non-elite must not count
    run2 = RunState(rng=random.Random(0))
    s2 = run2.add_relic("sword_of_stone")
    cs = CombatState(rng=random.Random(0), relics=[s2])
    run2.finish_combat(cs, room_type=RoomType.MONSTER)
    print(f"  monster room -> counter {s2.elites_defeated} (C#: unchanged)")

    # sword_of_jade: applier. C# passes applier = null (SwordOfJade.cs:25);
    # the port passes applier=self.player (sword_of_jade.py:26-29).
    cs = CombatState(rng=random.Random(0), relics=[make_relic("sword_of_jade")])
    print(f"  sword_of_jade combat start: strength="
          f"{cs.player.powers.get('strength')}")
    hits = subprocess.run(
        ["git", "grep", "-n", "applier is", "--", "sts2_rl"],
        capture_output=True, text=True, cwd=_REPO).stdout.strip().splitlines()
    print("  sim listeners that branch on the power APPLIER identity:")
    for h in hits:
        print("    " + h)


# ── b15-misc ──────────────────────────────────────────────────────────────
def probe_misc() -> None:
    """The remaining spot checks, one line each."""
    from sts2_rl.combat import CombatState
    from sts2_rl.cards import make_card
    from sts2_rl.relics import make_relic
    from sts2_rl.run import RunState

    # snecko_eye: Confused at combat start + 2 extra cards.
    cs = CombatState(rng=random.Random(0))
    plain = len(cs.player.hand)
    cs = CombatState(rng=random.Random(0), relics=[make_relic("snecko_eye")])
    print(f"  snecko_eye: hand {plain} -> {len(cs.player.hand)}, "
          f"confused={cs.player.powers.get('confused') is not None} "
          f"(C#: ConfusedPower 1 in BeforeCombatStart, ModifyHandDraw +2)")

    # spiked_gauntlets: +1 max energy and Power cards cost 1 more.
    cs = CombatState(rng=random.Random(0),
                     relics=[make_relic("spiked_gauntlets")])
    from sts2_rl.previews import preview_card_energy_cost as card_energy_cost
    inflame = make_card("inflame")
    inflame.combat = cs
    strike = make_card("strike")
    strike.combat = cs
    print(f"  spiked_gauntlets: energy {cs.player.energy}, "
          f"inflame(Power) cost {card_energy_cost(cs, inflame)} "
          f"(base {make_card('inflame').energy_cost}), "
          f"strike(Attack) cost {card_energy_cost(cs, strike)}")

    # stone_calendar: 52 to all enemies at the END of turn 7.
    from sts2_rl.monsters import FUZZY_WURM_ENCOUNTER
    cs = CombatState(rng=random.Random(0),
                     relics=[make_relic("stone_calendar")],
                     encounter=FUZZY_WURM_ENCOUNTER)
    hp = [(e.name, e.hp) for e in cs.enemies]
    for t in range(7):
        if cs.is_over:
            break
        cs.end_turn()
    print(f"  stone_calendar: enemies {hp} -> "
          f"{[(e.name, e.hp) for e in cs.enemies]} at turn {cs.turn} "
          f"(is_over={cs.is_over})")

    # strike_dummy: +3 on a Strike-tagged card only, powered only.
    from sts2_rl.cmds import DamageCmd
    from sts2_rl.valueprops import DamageProps
    cs = CombatState(rng=random.Random(0), relics=[make_relic("strike_dummy")])
    for cid, props in (("strike", DamageProps.CARD),
                       ("bash", DamageProps.CARD),
                       ("strike", DamageProps.CARD_UNPOWERED)):
        c = make_card(cid)
        e = cs.enemies[0]
        before = e.hp
        DamageCmd.deal(cs.hooks, e, 6, dealer=cs.player, card=c, props=props)
        print(f"    strike_dummy {cid} props={props!r}: 6 base -> "
              f"{before - e.hp} dealt")
    e = cs.enemies[0]
    before = e.hp
    DamageCmd.deal(cs.hooks, e, 6, dealer=None,
                   card=make_card("strike"), props=DamageProps.CARD)
    print(f"    strike_dummy dealer=None with a player's Strike: 6 -> "
          f"{before - e.hp} (C#: 9, cardSource.Owner == Owner suffices)")

    # stone_humidifier / strawberry / storybook / tanxs_whistle / small_capsule
    run = RunState(rng=random.Random(0))
    run.max_hp, run.hp = 80, 40
    run.add_relic("stone_humidifier")
    healed = run.rest_heal()
    print(f"  stone_humidifier: rest heal {healed} then "
          f"{run.hp}/{run.max_hp} (C#: 30% heal, then GainMaxHp(5) which "
          f"heals 5 more)")

    run = RunState(rng=random.Random(0))
    run.add_relic("storybook")
    run.add_relic("tanxs_whistle")
    print(f"  storybook/tanxs_whistle: deck tail "
          f"{[c.id for c in run.deck[-2:]]} (C#: CardPileCmd.Add(Deck) "
          f"appends, CardPile.AddInternal index=-1)")

    run = RunState(rng=random.Random(0))
    run.start_run()
    before = len(run.relic_grab_bag)
    got = run.add_relic("small_capsule")
    print(f"  small_capsule: relics {[r.id for r in run.relics]}; grab bag "
          f"{before} -> {len(run.relic_grab_bag)} (C#: one RelicReward the "
          f"player may SKIP)")


# ── b15-censuses ──────────────────────────────────────────────────────────
def probe_censuses() -> None:
    """The static censuses the batch-15 records lean on."""
    # (a) every C# ModifyDamageAdditive implementer gates on IsPoweredAttack?
    rel = _GAME / "src" / "Core" / "Models"
    impl = []
    for p in rel.rglob("*.cs"):
        text = p.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"override decimal ModifyDamageAdditive\b", text)
        if not m:
            continue
        body = text[m.start():m.start() + 1600]
        impl.append((p.name, "IsPoweredAttack()" in body))
    print(f"  C# ModifyDamageAdditive implementers: {len(impl)}; "
          f"gating on IsPoweredAttack: {sum(1 for _, g in impl if g)}")
    print(f"    not gating: {[n for n, g in impl if not g] or 'NONE'}")

    # (b) strike-tagged ported cards and the dealer they pass.
    from sts2_rl.cards import make_card
    from sts2_rl.cards.base import _CARD_CLASSES
    strikes = [cid for cid in sorted(_CARD_CLASSES)
               if "strike" in getattr(make_card(cid), "tags", frozenset())]
    print(f"  strike-tagged ported cards ({len(strikes)}): {strikes}")
    bad = []
    for cid in strikes:
        f = subprocess.run(["git", "grep", "-l", f'id = "{cid}"', "--",
                            "sts2_rl/cards"], capture_output=True, text=True,
                           cwd=_REPO).stdout.split()
        txt = "".join((_REPO / x).read_text(encoding="utf-8") for x in f)
        if "dealer=ctx.player" not in txt:
            bad.append(cid)
    print(f"    strike cards NOT passing dealer=ctx.player: {bad or 'NONE'}")

    # (c) X-cost Power cards (the ModifyEnergyCostInCombat `< 0` bail).
    from sts2_rl.cards import CardType
    xs = [cid for cid in sorted(_CARD_CLASSES)
          if getattr(make_card(cid), "energy_cost_x", False)]
    xpow = [c for c in xs if make_card(c).card_type == CardType.POWER]
    print(f"  X-cost ported cards {xs}; X-cost POWER cards: {xpow or 'NONE'}")

    # (d) the AfterRoomEntered(CombatRoom) collapse: which C# relics use it
    #     and which sim ports put it on on_combat_start (= BeforeCombatStart).
    from sts2_rl.relics import ALL_RELICS
    relics_dir = _GAME / "src" / "Core" / "Models" / "Relics"
    collapsed, kept = [], []
    for p in sorted(relics_dir.glob("*.cs")):
        text = p.read_text(encoding="utf-8", errors="replace")
        if "AfterRoomEntered" not in text:
            continue
        if "is CombatRoom" not in text:
            continue
        snake = re.sub(r"(?<!^)(?=[A-Z])", "_", p.stem).lower()
        cls = ALL_RELICS.get(snake)
        if cls is None:
            continue
        has_start = any(hasattr(k, "on_combat_start") for k in [cls])
        has_room = hasattr(cls, "after_room_entered") and \
            "after_room_entered" in cls.__dict__
        (collapsed if (has_start and "on_combat_start" in cls.__dict__)
         else kept).append(snake)
    print(f"  C# relics whose combat hook is AfterRoomEntered(CombatRoom) and "
          f"whose port uses on_combat_start (= BeforeCombatStart, one hook "
          f"LATER): {sorted(collapsed)}")
    print(f"  ... other ports of the same C# hook: {sorted(kept)}")


PROBES = {
    "b15-pool": probe_pool,
    "b15-cracker": probe_cracker,
    "b15-rouge": probe_rouge,
    "b15-clamp": probe_clamp,
    "b15-sozu": probe_sozu,
    "b15-strawberry": probe_strawberry,
    "b15-swords": probe_swords,
    "b15-misc": probe_misc,
    "b15-censuses": probe_censuses,
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
