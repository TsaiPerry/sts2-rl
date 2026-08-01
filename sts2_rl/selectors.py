"""Scripted deterministic card selector for ``CombatState.card_selector``.

Mid-resolution card selections (Armaments' upgrade pick, Burning Pact's
exhaust pick, ...) are synchronous callbacks the engine cannot pause on
(RL.md section 2). The engine's default resolves them uniformly at random
with the combat RNG; :func:`scripted_card_selector` replaces that with a
cheap deterministic heuristic (RL.md wiring option 2) so training sees no
hidden stochasticity from selection effects:

* ``"upgrade"``     — the highest-cost upgradable card (X-cost counts as
  the most expensive; upgrading the biggest card gains the most).
* ``"exhaust"``     — a Status/Curse first (they are dead weight), then
  hand order.
* ``"to_draw_top"`` — the cheapest attack, then the cheapest card.
* ``"curse_of_knowledge"`` — the least crippling of the Knowledge Demon's
  permanent-curse pair (see ``_CURSE_OF_KNOWLEDGE_RANK``).
* ``"gambling_chip"``, ``"exhaust_any"``, ``"discard_any"`` — only
  Status/Curse cards. These are the MinSelect-0 screens (Gambling Chip's
  mulligan, Ashwater, Gambler's Brew): the game always shows them and lets
  the player confirm *any number* including none, so the pick filters the
  candidates instead of taking ``count`` of them. Junk is worth
  exhausting/redrawing, everything else is kept.
* ``"choose_a_card"``, ``"choose_a_card_optional"`` — the cheapest playable
  card, junk last. These are the generator screens: the four generator
  potions and Toolbox go through ``CardSelectCmd.FromChooseACardScreen``
  (no auto-select shortcut at all — ``select_cards`` is called with
  ``has_shortcut=False``); Choices Paradox actually goes through
  ``CardSelectCmd.FromSimpleGrid`` instead (it DOES have the shortcut) but
  shares the ``"choose_a_card"`` purpose label since the heuristic below
  doesn't need to distinguish them. All three create fresh cards and offer
  three-to-five. The card is free, so the only question is whether it can be
  played this turn — cheapest wins, ties by offered order. ``*_optional`` is
  the ``canSkip: true`` twin, so an all-junk screen is declined instead of
  taking dead weight; the non-optional ones have to take something.
* any other purpose — the first candidates, in offered order.

Every branch is a stable sort over the candidate order, so ties resolve
to hand/pile position and the choice is a pure function of the candidate
list — no RNG draws, no state reads, no mutation.
"""
from __future__ import annotations

from .cards import Card, CardType

# Sort rank for X-cost cards: above any printed cost, so "highest-cost"
# treats them as the most expensive and "cheapest" as the least attractive.
_X_COST_RANK = 99


def _cost(card: Card) -> int:
    return _X_COST_RANK if card.energy_cost_x else card.energy_cost


def _is_junk(card: Card) -> bool:
    return card.card_type in (CardType.STATUS, CardType.CURSE)


# Knowledge Demon curse picks, least crippling first. Sloth (play ≤3 cards a
# turn) is barely felt at 3 energy; Mind Rot (−1 draw) costs a card of options;
# Disintegration (6/7/8 damage every turn) bleeds real HP over a 379-HP boss
# fight but leaves the turn engine intact; Waste Away (−1 energy) cuts a third
# of every remaining turn — take Disintegration over that. Net result across
# the boss's three pairs: Mind Rot, Sloth, then Disintegration — never two
# Disintegrations stacking and never the energy loss.
_CURSE_OF_KNOWLEDGE_RANK = {
    "sloth": 0,
    "mind_rot": 1,
    "disintegration": 2,
    "waste_away": 3,
}


def scripted_card_selector(
    purpose: str, candidates: list[Card], count: int
) -> list[Card]:
    """Deterministic (purpose, candidates, count) -> chosen cards.

    Plug into ``CombatState.card_selector`` (the env installs it by
    default). Returns the ``count`` best candidates per the purpose
    heuristics above; unknown purposes keep the offered order.
    """
    keyed = list(enumerate(candidates))
    if purpose == "upgrade":
        keyed.sort(key=lambda p: (not p[1].is_upgradable, -_cost(p[1]), p[0]))
    elif purpose == "exhaust":
        keyed.sort(key=lambda p: (not _is_junk(p[1]), p[0]))
    elif purpose == "to_draw_top":
        keyed.sort(
            key=lambda p: (p[1].card_type is not CardType.ATTACK, _cost(p[1]), p[0])
        )
    elif purpose == "curse_of_knowledge":
        keyed.sort(
            key=lambda p: (_CURSE_OF_KNOWLEDGE_RANK.get(p[1].id, len(_CURSE_OF_KNOWLEDGE_RANK)), p[0])
        )
    elif purpose in ("gambling_chip", "exhaust_any", "discard_any"):
        # A MinSelect-0 screen picks 0..count cards: toss only the dead weight
        # (Statuses/Curses) and keep everything playable. Gambling Chip's
        # turn-1 mulligan, Ashwater's exhaust and Gambler's Brew's discard all
        # build CardSelectorPrefs(prompt, 0, ...), which CardSelectCmd.cs:708
        # never auto-resolves.
        keyed = [p for p in keyed if _is_junk(p[1])]
    elif purpose in ("choose_a_card", "choose_a_card_optional"):
        # `CardSelectCmd.FromChooseACardScreen` — a screen of freshly created
        # cards (the four generator potions, Toolbox, Choices Paradox). The
        # card costs nothing to take, so rank by whether it can be played this
        # turn: junk last, then cheapest, ties by offered order. The selector
        # used to fall through to "the first candidate", which took whatever
        # the generator happened to roll first.
        keyed.sort(key=lambda p: (_is_junk(p[1]), _cost(p[1]), p[0]))
        if purpose == "choose_a_card_optional":
            # The canSkip:true twin (CardSelectCmd.cs:216-261). Declining is a
            # real outcome, so an all-junk screen takes nothing; Toolbox and
            # Choices Paradox (canSkip:false) must still take one.
            keyed = [p for p in keyed if not _is_junk(p[1])]
    return [card for _, card in keyed[:count]]
