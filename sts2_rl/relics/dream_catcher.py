from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class DreamCatcher(Relic):
    """Whenever you rest at a rest site, choose a card to obtain (from the
    Monster-room pool, like a combat reward).

    Source: DreamCatcher.cs — TryModifyRestSiteHealRewards adds a
    CardReward(CardCreationOptions.ForRoom(player, RoomType.Monster), 3,
    owner) to the rest-heal reward screen (the same 3-card, Regular-odds
    choice as a Monster-room combat reward); ModifyExtraRestSiteHealText is
    UI-only flavor text on the heal button and isn't modeled. Granted by the
    Trash Heap event."""

    id = "dream_catcher"
    name = "Dream Catcher"
    rarity = RelicRarity.EVENT

    def modify_rest_site_heal_rewards(self, run, rewards) -> None:
        from ..rewards import RarityOddsType, create_reward_cards

        rewards.cards.extend(create_reward_cards(run, RarityOddsType.REGULAR))
