from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class SilkenTress(Relic):
    """SilkenTress.cs — lose ALL gold; the next card reward's options are all
    enchanted with Glam (first time you play the card each combat, it plays
    an extra time); one-shot."""

    id = "silken_tress"
    name = "Silken Tress"
    rarity = RelicRarity.ANCIENT

    def __init__(self) -> None:
        super().__init__()
        self.is_used = False

    @property
    def is_used_up(self) -> bool:   # IsUsedUp => IsUsed
        return self.is_used

    def after_obtained(self, run) -> None:
        run.lose_gold(run.gold)

    def modify_card_reward_options_late(self, run, cards) -> None:
        from ..enchantments import GlamEnchantment

        if self.is_used:
            return
        for card in cards:
            if GlamEnchantment.can_enchant(card):
                GlamEnchantment().attach(card)
        self.is_used = True
