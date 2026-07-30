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

        from ..cmds import CardPileCmd

        player = self.combat.player
        # CardPilePosition.Random — CardPileCmd.cs:514 is
        # `Rng.Shuffle.NextInt(targetPile.Cards.Count + 1)`, an index into a pile
        # whose TOP is index 0, and the sim stores its draw pile with the top at
        # the END of the list. `CardPileCmd.add_to_draw` is the sim's port of
        # exactly this call and already carries the bridge (it inserts at
        # `count - p`) plus the `_enter_combat` step that registers the new card
        # as a hook listener. This relic hand-rolled the insert and used the raw
        # game index as a sim index, so with the stream pinned to NextInt -> 1 the
        # two Dazed landed near the BOTTOM of the pile where the game puts them at
        # the top — the player drew them at completely different times. Seven other
        # ported sites already call the helper, including relics/blessed_antler.py,
        # which adds Dazed to the draw pile the correct way.
        for _ in range(self.DAZED_COUNT):
            CardPileCmd.add_to_draw(self.hooks, player, make_card("dazed"))
        self.combats_left -= 1
