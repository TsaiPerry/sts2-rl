from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class DustyTome(Relic):
    """DustyTome.cs — upon pickup, add an UPGRADED copy of a random
    Ancient-rarity card to your deck.

    The card is chosen when the relic is offered (SetupForPlayer) from the
    character pool's Ancient-rarity cards, excluding the transcendence
    upgrades that Archaic Tooth grants (ArchaicTooth.TranscendenceCards).
    In the ported pool that leaves Corruption (Break is Bash's
    transcendence). Offered by the Darv shrine."""

    id = "dusty_tome"
    name = "Dusty Tome"
    rarity = RelicRarity.ANCIENT
    has_upon_pickup_effect = True

    def __init__(self) -> None:
        super().__init__()
        self.ancient_card: str | None = None

    @staticmethod
    def candidates(pool: tuple[str, ...]) -> list[str]:
        """The Ancient-rarity cards of `pool` (the character's CardPool) that
        Archaic Tooth's transcendence upgrades don't already cover."""
        from ..cards import CardRarity
        from ..cards.pool import _CARD_CLASSES
        from .archaic_tooth import ArchaicTooth

        excluded = set(ArchaicTooth.TRANSCENDENCE.values())
        return [
            cid for cid in pool
            if _CARD_CLASSES[cid].rarity == CardRarity.ANCIENT
            and cid not in excluded
        ]

    def setup_for_player(self, run) -> None:
        """SetupForPlayer: roll the Ancient card when the option is built."""
        options = self.candidates(run.card_pool)
        if not options:
            return
        # DustyTome.cs: AncientCard = PlayerRng.Rewards.NextItem(items).Id.
        if run.rng_set is not None:
            self.ancient_card = run.player_rng.rewards.next_item(options)
        else:
            self.ancient_card = run.rng.choice(options)

    def after_obtained(self, run) -> None:
        from ..cards import make_card

        if self.ancient_card is None:
            self.setup_for_player(run)
        if self.ancient_card is None:
            return
        card = make_card(self.ancient_card)
        card.upgrade()
        run.add_card(card)
