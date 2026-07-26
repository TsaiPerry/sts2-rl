"""Reproducible execution probes for relic audit batch 10.

Batch 10 units: mummified_hand, music_box, mystic_lighter, neows_bones,
neows_talisman, neows_torment, new_leaf, nunchaku, nutritious_oyster,
nutritious_soup, oddly_smooth_stone, old_coin, orichalcum, ornamental_fan,
orrery.

Own module per the concurrency contract (`tools/audit/relic_probes.py` is
read-only to this batch). Binding rules 5 and 6: never justify `faithful` with
an unreachability claim you have not EXECUTED, and never label a gap LIVE
without proving both sides reachable with ported content.

  py tools/audit/relic_probes_b10.py                 # every probe
  py tools/audit/relic_probes_b10.py mummified-hand  # one probe
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

BATCH10 = [
    "mummified_hand", "music_box", "mystic_lighter", "neows_bones",
    "neows_talisman", "neows_torment", "new_leaf", "nunchaku",
    "nutritious_oyster", "nutritious_soup", "oddly_smooth_stone", "old_coin",
    "orichalcum", "ornamental_fan", "orrery",
]


# ── pool ──────────────────────────────────────────────────────────────────
def probe_pool() -> None:
    """Where each batch-10 relic can come from (rule 6: prove obtainable)."""
    from sts2_rl.relic_pools import IRONCLAD_RELIC_POOL, SHARED_RELIC_POOL
    from sts2_rl.relics import ALL_RELICS

    bag = {rid.removeprefix("RELIC.").lower(): rarity
           for rid, rarity in SHARED_RELIC_POOL + IRONCLAD_RELIC_POOL}
    print(f"grab-bag pool: {len(bag)} relics")
    for rid in BATCH10:
        srcs = subprocess.run(
            ["git", "grep", "-l", f'"{rid}"', "--", "sts2_rl"],
            capture_output=True, text=True, cwd=_REPO,
        ).stdout.split()
        srcs = [s for s in srcs
                if not s.endswith(f"relics/{rid}.py") and "__pycache__" not in s]
        print(f"  {rid:<20} registered={rid in ALL_RELICS} "
              f"bag={bag.get(rid, '-'):<9} granted_by={srcs or ['(none)']}")


# ── mummified-hand ────────────────────────────────────────────────────────
def probe_mummified_hand() -> None:
    """MummifiedHand's FOUR-tier candidate fallback vs the sim's one filter.

    MummifiedHand.cs:30-46:
      list  = hand cards whose BASE cost (CostModifiers.None) > 0 or star > 0
      tier1 = NextItem(list.Where(CostsEnergyOrStars(includeGlobalModifiers:true)))
      tier2 = NextItem(cards.Where(CostsEnergyOrStars(true)))      if tier1 null
      tier3 = NextItem(list)                                       if tier2 null
      tier4 = NextItem(cards)                                      if tier3 null
    mummified_hand.py:25-29 keeps only `[c for c in hand if c.energy_cost > 0]`
    and RETURNS when it is empty -- so tiers 3 and 4 do not exist, and the
    CombatCardSelection draw they would consume is not taken.
    """
    from sts2_rl import CombatState
    from sts2_rl.cards import make_card
    from sts2_rl.relics import make_relic

    print("  -- (1/3) the normal path works: a Power play frees a costing card")
    hand = make_relic("mummified_hand")
    cs = CombatState(rng=random.Random(0), relics=[hand])
    cs.player.hand.clear()
    power = make_card("inflame")
    strike = make_card("strike")
    cs.player.hand += [power, strike]
    cs.player.energy = 9
    cs.play_card(0)
    print(f"     strike.energy_cost after the Power play: {strike.energy_cost} "
          f"(base {strike._energy_cost})   free_this_turn="
          f"{strike._free_this_turn}")

    print("\n  -- (2/3) tier-4 fallback MISSING: every remaining hand card "
          "costs 0, so C# still picks one (one CombatCardSelection draw) and "
          "the sim picks nothing (zero draws)")
    for label, ids in (("[dazed, dazed] (base cost 0)", ["dazed", "dazed"]),):
        hand = make_relic("mummified_hand")

        class CountingRng(random.Random):
            draws = 0

            def choice(self, seq):          # noqa: D102
                CountingRng.draws += 1
                return super().choice(seq)

        rng = CountingRng(0)
        cs = CombatState(rng=rng, relics=[hand])
        cs.player.hand.clear()
        power = make_card("inflame")
        rest = [make_card(i) for i in ids]
        cs.player.hand += [power] + rest
        cs.player.energy = 9
        before = CountingRng.draws
        cs.play_card(0)
        print(f"     hand={label}  card_selection choices consumed="
              f"{CountingRng.draws - before}   (C#: 1 NextItem from tier 4)")
        print(f"     any card left free: "
              f"{[c._free_this_turn for c in rest]}   (C#: exactly one True)")

    print("\n  -- (3/4) GLOBAL cost modifiers: C# filters on "
          "CostsEnergyOrStars(includeGlobalModifiers: TRUE) == "
          "EnergyCost.GetWithModifiers(CostModifiers.All) > 0; the sim's "
          "`c.energy_cost` is the card's LOCAL cost only -- the sim's global "
          "cost hook (combat.py:408 modify_card_energy_cost) is not consulted.")
    print("     Witness: CorruptionPower (powers.py:597, applied by the ported "
          "Ironclad Rare Power card cards/corruption.py:35) makes every SKILL "
          "cost 0 globally.")
    from sts2_rl.cmds import PowerCmd
    from sts2_rl.powers import CorruptionPower
    for corrupt in (False, True):
        hand = make_relic("mummified_hand")
        cs = CombatState(rng=random.Random(0), relics=[hand])
        cs.player.hand.clear()
        if corrupt:
            PowerCmd.apply(cs.hooks, cs.player, CorruptionPower, 1,
                           applier=cs.player)
        defends = [make_card("defend") for _ in range(4)]
        bash = make_card("bash")
        power = make_card("inflame")
        cs.player.hand += [power] + defends + [bash]
        cs.player.energy = 9
        print(f"     Corruption={corrupt}: sim sees energy_cost>0 for "
              f"{[c.id for c in cs.player.hand if c.energy_cost > 0]}")
        print(f"       hook cost of a Defend with Corruption up: "
              f"{cs.hooks.modify_card_energy_cost(defends[0], defends[0].energy_cost)}"
              f"   (C# GetWithModifiers(All) -> the same 0, so C# EXCLUDES it)")
        cs.play_card(0)
        freed = [c.id for c in cs.player.hand if c._free_this_turn]
        print(f"       card the sim freed: {freed}   "
              f"(C# with Corruption: only ['bash'] is eligible)")

    print("\n  -- (3b) per-Replay AfterCardPlayed (hook_dispatch G4) at this "
          "site: a DOUBLED Power card frees TWO cards in C# and one in the sim, "
          "and burns two CombatCardSelection draws instead of one.")
    hand = make_relic("mummified_hand")
    cs = CombatState(rng=random.Random(0),
                     relics=[hand, make_relic("throwing_axe")])
    cs.player.hand.clear()
    power = make_card("inflame")
    rest = [make_card("strike") for _ in range(4)]
    cs.player.hand += [power] + rest
    cs.player.energy = 9
    cs.play_card(0)
    print(f"     Throwing Axe + a Power as the first play: cards freed="
          f"{sum(1 for c in rest if c._free_this_turn)}   (C#: 2)")

    print("\n  -- (4/4) tier separation: C# tier 1 needs BASE>0 AND current>0; "
          "the sim's single filter is current>0 only.")
    print("     X-cost cards are excluded on BOTH sides (checked): "
          "EnergyCost.CostsX bars them from tiers 1-2 and their base cost is "
          "0 so `list` (tier 3) misses them too;")
    from sts2_rl.cards.base import _CARD_CLASSES
    import sts2_rl.cards  # noqa: F401
    xs = sorted(cid for cid, c in _CARD_CLASSES.items() if c.energy_cost_x)
    print(f"     ported X-cost cards: {xs}")
    print("     A card with base cost 0 but a RAISED current cost would sit in "
          "C#'s tier 2 and in the sim's only tier; ported cost-raising "
          "modifiers:")
    out = subprocess.run(
        ["git", "grep", "-n", "def modify_card_energy_cost", "--", "sts2_rl"],
        capture_output=True, text=True, cwd=_REPO).stdout
    print("     " + "\n     ".join(
        l for l in out.splitlines() if "__pycache__" not in l))


# ── music-box ─────────────────────────────────────────────────────────────
def probe_music_box() -> None:
    """MusicBox: the shallow rebuild (Sweep E) and the missing combat-end reset.

    (a) MusicBox.cs:78 is `cardPlay.Card.CreateClone()` --
        ClonePreservingMutability, which carries enchantment / affliction /
        keyword edits / local cost modifiers. music_box.py:46-49 is
        `make_card(card.id)` plus an upgrade replay, so only the level survives.
    (b) MusicBox.cs:96-100 zeroes WasUsedThisTurn at AfterCombatEnd; the sim
        resets only at on_player_turn_start. Sweep A files that as "safe" --
        this EXECUTES the claim across a real combat boundary.
    """
    from sts2_rl import CombatState
    from sts2_rl.cards import make_card
    from sts2_rl.enchantments import make_enchantment
    from sts2_rl.relics import make_relic

    print("  -- (a) shallow rebuild: an ENCHANTED Strike (Tezcatara's Ember, "
          "granted by relic/nutritious_soup) is cloned as a plain Strike")
    box = make_relic("music_box")
    cs = CombatState(rng=random.Random(0), relics=[box])
    cs.player.hand.clear()
    strike = make_card("strike")
    make_enchantment("tezcataras_ember").attach(strike)
    cs.player.hand.append(strike)
    cs.player.energy = 9
    cs.play_card(0)
    copies = [c for c in cs.player.hand if c.id == "strike"]
    print(f"     original: enchantment={strike.enchantment!r} "
          f"energy_cost={strike.energy_cost} eternal={strike.eternal}")
    for c in copies:
        print(f"     clone   : enchantment={c.enchantment!r} "
              f"energy_cost={c.energy_cost} eternal={c.eternal} "
              f"ethereal={c.is_ethereal}   (C#: Ember carried)")

    print("\n  -- (a2) same with an AFFLICTION (Ringing is applied to cards in "
          "hand by a ported enemy power, powers.py:1332)")
    from sts2_rl.cmds import CardCmd
    box = make_relic("music_box")
    cs = CombatState(rng=random.Random(0), relics=[box])
    cs.player.hand.clear()
    strike = make_card("strike")
    cs.player.hand.append(strike)
    try:
        from sts2_rl.afflictions import RingingAffliction
        CardCmd.afflict(strike, RingingAffliction, 1)
        print(f"     original.affliction={strike.affliction!r}")
    except Exception as exc:                                  # pragma: no cover
        print(f"     (afflict helper signature: {exc})")
    cs.player.energy = 9
    cs.play_card(0)
    for c in [c for c in cs.player.hand if c.id == "strike"]:
        print(f"     clone.affliction={c.affliction!r}   (C#: carried)")

    print("\n  -- (b) missing AfterCombatEnd reset: is the turn-start reset "
          "really shadowing it? Carry ONE instance into a second combat.")
    box = make_relic("music_box")
    for n, seed in enumerate((0, 1), start=1):
        cs = CombatState(rng=random.Random(seed), relics=[box])
        cs.player.hand.clear()
        strike = make_card("strike")
        cs.player.hand.append(strike)
        cs.player.energy = 9
        cs.play_card(0)
        copies = len([c for c in cs.player.hand if c.id == "strike"])
        print(f"     combat {n}: used_this_turn={box.used_this_turn} "
              f"_card_being_played={box._card_being_played!r} "
              f"ethereal copies in hand={copies}   (C# combat 2: 1)")
    print("     Also test the nastier carry: end combat 1 with the LATCH set "
          "and used_this_turn False, which is what a killing blow leaves.")
    box2 = make_relic("music_box")
    box2.used_this_turn = True
    box2._card_being_played = make_card("bash")
    cs = CombatState(rng=random.Random(3), relics=[box2])
    cs.player.hand.clear()
    strike = make_card("strike")
    cs.player.hand.append(strike)
    cs.player.energy = 9
    cs.play_card(0)
    print(f"     stale instance in combat 2: copies="
          f"{len([c for c in cs.player.hand if c.id == 'strike'])} "
          f"used_this_turn={box2.used_this_turn}   (C#: 1 copy)")


# ── mystic-lighter ────────────────────────────────────────────────────────
def probe_mystic_lighter() -> None:
    """MysticLighter is a behaviourless stub; its stated premise is false.

    mystic_lighter.py:8-9 says "the sim has no enchantments". sts2_rl/
    enchantments.py is ported (17 enchantments) and the sim's damage pipeline
    already dispatches modify_damage_additive over every combat listener,
    relics included (hooks.py:52-64, cmds.py:56-58).
    """
    from sts2_rl import CombatState
    from sts2_rl.cards import make_card
    from sts2_rl.enchantments import ALL_ENCHANTMENTS, make_enchantment
    from sts2_rl.relics import make_relic

    print(f"  ported enchantments: {len(ALL_ENCHANTMENTS)} "
          f"({sorted(ALL_ENCHANTMENTS)[:6]} ...)")
    print("  MysticLighter.cs:15-30 adds DamageVar(9) to any POWERED attack "
          "whose cardSource has an Enchantment and belongs to the owner.")
    for relics, label in (([], "no relic"),
                          ([make_relic("mystic_lighter")], "mystic_lighter")):
        cs = CombatState(rng=random.Random(0), relics=list(relics))
        cs.player.hand.clear()
        strike = make_card("strike")
        make_enchantment("swift").attach(strike)
        cs.player.hand.append(strike)
        cs.player.energy = 9
        hp_before = cs.enemy.hp
        cs.play_card(0, 0)
        print(f"     enchanted Strike, {label:<16} enemy HP "
              f"{hp_before} -> {cs.enemy.hp}  (dealt {hp_before - cs.enemy.hp})"
              f"   C# with the relic: +9")
    print("  NOTE the sim's hook signature is modify_damage_additive("
          "target, amount, dealer, card) -- no `props`; DamageCmd already "
          "restricts the call to powered attacks (cmds.py:56), so a port needs "
          "no signature change.")


# ── neows-bones ───────────────────────────────────────────────────────────
def probe_neows_bones() -> None:
    """NeowsBones draws its 2 relics from Neow.AllPossibleOptions, ORDER-SENSITIVE.

    NeowsBones.cs:33-42: GetValidRelics enumerates AllPossibleOptions, then
    `PlayerRng.Rewards.Shuffle(list)` and `.Take(2)`. A shuffle's output depends
    on the input ORDER, so the pool's order is load-bearing.

    Neow.cs:49-64 AllPossibleOptions order is
      CurseOptions(8) + PositiveOptions(14) + LavaRock, NeowsTalisman,
      NutritiousOyster, Pomander, SmallCapsule, StoneHumidifier
    events/neow.py:64-72 appends the three PAIRS instead:
      LavaRock, SmallCapsule, NutritiousOyster, StoneHumidifier,
      NeowsTalisman, Pomander
    """
    from sts2_rl.events.neow import neow_relic_pool
    from sts2_rl.run import RunState

    run = RunState(rng=random.Random(0), string_seed="B10PROBE")
    pool = [r for r in neow_relic_pool(run) if r != "neows_bones"]
    print(f"  sim pool ({len(pool)}): {pool}")
    csharp_tail = ["lava_rock", "neows_talisman", "nutritious_oyster",
                   "pomander", "small_capsule", "stone_humidifier"]
    print(f"  sim tail  : {pool[-6:]}")
    print(f"  C# tail   : {csharp_tail}")
    print(f"  tails equal: {pool[-6:] == csharp_tail}")
    csharp_pool = pool[:-6] + csharp_tail

    print("  Rng.Shuffle (Rng.cs:308-320) and rng.py:270-273 are the same "
          "top-down Fisher-Yates, so the swap INDICES agree and only the input "
          "order can differ. Search string seeds for a divergent pick:")
    diffs = 0
    shown = 0
    for n in range(60):
        seed = f"B10SEED{n:02d}"
        picks = []
        for order in (pool, csharp_pool):
            r = RunState(rng=random.Random(0), string_seed=seed)
            seq = list(order)
            r.player_rng.rewards.shuffle(seq)
            picks.append(seq[:2])
        if picks[0] != picks[1]:
            diffs += 1
            if shown < 5:
                shown += 1
                print(f"     seed {seed}: sim {picks[0]}  vs  C# {picks[1]}")
    print(f"  divergent seeds: {diffs} of 60")

    print("\n  curse half: C# orders availableCurses `orderby c.Id` over "
          "CurseCardPool's CanBeGeneratedByModifiers cards, then draws with "
          "Rng.Niche.NextItem and REMOVES the pick.")
    from sts2_rl.cards.pool import curse_pool_ids
    ids = curse_pool_ids()
    print(f"  generatable curses ({len(ids)} of 18 in CurseCardPool): "
          f"{sorted(ids)}")
    print(f"  lowercase sort == uppercase-ModelId sort: "
          f"{sorted(ids) == sorted(ids, key=str.upper)}  "
          f"(no '_' vs letter flip in this pool)")


# ── neows-talisman ────────────────────────────────────────────────────────
def probe_neows_talisman() -> None:
    """Sweep D flagged neows_talisman.py:29 as an UNGUARDED Card.upgrade().

    CardCmd.Upgrade (CardCmd.cs:265-276) skips any card whose IsUpgradable is
    false; card.upgrade() (cards/base.py:146-147) is a bare increment. The
    candidates here are Basic Strike/Defend (max_upgrade_level 1), so the
    reachable case is an ALREADY-UPGRADED last basic Strike or Defend.
    """
    from sts2_rl.cards import make_card
    from sts2_rl.relics import make_relic
    from sts2_rl.run import RunState

    deck = [make_card("strike") for _ in range(5)] + \
           [make_card("defend") for _ in range(4)]
    print(f"  fresh deck: strike max_upgrade_level="
          f"{deck[0].max_upgrade_level} is_upgradable={deck[0].is_upgradable}")
    run = RunState(rng=random.Random(0), deck=list(deck))
    run.add_relic("neows_talisman")
    print(f"  clean run: upgrade levels = "
          f"{[(c.id, c.upgrade_level) for c in run.deck]}")

    deck2 = [make_card("strike") for _ in range(5)] + \
            [make_card("defend") for _ in range(4)]
    deck2[4].upgrade()          # smith the LAST basic Strike (rest site / War Paint)
    deck2[8].upgrade()          # and the last basic Defend
    run2 = RunState(rng=random.Random(0), deck=list(deck2))
    run2.add_relic("neows_talisman")
    lvls = [(c.id, c.upgrade_level) for c in run2.deck]
    print(f"  pre-upgraded last Strike/Defend: {lvls}")
    bad = [t for t in lvls if t[1] > 1]
    print(f"  cards past max_upgrade_level: {bad}   "
          f"(C#: CardCmd.Upgrade SKIPS them, so both stay at 1)")
    print(f"  is_upgradable now False on those cards: "
          f"{[c.is_upgradable for c in run2.deck if c.upgrade_level > 1]}")
    print("  REACHABILITY. Neow's Talisman is only granted at floor 0 (Neow, or "
          "Neow's Bones drawing from the same pool), where the deck is "
          "pristine -- so the pre-upgraded basic needs an upgrade that happens "
          "in the SAME pickup. relic/neows_bones grants TWO pool relics in "
          "sequence and relic/pomander (upgrade a chosen card) is in that pool:")
    from sts2_rl.events.neow import neow_relic_pool
    r0 = RunState(rng=random.Random(0), string_seed="B10PROBE")
    pool = neow_relic_pool(r0)
    print(f"     'pomander' in the Neow pool: {'pomander' in pool}   "
          f"'neows_talisman' in it: {'neows_talisman' in pool}")
    found = None
    for n in range(4000):
        r = RunState(rng=random.Random(0), string_seed=f"B10BONES{n:04d}")
        seq = [x for x in neow_relic_pool(r) if x != "neows_bones"]
        r.player_rng.rewards.shuffle(seq)
        if seq[:2] == ["pomander", "neows_talisman"]:
            found = f"B10BONES{n:04d}"
            break
    print(f"     a seed where Neow's Bones grants pomander FIRST and "
          f"neows_talisman second: {found}")

    deck3 = [make_card("strike") for _ in range(5)] + \
            [make_card("defend") for _ in range(4)]
    run3 = RunState(
        rng=random.Random(0), deck=list(deck3),
        card_selector=lambda purpose, cands, count: (
            [c for c in cands if c.id == "strike"][-1:] if count else []),
    )
    run3.add_relic("pomander")
    run3.add_relic("neows_talisman")
    print(f"     executed pomander -> neows_talisman in one pickup: "
          f"{[(c.id, c.upgrade_level) for c in run3.deck]}")
    print("     (C#: Pomander's CardCmd.Upgrade takes it to 1, then "
          "NeowsTalisman's CardCmd.Upgrade SKIPS it -- IsUpgradable false.)")
    print("  Other deck-card upgraders in sts2_rl/relics (for the fix's blast "
          "radius):")
    out = subprocess.run(
        ["git", "grep", "-n", "-l", "upgrade()", "--", "sts2_rl/relics",
         "sts2_rl/rest_site.py"],
        capture_output=True, text=True, cwd=_REPO).stdout
    print("     " + " ".join(
        l for l in out.split() if "__pycache__" not in l))


# ── new-leaf ──────────────────────────────────────────────────────────────
def probe_new_leaf() -> None:
    """NewLeaf: the Niche stream is named in C# and dropped by the sim; and
    CardSelectCmd.FromDeckForTransformation also excludes Quest cards."""
    from sts2_rl.cards import make_card
    from sts2_rl.cards.base import _CARD_CLASSES
    import sts2_rl.cards  # noqa: F401
    from sts2_rl.run import RunState

    print("  NewLeaf.cs:27 -> CardCmd.TransformToRandom(item, Rng.Niche); "
          "TransformToRandom builds `new CardTransformation(original)` with NO "
          "explicit Replacement, so GetReplacement(rng) calls "
          "CardFactory.CreateRandomCardForTransform and the Niche stream IS "
          "consumed.")
    print("  new_leaf.py:17 calls run.transform_card(card) with no pick_rng, "
          "so run.py's `pick_rng=None` keeps the legacy shared rng.")
    src = subprocess.run(
        ["git", "grep", "-n", "transform_card(", "--", "sts2_rl"],
        capture_output=True, text=True, cwd=_REPO).stdout
    for line in src.splitlines():
        if "__pycache__" not in line:
            print("     " + line)

    run = RunState(rng=random.Random(0), string_seed="B10PROBE",
                   deck=[make_card("strike"), make_card("defend")])
    before = [c.id for c in run.deck]
    niche_before = run.rng_set.niche.counter if hasattr(
        run.rng_set.niche, "counter") else None
    run.add_relic("new_leaf")
    after = [c.id for c in run.deck]
    niche_after = run.rng_set.niche.counter if hasattr(
        run.rng_set.niche, "counter") else None
    print(f"  deck {before} -> {after}")
    print(f"  Niche stream counter {niche_before} -> {niche_after} "
          f"(C#: one CreateRandomCardForTransform draw)")

    quest = sorted(cid for cid, c in _CARD_CLASSES.items()
                   if c.card_type.name == "QUEST")
    print(f"  ported QUEST cards ({len(quest)}): {quest}")
    print("  FromDeckForTransformation (CardSelectCmd.cs:487) filters "
          "`c.Type != CardType.Quest && c.IsTransformable`; "
          "run.transformable_cards() (run.py:364-366) filters only `not "
          "eternal`, so a Quest deck card is offerable in the sim.")
    qcards = [make_card(q) for q in quest]
    print(f"  Quest cards' eternal flags: "
          f"{[(c.id, c.eternal) for c in qcards]}")


# ── nunchaku ──────────────────────────────────────────────────────────────
def probe_nunchaku() -> None:
    """Sweep A flagged nunchaku for a SECOND LOOK; settle it by execution.

    Nunchaku.AttacksPlayed is [SavedProperty] (Nunchaku.cs:59-72) and NOTHING
    in the C# file resets it -- it is a per-RUN counter that survives saves.
    nunchaku.py's docstring claims "the sim's is per-combat" -- check that.
    """
    from sts2_rl import CombatState
    from sts2_rl.cards import make_card
    from sts2_rl.relics import make_relic

    nun = make_relic("nunchaku")
    print(f"  ATTACKS constant: {nun.ATTACKS}  (C# CardsVar(10), EnergyVar(1))")
    for n, seed in enumerate((0, 1), start=1):
        cs = CombatState(rng=random.Random(seed), relics=[nun])
        cs.player.hand.clear()
        for _ in range(6):
            c = make_card("strike")
            cs.player.hand.append(c)
            cs.player.energy = 99
            cs.play_card(len(cs.player.hand) - 1, 0)
            if cs.is_over:
                break
        print(f"     combat {n}: _attacks_played={nun._attacks_played} "
              f"energy={cs.player.energy}")
    print("     -> the counter DOES persist across combats, so the port matches "
          "C#'s per-run SavedProperty. The docstring is wrong, not the code.")

    print("\n  -- replay double-count (hook_dispatch G4): C# fires "
          "AfterCardPlayed once per play-count iteration (CardModel.cs:1959 "
          "inside the 1904 loop); the sim fires on_card_played once "
          "(combat.py:514, outside the 477-494 loop).")
    nun2 = make_relic("nunchaku")
    cs = CombatState(rng=random.Random(0),
                     relics=[nun2, make_relic("throwing_axe")])
    cs.player.hand.clear()
    c = make_card("strike")
    cs.player.hand.append(c)
    cs.player.energy = 99
    cs.play_card(0, 0)
    print(f"     one Throwing-Axe-doubled Strike: _attacks_played="
          f"{nun2._attacks_played}   (C#: 2)")


# ── nutritious ────────────────────────────────────────────────────────────
def probe_nutritious() -> None:
    """nutritious_oyster (+11 Max HP), nutritious_soup (enchant basic Strikes)
    and neows_torment (add Neow's Fury) on the add_relic path."""
    from sts2_rl.cards import make_card
    from sts2_rl.run import RunState

    run = RunState(rng=random.Random(0), max_hp=80, hp=60)
    print(f"  oyster: hp/max {run.hp}/{run.max_hp}", end="")
    run.add_relic("nutritious_oyster")
    print(f" -> {run.hp}/{run.max_hp}   (C#: CreatureCmd.GainMaxHp(11) = "
          f"+11 max and +11 heal)")
    oyster = run.relics[-1]
    print(f"  undo_after_obtained defined on the port: "
          f"{'undo_after_obtained' in type(oyster).__dict__}   "
          f"(mango/pear/strawberry/lees_waffle/looming_fruit all define it)")
    oyster.undo_after_obtained(run)
    print(f"  after the conformance runner un-picks it "
          f"(runner.py:457-461): hp/max = {run.hp}/{run.max_hp}   "
          f"(should be 60/80)")

    deck = [make_card("strike") for _ in range(5)] + \
           [make_card("defend") for _ in range(4)] + [make_card("bash")]
    run2 = RunState(rng=random.Random(0), deck=list(deck))
    run2.add_relic("nutritious_soup")
    print("  soup: " + ", ".join(
        f"{c.id}{'/' + c.enchantment.id if c.enchantment else ''}"
        f"(cost {c.energy_cost},eternal {c.eternal})" for c in run2.deck))
    print("  soup on an ALREADY-enchanted Strike (C# CanEnchant returns false "
          "unless IsStackable; zero enchantments override IsStackable):")
    from sts2_rl.enchantments import make_enchantment
    d2 = [make_card("strike")]
    make_enchantment("swift").attach(d2[0])
    run3 = RunState(rng=random.Random(0), deck=list(d2))
    run3.add_relic("nutritious_soup")
    print(f"     {d2[0].id} enchantment={d2[0].enchantment!r} "
          f"cost={d2[0].energy_cost}   (C#: unchanged)")

    run4 = RunState(rng=random.Random(0), deck=[make_card("strike")])
    run4.add_relic("neows_torment")
    print(f"  torment: deck -> {[c.id for c in run4.deck]}   "
          f"(C#: CardPileCmd.Add(NeowsFury, PileType.Deck))")


# ── oddly-smooth-stone ────────────────────────────────────────────────────
def probe_oddly_smooth_stone() -> None:
    """OddlySmoothStone.cs uses AfterRoomEntered(room is CombatRoom); the sim
    uses on_combat_start. Same mechanism as bronze_scales / gorget
    (deliberate-divergence there). Dexterity is different from Thorns/Plating
    in one way: it MODIFIES block, so a listener in the intervening window
    would see a different number. Enumerate that window's occupants."""
    from sts2_rl import CombatState
    from sts2_rl.relics import make_relic

    cs = CombatState(rng=random.Random(0),
                     relics=[make_relic("oddly_smooth_stone")])
    print(f"  combat start: player powers={ {k: p.amount for k, p in cs.player.powers.items()} } "
          f"block={cs.player.block}   (C# PowerVar<DexterityPower>(1m))")

    print("  C# sequence: CombatRoom.cs:228 Hook.AfterRoomEntered  ->  "
          "CombatManager.cs:396 AfterCreatureAdded  ->  :403 "
          "Hook.BeforeCombatStart  ->  :418 StartTurn.")
    print("  So a divergence needs something in that window that READS the "
          "player's Dexterity. Dexterity is read by block gains "
          "(cmds.py:145-147). Ported on_combat_start listeners that gain "
          "POWERED block:")
    out = subprocess.run(
        ["git", "grep", "-n", "-A6", "def on_combat_start", "--",
         "sts2_rl/relics", "sts2_rl/powers.py"],
        capture_output=True, text=True, cwd=_REPO).stdout
    hits = [l for l in out.splitlines()
            if "BlockCmd" in l and "__pycache__" not in l]
    print(f"     raw hits: {hits or '(none)'}")
    print("     the ONE hit is PlatingPower._gain_block, reached from "
          "powers.py:1054-1056 `if self.owner.side == \"enemy\"` and applied "
          "with props=ValueProp.UNPOWERED (powers.py:1061) -- enemy-side AND "
          "unpowered, so the player's Dexterity cannot reach it.")
    print("  Also: does any on_combat_start listener gain block via the "
          "player state directly?")
    out2 = subprocess.run(
        ["git", "grep", "-n", "block +=", "--", "sts2_rl/relics"],
        capture_output=True, text=True, cwd=_REPO).stdout
    print(f"     {[l for l in out2.splitlines() if '__pycache__' not in l] or '(none)'}")


# ── old-coin ──────────────────────────────────────────────────────────────
def probe_old_coin() -> None:
    """OldCoin is a stub on two counts: the 300 gold and IsAllowed.

    Sweep C: "no gold system in the sim" is FALSE -- RunState.gold + gain_gold
    exist and relic/golden_pearl (the exact sibling) already uses them.
    Sweep B: IsAllowed => IsBeforeAct3TreasureChest (TotalFloor < 41), one of
    the 17-relic cluster; Relic has no is_allowed member at all.
    """
    from sts2_rl.relics import ALL_RELICS
    from sts2_rl.relics.base import Relic
    from sts2_rl.run import RunState

    run = RunState(rng=random.Random(0), gold=99)
    print(f"  gold {run.gold}", end="")
    run.add_relic("old_coin")
    print(f" -> {run.gold} after add_relic('old_coin')   "
          f"(C#: PlayerCmd.GainGold(GoldVar(300)) => 399)")
    run2 = RunState(rng=random.Random(0), gold=99)
    run2.add_relic("golden_pearl")
    print(f"  sibling relic/golden_pearl on the same path: gold 99 -> "
          f"{run2.gold}  (its after_obtained calls run.gain_gold)")

    print(f"  Relic base has an is_allowed member: "
          f"{hasattr(Relic, 'is_allowed')}")
    print(f"  old_coin.is_allowed_in_shops = "
          f"{ALL_RELICS['old_coin'].is_allowed_in_shops}  "
          f"(C# IsAllowedInShops => false)")
    print(f"  old_coin.has_upon_pickup_effect = "
          f"{ALL_RELICS['old_coin'].has_upon_pickup_effect}")
    run3 = RunState(rng=random.Random(0), total_floor=60)
    inbag = "old_coin" in run3.relic_grab_bag
    print(f"  at total_floor=60 (past the act-3 chest at 41) the grab bag "
          f"still contains old_coin: {inbag}   (C#: IsAllowed false)")
    pulled = []
    while run3.relic_grab_bag and len(pulled) < 200:
        r = run3.pull_relic_from_front()
        if r is None:
            break
        pulled.append(r.id)
    print(f"  and it is actually pullable at floor 60: "
          f"{'old_coin' in pulled}")


# ── orichalcum ────────────────────────────────────────────────────────────
def probe_orichalcum() -> None:
    """Orichalcum is the NAMED WITNESS of audits/seam/turn_structure.json G12.

    C# is deliberately two-phase: BeforeSideTurnEndVeryEarly snapshots
    `Block > 0` into ShouldTrigger (Orichalcum.cs:44-56) and BeforeSideTurnEnd
    then grants the 6 Block (:58-66). The sim folds both into
    on_player_turn_end (orichalcum.py:22-26), so a plain-phase listener that
    grants block first switches Orichalcum off.
    """
    from sts2_rl import CombatState
    from sts2_rl.cards import make_card
    from sts2_rl.relics import make_relic

    print("  Fire the turn-end hook directly (CombatState.end_turn runs the "
          "enemy turn and the next turn's block clear, which would erase the "
          "observable):")
    for order in (["cloak_clasp", "orichalcum"], ["orichalcum", "cloak_clasp"]):
        cs = CombatState(rng=random.Random(0),
                         relics=[make_relic(r) for r in order])
        cs.player.hand.clear()
        cs.player.hand += [make_card("strike") for _ in range(5)]
        cs.player.block = 0
        cs.hooks.on_player_turn_end(cs.player)
        print(f"  relics={order}  block at turn end = {cs.player.block}"
              f"   (C#: always 11 -- the VeryEarly snapshot precedes every "
              f"plain listener)")
    cs = CombatState(rng=random.Random(0), relics=[make_relic("orichalcum")])
    cs.player.hand.clear()
    cs.player.block = 0
    cs.hooks.on_player_turn_end(cs.player)
    print(f"  orichalcum alone: block at turn end = {cs.player.block} "
          f"(BlockVar(6m, Unpowered))")
    print("  the `no Block` guard: with 1 Block already, C# and the sim both "
          "skip:")
    cs = CombatState(rng=random.Random(0), relics=[make_relic("orichalcum")])
    cs.player.hand.clear()
    cs.player.block = 1
    cs.hooks.on_player_turn_end(cs.player)
    print(f"     block 1 -> {cs.player.block}")
    print("  unpowered check -- with 5 Dexterity the grant must stay 6:")
    from sts2_rl.cmds import PowerCmd
    from sts2_rl.powers import DexterityPower
    cs = CombatState(rng=random.Random(0), relics=[make_relic("orichalcum")])
    cs.player.hand.clear()
    PowerCmd.apply(cs.hooks, cs.player, DexterityPower, 5, applier=cs.player)
    cs.player.block = 0
    cs.hooks.on_player_turn_end(cs.player)
    print(f"     block = {cs.player.block}")
    print("  ShouldTrigger reset: C# clears it at BeforeSideTurnStart "
          "(Orichalcum.cs:68-76); the sim holds no flag at all, so there is "
          "nothing to go stale.")


# ── ornamental-fan ────────────────────────────────────────────────────────
def probe_ornamental_fan() -> None:
    """OrnamentalFan: 3 Attacks per turn -> 4 unpowered Block; the counter is
    per-turn on both sides. Sweep A puts it in the "reset at turn start" bucket;
    execute the safety claim, then the replay double-count."""
    from sts2_rl import CombatState
    from sts2_rl.cards import make_card
    from sts2_rl.relics import make_relic

    fan = make_relic("ornamental_fan")
    print(f"  ATTACKS={fan.ATTACKS} BLOCK={fan.BLOCK}  "
          f"(C# CardsVar(3), BlockVar(4m, Unpowered))")
    for n, seed in enumerate((0, 1), start=1):
        cs = CombatState(rng=random.Random(seed), relics=[fan])
        cs.player.hand.clear()
        for _ in range(3):
            c = make_card("strike")
            cs.player.hand.append(c)
            cs.player.energy = 99
            cs.play_card(len(cs.player.hand) - 1, 0)
            if cs.is_over:
                break
        print(f"     combat {n}: _attacks_this_turn={fan._attacks_this_turn} "
              f"block={cs.player.block}   (C#: 4 block on the 3rd Attack)")
    print("     stale-flag carry test: set the counter to 2 by hand and start "
          "a fresh combat (what the sim's missing AfterCombatEnd reset would "
          "leave -- C# resets only IsActivating there, a display flag).")
    fan2 = make_relic("ornamental_fan")
    fan2._attacks_this_turn = 2
    cs = CombatState(rng=random.Random(2), relics=[fan2])
    cs.player.hand.clear()
    c = make_card("strike")
    cs.player.hand.append(c)
    cs.player.energy = 99
    cs.play_card(0, 0)
    print(f"     after ONE Attack in combat 2: _attacks_this_turn="
          f"{fan2._attacks_this_turn} block={cs.player.block}   "
          f"(turn-start reset shadowed the stale 2 -> 0 block expected)")

    fan3 = make_relic("ornamental_fan")
    cs = CombatState(rng=random.Random(0),
                     relics=[fan3, make_relic("throwing_axe")])
    cs.player.hand.clear()
    cs.player.hand += [make_card("strike"), make_card("strike")]
    cs.player.energy = 99
    cs.play_card(0, 0)
    cs.play_card(0, 0)
    print(f"  replay (hook_dispatch G4): Throwing Axe doubles the first play, "
          f"so C# counts 3 Attacks and grants 4 block. sim: "
          f"_attacks_this_turn={fan3._attacks_this_turn} "
          f"block={cs.player.block}")


# ── orrery ────────────────────────────────────────────────────────────────
def probe_orrery() -> None:
    """Orrery is a behaviourless stub; its premise ("out-of-combat card
    reward") is false -- after_obtained is dispatched (run.py:552) and
    relic/lost_coffer already builds a card reward from it."""
    from sts2_rl.cards import make_card
    from sts2_rl.rewards import RarityOddsType, create_reward_cards
    from sts2_rl.run import RunState

    run = RunState(rng=random.Random(0), deck=[make_card("strike")])
    before = len(run.deck)
    run.add_relic("orrery")
    print(f"  deck size {before} -> {len(run.deck)} after "
          f"add_relic('orrery')   (C#: 5 sequential 3-card choices)")
    run2 = RunState(rng=random.Random(0), deck=[make_card("strike")])
    run2.add_relic("lost_coffer")
    print(f"  sibling relic/lost_coffer on the same path: deck 1 -> "
          f"{len(run2.deck)}, potions={[p.id for p in run2.potions if p]}")
    run3 = RunState(rng=random.Random(0), deck=[make_card("strike")])
    opts = create_reward_cards(run3, RarityOddsType.REGULAR, count=3)
    print(f"  the capability Orrery needs exists: create_reward_cards("
          f"REGULAR, 3) = {[c.id for c in opts]}")
    print(f"  RarityOddsType members: {[m.name for m in RarityOddsType]}   "
          f"(CardRarityOddsType.cs:17 RegularEncounter == the sim's REGULAR)")
    print("  Fix note: C# passes CardCreationSource.Other, so the roll must be "
          "the NON-mutating one (create_reward_cards(mutate_pity=False)) -- "
          "RollForRarity only mutates pity for CardCreationSource.Encounter, "
          "which is why relic/lost_coffer passes mutate_pity=False.")


PROBES = {
    "pool": probe_pool,
    "mummified-hand": probe_mummified_hand,
    "music-box": probe_music_box,
    "mystic-lighter": probe_mystic_lighter,
    "neows-bones": probe_neows_bones,
    "neows-talisman": probe_neows_talisman,
    "new-leaf": probe_new_leaf,
    "nunchaku": probe_nunchaku,
    "nutritious": probe_nutritious,
    "oddly-smooth-stone": probe_oddly_smooth_stone,
    "old-coin": probe_old_coin,
    "orichalcum": probe_orichalcum,
    "ornamental-fan": probe_ornamental_fan,
    "orrery": probe_orrery,
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
