"""Task 8, Mechanism C: `monster/aeonglass/AfterCardGeneratedForCombat` --
generated Withers are now fake-upgraded through the hook, not open-coded.

Aeonglass.cs:150-166 fake-upgrades EVERY card generated for combat that is a
Wither, from any source, via `MatchWitherToUpgradeCount`. Once Task 8's
Mechanism B wires `on_card_generated_for_combat` at the sim's two dispatch
sites, `monsters/glory/aeonglass.py`'s Aeonglass hook is the
sim's first ported listener for it (as of round 13 the handler is on the
Aeonglass monster itself -- hook_dispatch/G5), and the two former open-coded upgrade
loops -- the boss's own Increasing Intensity Wither (aeonglass.py) and
WitheringPresencePower's punish Wither (powers.py) -- are deleted in favour
of it.
"""
from __future__ import annotations

import random

import pytest

from sts2_rl import CombatState
from sts2_rl.cards import make_card
from sts2_rl.cmds import CardCmd, CardPileCmd
from sts2_rl.monsters import Encounter
from sts2_rl.monsters.glory import Aeonglass


def fresh_with(monster_cls, seed: int = 0) -> CombatState:
    enc = Encounter("test", [monster_cls])
    return CombatState(rng=random.Random(seed), encounter=enc)


def test_boss_own_wither_arrives_fake_upgraded_via_the_hook():
    """`_intensity` no longer open-codes the upgrade at its own generation
    site -- it relies on Aeonglass's own hook firing off
    `add_to_discard`'s new AfterCardGeneratedForCombat dispatch."""
    cs = fresh_with(Aeonglass)
    boss = cs.enemies[0]
    assert boss.wither_upgrade_count == 0
    boss._intensity(cs._ctx())
    assert boss.wither_upgrade_count == 1
    withers = [c for c in cs.player.discard_pile if c.id == "wither"]
    assert len(withers) == 1
    assert withers[0].fake_upgrade_level == 1


def test_boss_own_wither_compounds_across_repeated_moves():
    """Regression for the machinery `_intensity` keeps open-coded (fake-
    upgrading every EXISTING Wither on the field, Aeonglass.cs:136-142):
    after two Increasing Intensity moves both the original and the new
    Wither must sit at the same, doubly-upgraded level -- exactly the old
    open-coded behaviour, now split across two mechanisms."""
    cs = fresh_with(Aeonglass)
    boss = cs.enemies[0]
    boss._intensity(cs._ctx())
    first = next(c for c in cs.player.discard_pile if c.id == "wither")
    boss._intensity(cs._ctx())
    withers = [c for c in cs.player.discard_pile if c.id == "wither"]
    assert len(withers) == 2
    assert all(w.fake_upgrade_level == 2 for w in withers)
    assert first in withers


def test_witheringpresence_punish_wither_arrives_fake_upgraded_via_the_hook():
    """WitheringPresencePower.cs:55's real Wither is matched only via
    Aeonglass's hook (not the hover-tip preview at :37, which has no sim
    analogue) -- powers.py no longer open-codes
    `getattr(self.owner, "wither_upgrade_count", 0)` at its own generation
    site either."""
    cs = fresh_with(Aeonglass)
    boss = cs.enemies[0]
    boss._intensity(cs._ctx())  # wither_upgrade_count: 0 -> 1
    assert boss.wither_upgrade_count == 1

    cs.player.hand.clear()
    cs.player.hand[:] = [make_card("strike") for _ in range(6)]
    cs.player.energy = 999
    for _ in range(6):
        cs.play_card(0, 0)

    hand_withers = [c for c in cs.player.hand if c.id == "wither"]
    assert len(hand_withers) == 1
    assert hand_withers[0].fake_upgrade_level == 1


class _AlwaysWither:
    """Stands in for the CombatCardSelection stream, forcing Entropy's
    transform roll to land on "wither" -- `wither` is a real member of
    Dazed's in-combat transform pool (STATUS cards transform within their
    own pool, no rarity filter, `cards/pool.py`'s
    `transform_options_in_combat`)."""

    def choice(self, seq):
        assert "wither" in seq
        return "wither"


def test_a_wither_reaching_the_field_via_transform_arrives_fake_upgraded():
    """The THIRD route to a mid-combat Wither, and the one neither open-coded
    site ever covered: Entropy transforming a Status/Curse card (Dazed here)
    can itself roll "wither" (Wither.cs is a member of the Status pool,
    StatusCardPool.cs:28). Before Mechanism B wired
    `on_card_generated_for_combat` at the transform site (CardCmd.cs:
    499-506), a Wither arriving this way during an Aeonglass fight was NOT
    upgraded at all -- a real divergence neither of the two old open-coded
    sites could have caught, since neither sits anywhere near
    `transform_to_random`."""
    cs = fresh_with(Aeonglass)
    boss = cs.enemies[0]
    boss._intensity(cs._ctx())  # wither_upgrade_count: 0 -> 1
    dazed = make_card("dazed")
    cs.player.hand.clear()
    cs.player.hand.append(dazed)
    CardPileCmd._enter_combat(cs.hooks, dazed)
    cs.combat_rng._accessors["card_selection"] = _AlwaysWither()

    replacement = CardCmd.transform_to_random(cs.hooks, cs.player, dazed)

    assert replacement.id == "wither"
    assert replacement.fake_upgrade_level == 1


def test_third_party_generated_card_is_untouched():
    """Aeonglass.cs:152-154 `if (!(card is Wither wither)) return;` -- a
    Strike routed through the newly-wired Add pipeline must not be handed to
    `fake_upgrade` (a method only WitherCard defines); an incorrect isinstance
    guard would raise AttributeError here, not silently no-op."""
    cs = fresh_with(Aeonglass)
    cs.player.hand.clear()
    strike = make_card("strike")
    CardPileCmd.add_to_hand(cs.hooks, cs.player, strike)
    assert strike in cs.player.hand


def test_listener_ignores_a_card_with_no_upgrade_count_pending():
    """Direct unit check on the handler: zero pending upgrades is a no-op
    (range(0)), matching a freshly-spawned Aeonglass before its first
    Increasing Intensity move."""
    cs = fresh_with(Aeonglass)
    boss = cs.enemies[0]
    assert boss.wither_upgrade_count == 0
    wither = make_card("wither")
    boss.on_card_generated_for_combat(wither)
    assert wither.fake_upgrade_level == 0


def test_aeonglass_is_itself_the_listener():
    """hook_dispatch/G5: the handler used to live on a private
    `_AeonglassWitherListener` registered in a hand-made "Powers + 1" slot,
    because the sim had no MonsterModel listener category. It now sits on the
    monster, which is where `Aeonglass.AfterCardGeneratedForCombat`
    (Aeonglass.cs:150-166) sits, and the monster is the registered listener
    (CombatState.cs:417-421)."""
    import sts2_rl.monsters.glory.aeonglass as mod

    assert not hasattr(mod, "_AeonglassWitherListener")
    cs = fresh_with(Aeonglass)
    boss = cs.enemies[0]
    assert boss in cs.hooks._listeners
    assert boss.on_card_generated_for_combat.__self__ is boss
    # ...and it dispatches from the monster's own slot in the derived walk:
    # right after that creature's powers (CombatState.cs:416-421).
    order = cs.hooks._ordered()
    powers = [p for p in boss.powers.values()]
    assert order.index(boss) == max(order.index(p) for p in powers) + 1
