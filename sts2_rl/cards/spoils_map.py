"""Spoils Map — the quest card that reshapes Act 2 into the hourglass map.

Port of SpoilsMap.cs. An unplayable Quest card that, while it sits in the deck
during its target act (Act 2, index 1):
  - replaces the generated map with the converging SpoilsActMap (hourglass),
  - marks the single treasure node with itself as a quest, so that
  - entering that treasure pays out 600 gold and removes the card.

See sts2_rl.actmap.SpoilsActMap for the map, and RunState.enter_point /
RunState._apply_map_modifiers for the pipeline that drives these hooks.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class SpoilsMapCard(Card):
    """SpoilsMap.cs — 600-gold quest card, active in Act 2."""

    id = "spoils_map"
    name = "Spoils Map"
    card_type = CardType.QUEST
    rarity = CardRarity.QUEST
    target_type = TargetType.SELF
    is_playable = False  # CardKeyword.Unplayable
    max_upgrade_level = 0

    GOLD = 600
    # SpoilsMap.AfterCreated sets SpoilsActIndex = 1 (Act 2).
    SPOILS_ACT_INDEX = 1

    def _init_vars(self) -> None:
        self.spoils_act_index = self.SPOILS_ACT_INDEX
        # The treasure node coord recorded during the late map pass.
        self.spoils_coord: tuple[int, int] | None = None

    def on_play(self, ctx: "CombatCtx", target_idx: int | None = None) -> None:
        pass  # Unplayable.

    def _active_in(self, run, act_index: int) -> bool:
        """The card only acts on its target act while it is in the deck (the
        source guards on Pile.Type == Deck)."""
        return act_index == self.spoils_act_index and self in run.deck

    # ── Map-generation hooks ──────────────────────────────────────────────

    def modify_generated_map(self, run, act_map, act_index):
        if not self._active_in(run, act_index):
            return act_map
        from ..actmap import SpoilsActMap

        return SpoilsActMap(
            rng=run.rng, config=run.act_config, ascension=run.ascension
        )

    def modify_generated_map_late(self, run, act_map, act_index):
        if not self._active_in(run, act_index):
            return act_map
        from ..actmap import MapPointType

        self.spoils_coord = None
        for point in act_map.all_points():
            if point.point_type == MapPointType.TREASURE:
                self.spoils_coord = point.coord
                break
        return act_map

    def after_map_generated(self, run, act_map, act_index) -> None:
        if not self._active_in(run, act_index) or self.spoils_coord is None:
            return
        point = act_map.get_point(*self.spoils_coord)
        if point is not None:
            point.add_quest(self)

    # ── Quest completion (entering the treasure node) ─────────────────────

    def on_quest_complete(self, run) -> int:
        """SpoilsMap.OnQuestComplete: pay 600 gold and remove the card."""
        run.gain_gold(self.GOLD)
        if run.map is not None and self.spoils_coord is not None:
            point = run.map.get_point(*self.spoils_coord)
            if point is not None:
                point.remove_quest(self)
        if self in run.deck:
            run.deck.remove(self)
        return self.GOLD
