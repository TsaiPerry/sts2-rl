"""Orobas — one of the three Act-2 (Hive) Ancients.

Port of Orobas.cs GenerateInitialOptions: three relic options —

  1. one of OptionPool1 (Electric Shrymp / Glass Eye / Sand Castle) plus a
     rolled fourth entry: Prismatic Gem with odds 1/3, otherwise Sea Glass
     (another character's pool; a documented stub in the single-character sim);
  2. one of OptionPool2 (Alchemical Coffer / Driftwood / Radiant Pearl);
  3. one of OptionPool3 — Touch of Orobas (gated on a starter relic being
     present, SetupForPlayer) and/or Archaic Tooth (gated on the deck holding
     a transcendence starter card, i.e. Bash). If both gates fail the slot is
     the locked OPTION_POOL_3_LOCKED option.
"""
from __future__ import annotations

from ..characters import ALL_CHARACTER_IDS as ALL_CHARACTERS
from ..relics import ALL_RELICS  # noqa: F401  (parity with neow's imports)
from .ancient import AncientEvent
from .base import EventOption, register_event

OPTION_POOL_1: tuple[str, ...] = ("electric_shrymp", "glass_eye", "sand_castle")
OPTION_POOL_2: tuple[str, ...] = ("alchemical_coffer", "driftwood", "radiant_pearl")

_PRISMATIC_ODDS = 1 / 3

# ModelDb.AllCharacters (ModelDb.cs:123), in source order. Orobas opens by
# picking the Sea Glass character from the OTHER unlocked ones; the sim models
# a fully-unlocked run (as the card/potion pools do), so that pick is a real
# NextItem over these minus the player's own character. The order is
# parity-critical, which is why ALL_CHARACTERS is imported from the character
# registry above rather than kept as a second hand-maintained copy.


@register_event
class OrobasEvent(AncientEvent):
    id = "orobas"
    name = "Orobas"

    def initial_options(self) -> list[EventOption]:
        run = self.run
        # Orobas.cs GenerateInitialOptions draws on the per-event Rng (base.Rng),
        # in this order: a NextItem over the OTHER unlocked characters (the Sea
        # Glass owner), a NextFloat for the Prismatic/Sea Glass roll, then three
        # NextItem picks. The recorded runs are fully unlocked, so the character
        # pick draws over ModelDb.AllCharacters minus Ironclad — it is a real
        # draw, and dropping it shifts all three relic picks. Legacy keeps the
        # shared run rng.
        er = self.event_rng

        def pick(opts):
            return er.next_item(opts) if er is not None else self.rng.choice(opts)

        others = [c for c in ALL_CHARACTERS if c != run.character.id]
        pick(others)  # the Sea Glass character; only its draw matters here
        roll = er.next_float() if er is not None else self.rng.random()
        pool1 = list(OPTION_POOL_1)
        pool1.append("prismatic_gem" if roll < _PRISMATIC_ODDS else "sea_glass")
        first = pick(pool1)

        second = pick(list(OPTION_POOL_2))

        from ..relics.archaic_tooth import ArchaicTooth
        from ..relics.base import RelicRarity
        from ..relics.touch_of_orobas import TouchOfOrobas

        pool3: list[str] = []
        starter = next(
            (r for r in run.relics if r.rarity == RelicRarity.STARTER), None
        )
        if starter is not None and starter.id in TouchOfOrobas.REFINEMENTS:
            pool3.append("touch_of_orobas")
        if any(c.id in ArchaicTooth.TRANSCENDENCE for c in run.deck):
            pool3.append("archaic_tooth")

        options = [self._relic_option(first), self._relic_option(second)]
        if pool3:
            options.append(self._relic_option(pick(pool3)))
        else:
            # Orobas.cs: a locked placeholder option (null onChosen).
            options.append(EventOption("OPTION_POOL_3_LOCKED", None))
        return options
