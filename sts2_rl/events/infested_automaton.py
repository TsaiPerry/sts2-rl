from __future__ import annotations

from ..cards import CardType, make_card
from ..cards.pool import reward_pool_card_ids
from .base import Event, EventOption, register_event


@register_event
class InfestedAutomaton(Event):
    """Infested Automaton — study it for a Power card, or touch its core for a
    random 0-cost card.

    Source: InfestedAutomaton.cs
      STUDY:      add a random Power card from the character pool
      TOUCH_CORE: add a random 0-cost (non-X) card from the character pool

    Both branches are `CardFactory.CreateForReward(Owner, 1,
    ForNonCombatWithDefaultOdds(Character.CardPool, <filter>))`
    (InfestedAutomaton.cs:30-31 / 41-46) — the REWARD factory, not the
    in-combat generator: an escalating rarity roll off the non-mutating base
    odds (the creation source is `Other`, not `Encounter`) and a `NextItem`
    pick on PlayerRng.Rewards. `CardCreationOptions.GetPossibleCards` applies
    the filter to the unlocked pool (`GetUnlockedCards`, NOT FilterForCombat)
    before the rarity roll sees it — CardCreationOptions.cs:170-172.
    """

    id = "infested_automaton"
    name = "Infested Automaton"

    def initial_options(self) -> list[EventOption]:
        return [
            EventOption("STUDY", self._study),
            EventOption("TOUCH_CORE", self._touch_core),
        ]

    def _offer(self, pool: list[str]) -> None:
        from ..rewards import RarityOddsType, create_reward_cards

        for card in create_reward_cards(
            self.run, RarityOddsType.REGULAR, count=1, mutate_pity=False,
            pool=pool,
        ):
            self.run.add_card(card)

    def _study(self) -> None:
        from ..cards.pool import _CARD_CLASSES

        self._offer([
            cid for cid in reward_pool_card_ids()
            if _CARD_CLASSES[cid].card_type == CardType.POWER
        ])
        self._finish("STUDY")

    def _touch_core(self) -> None:
        # `c.EnergyCost != null && EnergyCost.Canonical == 0 && !CostsX`.
        self._offer([
            cid for cid in reward_pool_card_ids()
            if make_card(cid).energy_cost == 0 and not make_card(cid).energy_cost_x
        ])
        self._finish("TOUCH_CORE")
