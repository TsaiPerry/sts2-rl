from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class TinyMailbox(Relic):
    """When you Rest, also gain 2 potions — an out-of-combat rest-site reward,
    so this is a no-op stub."""

    id = "tiny_mailbox"
    name = "Tiny Mailbox"
    rarity = RelicRarity.UNCOMMON
