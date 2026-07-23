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
        from ..cards import make_card
        from ..cards.pool import curse_pool_ids, random_curses
        from ..events.neow import neow_relic_pool

        pool = [rid for rid in neow_relic_pool(run) if rid != self.id]
        if run.rng_set is not None:
            # NeowsBones.cs: PlayerRng.Rewards.Shuffle(relics).Take(2); each
            # curse = RunState.Rng.Niche.NextItem(generatable curses ordered by
            # Id), removed after each pick.
            run.player_rng.rewards.shuffle(pool)
            for rid in pool[: self.RELICS]:
                run.add_relic(rid)
            curse_opts = sorted(curse_pool_ids())
            for _ in range(self.CURSES):
                cid = run.rng_set.niche.next_item(curse_opts)
                curse_opts = [c for c in curse_opts if c != cid]
                run.add_card(make_card(cid))
        else:
            run.rng.shuffle(pool)
            for rid in pool[: self.RELICS]:
                run.add_relic(rid)
            for curse in random_curses(run.rng, self.CURSES, distinct=True):
                run.add_card(curse)
