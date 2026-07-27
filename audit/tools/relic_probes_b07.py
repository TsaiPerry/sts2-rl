"""Reproducible execution probes for relic content audit BATCH 7.

Batch 7's 15 units: golden_pearl, gorget, gremlin_horn, hand_drill,
happy_flower, hefty_tablet, horn_cleat, ice_cream, intimidating_helmet,
iron_club, jeweled_mask, jewelry_box, joss_paper, juzu_bracelet, kaleidoscope.

Per the concurrency contract this batch owns its OWN probe module; the shared
`audit/tools/relic_probes.py` is read-only here (re-use it for `turn-order`
and the pool-wide sweeps). Binding rules 5 and 6: never justify `faithful`
with an unreachability claim you have not EXECUTED, and never label a gap LIVE
without proving both sides reachable with ported content.

  py audit/tools/relic_probes_b07.py            # every probe
  py audit/tools/relic_probes_b07.py club-count # one probe

Probes:
  pool            obtainability of batch 7's 15 relics
  club-count      iron_club — CardsVar(4) vs the port's CARDS = 6
  club-replay     iron_club — per-Replay AfterCardPlayed (hook_dispatch G4)
  helmet-autoplay intimidating_helmet — Resources.EnergyValue vs energy SPENT
  helmet-replay   intimidating_helmet — Block per Replay iteration
  flower-carry    happy_flower — TurnsSeen really does carry across combats
  joss-ethereal   joss_paper — causedByEthereal vs card.is_ethereal, and the
                  flush-vetoed turn end that never counts the deferral
  icecream-energy ice_cream — reset on turn 1, conserve from turn 2
  cleat-turn2     horn_cleat — 14 Block on the turn-2 block clear
  gorget-plating  gorget — 4 Plating at combat start, block at turn end
  mask-turn1      jeweled_mask — a draw-pile Power moved to hand, free
  drill-vuln      hand_drill — 2 Vulnerable on a block break, incl. a kill
  horn-death      gremlin_horn — +1 energy and +1 card on an enemy death
  horn-illusion   gremlin_horn — AfterDeath on a prevented death (Fogmog)
  tablet-pool     hefty_tablet — FilterForCombat vs GetUnlockedCards, and the
                  dropped TryModifyCardRewardOptions hook
  pearl-gold      golden_pearl — 150 gold through modify_gold_gained
  box-apotheosis  jewelry_box — Apotheosis appended to the deck
  juzu-map        juzu_bracelet — Monster stays in the "?" room-type set
  kaleido-neow    kaleidoscope — IsAllowedAtNeow and the no-op AfterObtained
"""
from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

BATCH7 = [
    "golden_pearl", "gorget", "gremlin_horn", "hand_drill", "happy_flower",
    "hefty_tablet", "horn_cleat", "ice_cream", "intimidating_helmet",
    "iron_club", "jeweled_mask", "jewelry_box", "joss_paper",
    "juzu_bracelet", "kaleidoscope",
]


# ── pool ──────────────────────────────────────────────────────────────────
def probe_pool() -> None:
    """Where each batch-7 relic can come from (binding rule 6, "obtainable")."""
    import subprocess

    from sts2_rl.relic_pools import IRONCLAD_RELIC_POOL, SHARED_RELIC_POOL
    from sts2_rl.relics import ALL_RELICS

    bag = {rid.removeprefix("RELIC.").lower(): rarity
           for rid, rarity in SHARED_RELIC_POOL + IRONCLAD_RELIC_POOL}
    print(f"grab-bag pool: {len(bag)} relics")
    for rid in BATCH7:
        registered = rid in ALL_RELICS
        srcs = subprocess.run(
            ["git", "grep", "-l", f'"{rid}"', "--", "sts2_rl"],
            capture_output=True, text=True, cwd=_REPO,
        ).stdout.split()
        srcs = [s for s in srcs if not s.endswith(f"relics/{rid}.py")]
        print(f"  {rid:<21} registered={registered} bag={bag.get(rid, '-'):<9} "
              f"granted_by={srcs or ['(none)']}")


# ── club-count ────────────────────────────────────────────────────────────
def probe_club_count() -> None:
    """iron_club: IronClub.cs's CanonicalVars is `new CardsVar(4)`; the port
    pins CARDS = 6 and its own docstring claims "CardsVar(6)"."""
    from sts2_rl import CombatState
    from sts2_rl.cards import make_card
    from sts2_rl.relics import make_relic

    club = make_relic("iron_club")
    print(f"  sim IronClub.CARDS = {club.CARDS}   "
          f"(IronClub.cs:36 CanonicalVars = new CardsVar(4))")
    cs = CombatState(rng=random.Random(0), relics=[club])
    for n in range(1, 9):
        before = len(cs.player.hand)
        # Feed a card straight to the hook: the counter is the whole mechanism.
        cs.hooks.on_card_played(make_card("strike"))
        drew = len(cs.player.hand) - before
        print(f"    card {n}: cards_played={club.cards_played} drew={drew}"
              f"    (C# draws on 4 and 8)")


# ── club-replay ───────────────────────────────────────────────────────────
def probe_club_replay() -> None:
    """iron_club: C# fires Hook.AfterCardPlayed INSIDE the play-count loop
    (CardModel.cs:1904-1961), so a Throwing-Axe-doubled card advances
    CardsPlayed by 2. The sim fires on_card_played once per play."""
    from sts2_rl import CombatState
    from sts2_rl.relics import make_relic

    club = make_relic("iron_club")
    axe = make_relic("throwing_axe")
    cs = CombatState(rng=random.Random(0), relics=[club, axe])
    cs.player.hand.clear()
    from sts2_rl.cards import make_card
    cs.player.hand.append(make_card("strike"))
    cs.player.energy = 5
    cs.play_card(0)
    print(f"  Iron Club + Throwing Axe, one Strike played (twice): "
          f"cards_played={club.cards_played}   (C#: 2)")


# ── helmet-autoplay ───────────────────────────────────────────────────────
def probe_helmet_autoplay() -> None:
    """intimidating_helmet: C# gates on `cardPlay.Resources.EnergyValue >= 2`,
    and on the AUTO-PLAY path CardCmd.cs:123-128 sets EnergySpent = 0 but
    EnergyValue = the card's cost. The sim's on_energy_spent gets 0."""
    from sts2_rl import CombatState
    from sts2_rl.cards import make_card
    from sts2_rl.relics import make_relic

    # dark_embrace is a 2-cost Power card that grants no Block of its own, so
    # the player's Block is the relic's contribution and nothing else.
    for label, relics in (("no relic", []), ("helmet", ["intimidating_helmet"])):
        cs = CombatState(rng=random.Random(0),
                         relics=[make_relic(r) for r in relics])
        cs.player.hand.clear()
        cs.player.block = 0
        card = make_card("dark_embrace")
        cs.player.hand.append(card)
        cs.player.energy = 5
        cs.play_card(0)
        print(f"  {label:<10} MANUAL play of a cost-{card.energy_cost} card "
              f"-> block = {cs.player.block}   (C#: 0 / 4)")

        cs2 = CombatState(rng=random.Random(0),
                          relics=[make_relic(r) for r in relics])
        cs2.player.hand.clear()
        cs2.player.block = 0
        card2 = make_card("dark_embrace")
        cs2.auto_play_card(card2)
        print(f"  {label:<10} AUTO play   of a cost-{card2.energy_cost} card "
              f"-> block = {cs2.player.block}   "
              f"(C#: 0 / 4 — EnergyValue is the COST, not the spend)")


# ── helmet-replay ─────────────────────────────────────────────────────────
def probe_helmet_replay() -> None:
    """intimidating_helmet: Hook.BeforeCardPlayed fires once per Replay
    iteration (CardModel.cs:1919-1929), so a doubled 2-cost card grants the
    Block twice in C#."""
    from sts2_rl import CombatState
    from sts2_rl.cards import make_card
    from sts2_rl.relics import make_relic

    for label, relics in (
        ("helmet alone", ["intimidating_helmet"]),
        ("helmet + throwing_axe", ["intimidating_helmet", "throwing_axe"]),
    ):
        cs = CombatState(rng=random.Random(0),
                         relics=[make_relic(r) for r in relics])
        cs.player.hand.clear()
        cs.player.block = 0
        cs.player.hand.append(make_card("dark_embrace"))
        cs.player.energy = 5
        cs.play_card(0)
        powers = {p.id: p.amount for p in cs.player.powers.values()}
        print(f"  {label:<24} block = {cs.player.block} powers={powers}   "
              f"(C#: block 4 / 8)")


# ── flower-carry ──────────────────────────────────────────────────────────
def probe_flower_carry() -> None:
    """happy_flower: the port's docstring says "the game's counter persists
    between combats; the sim's resets each combat". Relic instances live on
    RunState.relics and are re-attached to every CombatState, so it does NOT
    reset — which is what makes the port faithful to C#'s [SavedProperty]
    TurnsSeen. The docstring is the thing that is wrong."""
    from sts2_rl import CombatState
    from sts2_rl.relics import make_relic

    flower = make_relic("happy_flower")
    print(f"  fresh instance: turns_seen={flower.turns_seen}")
    for n, seed in enumerate((0, 1, 2), start=1):
        # One player turn per combat: CombatState.__init__ runs start_turn.
        cs = CombatState(rng=random.Random(seed), relics=[flower])
        print(f"  combat {n}, turn 1 only: turns_seen={flower.turns_seen} "
              f"energy={cs.player.energy}   "
              f"(C#: 1, 2, 0 — and 4 energy in combat 3)")
    print("  C#: TurnsSeen is a [SavedProperty] and AfterCombatEnd only "
          "resets base.Status, so it carries there too -> MATCH. The port's "
          "docstring claim ('the sim's resets each combat') is FALSE.")


# ── joss-ethereal ─────────────────────────────────────────────────────────
def probe_joss_ethereal() -> None:
    """joss_paper, three findings.

    (1) C#'s AfterCardExhausted(card, causedByEthereal) takes the flag from
        the EXHAUST CALL (CombatManager.cs:1238-1241 passes true only for the
        turn-end ethereal pass); the port infers it from `card.is_ethereal`,
        so a mid-turn exhaust of an Ethereal card is deferred instead of
        counted.
    (2) The deferral is flushed from `on_hand_emptied`, which player.py:197
        fires only inside `discard_hand` — and combat.py:661 skips
        discard_hand entirely when a listener vetoes the flush. C#'s
        AfterSideTurnEnd is unconditional.
    (3) C# clears EtherealCount in AfterCombatEnd (JossPaper.cs); the port
        clears it nowhere, so anything stranded by (2) crosses into combat 2.
    """
    from sts2_rl import CombatState
    from sts2_rl.cards import make_card
    from sts2_rl.cmds import ExhaustCmd
    from sts2_rl.relics import make_relic

    eth = [cid for cid in ("dazed", "ascenders_bane", "writhe", "clumsy")
           if _is_ethereal(cid)]
    print(f"  ported Ethereal cards available for the probe: {eth}")

    # (1) mid-turn exhaust of an Ethereal card
    joss = make_relic("joss_paper")
    cs = CombatState(rng=random.Random(0), relics=[joss])
    cs.player.hand.clear()
    hand_before = 0
    for _ in range(5):
        c = make_card(eth[0])
        cs.player.hand.append(c)
        ExhaustCmd.exhaust(cs.hooks, cs.player, c)
    print(f"  (1) 5 mid-turn exhausts of {eth[0]}: cards_exhausted="
          f"{joss.cards_exhausted} _ethereal_pending={joss._ethereal_pending} "
          f"hand={len(cs.player.hand) - hand_before}   "
          f"(C#: cards_exhausted 0 after the draw, +1 card drawn)")

    # non-ethereal control
    joss2 = make_relic("joss_paper")
    cs2 = CombatState(rng=random.Random(0), relics=[joss2])
    cs2.player.hand.clear()
    for _ in range(5):
        c = make_card("defend")
        cs2.player.hand.append(c)
        ExhaustCmd.exhaust(cs2.hooks, cs2.player, c)
    print(f"      control (5 Defends): cards_exhausted={joss2.cards_exhausted} "
          f"hand={len(cs2.player.hand)}   (C#: identical)")

    # (2) flush vetoed by runic_pyramid -> the deferral is never flushed
    joss3 = make_relic("joss_paper")
    pyramid = make_relic("runic_pyramid")
    cs3 = CombatState(rng=random.Random(0), relics=[joss3, pyramid])
    cs3.player.hand.clear()
    for _ in range(5):
        cs3.player.hand.append(make_card(eth[0]))
    cs3.end_turn()
    print(f"  (2) joss_paper + runic_pyramid, 5 Ethereal in hand at turn end: "
          f"cards_exhausted={joss3.cards_exhausted} "
          f"_ethereal_pending={joss3._ethereal_pending}   "
          f"(C#: AfterSideTurnEnd is unconditional -> 0 pending, 1 drawn)")

    joss4 = make_relic("joss_paper")
    cs4 = CombatState(rng=random.Random(0), relics=[joss4])
    cs4.player.hand.clear()
    for _ in range(5):
        cs4.player.hand.append(make_card(eth[0]))
    cs4.end_turn()
    print(f"      control (no Runic Pyramid): cards_exhausted="
          f"{joss4.cards_exhausted} _ethereal_pending={joss4._ethereal_pending}")

    # (3) the stranded count crosses the combat boundary
    cs5 = CombatState(rng=random.Random(1), relics=[joss3, pyramid])
    print(f"  (3) the SAME joss_paper instance entering combat 2: "
          f"_ethereal_pending={joss3._ethereal_pending} "
          f"cards_exhausted={joss3.cards_exhausted}   "
          f"(C# AfterCombatEnd: EtherealCount = 0)")
    assert cs5 is not None


def _is_ethereal(card_id: str) -> bool:
    from sts2_rl.cards import make_card
    try:
        return bool(make_card(card_id).is_ethereal)
    except Exception:
        return False


# ── icecream-energy ───────────────────────────────────────────────────────
def probe_icecream_energy() -> None:
    """ice_cream: ShouldPlayerResetEnergy is true on TurnNumber == 1 and false
    afterwards, so leftover energy is kept from turn 2 on."""
    from sts2_rl import CombatState
    from sts2_rl.relics import make_relic

    for label, relics in (("no relic", []), ("ice_cream", ["ice_cream"])):
        cs = CombatState(rng=random.Random(0),
                         relics=[make_relic(r) for r in relics])
        seen = [cs.player.energy]
        for _ in range(3):
            cs.end_turn()
            seen.append(cs.player.energy)
        print(f"  {label:<10} energy at the start of turns 1-4: {seen}   "
              f"(C# with Ice Cream: 3, 6, 9, 12)")


# ── cleat-turn2 ───────────────────────────────────────────────────────────
def probe_cleat_turn2() -> None:
    """horn_cleat: AfterBlockCleared with TurnNumber == 2 -> BlockVar(14,
    Unpowered). The sim's on_block_cleared is turn_structure step 14, the
    UNCONDITIONAL AfterBlockCleared loop that record's guard G1 describes."""
    from sts2_rl import CombatState
    from sts2_rl.relics import make_relic

    cs = CombatState(rng=random.Random(0), relics=[make_relic("horn_cleat")])
    for turn in range(1, 5):
        print(f"  turn {turn} block after the clear = {cs.player.block}   "
              f"(C#: 0, 14, 0, 0)")
        cs.player.block = 0  # strip so the next turn's grant is unambiguous
        cs.end_turn()


# ── gorget-plating ────────────────────────────────────────────────────────
def probe_gorget_plating() -> None:
    """gorget: AfterRoomEntered(CombatRoom) -> 4 PlatingPower on the owner.
    PlatingPower.BeforeSideTurnStart explicitly returns early for a player
    owner (PlatingPower.cs:46-49), so the player gets NO combat-start block —
    matching the sim's enemy-only on_combat_start block."""
    from sts2_rl import CombatState
    from sts2_rl.relics import make_relic

    cs = CombatState(rng=random.Random(0), relics=[make_relic("gorget")])
    plating = {p.id: p.amount for p in cs.player.powers.values()}
    print(f"  combat start: powers={plating} block={cs.player.block}   "
          f"(C#: Plating 4, block 0 — PlatingPower.cs:46-49 skips a player "
          f"owner on the combat-start grant)")
    cs.hooks.on_player_turn_end(cs.player)
    print(f"  at turn-1 end (BeforeSideTurnEndEarly slot): block="
          f"{cs.player.block} "
          f"powers={ {p.id: p.amount for p in cs.player.powers.values()} }   "
          f"(C#: +4 block)")
    cs.end_turn()
    print(f"  start of turn 2: block={cs.player.block} "
          f"powers={ {p.id: p.amount for p in cs.player.powers.values()} }   "
          f"(C#: block cleared, Plating decayed to 3)")


# ── mask-turn1 ────────────────────────────────────────────────────────────
def probe_mask_turn1() -> None:
    """jeweled_mask: BeforeHandDraw on TurnNumber <= 1 pulls a random Power
    from the draw pile into the hand and frees it. The sim's
    on_player_turn_start sits in exactly the BeforeHandDraw slot (executed:
    `py audit/tools/relic_probes.py turn-order`)."""
    from sts2_rl import CombatState
    from sts2_rl.cards import CardType, make_card
    from sts2_rl.relics import make_relic

    def deck():
        return ([make_card("strike") for _ in range(8)]
                + [make_card("inflame"), make_card("demon_form")])

    for label, relics in (("no relic", []), ("jeweled_mask", ["jeweled_mask"])):
        cs = CombatState(rng=random.Random(0), starting_deck=deck(),
                         relics=[make_relic(r) for r in relics])
        powers_in_hand = [(c.id, c.energy_cost) for c in cs.player.hand
                          if c.card_type == CardType.POWER]
        print(f"  {label:<13} turn 1: hand={len(cs.player.hand)} "
              f"Powers in hand (id, cost)={powers_in_hand}   "
              f"(C# with the mask: 1 Power at cost 0, hand 6)")
        cs.end_turn()
        powers2 = [(c.id, c.energy_cost) for c in cs.player.hand
                   if c.card_type == CardType.POWER]
        print(f"  {label:<13} turn 2: Powers in hand={powers2}   "
              f"(C#: the mask does not fire again)")


# ── drill-vuln ────────────────────────────────────────────────────────────
def probe_drill_vuln() -> None:
    """hand_drill: AfterDamageGiven with result.WasBlockBroken applies
    PowerVar<VulnerablePower>(2) to a non-player target. The port listens on
    on_block_broken instead — damage_pipeline guard N5 already verdicts that
    slot difference (deliberate-divergence) and names Hand Drill."""
    from sts2_rl import CombatState
    from sts2_rl.cmds import DamageCmd
    from sts2_rl.monsters import Encounter
    from sts2_rl.monsters.overgrowth import FuzzyWurmCrawler
    from sts2_rl.relics import make_relic

    def fight():
        return CombatState(
            rng=random.Random(0),
            encounter=Encounter("b07_drill", [FuzzyWurmCrawler]),
            relics=[make_relic("hand_drill")],
        )

    for label, enemy_block, dmg in (
        ("exact break", 6, 6),
        ("overkill break", 6, 9),
        ("partial (no break)", 10, 6),
        ("no block at all", 0, 6),
    ):
        cs = fight()
        e = cs.enemies[0]
        e.block = enemy_block
        DamageCmd.deal(cs.hooks, e, dmg, dealer=cs.player)
        print(f"  {label:<20} enemy powers="
              f"{ {p.id: p.amount for p in e.powers.values()} }"
              f"   (C#: Vulnerable 2 on the two break cases only)")

    # killing blow that also breaks block
    cs = fight()
    e = cs.enemies[0]
    e.block = 3
    DamageCmd.deal(cs.hooks, e, 3 + e.hp, dealer=cs.player)
    print(f"  killing blow + break  enemy dead={e.is_dead} "
          f"powers={ {p.id: p.amount for p in e.powers.values()} }   "
          f"(C#: AfterDamageGiven is NOT killing-blow-guarded -> Vulnerable "
          f"applied to the corpse too)")

    # the enemy, not the player, is the one that gets it
    cs = fight()
    cs.player.block = 6
    DamageCmd.deal(cs.hooks, cs.player, 6, dealer=cs.enemies[0])
    print(f"  enemy breaks PLAYER's block: player powers="
          f"{ {p.id: p.amount for p in cs.player.powers.values()} }   "
          f"(C#: nothing — !target.IsPlayer and the dealer check)")


# ── horn-death ────────────────────────────────────────────────────────────
def probe_horn_death() -> None:
    """gremlin_horn: AfterDeath on an opposite-side target -> +1 energy and
    draw 1."""
    from sts2_rl import CombatState
    from sts2_rl.cmds import CreatureCmd
    from sts2_rl.monsters import Encounter
    from sts2_rl.monsters.overgrowth import FuzzyWurmCrawler
    from sts2_rl.relics import make_relic

    cs = CombatState(
        rng=random.Random(0),
        encounter=Encounter("b07_horn", [FuzzyWurmCrawler, FuzzyWurmCrawler]),
        relics=[make_relic("gremlin_horn")],
    )
    e0, e1 = cs.enemies
    before = (cs.player.energy, len(cs.player.hand))
    CreatureCmd.kill(cs.hooks, e0)
    print(f"  enemy death: energy {before[0]} -> {cs.player.energy}, "
          f"hand {before[1]} -> {len(cs.player.hand)}   (C#: +1 / +1)")
    # player-side death must NOT trigger it
    cs.hooks.on_death(cs.player)
    print(f"  player-side on_death: energy={cs.player.energy} "
          f"hand={len(cs.player.hand)}   (C#: unchanged, side check)")
    assert e1 is not None


# ── horn-illusion ─────────────────────────────────────────────────────────
def probe_horn_illusion() -> None:
    """gremlin_horn: C# fires Hook.AfterDeath on a PREVENTED death too
    (CreatureCmd.cs:566, `wasRemovalPrevented: true`), and the three ported
    revive powers do not prevent death in C# at all -- IllusionPower,
    SteamEruptionPower and AdaptablePower override
    ShouldCreatureBeRemovedFromCombatAfterDeath, NOT ShouldDie (a grep for
    `ShouldDie` over src/Core/Models finds only FairyInABottle, LizardTail and
    two Mock powers). The sim's ports return should_die = False, so
    cmds.py:105's on_death never runs."""
    from sts2_rl import CombatState
    from sts2_rl.cmds import DamageCmd
    from sts2_rl.monsters import Encounter
    from sts2_rl.monsters.overgrowth import EyeWithTeeth
    from sts2_rl.relics import make_relic

    # Eye With Teeth is summoned by Fogmog, a ported act-1 Overgrowth NORMAL
    # encounter (fogmog.py:95; Fogmog.cs:66 does the same), so no exotic
    # content is needed to reach an Illusion enemy.
    cs = CombatState(
        rng=random.Random(0),
        encounter=Encounter("b07_illusion", [EyeWithTeeth]),
        relics=[make_relic("gremlin_horn")],
    )
    e = cs.enemies[0]
    powers = sorted(e.powers)
    before = (cs.player.energy, len(cs.player.hand))
    DamageCmd.deal(cs.hooks, e, e.hp + 50, dealer=cs.player)
    print(f"  Eye With Teeth (summoned by the ported Fogmog) powers={powers}")
    print(f"  lethal hit -> enemy hp={e.hp} is_dead={e.is_dead} "
          f"is_gone={e.is_gone}; energy {before[0]} -> {cs.player.energy}, "
          f"hand {before[1]} -> {len(cs.player.hand)}   "
          f"(C#: hp 0, dead, +1 energy, +1 card)")
    print(f"  C#: IllusionPower.cs:77-90 AfterDeath (wasRemovalPrevented "
          f"False) -- the creature REALLY dies, stays in combat and revives on "
          f"its next turn, so Gremlin Horn gets +1 energy and +1 card.")


# ── tablet-pool ───────────────────────────────────────────────────────────
def probe_tablet_pool() -> None:
    """hefty_tablet, two findings.

    (1) C# draws its 3 Rares from `options.GetPossibleCards(player)` =
        CardPool.GetUnlockedCards() + the Rare predicate
        (CardCreationOptions.cs:168-178) — NOT FilterForCombat. The port uses
        cards.pool.pool_card_ids(), which IS FilterForCombat, so every Rare
        with CanBeGeneratedInCombat = false is missing from the candidate list.
    (2) CardFactory.CreateForReward runs Hook.TryModifyCardRewardOptions
        unless CardCreationFlags.NoModifyHooks is set (CardFactory.cs:104-107),
        and HeftyTablet sets only NoUpgradeRoll. The port never calls the
        sim's `modify_card_reward_options`.
    """
    from sts2_rl.cards import CardRarity
    from sts2_rl.cards.base import _CARD_CLASSES
    from sts2_rl.cards.pool import pool_card_ids, reward_pool_card_ids

    combat_rares = [c for c in pool_card_ids()
                    if _CARD_CLASSES[c].rarity == CardRarity.RARE]
    reward_rares = [c for c in reward_pool_card_ids()
                    if _CARD_CLASSES[c].rarity == CardRarity.RARE]
    missing = [c for c in reward_rares if c not in combat_rares]
    print(f"  (1) Rare candidates the PORT builds (FilterForCombat): "
          f"{len(combat_rares)}")
    print(f"      Rare candidates C# builds (GetUnlockedCards):      "
          f"{len(reward_rares)}")
    print(f"      missing from the port entirely: {missing}")
    for cid in missing:
        cls = _CARD_CLASSES[cid]
        print(f"        {cid}: rarity={cls.rarity.name} "
              f"can_be_generated_in_combat={cls.can_be_generated_in_combat}")

    # (2) is the reward-options hook reachable at all, and does the relic use it?
    import inspect

    from sts2_rl.relics import make_relic
    src = inspect.getsource(type(make_relic("hefty_tablet")))
    print(f"  (2) 'modify_card_reward_options' in hefty_tablet.py source: "
          f"{'modify_card_reward_options' in src}")
    import subprocess
    hits = subprocess.run(
        ["git", "grep", "-ln", "def modify_card_reward_options", "--",
         "sts2_rl/relics"],
        capture_output=True, text=True, cwd=_REPO).stdout.split()
    print(f"      ported relics that DO implement it: {hits}")


# ── pearl-gold ────────────────────────────────────────────────────────────
def probe_pearl_gold() -> None:
    """golden_pearl: AfterObtained -> PlayerCmd.GainGold(GoldVar(150))."""
    from sts2_rl.run import RunState

    run = RunState(rng=random.Random(0))
    before = run.gold
    run.add_relic("golden_pearl")
    print(f"  gold {before} -> {run.gold}   (C#: +150)")


# ── box-apotheosis ────────────────────────────────────────────────────────
def probe_box_apotheosis() -> None:
    """jewelry_box: AfterObtained -> CreateCard<Apotheosis>() into the deck."""
    from sts2_rl.run import RunState

    run = RunState(rng=random.Random(0))
    n = len(run.deck)
    run.add_relic("jewelry_box")
    print(f"  deck {n} -> {len(run.deck)}; tail = "
          f"{[c.id for c in run.deck[-2:]]}   (C#: Apotheosis appended)")


# ── juzu-map ──────────────────────────────────────────────────────────────
def probe_juzu_map() -> None:
    """juzu_bracelet: ModifyUnknownMapPointRoomTypes removes RoomType.Monster.
    The port is behaviourless, and run.py:1046-1049 dispatches the hook over
    every relic — a LIVE dispatch site (Sweep C)."""
    from sts2_rl.relics import make_relic
    from sts2_rl.run import RunState

    for label, relics in (("no relic", []), ("juzu_bracelet", ["juzu_bracelet"]),
                          ("golden_compass (sibling)", ["golden_compass"])):
        run = RunState(rng=random.Random(0))
        for rid in relics:
            r = make_relic(rid)
            if rid == "golden_compass":
                r.golden_path_act = run.act_index
            run.relics.append(r)
        allowed = run._unknown_allowed_room_types([])
        print(f"  {label:<26} allowed '?' room types = "
              f"{sorted(t.name for t in allowed)}")
    print("  C# with Juzu Bracelet: MONSTER removed. The sibling relic proves "
          "the pipeline works.")


# ── kaleido-neow ──────────────────────────────────────────────────────────
def probe_kaleido_neow() -> None:
    """kaleidoscope: IsAllowedAtNeow requires every character's card pool to
    be unlocked; the sim has one character, so False is the faithful value.
    AfterObtained offers 2 CardRewards built from OTHER characters' pools —
    out of the Ironclad-only sim's scope entirely."""
    from sts2_rl.cards.pool import COLORLESS_POOL, IRONCLAD_POOL
    from sts2_rl.relics import make_relic
    from sts2_rl.run import RunState

    k = make_relic("kaleidoscope")
    print(f"  is_allowed_at_neow={k.is_allowed_at_neow}   "
          f"(C#: base && UnlockState.CharacterCardPools.Count() == "
          f"AllCharacters.Count())")
    print(f"  character card pools the sim has: 1 (Ironclad, "
          f"{len(IRONCLAD_POOL)} cards) + Colorless ({len(COLORLESS_POOL)}) "
          f"+ Curse; ModelDb.AllCharacters = 5 in the game")
    run = RunState(rng=random.Random(0))
    n = len(run.deck)
    run.add_relic("kaleidoscope")
    print(f"  add_relic('kaleidoscope'): deck {n} -> {len(run.deck)}   "
          f"(C#: 2 card-reward screens from other characters' pools)")


PROBES = {
    "pool": probe_pool,
    "club-count": probe_club_count,
    "club-replay": probe_club_replay,
    "helmet-autoplay": probe_helmet_autoplay,
    "helmet-replay": probe_helmet_replay,
    "flower-carry": probe_flower_carry,
    "joss-ethereal": probe_joss_ethereal,
    "icecream-energy": probe_icecream_energy,
    "cleat-turn2": probe_cleat_turn2,
    "gorget-plating": probe_gorget_plating,
    "mask-turn1": probe_mask_turn1,
    "drill-vuln": probe_drill_vuln,
    "horn-death": probe_horn_death,
    "horn-illusion": probe_horn_illusion,
    "tablet-pool": probe_tablet_pool,
    "pearl-gold": probe_pearl_gold,
    "box-apotheosis": probe_box_apotheosis,
    "juzu-map": probe_juzu_map,
    "kaleido-neow": probe_kaleido_neow,
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
