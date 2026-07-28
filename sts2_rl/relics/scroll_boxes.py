from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class ScrollBoxes(Relic):
    """ScrollBoxes.cs — choose one of 2 card bundles; each bundle is 2 random
    Commons + 1 random Uncommon, all 6 cards unique across both bundles."""

    id = "scroll_boxes"
    name = "Scroll Boxes"
    rarity = RelicRarity.ANCIENT

    def after_obtained(self, run) -> None:
        from ..cards import CardRarity, make_card
        from ..cards.base import _CARD_CLASSES
        from ..cards.pool import pool_card_ids

        pool = pool_card_ids(pool=run.card_pool)
        commons = [
            cid for cid in pool
            if _CARD_CLASSES[cid].rarity == CardRarity.COMMON
        ]
        uncommons = [
            cid for cid in pool
            if _CARD_CLASSES[cid].rarity == CardRarity.UNCOMMON
        ]
        # ScrollBoxes.cs GenerateRandomBundles: per bundle, 2 Common then 1
        # Uncommon via PlayerRng.Rewards.NextItem (the Defect-only NextInt(100)
        # rare-swap never fires for Ironclad). Legacy keeps the shared rng.
        rewards = run.player_rng.rewards if run.rng_set is not None else None

        def draw(opts: list[str]) -> str:
            return rewards.next_item(opts) if rewards is not None else run.rng.choice(opts)

        used: set[str] = set()
        bundles: list[list[str]] = []
        for _ in range(2):
            bundle: list[str] = []
            for _ in range(2):
                options = [c for c in commons if c not in used]
                pick = draw(options)
                bundle.append(pick)
                used.add(pick)
            options = [c for c in uncommons if c not in used]
            pick = draw(options)
            bundle.append(pick)
            used.add(pick)
            bundles.append(bundle)
        chosen = bundles[run.select_option("bundle", len(bundles))]
        for cid in chosen:
            run.add_card(make_card(cid))
