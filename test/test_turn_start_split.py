"""The turn-start split: four C# hooks that the sim ran as two.

`power/_side_turn_slot` and the turn_structure seam both come down to this. A
player's turn start runs, in CombatManager order:

    Creature.BeforeTurnStart          (the per-turn card-cost reset)
    Hook.BeforeSideTurnStart          CombatManager.cs:458   <- was missing
    enemy PrepareForNextTurn          :478-484
    Creature.AfterTurnStart / clear   :492-499
    Hook.AfterBlockCleared            :500-507
    SetupPlayerTurn:
        ModifyMaxEnergy / ShouldPlayerResetEnergy / AfterEnergyReset
        Hook.BeforeHandDraw           :653                   = on_player_turn_start
        Hook.ModifyHandDraw + draw    :655-673
        Hook.AfterPlayerTurnStart     :675                   = on_player_turn_started
    Hook.AfterSideTurnStart           :522                   <- was missing
    orb queue, then PlayerTurnPhase.AutoPrePlay

The sim had only the two marked slots, so `on_player_turn_start` carried
BeforeSideTurnStart's 18 listeners as well as BeforeHandDraw's, and
`on_player_turn_started` carried AfterSideTurnStart's 18 as well as
AfterPlayerTurnStart's. 50 listeners moved. The whole-pipeline order is pinned
in test/test_hook_order.py::TestTurnStructureOrder; this file pins the
population and the behaviours that actually changed.
"""
from __future__ import annotations

import random

import pytest

from sts2_rl.cards import make_card
from sts2_rl.cmds import PowerCmd
from sts2_rl.combat import CombatState
from sts2_rl.monsters import Encounter
from sts2_rl.relics import make_relic


def fresh(**kw) -> CombatState:
    return CombatState(rng=random.Random(0), **kw)


# ── which slot each unit landed on ───────────────────────────────────────

# (unit id, factory, the sim slot == the C# hook it overrides). Every row was
# read off the C# `public override` — see the mechanism's audit record.
RELIC_SLOTS = [
    # Hook.BeforeSideTurnStart (CombatManager.cs:458)
    ("bag_of_marbles", "before_side_turn_start"),
    ("red_mask", "before_side_turn_start"),
    ("kunai", "before_side_turn_start"),
    ("shuriken", "before_side_turn_start"),
    ("orichalcum", "before_side_turn_start"),
    ("pocketwatch", "before_side_turn_start"),
    ("velvet_choker", "before_side_turn_start"),
    # Hook.BeforeHandDraw (:653) — the slot on_player_turn_start always was
    ("toolbox", "on_player_turn_start"),
    ("jeweled_mask", "on_player_turn_start"),
    ("blessed_antler", "on_player_turn_start"),
    ("toasty_mittens", "on_player_turn_start"),
    # Hook.AfterPlayerTurnStart (:675)
    ("bellows", "on_player_turn_started"),
    ("pendulum", "on_player_turn_started"),
    ("gambling_chip", "on_player_turn_started"),
    ("mercury_hourglass", "on_player_turn_started"),
    # ...and its LATE pass (BloodVial.cs:17 AfterPlayerTurnStartLate)
    ("blood_vial", "on_player_turn_started_late"),
    ("fake_blood_vial", "on_player_turn_started_late"),
    # Hook.AfterSideTurnStart (:522)
    ("akabeko", "after_side_turn_start"),
    ("lantern", "after_side_turn_start"),
    ("happy_flower", "after_side_turn_start"),
    ("crossbow", "after_side_turn_start"),
    ("sai", "after_side_turn_start"),
    ("seal_of_gold", "after_side_turn_start"),
    ("very_hot_cocoa", "after_side_turn_start"),
    ("paels_legion", "after_side_turn_start"),
    # AfterBlockCleared (SparklingRouge.cs:29) — never a turn-start hook
    ("sparkling_rouge", "on_block_cleared"),
]

_TURN_START_SLOTS = (
    "before_side_turn_start", "on_player_turn_start", "on_player_turn_started",
    "on_player_turn_started_late", "after_side_turn_start",
)


@pytest.mark.parametrize("relic_id,slot", RELIC_SLOTS)
def test_each_relic_listens_on_the_hook_it_overrides(relic_id, slot):
    relic = make_relic(relic_id)
    assert hasattr(relic, slot), f"{relic_id} does not implement {slot}"
    # ...and on no OTHER turn-start slot, which is what makes this a pin
    # rather than a smoke test: a unit left on both fires twice.
    for other in _TURN_START_SLOTS:
        if other != slot and not (
                slot == "on_player_turn_started_late"
                and other == "on_player_turn_started"):
            assert not hasattr(relic, other), f"{relic_id} also has {other}"


@pytest.mark.parametrize("power_id,slot", [
    ("aggression", "before_side_turn_start"),
    ("hardened_shell", "before_side_turn_start"),
    ("sloth", "before_side_turn_start"),
    ("hello_world", "on_player_turn_start"),
    # power/_side_turn_slot's two post-draw units
    ("crimson_mantle", "on_player_turn_started"),
    ("inferno", "on_player_turn_started"),
    ("demon_form", "after_side_turn_start"),
    ("poison", "after_side_turn_start"),
    ("rampart", "after_side_turn_start"),
    ("clarity", "after_side_turn_start"),
])
def test_each_power_listens_on_the_hook_it_overrides(power_id, slot):
    from sts2_rl.powers import ALL_POWERS

    cls = ALL_POWERS[power_id]
    assert hasattr(cls, slot), f"{power_id} does not implement {slot}"
    for other in _TURN_START_SLOTS:
        if other != slot:
            assert not hasattr(cls, other), f"{power_id} also has {other}"


# ── the behaviours that changed ──────────────────────────────────────────

def test_before_side_turn_start_runs_ahead_of_the_block_clear():
    """`Hook.BeforeSideTurnStart` is CombatManager.cs:458 and the clear is the
    `Creature.AfterTurnStart` pass at :492 — so a listener here still sees last
    turn's block. Bag of Marbles' Vulnerable landing before the clear is the
    same ordering the enemy's next-move roll depends on."""
    seen = []

    class _Spy:
        hook_category = 1

        def before_side_turn_start(self, player):
            seen.append(("before", player.block, len(player.hand)))

        def on_block_cleared(self, creature):
            # Fires for the enemies too (their own side's clear); only the
            # player's leg is what this pins.
            if creature is cs.player:
                seen.append(("cleared", creature.block, len(creature.hand)))

    cs = fresh()
    cs.hooks.register(_Spy())
    cs.player.block = 60          # survives the enemy's turn with some left
    cs.player.hand.clear()
    cs.end_turn()
    # Whatever the enemy's attack left of last turn's block is still standing
    # at BeforeSideTurnStart and gone by AfterBlockCleared; the hand has not
    # been drawn at either point.
    assert [tag for tag, _, _ in seen] == ["before", "cleared"]
    assert seen[0][1] > 0 and seen[1][1] == 0
    assert seen[0][2] == seen[1][2] == 0


def test_after_player_turn_start_precedes_after_side_turn_start():
    """CombatManager.cs:675 is SetupPlayerTurn's last line; :522 runs after
    SetupPlayerTurn returns. Both are post-draw, and their order is fixed."""
    seen = []

    class _Spy:
        hook_category = 1

        def on_player_turn_started(self, player):
            seen.append(("after_player", len(player.hand)))

        def after_side_turn_start(self, player):
            seen.append(("after_side", len(player.hand)))

    cs = fresh()
    cs.hooks.register(_Spy())
    cs.end_turn()
    assert seen == [("after_player", 5), ("after_side", 5)]


def test_crimson_mantle_now_fires_after_the_hand_is_drawn():
    """power/_side_turn_slot's live consequence. CrimsonMantlePower overrides
    `AfterPlayerTurnStart`, which is post-draw; the sim ran it pre-draw, so its
    self-damage could kill the player and cancel a hand draw the game had
    already made — and Hellraiser's draw-triggered auto-plays saw the block in
    the sim that the game has not granted yet."""
    from sts2_rl.powers import CrimsonMantlePower

    at_draw = []

    class _Spy:
        hook_category = 1

        def on_card_drawn(self, card, player=None):
            at_draw.append((cs.player.hp, cs.player.block))

    cs = fresh()
    cs.hooks.register(_Spy())
    PowerCmd.apply(cs.hooks, cs.player, CrimsonMantlePower, 8,
                   applier=cs.player)
    mantle = cs.player.powers["crimson_mantle"]
    mantle.self_damage = 1
    cs.player.block = 0
    at_draw.clear()
    cs.end_turn()

    # The whole 5-card draw happened BEFORE the mantle resolved: no block yet
    # and no HP lost to it at any of the five draws. Pre-draw, every one of
    # these would already carry the tick.
    assert len(at_draw) == 5
    hp_at_first_draw = at_draw[0][0]
    assert [(hp, block) for hp, block in at_draw] == [
        (hp_at_first_draw, 0)] * 5
    assert cs.player.hp == hp_at_first_draw - mantle.self_damage
    assert cs.player.block >= mantle.amount


def test_plating_grants_its_round_one_block_at_the_turn_start_not_combat_start():
    """PlatingPower.cs:41-56 uses the round-1 arm of `BeforeSideTurnStart` as a
    stand-in for combat start ("We want enemies that start with Plating to also
    start combat with block"). The sim used `on_combat_start`, one dispatch
    earlier, so a combat-start listener that reads an enemy's block saw it
    already blocked where the game shows it bare."""
    from sts2_rl.monsters.hive.slumbering_beetle import SlumberingBeetle
    from sts2_rl.powers import PlatingPower

    cs = CombatState(
        rng=random.Random(0),
        encounter=Encounter(id="one_beetle",
                            monster_classes=[SlumberingBeetle]))
    enemy = cs.enemies[0]
    plating = enemy.powers.get("plating")
    assert isinstance(plating, PlatingPower), (
        "Slumbering Beetle is the fixture because it starts with Plating")
    # By the time the player is acting, turn 1's BeforeSideTurnStart has run
    # and the block is on. The slot moved; the outcome at this point did not,
    # which is exactly why the finding was dormant.
    assert enemy.block == plating.amount
    assert not hasattr(PlatingPower, "on_combat_start")


def test_pocketwatch_snapshots_before_modify_hand_draw_reads_it():
    """Pocketwatch.cs:73-83 snapshots last turn's card count in
    BeforeSideTurnStart; ModifyHandDraw (:52-65) reads it later in the same
    turn start. Splitting the hooks must not invert that."""
    cs = fresh(relics=[make_relic("pocketwatch")])
    cs.player.hand.clear()
    cs.player.hand.append(make_card("strike"))
    cs.player.draw_pile.extend(make_card("strike") for _ in range(20))
    cs.end_turn()          # turn 2: turn-1 plays were 0, under the threshold
    assert len(cs.player.hand) == 5 + make_relic("pocketwatch").DRAW
