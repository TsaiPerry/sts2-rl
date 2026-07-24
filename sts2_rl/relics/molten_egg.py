from __future__ import annotations

from ..cards import CardType
from ._eggs import EggRelic
from .base import register_relic


@register_relic
class MoltenEgg(EggRelic):
    """MoltenEgg.cs — Attack cards added to your deck (and offered as card
    rewards) arrive Upgraded. Unlike the other two eggs it refuses a card that
    is already upgraded (MoltenEgg.cs:56)."""

    id = "molten_egg"
    name = "Molten Egg"
    CARD_TYPE = CardType.ATTACK
    ONLY_UNUPGRADED = True
