"""Tests for sts2_rl/selectors.py — the scripted deterministic card selector.

scripted_card_selector is the training default plugged into
CombatState.card_selector by STS2FullCombatEnv (RL.md wiring option 2). It
must be a pure function of (purpose, candidates, count): no RNG, no state
reads, no mutation — so training sees no hidden stochasticity from
mid-resolution selection effects.

Run with:  py -m pytest test/test_selectors.py -v
"""
from __future__ import annotations

import random

from sts2_rl import CombatState, make_card, scripted_card_selector
from sts2_rl.monsters import FUZZY_WURM_ENCOUNTER


# ── Purpose heuristics ────────────────────────────────────────────────────────


def test_upgrade_picks_highest_cost():
    strike, defend, bludgeon = make_card("strike"), make_card("defend"), make_card("bludgeon")
    assert scripted_card_selector("upgrade", [strike, defend, bludgeon], 1) == [bludgeon]


def test_upgrade_treats_x_cost_as_most_expensive():
    bludgeon, whirlwind = make_card("bludgeon"), make_card("whirlwind")
    assert scripted_card_selector("upgrade", [bludgeon, whirlwind], 1) == [whirlwind]


def test_upgrade_prefers_upgradable():
    bludgeon, strike = make_card("bludgeon"), make_card("strike")
    bludgeon.upgrade()                         # at max level → not upgradable
    assert scripted_card_selector("upgrade", [bludgeon, strike], 1) == [strike]


def test_exhaust_picks_status_and_curse_first():
    strike, wound, clumsy = make_card("strike"), make_card("wound"), make_card("clumsy")
    assert scripted_card_selector("exhaust", [strike, wound], 1) == [wound]
    assert scripted_card_selector("exhaust", [strike, wound, clumsy], 2) == [wound, clumsy]
    # No junk in hand → hand order.
    defend = make_card("defend")
    assert scripted_card_selector("exhaust", [strike, defend], 1) == [strike]


def test_to_draw_top_picks_cheapest_attack():
    defend, bludgeon, strike = make_card("defend"), make_card("bludgeon"), make_card("strike")
    assert scripted_card_selector("to_draw_top", [defend, bludgeon, strike], 1) == [strike]
    # No attack among candidates → cheapest card.
    assert scripted_card_selector("to_draw_top", [make_card("impervious"), defend], 1) == [defend]


def test_to_draw_top_clamps_unplayable_cost_to_tie_at_zero():
    """Round 13 R11 item 3. `Card.energy_cost` reads an unplayable card's
    canonical -1 back verbatim (cards/base.py:421-434 -- CardEnergyCost.cs
    :100-103's `if (_base < 0) return num;`, Wound.cs `base(-1, ...)`); the
    to_draw_top tie-break used to read that -1 raw, so a junk card sorted as
    CHEAPER than a genuinely free 0-cost card (like Thinking Ahead,
    colorless_skills.py:835) and won the pick regardless of offered order.

    BOTH assertions are load-bearing and they pin DIFFERENT wrong answers:

    * offered second, the Wound must LOSE -- RED against the round-12 body
      (`return card.energy_cost`), where -1 out-ranks 0 in either order;
    * offered FIRST, the Wound must WIN -- RED against a "rank unplayables
      LAST" body (e.g. `return 98 if card.energy_cost < 0 else ...`), which
      satisfies the first assertion but is a demotion, not a tie.

    Only `max(0, ...)` -- a genuine tie at 0 resolved by the stable sort's
    offered-order tiebreak -- satisfies both. (Round 13 R11 fix pass: the
    original test asserted only the first order and passed under the
    deliberately-wrong "rank last" body, so it did not pin the tie its own
    name claims.)"""
    thinking_ahead, wound = make_card("thinking_ahead"), make_card("wound")
    assert wound.energy_cost == -1
    assert thinking_ahead.energy_cost == 0
    assert scripted_card_selector(
        "to_draw_top", [thinking_ahead, wound], 1
    ) == [thinking_ahead]
    assert scripted_card_selector(
        "to_draw_top", [wound, thinking_ahead], 1
    ) == [wound]


def test_no_unplayable_card_is_upgradable():
    """The enumeration behind "the clamp is inert at the `upgrade` consumer".

    `_cost` has THREE consumers (selectors.py:89 `upgrade`, :94
    `to_draw_top`, :114 `choose_a_card`/`choose_a_card_optional`). The
    `upgrade` branch's leading sort key is `not is_upgradable`, so `_cost`
    can only decide between two cards that are BOTH upgradable -- and no
    card with a negative (unplayable) cost is upgradable, so the clamp can
    never change that branch's answer. That premise is what this test pins:
    if a future unplayable card ever becomes upgradable, the inertness claim
    in selectors.py's `_cost` comment stops holding and this fires."""
    from sts2_rl.cards.base import _CARD_CLASSES

    unplayables = [c for c in (make_card(cid) for cid in _CARD_CLASSES)
                   if c.energy_cost < 0]
    # CardEnergyCost's sentinel is exactly -1, never any other negative.
    assert {c.energy_cost for c in unplayables} == {-1}
    assert {c.card_type.name for c in unplayables} == {"CURSE", "QUEST", "STATUS"}
    assert [c.id for c in unplayables if c.is_upgradable] == []
    assert [c.id for c in unplayables if c.energy_cost_x] == []


def test_choose_a_card_clamp_reaches_the_quest_unplayables_too():
    """The third `_cost` consumer (selectors.py:114), which the clamp is NOT
    inert at.

    `_is_junk` is `card_type in (STATUS, CURSE)` -- it does not cover the
    three QUEST unplayables (Lantern Key, Byrdonis Egg, Spoils Map), so they
    sort past the junk key and reach `_cost` in the choose-a-card branch.
    Post-clamp they TIE a genuinely free playable (offered order decides)
    instead of out-ranking it, and they still beat a card that actually
    costs energy. Same two-order structure as the to_draw_top test: order A
    is RED against the round-12 raw -1, order B is RED against "rank
    unplayables last"."""
    from sts2_rl.cards import CardType

    for quest_id in ("lantern_key", "byrdonis_egg", "spoils_map"):
        quest = make_card(quest_id)
        assert quest.card_type is CardType.QUEST
        assert quest.energy_cost == -1
        for purpose in ("choose_a_card", "choose_a_card_optional"):
            free = make_card("thinking_ahead")
            assert scripted_card_selector(purpose, [free, quest], 1) == [free]
            quest_first = make_card(quest_id)
            assert scripted_card_selector(
                purpose, [quest_first, make_card("thinking_ahead")], 1
            ) == [quest_first]
            # A 1-cost card (Defend) is genuinely more expensive than the
            # clamped 0, so the clamp is a tie at zero and not a demotion.
            paid = make_card(quest_id)
            assert scripted_card_selector(
                purpose, [make_card("defend"), paid], 1
            ) == [paid]


def test_choose_a_card_screens_cannot_offer_an_unplayable_card_today():
    """Dormancy witness for the delta the test above pins.

    Every live `choose_a_card` / `choose_a_card_optional` call site builds
    its candidates by GENERATING cards from a pool -- Toolbox
    (relics/toolbox.py:46, COLORLESS_POOL), Choice's Paradox
    (relics/choices_paradox.py:56, `combat.card_pool`) and the four
    generator potions (potions.py:1408, `combat.card_pool` / COLORLESS_POOL)
    -- and no unplayable card is in any of those pools. So the QUEST
    ordering change above cannot be reached through today's call sites; it
    is a latent correctness improvement, not a live behaviour change. If a
    character pool ever gains an unplayable card this fires and the dormancy
    claim has to be re-derived."""
    from sts2_rl.cards.base import _CARD_CLASSES
    from sts2_rl.cards.pool import COLORLESS_POOL
    from sts2_rl.characters import CHARACTERS

    unplayable_ids = {cid for cid in _CARD_CLASSES
                      if make_card(cid).energy_cost < 0}
    pools = {"COLORLESS_POOL": COLORLESS_POOL}
    for char in CHARACTERS.values():
        pools[f"{char.id}.card_pool"] = char.card_pool
    for name, pool in pools.items():
        assert not (unplayable_ids & set(pool)), name


def test_curse_of_knowledge_picks_least_crippling():
    # The Knowledge Demon's three pairs: Disintegration is offered first each
    # time; the heuristic dodges it except against Waste Away (−1 energy).
    dis = make_card("disintegration")
    assert scripted_card_selector(
        "curse_of_knowledge", [dis, make_card("mind_rot")], 1
    )[0].id == "mind_rot"
    assert scripted_card_selector(
        "curse_of_knowledge", [dis, make_card("sloth")], 1
    )[0].id == "sloth"
    assert scripted_card_selector(
        "curse_of_knowledge", [dis, make_card("waste_away")], 1
    )[0].id == "disintegration"


def test_unknown_purpose_keeps_offered_order():
    cards = [make_card("defend"), make_card("bludgeon"), make_card("strike")]
    assert scripted_card_selector("???", list(cards), 1) == [cards[0]]
    assert scripted_card_selector("???", list(cards), 2) == cards[:2]


def test_selector_is_pure():
    cards = [make_card("strike"), make_card("wound"), make_card("bludgeon")]
    before = list(cards)
    chosen = scripted_card_selector("exhaust", cards, 2)
    assert cards == before                     # candidate list not reordered
    assert all(c in before for c in chosen)
    assert len(set(map(id, chosen))) == len(chosen)


# ── Wiring ────────────────────────────────────────────────────────────────────


def test_combat_select_cards_routes_through_installed_selector():
    c = CombatState(rng=random.Random(0), encounter=FUZZY_WURM_ENCOUNTER)
    c.card_selector = scripted_card_selector
    strike, wound = make_card("strike"), make_card("wound")
    assert c.select_cards("exhaust", [strike, wound], 1) == [wound]


def test_env_installs_scripted_selector_by_default():
    from sts2_rl import STS2FullCombatEnv

    env = STS2FullCombatEnv()
    env.reset(seed=0)
    assert env._state.card_selector is scripted_card_selector
    # card_selector=None opts back into the engine's seeded-random default.
    env_random = STS2FullCombatEnv(card_selector=None)
    env_random.reset(seed=0)
    assert env_random._state.card_selector is None
