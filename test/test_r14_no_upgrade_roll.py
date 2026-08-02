"""R14 R11 — NoUpgradeRoll at the remaining non-combat card-creation sites.

`CardCreationOptions.ForNonCombatWith*` factories all OR `NoUpgradeRoll`
(CardCreationOptions.cs:139/152/162), which makes `CardFactory.cs:98-102`
skip `RollForUpgrade` **and its `rng.NextFloat()` draw**
(CardFactory.cs:290). A creation of `count` cards through one of those
factories therefore spends `count` `PlayerRng.Rewards` draws, never
`2 * count` (the sim's un-fixed shape: one `NextItem` pick + one
`NextFloat` upgrade-roll draw per card).

Round 13 (F-R13d / seam/creature_card_cmds guard26) fixed exactly one site
(the_future_of_potions). Round 14 lane R3 carried two more (Brain Leech's
Rip, Trial's Nondescript Guilty) while fixing those events' reward screens.
This file pins the remaining sites this lane (R11) carries the flag to:

  - brain_leech.py `_share_knowledge` (BrainLeech.cs:66)
  - room_full_of_cheese.py `_gorge` (RoomFullOfCheese.cs:40-41)
  - endless_conveyor.py `_fried_eel` (EndlessConveyor.cs:181-183)
  - infested_automaton.py `_study` / `_touch_core` (InfestedAutomaton.cs:30-31/41-46)
  - relics/glass_eye.py `after_obtained`'s five screens (GlassEye.cs:29) —
    this one is a CORRECTED reading, not a new carry: the module's own
    docstring previously claimed "neither NoUpgradeRoll nor NoModifyHooks is
    set", which missed that `ForNonCombatWithUniformOdds` itself always ORs
    `NoUpgradeRoll` (CardCreationOptions.cs:160-163) on top of the
    `NoRarityModification` the call site adds explicitly.

Sites intentionally NOT touched, because their C# uses the RAW
`CardCreationOptions` constructor (or `ForRoom`), which does NOT set the
flag, so they correctly still take the roll: lost_coffer.py, lead_paperweight.py,
orrery.py, relics/lasting_candy.py, relics/dream_catcher.py.
"""
from __future__ import annotations

import random

from sts2_rl.run import RunState

SEED = "89U21BV1TZ"


def _run(seed: str = SEED) -> RunState:
    run = RunState(rng=random.Random(0), string_seed=seed)
    run.start_run()
    run.card_selector = lambda purpose, cands, count: list(cands)[:count]
    return run


def _draws(run: RunState, fn) -> int:
    before = run.player_rng.rewards.counter
    fn()
    return run.player_rng.rewards.counter - before


def test_brain_leech_share_knowledge_takes_no_upgrade_roll():
    """BrainLeech.cs:66 — 5 candidates, 1 pick: `ForNonCombatWithDefaultOdds`
    means 5 Rewards draws (the escalating rarity roll's NextFloat plus the
    NextItem pick, per candidate slot), never 10."""
    from sts2_rl.events.brain_leech import BrainLeech

    run = _run()
    ev = BrainLeech(run)
    delta = _draws(run, ev._share_knowledge)
    # 5 candidate slots: 1 rarity NextFloat + 1 NextItem pick each = 10 draws
    # total under REGULAR odds; NoUpgradeRoll removes nothing from the rarity
    # roll (that isn't gated by the flag) but DOES remove the upgrade-roll
    # NextFloat that would otherwise follow every accepted card. Assert the
    # upgrade draw is absent by comparing against the WITH-upgrade-roll shape.
    assert delta > 0
    # Re-derive the with-flag vs without-flag shapes directly against
    # create_reward_cards so this test does not hardcode RarityOddsType
    # internals that could change independently of this gap.
    from sts2_rl.rewards import CardCreationFlags, RarityOddsType, create_reward_cards
    run2 = _run()
    before = run2.player_rng.rewards.counter
    create_reward_cards(run2, RarityOddsType.REGULAR, count=5, mutate_pity=False,
                        extra_flags=CardCreationFlags.NO_UPGRADE_ROLL)
    with_flag = run2.player_rng.rewards.counter - before
    run3 = _run()
    before = run3.player_rng.rewards.counter
    create_reward_cards(run3, RarityOddsType.REGULAR, count=5, mutate_pity=False)
    without_flag = run3.player_rng.rewards.counter - before
    assert with_flag < without_flag
    assert delta == with_flag


def test_room_full_of_cheese_gorge_takes_no_upgrade_roll():
    """RoomFullOfCheese.cs:40-41 — 8 Common candidates, UNIFORM odds (no
    rarity roll at all): NoUpgradeRoll leaves exactly 1 NextItem draw per
    card, 8 total, not 16."""
    from sts2_rl.events.room_full_of_cheese import RoomFullOfCheese

    run = _run()
    ev = RoomFullOfCheese(run)
    delta = _draws(run, ev._gorge)
    assert delta == 8


def test_endless_conveyor_fried_eel_takes_no_upgrade_roll():
    """EndlessConveyor.cs:181-183 — 1 Colorless card, REGULAR odds:
    NoUpgradeRoll means 1 draw (rarity NextFloat consumed picking a matching
    rarity, or the NextItem pick — either way, no separate upgrade-roll
    draw), not 2."""
    from sts2_rl.events.endless_conveyor import EndlessConveyor
    from sts2_rl.rewards import CardCreationFlags, RarityOddsType, create_reward_cards
    from sts2_rl.cards.pool import COLORLESS_POOL

    run = _run()
    ev = EndlessConveyor(run)
    delta = _draws(run, ev._fried_eel)

    run2 = _run()
    before = run2.player_rng.rewards.counter
    create_reward_cards(run2, RarityOddsType.REGULAR, count=1, mutate_pity=False,
                        pool=list(COLORLESS_POOL))
    without_flag = run2.player_rng.rewards.counter - before
    assert delta < without_flag


def test_infested_automaton_study_takes_no_upgrade_roll():
    """InfestedAutomaton.cs:30-31 — 1 Power card: NoUpgradeRoll removes the
    upgrade-roll draw."""
    from sts2_rl.events.infested_automaton import InfestedAutomaton
    from sts2_rl.rewards import RarityOddsType, create_reward_cards
    from sts2_rl.cards.pool import reward_pool_card_ids
    from sts2_rl.cards.base import _CARD_CLASSES
    from sts2_rl.cards import CardType

    run = _run()
    ev = InfestedAutomaton(run)
    delta = _draws(run, ev._study)

    run2 = _run()
    powers = [cid for cid in reward_pool_card_ids(run2.card_pool)
              if _CARD_CLASSES[cid].card_type == CardType.POWER]
    before = run2.player_rng.rewards.counter
    create_reward_cards(run2, RarityOddsType.REGULAR, count=1, mutate_pity=False,
                        pool=powers)
    without_flag = run2.player_rng.rewards.counter - before
    assert delta < without_flag


def test_glass_eye_screens_take_no_upgrade_roll():
    """GlassEye.cs:29 — `ForNonCombatWithUniformOdds` itself ORs
    NoUpgradeRoll (CardCreationOptions.cs:160-163); the module's earlier
    docstring said neither flag was set, which was wrong (only NoModifyHooks
    is genuinely absent). Compare the relic's actual draw cost against the
    same pool/count/odds run WITHOUT the flag: the flagged run must draw
    strictly fewer PlayerRng.Rewards items — one per accepted card instead of
    two (NextItem pick + upgrade-roll NextFloat)."""
    from sts2_rl.cards import CardRarity
    from sts2_rl.cards.base import _CARD_CLASSES
    from sts2_rl.cards.pool import pool_card_ids, reward_pool_card_ids
    from sts2_rl.relics.glass_eye import GlassEye
    from sts2_rl.rewards import CardCreationFlags, CardRewardGroup, RarityOddsType
    from sts2_rl.rooms import RoomType

    run = _run()
    relic = GlassEye()
    before = run.player_rng.rewards.counter
    relic.after_obtained(run)
    flagged_delta = run.player_rng.rewards.counter - before

    run2 = _run()
    pool = (reward_pool_card_ids(run2.card_pool) if run2.rng_set is not None
            else pool_card_ids(pool=run2.card_pool))
    before2 = run2.player_rng.rewards.counter
    for name in relic.SCREEN_RARITIES:
        rarity = CardRarity[name.upper()]
        matching = tuple(cid for cid in pool if _CARD_CLASSES[cid].rarity == rarity)
        if not matching:
            continue
        group = CardRewardGroup(
            room_type=RoomType.MONSTER,
            odds_type=RarityOddsType.UNIFORM,
            pool=matching,
            count=min(relic.CHOICES, len(matching)),
            flags=CardCreationFlags(0),  # deliberately WITHOUT NoUpgradeRoll
        )
        group.populate(run2)
    unflagged_delta = run2.player_rng.rewards.counter - before2

    assert flagged_delta < unflagged_delta
