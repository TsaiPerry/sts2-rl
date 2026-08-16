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
    """Sort rank for a card's energy cost. -1 is a sentinel, not a price.

    `Card.energy_cost` reads an unplayable card's canonical -1 back verbatim
    (cards/base.py's `if self._energy_cost < 0: return self._energy_cost`,
    mirroring `CardEnergyCost.GetWithModifiers`'s `if (_base < 0) return
    num;` short-circuit at CardEnergyCost.cs:100-103 -- Wound.cs is
    `base(-1, CardType.Status, ...)`). That -1 is a flag meaning "cannot be
    played", immune to every cost modifier; reading it as a NUMBER made an
    unplayable card rank cheaper than a genuinely free 0-cost card. Clamped
    to 0 so it TIES instead.

    THREE consumers read this:

    * `"upgrade"` (:121, negated) -- INERT. Its leading sort key is
      `not is_upgradable`, and none of the 29 unplayable cards is upgradable
      (pinned: test_selectors.py::test_no_unplayable_card_is_upgradable), so
      `_cost` only ever decides between two upgradable cards, whose costs
      are all >= 0. An all-unplayable screen is a total tie under both the
      old and the new body, so the offered-order tiebreak decides either way.
    * `"to_draw_top"` (:125) -- the LIVE delta this clamp exists for. Both
      call sites read a real pile that holds junk (Thinking Ahead reads the
      hand, colorless_skills.py:845; Headbutt reads the discard pile,
      headbutt.py:43).
    * `"choose_a_card"` / `"choose_a_card_optional"` (:146) -- a real but
      currently UNREACHABLE delta. `_is_junk` is STATUS|CURSE only, so the
      three QUEST unplayables (Lantern Key, Byrdonis Egg, Spoils Map) sort
      past the junk key and reach `_cost`; post-clamp they tie a free
      playable instead of out-ranking it. No live call site can offer one
      today (candidates always come from a pool with no unplayable cards),
      pinned in test_selectors.py.
    """
    return _X_COST_RANK if card.energy_cost_x else max(0, card.energy_cost)


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
