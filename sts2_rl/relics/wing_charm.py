from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class WingCharm(Relic):
    """WingCharm.cs — one option in every card reward arrives enchanted with
    Swift 1 (TryModifyCardRewardOptionsLate: filter the options to the ones
    Swift CanEnchant, then `RunState.Rng.Niche.NextItem` picks the one to
    enchant)."""

    id = "wing_charm"
    name = "Wing Charm"
    rarity = RelicRarity.SHOP

    SWIFT_AMOUNT = 1   # DynamicVar "SwiftAmount"

    def modify_card_reward_options_late(self, run, cards) -> None:
        from ..enchantments import SwiftEnchantment

        options = [c for c in cards if SwiftEnchantment.can_enchant(c)]
        if not options:
            return
        # WingCharm.cs:38 draws the pick on the per-player Niche stream; the
        # legacy RL path stays on the shared run rng.
        if run.rng_set is not None:
            card = run.rng_set.niche.next_item(options)
        else:
            card = run.rng.choice(options)
        SwiftEnchantment(self.SWIFT_AMOUNT).attach(card)
