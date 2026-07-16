from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class LeadPaperweight(Relic):
    """LeadPaperweight.cs — on pickup, choose 1 of 2 Colorless cards to add
    to the deck (CardFactory.CreateForReward over the ColorlessCardPool with
    RegularEncounter odds, skippable choose-a-card screen)."""

    id = "lead_paperweight"
    name = "Lead Paperweight"
    rarity = RelicRarity.ANCIENT

    def after_obtained(self, run) -> None:
        from ..cards.pool import COLORLESS_POOL
        from ..rewards import RarityOddsType, create_reward_cards

        # The reward path filters only Basic/Ancient rarities (the whole
        # Colorless pool is eligible); CardCreationOptions(source=Other) →
        # the non-mutating base-odds rarity roll, and reward-modify hooks
        # run (no NoModifyHooks flag).
        cards = create_reward_cards(
            run, RarityOddsType.REGULAR, count=2,
            mutate_pity=False, modify_hooks=True,
            pool=list(COLORLESS_POOL),
        )
        chosen = run.select_cards("card_reward", cards, 1)
        for card in chosen:
            run.add_card(card)
