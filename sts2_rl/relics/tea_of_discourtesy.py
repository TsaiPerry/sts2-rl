from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class TeaOfDiscourtesy(Relic):
    """TeaOfDiscourtesy.cs — shuffle 2 Dazed into your draw pile at the start
    of your NEXT combat (BeforeCombatStart, one charge). The free option at
    the Tea Master event."""

    id = "tea_of_discourtesy"
    name = "Tea of Discourtesy"
    rarity = RelicRarity.EVENT

    COMBATS = 1
    DAZED_COUNT = 2

    def __init__(self) -> None:
        super().__init__()
        self.combats_left = self.COMBATS

    @property
    def is_used_up(self) -> bool:   # IsUsedUp => CombatsLeft <= 0
        return self.combats_left <= 0

    def on_combat_start(self) -> None:
        if self.is_used_up:
            return
        from ..cards import make_card

        player = self.combat.player
        # CardPilePosition.Random — shuffled into the draw pile.
        for _ in range(self.DAZED_COUNT):
            card = make_card("dazed")
            player.draw_pile.insert(
                self.combat._rng.randrange(len(player.draw_pile) + 1), card)
        self.combats_left -= 1
