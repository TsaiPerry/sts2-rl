"""Round 14, lane R8 — the AttackCommand-level AfterAttack bracket and the
damage-pipeline powered-attack gate (StrikeDummy / FakeStrikeDummy).

See .superpowers/sdd/round14/R8-report.md for the full per-entry verdicts and
citations. Each test below pins one entry's executed claim.
"""
from __future__ import annotations

import random

import pytest

from sts2_rl import CombatState, make_relic
from sts2_rl.cards import make_card
from sts2_rl.cmds import DamageCmd, PowerCmd
from sts2_rl.monsters import Encounter
from sts2_rl.monsters.overgrowth.slimes import LeafSlimeS
from sts2_rl.powers import PainfulStabsPower, SkittishPower, StrengthPower, SuckPower
from sts2_rl.valueprops import DamageProps, ValueProp


def _combat(relic_ids=(), hand=(), seed: int = 0) -> CombatState:
    cs = CombatState(rng=random.Random(seed),
                     starting_deck=[make_card("strike") for _ in range(5)],
                     encounter=Encounter("test", [LeafSlimeS]),
                     relics=[make_relic(r) for r in relic_ids])
    cs.player.hand.clear()
    for cid in hand:
        card = make_card(cid)
        card.combat = cs
        cs.hooks.register(card)
        cs.player.hand.append(card)
    return cs


# ══════════════════════════════════════════════════════════════════════════
# power/skittish/AfterAttack — LIVE. Moved from on_damage_received (per hit)
# to after_attack (once per AttackCommand, over the FIRST hit that landed on
# the owner). SkittishPower.cs:56-68.
# ══════════════════════════════════════════════════════════════════════════

class TestSkittish:
    def test_multi_hit_attack_does_not_get_blocked_mid_swing(self):
        """Twin Strike (2x5) against Skittish 8: both hits must land at full
        damage -- the block is granted only AFTER the whole AttackCommand
        resolves, not after the first hit. The old on_damage_received
        version granted block after hit 1, so hit 2 landed against block the
        game had not granted yet (enemy.hp dropped by only 5, not 10)."""
        cs = _combat(hand=["twin_strike"], seed=3)
        enemy = cs.enemies[0]
        PowerCmd.apply(cs.hooks, enemy, SkittishPower, 8)
        cs.player.energy = 10
        before = enemy.hp
        assert cs.play_card(0) is True
        assert enemy.hp == before - 10   # both 5-damage hits landed in full
        assert enemy.block == 8          # block granted once, after the swing

    def test_only_once_per_turn(self):
        """HasGainedBlockThisTurn latches for the rest of the enemy's
        opposing side's turn (SkittishPower.cs:38-49/71-82) -- a second
        Attack card played the same turn must not grant block again."""
        cs = _combat(hand=["strike", "strike"], seed=4)
        enemy = cs.enemies[0]
        PowerCmd.apply(cs.hooks, enemy, SkittishPower, 8)
        cs.player.energy = 10
        assert cs.play_card(0) is True
        assert enemy.block == 8
        assert enemy.powers["skittish"]._blocked_this_turn is True
        # Second Attack: the 8 block granted by the first Attack absorbs
        # this hit's 6 damage (block 8 -> 2); the LATCH stops a second
        # grant, so block only ever goes down here, never back up.
        assert cs.play_card(0) is True
        assert enemy.block == 2
        assert enemy.powers["skittish"]._blocked_this_turn is True

    def test_monster_attack_does_not_open_the_bracket(self):
        """SkittishPower.cs:58's `command.ModelSource is CardModel` check --
        a monster attack (card=None) never grants Skittish's block. The sim
        stands this in with `card is not None`."""
        cs = _combat(seed=5)
        enemy = cs.enemies[0]
        PowerCmd.apply(cs.hooks, enemy, SkittishPower, 8)
        cs.hooks.before_attack(enemy)
        DamageCmd.deal(cs.hooks, cs.player, 5, dealer=enemy)
        cs.hooks.after_attack(enemy)
        assert enemy.block == 0

    def test_zero_unblocked_damage_does_not_grant_block(self):
        """FirstOrDefault finds the hit on the owner, but
        `damageResult.UnblockedDamage != 0` still gates the grant -- a fully
        blocked hit must not trigger it."""
        cs = _combat(hand=["strike"], seed=6)
        enemy = cs.enemies[0]
        PowerCmd.apply(cs.hooks, enemy, SkittishPower, 8)
        enemy.block = 999
        cs.player.energy = 10
        assert cs.play_card(0) is True
        assert enemy.block != 8   # nothing GRANTED (still whatever absorption left)
        assert not enemy.powers["skittish"]._blocked_this_turn


# ══════════════════════════════════════════════════════════════════════════
# power/painful_stabs and power/suck AfterAttack — UNLABELLED, NARROWED in
# round 13. Re-confirm the hook fix (killing-blow skip + mid-attack timing
# both gone) is still in place, and re-confirm the residual
# `!IsPoweredAttack()` guard is unreachable: no ported monster attack sets
# Unpowered props on MOVE damage (monsters/base.py's `_execute_attack` always
# calls `DamageCmd.deal` with the default inferred props, which for a
# dealer-less call is DamageProps.MONSTER_MOVE = Move only).
# ══════════════════════════════════════════════════════════════════════════

class TestSuckAndPainfulStabsResidual:
    def test_suck_after_attack_fixed_shape_still_holds(self):
        cs = _combat(seed=7)
        enemy = cs.enemies[0]
        PowerCmd.apply(cs.hooks, enemy, SuckPower, 2)
        cs.hooks.before_attack(enemy)
        DamageCmd.deal(cs.hooks, cs.player, 5, dealer=enemy)
        DamageCmd.deal(cs.hooks, cs.player, 5, dealer=enemy)
        cs.hooks.after_attack(enemy)
        assert enemy.powers["strength"].amount == 4   # 2 hits * 2 amount

    def test_painful_stabs_after_attack_fixed_shape_still_holds(self):
        cs = _combat(seed=8)
        enemy = cs.enemies[0]
        PowerCmd.apply(cs.hooks, enemy, PainfulStabsPower, 1)
        cs.hooks.before_attack(enemy)
        DamageCmd.deal(cs.hooks, cs.player, 5, dealer=enemy)
        cs.hooks.after_attack(enemy)
        wounds = sum(1 for c in cs.player.discard_pile if c.id == "wound")
        assert wounds == 1

    def test_no_ported_monster_attack_deals_unpowered_move_damage(self):
        """Census for the residual `!command.DamageProps.IsPoweredAttack()`
        guard (SuckPower.cs:24, PainfulStabsPower.cs:36): grepped every
        `DamageCmd.deal(` call site with an explicit `props=` under
        `sts2_rl/monsters/` -- none passes an Unpowered MOVE prop set
        (`monsters/glory/fabricator.py`'s one `props=ValueProp.UNPOWERED`
        hit is a `BlockCmd.apply` call, not damage). `Monster._execute_attack`
        (monsters/base.py:264-275), the single shared attack entry point,
        always calls `DamageCmd.deal` with no `props=` at all, which
        `DamageCmd.deal` infers as `DamageProps.CARD`/`MONSTER_MOVE` --
        Move, never Unpowered. This is an EXECUTED reachability check, not a
        grep alone: it asserts the actual inferred props a real
        `_execute_attack` call produces."""
        cs = _combat(seed=9)
        enemy = cs.enemies[0]
        captured: list = []
        original_deal = DamageCmd.deal
        original_deal_entry = DamageCmd.__dict__["deal"]

        def _spy(hooks, target, amount, dealer=None, card=None,
                 props=None, result=None, _orig=original_deal):
            if props is None:
                inferred = (DamageProps.CARD_UNPOWERED
                            if card is not None and card.is_unpowered
                            else DamageProps.CARD)
            else:
                inferred = props
            captured.append(inferred)
            return _orig(hooks, target, amount, dealer=dealer, card=card,
                         props=props, result=result)

        DamageCmd.deal = staticmethod(_spy)
        try:
            enemy._execute_attack(cs._ctx(), 5, 2)
        finally:
            DamageCmd.deal = original_deal_entry
        assert captured, "no damage dealt"
        assert all(ValueProp.UNPOWERED not in p for p in captured)


# ══════════════════════════════════════════════════════════════════════════
# damage_pipeline/G3 — StrikeDummy / FakeStrikeDummy's card-ownership
# disjunct. StrikeDummy.cs:33-36 / FakeStrikeDummy.cs:35-38 decline the bonus
# only when BOTH `dealer != Owner.Creature` AND `cardSource.Owner != Owner`.
# The sim models no enemy-owned CardModel (every card belongs to the
# player), so the ownership disjunct can never be true and the relic must
# never decline on dealer grounds alone.
# ══════════════════════════════════════════════════════════════════════════

class TestStrikeDummyOwnershipDisjunct:
    def test_strike_dummy_grants_bonus_with_no_dealer(self):
        cs = _combat(["strike_dummy"], seed=12)
        strike = make_card("strike")
        strike.combat = cs
        base = 6
        with_player = cs.hooks.modify_damage_additive(
            cs.enemies[0], base, cs.player, strike, props=DamageProps.CARD)
        with_none = cs.hooks.modify_damage_additive(
            cs.enemies[0], base, None, strike, props=DamageProps.CARD)
        assert with_player == base + 3   # StrikeDummy.EXTRA_DAMAGE
        assert with_none == base + 3     # card is still the player's

    def test_fake_strike_dummy_grants_bonus_with_no_dealer(self):
        cs = _combat(["fake_strike_dummy"], seed=9)
        strike = make_card("strike")
        strike.combat = cs
        base = 6
        with_player = cs.hooks.modify_damage_additive(
            cs.enemies[0], base, cs.player, strike, props=DamageProps.CARD)
        with_none = cs.hooks.modify_damage_additive(
            cs.enemies[0], base, None, strike, props=DamageProps.CARD)
        assert with_player == base + 1   # FakeStrikeDummy.EXTRA_DAMAGE
        assert with_none == base + 1

    def test_non_strike_card_still_gets_nothing(self):
        cs = _combat(["strike_dummy"], seed=13)
        defend = make_card("defend")
        defend.combat = cs
        assert cs.hooks.modify_damage_additive(
            cs.enemies[0], 6, cs.player, defend, props=DamageProps.CARD) == 6

    def test_unpowered_attack_still_gets_nothing(self):
        cs = _combat(["strike_dummy"], seed=14)
        strike = make_card("strike")
        strike.combat = cs
        assert cs.hooks.modify_damage_additive(
            cs.enemies[0], 6, cs.player, strike,
            props=DamageProps.CARD_UNPOWERED) == 6
