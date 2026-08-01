"""Tier 1's residue: the former-Tier-1 mechanisms whose remaining sites were
never proven dormant.

Rounds 6-9 closed every gap entry the records *labelled* LIVE. That left a
category the headline count cannot see: entries whose liveness is **unlabelled**
and whose mechanism is unlabelled too, so `gap_queue` counts them neither live
nor dormant. Eight of them sat under mechanisms written out in full in the
queue's Tier 1 section. Each is settled here by execution rather than by
argument — the pipeline's own lesson that staleness, not difficulty, is the
largest category.

One acceptance test per unit, named for its queue id.
"""
from __future__ import annotations

import random

import pytest

from sts2_rl import CombatState
from sts2_rl.cards import make_card
from sts2_rl.rng import RunRngSet, make_encounter_rng


# ══════════════════════════════════════════════════════════════════════════
# turn_structure/step2 — the opening RollMove is SIDE-GATED
#
#   CombatManager.AfterCreatureAdded (CombatManager.cs:858-867):
#       await creature.AfterAddedToRoom();
#       if (creature.IsEnemy && _state.CurrentSide == CombatSide.Player)
#           creature.Monster.RollMove(...);
#
# The sim rolled unconditionally in MachineMonster.__init__, so a creature
# summoned during the ENEMY side — which is every monster SUMMON move — took a
# MonsterAi draw the game does not take at that moment.
# ══════════════════════════════════════════════════════════════════════════

def _rat_combat(seed: str = "T1RAT", floor: int = 3) -> tuple[CombatState, RunRngSet]:
    from sts2_rl.monsters.underdocks.two_tailed_rat import TWO_TAILED_RATS_NORMAL
    rs = RunRngSet(seed)
    sel = make_encounter_rng(rs.seed, floor, TWO_TAILED_RATS_NORMAL.entry)
    combat = CombatState(rng=random.Random(9), rng_set=rs,
                         encounter=TWO_TAILED_RATS_NORMAL,
                         encounter_selection_rng=sel,
                         starting_deck=[make_card("strike") for _ in range(5)])
    return combat, rs


def test_step2_two_tailed_rat_is_the_witness_it_draws_at_construction():
    """The gap is only observable on a monster whose OPENING roll consumes a
    draw, i.e. one whose initial state is not already a move
    (MonsterMoveStateMachine.cs:60-63 returns before `GetNextState`). Two of
    the 83 ported MachineMonsters qualify, and Two-Tailed Rat is the one that
    also summons its own kind."""
    from sts2_rl.monsters.underdocks.two_tailed_rat import TwoTailedRat

    combat, rs = _rat_combat()
    before = rs.monster_ai.counter
    TwoTailedRat(combat.hooks, random.Random(7)).machine.roll_move(
        TwoTailedRat(combat.hooks, random.Random(7)),
        combat.combat_rng.monster_ai)
    assert rs.monster_ai.counter > before, (
        "TwoTailedRat's opening roll must cost a MonsterAi draw, or this "
        "mechanism has no witness")


def test_step2_enemy_side_summon_takes_no_monster_ai_draw():
    """`CurrentSide == Enemy`, so C# skips RollMove entirely."""
    combat, rs = _rat_combat()
    for enemy in combat.enemies:
        enemy.performed_first_move = True
        enemy.machine._performed_first_move = True

    rat = combat.enemies[0]
    rat.turns_until_summonable = 0
    combat.current_side = "enemy"

    before = rs.monster_ai.counter
    rat._call_for_backup(combat._ctx())
    assert rs.monster_ai.counter == before

    spawn = combat.enemies[-1]
    assert spawn is not rat
    assert not spawn.has_rolled_a_move
    assert spawn._current_move.id == "UNSET_MOVE"


def test_step2_the_unrolled_spawn_is_rolled_by_the_next_pass_in_list_order():
    """C# calls PrepareForNextTurn on EVERY enemy (CombatManager.cs:478-484)
    and lets the machine's own guard decide, so the spawn is rolled here — at
    its position in the enemy list, not ahead of its siblings."""
    combat, rs = _rat_combat()
    for enemy in combat.enemies:
        enemy.performed_first_move = True
        enemy.machine._performed_first_move = True
    rat = combat.enemies[0]
    rat.turns_until_summonable = 0
    combat.current_side = "enemy"
    rat._call_for_backup(combat._ctx())
    spawn = combat.enemies[-1]

    combat.current_side = "player"
    before = rs.monster_ai.counter
    combat._roll_enemy_intents()

    # one draw per enemy, the spawn included — where the old code drew for the
    # spawn at summon time and then skipped it here.
    assert rs.monster_ai.counter - before == len(combat.enemies)
    assert spawn.has_rolled_a_move
    assert spawn._current_move.id != "UNSET_MOVE"


def test_step2_player_side_spawn_still_rolls_immediately():
    """The other arm of the gate: a summon on the player's side (a card, a
    relic, a power) IS rolled by AfterCreatureAdded, exactly where the sim's
    construction-time roll used to sit. This arm must not regress."""
    from sts2_rl.monsters.glory import FABRICATOR_NORMAL
    from sts2_rl.monsters.glory.fabricator import _AGGRO_SPAWNS

    rs = RunRngSet("T1FAB")
    combat = CombatState(rng=random.Random(5), rng_set=rs,
                         encounter=FABRICATOR_NORMAL,
                         starting_deck=[make_card("strike") for _ in range(5)])
    fab = combat.enemies[0]
    assert combat.current_side == "player"
    fab._spawn_bot(combat._ctx(), _AGGRO_SPAWNS)

    bot = [e for e in combat.enemies if e is not fab][0]
    assert bot.has_rolled_a_move


def test_step2_starting_enemies_are_rolled_by_the_setup_loop():
    """StartCombatInternal's AfterCreatureAdded loop (CombatManager.cs:394-398)
    runs before Hook.BeforeCombatStart, so every starting enemy has an intent
    by the time a combat-start listener can look at one."""
    combat, _ = _rat_combat()
    assert all(e.has_rolled_a_move for e in combat.enemies)
    assert all(e._current_move.id != "UNSET_MOVE" for e in combat.enemies)


# ══════════════════════════════════════════════════════════════════════════
# power/free_attack — the hook it declares, and the pile guard on both hooks
#
#   FreeAttackPower.cs:43  public override async Task BeforeCardPlayed(...)
#   FreeAttackPower.cs:26-39 / :48-59  card.Pile?.Type is Hand or Play
#
# The port consumed its stack in `on_energy_spent`, which fires ONCE per
# logical play — outside the play-count loop that Hook.BeforeCardPlayed sits
# inside (CardModel.cs:1929) — and neither hook carried the pile guard.
# ══════════════════════════════════════════════════════════════════════════

def _fa_combat(hand=("strike",), stacks: int = 3, seed: int = 0):
    from sts2_rl.monsters.overgrowth.slimes import LeafSlimeS
    from sts2_rl.monsters import Encounter
    from sts2_rl.powers import FreeAttackPower

    cs = CombatState(rng=random.Random(seed),
                     starting_deck=[make_card("strike") for _ in range(5)],
                     encounter=Encounter("test_fa", [LeafSlimeS]))
    cs.player.hand.clear()
    for cid in hand:
        card = make_card(cid)
        card.combat = cs
        cs.hooks.register(card)
        cs.player.hand.append(card)
    from sts2_rl.cmds import PowerCmd
    PowerCmd.apply(cs.hooks, cs.player, FreeAttackPower, stacks)
    return cs


def test_free_attack_consumes_one_stack_per_replay_iteration():
    """A doubled Attack is TWO CardPlays, so BeforeCardPlayed fires twice and
    `PowerCmd.Decrement` runs twice."""
    cs = _fa_combat(stacks=3)
    card = cs.player.hand[0]
    card.base_replay_count = 1          # Hidden Gem: playCount 2

    cs.player.energy = 3
    cs.play_card(0, 0)

    assert cs.player.powers["free_attack"].amount == 1, (
        "one stack per CardPlay: 3 - 2 = 1")


def test_free_attack_consumes_one_stack_for_a_single_play():
    cs = _fa_combat(stacks=3)
    cs.player.energy = 3
    cs.play_card(0, 0)
    assert cs.player.powers["free_attack"].amount == 2


def test_free_attack_pile_guard_keeps_a_draw_pile_attack_costed():
    """The cost hook is queried for cards in every pile. Without
    FreeAttackPower.cs:26-39's switch a draw-pile Attack reads as free."""
    cs = _fa_combat(hand=(), stacks=3)
    buried = make_card("strike")
    buried.combat = cs
    cs.hooks.register(buried)
    cs.player.draw_pile.append(buried)

    assert cs.player.pile_type_of(buried) == "draw"
    assert cs.hooks.modify_card_energy_cost(buried, buried.energy_cost) == \
        buried.energy_cost

    in_hand = make_card("strike")
    in_hand.combat = cs
    cs.hooks.register(in_hand)
    cs.player.hand.append(in_hand)
    assert cs.player.pile_type_of(in_hand) == "hand"
    assert cs.hooks.modify_card_energy_cost(in_hand, in_hand.energy_cost) == 0


def test_pile_type_of_reports_play_limbo_not_discard():
    """`_playing_card` is the sim's PileType.Play, and the card is physically
    in the discard list at the same time — membership order matters."""
    cs = _fa_combat(stacks=1)
    card = cs.player.hand[0]
    cs.player.hand.remove(card)
    cs.player.discard_pile.append(card)
    cs.player._playing_card = card
    assert cs.player.pile_type_of(card) == "play"
    cs.player._playing_card = None
    assert cs.player.pile_type_of(card) == "discard"


# ══════════════════════════════════════════════════════════════════════════
# enchantment/swift/EG1 — the EnchantmentModel.OnPlay slot
#
#   CardModel.cs:1931  await OnPlay(...)                 the card's own effect
#   CardModel.cs:1937-1945  await Enchantment.OnPlay(...)
#   CardModel.cs:1959  Hook.AfterCardPlayed
#
# EG1's machinery was built in round 8 and Corrupted/Sown were moved onto it;
# the record says Swift was left behind on `on_card_played`. It was not — the
# move landed too and the entry is stale. Verified by the ORDER the entry named
# as its observable, not by the method's name.
# ══════════════════════════════════════════════════════════════════════════

def test_swift_draws_before_the_after_card_played_listeners():
    """The record's own observable: at the 10-card hand cap, Music Box's
    AfterCardPlayed copy lands BEFORE Swift's draw in the sim and AFTER it in
    the game, so a near-full hand keeps a different card in each engine.
    Swift on the direct OnPlay slot draws first, as C# does."""
    from sts2_rl.monsters import Encounter
    from sts2_rl.monsters.overgrowth.slimes import LeafSlimeS
    from sts2_rl.enchantments import make_enchantment
    from sts2_rl.relics import make_relic

    order: list[str] = []

    cs = CombatState(rng=random.Random(3),
                     starting_deck=[make_card("strike") for _ in range(10)],
                     encounter=Encounter("test_swift", [LeafSlimeS]),
                     relics=[make_relic("music_box")])
    cs.player.hand.clear()

    attack = make_card("strike")
    attack.combat = cs
    attack.enchantment = make_enchantment("swift")
    attack.enchantment.amount = 3
    attack.enchantment.card = attack
    attack.enchantment.combat = cs
    cs.hooks.register(attack)
    cs.hooks.register(attack.enchantment)
    cs.player.hand.append(attack)

    real_draw = type(cs.player)._draw
    box = [r for r in cs.relics if r.id == "music_box"][0]
    real_box = type(box).on_card_played

    def spy_draw(self, *a, **k):
        order.append("swift_draw")
        return real_draw(self, *a, **k)

    def spy_box(self, card, is_auto_play=False):
        before = len(self.player.hand)
        out = real_box(self, card, is_auto_play)
        if len(self.player.hand) != before:
            order.append("music_box_copy")
        return out

    type(cs.player)._draw = spy_draw
    type(box).on_card_played = spy_box
    try:
        cs.player.energy = 3
        cs.play_card(0, 0)
    finally:
        type(cs.player)._draw = real_draw
        type(box).on_card_played = real_box

    assert "swift_draw" in order and "music_box_copy" in order, order
    assert order.index("swift_draw") < order.index("music_box_copy"), (
        f"Swift's OnPlay must precede every AfterCardPlayed listener; got {order}")


def test_swift_is_on_the_direct_onplay_slot_not_after_card_played():
    """The structural half of the same finding: Swift must not be reachable
    through the AfterCardPlayed dispatch at all."""
    from sts2_rl.enchantments import SwiftEnchantment

    assert "on_play" in vars(SwiftEnchantment)
    assert "on_card_played" not in vars(SwiftEnchantment)


# ══════════════════════════════════════════════════════════════════════════
# power/thorns/BeforeDamageReceived — the reflect has a DEALER
#
#   ThornsPower.cs:22
#     CreatureCmd.Damage(ctx, dealer, Amount,
#                        Unpowered|SkipHurtAnim, base.Owner, null)
#                                                ^^^^^^^^^^ the dealer
#
# The port left it None, so `on_damage_dealt` (Hook.AfterDamageGiven) never
# fired for a reflect and CreatureCmd.cs:242-245's dead-dealer return had
# nothing to test. Same omission in ConstrictPower (rule 3).
# ══════════════════════════════════════════════════════════════════════════

def _thorns_combat(thorns: int = 3, seed: int = 0):
    from sts2_rl.monsters import Encounter
    from sts2_rl.monsters.overgrowth.slimes import LeafSlimeS
    from sts2_rl.cmds import PowerCmd
    from sts2_rl.powers import ThornsPower

    cs = CombatState(rng=random.Random(seed),
                     starting_deck=[make_card("strike") for _ in range(5)],
                     encounter=Encounter("test_thorns", [LeafSlimeS]))
    PowerCmd.apply(cs.hooks, cs.player, ThornsPower, thorns)
    return cs


def test_thorns_reflect_fires_after_damage_given_on_the_owner():
    """`on_damage_dealt` is gated on `dealer is not None` (cmds.py), so a
    dealer-less reflect was invisible to every AfterDamageGiven listener."""
    seen: list[tuple] = []

    cs = _thorns_combat(thorns=3)
    enemy = cs.enemies[0]

    class Spy:
        # `on_damage_dealt` grew `props`/`was_fully_blocked` params under
        # tier-2 Task 26 (power/_after_damage_given_substitution), passed
        # positionally by `_each`; `*_` absorbs both without re-encoding the
        # old 4-arg shape.
        def on_damage_dealt(self, dealer, target, amount, card=None, *_):
            seen.append((dealer, target, amount))

    spy = Spy()
    cs.hooks.register(spy)

    from sts2_rl.cmds import DamageCmd
    from sts2_rl.valueprops import DamageProps
    DamageCmd.deal(cs.hooks, cs.player, 4, dealer=enemy,
                   props=DamageProps.MONSTER_MOVE)

    reflects = [s for s in seen if s[0] is cs.player and s[1] is enemy]
    assert reflects, (
        f"the reflect must be dealt BY the Thorns owner; saw {seen}")
    assert reflects[0][2] == 3


def test_thorns_reflect_still_lands_on_the_attacker():
    cs = _thorns_combat(thorns=3)
    enemy = cs.enemies[0]
    hp = enemy.hp

    from sts2_rl.cmds import DamageCmd
    from sts2_rl.valueprops import DamageProps
    DamageCmd.deal(cs.hooks, cs.player, 4, dealer=enemy,
                   props=DamageProps.MONSTER_MOVE)
    assert enemy.hp == hp - 3


def test_a_dead_dealer_deals_nothing():
    """`CreatureCmd.Damage`'s first statement (CreatureCmd.cs:242-245): a dead
    dealer returns empty DamageResults without running the pipeline."""
    cs = _thorns_combat(thorns=0)
    enemy = cs.enemies[0]
    hp_before = cs.player.hp

    enemy.hp = 0
    assert enemy.is_dead

    from sts2_rl.cmds import DamageCmd
    from sts2_rl.valueprops import DamageProps
    dealt = DamageCmd.deal(cs.hooks, cs.player, 5, dealer=enemy,
                           props=DamageProps.MONSTER_MOVE)
    assert dealt == 0
    assert cs.player.hp == hp_before


def test_constrict_squeeze_names_its_dealer_and_keeps_no_extra_is_dead_guard():
    """ConstrictPower.cs:21-24 — `participants.Contains(base.Owner)` with no
    is_dead test, and `base.Owner` as the dealer."""
    from sts2_rl.cmds import PowerCmd
    from sts2_rl.powers import ConstrictPower

    seen: list[tuple] = []
    cs = _thorns_combat(thorns=0)
    enemy = cs.enemies[0]
    PowerCmd.apply(cs.hooks, enemy, ConstrictPower, 2, applier=cs.player)

    class Spy:
        # See the note in test_thorns_reflect_fires_after_damage_given_on_the_
        # owner above: `on_damage_dealt` grew two more positional params
        # under tier-2 Task 26.
        def on_damage_dealt(self, dealer, target, amount, card=None, *_):
            seen.append((dealer, target, amount))

    cs.hooks.register(Spy())
    hp = enemy.hp
    enemy.powers["constrict"].on_enemy_side_end()

    assert enemy.hp == hp - 2
    assert (enemy, enemy, 2) in seen, seen


def test_constrict_survives_a_prevented_death_of_its_applier():
    """ConstrictPower.cs:29 — `!wasRemovalPrevented && creature == Applier`.
    The port ignored the flag it is handed."""
    from sts2_rl.cmds import PowerCmd
    from sts2_rl.powers import ConstrictPower

    cs = _thorns_combat(thorns=0)
    enemy = cs.enemies[0]
    PowerCmd.apply(cs.hooks, enemy, ConstrictPower, 2, applier=cs.player)
    power = enemy.powers["constrict"]

    power.on_death(cs.player, was_removal_prevented=True)
    assert "constrict" in enemy.powers, "a prevented death must not drop it"

    power.on_death(cs.player, was_removal_prevented=False)
    assert "constrict" not in enemy.powers


# ══════════════════════════════════════════════════════════════════════════
# relic/scroll_boxes/AfterObtained — the two ModifyCardRewardCreationOptions
# dispatches (ScrollBoxes.cs:73 and :75)
#
# Bug class 28: a one-implementer hook is still a hook. The record called this
# DORMANT because "dingy_rug's port implements no card-reward hook" — false,
# it implements the hook in full (relics/dingy_rug.py). The dormancy is real
# but for a different and ENUMERABLE reason, which this pins: ScrollBoxes'
# options do not carry IsCardReward, the flag Dingy Rug gates on.
# ══════════════════════════════════════════════════════════════════════════

def _scroll_run(seed: int = 16):
    from sts2_rl.run import RunState
    return RunState(rng=random.Random(seed))


def test_scroll_boxes_runs_the_creation_options_chain_once_per_rarity():
    """ScrollBoxes.cs:73 and :75 are TWO dispatches, one per rarity."""
    from sts2_rl.relics import make_relic
    from sts2_rl.rewards import (CardCreationFlags, CardCreationSource,
                                 RarityOddsType)

    from sts2_rl.relics.base import Relic

    seen = []

    class Spy(Relic):
        id = "spy"
        name = "Spy"

        def modify_card_reward_creation_options(self, run, options):
            seen.append(options)
            return options

    run = _scroll_run()
    run.relics.append(Spy())
    make_relic("scroll_boxes").after_obtained(run)

    assert len(seen) == 2, f"ScrollBoxes.cs:73 and :75 — got {len(seen)}"
    for opts in seen:
        assert opts.source is CardCreationSource.OTHER
        assert opts.odds_type is RarityOddsType.UNIFORM
        assert opts.has_flag(CardCreationFlags.NO_UPGRADE_ROLL)
        assert opts.has_flag(CardCreationFlags.NO_RARITY_MODIFICATION)
        # the enumerated dormancy: Dingy Rug gates on this flag, and
        # ForNonCombatWithUniformOdds + NoRarityModification never set it
        assert not opts.has_flag(CardCreationFlags.IS_CARD_REWARD)


def test_scroll_boxes_honours_a_listener_that_narrows_the_pool():
    """The rarity test runs AFTER the chain — in C# it is `CardPoolFilter`, a
    predicate stored on the options and evaluated inside `GetPossibleCards`
    (CardCreationOptions.cs:168-172) — so a listener's pool edit is visible to
    it rather than being overwritten."""
    import dataclasses

    from sts2_rl.cards import CardRarity
    from sts2_rl.cards.base import _CARD_CLASSES
    from sts2_rl.cards.pool import pool_card_ids
    from sts2_rl.relics import make_relic

    run = _scroll_run()
    full = pool_card_ids(pool=run.card_pool)
    commons = [c for c in full if _CARD_CLASSES[c].rarity == CardRarity.COMMON]
    uncommons = [c for c in full
                 if _CARD_CLASSES[c].rarity == CardRarity.UNCOMMON]
    narrow = set(commons[:4]) | set(uncommons[:2])   # CanGenerateBundles' floor

    from sts2_rl.relics.base import Relic

    class Narrower(Relic):
        id = "narrower"
        name = "Narrower"

        def modify_card_reward_creation_options(self, run, options):
            return dataclasses.replace(
                options, pool=tuple(c for c in options.pool if c in narrow))

    run.relics.append(Narrower())
    before = len(run.deck)
    make_relic("scroll_boxes").after_obtained(run)
    added = [c.id for c in run.deck[before:]]

    assert len(added) == 3
    assert all(cid in narrow for cid in added), added


def test_scroll_boxes_dingy_rug_does_not_widen_this_creation():
    """DingyRug.cs:23-26 returns early without IsCardReward, so holding it
    changes nothing here. This is the enumeration that replaces the record's
    false 'dingy_rug implements no card-reward hook' dormancy argument."""
    from sts2_rl.cards.pool import COLORLESS_POOL
    from sts2_rl.relics import make_relic

    run = _scroll_run()
    run.relics.append(make_relic("dingy_rug"))
    before = len(run.deck)
    make_relic("scroll_boxes").after_obtained(run)
    added = [c.id for c in run.deck[before:]]

    assert len(added) == 3
    assert not any(cid in COLORLESS_POOL for cid in added), added


# ══════════════════════════════════════════════════════════════════════════
# monster/punch_construct/AfterAddedToRoom — clause 2b: the wrong stream, and
# a reduction the parity HP roll then erased
#
#   PunchOffEventEncounter.cs:17,:19  base.Rng.NextInt(2, 10)   x2
#   PunchConstruct.cs:71-79           AfterAddedToRoom spends it on CURRENT HP
#
# The sim rolled on the shared combat rng (ignoring the `selection_rng` it
# accepts) and applied the reduction inside create_monsters -- BEFORE
# `_roll_parity_hp`, whose `hp = max_hp = rolled` then wiped it.
# ══════════════════════════════════════════════════════════════════════════

def _punch_off_combat(seed: str = "T1PUNCH", floor: int = 7):
    from sts2_rl.events.punch_off import PUNCH_OFF_EVENT_ENCOUNTER
    rs = RunRngSet(seed)
    sel = make_encounter_rng(rs.seed, floor, PUNCH_OFF_EVENT_ENCOUNTER.entry)
    combat = CombatState(rng=random.Random(11), rng_set=rs,
                         encounter=PUNCH_OFF_EVENT_ENCOUNTER,
                         encounter_selection_rng=sel,
                         starting_deck=[make_card("strike") for _ in range(5)])
    return combat, rs, sel


def test_punch_off_reductions_come_off_the_per_encounter_stream():
    """Two draws on the encounter Rng where the sim took none, and none on the
    shared combat rng where the sim took two."""
    from sts2_rl.events.punch_off import PUNCH_OFF_EVENT_ENCOUNTER

    rs = RunRngSet("T1PUNCH")
    expected_sel = make_encounter_rng(rs.seed, 7, PUNCH_OFF_EVENT_ENCOUNTER.entry)
    expected = [expected_sel.next_int_range(2, 10) for _ in range(2)]

    combat, _rs, sel = _punch_off_combat()
    assert sel.counter == 2, "PunchOffEventEncounter.cs:17 and :19"
    assert [m.starting_hp_reduction for m in combat.enemies] == expected


def test_punch_off_reduction_survives_the_parity_hp_roll():
    """The lifecycle half: `AfterAddedToRoom` runs AFTER `CreateCreature`'s HP
    roll, so the reduction must still be on the board once parity HP is
    assigned. Applied in create_monsters it was silently erased."""
    combat, _rs, _sel = _punch_off_combat()
    for m in combat.enemies:
        assert m.max_hp == 55, "MaxHp is untouched (PunchConstruct.cs:33-35)"
        assert m.hp == max(1, 55 - m.starting_hp_reduction)
        assert m.hp < m.max_hp


def test_after_added_to_room_runs_for_a_mid_combat_spawn_too():
    """`CombatManager.AfterCreatureAdded`'s first statement is
    `await creature.AfterAddedToRoom()` -- for every creature, not just the
    starting ones, and in legacy mode as well as the parity path. The fix-up
    used to hang off `_assign_parity_monster_hp`, which is neither."""
    from sts2_rl.cmds import CreatureCmd
    from sts2_rl.monsters.underdocks.punch_construct import PunchConstruct

    combat, _rs, _sel = _punch_off_combat()
    spawn = PunchConstruct(combat.hooks, random.Random(2))
    spawn.starting_hp_reduction = 7
    CreatureCmd.add(combat.hooks, spawn)

    assert spawn.max_hp == 55
    assert spawn.hp == 55 - 7


def test_punch_off_pregenerated_path_applies_the_reduction_exactly_once():
    """The end-to-end parity path, which is where the reduction was ERASED:
    room entry pre-rolls max HP (`GenerateInternalCombatState`), the fight
    rebuilds the creatures through `PregeneratedEncounter.create_monsters`
    (which re-assigns `hp = max_hp = pregenerated`), and only then does
    `after_creature_added` spend the reduction. Once, not zero times and not
    twice — the per-encounter Rng is re-seeded identically in both passes, so
    the two roll the same pair."""
    from sts2_rl.events import make_event
    from sts2_rl.run import RunState

    run = RunState(rng=random.Random(4), string_seed="T1PUNCHE2E", total_floor=7)
    assert run.rng_set is not None
    event = make_event("punch_off", run)
    event.generate_internal_combat_state()

    # max HP only: AfterAddedToRoom has not run on these throwaway creatures
    assert event.pregenerated_hp == [55, 55]

    combat = run.create_combat(event.internal_combat_encounter())
    for m in combat.enemies:
        assert m.max_hp == 55
        assert 2 <= m.starting_hp_reduction <= 9
        assert m.hp == 55 - m.starting_hp_reduction
