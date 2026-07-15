"""Golden Compass — the Ancient relic that turns an act into the golden path.

Port of GoldenCompass.cs. When obtained it records the current act and
regenerates that act's map as the fixed single-column GoldenPathActMap; every
"?" node on that act then resolves to an Event.

See sts2_rl.actmap.golden_path_map for the map, and RunState._apply_map_modifiers
/ RunState._unknown_allowed_room_types for the pipeline.
"""
from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class GoldenCompass(Relic):
    """GoldenCompass.cs — Ancient relic; golden-paths the act it is picked up in."""

    id = "golden_compass"
    name = "Golden Compass"
    rarity = RelicRarity.ANCIENT

    def __init__(self) -> None:
        super().__init__()
        # GoldenCompass.GoldenPathAct — the act index the golden path applies
        # to (-1 until obtained).
        self.golden_path_act = -1

    def after_obtained(self, run) -> None:
        """GoldenCompass.AfterObtained: pin the current act and regenerate."""
        self.golden_path_act = run.act_index
        run.regenerate_map()

    def modify_generated_map(self, run, act_map, act_index):
        if self.golden_path_act != act_index:
            return act_map
        from ..actmap import golden_path_map

        return golden_path_map(rng=run.rng, config=run.act_config)

    def modify_unknown_map_point_room_types(self, run, room_types):
        if self.golden_path_act != run.act_index:
            return room_types
        from ..rooms import RoomType

        return {RoomType.EVENT}
