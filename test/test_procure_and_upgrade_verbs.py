"""Two command verbs the sim was bypassing (round 7).

`PotionCmd.TryToProcure` (PotionCmd.cs:28-54) is the game's ONE procure entry
point: `Hook.ShouldProcurePotion` first (Sozu), `Hook.AfterPotionProcured` on
success (Belt Buckle). `CardCmd.Upgrade` (CardCmd.cs:265-290) is a no-op for a
card whose `IsUpgradable` is false, and `IsUpgradable` is
`CurrentUpgradeLevel < MaxUpgradeLevel` (CardModel.cs:785-789).

Queue entries: relic/delicate_frond (BeforeCombatStart, g1, g2, g3),
relic/petrified_toad (g1, g2), relic/sozu/g1; relic/astrolabe/g1,
relic/bone_tea/g1, relic/neows_talisman/g1.
"""
from __future__ import annotations

import random

import pytest

from sts2_rl import CombatState, make_relic
from sts2_rl.cards import make_card
from sts2_rl.run import RunState


def fresh_run(seed: int = 0, **kw) -> RunState:
    return RunState(rng=random.Random(seed), **kw)


# ══════════════════════════════════════════════════════════════════════════
# PotionCmd.TryToProcure
# ══════════════════════════════════════════════════════════════════════════

def test_sozu_refuses_the_delicate_fronds_potions():
    """DelicateFrond.cs:18-21 — `if (!(await PotionCmd.TryToProcure(...)).success)
    break;`. A Sozu owner gets NOTHING from the Frond, and the loop must BREAK
    rather than spin on a belt that never fills."""
    cs = CombatState(rng=random.Random(0),
                     relics=[make_relic("delicate_frond"), make_relic("sozu")])
    assert cs.player.potions == [None, None, None]


def test_the_delicate_frond_still_fills_the_belt_without_sozu():
    cs = CombatState(rng=random.Random(0), relics=[make_relic("delicate_frond")])
    assert all(p is not None for p in cs.player.potions)


def test_sozu_refuses_the_petrified_toads_rock():
    """PetrifiedToad.cs:19 — `await PotionCmd.TryToProcure<PotionShapedRock>`."""
    cs = CombatState(rng=random.Random(0),
                     relics=[make_relic("petrified_toad"), make_relic("sozu")])
    assert cs.player.potions == [None, None, None]


def test_the_petrified_toad_still_procures_without_sozu():
    cs = CombatState(rng=random.Random(0), relics=[make_relic("petrified_toad")])
    assert cs.player.potions[0] is not None


@pytest.mark.parametrize("relic_id", ["delicate_frond", "petrified_toad"])
def test_belt_buckle_loses_its_dexterity_when_the_belt_fills(relic_id):
    """`Hook.AfterPotionProcured` (PotionCmd.cs:46). BeltBuckle.cs:63-70 takes
    its 2 Dexterity back the moment a potion is procured, so both of these
    relics net the player ZERO Dexterity."""
    cs = CombatState(rng=random.Random(0),
                     relics=[make_relic("belt_buckle"), make_relic(relic_id)])
    assert "dexterity" not in cs.player.powers


def test_the_frond_rolls_a_rarity_rather_than_picking_uniformly():
    """DelicateFrond.cs:17 -> PotionFactory.CreateRandomPotionOutOfCombat ->
    `NextFloat()`; Rare <= 0.1, Uncommon <= 0.35, else Common
    (PotionFactory.cs:67-81). A uniform pick over a 16/16/16 pool gives Rare a
    third of the time instead of a tenth."""
    from sts2_rl.potion_pools import POTION_POOL

    _RARITY = dict(POTION_POOL)
    rares = 0
    total = 0
    for seed in range(120):
        cs = CombatState(rng=random.Random(seed),
                         relics=[make_relic("delicate_frond")])
        for potion in cs.player.potions:
            if potion is None:
                continue
            total += 1
            if _RARITY[potion.id] == "rare":
                rares += 1
    assert total > 0
    # 0.10 expected; a uniform pick over the pool would sit near 0.33.
    assert rares / total < 0.22, f"{rares}/{total} rare"


# ══════════════════════════════════════════════════════════════════════════
# CardCmd.Upgrade
# ══════════════════════════════════════════════════════════════════════════

def test_card_cmd_upgrade_skips_a_non_upgradable_card():
    """CardCmd.cs:271-276 — `if (!card.IsUpgradable) continue;`. C# also THROWS
    if CurrentUpgradeLevel is ever set above MaxUpgradeLevel
    (CardModel.cs:773-776), so the state the bare `upgrade()` produced is one
    the source treats as impossible."""
    from sts2_rl.cmds import CardCmd

    dazed = make_card("dazed")
    assert dazed.max_upgrade_level == 0
    CardCmd.upgrade(None, dazed)
    assert dazed.upgrade_level == 0

    strike = make_card("strike")
    CardCmd.upgrade(None, strike)
    assert strike.upgrade_level == 1
    CardCmd.upgrade(None, strike)
    assert strike.upgrade_level == 1


def test_bone_tea_leaves_the_statuses_in_hand_alone():
    """BoneTea.cs:53-56 upgrades the opening hand through CardCmd.Upgrade."""
    relic = make_relic("bone_tea")
    cs = CombatState(rng=random.Random(0), relics=[relic])
    cs.player.hand = [make_card("strike"), make_card("dazed"), make_card("burn")]
    cs.turn = 1
    relic.combats_left = 1   # it already spent its charge on the real turn 1
    relic.after_side_turn_start(cs.player)
    assert [c.upgrade_level for c in cs.player.hand] == [1, 0, 0]


def test_neows_talisman_does_not_push_a_smithed_strike_past_its_max():
    """CardCmd.cs:271-276 again — an already-upgraded last Basic Strike stays
    at 1 rather than reaching the impossible 2."""
    run = fresh_run()
    strike = [c for c in run.deck if c.id == "strike"][-1]
    defend = [c for c in run.deck if c.id == "defend"][-1]
    strike.upgrade()
    defend.upgrade()
    run.add_relic("neows_talisman")
    assert (strike.upgrade_level, defend.upgrade_level) == (1, 1)


def test_astrolabe_leaves_a_transformed_curse_unupgraded():
    """Astrolabe.cs:26 is `CardCmd.Upgrade`. Curses ARE transformable
    (CardSelectCmd.cs:487 admits everything non-Quest and removable), a curse
    transforms into another curse, and every curse has MaxUpgradeLevel 0."""
    run = fresh_run()
    curse = run.add_card(make_card("clumsy"))
    run.card_selector = lambda purpose, candidates, count: [curse]
    run.add_relic("astrolabe")
    replacements = [c for c in run.deck if c.rarity.value == "curse"]
    assert replacements
    assert all(c.upgrade_level == 0 for c in replacements)
