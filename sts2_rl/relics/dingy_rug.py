from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class DingyRug(Relic):
    """DingyRug.cs — card rewards can also contain Colorless cards.

    `ModifyCardRewardCreationOptions` (:13-36) appends the Colorless pool to
    the creation's card pools, under four guards in source order: the owner
    check, `NoCardPoolModifications`, `IsCardReward`, and "the Colorless pool
    is not already there". The fifth (`options.CustomCardPool != null`) has no
    sim counterpart — CardCreationOptions carries one pool tuple, so an
    explicit pool and a character pool are the same field; a caller that
    passes its own pool is the CustomCardPool case, and the "already
    contains Colorless" guard covers Lead Paperweight, the one relic that
    passes COLORLESS_POOL itself.
    """

    id = "dingy_rug"
    name = "Dingy Rug"
    rarity = RelicRarity.SHOP

    def modify_card_reward_creation_options(self, run, options):
        import dataclasses

        from ..cards.pool import COLORLESS_POOL
        from ..rewards import CardCreationFlags

        if options.has_flag(CardCreationFlags.NO_CARD_POOL_MODIFICATIONS):
            return options                                  # :19-22
        if not options.has_flag(CardCreationFlags.IS_CARD_REWARD):
            return options                                  # :23-26
        if any(cid in options.pool for cid in COLORLESS_POOL):
            return options                                  # :27-30
        return dataclasses.replace(
            options, pool=tuple(options.pool) + COLORLESS_POOL)
