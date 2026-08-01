"""
Tests for card/_unplayable_cost (audit gap queue mechanism `card/_unplayable_cost`).

AscendersBane.cs:19-22 and 28 other unplayable curse/status/quest cards
construct with a canonical energy cost of **-1**:
`base(-1, CardType.Curse, CardRarity.Curse, TargetType.None)`. -1 is not a
cosmetic "no cost" marker -- `CardEnergyCost.GetWithModifiers` short-circuits
on `if (_base < 0) return num;` (CardEnergyCost.cs:100-103) BEFORE any local
or global cost modifier is applied, so in the game an unplayable card is
IMMUNE to every cost modifier and keeps reporting -1. The sim used to set
`self._energy_cost = 0` and run the full modifier chain over it.

`GetAmountToSpend()` / `GetResolved()` both clamp their own call to
`Math.Max(0, GetWithModifiers(...))` (CardEnergyCost.cs:134-141), so what is
SPENT already agreed on both sides before this fix; only what is READ
diverged. The sim's `hooks.modify_card_energy_cost` dispatcher mirrors that
same clamp at its own tail (`return max(0, cost)`, hooks.py:574), so the
observation encoder's encoded value (which always routes through that
dispatcher via `preview_card_energy_cost`) is unaffected by this fix -- see
`test_obs_encoder_preview_unchanged_for_unplayable_cards` below.

Run with:  py -m pytest test/test_unplayable_cost.py -v
"""
from __future__ import annotations

import random

from sts2_rl import CombatState
from sts2_rl.cards import (
    AscendersBaneCard,
    BadLuckCard,
    BurnCard,
    ClumsyCard,
    CurseOfTheBellCard,
    DazedCard,
    DebtCard,
    DecayCard,
    DoubtCard,
    FollyCard,
    GreedCard,
    GuiltyCard,
    InfectionCard,
    InjuryCard,
    NormalityCard,
    PoorSleepCard,
    RegretCard,
    ShameCard,
    SootCard,
    WitherCard,
    WoundCard,
    WritheCard,
    make_card,
)
from sts2_rl.previews import preview_card_energy_cost


# The 29 ids from GAP-QUEUE mechanism card/_unplayable_cost. All 29 C#
# constructors were checked directly (`base(-1, ...)`) -- see the task
# report for the per-card citation table.
ALL_29_IDS = (
    "ascenders_bane", "bad_luck", "burn", "byrdonis_egg", "clumsy",
    "curse_of_the_bell", "dazed", "debt", "decay", "disintegration",
    "doubt", "folly", "greed", "guilty", "infection", "injury",
    "lantern_key", "mind_rot", "normality", "poor_sleep", "regret",
    "shame", "sloth", "soot", "spoils_map", "waste_away", "wither",
    "wound", "writhe",
)


def fresh(seed: int = 0) -> CombatState:
    return CombatState(rng=random.Random(seed))


# ── Every one of the 29 reports -1, not 0 ───────────────────────────────────

class TestAll29ReportNegativeOne:
    def test_energy_cost_is_negative_one_for_every_unplayable_card(self):
        for cid in ALL_29_IDS:
            card = make_card(cid)
            assert card.energy_cost == -1, cid
            assert card._energy_cost == -1, cid

    def test_costs_energy_before_modifiers_is_false_for_every_one(self):
        # relics/mummified_hand.py:31's printed-cost filter -- must still
        # exclude every one of the 29 (it did by accident at cost 0; -1 > 0
        # is False too, so the reader's own behaviour is unchanged).
        for cid in ALL_29_IDS:
            card = make_card(cid)
            assert card.costs_energy_before_modifiers() is False, cid

    def test_costs_energy_is_false_for_every_one(self):
        for cid in ALL_29_IDS:
            card = make_card(cid)
            assert card.costs_energy() is False, cid


# ── Wound: the simplest of the 29, used as the canonical example ───────────

class TestWoundReportsNegativeOne:
    def test_wound_reports_negative_one(self):
        wound = WoundCard()
        assert wound.energy_cost == -1
        assert wound._energy_cost == -1

    def test_wound_under_a_curious_shaped_global_modifier_still_reports_negative_one(self):
        """Curious (CuriousPower.cs) is a `modify_card_energy_cost` GLOBAL
        listener gated on `card_type == Power`; it does not touch a Status,
        but the dispatch chain itself is the thing under test here: the
        chain runs over `card.energy_cost` as its seed and the C# analogue
        (`Hook.ModifyEnergyCostInCombat`, CardEnergyCost.cs:116-119) is never
        even CALLED for an unplayable card because `GetWithModifiers` returns
        before reaching it. The sim's `hooks.modify_card_energy_cost` has no
        such short-circuit of its own -- it always clamps its OUTPUT to
        `max(0, cost)` instead (hooks.py:574) -- so the observable result
        (0) matches the game's (0, via GetAmountToSpend's own clamp) even
        though the two sides take different roads to get there."""
        cs = fresh()
        wound = WoundCard()
        wound.combat = cs
        assert wound.energy_cost == -1
        modified = cs.hooks.modify_card_energy_cost(wound, wound.energy_cost)
        assert modified == 0

    def test_wound_under_a_mummified_hand_shaped_local_free_flag_still_reports_negative_one(self):
        """set_free_this_turn mirrors EnergyCost.SetThisTurnOrUntilPlayed(0)
        (what Mummified Hand calls on its pick). C#'s SetThisTurnOrUntilPlayed
        guards `if (cost != 0 || Canonical >= 0)` -- for cost==0 and a
        Canonical<0 card, the game does not even ADD the local modifier,
        because GetWithModifiers would never consult it anyway. The sim's
        setter has no such guard (it always writes `_free_this_turn = True`),
        so this test is the one that actually exercises the property's own
        short-circuit ordering: `_energy_cost < 0` must be checked BEFORE
        `_free_this_turn`."""
        wound = WoundCard()
        wound.set_free_this_turn()
        assert wound.energy_cost == -1

    def test_wound_under_a_set_cost_this_turn_still_reports_negative_one(self):
        """Mirrors Snecko Oil's SetThisTurnOrUntilPlayed(randomised cost) --
        the potion calls this unconditionally on every non-X card in hand,
        including a drawn Wound (test_potions.py's snecko tests never put a
        curse/status in the draw pile, so this is the direct unit-level
        check the integration tests don't exercise)."""
        wound = WoundCard()
        wound.set_cost_this_turn(2)
        assert wound.energy_cost == -1

    def test_wound_under_a_set_cost_this_combat_still_reports_negative_one(self):
        """Mirrors Confused's per-draw SetThisCombat (ConfusedPower.cs) and
        the Slither enchantment's SetThisCombat."""
        wound = WoundCard()
        wound.set_cost_this_combat(2)
        assert wound.energy_cost == -1

    def test_wound_under_a_cost_delta_this_turn_still_reports_negative_one(self):
        """Mirrors AddThisTurn (Pinpoint-shaped relative deltas)."""
        wound = WoundCard()
        wound.add_cost_this_turn(-3)
        assert wound.energy_cost == -1
        wound.add_cost_this_turn(10)
        assert wound.energy_cost == -1


# ── A playable card's cost math is unchanged by the short-circuit ──────────

class TestPlayableCardCostMathUnchanged:
    def test_a_normal_cards_delta_and_floor_still_work(self):
        strike = make_card("strike")
        assert strike._energy_cost >= 0
        base_cost = strike.energy_cost
        strike.add_cost_this_turn(-99)
        assert strike.energy_cost == 0          # still floors at 0
        strike.reset_turn_cost_modifiers()
        assert strike.energy_cost == base_cost

    def test_free_this_turn_still_zeroes_a_playable_card(self):
        bash = make_card("bash")
        assert bash.energy_cost > 0
        bash.set_free_this_turn()
        assert bash.energy_cost == 0

    def test_set_cost_this_combat_still_overrides_a_playable_card(self):
        bash = make_card("bash")
        bash.set_cost_this_combat(5)
        assert bash.energy_cost == 5


# ── Spend path: hooks.modify_card_energy_cost always clamps to >= 0 ────────

class TestSpendPathUnaffected:
    def test_modify_card_energy_cost_clamps_every_one_of_the_29_to_zero(self):
        cs = fresh()
        for cid in ALL_29_IDS:
            card = make_card(cid)
            card.combat = cs
            modified = cs.hooks.modify_card_energy_cost(card, card.energy_cost)
            assert modified == 0, cid

    def test_play_card_still_refuses_an_unplayable_card(self):
        # combat.py's play_card gates on `card.is_playable` before ever
        # reading energy_cost -- confirms the -1 never reaches the spend
        # arithmetic through the manual-play path.
        cs = fresh()
        wound = WoundCard()
        cs.player.hand = [wound]
        before_energy = cs.player.energy
        assert cs.play_card(0) is False
        assert cs.player.energy == before_energy


# ── Observation encoder: encoded value is unchanged by this fix ────────────

class TestObsEncoderPreviewUnchanged:
    def test_preview_card_energy_cost_returns_zero_for_every_one_of_the_29(self):
        """full_env.py's card_features() computes
        `effective_cost = preview_card_energy_cost(s, card)` for every card
        it encodes, including cards still sitting in hand/draw/discard with
        is_playable=False. preview_card_energy_cost routes through
        `hooks.modify_card_energy_cost`, whose own tail clamp (`max(0,
        cost)`) makes its output identical whether the property's local
        result is 0 (pre-fix) or -1 (post-fix) -- so the obs encoding for
        these 29 cards is untouched by this change, by construction, not by
        a special case added to full_env.py."""
        cs = fresh()
        for cid in ALL_29_IDS:
            card = make_card(cid)
            card.combat = cs
            assert preview_card_energy_cost(cs, card) == 0, cid
