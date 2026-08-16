from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class HeftyTablet(Relic):
    """HeftyTablet.cs — choose one of 3 random Rare cards (uniform, never
    upgraded; skippable) and gain an Injury curse."""

    id = "hefty_tablet"
    name = "Hefty Tablet"
    rarity = RelicRarity.ANCIENT
    has_upon_pickup_effect = True  # RelicModel.HasUponPickupEffect
    CARDS = 3

    def after_obtained(self, run) -> None:
        from ..cards import CardRarity, make_card
        from ..cards.base import _CARD_CLASSES
        from ..cards.pool import reward_pool_card_ids
        from ..rewards import CardCreationFlags, RarityOddsType, create_reward_cards

        # HeftyTablet.cs:29 candidate set is CardFactory.CreateForReward's
        # `options.GetPossibleCards` (CardCreationOptions.cs:168-178), which
        # drops only Basic/Ancient (CardFactory.cs:221-224) — use
        # `reward_pool_card_ids`, not the FilterForCombat-based `pool_card_ids`
        # (that would drop can_be_generated_in_combat=False rares like `feed`/
        # `not_yet` and shift NextItem's index, diverging every seed).
        #
        # Builds its own CardCreationOptions(Source.Other, Uniform,
        # NoUpgradeRoll) and calls CreateForReward directly, not through
        # CardReward.cs, so IsCardReward is never set — that's what lets
        # DingyRug/PrismaticGem/SilkenTress/SilverCrucible skip firing on this
        # screen (they key off CardReward.cs:114-115/:134). Source.Other means
        # the pity offset must not advance (CardFactory.cs:244-260 only
        # mutates for Source.Encounter). Route through `create_reward_cards`
        # (rewards.py:313), not a hand-rolled pick loop, to preserve the
        # ModifyCardRewardCreationOptions / TryModifyCardRewardOptions[Late]
        # hook passes (egg relics / Silver Crucible / Silken Tress / Glitter)
        # and the RNG draw order.
        rares = [
            cid for cid in reward_pool_card_ids(pool=run.card_pool)
            if _CARD_CLASSES[cid].rarity == CardRarity.RARE
        ]
        options = create_reward_cards(
            run, RarityOddsType.UNIFORM, count=self.CARDS,
            mutate_pity=False,
            pool=rares,
            is_card_reward=False,
            extra_flags=CardCreationFlags.NO_UPGRADE_ROLL,
        )
        for card in run.select_cards("obtain", options, 1):
            run.add_card(card)
        run.add_card(make_card("injury"))
