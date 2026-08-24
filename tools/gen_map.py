"""Print randomized single-column act maps — the maps ``--env column`` trains on.

    py gen_map.py                           # one Overgrowth column, random seed
    py gen_map.py --seed 7                  # reproducible
    py gen_map.py --seed 7 --count 3        # three columns, side by side
    py gen_map.py --act hive --count 5

The sampling is not re-implemented here: this is a viewer over
``sts2_rl.curriculum_env.random_column_types`` / ``column_map``, the same two
functions STS2CurriculumRunEnv builds its maps from, so what prints is exactly
what training sees.

Floors marked ``*`` are StandardActMap's forced rows (floor 1 Monster, the
treasure row, the pre-boss Rest); every other floor is sampled from
DEFAULT_ROOM_WEIGHTS under the placement rules random_column_types enforces.
"""
from __future__ import annotations

import argparse
import random

from sts2_rl.actmap import ACT_MAP_CONFIGS, MapPointType, StandardMap
from sts2_rl.curriculum_env import column_map, random_column_types

# "?" mirrors the game's unknown room (ColumnRunState resolves it to an Event
# on entry).
_LABELS: dict[MapPointType, str] = {
    MapPointType.MONSTER: "MONSTER",
    MapPointType.ELITE: "ELITE",
    MapPointType.UNKNOWN: "?",
    MapPointType.REST_SITE: "REST",
    MapPointType.TREASURE: "TREASURE",
    MapPointType.SHOP: "SHOP",
}

_COL_WIDTH = 12
_GUTTER = 4       # "NN* " — floor number, forced marker, space


def forced_floors(n_rooms: int) -> set[int]:
    """The floors random_column_types assigns outright instead of sampling.

    Mirrors its `forced` dict: floor 1 is Monster, floor ``n_rooms - 6`` is
    the treasure row (StandardActMap's row_count - 7), the top floor is the
    pre-boss Rest.
    """
    forced = {1, n_rooms}
    treasure = n_rooms - 6
    if 1 < treasure < n_rooms:
        forced.add(treasure)
    return forced


def floor_label(act_map: StandardMap, floor: int) -> str:
    """The room type on `floor` — a column has exactly one node per row."""
    return _LABELS[act_map.points_in_row(floor)[0].point_type]


def render(maps: list[StandardMap], n_rooms: int) -> str:
    """Boss on top, Ancient at the bottom, one column per map."""
    forced = forced_floors(n_rooms)

    def row(cells: list[str]) -> str:
        return " " * _GUTTER + "".join(c.center(_COL_WIDTH) for c in cells)

    n = len(maps)
    lines = [
        row([f"#{i + 1}" for i in range(n)]),
        row(["BOSS"] * n),
        row(["|"] * n),
    ]
    for floor in range(n_rooms, 0, -1):
        gutter = f"{floor:>2}{'*' if floor in forced else ' '} "
        lines.append(
            gutter + "".join(floor_label(m, floor).center(_COL_WIDTH) for m in maps)
        )
    lines.append(row(["|"] * n))
    lines.append(row(["ANCIENT"] * n))
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Print randomized single-column act maps (the --env column "
                    "curriculum's maps).",
    )
    ap.add_argument("--seed", type=int, default=None,
                    help="RNG seed (default: random; the seed used is always "
                         "printed, so any output can be reproduced)")
    ap.add_argument("--count", type=int, default=1,
                    help="how many columns to sample and show side by side "
                         "(default 1); with an explicit --seed the whole set "
                         "is reproducible, since one Random drives them all")
    ap.add_argument("--act", default="overgrowth", choices=sorted(ACT_MAP_CONFIGS),
                    help="which act's config to use — it sets the floor count "
                         "(default: overgrowth)")
    args = ap.parse_args()
    if args.count < 1:
        ap.error("--count must be at least 1")

    seed = args.seed if args.seed is not None else random.randrange(2**31)
    rng = random.Random(seed)
    config = ACT_MAP_CONFIGS[args.act]
    maps = [
        column_map(rng, config, random_column_types(rng, n_rooms=config.num_rooms))
        for _ in range(args.count)
    ]

    print(f"act {config.name}   seed {seed}   {config.num_rooms} floors"
          + (f"   x{args.count}" if args.count > 1 else ""))
    print()
    print(render(maps, config.num_rooms))
    print()
    print("* forced floor: row-1 monster, treasure row, pre-boss rest")


if __name__ == "__main__":
    main()
