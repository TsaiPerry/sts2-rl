from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class SwordOfStone(Relic):
    """Event relic (Sunken Statue): counts elite combat victories; at 5 it is
    replaced by Sword of Jade.

    Source: SwordOfStone.cs — AfterCombatVictory increments ElitesDefeated
    only when room.RoomType == RoomType.Elite; when the counter reaches
    DynamicVars["Elites"] (5), RelicCmd.Replace(this, SwordOfJade), which
    removes this relic and obtains Sword of Jade at the same relic-list index
    (RelicCmd.cs Replace → Remove + Obtain(index), firing AfterObtained).
    The sim's RunState.finish_combat dispatches after_combat_end only when
    the player survived, matching the victory-only source hook.
    """

    id = "sword_of_stone"
    name = "Sword of Stone"
    rarity = RelicRarity.EVENT
    ELITES = 5  # DynamicVar "Elites"

    def __init__(self) -> None:
        super().__init__()
        self.elites_defeated = 0

    def after_combat_end(self, run, room_type) -> None:
        from ..rooms import RoomType

        if room_type != RoomType.ELITE:
            return
        self.elites_defeated += 1
        if self.elites_defeated >= self.ELITES:
            from .sword_of_jade import SwordOfJade

            # RelicCmd.Replace: swap in place at this relic's index, then
            # AfterObtained on the replacement.
            jade = SwordOfJade()
            run.relics[run.relics.index(self)] = jade
            jade.after_obtained(run)
