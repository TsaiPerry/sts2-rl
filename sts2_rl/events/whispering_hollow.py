from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Event, EventOption, register_event

if TYPE_CHECKING:
    from ..run import RunState

_BASE_GOLD = 35     # GoldVar(35)
_GOLD_VARIANCE = 9  # NextInt(-9, 10)
_HP_LOSS = 9        # HpLossVar(9)
_MIN_GOLD = 44      # IsAllowed gate (base + max variance)


@register_event
class WhisperingHollow(Event):
    """Whispering Hollow — pay for potions, or hug the thing.

    Source: WhisperingHollow.cs
      IsAllowed: gold >= 44
      CalculateVars: gold cost = 35 + NextInt(-9, 10)
      GOLD: pay the gold, two potion rewards are offered
      HUG:  choose 1 card to transform, lose 9 HP (unblockable, unpowered)
    """

    id = "whispering_hollow"
    name = "Whispering Hollow"

    def __init__(self, run) -> None:
        super().__init__(run)
        self.gold_cost = _BASE_GOLD

    @classmethod
    def is_allowed(cls, run: RunState) -> bool:
        return run.gold >= _MIN_GOLD

    def calculate_vars(self) -> None:
        # `base.Rng.NextInt(-9, 10)` — the event's own Rng, not the shared run
        # RNG. It is also the FIRST draw on that stream, so it shifts HUG's
        # transform pick below; both must be parity-wired together.
        if self.event_rng is not None:
            variance = self.event_rng.next_int_range(
                -_GOLD_VARIANCE, _GOLD_VARIANCE + 1)
        else:
            variance = self.rng.randint(-_GOLD_VARIANCE, _GOLD_VARIANCE)
        self.gold_cost = _BASE_GOLD + variance

    def initial_options(self) -> list[EventOption]:
        return [
            EventOption("GOLD", self._gold),
            EventOption("HUG", self._hug),
        ]

    def _gold(self) -> None:
        self.run.lose_gold(self.gold_cost)
        # Two bare `PotionReward(Owner)` (WhisperingHollow.cs:53-57); each
        # Populate is PotionFactory.CreateRandomPotionOutOfCombat on
        # PlayerRng.Rewards — a NextFloat rarity roll then a NextItem pick.
        # Both ride one RewardsCmd.OfferCustom screen: take-or-skip each.
        for _ in range(2):
            if self.run.rng_set is not None:
                from ..potion_pools import generate_random_potion
                potion = generate_random_potion(self.run.rewards_rng)
            else:
                potion = self.run.random_potion()
            self.offer_potion(potion)
        self._finish("GOLD")

    def _hug(self) -> None:
        chosen = self.run.select_cards("transform", self.run.transformable_cards(), 1)
        for card in chosen:
            # CardCmd.TransformToRandom(item, base.Rng): the replacement is
            # rolled on the event's Rng (NextItem over the filtered pool).
            self.run.transform_card(card, pick_rng=self.event_rng)
        self.run.lose_hp(_HP_LOSS)
        self._finish("HUG")
