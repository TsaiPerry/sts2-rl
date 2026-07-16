from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class NeowsBones(Relic):
    """NeowsBones.cs — obtain 2 random relics from Neow's own pool (excluding
    Neow's Bones; their pickup effects apply) and a random curse."""

    id = "neows_bones"
    name = "Neow's Bones"
    rarity = RelicRarity.ANCIENT
    RELICS = 2
    CURSES = 1

    def after_obtained(self, run) -> None:
        from ..cards.pool import random_curses
        from ..events.neow import neow_relic_pool

        pool = [rid for rid in neow_relic_pool(run) if rid != self.id]
        run.rng.shuffle(pool)
        for rid in pool[: self.RELICS]:
            run.add_relic(rid)
        for curse in random_curses(run.rng, self.CURSES, distinct=True):
            run.add_card(curse)
