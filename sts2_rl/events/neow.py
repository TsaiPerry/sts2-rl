"""Neow — the run-start Ancient event at Act 1's starting node.

Port of Neow.cs (src/Core/Models/Events/Neow.cs) without run modifiers:
GenerateInitialOptions builds 3 options, each granting one Ancient relic
(sts2_rl/relics/neow_relics.py):

  1. roll ONE "curse" option from the 8-relic curse pool (uniform, after the
     IsAllowedAtNeow filter);
  2. start from the 14 fixed "positive" relics, minus the one that pairs
     with the rolled curse (Cursed Pearl↔Golden Pearl, Hefty Tablet↔Arcane
     Scroll, Leafy Poultice↔New Leaf, Precarious Shears↔Precise Scissors);
  3. add one of each coin-flip pair — Lava Rock/Small Capsule (skipped
     entirely when the curse is Large Capsule), Nutritious Oyster/Stone
     Humidifier, Neow's Talisman/Pomander;
  4. filter by IsAllowedAtNeow, shuffle, take 2 positives + the curse.

Option keys are the relic ids; choosing one obtains the relic (its
AfterObtained pickup effect applies) and finishes the event.

The game gates Neow behind the NeowEpoch unlock (otherwise the start node is
a Monster room); the sim treats everything as unlocked, so a run always
starts at Neow. Run modifiers (the second branch of GenerateInitialOptions)
are not modeled.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from ..relics import ALL_RELICS, make_relic
from .base import Event, EventOption, register_event

if TYPE_CHECKING:
    from ..run import RunState

# Neow.PositiveOptions — the 14 fixed positive relics.
POSITIVE_RELICS: tuple[str, ...] = (
    "arcane_scroll", "booming_conch", "fishing_rod", "golden_pearl",
    "kaleidoscope", "lead_paperweight", "lost_coffer", "massive_scroll",
    "neows_torment", "new_leaf", "phial_holster", "precise_scissors",
    "scroll_boxes", "winged_boots",
)

# Neow.CurseOptions — the 8 curse relics.
CURSE_RELICS: tuple[str, ...] = (
    "cursed_pearl", "hefty_tablet", "large_capsule", "leafy_poultice",
    "neows_bones", "precarious_shears", "silken_tress", "silver_crucible",
)

# The coin-flip positive pairs appended per visit (in source order).
_LAVA_ROCK_PAIR = ("lava_rock", "small_capsule")
_OYSTER_PAIR = ("nutritious_oyster", "stone_humidifier")
_TALISMAN_PAIR = ("neows_talisman", "pomander")

# Curse → the positive it excludes (mutual-exclusion pruning).
_CURSE_EXCLUDES: dict[str, str] = {
    "cursed_pearl": "golden_pearl",
    "hefty_tablet": "arcane_scroll",
    "leafy_poultice": "new_leaf",
    "precarious_shears": "precise_scissors",
}


def neow_relic_pool(run: "RunState") -> list[str]:
    """Neow.AllPossibleOptions filtered by IsAllowedAtNeow — the full pool of
    relic ids Neow can hand out (Neow's Bones draws its 2 relics from this)."""
    ids = (
        list(CURSE_RELICS)
        + list(POSITIVE_RELICS)
        + [*_LAVA_ROCK_PAIR, *_OYSTER_PAIR, *_TALISMAN_PAIR]
    )
    return [rid for rid in ids if ALL_RELICS[rid].is_allowed_at_neow]


@register_event
class NeowEvent(Event):
    id = "neow"
    name = "Neow"

    def initial_options(self) -> list[EventOption]:
        rng = self.rng
        curses = [rid for rid in CURSE_RELICS if ALL_RELICS[rid].is_allowed_at_neow]
        curse = rng.choice(curses)

        positives = [
            rid for rid in POSITIVE_RELICS if rid != _CURSE_EXCLUDES.get(curse)
        ]
        if curse != "large_capsule":
            positives.append(_LAVA_ROCK_PAIR[0 if rng.random() < 0.5 else 1])
        positives.append(_OYSTER_PAIR[0 if rng.random() < 0.5 else 1])
        positives.append(_TALISMAN_PAIR[0 if rng.random() < 0.5 else 1])
        positives = [
            rid for rid in positives if ALL_RELICS[rid].is_allowed_at_neow
        ]
        rng.shuffle(positives)
        offered = positives[:2] + [curse]
        return [self._relic_option(rid) for rid in offered]

    def _relic_option(self, relic_id: str) -> EventOption:
        def on_chosen() -> None:
            self.run.add_relic(make_relic(relic_id))
            self._finish("DONE")

        return EventOption(relic_id, on_chosen)
