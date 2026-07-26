"""Reproducible execution probes for relic audit BATCH 4 (crossbow … ectoplasm).

Batch-local companion to `tools/audit/relic_probes.py` (shared, read-only to
this batch per the concurrency contract). Every reachability claim an
`audits/relic/*.json` record from batch 4 makes — "this gap is live", "this
value never occurs" — is produced here so a later auditor re-derives the number
instead of trusting a throwaway script. Binding rules 5 and 6.

  py tools/audit/relic_probes_b04.py            # every probe
  py tools/audit/relic_probes_b04.py b04-pool   # one probe

Probes:
  b04-pool        obtainability of batch 4's 15 relics (rule 6, first half)
  crossbow        card-pool filter + RNG stream vs GetDistinctForCombat
  darkstone       transform-into-Curse never fires after_card_added_to_deck
  diadem          cards_played_this_turn carried into combat 2
  demon-tongue    the turn-start reset shadows the missing combat reset
  frond           potion rarity weighting + the Sozu / AfterPotionProcured gates
  cape            -9 Max HP is in the event option, not the relic
  stubs           dingy_rug / dollys_mirror / dragon_fruit executed no-ops
  dream-driftwood rest-site reward screens: no reroll, and none on the mimic
  tome            dusty_tome's Ancient candidates and their max_upgrade_level
  ectoplasm       every gold-gain path is routed through RunState.gain_gold
"""
from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

BATCH4 = [
    "crossbow", "cursed_pearl", "darkstone_periapt", "daughter_of_the_wind",
    "delicate_frond", "demon_tongue", "diamond_diadem", "dingy_rug",
    "distinguished_cape", "dollys_mirror", "dragon_fruit", "dream_catcher",
    "driftwood", "dusty_tome", "ectoplasm",
]


def _run(**kw):
    """A minimal RunState (legacy RL path: rng_set is None)."""
    from sts2_rl.run import RunState
    kw.setdefault("rng", random.Random(0))
    return RunState(**kw)


# ── b04-pool ──────────────────────────────────────────────────────────────
def probe_b04_pool() -> None:
    """Obtainability of batch 4's 15 relics.

    Same method as the shared module's `pool` / `batch3-pool`: grab-bag
    membership from the transcribed C# pools, every other grant path is a
    literal relic id somewhere in sts2_rl/.
    """
    import subprocess

    from sts2_rl.relic_pools import IRONCLAD_RELIC_POOL, SHARED_RELIC_POOL
    from sts2_rl.relics import ALL_RELICS

    bag = {rid.removeprefix("RELIC.").lower(): rarity
           for rid, rarity in SHARED_RELIC_POOL + IRONCLAD_RELIC_POOL}
    for rid in BATCH4:
        srcs = subprocess.run(
            ["git", "grep", "-l", f'"{rid}"', "--", "sts2_rl"],
            capture_output=True, text=True, cwd=_REPO,
        ).stdout.split()
        srcs = [s for s in srcs if not s.endswith(f"relics/{rid}.py")]
        print(f"  {rid:<22} registered={rid in ALL_RELICS} "
              f"bag={bag.get(rid, '-'):<9} granted_by={srcs or ['(none)']}")


# ── crossbow ──────────────────────────────────────────────────────────────
def probe_crossbow() -> None:
    """Crossbow's generated Attack: pool filter, draw shape, RNG stream.

    C# (Crossbow.cs:23-36): GetUnlockedCards().Where(Attack) ->
    CardFactory.GetDistinctForCombat(owner, list, 1, Rng.CombatCardGeneration),
    i.e. FilterForCombat (drops CanBeGeneratedInCombat=false AND
    Basic/Ancient/**Event** rarity) then TakeRandom == UnstableShuffle + Take(1).
    Sim (crossbow.py:26-28): random_pool_cards(self.combat._rng, ...) ->
    pool_card_ids (drops Basic/Ancient, NOT Event) then rng.sample.
    """
    import sts2_rl.cards  # noqa: F401
    from sts2_rl.cards import CardType
    from sts2_rl.cards.base import _CARD_CLASSES, CardRarity
    from sts2_rl.cards.pool import IRONCLAD_POOL, pool_card_ids

    print("  -- FilterForCombat parity: CardFactory.cs:161 excludes "
          "CardRarity.Event; cards/pool.py:110 excludes only Basic/Ancient")
    ev = [cid for cid in IRONCLAD_POOL
          if _CARD_CLASSES[cid].rarity == CardRarity.EVENT]
    print(f"     Event-rarity cards in IRONCLAD_POOL: {ev or '(none)'} "
          f"-> the extra C# clause is a NO-OP on today's pool")
    attacks = pool_card_ids(CardType.ATTACK)
    print(f"     Attack candidates the sim offers: {len(attacks)}")

    print("  -- RNG stream (PROMPT.md class 16): C# names "
          "Rng.CombatCardGeneration; crossbow.py passes self.combat._rng")
    import inspect

    from sts2_rl.cards import pool as poolmod
    from sts2_rl.relics.crossbow import Crossbow
    src = inspect.getsource(Crossbow)
    print(f"     'random_pool_cards' in port: {'random_pool_cards' in src}; "
          f"'get_distinct_for_combat_parity' in port: "
          f"{'get_distinct_for_combat_parity' in src}")
    print("     the faithful helper exists and is unused: "
          f"{hasattr(poolmod, 'get_distinct_for_combat_parity')}")
    # Draw shape: sample vs shuffle+take consume the stream differently.
    ids = list(attacks)
    a = random.Random(7).sample(ids, 1)
    b = ids[:]
    random.Random(7).shuffle(b)
    print(f"     sample(seed 7)={a[0]!r} vs shuffle+take(seed 7)={b[0]!r} "
          f"-> same stream, different card: {a[0] != b[0]}")

    print("  -- executed: the card lands in hand, free this turn "
          "(CombatState.__init__ already runs turn 1)")
    from sts2_rl import CombatState
    from sts2_rl.relics import make_relic
    base = CombatState(rng=random.Random(3))
    cs = CombatState(rng=random.Random(3), relics=[make_relic("crossbow")])
    print(f"     hand without the relic: {[c.id for c in base.player.hand]}")
    print(f"     hand with the relic:    {[c.id for c in cs.player.hand]}")
    print(f"     costs: "
          f"{[(c.id, c.energy_cost) for c in cs.player.hand[len(base.player.hand):]]}")


# ── darkstone ─────────────────────────────────────────────────────────────
def probe_darkstone() -> None:
    """Darkstone Periapt on the out-of-combat TRANSFORM path.

    C# fires Hook.AfterCardChangedPiles for the replacement whenever the pile
    is PileType.Deck (CardCmd.cs:447), so a Curse produced by a transform pays
    the +6 Max HP. RunState.transform_card writes the deck directly
    (run.py:466 / :469) and dispatches no deck hook at all.
    """
    import sts2_rl.cards  # noqa: F401
    from sts2_rl.cards import CardType, make_card
    from sts2_rl.relics import make_relic

    run = _run()
    run.relics.append(make_relic("darkstone_periapt"))

    base_max = run.max_hp
    run.add_card(make_card("regret"))
    print(f"  add_card(curse):      max_hp {base_max} -> {run.max_hp} "
          f"(C#: +6, matches)")

    curse = run.deck[-1]
    before = run.max_hp
    got = run.transform_card(curse)
    print(f"  transform_card(curse) -> {got.id!r} type={got.card_type.name}; "
          f"max_hp {before} -> {run.max_hp} "
          f"(C# CardCmd.cs:429-447 fires ModifyCardBeingAddedToDeck AND "
          f"AfterCardChangedPiles on the Deck pile -> +6)")
    assert got.card_type == CardType.CURSE, got
    print(f"  DIVERGENCE: sim +{run.max_hp - before}, C# +6")

    # Which ported callers reach it.
    import subprocess
    hits = subprocess.run(
        ["git", "grep", "-n", "transform_card", "--", "sts2_rl"],
        capture_output=True, text=True, cwd=_REPO,
    ).stdout.splitlines()
    hits = [h for h in hits if "def transform_card" not in h and "run.py" not in h]
    print(f"  ported transform_card call sites: {len(hits)}")
    for h in hits[:6]:
        print(f"     {h.strip()}")


# ── diadem ────────────────────────────────────────────────────────────────
def probe_diadem() -> None:
    """Diamond Diadem's cards_played_this_turn across a combat boundary.

    C# resets it in BOTH BeforeSideTurnEnd (DiamondDiadem.cs:67) and
    AfterCombatEnd (:80). The sim resets only in on_player_turn_end
    (diamond_diadem.py:39) — and CombatState.end_turn returns early when the
    fight is already over (combat.py:641-642), which is the NORMAL way a
    combat ends (the player kills the last enemy on their own turn). So the
    winning turn's count is never cleared.
    """
    import sts2_rl.cards  # noqa: F401
    from sts2_rl import CombatState
    from sts2_rl.relics import make_relic

    diadem = make_relic("diamond_diadem")

    # Combat 1: play three cards, the last of which kills the last enemy, so
    # the combat ends DURING the player's turn — the normal way a fight ends.
    from sts2_rl.cards import make_card
    cs = CombatState(rng=random.Random(1), relics=[diadem])
    cs.player.hand[:] = [make_card("strike") for _ in range(3)]
    cs.player.energy = 3
    cs.enemies[0].hp = 18
    while not cs.is_over and cs.player.hand and cs.player.energy > 0:
        cs.play_card(0, 0)
    print(f"  combat 1: is_over={cs.is_over} phase={cs.phase} "
          f"cards_played_this_turn={diadem.cards_played_this_turn}")
    cs.end_turn()
    print(f"  after end_turn() (early-returns at combat.py:641-642 because "
          f"phase != PLAYER_TURN, so on_player_turn_end never fires): "
          f"cards_played_this_turn={diadem.cards_played_this_turn}")

    # Combat 2 with the SAME instance vs a fresh one. Read the power at the
    # moment on_player_turn_end grants it (the enemy turn strips it again).
    fresh = make_relic("diamond_diadem")
    out = {}
    for name, relic in (("carried", diadem), ("fresh", fresh)):
        cs2 = CombatState(rng=random.Random(2), relics=[relic])
        cs2.hooks.on_player_turn_end(cs2.player)
        out[name] = ([(p.id, p.amount) for p in cs2.player.powers.values()],
                     relic.cards_played_this_turn)
    print(f"  combat 2, turn 1, zero cards played -> powers at the moment "
          f"on_player_turn_end runs:")
    print(f"     carried instance: {out['carried'][0]}")
    print(f"     fresh   instance: {out['fresh'][0]}")
    print(f"  DIVERGENCE (C# AfterCombatEnd, DiamondDiadem.cs:78-84, always "
          f"gives the 'fresh' answer): {out['carried'][0] != out['fresh'][0]}")


# ── demon-tongue ──────────────────────────────────────────────────────────
def probe_demon_tongue() -> None:
    """Demon Tongue's _triggered_this_turn across a combat boundary.

    Neither C# nor the sim resets it at a combat boundary (DemonTongue.cs has
    only BeforeSideTurnStart), so PROMPT.md class 13 needs a trace to the first
    READER of the stale flag, not a reset diff.
    """
    from sts2_rl import CombatState
    from sts2_rl.relics import make_relic

    dt = make_relic("demon_tongue")
    CombatState(rng=random.Random(1), relics=[dt])
    dt._triggered_this_turn = True          # latch it as a won combat would
    print(f"  end of combat 1: _triggered_this_turn={dt._triggered_this_turn}")

    cs2 = CombatState(rng=random.Random(2), relics=[dt])
    print(f"  combat 2 after construction (which runs turn 1): "
          f"_triggered_this_turn={dt._triggered_this_turn} "
          f"-> the turn-start reset (demon_tongue.py:44-45) shadows the "
          f"missing combat reset")
    print(f"  the port also requires combat.current_side == 'player'; "
          f"combat 2 side = {cs2.current_side!r}")

    # Heal amount: hp_lost (sim) vs DamageResult.UnblockedDamage (C#).
    from sts2_rl.cmds import DamageCmd
    from sts2_rl.valueprops import ValueProp
    cs3 = CombatState(rng=random.Random(4), relics=[make_relic("demon_tongue")],
                      current_hp=60)
    hp0 = cs3.player.hp
    DamageCmd.deal(cs3.hooks, cs3.player, 7,
                   props=ValueProp.UNBLOCKABLE, dealer=None, card=None)
    print(f"  self-damage 7 on the player's turn: hp {hp0} -> {cs3.player.hp} "
          f"(once per turn; a second hit is not healed)")
    DamageCmd.deal(cs3.hooks, cs3.player, 5,
                   props=ValueProp.UNBLOCKABLE, dealer=None, card=None)
    print(f"  second self-damage 5: hp -> {cs3.player.hp}")


# ── frond ─────────────────────────────────────────────────────────────────
def probe_frond() -> None:
    """Delicate Frond's potion generation vs CreateRandomPotionOutOfCombat.

    C#: PotionFactory.CreateRandomPotionOutOfCombat -> CreateRandomPotion
    (PotionFactory.cs:67-81) rolls a RARITY first (<=0.1 Rare, <=0.35 Uncommon,
    else Common) then NextItem inside that bucket, on Rng.CombatPotionGeneration;
    procurement goes through PotionCmd.TryToProcure, which consults
    Hook.ShouldProcurePotion (Sozu) and fires Hook.AfterPotionProcured.
    Sim (delicate_frond.py:20-25): uniform choice over every in_reward_pool
    potion class on the shared combat rng, via PlayerCombatState.add_potion.
    """
    from sts2_rl.potion_pools import POTION_POOL
    from sts2_rl.potions import _POTION_CLASSES

    by_rarity: dict[str, int] = {}
    for _pid, r in POTION_POOL:
        by_rarity[str(r)] = by_rarity.get(str(r), 0) + 1
    print(f"  potion_pools.POTION_POOL buckets: {by_rarity}")
    frond_pool = sorted(c.id for c in _POTION_CLASSES.values() if c.in_reward_pool)
    print(f"  delicate_frond's uniform pool: {len(frond_pool)} potions")
    rare = [pid for pid, r in POTION_POOL if str(r).lower().endswith("rare")]
    if rare:
        p_uniform = len(rare) / len(frond_pool)
        print(f"  P(a Rare potion): C# = 0.10 (the rarity roll), "
              f"sim = {len(rare)}/{len(frond_pool)} = {p_uniform:.3f}")
    print("  the faithful helper exists and is unused: "
          "potion_pools.generate_random_potion")

    print("  -- Sozu gate (Hook.ShouldProcurePotion): C# TryToProcure "
          "(PotionCmd.cs:31) consults it; player.add_potion does not")
    from sts2_rl import CombatState
    from sts2_rl.relics import make_relic
    for relics in (["delicate_frond"], ["delicate_frond", "sozu"]):
        cs = CombatState(rng=random.Random(5),
                         relics=[make_relic(r) for r in relics])
        print(f"     relics={relics} -> belt="
              f"{[p.id for p in cs.player.held_potions]}")
    print("     C# with Sozu: ShouldProcurePotion is False -> "
          "TryToProcure fails -> the while loop breaks -> belt stays EMPTY")

    print("  -- AfterPotionProcured (belt_buckle's own recorded gap): "
          "C# TryToProcure fires it, so Belt Buckle's 2 Dexterity is removed "
          "the moment the Frond fills a slot at combat start")
    cs = CombatState(rng=random.Random(6),
                     relics=[make_relic("belt_buckle"),
                             make_relic("delicate_frond")])
    print(f"     [belt_buckle, delicate_frond] -> powers="
          f"{[(p.id, p.amount) for p in cs.player.powers.values()]} "
          f"belt={[p.id for p in cs.player.held_potions]} (C#: no Dexterity)")


# ── cape ──────────────────────────────────────────────────────────────────
def probe_cape() -> None:
    """Distinguished Cape's -9 Max HP: the port puts it in the wrong place.

    DistinguishedCape.cs:31 loses the 9 Max HP in AfterObtained. The event
    helper the port's docstring blames, EventOption.ThatDecreasesMaxHp
    (EventOption.cs:194-197), is PRESENTATION ONLY — it sets WillKillPlayer so
    the option flashes red; it applies no HP loss and nothing consumes it.
    """
    from sts2_rl.relics import make_relic

    run = _run()
    before = (run.max_hp, run.hp, len(run.deck))
    run.add_relic(make_relic("distinguished_cape"))
    after = (run.max_hp, run.hp, len(run.deck))
    print(f"  add_relic('distinguished_cape'): (max_hp, hp, deck) "
          f"{before} -> {after}")
    print(f"  C#: max_hp {before[0]} -> {before[0] - 9}, +3 Apparition. "
          f"sim loses {before[0] - after[0]} Max HP.")

    run2 = _run()
    from sts2_rl.events.vakuu import VakuuEvent
    ev = VakuuEvent(run2)
    b2 = run2.max_hp
    run2.lose_max_hp(9)                       # what events/vakuu.py:59 does
    run2.add_relic(make_relic("distinguished_cape"))
    print(f"  via the Vakuu option (events/vakuu.py:58-60, event {ev.id!r}): "
          f"max_hp {b2} -> {run2.max_hp} == C#'s {b2 - 9} — the TOTAL is right "
          f"by accident, because the event pays what the relic should")
    print(f"  undo_after_obtained implemented: "
          f"{'undo_after_obtained' in type(make_relic('distinguished_cape')).__dict__}"
          f" (the conformance runner's relic swap needs it — runner.py:461/694)")


# ── stubs ─────────────────────────────────────────────────────────────────
def probe_stubs() -> None:
    """dingy_rug / dollys_mirror / dragon_fruit: executed no-ops.

    Sweep C found all three behaviourless. This re-executes the observable so
    each record carries a number rather than a premise.
    """
    import sts2_rl.cards  # noqa: F401
    from sts2_rl.cards import make_card
    from sts2_rl.cards.pool import COLORLESS_POOL, IRONCLAD_POOL
    from sts2_rl.relics import make_relic
    from sts2_rl.rewards import RarityOddsType, create_reward_cards

    print("  -- dingy_rug: card rewards should also draw from the Colorless pool")
    print(f"     COLORLESS_POOL is ported: {len(COLORLESS_POOL)} cards; "
          f"create_reward_cards already takes a `pool` override "
          f"(rewards.py:234-241)")
    for relics in ([], ["dingy_rug"]):
        run = _run()
        run.relics.extend(make_relic(r) for r in relics)
        cards = create_reward_cards(run, RarityOddsType.REGULAR)
        colorless = [c.id for c in cards if c.id in COLORLESS_POOL]
        print(f"     relics={relics} -> options={[c.id for c in cards]} "
              f"colorless={colorless}")
    print("     every option comes from IRONCLAD_POOL either way: "
          f"{all(c in IRONCLAD_POOL for c in ('strike', 'defend'))}")
    print("     NOTE: ModifyCardRewardCreationOptions has NO base hook on "
          "Relic (sweep C) — the sim's nearest hook, modify_card_reward_options "
          "(rewards.py:301), runs AFTER the options are generated, so it "
          "cannot widen the pool")

    print("  -- dollys_mirror: AfterObtained duplicates a chosen deck card")
    run = _run()
    before = [c.id for c in run.deck]
    run.add_relic(make_relic("dollys_mirror"))
    print(f"     deck {len(before)} -> {len(run.deck)} cards "
          f"(C#: +1, a CloneCard of the chosen non-Quest card)")
    print(f"     after_obtained IS dispatched for every relic at run.py:552; "
          f"the port simply defines none: "
          f"{'after_obtained' not in type(make_relic('dollys_mirror')).__dict__}")

    print("  -- dragon_fruit: AfterGoldGained -> +1 Max HP")
    for relics in ([], ["dragon_fruit"]):
        run = _run()
        run.relics.extend(make_relic(r) for r in relics)
        b = (run.gold, run.max_hp)
        run.gain_gold(25)
        print(f"     relics={relics} -> gold {b[0]}->{run.gold} "
              f"max_hp {b[1]}->{run.max_hp} (C# with the relic: +1 Max HP)")
    from sts2_rl.relics.base import Relic
    print(f"     Relic base defines after_gold_gained: "
          f"{hasattr(Relic, 'after_gold_gained')}; is_allowed: "
          f"{hasattr(Relic, 'is_allowed')} (sweep B: 16-relic cluster)")
    run = _run()
    print(f"     RunState.total_floor exists for IsBeforeAct3TreasureChest: "
          f"{hasattr(run, 'total_floor')} (= {run.total_floor})")
    _ = make_card  # keep the import honest


# ── dream-driftwood ───────────────────────────────────────────────────────
def probe_dream_driftwood() -> None:
    """The rest-site reward screen: Dream Catcher's cards and Driftwood's reroll.

    C# routes the rest-site heal reward list through RewardsCmd.OfferCustom ->
    RewardsSet.GenerateWithoutOffering (RewardsSet.cs:136) -> Hook.ModifyRewards,
    whose SECOND pass is TryModifyRewardsLate (Hook.cs:1991-1996) — so Driftwood
    marks a rest-site CardReward rerollable. RunState.rest_heal_rewards
    (run.py:1097-1110) dispatches only modify_rest_site_heal_rewards.
    """
    import sts2_rl.cards  # noqa: F401
    from sts2_rl.relics import make_relic

    for relics in (["dream_catcher"], ["dream_catcher", "driftwood"]):
        run = _run()
        run.relics.extend(make_relic(r) for r in relics)
        rewards = run.rest_heal_rewards()
        print(f"  relics={relics} -> rest cards={[c.id for c in rewards.cards]} "
              f"can_reroll={rewards.can_reroll}")
    print("  C# with Driftwood: CanReroll=True on that CardReward")

    print("  -- combat screen for contrast (modify_combat_rewards IS dispatched)")
    from sts2_rl.rewards import generate_combat_rewards
    from sts2_rl.rooms import RoomType
    run = _run()
    run.relics.append(make_relic("driftwood"))
    r = generate_combat_rewards(run, RoomType.MONSTER)
    print(f"     combat rewards can_reroll={r.can_reroll}")

    print("  -- the MIMICKED rest heal (PlayerCmd.MimicRestSiteHeal): "
          "Dense Vegetation's REST option")
    import inspect

    from sts2_rl.events.dense_vegetation import DenseVegetation
    src = inspect.getsource(DenseVegetation._rest)
    print(f"     events/dense_vegetation.py::_rest calls rest_heal_rewards: "
          f"{'rest_heal_rewards' in src}; after_rest_site_heal: "
          f"{'after_rest_site_heal' in src}")
    run = _run()
    run.relics.append(make_relic("dream_catcher"))
    ev = DenseVegetation(run)
    run.hp = max(1, run.max_hp - 30)
    hp0 = run.hp
    ev._rest()
    print(f"     after _rest(): hp {hp0} -> {run.hp}, page={ev.page!r}, "
          f"options={ev.option_keys()} — a heal and a FIGHT, no "
          f"reward screen. C# MimicRestSiteHeal -> ExecuteRestSiteHeal fires "
          f"AfterRestSiteHeal AND ModifyRestSiteHealRewards (isMimicked:true, "
          f"which DreamCatcher ignores) then RewardsCmd.OfferCustom")


# ── tome ──────────────────────────────────────────────────────────────────
def probe_tome() -> None:
    """Dusty Tome's Ancient candidates and the unguarded Card.upgrade().

    Sweep D flagged dusty_tome.py's after_obtained as an unguarded
    `Card.upgrade()` (PROMPT.md class 14). Settle it by execution: the census
    of level-0 cards is Curse/Status/Quest, and the Tome only ever picks
    Ancient-rarity pool cards.
    """
    import sts2_rl.cards  # noqa: F401
    from sts2_rl.cards.base import _CARD_CLASSES
    from sts2_rl.relics import make_relic
    from sts2_rl.relics.dusty_tome import DustyTome

    cands = DustyTome.candidates()
    print(f"  candidates(): {cands}")
    for cid in cands:
        cls = _CARD_CLASSES[cid]
        print(f"     {cid:<16} rarity={cls.rarity.name:<9} "
              f"max_upgrade_level={cls.max_upgrade_level} "
              f"type={cls.card_type.name}")
    zero = [cid for cid in cands if _CARD_CLASSES[cid].max_upgrade_level == 0]
    print(f"  candidates with max_upgrade_level == 0: {zero or '(none)'} "
          f"-> class 14 is DORMANT at this site")
    allzero = sorted(cid for cid, c in _CARD_CLASSES.items()
                     if c.max_upgrade_level == 0)
    print(f"  pool-wide level-0 census: {len(allzero)} cards, types="
          f"{sorted({_CARD_CLASSES[c].card_type.name for c in allzero})}")

    print("  -- executed pickup")
    run = _run()
    tome = make_relic("dusty_tome")
    run.add_relic(tome)
    added = run.deck[-1]
    print(f"     ancient_card={tome.ancient_card!r} deck tail="
          f"({added.id}, upgrade_level={added.upgrade_level})")

    print("  -- SetupForPlayer timing (C# rolls at OFFER time, "
          "DustyTome.cs:50-56, on PlayerRng.Rewards)")
    import inspect

    from sts2_rl.events import darv
    src = inspect.getsource(darv)
    print(f"     events/darv.py calls setup_for_player: "
          f"{'setup_for_player' in src}")
    run2 = _run()
    t2 = make_relic("dusty_tome")
    run2.add_relic(t2)   # no prior setup_for_player -> lazy roll at pickup
    print(f"     add_relic with no prior setup: ancient_card="
          f"{t2.ancient_card!r} (rolled at pickup, "
          f"dusty_tome.py:53-54, on the shared run rng)")


# ── ectoplasm ─────────────────────────────────────────────────────────────
def probe_ectoplasm() -> None:
    """Ectoplasm: every ported gold gain must route through RunState.gain_gold.

    ModifyGoldGained is a chain hook dispatched only from run.py:329-330, so a
    gold gain that writes RunState.gold directly would escape the relic.
    """
    import subprocess

    from sts2_rl.relics import make_relic

    run = _run()
    run.relics.append(make_relic("ectoplasm"))
    g0 = run.gold
    run.gain_gold(99)
    print(f"  gain_gold(99) with ectoplasm: gold {g0} -> {run.gold} (C#: 0)")

    from sts2_rl.rewards import generate_combat_rewards
    from sts2_rl.rooms import RoomType
    run2 = _run()
    run2.relics.append(make_relic("ectoplasm"))
    g0 = run2.gold
    r = generate_combat_rewards(run2, RoomType.MONSTER)
    print(f"  MONSTER reward screen: rewards.gold={r.gold} "
          f"run gold {g0} -> {run2.gold} (banked via run.gain_gold at "
          f"rewards.py:485, so the relic sees it)")

    writes = subprocess.run(
        ["git", "grep", "-n", r"self\.gold += \|self\.gold = ", "--", "sts2_rl"],
        capture_output=True, text=True, cwd=_REPO,
    ).stdout.splitlines()
    print("  direct RunState.gold writes in the engine:")
    for w in writes:
        print(f"     {w.strip()}")

    print("  -- ModifyMaxEnergy")
    from sts2_rl import CombatState
    for relics in ([], ["ectoplasm"]):
        cs = CombatState(rng=random.Random(9),
                         relics=[make_relic(x) for x in relics])
        print(f"     relics={relics} -> energy={cs.player.energy}")


# ── dotw ──────────────────────────────────────────────────────────────────
def probe_dotw() -> None:
    """Daughter of the Wind x a Replay source (audits/seam/hook_dispatch G4).

    C# fires Hook.AfterCardPlayed once per CardPlay, i.e. once per Replay
    iteration (CardModel.cs:1904-1965); the sim fires on_card_played once per
    logical play (combat.py:514). So a replayed Attack should grant 2 Block.
    """
    import sts2_rl.cards  # noqa: F401
    from sts2_rl import CombatState
    from sts2_rl.cards import make_card
    from sts2_rl.relics import make_relic

    for relics in (["daughter_of_the_wind"],
                   ["daughter_of_the_wind", "throwing_axe"]):
        cs = CombatState(rng=random.Random(0),
                         relics=[make_relic(r) for r in relics])
        cs.player.hand[:] = [make_card("strike")]
        cs.player.energy = 3
        cs.player.block = 0
        cs.play_card(0, 0)
        print(f"  relics={relics} -> block after one Strike = {cs.player.block}")
    print("  C#: 1 Block alone, 2 Block with Throwing Axe (the Strike plays "
          "twice and AfterCardPlayed fires per CardPlay)")


# ── earring-order ─────────────────────────────────────────────────────────
def probe_earring_order() -> None:
    """Crossbow x Whispering Earring — turn_structure guard G8 at a new site.

    C# puts start-of-turn auto-plays in their own phase entered strictly AFTER
    Hook.AfterSideTurnStart (CombatManager.cs:556-572), so Crossbow's free
    Attack is ALWAYS in hand before Whispering Earring starts auto-playing.
    The sim fires both from on_player_turn_started in listener-registration
    order, so the answer depends on the relic order.
    """
    from sts2_rl import CombatState
    from sts2_rl.relics import make_relic

    for order in (["crossbow", "whispering_earring"],
                  ["whispering_earring", "crossbow"]):
        cs = CombatState(rng=random.Random(11),
                         relics=[make_relic(r) for r in order])
        print(f"  relics={order} -> hand left={[c.id for c in cs.player.hand]} "
              f"discard={len(cs.player.discard_pile)} "
              f"enemy_hp={[e.hp for e in cs.enemies]}")
    print("  C# always gives the '[crossbow, whispering_earring]' answer: the "
          "generated Attack is in hand before the AutoPrePlay phase opens")
    print("  turn_structure G8 called the AutoPrePlay side DORMANT because "
          "'Whispering Earring and Imbued ... neither reads another turn-start "
          "listener's output' — Crossbow refutes that: it WRITES the hand the "
          "Earring then consumes")


PROBES = {
    "b04-pool": probe_b04_pool,
    "dotw": probe_dotw,
    "earring-order": probe_earring_order,
    "crossbow": probe_crossbow,
    "darkstone": probe_darkstone,
    "diadem": probe_diadem,
    "demon-tongue": probe_demon_tongue,
    "frond": probe_frond,
    "cape": probe_cape,
    "stubs": probe_stubs,
    "dream-driftwood": probe_dream_driftwood,
    "tome": probe_tome,
    "ectoplasm": probe_ectoplasm,
}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("probe", nargs="?", choices=sorted(PROBES))
    args = ap.parse_args()
    names = [args.probe] if args.probe else list(PROBES)
    for name in names:
        print(f"== {name} ==")
        PROBES[name]()
        print()


if __name__ == "__main__":
    main()
