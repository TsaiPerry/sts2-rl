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

    def modify_card_reward_options_late(self, run, cards, options=None) -> None:
        from ..enchantments import GlamEnchantment

        # SilkenTress.cs:53-56 / SilverCrucible.cs:104-107 —
        # `if (!options.Flags.HasFlag(CardCreationFlags.IsCardReward)) return
        # false;`. Without it a relic or event card generation spent the
        # one-shot (relic/_reward_late_pass).
        from ..rewards import CardCreationFlags

        if options is None or not options.has_flag(CardCreationFlags.IS_CARD_REWARD):
            return False
        if self.is_used:
            return False
        for card in cards:
            if GlamEnchantment.can_enchant(card):
                GlamEnchantment().attach(card)
        return True                             # SilkenTress.cs:72

    def after_modify_card_reward_options(self, run) -> None:
        # SilkenTress.cs:75-81 — the one-shot is spent HERE, in the companion
        # event that only reaches listeners which returned true, not inside
        # the modifier.
        if not self.is_used:
            self.is_used = True
