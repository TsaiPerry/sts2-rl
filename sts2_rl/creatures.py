"""Creature base class — the common ground between the player and monsters.

A Creature owns the state every combatant shares: HP, block, the `powers`
list, side ("player"/"enemy"), and the `stunned`/`escaped` flags that the
combat loop reads. `PlayerCombatState` (player.py) and `Monster`
(monsters/base.py) both subclass it. Mirrors STS2's CreatureModel.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Iterator

if TYPE_CHECKING:
    from .powers import Power


class PowerList:
    """`Creature._powers` (Creature.cs:34) — an ORDERED LIST of power
    instances, not one slot per power id.

    C# holds `List<PowerModel> _powers` and lets several instances share an
    id: `PowerCmd.FindExistingInstanceForStacking` (PowerCmd.cs:165-174)
    returns `null` for a `PowerInstanceType.Instanced` power, so each
    application appends a new, independently ticking instance. The sim used a
    `dict[str, Power]` here, so a second Instanced application OVERWROTE the
    slot: the older instance stayed hook-registered and kept ticking, but no
    reader could see it. That is the state half of `power_cmd/G5`.

    Reads mirror C#'s own accessors exactly, so a sim call site translates
    one-for-one:

    ==========================  =========================================
    sim                         C# (Creature.cs)
    ==========================  =========================================
    ``id in creature.powers``   ``HasPower(id)``          (:561, Any)
    ``creature.powers[id]``     ``GetPower(id)``          (:571, First)
    ``.get(id)``                ``GetPower(id)``          (:571, First)
    ``.instances(id)``          ``GetPowerInstances(id)`` (:581, Where)
    ``.values()``               ``Powers``                (:326, all)
    ==========================  =========================================

    NOT a Mapping, deliberately: ``values()`` walks every instance in
    application order (what the hook walk, the death strip and the turn-start
    snapshot all need — C# iterates `_powers` at each of those sites), while
    ``__iter__``/``keys()`` yield each id ONCE, in first-application order, so
    ``"minion" in c.powers`` and ``set(c.powers)`` keep reading as before.
    ``len()`` counts INSTANCES, matching `_powers.Count`.
    """

    __slots__ = ("_list",)

    def __init__(self) -> None:
        self._list: list[Power] = []

    # ── C# Creature accessors ────────────────────────────────────────────
    def __contains__(self, power_id: object) -> bool:
        return any(p.id == power_id for p in self._list)

    def get(self, power_id: str, default=None):
        """`Creature.GetPower(id)` — the FIRST (oldest) instance, or
        ``default``. C# is `FirstOrDefault`, so a second Instanced
        application never displaces the answer."""
        for p in self._list:
            if p.id == power_id:
                return p
        return default

    def __getitem__(self, power_id: str):
        p = self.get(power_id)
        if p is None:
            raise KeyError(power_id)
        return p

    def instances(self, power_id: str) -> tuple:
        """`Creature.GetPowerInstances(id)` (Creature.cs:581) — every
        instance sharing this id, in application order."""
        return tuple(p for p in self._list if p.id == power_id)

    def values(self) -> tuple:
        """`Creature.Powers` (Creature.cs:326) — EVERY instance, in
        application order. Returned as a tuple: callers walk this while
        expiring powers, and C#'s own sites (`RemoveAllPowersInternalExcept`,
        Creature.cs:660) snapshot to a list first for the same reason."""
        return tuple(self._list)

    def items(self) -> tuple:
        return tuple((p.id, p) for p in self._list)

    def keys(self) -> tuple:
        return tuple(self)

    def __iter__(self) -> Iterator[str]:
        seen: set[str] = set()
        for p in self._list:
            if p.id not in seen:
                seen.add(p.id)
                yield p.id

    def __len__(self) -> int:
        return len(self._list)

    def __repr__(self) -> str:
        return f"PowerList({list(self._list)!r})"

    # ── Mutation (command layer only) ────────────────────────────────────
    def add(self, power: Power) -> None:
        """`Creature.ApplyPowerInternal` (Creature.cs:600-612) — appends.

        C#'s own guard here throws on a second `PowerInstanceType.None`
        instance ("Trying to add multiple instances of a non-instanced
        power"); `PowerCmd.apply` routes those to `on_stack` instead, so
        reaching this method with one is a bug in the command layer.
        """
        from .powers import PowerInstanceType

        if (power.instance_type is PowerInstanceType.NONE
                and power.id in self):
            raise RuntimeError(
                f"second instance of the non-instanced power {power.id!r}")
        self._list.append(power)

    def discard(self, power: Power) -> bool:
        """`Creature.RemovePowerInternal` (Creature.cs:641-650) — removes THIS
        instance by identity, never "whichever one has that id". Returns
        whether it was attached."""
        for i, p in enumerate(self._list):
            if p is power:
                del self._list[i]
                return True
        return False

    def pop(self, power_id: str, default=None):
        """Remove and return the FIRST instance with this id — the shape
        `PowerCmd.Remove<T>(creature)` has in C# (PowerCmd.cs:278-281:
        `Remove(creature.GetPower<T>())`, a `FirstOrDefault`)."""
        p = self.get(power_id)
        if p is None:
            return default
        self.discard(p)
        return p


class Creature:
    def __init__(self, max_hp: int) -> None:
        self.max_hp = max_hp
        self.hp = max_hp
        self.block = 0
        self.side: str = "enemy"
        self.powers: PowerList = PowerList()
        # Set by CreatureCmd.stun; the creature skips its next turn.
        self.stunned = False
        # Set by CreatureCmd.escape; the creature has left combat alive.
        self.escaped = False
        # Set on death when Hook.ShouldCreatureBeRemovedFromCombatAfterDeath
        # says no (CreatureCmd.cs:508): the corpse stays in CombatState.Enemies
        # — it still shows in the UI/recording and still takes turns, which is
        # how a withered Decimillipede segment reaches its REATTACH move.
        self.retained_after_death = False
        # `Creature.SlotName` — the named Encounter.Slots entry this creature
        # occupies, or None for an encounter with no slot row. It is what decides
        # the creature's POSITION in CombatState.Enemies: CreatureCmd.Add appends
        # and then CombatManager.AddCreature re-sorts the whole list by
        # `Encounter.Slots.IndexOf(SlotName)` whenever the added creature has one
        # (CombatManager.cs:841-851 -> CombatState.cs:495-501).
        self.slot_name: str | None = None

    @property
    def strength(self) -> int:
        """Convenience read of the StrengthPower amount; 0 if not present."""
        p = self.powers.get("strength")
        return p.amount if p is not None else 0

    @property
    def is_dead(self) -> bool:
        return self.hp <= 0

    @property
    def is_gone(self) -> bool:
        """Dead or escaped — no longer participating in combat."""
        return self.is_dead or self.escaped

    @property
    def is_removed_from_combat(self) -> bool:
        """C#'s `Creature.CombatState == null`, which is what
        `CanReceivePowers` actually refuses on (Creature.cs:308-322).

        The sim never physically drops a creature from `CombatState.enemies` —
        conformance addresses enemies by index, so a corpse holds its slot —
        so "was it removed?" is a predicate rather than a list membership.
        C# removes on exactly two paths and both are recorded here:
        `KillWithoutCheckingWinCondition` removes only when
        `Hook.ShouldCreatureBeRemovedFromCombatAfterDeath` agrees
        (CreatureCmd.cs:508, :523-531), and `CreatureCmd.Escape` always removes
        (:600-601); `CombatState.RemoveCreature` is what nulls the back-pointer
        (CombatState.cs:299-302).

        This is NOT `is_gone`. A creature can be DEAD and still in the combat —
        SteamEruptionPower.cs:28-35, PainfulStabsPower.cs:29-32,
        IllusionPower.cs:108-114, ReattachPower.cs:93-96 and AdaptablePower.cs:58-66
        all veto their owner's removal — and C#'s own doc comment for
        `CanReceivePowers` says of that state, in as many words, that "dead
        creatures can still have powers applied to them".
        """
        return self.is_gone and not self.retained_after_death

    def snapshot_powers_on_turn_start(self) -> None:
        """`Creature.BeforeTurnStart` (Creature.cs:673-679) —

            foreach (PowerModel power in _powers)
                power.AmountOnTurnStart = power.Amount;

        Called from `CombatManager.StartTurn`'s own per-creature loop
        (CombatManager.cs:447-450), which runs before ANYTHING else in the
        turn — before `Hook.BeforeSideTurnStart`, before the block clear,
        before the enemy move-roll pass. Every power gets snapshotted, not
        just the ones that read it (DrawCardsNextTurnPower, HelloWorldPower).

        The attribute is set here via plain assignment rather than declared
        on `Power.__init__` — `power_cmd/G5`-adjacent code elsewhere in
        `powers.py` is owned by a concurrent task this wave, so readers use
        `getattr(power, "amount_on_turn_start", 0)`, which is exactly what an
        un-snapshotted (freshly-applied-this-turn) power's C# field would
        read: the type's zero default.
        """
        for power in self.powers.values():
            power.amount_on_turn_start = power.amount
