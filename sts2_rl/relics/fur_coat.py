from __future__ import annotations

from .base import Relic, RelicRarity, register_relic


@register_relic
class FurCoat(Relic):
    """FurCoat.cs — upon pickup, mark 7 random Monster/Elite rooms on the
    CURRENT act's map ("Combats" = 7; the marks re-apply if the map is
    regenerated in the same act, ModifyGeneratedMapLate). Entering a marked
    room's combat sets EVERY enemy to 1 HP at combat start (SetCurrentHp), and
    any enemy that joins mid-fight too (AfterCreatureAddedToCombat)."""

    id = "fur_coat"
    name = "Fur Coat"
    rarity = RelicRarity.ANCIENT

    COMBATS = 7

    def __init__(self) -> None:
        super().__init__()
        self.act_index: int | None = None
        self.marked_coords: set[tuple[int, int]] = set()
        # Set on room entry when the entered point is marked; cleared after
        # the combat ends.
        self._armed = False

    # ── Marking ──────────────────────────────────────────────────────────

    def _mark_rooms(self, run, act_map) -> None:
        from ..actmap import MapPointType

        candidates = [
            p for p in act_map.all_points()
            if p.point_type in (MapPointType.MONSTER, MapPointType.ELITE)
        ]
        # FurCoat.cs: new Rng(owner, Id).UnstableShuffle(points) — a per-relic
        # deterministic stream = Rng(run seed + slot(0) + hash(relic Entry)),
        # matching make_event_rng keyed on the relic id. Legacy keeps the
        # shared run rng.
        if run.rng_set is not None:
            from ..rng import make_event_rng
            make_event_rng(run.rng_set.seed, self.id.upper()).shuffle(candidates)
        else:
            run.rng.shuffle(candidates)
        self.marked_coords = {
            p.coord for p in candidates[: self.COMBATS]
        }

    def after_obtained(self, run) -> None:
        if run.map is not None:
            self.act_index = run.act_index
            self._mark_rooms(run, run.map)

    def modify_generated_map_late(self, run, act_map, act_index):
        # Re-mark a regenerated same-act map (Golden Compass); keep existing
        # coords when they still point at Monster/Elite rooms.
        if self.act_index == act_index and self.marked_coords:
            from ..actmap import MapPointType

            def still_valid(coord) -> bool:
                point = act_map.get_point(*coord)
                return point is not None and point.point_type in (
                    MapPointType.MONSTER, MapPointType.ELITE,
                )

            if not all(still_valid(c) for c in self.marked_coords):
                self._mark_rooms(run, act_map)
        return act_map

    # ── The 1-HP effect ──────────────────────────────────────────────────

    def after_room_entered(self, run, point, room_type) -> None:
        self._armed = (
            self.act_index == run.act_index
            and point.coord in self.marked_coords
        )

    def on_combat_start(self) -> None:
        if not self._armed:
            return
        for enemy in self.living_enemies():
            enemy.hp = 1  # SetCurrentHp: a raw set, no damage pipeline

    def on_creature_added(self, creature) -> None:
        if self._armed and creature.side == "enemy":
            creature.hp = 1

    def after_combat_end(self, run, room_type) -> None:
        self._armed = False
