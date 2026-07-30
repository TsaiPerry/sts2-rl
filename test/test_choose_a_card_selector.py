"""`scripted_card_selector`'s arm for the generator screens.

`CardSelectCmd.FromChooseACardScreen` is the three-card offer behind the four
generator potions (Attack / Skill / Power / Colorless), Toolbox and Choices
Paradox. Skippability is per-SCREEN in the source, which is why the sim has two
purposes: `choose_a_card` (Toolbox.cs:28, ChoicesParadox.cs:46 — `canSkip:
false`) and `choose_a_card_optional` (CardSelectCmd.cs:216-261 — `canSkip:
true`).

Until this arm existed the selector fell through to "the first candidate", so
the training env always took whatever the generator rolled first and could
never decline. That was the observable the four potion records were verdicted
on.
"""
from __future__ import annotations

from sts2_rl.cards import make_card
from sts2_rl.selectors import scripted_card_selector


def _ids(cards):
    return [c.id for c in cards]


def test_it_takes_the_cheapest_playable_card():
    # bludgeon 3, strike 1, pommel_strike 1 (offered after strike)
    offered = [make_card("bludgeon"), make_card("strike"),
               make_card("pommel_strike")]
    assert _ids(scripted_card_selector("choose_a_card", offered, 1)) == ["strike"]


def test_ties_resolve_to_the_offered_order():
    offered = [make_card("pommel_strike"), make_card("strike")]
    assert _ids(scripted_card_selector("choose_a_card", offered, 1)) == [
        "pommel_strike"]


def test_junk_goes_last_but_the_non_skippable_screen_still_takes_one():
    """Toolbox and Choices Paradox pass `canSkip: false`, so the screen has to
    return a card even when every option is dead weight."""
    offered = [make_card("dazed"), make_card("wound")]
    picked = scripted_card_selector("choose_a_card", offered, 1)
    assert len(picked) == 1


def test_junk_is_preferred_last_when_a_real_card_is_offered():
    offered = [make_card("dazed"), make_card("bludgeon")]
    assert _ids(scripted_card_selector("choose_a_card", offered, 1)) == [
        "bludgeon"]


def test_the_optional_screen_declines_an_all_junk_offer():
    offered = [make_card("dazed"), make_card("wound"), make_card("burn")]
    assert scripted_card_selector("choose_a_card_optional", offered, 1) == []


def test_the_optional_screen_still_takes_a_real_card():
    offered = [make_card("dazed"), make_card("strike")]
    assert _ids(scripted_card_selector("choose_a_card_optional", offered, 1)) == [
        "strike"]


def test_an_x_cost_card_ranks_as_the_most_expensive():
    """`_X_COST_RANK` — the same convention the "upgrade" arm uses, so an
    X-cost card is never the cheapest-playable pick."""
    offered = [make_card("whirlwind"), make_card("bludgeon")]
    assert _ids(scripted_card_selector("choose_a_card", offered, 1)) == [
        "bludgeon"]


def test_a_generator_potion_takes_the_cheapest_of_its_three():
    """End to end through the potion, with the env's default selector."""
    import random

    from sts2_rl.combat import CombatState
    from sts2_rl.potions import make_potion
    from sts2_rl.selectors import scripted_card_selector as sel

    cs = CombatState(rng=random.Random(3), card_selector=sel)
    before = len(cs.player.hand)
    offered: list[list] = []
    real = cs.card_selector

    def spy(purpose, cands, count, **kw):
        if purpose == "choose_a_card_optional":
            offered.append(list(cands))
        return real(purpose, cands, count, **kw) if kw else real(
            purpose, cands, count)

    cs.card_selector = spy
    potion = make_potion("skill_potion")
    cs.player.potions[0] = potion
    cs.use_potion(0)

    assert offered, "the potion never opened a choose-a-card screen"
    cheapest = min(offered[0], key=lambda c: (c.energy_cost_x, c.energy_cost))
    taken = cs.player.hand[before:]
    assert len(taken) == 1
    assert taken[0].energy_cost == cheapest.energy_cost
