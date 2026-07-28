from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class Glitter(Relic):
    """Glitter.cs — every card reward option that can hold Glam is enchanted
    with Glam (TryModifyCardRewardOptionsLate; unlike Silken Tress this is
    not one-shot)."""

    id = "glitter"
    name = "Glitter"
    rarity = RelicRarity.ANCIENT

    def modify_card_reward_options_late(self, run, cards) -> None:
        from ..enchantments import GlamEnchantment

        for card in cards:
            if GlamEnchantment.can_enchant(card):
                GlamEnchantment().attach(card)
