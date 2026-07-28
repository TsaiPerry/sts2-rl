"""Tier-1 relic gap fixes (audit/GAP-QUEUE.md entries 45, 46, 48, 49, 50, 51, 55).

One file per work package, per the wave plan's "put new tests in a file you
own" rule.  Each section names the queue entry it pins and asserts the numbers
that entry's ``observable`` field states.
"""
from __future__ import annotations

import random

import pytest

from sts2_rl import ALL_RELICS, CombatState, DamageCmd, make_relic
from sts2_rl.cards import make_card
from sts2_rl.relics import Relic, RelicRarity
from sts2_rl.rewards import RarityOddsType, create_reward_cards, generate_combat_rewards
from sts2_rl.rooms import RoomType
from sts2_rl.run import RunState
from sts2_rl.valueprops import DamageProps, ValueProp


def fresh(relics=None, seed: int = 0, **kwargs) -> CombatState:
    return CombatState(rng=random.Random(seed), relics=relics, **kwargs)


def fresh_run(seed: int = 0, **kwargs) -> RunState:
    return RunState(rng=random.Random(seed), **kwargs)


# ══════════════════════════════════════════════════════════════════════════
# Entry 51 (+45) — relic/_combat_reset
#
# "Run the stimulus in two successive combats with the same relic instance and
#  assert the observations are equal."  Every probe below is written as
#  OBSERVE-then-LATCH: it reads the fresh-combat answer first, then sets the
#  per-combat latch, so combat 2's read is the one the gap corrupts.
# ══════════════════════════════════════════════════════════════════════════

def _skill() -> object:
    return make_card("defend")


def _probe_red_skull(cs, r):
    return cs.player.strength


def _probe_permafrost(cs, r):
    r.on_card_played(make_card("inflame"))
    return cs.player.block


def _probe_vambrace(cs, r):
    card = make_card("defend")
    v = r.modify_block_multiplicative(cs.player, 5, card, ValueProp.MOVE)
    # Vambrace.cs:82-113 — AfterModifyingBlockAmount latches the card, the end
    # of that card's play burns BlockGainedThisCombat.
    r.after_modify_block_amount(cs.player, card)
    r.on_card_played(card)
    return v


def _probe_centennial_puzzle(cs, r):
    before = len(cs.player.hand)
    r.on_damage_received(
        cs.player, 4, cs.enemy, None, DamageProps.MONSTER_MOVE)
    return len(cs.player.hand) - before


def _probe_ruined_helmet(cs, r):
    from sts2_rl.cmds import PowerCmd
    from sts2_rl.powers import StrengthPower
    PowerCmd.apply(cs.hooks, cs.player, StrengthPower, 2, applier=cs.player)
    return cs.player.strength


def _probe_paels_tears(cs, r):
    r.on_player_turn_started(cs.player)
    v = cs.player.energy
    cs.player.energy = 2
    r.on_player_turn_end(cs.player)
    return v


def _probe_burning_sticks(cs, r):
    before = len(cs.player.hand)
    r.on_card_exhausted(_skill())
    return len(cs.player.hand) - before


def _probe_belt_buckle(cs, r):
    p = cs.player.powers.get("dexterity")
    return p.amount if p is not None else 0


def _probe_paels_eye(cs, r):
    v = 1 if r.should_take_extra_turn(cs.player) else 0
    r.on_extra_turn(cs.player)
    return v


def _probe_paels_legion(cs, r):
    card = make_card("defend")
    v = r.modify_block_multiplicative(cs.player, 5, card, ValueProp.MOVE)
    r.on_card_played(card)
    return v


def _probe_self_forming_clay(cs, r):
    r.on_player_turn_started(cs.player)
    v = cs.player.block
    r.on_damage_received(
        cs.player, 3, cs.enemy, None, DamageProps.MONSTER_MOVE)
    return v


def _probe_diamond_diadem(cs, r):
    """Entry 45's hole: the combat ends on the player's own turn, so
    `on_player_turn_end` never runs and the counter carries over."""
    from sts2_rl.powers import DiamondDiademPower
    r.on_player_turn_end(cs.player)
    v = 1 if DiamondDiademPower.id in cs.player.powers else 0
    for _ in range(3):
        r.on_card_played(make_card("strike"))
    return v


def _probe_joss_paper(cs, r):
    ethereal = make_card("dazed")
    v = r._ethereal_pending
    r.on_card_exhausted(ethereal)
    r.on_card_exhausted(ethereal)
    return v


# (relic_id, probe, expected value in a FRESH combat)
COMBAT_RESET_CASES = [
    ("red_skull", _probe_red_skull, 3),
    ("permafrost", _probe_permafrost, 7),
    ("vambrace", _probe_vambrace, 2.0),
    ("centennial_puzzle", _probe_centennial_puzzle, 3),
    ("ruined_helmet", _probe_ruined_helmet, 4),
    ("paels_tears", _probe_paels_tears, 3),
    ("burning_sticks", _probe_burning_sticks, 1),
    ("belt_buckle", _probe_belt_buckle, 2),
    ("paels_eye", _probe_paels_eye, 1),
    ("paels_legion", _probe_paels_legion, 2.0),
    ("self_forming_clay", _probe_self_forming_clay, 0),
    ("diamond_diadem", _probe_diamond_diadem, 1),
    ("joss_paper", _probe_joss_paper, 0),
]


@pytest.mark.parametrize("relic_id,probe,expected", COMBAT_RESET_CASES)
def test_relic_state_resets_at_the_combat_boundary(relic_id, probe, expected):
    """RunState carries ONE relic instance across combats; C# resets its
    per-combat state at the boundary (AfterCombatEnd / BeforeCombatStart /
    AfterRoomEntered(CombatRoom)).  Combat 2 must answer exactly like combat 1.
    """
    relic = make_relic(relic_id)
    first = probe(fresh(relics=[relic], current_hp=30), relic)
    second = probe(fresh(relics=[relic], current_hp=30), relic)
    assert first == expected
    assert second == first


def test_joss_paper_exhaust_counter_survives_the_combat_boundary():
    """JossPaper.AfterCombatEnd resets EtherealCount ONLY — CardsExhausted is a
    [SavedProperty] that persists across combats (JossPaper.cs:181-185)."""
    r = make_relic("joss_paper")
    cs = fresh(relics=[r])
    for _ in range(3):
        r.on_card_exhausted(make_card("defend"))
    assert r.cards_exhausted == 3
    fresh(relics=[r])
    assert r.cards_exhausted == 3


# ══════════════════════════════════════════════════════════════════════════
# Entry 55 — relic/_victory_flatten
# ══════════════════════════════════════════════════════════════════════════

def test_meat_on_the_bone_reads_the_pre_burning_blood_hp():
    """Hook.AfterCombatVictory (Hook.cs:340-351) runs AfterCombatVictoryEarly
    over EVERY listener before the plain pass.  Meat on the Bone is the only
    Early implementer in the game, so its 50% threshold always sees the
    pre-heal HP: at 38/80 the game reaches 56, the flattened sim reached 44."""
    relics = [make_relic("burning_blood"), make_relic("meat_on_the_bone")]
    cs = fresh(relics=relics, current_hp=38)
    cs._end_combat(player_won=True)
    assert cs.player.hp == 56


def test_meat_on_the_bone_order_independence():
    """The reverse relic order already gave 56; both must now agree."""
    relics = [make_relic("meat_on_the_bone"), make_relic("burning_blood")]
    cs = fresh(relics=relics, current_hp=38)
    cs._end_combat(player_won=True)
    assert cs.player.hp == 56


def test_run_level_victory_dispatch_runs_the_early_pass_first():
    """The RUN-level walk (`RunState.finish_combat`) is the second half of the
    same Hook.AfterCombatVictory, so it makes the same two COMPLETE passes.
    A relic registered *after* Sword of Stone but listening on the Early phase
    must still see the pre-increment counter."""
    seen = []

    class EarlyProbe(Relic):
        id = "_early_probe"
        name = "Early Probe"
        rarity = RelicRarity.EVENT

        def after_combat_end_early(self, run, room_type) -> None:
            seen.append(("early", sword.elites_defeated))

        def after_combat_end(self, run, room_type) -> None:
            seen.append(("main", sword.elites_defeated))

    sword = make_relic("sword_of_stone")
    run = fresh_run(relics=[sword, EarlyProbe()])
    cs = fresh(relics=list(run.relics))
    run.finish_combat(cs, RoomType.ELITE)
    assert seen == [("early", 0), ("main", 1)]


def test_sword_of_stone_and_war_hammer_stay_on_the_main_victory_pass():
    """Both are plain `AfterCombatVictory` in the source (SwordOfStone.cs:40,
    WarHammer.cs:19) — MeatOnTheBone.cs:47 is the game's ONLY Early
    implementer, so neither moves to the Early pass."""
    for relic_id in ("sword_of_stone", "war_hammer"):
        relic = make_relic(relic_id)
        assert type(relic).after_combat_end is not Relic.after_combat_end
        assert type(relic).after_combat_end_early is Relic.after_combat_end_early


# ══════════════════════════════════════════════════════════════════════════
# Entry 46 — relic/_is_allowed
# ══════════════════════════════════════════════════════════════════════════

# RelicModel.IsBeforeAct3TreasureChest (RelicModel.cs:452-456): TotalFloor < 41
# in single player.  Seventeen relics gate on it.
FLOOR_GATED = [
    "amethyst_aubergine", "book_of_five_rings", "bowler_hat", "dragon_fruit",
    "frozen_egg", "girya", "juzu_bracelet", "lasting_candy", "lucky_fysh",
    "meal_ticket", "molten_egg", "old_coin", "planisphere", "shovel",
    "toxic_egg", "white_beast_statue", "white_star",
]


@pytest.mark.parametrize("relic_id", FLOOR_GATED)
def test_is_before_act3_treasure_chest_gate(relic_id):
    cls = ALL_RELICS[relic_id]
    assert cls.is_allowed(fresh_run(total_floor=40)) is True
    assert cls.is_allowed(fresh_run(total_floor=41)) is False
    assert cls.is_allowed(fresh_run(total_floor=60)) is False


def test_is_allowed_defaults_to_true():
    assert ALL_RELICS["akabeko"].is_allowed(fresh_run(total_floor=60)) is True


def test_multiplayer_only_relic_is_never_allowed():
    """MassiveScroll.IsAllowed => runState.Players.Count > 1."""
    assert ALL_RELICS["massive_scroll"].is_allowed(fresh_run()) is False


def test_single_player_only_relics_are_allowed():
    """SilverCrucible / WingedBoots gate on Players.Count == 1."""
    for rid in ("silver_crucible", "winged_boots"):
        assert ALL_RELICS[rid].is_allowed(fresh_run(total_floor=60)) is True


# ══════════════════════════════════════════════════════════════════════════
# Entry 49 — relic/_reward_late_pass
# ══════════════════════════════════════════════════════════════════════════

class _AddsAStrike(Relic):
    """Stand-in for LastingCandy: adds an option in the EARLY pass.
    Not registered — it exists only to exercise the two-pass dispatch."""

    id = "_adds_a_strike"
    name = "Adds a Strike"
    rarity = RelicRarity.COMMON

    def modify_card_reward_options(self, run, cards):
        cards.append(make_card("strike"))


def test_early_added_reward_option_is_visible_to_the_late_upgraders():
    """C# dispatches TryModifyCardRewardOptions over every listener, THEN
    TryModifyCardRewardOptionsLate over every listener (Hook.cs:1444-1466).
    The egg relics upgrade in the late pass, so a card added by an early-pass
    relic must be upgraded too — regardless of registration order."""
    run = fresh_run()
    run.relics = [make_relic("molten_egg"), _AddsAStrike()]
    cards = create_reward_cards(run, RarityOddsType.REGULAR, count=0)
    added = [c for c in cards if c.id == "strike"]
    assert len(added) == 1
    assert added[0].upgrade_level == 1


def test_early_added_reward_option_is_upgraded_in_the_other_order():
    run = fresh_run()
    run.relics = [_AddsAStrike(), make_relic("molten_egg")]
    cards = create_reward_cards(run, RarityOddsType.REGULAR, count=0)
    assert [c.upgrade_level for c in cards if c.id == "strike"] == [1]


def test_driftwood_reroll_flag_is_a_late_rewards_modifier():
    """Driftwood.cs:14 overrides TryModifyRewardsLate, not the plain pass."""
    from sts2_rl.relics import Driftwood
    assert hasattr(Driftwood, "modify_combat_rewards_late")
    assert "modify_combat_rewards" not in Driftwood.__dict__


# ══════════════════════════════════════════════════════════════════════════
# Entry 48 — relic/_stub  (the stubs whose premises the sim has outgrown)
# ══════════════════════════════════════════════════════════════════════════

def test_old_coin_grants_300_gold_on_pickup():
    run = fresh_run()
    before = run.gold
    run.add_relic(make_relic("old_coin"))
    assert run.gold == before + 300


def test_old_coin_undo_removes_the_gold_again():
    run = fresh_run()
    before = run.gold
    relic = make_relic("old_coin")
    run.add_relic(relic)
    relic.undo_after_obtained(run)
    assert run.gold == before


def test_bowler_hat_scales_gold_gains_by_125_percent():
    run = fresh_run()
    run.add_relic(make_relic("bowler_hat"))
    before = run.gold
    run.gain_gold(100)
    assert run.gold - before == 125


def test_lucky_fysh_pays_15_gold_per_card_added_to_the_deck():
    run = fresh_run()
    run.add_relic(make_relic("lucky_fysh"))
    before = run.gold
    run.add_card(make_card("strike"))
    assert run.gold - before == 15


def test_book_of_five_rings_heals_20_every_fifth_card():
    run = fresh_run()
    run.hp = 40
    run.add_relic(make_relic("book_of_five_rings"))
    for _ in range(4):
        run.add_card(make_card("strike"))
    assert run.hp == 40
    run.add_card(make_card("strike"))
    assert run.hp == 60


def test_amethyst_aubergine_adds_15_gold_to_a_combat_reward():
    plain = fresh_run(seed=3)
    base = generate_combat_rewards(plain, RoomType.MONSTER).gold
    run = fresh_run(seed=3)
    run.add_relic(make_relic("amethyst_aubergine"))
    assert generate_combat_rewards(run, RoomType.MONSTER).gold == base + 15


def test_white_beast_statue_forces_a_potion_reward():
    # Drive the pity threshold to 0 so only the force flag can produce a drop.
    plain = fresh_run(seed=5)
    plain.potion_reward_odds.current_value = 0.0
    assert generate_combat_rewards(plain, RoomType.MONSTER).potion is None
    run = fresh_run(seed=5)
    run.potion_reward_odds.current_value = 0.0
    run.add_relic(make_relic("white_beast_statue"))
    assert generate_combat_rewards(run, RoomType.MONSTER).potion is not None


def test_a_forced_potion_reward_still_consumes_its_roll():
    """PotionRewardOdds.Roll takes `_rng.NextFloat()` before testing the force
    flag, so White Beast Statue must not swallow a Rewards draw."""
    from sts2_rl.rewards import PotionRewardOdds

    class _Counting:
        def __init__(self):
            self.draws = 0

        def random(self):
            self.draws += 1
            return 0.99

    rng = _Counting()
    odds = PotionRewardOdds(rng)
    assert odds.roll(RoomType.MONSTER, force=True) is True
    assert rng.draws == 1


def test_lava_lamp_upgrades_a_damage_free_combats_card_reward():
    """LavaLamp.TryModifyCardRewardOptionsLate upgrades every upgradable
    option while TookDamageThisCombat is clear, and does nothing once the
    owner has taken unblocked damage."""
    relic = make_relic("lava_lamp")
    run = fresh_run()
    run.add_relic(relic)
    cards = [make_card("strike"), make_card("defend")]
    relic.modify_card_reward_options_late(run, cards)
    assert [c.upgrade_level for c in cards] == [1, 1]

    cs = fresh(relics=[relic])
    DamageCmd.deal(cs.hooks, cs.player, 5, dealer=cs.enemy,
                   props=DamageProps.MONSTER_MOVE)
    assert relic.took_damage_this_combat is True
    cards = [make_card("strike"), make_card("defend")]
    relic.modify_card_reward_options_late(run, cards)
    assert [c.upgrade_level for c in cards] == [0, 0]


def test_meal_ticket_heals_15_on_entering_a_shop():
    run = fresh_run()
    run.hp = 50
    relic = make_relic("meal_ticket")
    relic.after_room_entered(run, None, RoomType.SHOP)
    assert run.hp == 65
    relic.after_room_entered(run, None, RoomType.MONSTER)
    assert run.hp == 65


def test_planisphere_heals_5_on_a_question_mark_node():
    from sts2_rl.actmap import MapPoint, MapPointType

    run = fresh_run()
    run.hp = 50
    relic = make_relic("planisphere")
    unknown = MapPoint(0, 0)
    unknown.point_type = MapPointType.UNKNOWN
    rest = MapPoint(0, 0)
    rest.point_type = MapPointType.REST_SITE
    relic.after_room_entered(run, unknown, RoomType.EVENT)
    assert run.hp == 55
    relic.after_room_entered(run, rest, RoomType.REST_SITE)
    assert run.hp == 55


def test_potion_belt_grows_the_belt_by_two_slots():
    run = fresh_run()
    before = run.max_potions
    run.add_relic(make_relic("potion_belt"))
    assert run.max_potions == before + 2
    assert len(run.potions) == before + 2


def test_tiny_mailbox_adds_two_potion_offers_to_the_rest_heal_screen():
    from sts2_rl.rewards import CombatRewards

    run = fresh_run()
    rewards = CombatRewards(room_type=RoomType.REST_SITE)
    make_relic("tiny_mailbox").modify_rest_site_heal_rewards(run, rewards)
    assert len(rewards.special_potions) == 2


def test_wing_charm_enchants_one_reward_option_with_swift():
    from sts2_rl.enchantments import SwiftEnchantment

    run = fresh_run()
    relic = make_relic("wing_charm")
    cards = [make_card("strike"), make_card("defend"), make_card("bash")]
    relic.modify_card_reward_options_late(run, cards)
    enchanted = [c for c in cards if isinstance(c.enchantment, SwiftEnchantment)]
    assert len(enchanted) == 1
    assert enchanted[0].enchantment.amount == 1


def test_mystic_lighter_adds_9_to_an_enchanted_attack():
    from sts2_rl.cmds import DamageCmd as _DamageCmd
    from sts2_rl.enchantments import SharpEnchantment

    relic = make_relic("mystic_lighter")
    plain = make_card("strike")
    assert relic.modify_damage_additive(
        None, 6, None, plain, DamageProps.CARD) == 0

    cs = fresh(relics=[relic])
    enchanted = make_card("strike")
    SharpEnchantment().attach(enchanted)
    assert relic.modify_damage_additive(
        cs.enemy, 6, cs.player, enchanted, DamageProps.CARD) == 9
    # Unpowered damage is untouched (MysticLighter.cs:18-21).
    assert relic.modify_damage_additive(
        cs.enemy, 6, cs.player, enchanted,
        DamageProps.NON_CARD_UNPOWERED) == 0


def test_regal_pillow_adds_15_to_the_rest_site_heal_amount():
    """HealRestSiteOption.GetHealAmount (HealRestSiteOption.cs:60-63) runs the
    base `MaxHp * 0.3m` through Hook.ModifyRestSiteHealAmount; RegalPillow.cs:
    19-26 adds 15 to that chain.  Base 24 -> 39 at 80 max HP."""
    run = fresh_run()
    relic = make_relic("regal_pillow")
    assert run.rest_site_heal_amount() == 24
    assert relic.modify_rest_site_heal_amount(run, 24) == 39
    run.relics.append(relic)
    assert run.rest_site_heal_amount() == 39


def test_regal_pillow_makes_the_rest_site_heal_39():
    """`RunState.rest_heal` heals whatever the hook chain returns."""
    run = fresh_run(relics=[make_relic("regal_pillow")])
    run.hp = 20
    assert run.rest_heal() == 39
    assert run.hp == 59


# ══════════════════════════════════════════════════════════════════════════
# Entry 50 — relic/_auto_keep
#
# `WithSkippingDisallowed` appears on exactly two lines in the whole C# source
# (RewardsSet.cs:115 and its one caller NeowsBones.cs:43), so every other
# `RewardsCmd.OfferCustom` is a take-or-SKIP screen: RelicReward.OnSelect
# (RelicReward.cs:109-115) is the only path to RelicCmd.Obtain, and
# RelicReward.OnSkipped (RelicReward.cs:117-123) records `wasPicked: false`
# instead.  These pin the decline as a first-class outcome.
# ══════════════════════════════════════════════════════════════════════════

def _skipping_driver(run):
    """A driver whose asker declines every take-or-skip reward offer."""
    from sts2_rl.driver import DecisionKind as DK
    from sts2_rl.driver import RunDriver

    seen = []

    def ask(request):
        seen.append(request)
        if request.kind is DK.REWARD_RELIC:
            return 1                      # skip
        if request.kind is DK.REWARD_POTION:
            return 1                      # skip
        if request.kind is DK.SELECT_CARDS and request.skippable:
            return len(request.candidates)
        return request.legal_actions()[0]

    RunDriver(run, ask)
    return seen


def _taking_driver(run):
    """A driver whose asker takes every take-or-skip reward offer."""
    from sts2_rl.driver import RunDriver

    seen = []

    def ask(request):
        seen.append(request)
        return request.legal_actions()[0]

    RunDriver(run, ask)
    return seen


def test_small_capsule_relic_can_be_declined():
    """SmallCapsule.cs:13-19 offers exactly one RelicReward.  Populate runs
    before the offer, so a declined relic still LEAVES the grab bag; only
    RelicCmd.Obtain (and with it AfterObtained) is skipped."""
    from sts2_rl.driver import DecisionKind as DK

    run = fresh_run()
    seen = _skipping_driver(run)
    bag_before = len(run.relic_grab_bag)
    run.add_relic("small_capsule")
    assert [r.id for r in run.relics] == ["small_capsule"]
    assert len(run.relic_grab_bag) == bag_before - 1
    assert [r.kind for r in seen] == [DK.REWARD_RELIC]
    assert seen[0].relic is not None


def test_small_capsule_relic_is_granted_when_taken():
    run = fresh_run()
    _taking_driver(run)
    run.add_relic("small_capsule")
    assert len(run.relics) == 2


def test_a_relic_offer_with_no_selector_is_still_auto_taken():
    """A bare RunState has nobody to decline: the offer resolves as a take,
    which is also the pre-seam behaviour every other test relies on."""
    run = fresh_run()
    run.add_relic("small_capsule")
    assert len(run.relics) == 2


def test_calling_bell_offers_its_three_relics_separately():
    """CallingBell.cs:31 hands three RelicRewards to RewardsCmd.OfferCustom —
    three independent declines.  The curse is NOT part of the screen
    (CardPileCmd.AddCurseToDeck at CallingBell.cs:29 precedes it)."""
    from sts2_rl.driver import DecisionKind as DK

    run = fresh_run()
    seen = _skipping_driver(run)
    run.add_relic("calling_bell")
    assert [r.id for r in run.relics] == ["calling_bell"]
    assert len([r for r in seen if r.kind is DK.REWARD_RELIC]) == 3
    assert any(c.id == "curse_of_the_bell" for c in run.deck)


def test_toy_box_offers_its_four_wax_relics():
    """ToyBox.cs:87-97 pulls four relics and OFFERS them; a declined one never
    runs its own AfterObtained."""
    from sts2_rl.driver import DecisionKind as DK

    run = fresh_run()
    seen = _skipping_driver(run)
    bag_before = len(run.relic_grab_bag)
    run.add_relic("toy_box")
    assert [r.id for r in run.relics] == ["toy_box"]
    assert len(run.relic_grab_bag) == bag_before - 4
    assert len([r for r in seen if r.kind is DK.REWARD_RELIC]) == 4


def test_elite_reward_relic_can_be_declined():
    """The elite screen's RelicReward (rewards.py's elite branch) is the same
    take-or-skip offer — the two force-grant sites the queue records as having
    no owning record."""
    run = fresh_run(7)
    _skipping_driver(run)
    bag_before = len(run.relic_grab_bag)
    rewards = generate_combat_rewards(run, RoomType.ELITE)
    assert len(rewards.relics) == 1              # still on the screen
    assert rewards.relics[0] not in run.relics   # but never obtained
    assert len(run.relic_grab_bag) == bag_before - 1


def test_lava_rock_boss_relics_can_be_declined():
    run = fresh_run(18)
    run.start_act("overgrowth", act_index=0)
    run.add_relic("lava_rock")
    _skipping_driver(run)
    owned = len(run.relics)
    rewards = generate_combat_rewards(run, RoomType.BOSS)
    assert len(rewards.relics) == 2
    assert len(run.relics) == owned


def test_lost_coffer_potion_can_be_declined():
    """LostCoffer.cs:21's PotionReward is its own declinable entry; the card
    half already modelled the decline."""
    from sts2_rl.driver import DecisionKind as DK

    run = fresh_run()
    seen = _skipping_driver(run)
    run.add_relic("lost_coffer")
    assert run.held_potions == []
    assert len(run.deck) == 10                   # the card offer was declined
    assert len([r for r in seen if r.kind is DK.REWARD_POTION]) == 1


def test_lost_coffer_potion_is_kept_when_taken():
    run = fresh_run()
    _taking_driver(run)
    run.add_relic("lost_coffer")
    assert len(run.held_potions) == 1


def test_cauldron_offers_five_potions():
    """Cauldron.cs:31-55 offers `DynamicVars['Potions'].IntValue == 5`
    PotionRewards; the port was a behaviourless stub."""
    from sts2_rl.driver import DecisionKind as DK

    run = fresh_run()
    seen = _skipping_driver(run)
    run.add_relic("cauldron")
    assert run.held_potions == []
    assert len([r for r in seen if r.kind is DK.REWARD_POTION]) == 5


def test_cauldron_fills_the_belt_when_taken():
    run = fresh_run()
    _taking_driver(run)
    run.add_relic("cauldron")
    # Five offers, a three-slot belt: the belt fills and the rest are refused
    # by Player.AddPotionInternal, not by the screen.
    assert len(run.held_potions) == run.max_potions


def test_orrery_offers_five_three_card_choices():
    """Orrery.cs:19-28 offers five independently skippable CardRewards of 3."""
    from sts2_rl.driver import DecisionKind as DK

    run = fresh_run()
    seen = _skipping_driver(run)
    run.add_relic("orrery")
    assert len(run.deck) == 10                   # every screen declined
    picks = [r for r in seen if r.kind is DK.SELECT_CARDS]
    assert len(picks) == 5
    assert all(len(r.candidates) == 3 and r.skippable for r in picks)


def test_orrery_adds_one_card_per_screen_when_taken():
    run = fresh_run()
    _taking_driver(run)
    run.add_relic("orrery")
    assert len(run.deck) == 15


def test_gambling_chip_may_keep_the_whole_hand():
    """GamblingChip.cs:12 is `CardSelectorPrefs(prompt, 0, 999999999)` —
    MinSelect ZERO — so "discard nothing" is a first-class outcome.  The
    driver used to short-circuit the whole hand away without ever issuing a
    decision request."""
    from sts2_rl.driver import DecisionKind as DK
    from sts2_rl.driver import RunDriver

    run = fresh_run()
    seen = []

    def ask(request):
        seen.append(request)
        return len(request.candidates)           # the skip action

    driver = RunDriver(run, ask)
    hand = [make_card("strike") for _ in range(5)]
    kept = driver._card_selector("gambling_chip", list(hand), len(hand))
    assert kept == []
    assert [r.kind for r in seen] == [DK.SELECT_CARDS]
    assert seen[0].skippable


def test_toolbox_and_choices_paradox_selections_are_not_skippable():
    """Toolbox.cs:28 is `FromChooseACardScreen(...)` with `canSkip` defaulting
    to false, and ChoicesParadox.cs:46 is `CardSelectorPrefs(prompt, 1)` —
    the 2-arg ctor, MinSelect == MaxSelect == 1.  Neither may be declined, so
    neither may use a purpose in SKIPPABLE_PURPOSES."""
    from sts2_rl.driver import SKIPPABLE_PURPOSES

    seen = []

    def selector(purpose, candidates, count):
        seen.append(purpose)
        return list(candidates)[:count]

    fresh(
        relics=[make_relic("toolbox"), make_relic("choices_paradox")],
        card_selector=selector,
    )
    assert len(seen) == 2
    assert all(p not in SKIPPABLE_PURPOSES for p in seen)
