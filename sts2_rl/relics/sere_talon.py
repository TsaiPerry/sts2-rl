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
    has_upon_pickup_effect = True  # RelicModel.HasUponPickupEffect

    CURSES = 2
    WISHES = 3

    def after_obtained(self, run) -> None:
        from ..cards import make_card
        from ..cards.pool import curse_pool_ids, random_curses

        if run.rng_set is not None:
            # SereTalon.cs:41: each curse is RunState.Rng.Niche.NextItem over
            # the generatable curses ordered by Id, removed after each pick
            # (the sibling NeowsBones.cs does the same thing).
            curse_opts = sorted(curse_pool_ids())
            for _ in range(self.CURSES):
                cid = run.rng_set.niche.next_item(curse_opts)
                curse_opts = [c for c in curse_opts if c != cid]
                run.add_card(make_card(cid))
        else:
            for curse in random_curses(run.rng, self.CURSES, distinct=True):
                run.add_card(curse)
        for _ in range(self.WISHES):
            run.add_card(make_card("wish"))
