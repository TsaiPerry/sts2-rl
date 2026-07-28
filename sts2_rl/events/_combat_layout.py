"""Room-entry encounter generation for `EventLayoutType.Combat` events.

`EventRoom.EnterInternal` calls `EventModel.GenerateInternalCombatState`
(EventRoom.cs:69-72) for every Combat-layout event — the monsters are visible
behind the event text, so they exist from the moment the room is entered:

    _mutableEncounter = CanonicalEncounter.ToMutable();
    _mutableEncounter.GenerateMonstersWithSlots(runState);       // encounter Rng
    ... CreateCreature(...) -> SetUniqueMonsterHpValue(...)      // Niche stream
                                                     (EventModel.cs:383-403)

`EnterCombatWithoutExitingEvent` then REUSES that state instead of building a
second one (`ShouldCreateCombat = LayoutType != Combat`, EventModel.cs:624-628),
so the draws are spent exactly once and UNCONDITIONALLY: a player who declines
the fight has already paid them.

The sim cannot hand live creatures to `RunState.create_combat` — the combat owns
the `HookSystem` its enemies' powers register into — so the room-entry pass
keeps only what is observable off the event: the Niche HP rolls. The fight
option then wraps the encounter in a `PregeneratedEncounter`, which rebuilds the
creatures against the real combat's hooks and stamps the HP that was already
rolled. Everything else the pass touches is a freshly seeded private stream
(`make_encounter_rng` is re-seeded from the same run seed / floor / entry, so
re-running it yields the same composition) or a throwaway.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ..monsters import Encounter

if TYPE_CHECKING:
    from ..monsters import Monster
    from ..run import RunState


@dataclass
class PregeneratedEncounter(Encounter):
    """An encounter whose creatures were already generated at event-room entry.

    Mirrors `EnterCombatWithoutExitingEvent` reusing
    `_combatStateForCombatLayout`: no second `GenerateMonstersWithSlots` /
    `SetUniqueMonsterHpValue` pass, so the run's Niche stream does not move
    again when the fight actually starts.
    """

    # The canonical encounter this was generated from (EventModel.
    # CanonicalEncounter); it still owns the composition.
    source: Encounter | None = None
    # `Creature.SetUniqueMonsterHpValue`'s results, in creation order, rolled at
    # room entry.
    pregenerated_hp: list[int] = field(default_factory=list)
    # Read by the combat builder: these creatures already have their HP, so the
    # Niche roll must not run a second time.
    monsters_are_pregenerated: bool = True

    @classmethod
    def of(cls, source: Encounter, pregenerated_hp: list[int]) -> "PregeneratedEncounter":
        return cls(
            id=source.id,
            monster_classes=list(source.monster_classes),
            should_give_rewards=source.should_give_rewards,
            min_gold=source.min_gold,
            max_gold=source.max_gold,
            source=source,
            pregenerated_hp=list(pregenerated_hp),
        )

    def create_monsters(self, hooks, rng, selection_rng=None) -> list["Monster"]:
        monsters = self.source.create_monsters(hooks, rng, selection_rng)
        for monster, hp in zip(monsters, self.pregenerated_hp):
            monster.hp = monster.max_hp = hp
        return monsters


class _RoomEntryCombat:
    """The `CombatState` GenerateInternalCombatState builds at room entry, cut
    down to what creature construction reads off it: the combat's stream
    bundle. `CombatState.__init__` likewise sets `hooks.combat` before it
    creates the enemies, so a monster that draws while being built (a state
    machine rolling its opening move) draws on the run's real streams."""

    def __init__(self, run: "RunState") -> None:
        from ..combat_rng import CombatRng
        self.combat_rng = (
            CombatRng.parity(run.rng_set) if run.rng_set is not None
            else CombatRng.legacy(run.rng)
        )


def pregenerate_monster_hp(run: "RunState", encounter: Encounter | None) -> list[int]:
    """Run `GenerateInternalCombatState`'s draws for `encounter` and return the
    HP each creature was given, in creation order.

    Only the Niche stream is a run-wide stream, so it is the only thing this
    spends: the composition rides a per-encounter Rng seeded from the run seed,
    the current floor and the encounter's entry (`EncounterModel.
    GenerateMonstersWithSlots`), which is re-seeded identically when the fight
    builds the creatures for real, and the creatures built here are a vehicle
    for the roll rather than the ones that fight.

    Legacy (non-parity) runs have no Niche stream, so there is nothing to
    pre-roll and this is a no-op.
    """
    if encounter is None or run.rng_set is None:
        return []
    from ..combat import CombatState
    from ..hooks import HookSystem
    from ..rng import make_encounter_rng

    selection_rng = make_encounter_rng(
        run.rng_set.seed, run.total_floor, encounter.entry)
    hooks = HookSystem()
    hooks.combat = _RoomEntryCombat(run)
    monsters = encounter.create_monsters(hooks, random.Random(0), selection_rng)
    # CombatState.CreateCreature -> Creature.SetUniqueMonsterHpValue, then
    # MonsterModel.AfterAddedToRoom's HP fix-up — the same pass the combat runs.
    CombatState._assign_parity_monster_hp(monsters, run.rng_set.niche)
    return [m.max_hp for m in monsters]
