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
    # `amount` is C#'s `modifiedBlock` (CreatureCmd.cs:646); the listener
    # opens on `if (modifiedAmount <= 0m) return;` (Vambrace.cs:84).
    r.after_modify_block_amount(cs.player, 10, card)
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
    r.after_side_turn_start(cs.player)
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
    # MOVED 2026-07-29 (round 7, relic/self_forming_clay/g2): the payout slot is
    # AfterBlockCleared (SelfFormingClayPower.cs:19-25), not the last turn-start
    # slot. The probe is about the COMBAT-BOUNDARY reset, which is unchanged.
    r.on_block_cleared(cs.player)
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

    def modify_card_reward_options(self, run, cards, options=None):
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


def test_driftwood_makes_the_rest_site_card_reward_rerollable_too():
    """Hook.ModifyRewards's only caller is RewardsSet.GenerateWithoutOffering
    (RewardsSet.cs:125-147), which EVERY RewardsSet goes through -- including
    the one RewardsCmd.OfferCustom builds for a rest-site heal
    (HealRestSiteOption.cs:110-112).  Driftwood.cs:14-25 does not look at the
    room at all, so it marks that screen's CardReward rerollable exactly like
    a combat one."""
    run = fresh_run(16)
    run.add_relic(make_relic("dream_catcher"))
    run.add_relic(make_relic("driftwood"))
    rewards = run.rest_heal_rewards()
    assert len(rewards.cards) == 3
    assert rewards.can_reroll


def test_room_gated_reward_relics_stay_off_the_rest_site_screen():
    """...but the room-gated ones must NOT fire there.  A custom RewardsSet
    never sets Room (RewardsSet.WithCustomRewards, RewardsSet.cs:106-110), so
    `room == null` short-circuits AmethystAubergine.cs:25-35, BlackStar.cs,
    LavaRock.cs and WongosMysteryTicket.cs (`!(room is CombatRoom)`)."""
    run = fresh_run(16)
    run.add_relic(make_relic("dream_catcher"))
    run.add_relic(make_relic("amethyst_aubergine"))
    gold_before = run.gold
    rewards = run.rest_heal_rewards()
    assert rewards.gold == 0
    assert run.gold == gold_before


def test_a_ripe_ticket_still_pays_on_the_final_acts_boss():
    """The sim short-circuited the whole of generate_combat_rewards for the
    last act's boss; C# skips only the room's OWN rewards (RewardsSet.cs:85-91)
    and still runs Hook.ModifyRewards on the empty list, so Wongo's Mystery
    Ticket pays its three relics there."""
    run = fresh_run(19)
    run._is_final_act = True   # what start_act(is_final_act=) sets
    ticket = make_relic("wongos_mystery_ticket")
    run.add_relic(ticket)
    for _ in range(5):
        ticket.after_combat_end(run, RoomType.MONSTER)
    rewards = generate_combat_rewards(run, RoomType.BOSS)
    assert len(rewards.relics) == 3
    assert ticket.is_used_up
    # ...and the room's own rewards still do not exist there.
    assert rewards.gold == 0 and rewards.cards == [] and rewards.potion is None


def test_the_final_boss_screen_still_pays_no_aubergine_gold():
    """AmethystAubergine.cs:33-35 is the explicit final-act guard that proves
    the pass runs at all — and it must keep the gold off that screen."""
    run = fresh_run(19)
    run._is_final_act = True   # what start_act(is_final_act=) sets
    run.add_relic(make_relic("amethyst_aubergine"))
    gold_before = run.gold
    rewards = generate_combat_rewards(run, RoomType.BOSS)
    assert rewards.gold == 0
    assert run.gold == gold_before


def test_lasting_candy_adds_a_power_option_every_other_combat():
    """LastingCandy.cs:100-136 — the game's only implementer of the EARLY
    TryModifyCardRewardOptions pass. `IsInTriggeringCombat` is
    `CombatsSeen > 0 && CombatsSeen % 2 == 0` (LastingCandy.cs:68-78), and
    AfterCombatEnd increments before the screen is generated
    (CombatManager.cs:988 precedes CombatRoom.cs:251-253), so combats 2, 4, ...
    carry a fourth, always-Power option."""
    from sts2_rl.cards import CardType

    run = fresh_run(31)
    candy = make_relic("lasting_candy")
    run.add_relic(candy)

    plain = generate_combat_rewards(run, RoomType.MONSTER)
    assert len(plain.cards) == 3               # combat 1: nothing added

    candy.after_combat_end(run, RoomType.MONSTER)
    candy.after_combat_end(run, RoomType.MONSTER)
    charged = generate_combat_rewards(run, RoomType.MONSTER)
    assert len(charged.cards) == 4
    assert charged.cards[-1].card_type is CardType.POWER


def test_lasting_candy_stays_off_non_encounter_card_creations():
    """`creationOptions.Source != CardCreationSource.Encounter` -> false
    (LastingCandy.cs:106-109): an event's or relic's own card offer is
    CardCreationSource.Other and gets nothing."""
    from sts2_rl.rewards import RarityOddsType, create_reward_cards

    run = fresh_run(31)
    candy = make_relic("lasting_candy")
    run.add_relic(candy)
    candy.after_combat_end(run, RoomType.MONSTER)
    candy.after_combat_end(run, RoomType.MONSTER)
    cards = create_reward_cards(run, RarityOddsType.REGULAR, mutate_pity=False)
    assert len(cards) == 3


def test_lasting_candys_option_is_visible_to_the_late_pass():
    """It is added in the FIRST pass, so the egg relics / Silver Crucible see
    it (Hook.cs:1444-1466 runs the Late pass over the whole list)."""
    run = fresh_run(31)
    candy = make_relic("lasting_candy")
    run.add_relic(candy)
    run.add_relic(make_relic("frozen_egg"))      # Power cards, upgraded
    candy.after_combat_end(run, RoomType.MONSTER)
    candy.after_combat_end(run, RoomType.MONSTER)
    rewards = generate_combat_rewards(run, RoomType.MONSTER)
    added = rewards.cards[-1]
    assert added.upgrade_level == 1


def test_prayer_wheel_adds_a_second_monster_card_choice():
    """PrayerWheel.cs:14-25 — `rewards.Add(new CardReward(ForRoom(player,
    Monster), 3, player))` on Monster rooms: a SECOND pick-one-of-3, not three
    more options on the first."""
    run = fresh_run(21)
    run.add_relic(make_relic("prayer_wheel"))
    rewards = generate_combat_rewards(run, RoomType.MONSTER)
    assert len(rewards.card_rewards) == 2
    assert [len(g.cards) for g in rewards.card_rewards] == [3, 3]


def test_prayer_wheel_stays_off_elite_and_boss_screens():
    """`room.RoomType != RoomType.Monster` -> false (PrayerWheel.cs:20-23)."""
    for room in (RoomType.ELITE, RoomType.BOSS):
        run = fresh_run(21)
        run.add_relic(make_relic("prayer_wheel"))
        rewards = generate_combat_rewards(run, room)
        assert len(rewards.card_rewards) == 1, room


def test_prayer_wheels_second_choice_is_taken_separately():
    """Two CardRewards on one set are two decisions, so a player who takes
    from both keeps two cards."""
    from sts2_rl.driver import DecisionKind, RunDriver

    run = fresh_run(21)
    run.add_relic(make_relic("prayer_wheel"))
    rewards = generate_combat_rewards(run, RoomType.MONSTER)
    seen = []

    def scripted(request):
        if request.kind == DecisionKind.REWARD_CARD:
            seen.append([c.id for c in request.rewards.cards])
            return 0                       # take the first option
        return request.legal_actions()[0]

    deck_before = len(run.deck)
    RunDriver(run, scripted)._offer_rewards(rewards)
    assert len(seen) == 2
    assert len(run.deck) == deck_before + 2


def test_prayer_wheels_group_is_populated_after_the_late_pass():
    """RewardsSet.cs:137-143 populates a hook-ADDED reward only after both
    ModifyRewards passes, so Driftwood's late flag reaches a group whose cards
    do not exist yet."""
    run = fresh_run(21)
    run.add_relic(make_relic("prayer_wheel"))
    run.add_relic(make_relic("driftwood"))
    rewards = generate_combat_rewards(run, RoomType.MONSTER)
    assert [g.can_reroll for g in rewards.card_rewards] == [True, True]
    assert all(len(g.cards) == 3 for g in rewards.card_rewards)


def test_paels_wing_offers_its_sacrifice_on_the_rest_site_card_reward():
    """PaelsWing.cs:73-81 is TryModifyCardRewardAlternatives -- per CardReward,
    with no room gate -- so the rest screen's 3-card choice carries the
    SACRIFICE alternative too."""
    run = fresh_run(16)
    run.add_relic(make_relic("dream_catcher"))
    wing = make_relic("paels_wing")
    run.add_relic(wing)
    rewards = run.rest_heal_rewards()
    assert rewards.sacrifice_relic is wing


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
    # LavaLamp.cs:66-69 gates on `RunState.CurrentRoom is CombatRoom`, so the
    # relic has to be IN one. This call used to be absent and the upgrade
    # landed anyway (relic/lava_lamp arm 3).
    relic.after_room_entered(run, None, RoomType.MONSTER)
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


def test_calling_bell_pulls_one_relic_of_each_rarity_from_the_bag():
    """CallingBell.GenerateRewards' SHIPPING arm (CallingBell.cs:53-63) builds
    `new RelicReward(Common/Uncommon/Rare, Owner)`; the fixed
    Anchor/GremlinHorn/MummifiedHand list at CallingBell.cs:39-52 is the
    `TestMode.IsOn` branch.  Each Populate is
    `RelicFactory.PullNextRelicFromFront(Player, rarity)`
    (RelicReward.cs:92-95), which SPENDS the bag slot."""
    from sts2_rl.relics import ALL_RELICS, RelicRarity

    run = fresh_run()
    seen = _skipping_driver(run)
    bag_before = len(run.relic_grab_bag)
    run.add_relic("calling_bell")
    offered = [r.relic for r in seen if r.relic is not None]
    assert [ALL_RELICS[r.id].rarity for r in offered] == [
        RelicRarity.COMMON, RelicRarity.UNCOMMON, RelicRarity.RARE,
    ]
    # Not the TestMode trio.
    assert {r.id for r in offered} != {"anchor", "gremlin_horn", "mummified_hand"}
    # ...and the three pulls came out of the bag even though all were declined.
    assert len(run.relic_grab_bag) == bag_before - 3


def test_calling_bell_populates_all_three_before_offering_any():
    """RewardsSet.GenerateWithoutOffering populates every reward first and
    only then offers them (RewardsSet.cs:125-147, 153-159), so a relic taken
    from the screen cannot change what the later slots pulled."""
    from sts2_rl.driver import DecisionKind as DK

    run = fresh_run()
    pulls: list[int] = []
    original = run.pull_relic_from_front

    def counting_pull(*a, **kw):
        pulls.append(len(seen))
        return original(*a, **kw)

    run.pull_relic_from_front = counting_pull
    seen = _skipping_driver(run)
    run.add_relic("calling_bell")
    relic_offers = [r for r in seen if r.kind is DK.REWARD_RELIC]
    assert len(relic_offers) == 3
    # All three pulls happened before the first offer was asked for.
    assert pulls == [0, 0, 0]


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



def test_lava_lamp_does_not_upgrade_outside_a_combat_room():
    """LavaLamp.cs:66-69 — `if (!(RunState.CurrentRoom is CombatRoom)) return
    false;`. An event's card reward is generated in an EventRoom, so the relic
    must not touch it even though no damage was taken."""
    relic = make_relic("lava_lamp")
    run = fresh_run()
    run.add_relic(relic)
    relic.after_room_entered(run, None, RoomType.EVENT)
    cards = [make_card("strike"), make_card("defend")]
    relic.modify_card_reward_options_late(run, cards)
    assert [c.upgrade_level for c in cards] == [0, 0]


def test_fresnel_lens_enchants_reward_options_and_deck_adds_with_nimble():
    """FresnelLens.cs:23-31 (TryModifyCardRewardOptionsLate) and :40-53
    (TryModifyCardBeingAddedToDeck) both enchant with Nimble 2. The port
    implemented neither: its docstring claimed the sim had no enchantments and
    no deck edits, and both halves of that premise were false."""
    from sts2_rl.enchantments import NimbleEnchantment

    relic = make_relic("fresnel_lens")
    run = fresh_run()
    run.add_relic(relic)

    defend = make_card("defend")
    assert NimbleEnchantment.can_enchant(defend)     # gains_block
    relic.modify_card_reward_options_late(run, [defend])
    assert defend.enchantment is not None
    assert defend.enchantment.id == "nimble"
    assert defend.enchantment.amount == 2

    added = run.add_card(make_card("defend"))
    assert added.enchantment is not None and added.enchantment.id == "nimble"

    # Nimble.CanEnchant requires CardModel.GainsBlock, so a Strike is skipped.
    strike = make_card("strike")
    relic.modify_card_reward_options_late(run, [strike])
    assert strike.enchantment is None


# ── CardCreationFlags.IsCardReward (relic/_reward_late_pass) ─────────────


def test_dingy_rug_adds_the_colorless_pool_to_a_card_reward():
    """DingyRug.cs:13-36 — ModifyCardRewardCreationOptions appends the
    Colorless pool. The relic was a documented stub; the sim had no
    creation-options hook and no CardCreationFlags at all."""
    from sts2_rl.cards.pool import COLORLESS_POOL

    run = fresh_run()
    run.add_relic(make_relic("dingy_rug"))
    seen = set()
    for _ in range(40):
        seen.update(c.id for c in create_reward_cards(
            run, RarityOddsType.REGULAR, is_card_reward=True))
    assert seen & set(COLORLESS_POOL)


def test_dingy_rug_leaves_a_non_reward_generation_alone():
    """`if (!options.Flags.HasFlag(CardCreationFlags.IsCardReward)) return
    options;` (DingyRug.cs:23-26) — a relic or event card generation is not a
    card reward."""
    from sts2_rl.cards.pool import COLORLESS_POOL

    run = fresh_run()
    run.add_relic(make_relic("dingy_rug"))
    seen = set()
    for _ in range(40):
        seen.update(c.id for c in create_reward_cards(
            run, RarityOddsType.REGULAR))          # is_card_reward defaults False
    assert not (seen & set(COLORLESS_POOL))


def test_silver_crucible_does_not_spend_a_charge_on_a_non_reward():
    """SilverCrucible.cs:104-107 — the same IsCardReward gate. Without it a
    Lost Coffer or event generation burned one of the two upgrades."""
    relic = make_relic("silver_crucible")
    run = fresh_run()
    run.add_relic(relic)
    create_reward_cards(run, RarityOddsType.REGULAR)          # not a reward
    assert relic.times_used == 0
    create_reward_cards(run, RarityOddsType.REGULAR, is_card_reward=True)
    assert relic.times_used == 1


def test_silken_tress_does_not_spend_itself_on_a_non_reward():
    """SilkenTress.cs:53-56 — the same gate on its one-shot."""
    relic = make_relic("silken_tress")
    run = fresh_run()
    run.add_relic(relic)
    create_reward_cards(run, RarityOddsType.REGULAR)
    assert relic.is_used is False
    create_reward_cards(run, RarityOddsType.REGULAR, is_card_reward=True)
    assert relic.is_used is True


# ── relic/_undo_clamp: the pickup effect belongs to the relic ────────────


def test_big_mushroom_gains_its_max_hp_on_pickup():
    """relic/big_mushroom. BigMushroom.cs:24-28 is the relic's own
    AfterObtained. The port implemented none, justifying it with "RunState has
    no run-level AfterObtained dispatch" — which is false: RunState.add_relic
    calls it, and the sibling relic from the same event uses it."""
    run = fresh_run()
    before = run.max_hp
    run.add_relic(make_relic("big_mushroom"))
    assert run.max_hp == before + 20


def test_distinguished_cape_loses_max_hp_before_adding_its_cards():
    """relic/distinguished_cape/g1. DistinguishedCape.cs:30-41 loses 9 Max HP
    FIRST and then adds 3 Apparitions. The port attributed the −9 to the Vakuu
    option, but `ThatDecreasesMaxHp` (EventOption.cs:194-197) is
    `ThatWillKillPlayerIf` — a red-flash UI flag that applies no HP."""
    run = fresh_run()
    before_max, before_deck = run.max_hp, len(run.deck)
    run.add_relic(make_relic("distinguished_cape"))
    assert run.max_hp == before_max - 9
    assert len(run.deck) == before_deck + 3
    assert sum(1 for c in run.deck if c.id == "apparition") == 3


def test_the_vakuu_cape_option_does_not_double_the_max_hp_loss():
    """The event applied its own −9 on top of nothing, which happened to total
    the right number; now that the relic carries it, the option must not."""
    from sts2_rl.events import make_event

    run = fresh_run()
    before = run.max_hp
    event = make_event("vakuu", run)
    option = event._cape_option()
    option.on_chosen()
    assert run.max_hp == before - 9        # once, not twice


def test_whispering_earring_plays_are_auto_plays():
    """relic/whispering_earring/g2. WhisperingEarring.cs:78-80 spends the card's
    resources and then calls `CardCmd.AutoPlay(..., AutoPlayType.Default,
    skipXCapture: true)`, so the resulting CardPlay carries IsAutoPlay. The
    port called the MANUAL `play_card`, so every `is_auto_play` listener —
    Tuning Fork's counter among them — counted these as real plays."""
    seen = []

    class _Spy(Relic):
        id = "spy2"
        name = "Spy2"

        def on_card_played(self, card, is_auto_play=False):
            seen.append(is_auto_play)

    from sts2_rl.cards import make_card

    relic = make_relic("whispering_earring")
    cs = CombatState(starting_deck=[make_card("strike") for _ in range(10)],
                     rng=random.Random(0), relics=[relic, _Spy()])
    # The relic auto-plays during the AutoPrePlay phase of turn 1, which
    # CombatState's construction already ran.
    assert seen and all(seen)          # every one of them auto


def test_a_doubled_skill_that_kills_still_runs_its_second_replay():
    """relic/tuning_fork/g1's residue. CardModel.cs's Replay loop returns early
    on `Owner.Creature.IsDead` alone (:1950 and :1960) — the PLAYER dying. The
    sim also broke on `_all_enemies_dead()`, so a Throwing-Axe-doubled Skill
    that killed on iteration 0 counted ONCE in the game's terms and zero more
    times in the sim's; Tuning Fork's SkillsPlayed is run-scoped, so the drift
    never washes out."""
    plays = []

    class _Counter(Relic):
        id = "counter"
        name = "Counter"

        def on_card_played(self, card, is_auto_play=False):
            plays.append(card.id)

    cs = fresh(relics=[make_relic("throwing_axe"), _Counter()])
    cs.enemy.hp = 1
    cs.player.energy = 10
    defend = make_card("defend")
    cs.player.hand.append(defend)
    # Kill with an attack first so the Skill's own play lands in the ending
    # window, then play the doubled Skill.
    DamageCmd.deal(cs.hooks, cs.enemy, 50, dealer=cs.player,
                   props=DamageProps.CARD)
    plays.clear()
    cs.play_card(cs.player.hand.index(defend))
    assert plays == ["defend", "defend"]     # both Replay iterations counted
