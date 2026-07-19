from __future__ import annotations

from typing import TYPE_CHECKING

from ..cards import CardRarity, CardType, make_card
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
        return len(run.potions) >= 2

    def calculate_vars(self) -> None:
        # PotionToCardType: one roll per held potion, in belt order.
        self._card_types: dict[int, CardType] = {}
        for potion in self.run.potions:
            types = [CardType.ATTACK, CardType.SKILL, CardType.POWER]
            if potion.rarity in ("common", "token"):
                types.remove(CardType.POWER)
            self._card_types[id(potion)] = self.rng.choice(types)

    def initial_options(self) -> list[EventOption]:
        options = []
        for i, potion in enumerate(self.run.potions[:3]):
            options.append(EventOption(
                f"POTION_{i}",
                lambda p=potion: self._trade(p),
            ))
        return options

    def _trade(self, potion: Potion) -> None:
        from ..cards.pool import IRONCLAD_POOL, _CARD_CLASSES

        target_rarity = _CARD_RARITY[potion.rarity]
        card_type = self._card_types[id(potion)]
        self.run.potions.remove(potion)
        candidates = [
            cid for cid in IRONCLAD_POOL
            if _CARD_CLASSES[cid].rarity == target_rarity
            and _CARD_CLASSES[cid].card_type == card_type
        ]
        picks = self.rng.sample(candidates, min(3, len(candidates)))
        cards = []
        for cid in picks:
            card = make_card(cid)
            card.upgrade()               # reward.AfterGenerated upgrades all
            cards.append(card)
        for card in self.run.select_cards("card_reward", cards, 1):
            self.run.add_card(card)
        self._finish("DONE")
