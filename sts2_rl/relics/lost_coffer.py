from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class LostCoffer(Relic):
    """LostCoffer.cs — a reward screen: a 3-card choice (regular base odds)
    and a potion."""

    id = "lost_coffer"
    name = "Lost Coffer"
    rarity = RelicRarity.ANCIENT

    def after_obtained(self, run) -> None:
        from ..rewards import RarityOddsType, create_reward_cards

        cards = create_reward_cards(
            run, RarityOddsType.REGULAR, mutate_pity=False,
        )
        for card in run.select_cards("card_reward", cards, 1):
            run.add_card(card)
        run.add_potion(run.random_potion())
