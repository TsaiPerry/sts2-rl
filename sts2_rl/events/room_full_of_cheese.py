from __future__ import annotations

from typing import TYPE_CHECKING

from ..cards import CardRarity
from .base import Event, EventOption, register_event

if TYPE_CHECKING:
    from ..run import RunState

_SEARCH_HP_LOSS = 14   # DamageVar(14, Unblockable | Unpowered)


@register_event
class RoomFullOfCheese(Event):
    """Room Full of Cheese — gorge on commons, or dig for the Chosen Cheese.

    Shared event (ModelDb.AllSharedEvents). Source: RoomFullOfCheese.cs
      IsAllowed: acts 1-2 only (CurrentActIndex < 2)
      GORGE:  pick 2 of 8 uniform-odds Common character-pool cards
      SEARCH: take 14 damage, obtain the Chosen Cheese relic
    """

    id = "room_full_of_cheese"
    name = "Room Full of Cheese"

    @classmethod
    def is_allowed(cls, run: RunState) -> bool:
        return run.act_index < 2

    def initial_options(self) -> list[EventOption]:
        return [
            EventOption("GORGE", self._gorge),
            EventOption("SEARCH", self._search),
        ]

    def _gorge(self) -> None:
        from ..cards.pool import _CARD_CLASSES, reward_pool_card_ids
        from ..rewards import CardCreationFlags, RarityOddsType, create_reward_cards

        # `CardFactory.CreateForReward(owner, 8,
        #  ForNonCombatWithUniformOdds(Character.CardPool, Rarity == Common))`
        # (RoomFullOfCheese.cs:40-41). Routing it through the reward factory is
        # what runs CreateForReward's tail — Hook.TryModifyCardRewardOptions
        # (CardFactory.cs:262-266), i.e. the egg relics' offer-side upgrade —
        # which a hand-rolled offer never reaches (NoModifyHooks is NOT set
        # here). `ForNonCombatWithUniformOdds` always ORs `NoUpgradeRoll`
        # (CardCreationOptions.cs:160-163), so this offer takes 8 Rewards
        # draws, not 16, and its cards reach AfterGenerated at +0.
        commons = [
            cid for cid in reward_pool_card_ids(self.run.card_pool)
            if _CARD_CLASSES[cid].rarity == CardRarity.COMMON
        ]
        cards = create_reward_cards(
            self.run, RarityOddsType.UNIFORM, count=8, mutate_pity=False,
            pool=commons,
            extra_flags=CardCreationFlags.NO_UPGRADE_ROLL,
        )
        for card in self.run.select_cards("card_reward", cards, 2):
            self.run.add_card(card)
        self._finish("GORGE")

    def _search(self) -> None:
        self.run.lose_hp(_SEARCH_HP_LOSS)
        self.run.add_relic("chosen_cheese")
        self._finish("SEARCH")
