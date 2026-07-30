"""Commands refuse to act once the combat is over or ENDING
(creature_card_cmds G14, power_cmd G6).

Every command in these two seams opens with its own liveness check --
`CombatManager.IsOverOrEnding`, `IsEnding`, or `!IsInProgress` -- and returns
an empty/zero/no-op result. `IsEnding` (CombatManager.cs:180-202) is true from
the moment the last primary enemy dies, BEFORE the teardown runs, so there is a
real window in which the sim considered the fight live: the killing blow's own
card is still resolving, and anything it triggers afterwards used to land.

`HookSystem._each` already stops a guarded-bucket DISPATCH in that window
(hook_dispatch G8). These are the COMMANDS: the mutation each one performs was
still happening even with every listener silenced.

The window is reproduced here by killing the only enemy without letting
`_end_combat` run -- exactly the state the engine is in between the killing
blow and `CheckWinCondition`.
"""
from __future__ import annotations

import random

import pytest

from sts2_rl import CombatState, PowerCmd, StrengthPower, VulnerablePower
from sts2_rl.cards import make_card
from sts2_rl.cmds import BlockCmd, CardCmd, CardPileCmd
from sts2_rl.combat import Phase


def ending() -> CombatState:
    """A combat in the IsEnding window: the last primary enemy is dead, the
    teardown has not run, `phase` is still the player's turn."""
    cs = CombatState(rng=random.Random(0))
    cs.enemies[0].hp = 0
    assert cs.phase != Phase.COMBAT_OVER
    assert cs.is_ending and cs.is_over_or_ending
    return cs


def live() -> CombatState:
    cs = CombatState(rng=random.Random(0))
    assert not cs.is_ending and not cs.is_over_or_ending
    return cs


class TestTheWindowItself:
    def test_is_ending_is_true_before_the_teardown(self):
        cs = ending()
        assert not cs.is_over          # !IsInProgress is still false
        assert cs.is_ending            # ...but IsEnding is already true

    def test_a_finished_combat_is_over_but_not_ending(self):
        """CombatManager.cs:184-187 — `IsEnding` opens `if (!IsInProgress)
        return false`, so a combat that has already ended is
        `IsOverOrEnding` via the OTHER arm."""
        cs = live()
        cs._end_combat(player_won=True)
        assert cs.is_over and not cs.is_ending and cs.is_over_or_ending

    def test_a_power_holding_the_fight_open_keeps_it_live(self):
        """`IsEnding` consults Hook.ShouldStopCombatFromEnding
        (CombatManager.cs:196), which is what `_all_enemies_dead` already
        carries -- so a creature dead at 0 HP and about to revive does NOT put
        the commands into refusal mode."""
        cs = CombatState(rng=random.Random(0))

        class Holder:
            def should_stop_combat_from_ending(self):
                return True

        cs.hooks.register(Holder())
        cs.enemies[0].hp = 0
        assert not cs.is_ending


class TestCreatureAndCardCommands:
    def test_gain_block_returns_zero(self):
        """CreatureCmd.cs:637-640 — `IsOverOrEnding -> return default`."""
        cs = ending()
        cs.player.block = 0
        assert BlockCmd.apply(cs.hooks, cs.player, 8) == 0
        assert cs.player.block == 0
        alive = live()
        assert BlockCmd.apply(alive.hooks, alive.player, 8) == 8

    def test_draw_returns_nothing(self):
        """CardPileCmd.cs:800-803 — `IsOverOrEnding -> empty`."""
        cs = ending()
        cs.player.hand.clear()
        cs.player.draw_pile.clear()
        cs.player.draw_pile.extend(make_card("strike") for _ in range(5))
        cs.player._draw(3)
        assert cs.player.hand == []
        assert len(cs.player.draw_pile) == 5

    def test_shuffle_does_not_happen(self):
        """CardPileCmd.cs:866-869, and :914-918 for the AfterShuffle site."""
        cs = ending()
        cs.player.draw_pile.clear()
        cs.player.discard_pile.extend(make_card("strike") for _ in range(4))
        seen = []

        class Spy:
            def on_shuffle(self, player):
                seen.append(1)

        cs.hooks.register(Spy())
        cs.player.reshuffle_discard_into_draw()
        assert len(cs.player.discard_pile) == 4
        assert cs.player.draw_pile == []
        assert seen == []

    def test_the_hand_is_not_discarded(self):
        """CardCmd.cs:174-177 — `IsOverOrEnding -> return`."""
        cs = ending()
        cs.player.hand.clear()
        cs.player.hand.extend(make_card("strike") for _ in range(3))
        cs.player.discard_hand()
        assert len(cs.player.hand) == 3
        assert cs.player.discard_pile == []

    def test_a_generated_card_does_not_enter_a_combat_pile(self):
        """CardPileCmd.cs:312-319 (`IsEnding` -> every result success=false),
        :329-340 (a dead owner) and :398-401 (`!IsInProgress`). The pile move
        itself is downstream of all three, so a refused add really does leave
        the pile alone."""
        cs = ending()
        cs.player.hand.clear()
        cs.player.discard_pile.clear()
        cs.player.draw_pile.clear()
        CardPileCmd.add_to_hand(cs.hooks, cs.player, make_card("strike"))
        CardPileCmd.add_to_discard(cs.hooks, cs.player, make_card("strike"))
        CardPileCmd.add_to_draw(cs.hooks, cs.player, make_card("strike"))
        assert cs.player.hand == []
        assert cs.player.discard_pile == []
        assert cs.player.draw_pile == []

    def test_a_generated_card_is_dropped_when_the_owner_is_dead(self):
        """CardPileCmd.cs:329-340 is a refusal on the card's OWNER, tested per
        card and separately from the ending one -- it survives even if a power
        holds the fight open around the corpse."""
        cs = CombatState(rng=random.Random(0))
        cs.player.hp = 0
        cs.player.hand.clear()
        cs.player.discard_pile.clear()
        CardPileCmd.add_to_hand(cs.hooks, cs.player, make_card("strike"))
        assert cs.player.hand == []
        assert cs.player.discard_pile == []

    def test_transform_is_refused(self):
        """CardCmd.cs:371-374 — `IsEnding -> empty`. Note this one is IsEnding,
        not IsOverOrEnding: the out-of-combat deck transformers are unaffected
        because `IsEnding` opens with `if (!IsInProgress) return false`."""
        cs = ending()
        card = make_card("strike")
        cs.player.hand.clear()
        cs.player.hand.append(card)
        assert CardCmd.transform_to_random(cs.hooks, cs.player, card) is None
        assert cs.player.hand == [card]

    def test_afflict_is_refused_only_for_a_card_in_a_combat_pile(self):
        """CardCmd.cs:627-634 is asymmetric: refuse when `IsOverOrEnding` AND
        the card sits in a combat pile, allow it otherwise."""
        from sts2_rl.afflictions import RingingAffliction as affliction_cls

        cs = ending()
        # A real combat card: CardPileCmd._enter_combat is what stamps
        # `card.combat`, which is the sim's `card.Pile.IsCombatPile` handle.
        in_pile = cs.player.hand[0] if cs.player.hand else cs.player.draw_pile[0]
        assert in_pile.combat is cs
        assert CardCmd.afflict(in_pile, affliction_cls, 1) is None
        assert in_pile.affliction is None

        loose = make_card("strike")          # in no combat pile at all
        assert CardCmd.afflict(loose, affliction_cls, 1) is not None


class TestPowerCmd:
    def test_apply_returns_none(self):
        """PowerCmd.cs:69-72 — `IsEnding -> return null`."""
        cs = ending()
        assert PowerCmd.apply(cs.hooks, cs.player, StrengthPower, 3) is None
        assert "strength" not in cs.player.powers

    def test_stacking_onto_an_existing_power_is_refused(self):
        """PowerCmd.cs:217-220 — ModifyAmount has its OWN `IsEnding` guard, so
        the stacking branch is refused too, not just the first application."""
        cs = live()
        PowerCmd.apply(cs.hooks, cs.player, StrengthPower, 3)
        assert cs.player.powers["strength"].amount == 3
        cs.enemies[0].hp = 0
        assert cs.is_ending
        PowerCmd.apply(cs.hooks, cs.player, StrengthPower, 4)
        assert cs.player.powers["strength"].amount == 3

    def test_a_mid_pipeline_hittability_change_refuses_the_power(self):
        """PowerCmd.cs:133 re-tests `target.CanReceivePowers` AFTER the
        given/received modifier chains have run, so a listener that made the
        target unhittable DURING those chains still stops the application. The
        sim tested it once, at the entry."""
        cs = live()
        target = cs.enemies[0]

        class Flipper:
            """Hittable at the entry check, not by the time the amount is
            settled -- `modify_power_amount` is the last chain before :133."""

            def __init__(self):
                self.armed = False

            def modify_power_amount(self, name, tgt, amount, applier=None):
                self.armed = True
                return amount

            def should_allow_hitting(self, tgt):
                return not self.armed

        cs.hooks.register(Flipper())
        PowerCmd.apply(cs.hooks, target, VulnerablePower, 2, applier=cs.player)
        assert "vulnerable" not in target.powers
