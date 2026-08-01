"""Creature base class — the common ground between the player and monsters.

A Creature owns the state every combatant shares: HP, block, the `powers`
dict, side ("player"/"enemy"), and the `stunned`/`escaped` flags that the
combat loop reads. `PlayerCombatState` (player.py) and `Monster`
(monsters/base.py) both subclass it. Mirrors STS2's CreatureModel.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .powers import Power


class Creature:
    def __init__(self, max_hp: int) -> None:
        self.max_hp = max_hp
        self.hp = max_hp
        self.block = 0
        self.side: str = "enemy"
        self.powers: dict[str, Power] = {}
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
