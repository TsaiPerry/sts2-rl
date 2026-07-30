from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Event, EventOption, register_event

if TYPE_CHECKING:
    from ..run import RunState

_RIP_HP_LOSS = 5           # DamageVar(5, Unblockable | Unpowered)
_REWARD_COUNT = 1          # IntVar RewardCount
_CARD_CHOICE_COUNT = 1     # IntVar CardChoiceCount
_FROM_CHOICE_COUNT = 5     # IntVar FromCardChoiceCount


@register_event
class BrainLeech(Event):
    """Brain Leech — share knowledge for a card, or rip it free.

    Shared event (ModelDb.AllSharedEvents). Source: BrainLeech.cs
      IsAllowed: acts 1-2 only (CurrentActIndex < 2)
      SHARE_KNOWLEDGE: pick 1 of 5 character-pool reward cards (default
                       non-mutating odds; the screen is not cancelable)
      RIP: take 5 damage, then a 3-card Colorless reward choice (default
           odds, no rarity/pool modification hooks)
    """

    id = "brain_leech"
    name = "Brain Leech"

    @classmethod
    def is_allowed(cls, run: RunState) -> bool:
        return run.act_index < 2

    def initial_options(self) -> list[EventOption]:
        return [
            EventOption("SHARE_KNOWLEDGE", self._share_knowledge),
            EventOption("RIP", self._rip),
        ]

    def _share_knowledge(self) -> None:
        from ..rewards import RarityOddsType, create_reward_cards

        cards = create_reward_cards(
            self.run, RarityOddsType.REGULAR, count=_FROM_CHOICE_COUNT,
            mutate_pity=False,
        )
        for card in self.run.select_cards("card_reward", cards,
                                          _CARD_CHOICE_COUNT):
            self.run.add_card(card)
        self._finish("SHARE_KNOWLEDGE")

    def _rip(self) -> None:
        from ..cards.pool import COLORLESS_POOL
        from ..rewards import RarityOddsType, create_reward_cards

        from ..rewards import CardRewardGroup, CombatRewards
        from ..rooms import RoomType

        self.run.lose_hp(_RIP_HP_LOSS)
        # BrainLeech.cs:51-61 hands its RewardCount 3-card colourless CardRewards
        # to `RewardsCmd.OfferCustom` — a SKIPPABLE screen. The sim ran them
        # through `select_cards`, which always returns a card when the candidate
        # list is non-empty (run.py), so the player could not decline: the
        # colourless pool holds curses and situational cards, and the source
        # distinguishes the two screens deliberately — SHARE_KNOWLEDGE sets
        # `Cancelable = false` and this branch does not. `pending_rewards` is the
        # sim's mid-event OfferCustom channel (the driver offers and clears it as
        # soon as the option returns), the same one Dense Vegetation's rest heal
        # uses.
        groups = []
        for _ in range(_REWARD_COUNT):
            # CardCreationFlags.NoRarityModification|NoCardPoolModifications.
            cards = create_reward_cards(
                self.run, RarityOddsType.REGULAR, count=3,
                mutate_pity=False, modify_hooks=False,
                pool=list(COLORLESS_POOL),
            )
            groups.append(CardRewardGroup(cards=cards, room_type=RoomType.MONSTER,
                                          count=3, populated=True))
        self.pending_rewards = CombatRewards(room_type=RoomType.MONSTER,
                                             card_rewards=groups)
        self._finish("RIP")
