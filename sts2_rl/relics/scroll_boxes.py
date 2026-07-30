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

        def possible(rarity: CardRarity) -> list[str]:
            """ScrollBoxes.cs:71-77 builds ONE CardCreationOptions per rarity,
            runs `Hook.ModifyCardRewardCreationOptions` over each (`:73` and
            `:75` — two separate dispatches, not one), and only then calls
            `GetPossibleCards`.

            The order matters and is why the rarity test is applied AFTER the
            chain rather than folded into the starting pool: in C# the rarity
            test is `CardPoolFilter`, a predicate stored ON the options and
            evaluated inside `GetPossibleCards` (CardCreationOptions.cs:168-172),
            so a listener that appends a pool has that pool filtered too.

            Flags are `NoUpgradeRoll` from `ForNonCombatWithUniformOdds`
            (CardCreationOptions.cs:160-163) plus the `NoRarityModification`
            ScrollBoxes.cs:71 adds. `IsCardReward` is NOT among them, which is
            what makes Dingy Rug — the sim's only ported implementer of this
            hook — return the options untouched here (DingyRug.cs:23-26).
            """
            from ..rewards import (CardCreationFlags, CardCreationOptions,
                                   CardCreationSource, RarityOddsType)
            options = CardCreationOptions(
                pool=tuple(pool),
                source=CardCreationSource.OTHER,
                odds_type=RarityOddsType.UNIFORM,
                flags=(CardCreationFlags.NO_UPGRADE_ROLL
                       | CardCreationFlags.NO_RARITY_MODIFICATION),
            )
            for relic in list(run.relics):
                options = relic.modify_card_reward_creation_options(run, options)
            return [cid for cid in options.pool
                    if _CARD_CLASSES[cid].rarity == rarity]

        commons = possible(CardRarity.COMMON)
        uncommons = possible(CardRarity.UNCOMMON)
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
