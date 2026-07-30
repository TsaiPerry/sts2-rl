"""The last five LIVE Tier 1 mechanisms.

relic/wongos_mystery_ticket/TryModifyRewards, relic/lizard_tail/g3,
power/burrowed/AfterBlockBroken, enchantment/EG2,
event/war_historian_repy/g1.
"""
from __future__ import annotations

import random

import pytest

from sts2_rl import CombatState, make_relic
from sts2_rl.cards import make_card
from sts2_rl.rooms import RoomType
from sts2_rl.run import RunState


# ══════════════════════════════════════════════════════════════════════════
# relic/wongos_mystery_ticket — the hooks fire on the FINAL act's boss too
# ══════════════════════════════════════════════════════════════════════════

def _ripe_ticket(final_act: bool = False, combats: int = 5, gave: bool = False):
    run = RunState(rng=random.Random(0))
    run._is_final_act = final_act
    run.add_relic("wongos_mystery_ticket")
    ticket = next(r for r in run.relics if r.id == "wongos_mystery_ticket")
    ticket.combats_finished = combats
    ticket.gave_relic = gave
    run.offer_relic = lambda relic: None
    return run, ticket


def test_wongos_ticket_pays_on_the_final_acts_boss():
    """`RewardsSet.WithRewardsFromRoom` returns early on the run's last boss
    (RewardsSet.cs:85-91) WITHOUT the room's own gold/potion/card rewards — but
    it has already set `Room`, and the separate GenerateWithoutOffering still
    runs `Hook.ModifyRewards` over the (empty) list. AmethystAubergine.cs:33-35's
    explicit final-act guard would be dead code otherwise. So a ripe ticket pays
    its three relics there."""
    from sts2_rl.rewards import generate_combat_rewards

    run, ticket = _ripe_ticket(final_act=True)
    rewards = generate_combat_rewards(run, RoomType.BOSS)
    assert rewards.room == RoomType.BOSS
    assert len(rewards.relics) == 3
    assert ticket.gave_relic is True


def test_wongos_ticket_pays_on_a_non_final_boss():
    from sts2_rl.rewards import generate_combat_rewards

    run, ticket = _ripe_ticket(final_act=False)
    rewards = generate_combat_rewards(run, RoomType.BOSS)
    assert len(rewards.relics) == 3


@pytest.mark.parametrize("combats,expected", [(4, 0), (5, 3), (6, 3)])
def test_wongos_ticket_countdown(combats, expected):
    """`5 - CombatsFinished > 0` -> return (WongosMysteryTicket.cs:80-104)."""
    from sts2_rl.rewards import generate_combat_rewards

    run, _ = _ripe_ticket(combats=combats)
    rewards = generate_combat_rewards(run, RoomType.MONSTER)
    assert len(rewards.relics) == expected


def test_wongos_ticket_pays_once():
    """`GaveRelic` is IsUsedUp."""
    from sts2_rl.rewards import generate_combat_rewards

    run, _ = _ripe_ticket(gave=True)
    assert len(generate_combat_rewards(run, RoomType.MONSTER).relics) == 0


def test_wongos_ticket_rides_an_elite_screen_alongside_its_own_relic():
    from sts2_rl.rewards import generate_combat_rewards

    run, _ = _ripe_ticket()
    assert len(generate_combat_rewards(run, RoomType.ELITE).relics) == 4


def test_wongos_ticket_ignores_a_custom_screen():
    """WongosMysteryTicket.cs:86's `!(room is CombatRoom)` — a custom reward set
    carries no room, so the ticket never pays out on one and keeps its charge."""
    from sts2_rl.rewards import CombatRewards, apply_reward_modifiers

    run, ticket = _ripe_ticket()
    custom = CombatRewards(room_type=RoomType.MONSTER)     # room stays None
    apply_reward_modifiers(run, custom)
    assert custom.relics == []
    assert ticket.gave_relic is False


# ══════════════════════════════════════════════════════════════════════════
# relic/lizard_tail — ShouldDieLate is a PURE predicate
# ══════════════════════════════════════════════════════════════════════════

def _clay_combat(relic_ids=(), seed: int = 0) -> CombatState:
    from sts2_rl.monsters import Encounter
    from sts2_rl.monsters.overgrowth.slimes import LeafSlimeS
    return CombatState(rng=random.Random(seed),
                       starting_deck=[make_card("strike") for _ in range(5)],
                       encounter=Encounter("t", [LeafSlimeS]),
                       relics=[make_relic(r) for r in relic_ids])


def test_lizard_tail_should_die_late_is_pure():
    """`LizardTail.ShouldDieLate` (LizardTail.cs:40-51) reads `WasUsed` and
    returns; the charge is spent in `AfterPreventingDeath` (:53-59, `WasUsed =
    true` then the heal). The port mutated `_used` inside the predicate, so any
    caller that queried `should_die` without going on to the prevention path
    burned the relic for nothing."""
    relic = make_relic("lizard_tail")
    cs = _clay_combat()
    cs.relics.append(relic)
    relic.attach(cs)
    for _ in range(3):
        assert relic.should_die_late(cs.player) is False
    assert relic.is_used_up is False, "querying must not spend the charge"


def test_lizard_tail_spends_its_charge_when_it_actually_prevents():
    relic = make_relic("lizard_tail")
    cs = _clay_combat()
    cs.relics.append(relic)
    relic.attach(cs)
    cs.player.hp = 1
    from sts2_rl.cmds import DamageCmd
    DamageCmd.deal(cs.hooks, cs.player, 99, dealer=cs.enemies[0])
    assert relic.is_used_up is True
    # `Math.Max(1, MaxHp * Heal/100)` — the creature is healed off 0, not floored.
    assert cs.player.hp > 0
    assert cs.player.is_dead is False


def test_lizard_tail_only_prevents_once():
    relic = make_relic("lizard_tail")
    cs = _clay_combat()
    cs.relics.append(relic)
    relic.attach(cs)
    from sts2_rl.cmds import DamageCmd
    DamageCmd.deal(cs.hooks, cs.player, 999, dealer=cs.enemies[0])
    assert relic.is_used_up is True
    DamageCmd.deal(cs.hooks, cs.player, 999, dealer=cs.enemies[0])
    assert cs.player.is_dead is True


def test_lizard_tail_ignores_another_creatures_death():
    """`creature != base.Owner.Creature -> return true`."""
    relic = make_relic("lizard_tail")
    cs = _clay_combat()
    cs.relics.append(relic)
    relic.attach(cs)
    assert relic.should_die_late(cs.enemies[0]) is True
    assert relic.is_used_up is False


# ══════════════════════════════════════════════════════════════════════════
# power/burrowed — the stun is CreatureCmd.Stun, not a bare state force
# ══════════════════════════════════════════════════════════════════════════

def _tunneler_combat(seed: int = 0):
    from sts2_rl.monsters import Encounter
    from sts2_rl.monsters.hive.tunneler import Tunneler
    cs = CombatState(rng=random.Random(seed),
                     starting_deck=[make_card("strike") for _ in range(5)],
                     encounter=Encounter("t", [Tunneler]))
    return cs, cs.enemies[0]


def test_burrowed_block_break_installs_the_synthetic_stun_state():
    """BurrowedPower.cs:28-34, in order: `tunneler.GetStunned()`, then
    `CreatureCmd.Stun(Owner, tunneler.StillDizzyMove, "BITE_MOVE")`, then
    `PowerCmd.Remove<BurrowedPower>`.

    The middle call is the one that changes state, and it goes through
    `Creature.StunInternal` — a REAL synthetic move with
    `MustPerformOnceBeforeTransitioning = true` and `FollowUpStateId =
    "BITE_MOVE"` (Creature.cs:524-544). The port called the monster's own
    `get_stunned()`, which forced the registered DIZZY_MOVE state and so carried
    no pin: the machine could transition away before the stunned turn was ever
    performed, and the Tunneler would not lose its turn at all.

    Note the registered `DIZZY_MOVE` state (Tunneler.cs:75) has no incoming edge
    in the source's own machine — BITE→BURROW→BELOW→BELOW is the whole graph —
    so the synthetic state is the only way in."""
    from sts2_rl.cmds import BlockCmd, DamageCmd
    from sts2_rl.monsters.state_machine import STUN_STATE_ID
    from sts2_rl.powers import BurrowedPower

    cs, tun = _tunneler_combat()
    tun._burrow(cs._ctx())
    assert "burrowed" in tun.powers
    assert tun.block > 0
    DamageCmd.deal(cs.hooks, tun, tun.block + 5, dealer=cs.player,
                   card=make_card("strike"))
    assert "burrowed" not in tun.powers        # the power was removed
    assert tun.block == 0                      # AfterRemoved: LoseBlock(all)
    assert tun.stunned is True
    assert tun.machine.current.id == STUN_STATE_ID
    assert tun.machine.current.must_perform_once_before_transitioning is True
    assert tun.machine.current.follow_up.id == "BITE_MOVE"


def test_burrowed_get_stunned_is_presentation_only():
    """The entry claimed C# "stuns first and removes the power SECOND ... so C#'s
    stun happens while the block is still there and the sim's after it is gone".
    THAT PREMISE IS WRONG ABOUT THE SOURCE (trap (c)): `AfterBlockBroken` fires on
    `Block <= 0 && blockedDamage > 0`, so the block has ALREADY been spent
    absorbing the hit in both engines — it is 0 when the hook runs either way, and
    `AfterRemoved`'s `LoseBlock(999999999)` is belt-and-braces. What the order
    does decide is only that `Tunneler.GetStunned()` (IsStunned + TriggerAnim,
    read by two animator predicates and nothing else) runs before the removal.
    """
    from sts2_rl.cmds import DamageCmd

    cs, tun = _tunneler_combat()
    tun._burrow(cs._ctx())
    seen: list = []
    original = type(tun).get_stunned

    def spy(self):
        seen.append(self.block)
        return original(self)

    type(tun).get_stunned = spy
    try:
        DamageCmd.deal(cs.hooks, tun, tun.block + 5, dealer=cs.player,
                       card=make_card("strike"))
    finally:
        type(tun).get_stunned = original
    # Zero in the sim AND zero in the game: the absorption already spent it.
    assert seen == [0]


# ══════════════════════════════════════════════════════════════════════════
# event/war_historian_repy — Hook.ModifyNextEvent
# ══════════════════════════════════════════════════════════════════════════

def test_lantern_key_narrows_act_three_unknown_nodes():
    """LanternKey.cs:21-27 — outside act index 2 the set passes through; inside
    it, it is REPLACED by {Event}. Already ported; re-pinned so the pair cannot
    drift apart."""
    from sts2_rl.rooms import RoomType

    card = make_card("lantern_key")
    run = RunState(rng=random.Random(0))
    run.act_index = 1
    passthrough = {RoomType.MONSTER, RoomType.SHOP}
    assert card.modify_unknown_map_point_room_types(run, passthrough) == passthrough
    run.act_index = 2
    assert card.modify_unknown_map_point_room_types(run, passthrough) == {
        RoomType.EVENT}


def test_lantern_key_redirects_the_next_act_three_event():
    """LanternKey.cs:29-36 — `ModifyNextEvent` returns
    `ModelDb.Event<WarHistorianRepy>()` when `CurrentActIndex == 2`. The
    dispatcher is `Hook.cs:1830-1836` and its ONE call site is
    `ActModel.PullNextEvent` (ActModel.cs:437-443)."""
    card = make_card("lantern_key")
    run = RunState(rng=random.Random(0))
    run.act_index = 1
    assert card.modify_next_event(run, "brain_leech") == "brain_leech"
    run.act_index = 2
    assert card.modify_next_event(run, "brain_leech") == "war_historian_repy"


def _walk_to_an_event(run):
    """Walk the act until a room resolves to EVENT; return that resolution."""
    from sts2_rl.rooms import RoomType

    while not run.at_act_end:
        point = run.travelable_points()[0]
        resolution = run.enter_point(point)
        if resolution.room_type == RoomType.EVENT and resolution.event is not None:
            return resolution
    return None


def test_the_next_event_hook_is_dispatched_over_the_deck():
    """`PullNextEvent` is EnsureNextEventIsValid -> Hook.ModifyNextEvent ->
    `AddVisitedEvent(eventModel)` (ActModel.cs:437-443), so the hook sits between
    the pull and the visited-set add and the VISITED event is the MODIFIED one.
    Holding a Lantern Key in act index 2 therefore turns the node into War
    Historian Repy — an event whose own `IsAllowed` is False, which is exactly why
    the injection exists."""
    run = RunState(rng=random.Random(0))
    run.start_run(acts=["overgrowth"])
    run._act_index = 2 if hasattr(run, "_act_index") else run.act_index
    run.act_index = 2
    run.add_card(make_card("lantern_key"))
    resolution = _walk_to_an_event(run)
    assert resolution is not None, "no event room on this walk"
    assert resolution.event.id == "war_historian_repy"
    assert "war_historian_repy" in run.visited_event_ids


def test_without_the_key_the_event_is_untouched():
    run = RunState(rng=random.Random(0))
    run.start_run(acts=["overgrowth"])
    run.act_index = 2
    resolution = _walk_to_an_event(run)
    assert resolution is not None
    assert resolution.event.id != "war_historian_repy"


# ══════════════════════════════════════════════════════════════════════════
# enchantment/EG2 — ModifyShuffleOrder is dispatched in PILE order
# ══════════════════════════════════════════════════════════════════════════

def test_perfect_fit_still_goes_on_top_after_a_reshuffle():
    """The control: PerfectFit.cs:10-16, one enchanted card."""
    from sts2_rl.enchantments import make_enchantment

    card = make_card("pommel_strike")
    make_enchantment("perfect_fit").attach(card)
    cs = CombatState(rng=random.Random(0),
                     starting_deck=[card] + [make_card("defend") for _ in range(4)])
    cs.player.hand.remove(card)
    cs.player.draw_pile.clear()
    cs.player.discard_pile.append(card)
    cs.player.reshuffle_discard_into_draw()
    assert cs.player.draw_pile[-1] is card


def test_perfect_fit_skips_the_initial_shuffle():
    """`if (!isInitialShuffle && ...)` — the combat-start
    RandomizeOrderInternal dispatch (CardPile.cs:73) is skipped."""
    from sts2_rl.enchantments import make_enchantment

    ench = make_enchantment("perfect_fit")
    card = make_card("pommel_strike")
    ench.attach(card)
    cards = [make_card("defend"), card, make_card("strike")]
    order = list(cards)
    ench.modify_shuffle_order(None, order, is_initial_shuffle=True)
    assert order == cards                      # untouched
    ench.modify_shuffle_order(None, order, is_initial_shuffle=False)
    assert order[-1] is card                   # top of the sim's pile


def test_the_later_card_in_the_discard_wins_the_shuffle():
    """The residual EG2 recorded. `Hook.ModifyShuffleOrder` listeners are
    re-derived per dispatch from the piles (CombatState.cs:449-467, the
    enchantment added at :462-465), and `CardPileCmd.Shuffle` fires the hook while
    the DISCARD still holds all of its cards (only drawPile entries are removed,
    CardPileCmd.cs:878-881). So with a card and its copy both carrying Perfect
    Fit, the one LATER IN THE DISCARD fires last and ends on top.

    The sim dispatched in REGISTRATION order, so a mid-combat copy always won."""
    from sts2_rl.cards.base import create_clone
    from sts2_rl.cmds import CardPileCmd
    from sts2_rl.enchantments import make_enchantment

    original = make_card("pommel_strike")
    make_enchantment("perfect_fit").attach(original)
    cs = CombatState(rng=random.Random(0),
                     starting_deck=[original]
                                   + [make_card("defend") for _ in range(4)])
    cs.player.hand.remove(original)
    cs.player.draw_pile.clear()
    cs.player.discard_pile.clear()

    clone = create_clone(original)
    # Discard order [clone, original]: the ORIGINAL is later, so it must win.
    CardPileCmd.add_to_discard(cs.hooks, cs.player, clone)
    cs.player.discard_pile.remove(clone)
    cs.player.discard_pile.append(clone)
    cs.player.discard_pile.append(original)
    assert clone.enchantment is not None and clone.enchantment is not original.enchantment

    cs.player.reshuffle_discard_into_draw()
    assert cs.player.draw_pile[-1] is original, "the later discard entry must win"


def test_the_earlier_card_loses_when_the_order_is_reversed():
    """The same setup with the discard order flipped — [original, clone] — must
    put the CLONE on top, which is what proves the key is pile position and not
    registration index."""
    from sts2_rl.cards.base import create_clone
    from sts2_rl.cmds import CardPileCmd
    from sts2_rl.enchantments import make_enchantment

    original = make_card("pommel_strike")
    make_enchantment("perfect_fit").attach(original)
    cs = CombatState(rng=random.Random(0),
                     starting_deck=[original]
                                   + [make_card("defend") for _ in range(4)])
    cs.player.hand.remove(original)
    cs.player.draw_pile.clear()
    cs.player.discard_pile.clear()

    clone = create_clone(original)
    CardPileCmd.add_to_discard(cs.hooks, cs.player, clone)
    cs.player.discard_pile.remove(clone)
    cs.player.discard_pile.append(original)
    cs.player.discard_pile.append(clone)

    cs.player.reshuffle_discard_into_draw()
    assert cs.player.draw_pile[-1] is clone
