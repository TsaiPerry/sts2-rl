"""Reproducible execution probes for relic audit BATCH 17.

Batch 17's units: vajra, vambrace, velvet_choker, venerable_tea_set,
very_hot_cocoa, vexing_puzzlebox, war_hammer, war_paint, whetstone,
whispering_earring, white_beast_statue, white_star, wing_charm, winged_boots,
wongo_customer_appreciation_badge.

Companion to `audit/tools/relic_probes.py` (the shared module, read-only to
this batch per the concurrency contract). Every reachability claim in
`audit/records/relic/<unit>.json` for these fifteen units is produced here, so a later
auditor re-derives the number instead of trusting a throwaway script — binding
rules 5 and 6.

  py audit/tools/relic_probes_b17.py              # every probe
  py audit/tools/relic_probes_b17.py teaset       # one probe

Probes:
  pool           obtainability of all 15 batch-17 relics (rule 6)
  teaset         venerable_tea_set -- frozen constructor state: the relic can
                 never fire, and what it would do if _pending were True
  vambrace       vambrace -- (a) _used carried into combat 2, (b) the seam's
                 G1 unpowered-block gate, (c) the seam's G2 multi-gain latch
  choker         velvet_choker -- the per-turn reset really runs before any
                 reader, and the counter carried across the combat boundary
  cocoa          very_hot_cocoa -- turn-1 energy, and the extra-turn question
  puzzlebox      vexing_puzzlebox -- the free card, its cost, and the hand cap
  earring-order  vexing_puzzlebox x whispering_earring registration order
                 (turn_structure G8 / crossbow G1 at a second pair of sites)
  earring-auto   whispering_earring -- its plays are MANUAL, not auto-plays
  warhammer      war_hammer -- upgrades EVERY upgradable deck card, not 4
  upgradestubs   war_paint / whetstone -- after_obtained is dispatched and the
                 two stubs upgrade nothing
  rewardstubs    white_beast_statue / white_star / wing_charm -- the three
                 reward hooks are dispatched and the stubs do nothing
  isallowed      the 17-relic IsAllowed cluster at this batch's three sites
                 (white_beast_statue, white_star, winged_boots)
  boots          winged_boots -- free travel, the charge, and children vs row
  wongo          wongo_customer_appreciation_badge -- executed unreachability
  vajra          vajra -- the Strength lands at BeforeCombatStart, not at
                 AfterRoomEntered
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

BATCH17 = [
    "vajra", "vambrace", "velvet_choker", "venerable_tea_set",
    "very_hot_cocoa", "vexing_puzzlebox", "war_hammer", "war_paint",
    "whetstone", "whispering_earring", "white_beast_statue", "white_star",
    "wing_charm", "winged_boots", "wongo_customer_appreciation_badge",
]


# ── pool ──────────────────────────────────────────────────────────────────
def probe_pool() -> None:
    """Where each batch-17 relic can come from (binding rule 6)."""
    from sts2_rl.relic_pools import IRONCLAD_RELIC_POOL, SHARED_RELIC_POOL
    from sts2_rl.relics import ALL_RELICS

    bag = {rid.removeprefix("RELIC.").lower(): rarity
           for rid, rarity in SHARED_RELIC_POOL + IRONCLAD_RELIC_POOL}
    print(f"grab-bag pool: {len(bag)} relics "
          f"({len(SHARED_RELIC_POOL)} shared + {len(IRONCLAD_RELIC_POOL)} Ironclad)")
    for rid in BATCH17:
        registered = rid in ALL_RELICS
        srcs = subprocess.run(
            ["git", "grep", "-l", f'"{rid}"', "--", "sts2_rl"],
            capture_output=True, text=True, cwd=_REPO,
        ).stdout.split()
        srcs = [s for s in srcs if not s.endswith(f"relics/{rid}.py")]
        print(f"  {rid:<36} registered={registered} bag={bag.get(rid, '-'):<9} "
              f"granted_by={srcs or ['(none)']}")


# ── teaset ────────────────────────────────────────────────────────────────
def probe_teaset() -> None:
    """venerable_tea_set: FROZEN CONSTRUCTOR STATE (sweep A, rewritten).

    VenerableTeaSet.cs:41-49 latches GainEnergyInNextCombat = true in
    AfterRoomEntered on a RestSiteRoom, and AfterEnergyReset (lines 51-60)
    spends it for EnergyVar(2). The port's whole trigger is
    `self._pending = rested`, a constructor parameter, and make_relic
    (relics/base.py:74) constructs every relic with NO arguments -- so the
    relic can never fire in any run. Its knock-off sibling
    fake_venerable_tea_set is the same defect (batch 5, LIVE).
    """
    import inspect

    from sts2_rl import CombatState
    from sts2_rl.relics import make_relic
    from sts2_rl.relics.venerable_tea_set import VenerableTeaSet

    print("  make_relic signature: "
          f"{inspect.signature(make_relic)}  -> `_RELIC_CLASSES[relic_id]()`")
    r = make_relic("venerable_tea_set")
    print(f"  make_relic('venerable_tea_set')._pending = {r._pending}")
    print(f"  has after_room_entered override: "
          f"{'after_room_entered' in VenerableTeaSet.__dict__}")

    for pending, label in ((False, "as make_relic builds it"),
                           (True, "_pending forced True")):
        relic = VenerableTeaSet()
        relic._pending = pending
        cs = CombatState(rng=random.Random(0), relics=[relic])
        print(f"  {label:<28} turn-1 energy={cs.player.energy}   (C# after a "
              f"rest site: 3 base + 2 = 5)")

    # Every path that grants this relic goes through make_relic / add_relic.
    grants = subprocess.run(
        ["git", "grep", "-n", "venerable_tea_set", "--", "sts2_rl"],
        capture_output=True, text=True, cwd=_REPO).stdout.strip().splitlines()
    print("  grant sites in sts2_rl/:")
    for line in grants:
        print(f"    {line}")


# ── vambrace ──────────────────────────────────────────────────────────────
def probe_vambrace() -> None:
    """vambrace: three separate divergences, all executed.

    (a) sweep A CONFIRMED: `_used` is never reset, and C# assigns at BOTH
        BeforeCombatStart (Vambrace.cs:47-53) and AfterCombatEnd (:107-113).
    (b) audit/records/seam/creature_card_cmds.json G1: BlockCmd.apply gates the whole
        block-modifier dispatch on is_powered_attack, and Vambrace's C# gate is
        the looser IsCardOrMonsterMove().
    (c) audit/records/seam/creature_card_cmds.json G2: C# latches TriggeringCard in
        AfterModifyingBlockAmount but only sets BlockGainedThisCombat in
        AfterCardPlayed, so EVERY block gain of one card play is doubled.
    """
    from sts2_rl import CombatState
    from sts2_rl.cards import make_card
    from sts2_rl.relics import make_relic

    v = make_relic("vambrace")

    # (a) carried instance
    cs = CombatState(rng=random.Random(0), relics=[v])
    d = make_card("defend")
    cs.player.energy = 10
    cs.player.hand.append(d)
    cs.play_card(len(cs.player.hand) - 1)
    print(f"  combat 1: Defend block={cs.player.block}  _used={v._used}"
          f"   (C#: 10)")
    cs2 = CombatState(rng=random.Random(1), relics=[v])
    print(f"  combat 2 entered with the SAME instance: _used={v._used}"
          f"   (C# BeforeCombatStart: False)")
    d2 = make_card("defend")
    cs2.player.energy = 10
    cs2.player.hand.append(d2)
    cs2.play_card(len(cs2.player.hand) - 1)
    print(f"  combat 2: Defend block={cs2.player.block}   (C#: 10)")

    # (c) two block gains inside one card play, same instance, fresh combat
    v2 = make_relic("vambrace")
    cs3 = CombatState(rng=random.Random(2), relics=[v2])
    from sts2_rl.cmds import BlockCmd
    card = make_card("defend")
    BlockCmd.apply(cs3.hooks, cs3.player, 5, card=card)
    first = cs3.player.block
    BlockCmd.apply(cs3.hooks, cs3.player, 5, card=card)
    print(f"  two BlockCmd.apply calls carrying the SAME card: "
          f"{first} then {cs3.player.block - first}   (C#: 10 then 10)")

    # (b) the seam's G1: BlockCmd.apply skips the whole modifier dispatch for
    # an UNPOWERED card gain, and Vambrace's C# gate is IsCardOrMonsterMove()
    # only -- Entrench (a ported Ironclad Event card) is MOVE|UNPOWERED.
    from sts2_rl.valueprops import ValueProp
    for props, label in ((ValueProp.MOVE, "powered card (Defend)"),
                         (ValueProp.MOVE | ValueProp.UNPOWERED,
                          "UNPOWERED card gain (Entrench's shape)")):
        v3 = make_relic("vambrace")
        cs4 = CombatState(rng=random.Random(3), relics=[v3])
        BlockCmd.apply(cs4.hooks, cs4.player, 5, card=make_card("defend"),
                       props=props)
        print(f"  {label:<38} block={cs4.player.block}   (C#: 10 both)")


# ── choker ────────────────────────────────────────────────────────────────
def probe_choker() -> None:
    """velvet_choker: does the per-turn reset run before any reader?

    C# resets _cardsPlayedThisTurn in THREE places -- BeforeSideTurnStart
    (VelvetChoker.cs:91-100, player side only), AfterRoomEntered
    (:77-84) and AfterCombatEnd (:86-89). The port keeps only the turn-start
    half, so bug class 13 needs the trace to the first READER of the stale
    counter: ShouldPlay, consulted only during the play phase.
    """
    from sts2_rl import CombatState
    from sts2_rl.cards import make_card
    from sts2_rl.relics import make_relic

    c = make_relic("velvet_choker")
    cs = CombatState(rng=random.Random(0), relics=[c])
    print(f"  combat 1 turn 1: ENERGY_PER_TURN={cs.player.ENERGY_PER_TURN} "
          f"energy={cs.player.energy}  (C#: base 3 + 1 = 4)")
    cs.player.energy = 40
    for i in range(8):
        card = make_card("strike")
        cs.player.hand.append(card)
        ok = cs.play_card(len(cs.player.hand) - 1, 0)
        if not ok:
            print(f"  play #{i + 1} refused; counter="
                  f"{c.cards_played_this_turn}   (C# ShouldPlay blocks the 7th)")
            break
    # Carry the stale counter into a second combat WITHOUT ending the turn:
    # combat.py:209 runs start_turn immediately after on_combat_start, so
    # on_player_turn_start clears it before the play phase opens.
    cs2 = CombatState(rng=random.Random(1), relics=[c])
    print(f"  combat 2 turn 1 counter after entering: "
          f"{c.cards_played_this_turn}   (C# AfterRoomEntered: 0)")
    cs2.player.energy = 40
    card = make_card("strike")
    cs2.player.hand.append(card)
    print(f"  combat 2 first play accepted: "
          f"{cs2.play_card(len(cs2.player.hand) - 1, 0)}")

    # Would a reader see the stale value BEFORE the turn-start clear? Register
    # a spy relic whose on_combat_start asks the hook the same question.
    from sts2_rl.relics.base import Relic, RelicRarity
    seen = []

    class Spy(Relic):
        id, name, rarity = "_spy_choker", "Spy", RelicRarity.COMMON

        def on_combat_start(self):
            seen.append(self.hooks.should_play_card(make_card("strike")))

    c2 = make_relic("velvet_choker")
    c2.cards_played_this_turn = 6   # as if combat 1 ended mid-turn at the cap
    CombatState(rng=random.Random(3), relics=[c2, Spy()])
    print(f"  should_play_card asked from on_combat_start with a stale 6: "
          f"{seen}   (a False here would be an observable stale read)")


# ── cocoa ─────────────────────────────────────────────────────────────────
def probe_cocoa() -> None:
    """very_hot_cocoa: EnergyVar(4) on turn 1 only, and the extra-turn case.

    VeryHotCocoa.cs:20-28 is AfterSideTurnStart with
    `PlayerCombatState.TurnNumber <= 1`; the port is on_player_turn_started
    with `self.turn <= 1` (very_hot_cocoa.py:21-24). self.turn is
    CombatState.turn, not PlayerCombatState.TurnNumber -- the probe checks the
    two agree across a turn boundary and across an extra turn.
    """
    from sts2_rl import CombatState
    from sts2_rl.relics import make_relic

    cs = CombatState(rng=random.Random(0), relics=[make_relic("very_hot_cocoa")])
    print(f"  turn 1: combat.turn={cs.turn} energy={cs.player.energy} "
          f"   (C#: 3 + 4 = 7)")
    cs.end_turn()
    print(f"  turn 2: combat.turn={cs.turn} energy={cs.player.energy}"
          f"   (C#: 3, TurnNumber 2 > 1)")

    # An extra turn: does combat.turn advance, i.e. can the relic re-fire?
    from sts2_rl.relics.base import Relic, RelicRarity

    class OneExtraTurn(Relic):
        id, name, rarity = "_extra", "Extra", RelicRarity.COMMON

        def __init__(self):
            super().__init__()
            self.done = False

        def should_take_extra_turn(self, player):
            if self.done:
                return False
            self.done = True
            return True

    cs2 = CombatState(rng=random.Random(1),
                      relics=[make_relic("very_hot_cocoa"), OneExtraTurn()])
    print(f"  extra-turn run, turn 1 energy={cs2.player.energy}")
    cs2.end_turn()
    print(f"  after an EXTRA turn: combat.turn={cs2.turn} "
          f"energy={cs2.player.energy}")


# ── puzzlebox ─────────────────────────────────────────────────────────────
def probe_puzzlebox() -> None:
    """vexing_puzzlebox: the free turn-1 card.

    VexingPuzzlebox.cs:15-25 -- GetDistinctForCombat(pool.GetUnlockedCards, 1,
    Rng.CombatCardGeneration).First(), SetToFreeThisTurn(),
    AddGeneratedCardToCombat(card, PileType.Hand). Checks the card arrives, its
    cost is 0 for this turn only, the turn-2 non-repeat, and the hand cap.
    """
    from sts2_rl import CombatState
    from sts2_rl.cards import make_card
    from sts2_rl.relics import make_relic

    cs = CombatState(rng=random.Random(0), relics=[make_relic("vexing_puzzlebox")])
    print(f"  turn 1 hand ({len(cs.player.hand)}): "
          f"{[c.id for c in cs.player.hand]}")
    extra = cs.player.hand[-1]
    print(f"  added card={extra.id} energy_cost={extra.energy_cost} "
          f"hooked cost={cs.hooks.modify_card_energy_cost(extra, extra.energy_cost)}")
    cs.end_turn()
    print(f"  turn 2 hand ({len(cs.player.hand)}): "
          f"{[c.id for c in cs.player.hand]}  (no second card: turn != 1)")

    # Hand cap: C#'s AddGeneratedCardToCombat / the sim's add_to_hand both
    # overflow to the discard pile at MAX_HAND_SIZE.
    from sts2_rl.relics.base import Relic, RelicRarity

    class FillHand(Relic):
        id, name, rarity = "_fill", "Fill", RelicRarity.COMMON

        def modify_hand_draw(self, player, count):
            return count

        def on_player_turn_start(self, player):
            for _ in range(10):
                player.hand.append(make_card("strike"))

    cs2 = CombatState(rng=random.Random(1),
                      relics=[FillHand(), make_relic("vexing_puzzlebox")])
    print(f"  hand-full case: hand={len(cs2.player.hand)} "
          f"discard={len(cs2.player.discard_pile)} "
          f"MAX_HAND_SIZE={cs2.player.MAX_HAND_SIZE}")


# ── earring-order ─────────────────────────────────────────────────────────
def probe_earring_order() -> None:
    """vexing_puzzlebox x whispering_earring: registration order decides.

    C# runs Puzzlebox at Hook.AfterPlayerTurnStart (turn_structure step 22,
    immediately after the hand draw) and the Earring at
    Hook.AfterAutoPrePlayPhaseEnteredLate (step 26), the THIRD of three full
    passes (Hook.cs:928-955) entered strictly after steps 22-24. So the free
    0-cost card is ALWAYS in hand before the Earring's loop starts. The sim
    fires both from on_player_turn_started in one pass, so the answer depends
    on the order of run.relics. Same mechanism as audit/records/seam/turn_structure
    guard G8 and audit/records/relic/crossbow.json G1.
    """
    from sts2_rl import CombatState
    from sts2_rl.relics import make_relic
    from sts2_rl.relics.base import Relic, RelicRarity

    for order in (["vexing_puzzlebox", "whispering_earring"],
                  ["whispering_earring", "vexing_puzzlebox"]):
        played: list[str] = []

        class Spy(Relic):
            id, name, rarity = "_spy_order", "SpyO", RelicRarity.COMMON

            def on_card_played(self, card):
                played.append(card.id)

        # The spy registers LAST so it never displaces the pair's own order.
        cs = CombatState(rng=random.Random(4),
                         relics=[make_relic(r) for r in order] + [Spy()])
        gen = [c for c in cs.player.all_cards if c.energy_cost == 0]
        print(f"  relics={order}")
        print(f"    cards the Earring played: {played}")
        print(f"    leftover hand={[c.id for c in cs.player.hand]}  "
              f"free (0-cost) cards still around={[c.id for c in gen]}")
    print("  C# always plays the Puzzlebox card too: it is in hand at cost 0 "
          "from step 22, and the Earring's loop only opens at step 26.")


# ── earring-auto ──────────────────────────────────────────────────────────
def probe_earring_auto() -> None:
    """whispering_earring: the port plays cards MANUALLY, not as auto-plays.

    WhisperingEarring.cs:78 is `CardCmd.AutoPlay(choiceContext, card, target,
    AutoPlayType.Default, skipXCapture: true)` after an explicit
    `card.SpendResources()`. CardCmd.AutoPlay (CardCmd.cs:51-128) ends in
    `OnPlayWrapper(..., isAutoPlay: true, ...)`. The port calls
    CombatState.play_card (whispering_earring.py:43), the MANUAL path, so the
    resulting plays are not flagged as auto-plays anywhere.

    Observable via relic/brilliant_scarf, whose C# AfterCardPlayed returns
    early on cardPlay.IsAutoPlay (BrilliantScarf.cs:84-87).
    """
    from sts2_rl import CombatState
    from sts2_rl.relics import make_relic

    cs = CombatState(rng=random.Random(5),
                     relics=[make_relic("whispering_earring"),
                             make_relic("brilliant_scarf")])
    scarf = [r for r in cs.relics if r.id == "brilliant_scarf"][0]
    print(f"  after the Earring's turn-1 loop: brilliant_scarf "
          f"cards_played_this_turn={scarf.cards_played_this_turn}"
          f"   (C#: 0 -- every one of those plays is IsAutoPlay)")

    # The same routing means Enthralled's manual-only block stops the Earring,
    # where C#'s AutoPlayType.Default play is explicitly allowed through.
    from sts2_rl.cards import make_card
    from sts2_rl.relics.base import Relic, RelicRarity

    class PutEnthralled(Relic):
        id, name, rarity = "_enth", "Enth", RelicRarity.COMMON

        def on_player_turn_start(self, player):
            player.hand.append(make_card("enthralled"))

    cs2 = CombatState(rng=random.Random(5),
                      relics=[PutEnthralled(), make_relic("whispering_earring")])
    print(f"  with Enthralled in hand: enemy HP={cs2.enemy.hp} "
          f"hand={[c.id for c in cs2.player.hand]} energy={cs2.player.energy}")
    cs3 = CombatState(rng=random.Random(5), relics=[PutEnthralled()])
    print(f"  control (no Earring):    enemy HP={cs3.enemy.hp} "
          f"hand={[c.id for c in cs3.player.hand]} energy={cs3.player.energy}")
    print("  ^ selection agrees with C#: CardModel.CanPlay() asks "
          "Hook.ShouldPlay with AutoPlayType.None (CardModel.cs:1755), which "
          "is the sim's manual arm, and Enthralled.cs:21-38 lets Enthralled "
          "itself through on both sides.")

    # No card selector is installed, so a card the Earring auto-plays that
    # opens a selection screen picks RANDOMLY where C# pushes VakuuCardSelector
    # (VakuuCardSelector.cs:17-20: options.Take(maxSelect), row-major order).
    class FixedHand(Relic):
        """Registers BEFORE the Earring, so the hand is fixed by the time the
        Earring's loop opens: Armaments first, then four distinct upgradables."""
        id, name, rarity = "_fixed", "Fixed", RelicRarity.COMMON

        def on_player_turn_started(self, player):
            player.hand[:] = [make_card(i) for i in
                              ("armaments", "bash", "anger", "twin_strike",
                               "iron_wave")]

    for seed in (0, 1, 2, 3, 4):
        cs4 = CombatState(rng=random.Random(seed),
                          relics=[FixedHand(),
                                  make_relic("whispering_earring")])
        ups = [c.id for c in cs4.player.all_cards if c.upgrade_level]
        print(f"  seed={seed} card_selector={cs4.card_selector} "
              f"Armaments upgraded: {ups}   (C# VakuuCardSelector: always the "
              f"FIRST option in the screen's order)")


# ── warhammer ─────────────────────────────────────────────────────────────
def probe_warhammer() -> None:
    """war_hammer: C# upgrades FOUR random upgradable deck cards, not all.

    WarHammer.cs:22-36 -- AfterCombatVictory, RoomType.Elite only, then
    `Deck.Cards.Where(c => c.IsUpgradable).StableShuffle(Rng.Niche)
    .Take(CardsVar(4))`. war_hammer.py:15-22 upgrades EVERY upgradable card in
    the deck and consumes no Niche draw.
    """
    from sts2_rl.rooms import RoomType
    from sts2_rl.run import RunState

    run = RunState(rng=random.Random(0))
    run.add_relic("war_hammer")
    print(f"  starting deck ({len(run.deck)}): "
          f"{[(c.id, c.upgrade_level) for c in run.deck]}")
    upgradable = [c for c in run.deck if c.is_upgradable]
    print(f"  upgradable: {len(upgradable)}")
    for relic in run.relics:
        relic.after_combat_end(run, RoomType.ELITE)
    ups = [(c.id, c.upgrade_level) for c in run.deck if c.upgrade_level]
    print(f"  after one Elite victory: {len(ups)} card(s) upgraded "
          f"(C#: exactly 4)")
    print(f"    {ups}")

    # A MONSTER victory must do nothing on both sides.
    run2 = RunState(rng=random.Random(0))
    run2.add_relic("war_hammer")
    for relic in run2.relics:
        relic.after_combat_end(run2, RoomType.MONSTER)
    print(f"  after a MONSTER victory: "
          f"{sum(1 for c in run2.deck if c.upgrade_level)} upgraded (C#: 0)")

    # Is after_combat_end dispatched on defeat too? (C# is AfterCombatVictory.)
    sites = subprocess.run(
        ["git", "grep", "-n", "after_combat_end", "--", "sts2_rl"],
        capture_output=True, text=True, cwd=_REPO).stdout.strip().splitlines()
    print("  after_combat_end dispatch sites:")
    for line in sites:
        if "relics/" not in line:
            print(f"    {line}")


# ── upgradestubs ──────────────────────────────────────────────────────────
def probe_upgradestubs() -> None:
    """war_paint / whetstone: AfterObtained is dispatched; the stubs no-op.

    WarPaint.cs:22-31 upgrades CardsVar(2) random upgradable SKILLS,
    Whetstone.cs:22-31 the same for ATTACKS, both via
    `StableShuffle(Rng.Niche).Take(2)`. Both sim ports are behaviourless
    (war_paint.py, whetstone.py), and run.py:552 calls after_obtained on every
    granted relic -- sweep C's premise check, executed here.
    """
    from sts2_rl.run import RunState

    for rid in ("war_paint", "whetstone", "neows_talisman"):
        run = RunState(rng=random.Random(0))
        before = [(c.id, c.upgrade_level) for c in run.deck]
        run.add_relic(rid)
        after = [(c.id, c.upgrade_level) for c in run.deck]
        changed = [(b, a) for b, a in zip(before, after) if b != a]
        print(f"  add_relic({rid!r}): {len(changed)} deck card(s) changed "
              f"{changed}")
    print("  neows_talisman is the control: a ported relic that DOES upgrade "
          "deck cards from after_obtained (neows_talisman.py:29-33), proving "
          "the run.py:552 dispatch is live.")


# ── rewardstubs ───────────────────────────────────────────────────────────
def probe_rewardstubs() -> None:
    """white_beast_statue / white_star / wing_charm: three live reward hooks.

    - WhiteBeastStatue.ShouldForcePotionReward -> rewards.py:449
    - WhiteStar.TryModifyRewards            -> rewards.py:500
    - WingCharm.TryModifyCardRewardOptionsLate -> rewards.py:301
    """
    from sts2_rl.rewards import (
        ROOM_RARITY_ODDS,
        create_reward_cards,
        generate_combat_rewards,
    )
    from sts2_rl.rooms import RoomType
    from sts2_rl.run import RunState

    # white_beast_statue: potion forced on every combat room.
    for relics in ([], ["white_beast_statue"]):
        got = 0
        for seed in range(20):
            run = RunState(rng=random.Random(seed))
            for rid in relics:
                run.add_relic(rid)
            rw = generate_combat_rewards(run, RoomType.MONSTER)
            got += rw.potion is not None
        print(f"  white_beast_statue relics={relics or ['(none)']}: "
              f"{got}/20 MONSTER screens carry a potion   (C# with it: 20/20)")

    # white_star: an extra 3-card Boss-tier reward on Elite screens.
    for relics in ([], ["white_star"], ["black_star"]):
        run = RunState(rng=random.Random(3))
        for rid in relics:
            run.add_relic(rid)
        rw = generate_combat_rewards(run, RoomType.ELITE)
        print(f"  white_star relics={relics or ['(none)']}: "
              f"cards={len(rw.cards)} special_cards={len(rw.special_cards)} "
              f"relics={[r.id for r in rw.relics]}")
    print("  black_star is the control: the SAME TryModifyRewards hook, at the "
          "same Elite gate, IS implemented (black_star.py:15-23).")

    # wing_charm: one Swift-enchanted option per card reward.
    from sts2_rl.enchantments import SwiftEnchantment
    for relics in ([], ["wing_charm"], ["glitter"]):
        run = RunState(rng=random.Random(3))
        for rid in relics:
            run.add_relic(rid)
        cards = create_reward_cards(run, ROOM_RARITY_ODDS[RoomType.MONSTER])
        ench = [(c.id, c.enchantment.id if c.enchantment else None)
                for c in cards]
        print(f"  wing_charm relics={relics or ['(none)']}: {ench}")
    print(f"  SwiftEnchantment ported: {SwiftEnchantment.id!r}; "
          f"can_enchant(strike)="
          f"{SwiftEnchantment.can_enchant(__import__('sts2_rl.cards', fromlist=['make_card']).make_card('strike'))}")
    print("  glitter is the control: the SAME "
          "TryModifyCardRewardOptionsLate hook IS implemented (glitter.py:16).")


# ── isallowed ─────────────────────────────────────────────────────────────
def probe_isallowed() -> None:
    """The IsAllowed pool gate at this batch's three sites.

    white_beast_statue / white_star: IsBeforeAct3TreasureChest(runState) ==
    `TotalFloor < 41` in single-player (RelicModel.cs:452-456).
    winged_boots: `runState.Players.Count == 1` -- always true here.
    RelicModel.IsAllowedAtNeow DEFAULTS to IsAllowed(player.RunState)
    (RelicModel.cs:443-446), which the sim models as an independent flag.
    """
    from sts2_rl.relics import make_relic
    from sts2_rl.relics.base import Relic
    from sts2_rl.run import RunState

    print(f"  Relic base has 'is_allowed': {hasattr(Relic, 'is_allowed')}")
    print(f"  Relic base has 'is_allowed_at_neow': "
          f"{hasattr(Relic, 'is_allowed_at_neow')} "
          f"(value {Relic.is_allowed_at_neow})")
    for rid in ("white_beast_statue", "white_star", "winged_boots"):
        r = make_relic(rid)
        print(f"  {rid:<20} is_allowed attr={hasattr(r, 'is_allowed')} "
              f"is_allowed_at_neow={r.is_allowed_at_neow}")

    run = RunState(rng=random.Random(11))
    run.total_floor = 60
    bag = [r for r in run.relic_grab_bag]
    hits = [rid for rid in ("white_beast_statue", "white_star")
            if any(getattr(x, "id", x) == rid for x in bag)]
    print(f"  at total_floor=60 the grab bag still contains: {hits} "
          f"(C# IsAllowed: neither)")
    from sts2_rl.relics.base import RelicRarity
    pulled = []
    while True:
        r = run.pull_relic_from_front(rarity=RelicRarity.RARE)
        if r is None or r.id in ("white_beast_statue", "white_star"):
            if r is not None:
                pulled.append(r.id)
            break
        pulled.append(r.id)
    print(f"  Rare pulls at total_floor=60 until one of the two appears: "
          f"{len(pulled)} pull(s), last = {pulled[-1] if pulled else None}"
          f"   (C# IsAllowed: never offerable past floor 41)")


# ── boots ─────────────────────────────────────────────────────────────────
def probe_boots() -> None:
    """winged_boots: free travel, the charge, and children-vs-row.

    C# MapTravel.GetTravelablePointsFrom (MapTravel.cs:14-21) REPLACES the
    children with `Map.GetPointsInRow(row + 1)` while any model allows free
    travel; run.py:912-919 UNIONS the two. The union differs only if some child
    lives outside row+1 -- executed here over generated maps.
    WingedBoots.AfterRoomEntered (WingedBoots.cs:56-84) consumes the charge; the
    sim hand-rolls it as run.py:947-950's on_free_travel_used.
    """
    from sts2_rl.relics import make_relic
    from sts2_rl.run import RunState

    off_row = 0
    total = 0
    for seed in range(8):
        run = RunState(rng=random.Random(seed))
        run.start_act()
        for row in range(run.map.map_length):
            for p in run.map.points_in_row(row):
                for ch in p.children:
                    total += 1
                    if ch.row != p.row + 1:
                        off_row += 1
    print(f"  8 generated maps: {total} parent->child links, {off_row} whose "
          f"child is NOT in row+1  (0 => the sim's union == C#'s replacement)")

    run = RunState(rng=random.Random(0))
    boots = make_relic("winged_boots")
    run.add_relic(boots)
    run.start_act()
    print(f"  boots: is_used_up={boots.is_used_up} "
          f"should_allow_free_travel={boots.should_allow_free_travel()}")
    print(f"  travelable from row 0: {len(run.travelable_points())} points; "
          f"children={len(run.current_point.children)}; "
          f"row1={len(run.map.points_in_row(run.current_point.row + 1))}")

    # Consume all three charges by always travelling to a non-child.
    used = 0
    for _ in range(12):
        cur = run.current_point
        options = run.travelable_points()
        non_child = [p for p in options if p not in cur.children]
        target = non_child[0] if non_child else (
            list(cur.children)[0] if cur.children else None)
        if target is None:
            break
        was_nonchild = target not in cur.children
        run.enter_point(target)
        used += was_nonchild
        if not cur.children:
            break
    print(f"  travelled to {used} non-child point(s); times_used="
          f"{boots.times_used} is_used_up={boots.is_used_up} "
          f"free_travel={boots.should_allow_free_travel()}")


# ── wongo ─────────────────────────────────────────────────────────────────
def probe_wongo() -> None:
    """wongo_customer_appreciation_badge: the unreachability claim, EXECUTED.

    The port is Rarity-only and its docstring claims the relic is unreachable
    within one sim run. WelcomeToWongos.CheckObtainWongoBadge
    (WelcomeToWongos.cs:111-131) grants it when
    `SaveManager.Progress.WongoPoints % 2000 + pointsEarned >= 2000`.
    """
    from sts2_rl.events.welcome_to_wongos import _POINTS
    from sts2_rl.relic_pools import IRONCLAD_RELIC_POOL, SHARED_RELIC_POOL
    from sts2_rl.relics import make_relic

    rid = "wongo_customer_appreciation_badge"
    bag = {x.removeprefix("RELIC.").lower() for x, _ in
           SHARED_RELIC_POOL + IRONCLAD_RELIC_POOL}
    print(f"  in the transcribed grab bag: {rid in bag}")
    print(f"  sim per-run Wongo points available: {_POINTS} "
          f"= {sum(_POINTS.values())} max; badge threshold 2000")
    grants = subprocess.run(
        ["git", "grep", "-n", rid, "--", "sts2_rl"],
        capture_output=True, text=True, cwd=_REPO).stdout.strip().splitlines()
    print(f"  references in sts2_rl/ outside its own module:")
    for line in grants:
        if f"relics/{rid}.py" not in line:
            print(f"    {line}")
    r = make_relic(rid)
    print(f"  constructible by id: {r!r} rarity={r.rarity} "
          f"is_tradable={r.is_tradable} merchant_cost={r.merchant_cost}")
    # Every hook the base class offers, to show the port drops nothing.
    own = [k for k in type(r).__dict__ if not k.startswith("__")]
    print(f"  port's own members: {sorted(own)}")


# ── vajra ─────────────────────────────────────────────────────────────────
def probe_vajra() -> None:
    """vajra: the Strength lands at BeforeCombatStart, not AfterRoomEntered.

    Vajra.cs:22-29 applies StrengthPower(1) in AfterRoomEntered on a
    CombatRoom. For a CombatRoom the game fires Hook.AfterRoomEntered right
    after SetUpCombat and BEFORE StartCombatInternal
    (CombatRoom.cs:224-229 -> CombatManager.cs:380-403), so the Strength is on
    the player before every enemy's first RollMove and before
    Hook.BeforeCombatStart. vajra.py:14-17 applies it from on_combat_start,
    which IS Hook.BeforeCombatStart (turn_structure step 3).
    """
    from sts2_rl import CombatState
    from sts2_rl.relics import make_relic
    from sts2_rl.relics.base import Relic, RelicRarity

    cs = CombatState(rng=random.Random(0), relics=[make_relic("vajra")])
    st = cs.player.powers.get("strength")
    print(f"  turn 1 Strength={st.amount if st else 0}  (C#: 1)")

    # Does anything observe the player between the two positions? In the sim
    # every enemy has already telegraphed its opening intent by the time
    # on_combat_start runs (turn_structure step 2, guard G9), so a monster whose
    # move choice read player Strength would see 0 where C# sees 1.
    seen = []

    class Spy(Relic):
        id, name, rarity = "_spy_vajra", "SpyV", RelicRarity.COMMON

        def on_combat_start(self):
            st = self.player.powers.get("strength")
            seen.append(("on_combat_start", st.amount if st else 0))

    for order in ("spy first", "vajra first"):
        seen.clear()
        relics = ([Spy(), make_relic("vajra")] if order == "spy first"
                  else [make_relic("vajra"), Spy()])
        CombatState(rng=random.Random(0), relics=relics)
        print(f"  {order:<12} spy read {seen}  (C#: 1 either way -- Vajra's "
              f"hook already ran in the previous phase)")

    # Which ported monsters read the player's Strength when choosing a move?
    hits = subprocess.run(
        ["git", "grep", "-ln", "strength", "--", "sts2_rl/monsters"],
        capture_output=True, text=True, cwd=_REPO).stdout.split()
    print(f"  ported monster modules mentioning 'strength': {hits}")


PROBES = {
    "pool": probe_pool,
    "teaset": probe_teaset,
    "vambrace": probe_vambrace,
    "choker": probe_choker,
    "cocoa": probe_cocoa,
    "puzzlebox": probe_puzzlebox,
    "earring-order": probe_earring_order,
    "earring-auto": probe_earring_auto,
    "warhammer": probe_warhammer,
    "upgradestubs": probe_upgradestubs,
    "rewardstubs": probe_rewardstubs,
    "isallowed": probe_isallowed,
    "boots": probe_boots,
    "wongo": probe_wongo,
    "vajra": probe_vajra,
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
