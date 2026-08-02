"""The Crystal Sphere reveal minigame — a port of
src/Core/Events/Custom/CrystalSphereEvent/ (CrystalSphereMinigame.cs,
CrystalSphereCell.cs, CrystalSphereItem.cs, CrystalSphereItems/*.cs).

An 11x11 fog grid holding 15 randomly-placed items. Each "divination" clears
one cell (Small tool) or a 3x3 block (Big tool); an item fires its reveal only
once EVERY cell it occupies is clear (AreAllOccupiedCellsClear, :315-330).

Pure engine: it knows nothing about RunState. Placement randomness arrives as
`pick` (the source's `Rng.NextItem`) and the one reveal that has an immediate
side effect — the curse — is handed back through `on_reveal`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Sequence

GRID_WIDTH = 11   # CrystalSphereMinigame._defaultWidth
GRID_HEIGHT = 11  # CrystalSphereMinigame._defaultHeight

# CrystalSphereMinigame.CrystalSphereToolType — the ordinals RunReplays records
# in its `CrystalSphereClick {x} {y} {tool}` command.
TOOL_NONE, TOOL_SMALL, TOOL_BIG = 0, 1, 2


class ItemKind(Enum):
    RELIC = "relic"
    POTION = "potion"
    CARD = "card"
    CURSE = "curse"
    GOLD = "gold"


@dataclass
class Item:
    """One CrystalSphereItem. `size` is (Size.X, Size.Y) and `pos` its
    top-left (Position) once placed; an item that never found a legal spot
    keeps `pos is None` and can never be revealed."""

    kind: ItemKind
    size: tuple[int, int]
    is_good: bool
    rarity: str | None = None   # potion / card rarity
    is_big: bool = False        # gold only
    pos: tuple[int, int] | None = None

    def cells(self) -> list[tuple[int, int]]:
        if self.pos is None:
            return []
        px, py = self.pos
        w, h = self.size
        return [(px + i, py + j) for i in range(w) for j in range(h)]


class CrystalSphereMinigame:
    def __init__(
        self,
        pick: Callable[[Sequence], object],
        divinations: int,
        on_reveal: Callable[[Item], None] | None = None,
    ) -> None:
        self._pick = pick
        self._on_reveal = on_reveal
        self.divinations = divinations
        self.width = GRID_WIDTH
        self.height = GRID_HEIGHT
        self._hidden = [[True] * self.height for _ in range(self.width)]
        self._item_at: list[list[Item | None]] = [
            [None] * self.height for _ in range(self.width)
        ]
        self.items: list[Item] = []
        self.revealed: list[Item] = []
        # CrystalSphereMinigame.cs:104-125 — seed the four corners, expand the
        # list TWICE by horizontal+vertical neighbours, then clear every entry.
        # The intermediate list is duplicate-laden; the duplicates are inert
        # because `_clear_cell` early-returns on an already-visible cell and no
        # item has been placed yet, so this reproduces the source exactly
        # without needing to reproduce its list arithmetic.
        spots = [
            (0, 0),
            (self.width - 1, 0),
            (self.width - 1, self.width - 1),
            (0, self.width - 1),
        ]
        for _ in range(2):
            spots = (
                spots
                + [c for s in spots for c in self._horizontal(*s)]
                + [c for s in spots for c in self._vertical(*s)]
            )
        for x, y in spots:
            self._clear_cell(x, y)
        # `do { PlacedAllItems = PopulateItems(); n++ } while (!PlacedAllItems
        # && n < 10)` (:126-132).
        attempts = 0
        self.placed_all_items = False
        while not self.placed_all_items and attempts < 10:
            self.placed_all_items = self._populate_items()
            attempts += 1

    # ── Item population (PopulateItems, :159-203) ────────────────────────

    def _populate_items(self) -> bool:
        ok = True

        def add(item: Item) -> None:
            nonlocal ok
            # `flag = flag && item.PlaceItem(this); _items.Add(item)`. C#'s &&
            # SHORT-CIRCUITS, so once one placement has failed every later item
            # is appended WITHOUT being placed — it stays off the board and can
            # never be revealed, while still occupying a slot in `_items`. That
            # is a source bug; it is reproduced here rather than corrected
            # because `_items` is observable through the reveal path.
            if ok:
                ok = self._place(item)
            self.items.append(item)

        add(Item(ItemKind.RELIC, (4, 4), True))
        for _ in range(2):
            add(Item(ItemKind.POTION, (1, 3), True, rarity="common"))
        add(Item(ItemKind.POTION, (2, 2), True, rarity="rare"))
        for rarity in ("common", "uncommon", "rare"):
            add(Item(ItemKind.CARD, (2, 2), True, rarity=rarity))
        add(Item(ItemKind.CURSE, (2, 2), False))
        for _ in range(5):
            add(Item(ItemKind.GOLD, (1, 1), True))
        for _ in range(2):
            add(Item(ItemKind.GOLD, (2, 1), True, is_big=True))
        return ok

    def _place(self, item: Item) -> bool:
        """CrystalSphereItem.PlaceItem — enumerate every legal top-left with x
        OUTER, then spend exactly one `Rng.NextItem` on the list."""
        candidates = [
            (x, y)
            for x in range(self.width)
            for y in range(self.height)
            if self._can_place(item, x, y)
        ]
        if not candidates:
            return False
        item.pos = self._pick(candidates)
        for cx, cy in item.cells():
            self._item_at[cx][cy] = item
        return True

    def _can_place(self, item: Item, x: int, y: int) -> bool:
        """CanPlaceHere (CrystalSphereItem.cs:74-101): the whole footprint must
        be in bounds, still hidden (so the pre-cleared corners are excluded)
        and unoccupied."""
        w, h = item.size
        for i in range(w):
            for j in range(h):
                cx, cy = x + i, y + j
                if not (0 <= cx < self.width and 0 <= cy < self.height):
                    return False
                if not self._hidden[cx][cy]:
                    return False
                if self._item_at[cx][cy] is not None:
                    return False
        return True

    # ── Board queries ────────────────────────────────────────────────────

    def is_hidden(self, x: int, y: int) -> bool:
        return self._hidden[x][y]

    def item_at(self, x: int, y: int) -> Item | None:
        return self._item_at[x][y]

    @property
    def is_finished(self) -> bool:
        return self.divinations == 0

    def hidden_cells(self) -> list[tuple[int, int]]:
        return [
            (x, y)
            for x in range(self.width)
            for y in range(self.height)
            if self._hidden[x][y]
        ]

    # ── Clicking (CellClicked, :259-278) ─────────────────────────────────

    def click(self, x: int, y: int, tool: int = TOOL_BIG) -> None:
        if not (0 <= x < self.width and 0 <= y < self.height):
            raise ValueError(f"[{x},{y}] is not a valid cell on this grid")
        # The decrement is unconditional and comes FIRST — clicking ground that
        # is already clear still burns the divination.
        self.divinations -= 1
        if tool != TOOL_BIG:
            self._clear_cell(x, y)
        else:
            for cx, cy in self._adjacent(x, y):
                self._clear_cell(cx, cy)

    # ── Reveal (ClearCell, :285-308) ─────────────────────────────────────

    def _clear_cell(self, x: int, y: int) -> None:
        if not (0 <= x < self.width and 0 <= y < self.height):
            raise ValueError(f"[{x},{y}] is not a valid cell on this grid")
        if not self._hidden[x][y]:
            return
        self._hidden[x][y] = False
        item = self._item_at[x][y]
        if item is not None and all(
            not self._hidden[cx][cy] for cx, cy in item.cells()
        ):
            self.revealed.append(item)
            if self._on_reveal is not None:
                self._on_reveal(item)

    # ── Neighbourhoods (:339-389) ────────────────────────────────────────

    def _horizontal(self, x: int, y: int) -> list[tuple[int, int]]:
        return [(x + d, y) for d in (-1, 1) if 0 <= x + d < GRID_WIDTH]

    def _vertical(self, x: int, y: int) -> list[tuple[int, int]]:
        return [(x, y + d) for d in (-1, 1) if 0 <= y + d < GRID_WIDTH]

    def _diagonal(self, x: int, y: int) -> list[tuple[int, int]]:
        return [
            (x + dx, y + dy)
            for dx in (-1, 1)
            for dy in (-1, 1)
            if 0 <= x + dx < GRID_WIDTH and 0 <= y + dy < GRID_WIDTH
        ]

    def _adjacent(self, x: int, y: int) -> list[tuple[int, int]]:
        """GetAdjacentCells (:339-343): horizontal, then vertical, then
        diagonal, then the cell itself. The ORDER is load-bearing — it sets
        reveal order, which sets the order rewards are generated in, which
        sets the order the event's Rng is consumed in."""
        return (
            self._horizontal(x, y)
            + self._vertical(x, y)
            + self._diagonal(x, y)
            + [(x, y)]
        )
