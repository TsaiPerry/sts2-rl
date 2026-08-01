from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Relic, RelicRarity, register_relic

if TYPE_CHECKING:
    from ..combat import CombatState
    from ..player import PlayerCombatState

@register_relic
class GamblingChip(Relic):
    """At the start of combat, you may discard any number of cards, then
    draw that many. The choice goes through CombatState.select_cards with
    purpose "gambling_chip" (candidates = hand, count = hand size; the
    selector may return fewer — the scripted selector discards only
    Status/Curse cards, the default random selector mulligans the hand)."""

    id = "gambling_chip"
    name = "Gambling Chip"
    rarity = RelicRarity.RARE

    def on_player_turn_started(self, player: PlayerCombatState) -> None:
        if self.turn > 1:
            return
        chosen = self.combat.select_cards(
            "gambling_chip", list(player.hand), len(player.hand),
            min_select=0,   # GamblingChip.cs:20 CardSelectorPrefs(prompt, 0, ...)
        )
        if not chosen:
            return
        # GamblingChip.cs:21 is `CardCmd.DiscardAndDraw(picked, picked.Count)`
        # — the same command Gambler's Brew uses, which is why neither should
        # open-code it: the two sim copies disagreed about whether
        # `AfterCardDiscarded` fires before or after the append (C# appends
        # first, CardCmd.cs:192-194) and neither had the Sly tail (:201-204).
        from ..cmds import CardCmd
        CardCmd.discard_and_draw(self.hooks, player, chosen, len(chosen))
