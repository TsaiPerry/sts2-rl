"""Port of .NET's `List<T>.Sort()` — the sort inside `ListExtensions.StableShuffle`.

`StableShuffle` (src/Core/Extensions/ListExtensions.cs:22-31) is

    List<T> list2 = list.ToList();
    list2.Sort();                 // <- THIS
    for (int i = 0; i < list.Count; i++) list[i] = list2[i];
    return list.UnstableShuffle(rng);

and the sort is the whole reason the verb exists: it puts the pile into a
canonical order so the Fisher-Yates result does not depend on the incoming
(play) order. The sim reproduced it with Python's `list.sort`, which is
**stable** — and `List<T>.Sort()` is not. It is `ArraySortHelper`'s
INTROSORT: median-of-three quicksort, falling back to heapsort past a depth
limit and to insertion sort at 16 elements or fewer. Elements that compare
equal come out in an order decided by that algorithm, not by their incoming
order, and the two disagree as soon as a partition is larger than the
insertion-sort threshold.

That is not a theoretical difference. It is what walled the 89U21BV1TZ act-2
replay at its Mecha Knight fight: the deck holds two identical un-upgraded
Forgotten Rituals, `CardModel.CompareTo` returns 0 for them
(CardModel.cs:2242-2263 — ModelId, then CurrentUpgradeLevel, then 0), and a
turn-4 reshuffle of a 20-plus-card discard pile put them in the opposite order
from the game. Nothing about the fight LOOKS different — the two cards are
interchangeable in play, and the recording's per-command Hand annotations
matched name-for-name the whole way — but the recorded `PlayCard 12` names one
of them by its `NetCombatCardDb` id, and it resolved to the twin that was still
in the draw pile. Fixing the tie order took the seed's act-2 `forced_combats`
from 5 to 0.

So the tie order is observable, it is not arbitrary, and the only way to get it
right is to run the same algorithm. Transcribed from
`System.Private.CoreLib`'s `ArraySortHelper<T>` / `GenericArraySortHelper<T>`
(the two share this algorithm; the generic specialization only inlines the
comparison). `key` has Python's `sort(key=...)` meaning and stands in for
`CompareTo`: keys are compared with `<` / `>`, exactly as the callers'
`_compare_to_key` tuples already are.
"""
from __future__ import annotations

# `ArraySortHelper.IntrosortSizeThreshold`.
_INTROSORT_SIZE_THRESHOLD = 16


def dotnet_list_sort(items: list, key=None) -> list:
    """Sort `items` IN PLACE the way `List<T>.Sort()` does, and return it.

    Equal elements are ordered by the algorithm, not by their incoming
    positions — that is the entire point; see the module docstring.
    """
    n = len(items)
    if n <= 1:
        return items
    keys = [key(x) for x in items] if key is not None else list(items)
    # `IntrospectiveSort`: depthLimit = 2 * (BitOperations.Log2(length) + 1),
    # and Log2 of a positive int is `bit_length() - 1`.
    _intro_sort(items, keys, 0, n - 1, 2 * n.bit_length())
    return items


def _swap(a: list, k: list, i: int, j: int) -> None:
    a[i], a[j] = a[j], a[i]
    k[i], k[j] = k[j], k[i]


def _swap_if_greater(a: list, k: list, i: int, j: int) -> None:
    """`SwapIfGreater` — note the `i != j` guard is C#'s, not defensive."""
    if i != j and k[i] > k[j]:
        _swap(a, k, i, j)


def _insertion_sort(a: list, k: list, lo: int, hi: int) -> None:
    """`InsertionSort` (which IS stable — this is why small piles never showed
    the divergence)."""
    for i in range(lo, hi):
        t, tk = a[i + 1], k[i + 1]
        j = i
        while j >= lo and tk < k[j]:
            a[j + 1], k[j + 1] = a[j], k[j]
            j -= 1
        a[j + 1], k[j + 1] = t, tk


def _down_heap(a: list, k: list, lo: int, i: int, n: int) -> None:
    """`DownHeap`, with C#'s 1-based `i`/`n` over the partition starting at
    `lo`."""
    d, dk = a[lo + i - 1], k[lo + i - 1]
    while i <= n >> 1:
        child = 2 * i
        if child < n and k[lo + child - 1] < k[lo + child]:
            child += 1
        if not dk < k[lo + child - 1]:
            break
        a[lo + i - 1], k[lo + i - 1] = a[lo + child - 1], k[lo + child - 1]
        i = child
    a[lo + i - 1], k[lo + i - 1] = d, dk


def _heap_sort(a: list, k: list, lo: int, hi: int) -> None:
    """`HeapSort` — the depth-limit fallback that keeps introsort O(n log n)."""
    n = hi - lo + 1
    for i in range(n >> 1, 0, -1):
        _down_heap(a, k, lo, i, n)
    for i in range(n, 1, -1):
        _swap(a, k, lo, lo + i - 1)
        _down_heap(a, k, lo, 1, i - 1)


def _pick_pivot_and_partition(a: list, k: list, lo: int, hi: int) -> int:
    """`PickPivotAndPartition`: median-of-three (lo, middle, hi), pivot parked
    at `hi - 1`, then the two-sided scan.

    The scans are unguarded in C# for a reason worth keeping in mind when
    reading them here: the median-of-three leaves `a[lo] <= pivot <= a[hi]`, so
    each scan is stopped by a sentinel rather than by a bound check.
    """
    middle = lo + ((hi - lo) >> 1)
    _swap_if_greater(a, k, lo, middle)
    _swap_if_greater(a, k, lo, hi)
    _swap_if_greater(a, k, middle, hi)
    pivot_k = k[middle]
    _swap(a, k, middle, hi - 1)
    left, right = lo, hi - 1
    while left < right:
        left += 1
        while k[left] < pivot_k:
            left += 1
        right -= 1
        while pivot_k < k[right]:
            right -= 1
        if left >= right:
            break
        _swap(a, k, left, right)
    if left != hi - 1:
        _swap(a, k, left, hi - 1)
    return left


def _intro_sort(a: list, k: list, lo: int, hi: int, depth_limit: int) -> None:
    """`IntroSort`: loop on the LEFT partition, recurse on the right."""
    while hi > lo:
        size = hi - lo + 1
        if size <= _INTROSORT_SIZE_THRESHOLD:
            if size == 2:
                _swap_if_greater(a, k, lo, hi)
                return
            if size == 3:
                _swap_if_greater(a, k, lo, hi - 1)
                _swap_if_greater(a, k, lo, hi)
                _swap_if_greater(a, k, hi - 1, hi)
                return
            _insertion_sort(a, k, lo, hi)
            return
        if depth_limit == 0:
            _heap_sort(a, k, lo, hi)
            return
        depth_limit -= 1
        p = _pick_pivot_and_partition(a, k, lo, hi)
        # "we've already partitioned around the pivot and do not have to move
        # the pivot again" — the right half recurses, the left half loops.
        _intro_sort(a, k, p + 1, hi, depth_limit)
        hi = p - 1
