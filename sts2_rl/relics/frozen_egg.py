from __future__ import annotations

from ..cards import CardType
from ._eggs import EggRelic
from .base import register_relic


@register_relic
class FrozenEgg(EggRelic):
    """FrozenEgg.cs — Power cards added to your deck (and offered as card
    rewards) arrive Upgraded."""

    id = "frozen_egg"
    name = "Frozen Egg"
    CARD_TYPE = CardType.POWER
