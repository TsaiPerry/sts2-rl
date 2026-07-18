from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class SereTalon(Relic):
    """SereTalon.cs — upon pickup, add 2 random distinct curses
    (CanBeGeneratedByModifiers pool, "Curses" = 2) and 3 Wish cards
    ("Wishes" = 3)."""

    id = "sere_talon"
    name = "Sere Talon"
    rarity = RelicRarity.ANCIENT

    CURSES = 2
    WISHES = 3

    def after_obtained(self, run) -> None:
        from ..cards import make_card
        from ..cards.pool import random_curses

        for curse in random_curses(run.rng, self.CURSES, distinct=True):
            run.add_card(curse)
        for _ in range(self.WISHES):
            run.add_card(make_card("wish"))
