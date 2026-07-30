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

    # NO `modify_generated_map_late` OVERRIDE. FurCoat.cs:57-60 has one, but
    # `Hook.ModifyGeneratedMapLate` has exactly ONE caller in the game: the
    # SavedActMap branch of RunManager.GenerateMap (RunManager.cs:740, inside
    # `if (SavedMapsToLoad != null && SavedMapsToLoad.TryGetValue(...))`), the
    # branch that DESERIALIZES a saved map. The branch that GENERATES one
    # (:743-747) runs ModifyGeneratedMap and AfterMapGenerated only — the Late
    # hook exists to re-attach quests/shape to a LOADED map. The sim has no
    # save-load, so on the only path it has, the game never calls this.
    #
    # The port implemented it and the sim dispatches the pass (card/spoils_map
    # needs it — see RunState._generate_map), so Fur Coat re-marked on every
    # fresh generation and could RE-ROLL: take Fur Coat and then Golden Compass
    # in the same act, and the sim regenerated the map, saw the golden path had
    # invalidated the marked coords, and rolled five fresh ones off a new
    # event-rng shuffle where the game leaves the persisted FurCoatCoordCols/Rows
    # arrays untouched — so only the marks that happen to fall on the golden
    # path's single column can ever fire. It also burned a shuffle the game never
    # takes, a parity divergence on its own. Dropping the override is what closes
    # relic/fur_coat/g2; the marks are set once, by `after_obtained`.

    # ── The 1-HP effect ──────────────────────────────────────────────────

    def after_room_entered(self, run, point, room_type) -> None:
        # FurCoat.cs has an act check in exactly ONE place: AddMarkedRooms
        # (:64-67), which controls only whether the marks are ATTACHED to a map.
        # BeforeCombatStart (:114-120) tests `GetMarkedCoords().Contains(
        # RunState.CurrentMapPoint.coord)` and NOTHING ELSE — and a MapCoord is a
        # bare (col, row) pair with no act component, so a coord that recurs in a
        # later act fires again. The sim's latch also required
        # `act_index == run.act_index`, so it never did: with 7 act-0 coords
        # marked, between 1 and all 7 survive onto the act-1 map on the seeds the
        # entry's probe measured, and in the game every one of those combats opens
        # with the enemies at 1 HP. Recorded as a gap against the source even
        # though the source's behaviour looks like a bug: the ground truth is the
        # decompiled game.
        self._armed = point.coord in self.marked_coords

    def on_combat_start(self) -> None:
        if not self._armed:
            return
        # FurCoat.cs:121-127 walks `CombatState.HittableEnemies`, not every enemy
        # that is not gone: a creature can be present and un-hittable.
        for enemy in self.hittable_enemies():
            enemy.hp = 1  # SetCurrentHp: a raw set, no damage pipeline

    def on_creature_added(self, creature) -> None:
        if self._armed and creature.side == "enemy":
            creature.hp = 1

    def after_combat_end(self, run, room_type) -> None:
        self._armed = False
