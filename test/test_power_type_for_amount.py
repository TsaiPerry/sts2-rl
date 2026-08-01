"""power_cmd/G1 + power_cmd/G2 — PowerModel.GetTypeForAmount sign-awareness
(PowerModel.cs:460-471), consumed by ArtifactPower.TryModifyPowerAmountReceived
(ArtifactPower.cs:24) and UnsettlingLamp's latch/doubling (UnsettlingLamp.cs:97,
:124).

Task 17. Auditing this task found Mechanism A (power_cmd/G1, Artifact) was
ALREADY FIXED in today's code: `Power.type_for_amount` (sts2_rl/powers.py)
ports `GetTypeForAmount` and `PowerCmd.apply`'s Artifact branch
(sts2_rl/cmds.py) already consults it, not the static `power_cls.power_type`.
The `TestPowerTypeForAmount` / `TestArtifactSignAwareTyping` classes below
re-confirm that fix directly rather than introduce it — see
test/test_hook_order.py::TestPowerCmdOrder::test_artifact_blocks_negative_signed_debuff
for the pre-existing pin.

Mechanism B (power_cmd/G2, Unsettling Lamp) was still checking the static
`power_cls.power_type` and bailing on `amount <= 0` before that check could
ever matter. UnsettlingLamp.cs, read in full, has NO `amount <= 0` guard
anywhere — BeforePowerAmountChanged (:71-104) and
ModifyPowerAmountGivenMultiplicative (:106-129) both gate purely on
`power.GetTypeForAmount(amount) != PowerType.Debuff`. Fixed in
sts2_rl/relics/unsettling_lamp.py — `TestUnsettlingLampSignAwareTyping` below
is the TDD evidence.

Malaise.cs:40, Resonance.cs:33 and SharedFate.cs:39 (C# cards that apply a
negative-amount Buff-typed, allow_negative power to an enemy — the shape
both mechanisms are about) are neither ported (`grep -rli "malaise" -e
"resonance" sts2_rl/cards/` returns nothing), so every witness here
constructs the shape
directly with `PowerCmd.apply(..., amount=-N, applier=player)` instead of
playing a card, per both cards' own applier/cardSource shape:
`PowerCmd.Apply<StrengthPower>(choiceContext, target, -powerAmount,
base.Owner.Creature, this)` — applier=player, cardSource=the card.
"""
from __future__ import annotations

import random

from sts2_rl import (
    ArtifactPower,
    CombatState,
    DexterityPower,
    PowerCmd,
    PowerType,
    StrengthPower,
    VulnerablePower,
    WeakPower,
    make_relic,
)
from sts2_rl.cards import make_card
from sts2_rl.powers import BarricadePower


def fresh(relics=None, seed: int = 0) -> CombatState:
    return CombatState(rng=random.Random(seed), relics=relics)


class TestPowerTypeForAmount:
    """Power.type_for_amount (sts2_rl/powers.py:72-94) ports
    PowerModel.GetTypeForAmount (PowerModel.cs:460-471) directly: unit-level
    checks of the function itself, independent of its two call sites."""

    def test_negative_allow_negative_buff_becomes_debuff(self):
        """StrengthPower/DexterityPower.cs:14 declare Counter+AllowNegative;
        PowerModel.cs:462-465: a negative amount on such a power is Debuff."""
        assert StrengthPower.type_for_amount(-3) == PowerType.DEBUFF
        assert DexterityPower.type_for_amount(-1) == PowerType.DEBUFF

    def test_positive_or_zero_allow_negative_buff_stays_buff(self):
        assert StrengthPower.type_for_amount(3) == PowerType.BUFF
        assert StrengthPower.type_for_amount(0) == PowerType.BUFF

    def test_negative_non_allow_negative_debuff_becomes_buff(self):
        """PowerModel.cs:466-469: `!AllowNegative && Type==Debuff &&
        amount<0 -> Buff` — a negative offset REDUCING a duration-based
        debuff (Weak/Vulnerable ticking down) is itself typed a Buff, not a
        Debuff. Neither power sets allow_negative (defaults False). This is
        the mechanism that self-protects a duration tick from Artifact/Lamp
        without needing any `amount <= 0` bail: see
        TestUnsettlingLampSignAwareTyping below."""
        assert WeakPower.type_for_amount(-1) == PowerType.BUFF
        assert VulnerablePower.type_for_amount(-2) == PowerType.BUFF

    def test_positive_debuff_stays_debuff(self):
        assert WeakPower.type_for_amount(2) == PowerType.DEBUFF

    def test_genuinely_buff_power_is_unaffected_by_sign(self):
        """A Buff-typed power that is NOT allow_negative (BarricadePower)
        hits neither of GetTypeForAmount's two branches regardless of sign —
        PowerModel.cs:470 `return Type` — so it is a Buff no matter the
        amount's sign, unlike Strength/Dexterity."""
        assert BarricadePower.type_for_amount(1) == PowerType.BUFF
        assert BarricadePower.type_for_amount(-1) == PowerType.BUFF


class TestArtifactSignAwareTyping:
    """power_cmd/G1 — re-confirms PowerCmd.apply's Artifact branch
    (sts2_rl/cmds.py) consults type_for_amount, not the static power_type,
    matching ArtifactPower.cs:24's
    `canonicalPower.GetTypeForAmount(amount) != PowerType.Debuff`. Found
    already fixed; these witnesses exercise it at the PowerCmd.apply layer
    directly, mirroring Malaise/Resonance's shape (applier=player,
    target=enemy, negative StrengthPower/DexterityPower)."""

    def test_negative_strength_steal_is_blocked_by_artifact(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.enemy, ArtifactPower, 1)
        PowerCmd.apply(cs.hooks, cs.enemy, StrengthPower, -3, applier=cs.player)
        assert "strength" not in cs.enemy.powers   # Malaise's steal blocked
        assert "artifact" not in cs.enemy.powers    # its one stack consumed

    def test_negative_dexterity_steal_is_blocked_by_artifact(self):
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.enemy, ArtifactPower, 1)
        PowerCmd.apply(cs.hooks, cs.enemy, DexterityPower, -1, applier=cs.player)
        assert "dexterity" not in cs.enemy.powers   # blocked; no shipped C# card
        # applies negative Dexterity to an enemy -- Dexterity is used here purely
        # as a second Counter+AllowNegative+Buff power sharing Strength's shape.
        assert "artifact" not in cs.enemy.powers

    def test_positive_strength_is_not_blocked_by_artifact(self):
        """Control: a positive-amount Buff is never a Debuff by
        GetTypeForAmount, so Artifact must not intercept it."""
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.enemy, ArtifactPower, 1)
        PowerCmd.apply(cs.hooks, cs.enemy, StrengthPower, 3, applier=cs.player)
        assert cs.enemy.powers["strength"].amount == 3
        assert cs.enemy.powers["artifact"].amount == 1   # untouched

    def test_ordinary_positive_debuff_is_still_blocked(self):
        """Control: an ordinary positive-amount Debuff (Vulnerable) is
        unaffected by the sign-aware switch — still blocked as before."""
        cs = fresh()
        PowerCmd.apply(cs.hooks, cs.enemy, ArtifactPower, 1)
        PowerCmd.apply(cs.hooks, cs.enemy, VulnerablePower, 2, applier=cs.player)
        assert "vulnerable" not in cs.enemy.powers
        assert "artifact" not in cs.enemy.powers


class TestUnsettlingLampSignAwareTyping:
    """power_cmd/G2 — UnsettlingLamp.modify_power_amount_given_multiplicative
    (sts2_rl/relics/unsettling_lamp.py; renamed from modify_power_amount by
    the power_cmd/G3+G4 given/received split) now checks
    `power_cls.type_for_amount(amount)`, matching UnsettlingLamp.cs:97
    (latch) and :124 (ModifyPowerAmountGivenMultiplicative), and no longer
    bails on `amount <= 0` — UnsettlingLamp.cs has no such bail anywhere.
    Malaise.cs:40 / Resonance.cs:33 both apply negative StrengthPower to an
    enemy with applier=player, cardSource=this: the unported shape these
    witnesses construct directly (`lamp.before_card_played(card)` stands in
    for the card bracket that would normally open/close around the
    PowerCmd.apply call)."""

    def test_negative_strength_steal_is_doubled(self):
        cs = fresh(relics=[make_relic("unsettling_lamp")])
        lamp = cs.relics[0]
        card = make_card("strike")   # only its identity matters here
        lamp.before_card_played(card)
        PowerCmd.apply(cs.hooks, cs.enemy, StrengthPower, -3, applier=cs.player)
        assert cs.enemy.powers["strength"].amount == -6   # doubled, not -3

    def test_second_negative_strength_steal_same_combat_is_not_doubled(self):
        """Once-per-combat: after the triggering card finishes playing
        (AfterCardPlayed -> IsFinishedTriggering), a later card's debuff is
        not doubled."""
        cs = fresh(relics=[make_relic("unsettling_lamp")])
        lamp = cs.relics[0]
        card_a = make_card("strike")
        lamp.before_card_played(card_a)
        PowerCmd.apply(cs.hooks, cs.enemy, StrengthPower, -3, applier=cs.player)
        lamp.on_card_played(card_a)   # card A finishes -> IsFinishedTriggering
        card_b = make_card("strike")
        lamp.before_card_played(card_b)
        PowerCmd.apply(cs.hooks, cs.enemy, StrengthPower, -1, applier=cs.player)
        assert cs.enemy.powers["strength"].amount == -6 - 1   # -1, not -2

    def test_positive_strength_gain_on_enemy_is_not_doubled(self):
        """Control: a positive-amount Buff applied to an enemy is not a
        Debuff by GetTypeForAmount, so the Lamp — which only doubles
        Debuffs — leaves it unchanged and does not latch."""
        cs = fresh(relics=[make_relic("unsettling_lamp")])
        lamp = cs.relics[0]
        card = make_card("strike")
        lamp.before_card_played(card)
        PowerCmd.apply(cs.hooks, cs.enemy, StrengthPower, 3, applier=cs.player)
        assert cs.enemy.powers["strength"].amount == 3   # not doubled
        assert lamp._triggering is None   # never latched

    def test_negative_reduction_of_a_non_allow_negative_debuff_is_not_doubled(self):
        """A negative amount on a Debuff-typed, non-allow_negative power
        (Weak/Vulnerable — the shape a duration tick would have, if duration
        ticks routed through this chain) resolves to Buff by
        GetTypeForAmount, so the Lamp does not double it either — this is
        what makes the removed `amount <= 0` bail unnecessary rather than
        merely redundant."""
        cs = fresh(relics=[make_relic("unsettling_lamp")])
        lamp = cs.relics[0]
        card = make_card("strike")
        lamp.before_card_played(card)
        PowerCmd.apply(cs.hooks, cs.enemy, WeakPower, -1, applier=cs.player)
        assert cs.enemy.powers["weak"].amount == -1   # not doubled to -2
        assert lamp._triggering is None   # did not latch either

    def test_activation_still_spent_when_artifact_blocks_a_negative_steal(self):
        """Combines both mechanisms, mirroring the 933T Mecha Knight
        regression this seam already fixed for positive debuffs
        (test_relics.py::TestUnsettlingLamp::
        test_activation_spent_even_when_artifact_negates_debuff): Lamp's
        given-side chain runs (and latches/doubles) BEFORE Artifact's veto,
        now itself a received-side listener rather than a hand-rolled block
        (cmds.py's given-then-received dispatch order, power_cmd/G3+G4), so
        a negative Strength steal Artifact fully blocks still spends the
        Lamp's once-per-combat activation."""
        cs = fresh(relics=[make_relic("unsettling_lamp")])
        lamp = cs.relics[0]
        PowerCmd.apply(cs.hooks, cs.enemy, ArtifactPower, 1)
        card_a = make_card("strike")
        lamp.before_card_played(card_a)
        PowerCmd.apply(cs.hooks, cs.enemy, StrengthPower, -3, applier=cs.player)
        assert "strength" not in cs.enemy.powers    # Artifact ate the steal
        assert "artifact" not in cs.enemy.powers     # its one charge consumed
        lamp.on_card_played(card_a)
        # The Lamp's activation was still spent: a later steal applies its
        # plain amount, not doubled.
        card_b = make_card("strike")
        lamp.before_card_played(card_b)
        PowerCmd.apply(cs.hooks, cs.enemy, StrengthPower, -1, applier=cs.player)
        assert cs.enemy.powers["strength"].amount == -1
