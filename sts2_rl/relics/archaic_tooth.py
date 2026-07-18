from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class ArchaicTooth(Relic):
    """ArchaicTooth.cs — upon pickup, transform the character's signature
    starter card into its transcendence (TranscendenceUpgrades: Bash → Break
    for the Ironclad), preserving upgrade and enchantment. Only offered by
    Orobas when the deck still holds the starter card (SetupForPlayer)."""

    id = "archaic_tooth"
    name = "Archaic Tooth"
    rarity = RelicRarity.ANCIENT

    # TranscendenceUpgrades, restricted to the sim's single character.
    TRANSCENDENCE = {"bash": "break"}

    def after_obtained(self, run) -> None:
        from ..cards import make_card

        original = next(
            (c for c in run.deck if c.id in self.TRANSCENDENCE), None
        )
        if original is None:
            return
        transformed = make_card(self.TRANSCENDENCE[original.id])
        # GetTranscendenceTransformedCard: carry over upgrade + enchantment.
        for _ in range(original.upgrade_level):
            if transformed.is_upgradable:
                transformed.upgrade()
        if original.enchantment is not None:
            enchantment = original.enchantment
            original.enchantment = None       # free it for re-attachment
            enchantment.card = None
            if enchantment.can_enchant(transformed):
                enchantment.attach(transformed)
        run.transform_card(original, into=transformed)
