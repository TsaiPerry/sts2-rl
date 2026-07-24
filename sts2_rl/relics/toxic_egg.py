from __future__ import annotations

from ..cards import CardType
from ._eggs import EggRelic
from .base import register_relic


@register_relic
class ToxicEgg(EggRelic):
    """ToxicEgg.cs — Skill cards added to your deck (and offered as card
    rewards) arrive Upgraded."""

    id = "toxic_egg"
    name = "Toxic Egg"
    CARD_TYPE = CardType.SKILL
