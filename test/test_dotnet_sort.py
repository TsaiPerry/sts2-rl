# test/test_dotnet_sort.py
"""`dotnet_list_sort` — the port of `List<T>.Sort()` inside StableShuffle."""
from __future__ import annotations

import random

from sts2_rl.dotnet_sort import dotnet_list_sort


def test_it_sorts():
    """Whatever it does with ties, it is still a sort."""
    rng = random.Random(1234)
    for n in range(0, 120):
        data = [rng.randrange(20) for _ in range(n)]
        got = list(data)
        dotnet_list_sort(got)
        assert got == sorted(data), n


def test_it_sorts_by_key():
    rng = random.Random(99)
    for n in range(0, 80):
        data = [(rng.randrange(6), i) for i in range(n)]
        got = list(data)
        dotnet_list_sort(got, key=lambda x: x[0])
        assert [x[0] for x in got] == sorted(x[0] for x in data), n
        assert sorted(got) == sorted(data), n     # a permutation, nothing lost


def test_small_partitions_are_insertion_sorted_and_therefore_stable():
    """`IntroSort` hands anything of 16 elements or fewer to `InsertionSort`,
    which IS stable — which is exactly why this divergence stayed hidden for so
    long: every small pile agrees with Python's sort."""
    for n in range(1, 17):
        data = [(0, i) for i in range(n)]         # every element ties
        got = list(data)
        dotnet_list_sort(got, key=lambda x: x[0])
        assert got == data, n


def test_a_large_all_ties_partition_is_NOT_stable():
    """Past the threshold the quicksort partition reorders equal elements. This
    is the whole point of the port: with a stable sort the assertion below
    would be `== data`, and the 89U act-2 Mecha Knight reshuffle would keep
    picking the wrong one of two identical Forgotten Rituals."""
    data = [(0, i) for i in range(40)]
    got = list(data)
    dotnet_list_sort(got, key=lambda x: x[0])
    assert sorted(got) == data                    # same elements …
    assert got != data                            # … different order


def test_the_reshuffle_uses_it():
    """The stabilizing sort in `PlayerCombatState._shuffle_cards` is this sort,
    not `list.sort` — a parity reshuffle of a pile with more than 16 equal
    cards must not come back in incoming order."""
    from sts2_rl.combat import CombatState
    from sts2_rl.cards import make_card
    from sts2_rl.rng import RunRngSet

    deck = [make_card("strike") for _ in range(40)]
    combat = CombatState(starting_deck=deck, rng_set=RunRngSet("introsort-seed"))
    player = combat.player
    incoming = [make_card("strike") for _ in range(40)]
    for card in incoming:
        card.combat = combat
    player.draw_pile = []
    player.discard_pile = list(incoming)
    player.reshuffle_discard_into_draw()
    # `_shuffle_cards` reverses at the end (game top-first -> sim top-last), so
    # undo that to compare against what the sort+Fisher-Yates produced.
    produced = list(reversed(player.draw_pile))
    assert sorted(id(c) for c in produced) == sorted(id(c) for c in incoming)

    # Same pile, same stream, but sorted stably instead: a different order.
    stable = list(incoming)
    stable.sort(key=lambda c: (c.id.upper(), c.upgrade_level))
    assert [id(c) for c in stable] == [id(c) for c in incoming]   # stable == no-op
    dotnet = list(incoming)
    dotnet_list_sort(dotnet, key=lambda c: (c.id.upper(), c.upgrade_level))
    assert [id(c) for c in dotnet] != [id(c) for c in stable]
