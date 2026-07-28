from __future__ import annotations

from typing import TYPE_CHECKING

from ..cards import CardRarity, CardType
from .base import Event, EventOption, register_event

if TYPE_CHECKING:
    from ..potions import Potion
    from ..run import RunState

# PotionRarity -> CardRarity (GetCardRarity; unknown rarities throw there,
# the sim's potion rarities are all covered).
_CARD_RARITY = {
    "rare": CardRarity.RARE,
    "event": CardRarity.RARE,
    "uncommon": CardRarity.UNCOMMON,
    "common": CardRarity.COMMON,
    "token": CardRarity.COMMON,
}


@register_event
class TheFutureOfPotions(Event):
    """The Future of Potions — trade a potion for its card of the future.

    Shared event (ModelDb.AllSharedEvents). Source: TheFutureOfPotions.cs
      IsAllowed: every player holds at least 2 potions
      POTION_i (first 3 held potions): discard it, then pick 1 of 3 UPGRADED
        character-pool cards whose rarity maps from the potion's
        (Rare/Event -> Rare, Uncommon -> Uncommon, Common/Token -> Common)
        and whose type was pre-rolled per potion (Attack/Skill, plus Power
        only for Uncommon+ rarities) — uniform odds, distinct cards.

    The source's CanRemovePotions=false guard is UI-only (the sim has no
    out-of-combat potion discard surface) and is not modeled.
    """

    id = "the_future_of_potions"
    name = "The Future of Potions"

    @classmethod
    def is_allowed(cls, run: RunState) -> bool:
        return len(run.held_potions) >= 2

    def calculate_vars(self) -> None:
        # PotionToCardType: one roll per held potion, in belt order.
        er = self.event_rng
        self._card_types: dict[int, CardType] = {}
        for potion in self.run.held_potions:
            types = [CardType.ATTACK, CardType.SKILL, CardType.POWER]
            if potion.rarity in ("common", "token"):
                types.remove(CardType.POWER)
            # `base.Rng.NextItem(list2)` — the event's own Rng
            # (TheFutureOfPotions.cs:59).
            self._card_types[id(potion)] = (
                er.next_item(types) if er is not None
                else self.rng.choice(types))

    def initial_options(self) -> list[EventOption]:
        options = []
        for i, potion in enumerate(self.run.held_potions[:3]):
            options.append(EventOption(
                f"POTION_{i}",
                lambda p=potion: self._trade(p),
            ))
        return options

    def _trade(self, potion: Potion) -> None:
        from ..cards.pool import _CARD_CLASSES, reward_pool_card_ids
        from ..rewards import RarityOddsType, create_reward_cards

        target_rarity = _CARD_RARITY[potion.rarity]
        card_type = self._card_types[id(potion)]
        self.run.discard_potion(potion)
        candidates = [
            cid for cid in reward_pool_card_ids()
            if _CARD_CLASSES[cid].rarity == target_rarity
            and _CARD_CLASSES[cid].card_type == card_type
        ]
        # `new CardReward(ForNonCombatWithUniformOdds(Character.CardPool,
        #  Rarity == targetRarity && Type == PotionToCardType[potion]), 3, ...)`
        # (TheFutureOfPotions.cs:127-129) — CardFactory.CreateForReward, so the
        # offer reaches Hook.TryModifyCardRewardOptions (CardFactory.cs:262-266)
        # before AfterGenerated upgrades every offered card.
        cards = create_reward_cards(
            self.run, RarityOddsType.UNIFORM, count=3, mutate_pity=False,
            pool=candidates,
        )
        for card in cards:
            card.upgrade()               # reward.AfterGenerated upgrades all
        # The CardReward rides RewardsCmd.OfferCustom (TheFutureOfPotions.cs:130),
        # so the whole screen can be walked away from — the potion is already
        # spent either way (PotionCmd.Discard above).
        self.offer_card_reward(cards)
        self._finish("DONE")
