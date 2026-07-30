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

from ..relics import ALL_RELICS
from .ancient import AncientEvent
from .base import EventOption, register_event

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

# The same six relics as SEPARATE trailing options, which is how
# Neow.AllPossibleOptions builds the full pool (Neow.cs:56-61 adds
# LavaRockOption, NeowsTalismanOption, NutritiousOysterOption, PomanderOption,
# SmallCapsuleOption, StoneHumidifierOption one at a time, in that declaration
# order). The pairing above is a fact about GenerateInitialOptions' coin flips,
# not about the pool — and the ORDER is load-bearing, because Neow's Bones
# shuffles this list and a Fisher-Yates swap sequence depends only on the RNG.
_SINGLETON_OPTIONS: tuple[str, ...] = (
    "lava_rock", "neows_talisman", "nutritious_oyster",
    "pomander", "small_capsule", "stone_humidifier",
)

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
        + list(_SINGLETON_OPTIONS)
    )
    return [rid for rid in ids if ALL_RELICS[rid].is_allowed_at_neow(run)]


@register_event
class NeowEvent(AncientEvent):
    id = "neow"
    name = "Neow"

    def initial_options(self) -> list[EventOption]:
        # Neow.cs GenerateInitialOptions draws on the per-event Rng (base.Rng):
        # NextItem(curses), then for each pair a NextBool (true => the first,
        # NextBool-true option: LavaRock / NutritiousOyster / NeowsTalisman),
        # then UnstableShuffle(positives).Take(2) + the curse. Legacy keeps the
        # shared run rng byte-for-byte.
        er = self.event_rng
        curses = [rid for rid in CURSE_RELICS
                  if ALL_RELICS[rid].is_allowed_at_neow(self.run)]
        curse = er.next_item(curses) if er is not None else self.rng.choice(curses)

        def coin() -> bool:                       # Rng.NextBool()
            return er.next_bool() if er is not None else self.rng.random() < 0.5

        positives = [
            rid for rid in POSITIVE_RELICS if rid != _CURSE_EXCLUDES.get(curse)
        ]
        if curse != "large_capsule":
            positives.append(_LAVA_ROCK_PAIR[0 if coin() else 1])
        positives.append(_OYSTER_PAIR[0 if coin() else 1])
        positives.append(_TALISMAN_PAIR[0 if coin() else 1])
        positives = [
            rid for rid in positives
            if ALL_RELICS[rid].is_allowed_at_neow(self.run)
        ]
        if er is not None:
            er.shuffle(positives)
        else:
            self.rng.shuffle(positives)
        offered = positives[:2] + [curse]
        return [self._relic_option(rid) for rid in offered]
