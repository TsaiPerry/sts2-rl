"""Powers — buffs and debuffs, mirroring STS2's PowerModel (src/Core/Models/
Powers).

Every power subclasses `Power` and overrides only the hook methods it needs;
the HookSystem calls them by duck-typing. `PowerCmd.apply` (cmds.py) handles
stacking, Artifact interception of debuffs, and registration; `_tick` /
`_tick_duration` handle duration decrement and `_expire` unregisters.

Organised into sections: Buffs, Debuffs, Ironclad card powers, Overgrowth
(Act 1) enemy powers, Hive (Act 2) enemy powers, Glory (Act 3) powers, and
Colorless card powers, followed by the `ALL_POWERS` id→class registry at
the bottom.
"""
from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

from .hooks import CAT_POWER
from .valueprops import ValueProp, is_card_or_monster_move, is_powered_attack, is_powered_card_or_monster_move_block

if TYPE_CHECKING:
    from .cards import Card
    from .creatures import Creature
    from .hooks import HookSystem


class PowerType(Enum):
    BUFF = "buff"
    DEBUFF = "debuff"


class PowerInstanceType(Enum):
    """Mirrors PowerInstanceType (PowerInstanceType.cs), consulted by
    PowerCmd.apply's stacking dispatch (power_cmd/G5, PowerCmd.cs:165-174).

    NONE (the default): re-applying finds the target's existing instance by
    id and stacks onto it via `on_stack`.
    INSTANCED: re-applying never finds an existing instance — every
    application starts its own, independently ticking/expiring one.
    INSTANCED_PER_APPLIER: re-applying finds an existing instance only if it
    shares the SAME applier; a different applier starts its own instance."""
    NONE = "none"
    INSTANCED = "instanced"
    INSTANCED_PER_APPLIER = "instanced_per_applier"


class Power:
    """
    Base class for all powers/buffs/debuffs, mirroring STS2's PowerModel.

    Subclasses override hook methods as needed. The hook system calls them
    via hasattr duck-typing, so only overridden methods are called.
    """

    id: str
    name: str
    power_type: PowerType
    # First in its owner's slice of the dispatch walk
    # (CombatState.IterateHookListeners, CombatState.cs:416).
    hook_category = CAT_POWER
    # Mirrors PowerModel.AllowNegative: powers that can hold a negative amount
    # (Strength, Dexterity). When stacking drops the amount to 0 (or below 0
    # for powers that don't allow negatives) the power is removed, mirroring
    # PowerCmd.ModifyAmount → ShouldRemoveDueToAmount.
    allow_negative = False
    # Mirrors PowerModel.InstanceType (PowerModel.cs:144); see
    # PowerInstanceType above. Consulted by PowerCmd.apply (power_cmd/G5).
    instance_type = PowerInstanceType.NONE

    @classmethod
    def type_for_amount(cls, amount: int) -> PowerType:
        """PowerModel.GetTypeForAmount (PowerModel.cs:460-471).

        The SIGN-AWARE type. It is what Artifact tests
        (`canonicalPower.GetTypeForAmount(amount) != PowerType.Debuff`,
        ArtifactPower.cs:24), not the static `Type` — so a negative-amount
        application of a Buff-typed `allow_negative` power (Malaise stealing
        Strength, Resonance stealing Strength) is a Debuff by C#'s rule and
        Artifact blocks it.

        C#'s first clause is `StackType == Counter && AllowNegative`. The sim
        has no `PowerStackType` (audit `power_cmd/G5`), but every AllowNegative
        power in the game is Counter-stacking — StrengthPower.cs:14,
        DexterityPower.cs:14, FocusPower.cs and ShriekPower.cs declare it
        outright, and ShrinkPower's is Counter unless IsInfinite — so
        `allow_negative` alone carries the clause for all ported content.
        """
        if amount < 0:
            if cls.allow_negative:
                return PowerType.DEBUFF
            if cls.power_type is PowerType.DEBUFF:
                return PowerType.BUFF
        return cls.power_type

    def __init__(
        self,
        owner: Creature,
        amount: int,
        hooks: HookSystem,
        applier: Creature | None = None,
    ) -> None:
        self.owner = owner
        self.amount = amount
        self.hooks = hooks
        self.applier = applier
        # Set by PowerCmd.apply when a debuff lands on the player: the first
        # duration tick is skipped (mirrors PowerModel.SkipNextDurationTick).
        self.skip_next_tick = False

    def on_stack(self, amount: int) -> None:
        """Called when more of this power is applied to the same owner. Default: additive."""
        self.amount += amount

    def should_power_be_removed_after_owner_death(self) -> bool:
        """PowerModel.ShouldPowerBeRemovedAfterOwnerDeath (PowerModel.cs:637-640).

        **Defaults to True** — "Usually true, but false for powers that do
        things like revive their owner." Only six non-mock powers override it
        (Adaptable, DieForYou, Minion, PainfulStabs, Reattach, SteamEruption).
        The sim used to have no strip at all, which inverted this default:
        every power C# strips survived, so a killed Decimillipede segment came
        back at 25 HP still holding the Vulnerable it died with.
        """
        return True

    def should_owner_death_trigger_fatal(self) -> bool:
        """`PowerModel.ShouldOwnerDeathTriggerFatal` (PowerModel.cs:646).

        **Defaults to True.** A false answer does NOT prevent the death — the
        creature dies normally — it only suppresses the killer's Fatal payout
        (Feed's Max HP, Hand of Greed's gold). Exactly two non-mock powers
        override it and both are ported: MinionPower and ReattachPower.
        """
        return True

    def on_removed(self, owner: Creature) -> None:
        """PowerModel.AfterRemoved — awaited for each power stripped by
        `Creature.RemoveAllPowersAfterDeath` (CreatureCmd.cs:533-537). Default
        no-op."""

    # ── Internal helpers ─────────────────────────────────────────────────

    def _tick(self) -> None:
        """PowerCmd.Decrement (PowerCmd.cs:179-182) — `ModifyAmount(power, -1)`.

        Routed through the command rather than mutating `amount` in place, so
        the tick picks up ModifyAmount's `IsEnding` guard (power_cmd G6).
        """
        from .cmds import PowerCmd
        PowerCmd.modify_amount(self.hooks, self, -1)

    def _tick_duration(self) -> None:
        """PowerCmd.TickDownDuration (PowerCmd.cs:190-200) — Decrement, but
        SkipNextDurationTick is consumed FIRST and returns without calling it,
        so a debuff applied to the player during the enemy turn survives its
        first side-end tick (Vulnerable/Weak/Frail)."""
        if self.skip_next_tick:
            self.skip_next_tick = False
            return
        self._tick()

    def _expire(self) -> None:
        """Remove this power from owner.powers and unregister from the hook system.

        Identity-checked rather than a bare pop-by-id: a second application
        of an Instanced/InstancedPerApplier power (power_cmd/G5) overwrites
        the dict slot with a NEW instance while the one it replaced stays
        independently hook-registered, still ticking toward its own expiry.
        If THAT orphaned instance is the one expiring, a bare
        `owner.powers.pop(self.id)` would delete the other, still-live
        instance's dict entry instead of a no-op.
        """
        if self.owner.powers.get(self.id) is self:
            del self.owner.powers[self.id]
        try:
            self.hooks.unregister(self)
        except ValueError:
            pass

    def __repr__(self) -> str:
        return f"{self.name}({self.amount})"


# ── Buffs ─────────────────────────────────────────────────────────────────


class StrengthPower(Power):
    """Flat additive bonus to outgoing damage. Does not apply to unpowered cards."""

    id = "strength"
    name = "Strength"
    power_type = PowerType.BUFF
    allow_negative = True

    def modify_damage_additive(
        self,
        target: Creature,
        amount: int,
        dealer: Creature | None,
        card: Card | None,
        props: ValueProp = ValueProp.NONE,
    ) -> int:
        if not is_powered_attack(props):   # StrengthPower.cs:21
            return 0
        if dealer is self.owner and (card is None or not card.is_unpowered):
            return self.amount
        return 0


class DexterityPower(Power):
    """Flat additive bonus to block gained by the owner."""

    id = "dexterity"
    name = "Dexterity"
    power_type = PowerType.BUFF
    allow_negative = True

    def modify_block_additive(
        self,
        target: Creature,
        amount: int,
        card: Card | None,
        props: ValueProp = ValueProp.NONE,
    ) -> int:
        if not is_powered_card_or_monster_move_block(props):   # DexterityPower.cs:33
            return 0
        if target is self.owner:
            return self.amount
        return 0


class BarricadePower(Power):
    """Block is not cleared at the start of the owner's turn."""

    id = "barricade"
    name = "Barricade"
    power_type = PowerType.BUFF

    def should_clear_block(self, creature: Creature) -> bool:
        if creature is self.owner:
            return False
        return True


class RegenPower(Power):
    """Heal N HP at the end of the owner's turn, then decrement."""

    id = "regen"
    name = "Regen"
    power_type = PowerType.BUFF

    def _apply_regen(self) -> None:
        from .cmds import CreatureCmd
        CreatureCmd.heal(self.hooks, self.owner, self.amount)
        self._tick()

    def on_enemy_side_end(self) -> None:
        # RegenPower.cs:20 is AfterSideTurnEnd — ONE dispatch for the whole
        # side, so the `!Owner.IsDead` half of its guard has to be tested here:
        # on the old per-enemy slot the loop had already returned.
        if self.owner.side == "enemy" and not self.owner.is_dead:
            self._apply_regen()

    def after_player_turn_end(self, player: Creature) -> None:
        if self.owner is player and not self.owner.is_dead:
            self._apply_regen()


class RitualPower(Power):
    """
    Gain N Strength at the end of the owner's turn.

    Skips the first trigger if this power was applied by a creature on the
    opposing side (mirrors STS2's Ritual "skip first" behaviour).
    """

    id = "ritual"
    name = "Ritual"
    power_type = PowerType.BUFF

    def __init__(
        self,
        owner: Creature,
        amount: int,
        hooks: HookSystem,
        applier: Creature | None = None,
    ) -> None:
        super().__init__(owner, amount, hooks, applier)
        # RitualPower.cs:36-43 — `AfterApplied` sets WasJustAppliedByEnemy
        # whenever **base.Owner.IsEnemy**. The APPLIER is not consulted at all,
        # and every ported Ritual source is a monster buffing ITSELF — so the
        # old `applier.side != owner.side` test was False exactly where C#'s is
        # True, and the enemy took one extra Strength on the turn it cast
        # Ritual. The player-side direction is unchanged: Owner.IsEnemy is
        # false there and so was the applier-side test.
        self._was_just_applied = (owner.side == "enemy")

    def _trigger(self) -> None:
        if self._was_just_applied:
            self._was_just_applied = False
            return
        from .cmds import StrengthCmd
        StrengthCmd.apply(self.hooks, self.owner, self.amount)

    def on_enemy_side_end(self) -> None:
        # RitualPower.cs:45 — AfterSideTurnEnd, once for the side.
        if self.owner.side == "enemy":
            self._trigger()

    def after_player_turn_end(self, player: Creature) -> None:
        if self.owner is player:
            self._trigger()


class DemonFormPower(Power):
    """Gain N Strength at the START of the owner's turn each turn."""

    id = "demon_form"
    name = "Demon Form"
    power_type = PowerType.BUFF

    def after_enemy_side_start(self) -> None:
        # DemonFormPower.cs:21 — AfterSideTurnStart, once for the side.
        if self.owner.side == "enemy":
            from .cmds import StrengthCmd
            StrengthCmd.apply(self.hooks, self.owner, self.amount)

    def after_side_turn_start(self, player: Creature) -> None:
        if self.owner is player:
            from .cmds import StrengthCmd
            StrengthCmd.apply(self.hooks, self.owner, self.amount)


class FeelNoPainPower(Power):
    """Gain N block whenever a card is exhausted."""

    id = "feel_no_pain"
    name = "Feel No Pain"
    power_type = PowerType.BUFF

    def on_card_exhausted(self, card: Card,
                          caused_by_ethereal: bool = False) -> None:
        from .cmds import BlockCmd
        # FeelNoPainPower.cs:23 is `GainBlock(Owner, Amount, ValueProp.Unpowered,
        # null)`. BlockCmd.apply defaults to ValueProp.MOVE, which
        # `is_powered_attack` accepts, so the block was running the modifier
        # families: with Dexterity 3 the sim gave 6 where the game gives 3, and
        # under Frail it gave 2 where the game gives 3. Eight sibling powers
        # already pass this prop explicitly.
        BlockCmd.apply(self.hooks, self.owner, self.amount,
                       props=ValueProp.UNPOWERED)


class DarkEmbracePower(Power):
    """Draw 1 card whenever a card is exhausted. Owner must be the player."""

    id = "dark_embrace"
    name = "Dark Embrace"
    power_type = PowerType.BUFF

    def on_card_exhausted(self, card: Card,
                          caused_by_ethereal: bool = False) -> None:
        from .player import PlayerCombatState
        if isinstance(self.owner, PlayerCombatState):
            from .cmds import DrawCmd
            DrawCmd.draw(self.owner, 1)


class EnragePower(Power):
    """Gain N Strength whenever a Skill card is played."""

    id = "enrage"
    name = "Enrage"
    power_type = PowerType.BUFF

    def on_card_played(self, card: Card,
                       is_auto_play: bool = False) -> None:
        from .cards import CardType
        if card.card_type == CardType.SKILL:
            from .cmds import StrengthCmd
            StrengthCmd.apply(self.hooks, self.owner, self.amount)


class RupturePower(Power):
    """Gain N Strength whenever the owner loses HP from damage ON ITS OWN
    TURN — i.e. from self-inflicted HP loss, not from being attacked."""

    id = "rupture"
    name = "Rupture"
    power_type = PowerType.BUFF

    def __init__(
        self,
        owner: Creature,
        amount: int,
        hooks: HookSystem,
        applier: Creature | None = None,
    ) -> None:
        super().__init__(owner, amount, hooks, applier)
        # RupturePower.cs:31-43's `playedCards` dictionary: the card currently
        # being played by the owner, and the Strength accumulated for it.
        self._pending_card: Card | None = None
        self._pending_amount = 0

    def before_card_played(self, card: Card, is_auto_play: bool = False) -> None:
        # RupturePower.cs:31-43 — every card the owner STARTS playing during
        # its own side turn opens an accumulator entry. That is the whole point
        # of the deferral: a card that damages its own player several times
        # must not have its later hits boosted by the Strength its earlier hits
        # earned.
        combat = self.hooks.combat
        if combat is None or combat.current_side != self.owner.side:
            return
        self._pending_card = card
        self._pending_amount = 0

    def on_damage_received(
        self,
        target: Creature,
        amount: int,
        dealer: Creature | None,
        card: Card | None,
        props: ValueProp = ValueProp.NONE,
    ) -> None:
        if target is not self.owner or amount <= 0:
            return
        # RupturePower.cs:47 — `CombatState.CurrentSide == Owner.Side`. Without
        # it a self-harm payoff card became a free Strength engine that grew
        # whenever the player was hit on the ENEMY's turn.
        combat = self.hooks.combat
        if combat is not None and combat.current_side != self.owner.side:
            return
        if self._pending_card is not None:
            self._pending_amount += self.amount   # accumulate, do not apply
            return
        from .cmds import StrengthCmd
        StrengthCmd.apply(self.hooks, self.owner, self.amount)

    def on_card_played(self, card: Card, is_auto_play: bool = False) -> None:
        # The accumulated total lands once the card has fully resolved.
        if card is not self._pending_card:
            return
        self._pending_card = None
        pending, self._pending_amount = self._pending_amount, 0
        if pending:
            from .cmds import StrengthCmd
            StrengthCmd.apply(self.hooks, self.owner, pending)


class CurlUpPower(Power):
    """Gain N block the first time the owner is hit. One-shot."""

    id = "curl_up"
    name = "Curl Up"
    power_type = PowerType.BUFF

    def __init__(
        self,
        owner: Creature,
        amount: int,
        hooks: HookSystem,
        applier: Creature | None = None,
    ) -> None:
        super().__init__(owner, amount, hooks, applier)
        self._played_card: Card | None = None

    def on_damage_received(
        self,
        target: Creature,
        amount: int,
        dealer: Creature | None,
        card: Card | None,
        props: ValueProp = ValueProp.NONE,
    ) -> None:
        # CurlUpPower.cs:34-54 only LATCHES the triggering card here and grants
        # NOTHING. Granting on the spot meant the second and later hits of a
        # multi-hit attack were absorbed by block the game had not handed out
        # yet. The three C# guards come with it: the owner, a POWERED attack,
        # a non-null cardSource, and no re-latch onto a different card.
        if target is not self.owner or card is None:
            return
        if not is_powered_attack(props):
            return
        if self._played_card is not None and card is not self._played_card:
            return
        self._played_card = card

    def on_card_played(self, card: Card, is_auto_play: bool = False) -> None:
        # CurlUpPower.cs:56-70 — the block lands once the whole card play has
        # resolved, UNPOWERED, and the power is removed with it.
        if card is not self._played_card:
            return
        self._played_card = None
        from .cmds import BlockCmd
        BlockCmd.apply(self.hooks, self.owner, self.amount,
                       props=ValueProp.UNPOWERED)
        self._expire()


class ArtifactPower(Power):
    """
    Blocks the next N debuffs applied to the owner.

    A real `modify_power_amount_received` / `after_modify_power_amount_received`
    listener pair now (power_cmd/G3, G4 — was hard-coded as a direct block in
    `PowerCmd.apply`, outside the hook-listener system entirely).
    `TryModifyPowerAmountReceived` (ArtifactPower.cs:17-36) is where the
    interception decision lives — it zeroes the incoming amount when it
    intercepts, it does not short-circuit the caller — and
    `AfterModifyingPowerAmountReceived` (ArtifactPower.cs:38-41) is where the
    charge is actually spent (`PowerCmd.Decrement(this)`), not inline in the
    command.
    """

    id = "artifact"
    name = "Artifact"
    power_type = PowerType.BUFF

    def modify_power_amount_received(
        self,
        power_cls: type[Power],
        target: Creature,
        amount: int,
        applier: Creature | None,
    ) -> int | None:
        """ArtifactPower.cs:17-36. `self.owner` is Artifact's OWN owner —
        this only ever intercepts a debuff aimed at the creature that holds
        it; C#'s own `target` parameter is likewise the recipient of the
        power being applied, not `applier`."""
        if target is not self.owner:
            return None
        # ArtifactPower.cs:24 — sign-aware: `type_for_amount(amount)`, not
        # the static `Type` (power_cmd/G1, already fixed).
        if power_cls.type_for_amount(amount) != PowerType.DEBUFF:
            return None
        # ArtifactPower.cs:29-33 tests `canonicalPower.IsVisible` here too.
        # IsVisible is provably always true for every power in the current
        # game (power_cmd/N1, waived) — omitted.
        return 0

    def after_modify_power_amount_received(self, power) -> None:
        """ArtifactPower.cs:38-41 — decrements ITSELF, ignoring the `power`
        argument entirely (C#: `await PowerCmd.Decrement(this);`)."""
        self._tick()


class ThornsPower(Power):
    """Reflect N damage to the attacker when the owner is hit.

    The reflected damage is unpowered but blockable (STS2's ThornsPower deals
    ValueProp.Unpowered damage): the attacker's block absorbs it, Strength and
    Vulnerable do not modify it."""

    id = "thorns"
    name = "Thorns"
    power_type = PowerType.BUFF

    def before_damage_received(
        self,
        target: Creature,
        amount: int,
        dealer: Creature | None,
        card: Card | None,
        props: ValueProp = ValueProp.NONE,
    ) -> None:
        # ThornsPower.cs:17-24 is BeforeDamageReceived, guarded by
        # `target == Owner && dealer != null && (props.IsPoweredAttack() ||
        # cardSource is Omnislice)`. Both halves matter: on the Before hook the
        # reflect survives a killing blow, and the props gate stops it
        # reflecting off unpowered non-attack damage (Juggernaut, Panache,
        # Inferno, Rolling Boulder, The Bomb, Flame Barrier) that the game
        # ignores. Omnislice is unported, so the second disjunct has no site.
        if target is not self.owner or dealer is None:
            return
        if not is_powered_attack(props):
            return
        from .cmds import DamageCmd
        from .valueprops import DamageProps
        # ThornsPower.cs:22 deals the reflect BY `base.Owner`:
        # `CreatureCmd.Damage(ctx, dealer, Amount, Unpowered|SkipHurtAnim,
        #                     base.Owner, null)`
        # — the 5th argument is the DEALER. The port left it None, which is not
        # a cosmetic omission: `on_damage_dealt` is gated on `dealer is not
        # None` (cmds.py), so Hook.AfterDamageGiven (CreatureCmd.cs:390) never
        # fired for a reflect and no Thorns-on-Thorns chain was possible, and
        # the dead-dealer early return (CreatureCmd.cs:242-245) had nothing to
        # test. FlameBarrierPower, the same shape one power over, already
        # passed it.
        DamageCmd.deal(
            self.hooks, dealer, self.amount,
            dealer=self.owner, props=DamageProps.NON_CARD_UNPOWERED,
        )


class IntangiblePower(Power):
    """Cap all incoming damage at 1. Ticks at the end of the enemy's turn."""

    id = "intangible"
    name = "Intangible"
    power_type = PowerType.BUFF

    def modify_damage_cap(
        self,
        target: Creature,
        dealer: Creature | None,
        card: Card | None,
    ) -> int | None:
        # Caps block loss and damage preview (mirrors STS2 ModifyDamageCap)
        if target is self.owner:
            return 1
        return None

    def modify_hp_lost(
        self,
        target: Creature,
        amount: int,
        dealer: Creature | None,
        card: Card | None,
    ) -> int:
        # Caps actual HP loss at 1 (mirrors STS2 ModifyHpLostAfterOsty)
        if target is self.owner:
            return min(amount, 1)
        return amount

    def on_enemy_side_end(self) -> None:
        self._tick()


# ── Debuffs ───────────────────────────────────────────────────────────────


class VulnerablePower(Power):
    """Target takes 50% more damage. Ticks at the end of the enemy's turn.

    The dealer's Cruelty stacks raise the multiplier (mirrors the game's
    VulnerablePower consulting CrueltyPower.ModifyVulnerableMultiplier)."""

    id = "vulnerable"
    name = "Vulnerable"
    power_type = PowerType.DEBUFF

    def modify_damage_multiplicative(
        self,
        target: Creature,
        amount: int,
        dealer: Creature | None,
        card: Card | None,
        props: ValueProp = ValueProp.NONE,
    ) -> float:
        if not is_powered_attack(props):   # VulnerablePower.cs:33
            return 1.0
        if target is not self.owner:
            return 1.0
        mult = 1.5
        if dealer is not None:
            cruelty = dealer.powers.get("cruelty")
            if cruelty is not None:
                mult += cruelty.amount / 100.0
        return self.hooks.modify_vulnerable_multiplier(dealer, mult)

    def on_enemy_side_end(self) -> None:
        self._tick_duration()


class WeakPower(Power):
    """Dealer deals 25% less damage. Ticks at the end of the enemy's turn."""

    id = "weak"
    name = "Weak"
    power_type = PowerType.DEBUFF

    def modify_damage_multiplicative(
        self,
        target: Creature,
        amount: int,
        dealer: Creature | None,
        card: Card | None,
        props: ValueProp = ValueProp.NONE,
    ) -> float:
        if not is_powered_attack(props):   # WeakPower.cs:30
            return 1.0
        if dealer is self.owner:
            return 0.75
        return 1.0

    def on_enemy_side_end(self) -> None:
        self._tick_duration()


class FrailPower(Power):
    """Owner gains 25% less block. Ticks at the end of the enemy's turn."""

    id = "frail"
    name = "Frail"
    power_type = PowerType.DEBUFF

    def modify_block_multiplicative(
        self,
        target: Creature,
        amount: int,
        card: Card | None,
        props: ValueProp = ValueProp.NONE,
    ) -> float:
        if not is_powered_card_or_monster_move_block(props):   # FrailPower.cs:28
            return 1.0
        if target is self.owner:
            return 0.75
        return 1.0

    def on_enemy_side_end(self) -> None:
        self._tick_duration()


class PoisonPower(Power):
    """Deal N unblockable damage to the owner at the start of their side's turn, then decrement."""

    id = "poison"
    name = "Poison"
    power_type = PowerType.DEBUFF

    def _apply_poison(self) -> None:
        if self.owner.is_dead:
            return
        from .cmds import DamageCmd
        from .valueprops import DamageProps
        # Unblockable, unpowered HP loss (STS2: ValueProp.Unblockable | Unpowered)
        DamageCmd.deal(
            self.hooks, self.owner, self.amount, props=DamageProps.NON_CARD_HP_LOSS
        )
        self._tick()

    def after_enemy_side_start(self) -> None:
        # PoisonPower.cs:55-73 — AfterSideTurnStart, ONE dispatch for the whole
        # side before any enemy moves, so a three-enemy board takes all three
        # poison ticks up front.
        if self.owner.side == "enemy":
            self._apply_poison()

    def after_side_turn_start(self, player: Creature) -> None:
        if self.owner is player:
            self._apply_poison()


# ── Ironclad card powers ─────────────────────────────────────────────────


class AggressionPower(Power):
    """At the start of the owner's turn (before the hand draw), move N random
    Attack cards from the discard pile to the hand and upgrade them."""

    id = "aggression"
    name = "Aggression"
    power_type = PowerType.BUFF

    def before_side_turn_start(self, player: Creature) -> None:
        if player is not self.owner:
            return
        combat = self.hooks.combat
        if combat is None:
            return
        from .cards import CardType
        candidates = [c for c in player.discard_pile if c.card_type == CardType.ATTACK]
        if not candidates:
            return
        chosen = combat._rng.sample(candidates, min(self.amount, len(candidates)))
        for card in chosen:
            player.discard_pile.remove(card)
            player.hand.append(card)
            if card.upgrade_level == 0:  # IsUpgradable: only unupgraded cards
                card.upgrade()


class NoDrawPower(Power):
    """Blocks all mid-turn card draws (start-of-turn hand draws are exempt).
    Removed at the end of the owner's turn. StackType.Single only hides the
    Amount display (PowerCmd.ModifyAmount adds unconditionally); Amount still
    accumulates on re-application, but nothing reads it here."""

    id = "no_draw"
    name = "No Draw"
    power_type = PowerType.DEBUFF

    def should_draw(self, player: Creature, from_hand_draw: bool = False) -> bool:
        if from_hand_draw or player is not self.owner:
            return True
        return False

    def after_player_turn_end(self, player: Creature) -> None:
        if player is self.owner:
            self._expire()


class NoEnergyGainPower(Power):
    """Mid-turn energy gains are reduced to 0 (turn-start energy is unaffected).
    Removed at the end of the owner's turn. StackType.Single only hides the
    Amount display; Amount still accumulates on re-application, but nothing
    reads it here."""

    id = "no_energy_gain"
    name = "No Energy Gain"
    power_type = PowerType.DEBUFF

    def modify_energy_gain(self, player: Creature, amount: int) -> int:
        if player is self.owner:
            return 0
        return amount

    def after_player_turn_end(self, player: Creature) -> None:
        if player is self.owner:
            self._expire()


class ColossusPower(Power):
    """Powered attacks from Vulnerable dealers deal half damage to the owner.
    Ticks at the end of the enemy's turn."""

    id = "colossus"
    name = "Colossus"
    power_type = PowerType.BUFF

    def modify_damage_multiplicative(
        self,
        target: Creature,
        amount: int,
        dealer: Creature | None,
        card: Card | None,
        props: ValueProp = ValueProp.NONE,
    ) -> float:
        if not is_powered_attack(props):   # ColossusPower.cs
            return 1.0
        if target is self.owner and dealer is not None and "vulnerable" in dealer.powers:
            return 0.5
        return 1.0

    def on_enemy_side_end(self) -> None:
        self._tick()


class CorruptionPower(Power):
    """Skill cards cost 0 and are exhausted when played. StackType.Single only
    hides the Amount display; Amount still accumulates on re-application, but
    nothing reads it here."""

    id = "corruption"
    name = "Corruption"
    power_type = PowerType.BUFF

    def modify_card_energy_cost_late(self, card: Card, cost: int) -> int:
        # CorruptionPower.cs:16 is TryModifyEnergyCostInCombatLate: the Late
        # pass runs after every plain modifier, so the Skill ends at 0
        # whatever raised its cost first.
        from .cards import CardType
        if card.card_type == CardType.SKILL:
            return 0
        return cost

    def on_card_played(self, card: Card,
                       is_auto_play: bool = False) -> None:
        # ModifyCardPlayResultPileTypeAndPosition: played Skills go to the
        # exhaust pile instead of the discard pile.
        from .cards import CardType
        if card.card_type != CardType.SKILL:
            return
        player = self.owner
        if card in player.discard_pile:
            player.discard_pile.remove(card)
            player.exhaust_pile.append(card)
            self.hooks.on_card_exhausted(card)


class CrimsonMantlePower(Power):
    """At the start of the owner's turn: lose 1 HP per Crimson Mantle card
    played this combat, then gain N block. The HP loss counter starts at 0 and
    is incremented by each Crimson Mantle play (IncrementSelfDamage)."""

    id = "crimson_mantle"
    name = "Crimson Mantle"
    power_type = PowerType.BUFF

    def __init__(
        self,
        owner: Creature,
        amount: int,
        hooks: HookSystem,
        applier: Creature | None = None,
    ) -> None:
        super().__init__(owner, amount, hooks, applier)
        self.self_damage = 0

    def increment_self_damage(self) -> None:
        self.self_damage += 1

    def on_player_turn_started(self, player: Creature) -> None:
        if player is not self.owner:
            return
        from .cmds import BlockCmd, DamageCmd
        from .valueprops import DamageProps, ValueProp
        if self.self_damage > 0:
            DamageCmd.deal(
                self.hooks, self.owner, self.self_damage,
                dealer=self.owner, props=DamageProps.NON_CARD_HP_LOSS,
            )
        BlockCmd.apply(self.hooks, self.owner, self.amount, props=ValueProp.UNPOWERED)


class CrueltyPower(Power):
    """The owner's attacks against Vulnerable targets deal N% extra: the ×1.5
    Vulnerable multiplier becomes ×(1.5 + N/100). Passive — consulted by
    VulnerablePower.modify_damage_multiplicative (mirrors the game's
    ModifyVulnerableMultiplier plumbing)."""

    id = "cruelty"
    name = "Cruelty"
    power_type = PowerType.BUFF


class FlameBarrierPower(Power):
    """Deal N unpowered damage back to any creature whose powered attack hits
    the owner (even if fully blocked). Removed at the end of the enemy's
    turn."""

    id = "flame_barrier"
    name = "Flame Barrier"
    power_type = PowerType.BUFF

    def on_damage_received(
        self,
        target: Creature,
        amount: int,
        dealer: Creature | None,
        card: Card | None,
        props: ValueProp = ValueProp.NONE,
    ) -> None:
        from .valueprops import is_powered_attack
        if target is not self.owner or dealer is None or not is_powered_attack(props):
            return
        from .cmds import DamageCmd
        from .valueprops import DamageProps
        DamageCmd.deal(
            self.hooks, dealer, self.amount,
            dealer=self.owner, props=DamageProps.NON_CARD_UNPOWERED,
        )

    def on_enemy_side_end(self) -> None:
        self._expire()


class HellraiserPower(Power):
    """Whenever a Strike card is drawn, auto-play it (for free, at a random
    target). StackType.Single only hides the Amount display; Amount still
    accumulates on re-application, but nothing reads it here.

    The game caps consecutive auto-plays at 9 only against infinite-HP
    enemies, which the sim does not have."""

    id = "hellraiser"
    name = "Hellraiser"
    power_type = PowerType.BUFF

    def on_card_drawn_early(self, card: Card, from_hand_draw: bool = False) -> None:
        # HellraiserPower.cs:37 is AfterCardDrawnEarly -- the Early pass runs
        # complete before any plain AfterCardDrawn listener sees the draw.
        if "strike" not in card.tags:
            return
        combat = self.hooks.combat
        if combat is None or combat.is_over:
            return
        combat.auto_play_card(card)


class InfernoPower(Power):
    """At the start of the owner's turn: lose 1 HP per Inferno card played this
    combat (IncrementSelfDamage, starts at 0). Whenever the owner loses HP
    during their own turn, deal N unpowered damage to ALL enemies."""

    id = "inferno"
    name = "Inferno"
    power_type = PowerType.BUFF

    def __init__(
        self,
        owner: Creature,
        amount: int,
        hooks: HookSystem,
        applier: Creature | None = None,
    ) -> None:
        super().__init__(owner, amount, hooks, applier)
        self.self_damage = 0

    def increment_self_damage(self) -> None:
        self.self_damage += 1

    def on_player_turn_started(self, player: Creature) -> None:
        # InfernoPower.cs:26-35 fires `CreatureCmd.Damage(..., SelfDamage, ...)`
        # with NO `> 0` test, so a turn-1 Inferno still runs a 0-damage command
        # through the whole pipeline — modifiers, block, and the on-damage
        # hooks a listener could be watching. The sim short-circuited it.
        if player is self.owner:
            from .cmds import DamageCmd
            from .valueprops import DamageProps
            DamageCmd.deal(
                self.hooks, self.owner, self.self_damage,
                dealer=self.owner, props=DamageProps.NON_CARD_HP_LOSS,
            )

    def on_damage_received(
        self,
        target: Creature,
        amount: int,
        dealer: Creature | None,
        card: Card | None,
        props: ValueProp = ValueProp.NONE,
    ) -> None:
        if target is not self.owner or amount <= 0:
            return
        combat = self.hooks.combat
        if combat is None or combat.current_side != self.owner.side:
            return
        from .cmds import DamageCmd
        from .valueprops import DamageProps
        for enemy in list(combat.enemies):
            if not enemy.is_gone:
                DamageCmd.deal(
                    self.hooks, enemy, self.amount,
                    dealer=self.owner, props=DamageProps.NON_CARD_UNPOWERED,
                )


class JuggernautPower(Power):
    """Whenever the owner gains block (> 0), deal N unpowered damage to a
    random living enemy."""

    id = "juggernaut"
    name = "Juggernaut"
    power_type = PowerType.BUFF

    def on_block_gained(
        self, target: Creature, amount: int, card: Card | None = None
    ) -> None:
        if target is not self.owner or amount <= 0:
            return
        combat = self.hooks.combat
        if combat is None:
            return
        living = [e for e in combat.enemies if not e.is_gone]
        if not living:
            return
        from .cmds import DamageCmd
        from .valueprops import DamageProps
        # `RunState.Rng.CombatTargets.NextItem(hittableEnemies)`
        # (JuggernautPower.cs:24) — the named targets stream, not the shared
        # combat rng.
        DamageCmd.deal(
            self.hooks, combat.combat_rng.targets.choice(living), self.amount,
            dealer=self.owner, props=DamageProps.NON_CARD_UNPOWERED,
        )


class JugglingPower(Power):
    """When the owner plays their 3rd Attack in a turn, add N copies of it to
    the hand. Attacks played earlier in the turn count (the counter is seeded
    from combat history, mirroring the CombatHistory seed in AfterApplied)."""

    id = "juggling"
    name = "Juggling"
    power_type = PowerType.BUFF

    def __init__(
        self,
        owner: Creature,
        amount: int,
        hooks: HookSystem,
        applier: Creature | None = None,
    ) -> None:
        super().__init__(owner, amount, hooks, applier)
        combat = hooks.combat
        self._attacks_this_turn = (
            combat.history.attack_plays_this_turn() if combat is not None else 0
        )

    def on_card_played(self, card: Card,
                       is_auto_play: bool = False) -> None:
        from .cards import CardType
        if card.card_type != CardType.ATTACK:
            return
        self._attacks_this_turn += 1
        if self._attacks_this_turn == 3:
            from .cards.base import create_clone
            from .cmds import CardPileCmd
            for _ in range(self.amount):
                # CardModel.CreateClone -> DeepCloneFields re-attaches a live
                # copy of the source's enchantment AND affliction
                # (CardModel.cs:1204-1215); the hand-rolled rebuild carried
                # only the upgrade level, so a Juggling copy of an enchanted
                # Attack behaved as a different card for the rest of the
                # combat (enchantment/EG2, the fifth copy site).
                CardPileCmd.add_to_hand(self.hooks, self.owner,
                                        create_clone(card))

    def after_player_turn_end(self, player: Creature) -> None:
        if player is self.owner:
            self._attacks_this_turn = 0


class TemporaryStrengthPower(Power):
    """Base for powers that grant Strength immediately and revert it at the end
    of the owner's side turn (mirrors TemporaryStrengthPower). Subclasses set
    _sign = -1 for temporary Strength loss (Mangle)."""

    _sign = 1

    def __init__(
        self,
        owner: Creature,
        amount: int,
        hooks: HookSystem,
        applier: Creature | None = None,
    ) -> None:
        super().__init__(owner, amount, hooks, applier)
        from .cmds import PowerCmd
        PowerCmd.apply(hooks, owner, StrengthPower, self._sign * amount)

    def on_stack(self, amount: int) -> None:
        super().on_stack(amount)
        from .cmds import PowerCmd
        PowerCmd.apply(self.hooks, self.owner, StrengthPower, self._sign * amount)

    def _revert(self) -> None:
        if not self.owner.is_dead:
            from .cmds import PowerCmd
            PowerCmd.apply(self.hooks, self.owner, StrengthPower, -self._sign * self.amount)
        self._expire()

    def after_player_turn_end(self, player: Creature) -> None:
        # TemporaryStrengthPower.cs:173-181 overrides AfterSideTurnEnd, which
        # Hook.AfterTurnEnd dispatches (Hook.cs:1267-1292) — for the player
        # side at CombatManager.cs:1307, i.e. AFTER the turn-end card effects
        # and the hand flush, not in the BeforeTurnEnd pass. So the Strength is
        # still standing for everything those two steps do, and the revert can
        # never race a BeforeTurnEnd listener on registration order.
        if player is self.owner:
            self._revert()

    def on_enemy_side_end(self) -> None:
        if self.owner.side == "enemy":
            self._revert()


class SetupStrikePower(TemporaryStrengthPower):
    """Temporary Strength from Setup Strike: reverted at end of turn."""

    id = "setup_strike"
    name = "Setup Strike"
    power_type = PowerType.BUFF


class ManglePower(TemporaryStrengthPower):
    """Temporary Strength LOSS from Mangle: restored at the end of the owner's
    side turn."""

    id = "mangle"
    name = "Mangle"
    power_type = PowerType.DEBUFF
    _sign = -1


class ReptileTrinketPower(TemporaryStrengthPower):
    """Temporary Strength from Reptile Trinket (granted each time a potion is
    used): reverted at the end of the owner's side turn."""

    id = "reptile_trinket"
    name = "Reptile Trinket"
    power_type = PowerType.BUFF


class FlexPotionPower(TemporaryStrengthPower):
    """Temporary Strength from Flex Potion: reverted at the end of the owner's
    side turn. Source: FlexPotionPower.cs : TemporaryStrengthPower."""

    id = "flex_potion"
    name = "Flex Potion"
    power_type = PowerType.BUFF


class TemporaryDexterityPower(Power):
    """Base for powers that grant Dexterity immediately and revert it at the end
    of the owner's side turn (mirrors TemporaryDexterityPower). Subclasses set
    _sign = -1 for temporary Dexterity loss."""

    _sign = 1

    def __init__(
        self,
        owner: Creature,
        amount: int,
        hooks: HookSystem,
        applier: Creature | None = None,
    ) -> None:
        super().__init__(owner, amount, hooks, applier)
        from .cmds import PowerCmd
        PowerCmd.apply(hooks, owner, DexterityPower, self._sign * amount)

    def on_stack(self, amount: int) -> None:
        super().on_stack(amount)
        from .cmds import PowerCmd
        PowerCmd.apply(self.hooks, self.owner, DexterityPower, self._sign * amount)

    def _revert(self) -> None:
        if not self.owner.is_dead:
            from .cmds import PowerCmd
            PowerCmd.apply(self.hooks, self.owner, DexterityPower, -self._sign * self.amount)
        self._expire()

    def after_player_turn_end(self, player: Creature) -> None:
        # TemporaryDexterityPower.cs:169-177 — AfterSideTurnEnd, the same slot
        # its line-for-line Strength twin uses. See TemporaryStrengthPower.
        if player is self.owner:
            self._revert()

    def on_enemy_side_end(self) -> None:
        if self.owner.side == "enemy":
            self._revert()


class SpeedPotionPower(TemporaryDexterityPower):
    """Temporary Dexterity from Speed Potion: reverted at the end of the owner's
    side turn. Source: SpeedPotionPower.cs : TemporaryDexterityPower."""

    id = "speed_potion"
    name = "Speed Potion"
    power_type = PowerType.BUFF


class OneTwoPunchPower(Power):
    """The owner's next N Attacks this turn are played twice. Each affected
    play consumes one stack; removed at the end of the owner's turn."""

    id = "one_two_punch"
    name = "One-Two Punch"
    power_type = PowerType.BUFF

    def modify_card_play_count(
        self,
        card: Card,
        target: Creature | None,
        count: int,
    ) -> int:
        from .cards import CardType
        if card.card_type != CardType.ATTACK:
            return count
        # AfterModifyingCardPlayCount: each modified play consumes a stack.
        self._tick()
        return count + 1

    def after_player_turn_end(self, player: Creature) -> None:
        if player is self.owner:
            self._expire()


class PyrePower(Power):
    """The owner gains N extra energy at the start of each turn."""

    id = "pyre"
    name = "Pyre"
    power_type = PowerType.BUFF

    def modify_max_energy(self, player: Creature, amount: int) -> int:
        if player is self.owner:
            return amount + self.amount
        return amount


class RagePower(Power):
    """Gain N block (unpowered) whenever the owner plays an Attack. Removed at
    the end of the owner's turn."""

    id = "rage"
    name = "Rage"
    power_type = PowerType.BUFF

    def on_card_played(self, card: Card,
                       is_auto_play: bool = False) -> None:
        from .cards import CardType
        if card.card_type == CardType.ATTACK:
            from .cmds import BlockCmd
            from .valueprops import ValueProp
            BlockCmd.apply(self.hooks, self.owner, self.amount, props=ValueProp.UNPOWERED)

    def after_player_turn_end(self, player: Creature) -> None:
        if player is self.owner:
            self._expire()


class StampedePower(Power):
    """When the owner ends their turn, auto-play N random playable Attacks
    from the hand (before turn-end card effects and the hand discard)."""

    id = "stampede"
    name = "Stampede"
    power_type = PowerType.BUFF

    def after_auto_post_play_phase_entered(self, player: Creature) -> None:
        # StampedePower.cs is AfterAutoPostPlayPhaseEntered, not BeforeTurnEnd.
        if player is not self.owner:
            return
        combat = self.hooks.combat
        if combat is None:
            return
        from .cards import CardType
        for _ in range(self.amount):
            if combat.is_over:
                break
            candidates = [
                c for c in player.hand
                if c.card_type == CardType.ATTACK and c.is_playable
            ]
            if not candidates:
                continue
            # StampedePower.cs:28 picks on Rng.Shuffle
            # (`RunState.Rng.Shuffle.NextItem(items)`), not on the legacy
            # shared rng. Latent until the dispatch-order fix (hook_dispatch
            # G2) made Stampede's auto-plays run first and reliably, which is
            # what test_rng_tripwire caught.
            combat.auto_play_card(combat.combat_rng.shuffle.choice(candidates))


class PlatingPower(Power):
    """Gain N block at the end of the owner's turn (before turn-end card
    effects); lose 1 stack at the start of the owner's turn (except on the
    first turn of combat). Enemies that start combat with Plating also start
    with the block (mirrors PlatingPower.BeforeSideTurnStart on round 1)."""

    id = "plating"
    name = "Plating"
    power_type = PowerType.BUFF

    def before_side_turn_start(self, player: Creature) -> None:
        """PlatingPower.cs:41-56 — the round-1 arm of a turn-start hook used as
        a stand-in for combat start ("We want enemies that start with Plating to
        also start combat with block"). It fires on the PLAYER's side turn
        start, for a non-player owner, while RoundNumber <= 1. The sim used
        `on_combat_start`, which is one dispatch earlier: any combat-start
        listener registered after this power saw the enemy already blocked.
        """
        combat = self.hooks.combat
        if self.owner.side == "enemy" and (combat is None or combat.turn <= 1):
            self._gain_block()

    def _gain_block(self) -> None:
        from .cmds import BlockCmd
        from .valueprops import ValueProp
        BlockCmd.apply(self.hooks, self.owner, self.amount, props=ValueProp.UNPOWERED)

    def _decay(self) -> None:
        combat = self.hooks.combat
        if combat is not None and combat.turn > 1:
            self._tick()

    def on_player_turn_end_early(self, player: Creature) -> None:
        # PlatingPower.cs:61 is BeforeSideTurnEndEARLY, not the plain pass:
        # "We do this in early so that it triggers before end-of-turn damage
        # effects." The sim ran it plain on both sides, which put it after any
        # _very_early or _early listener that reads the owner's block.
        if player is self.owner:
            self._gain_block()

    def after_side_turn_start(self, player: Creature) -> None:
        # PlatingPower.cs:70 — AfterSideTurnStart, and `participants.Contains
        # (Owner)` is what the `player is self.owner` test reproduces: an
        # enemy-owned Plating decays on the ENEMY side's pass instead
        # (after_enemy_side_start below).
        if player is self.owner:
            self._decay()

    def before_enemy_side_end_early(self) -> None:
        # PlatingPower.cs:61, the enemy leg. AsleepPower's _very_early pass
        # removes this power first on the last sleeping turn, so the sleeper
        # gains no block on the turn it wakes.
        if self.owner.side == "enemy" and not self.owner.is_dead:
            self._gain_block()

    def after_enemy_side_start(self) -> None:
        if self.owner.side == "enemy":
            self._decay()


class UnmovablePower(Power):
    """The first N card plays that gain the owner block each turn grant double
    block (unpowered block like Plating/Rage is unaffected — the sim only
    consults block multipliers for powered card/move block)."""

    id = "unmovable"
    name = "Unmovable"
    power_type = PowerType.BUFF

    def __init__(
        self,
        owner: Creature,
        amount: int,
        hooks: HookSystem,
        applier: Creature | None = None,
    ) -> None:
        super().__init__(owner, amount, hooks, applier)
        self._plays_used = 0
        self._active_card: Card | None = None

    def modify_block_multiplicative(
        self,
        target: Creature,
        amount: int,
        card: Card | None,
        props: ValueProp = ValueProp.NONE,
    ) -> float:
        if not is_card_or_monster_move(props):   # UnmovablePower.cs:27
            return 1.0
        if target is not self.owner or card is None:
            return 1.0
        if card is self._active_card:
            # Multiple block gains within one card play all double (the game
            # counts BlockGainedEntries per card play, not per gain).
            return 2.0
        if self._plays_used < self.amount:
            self._active_card = card
            return 2.0
        return 1.0

    def on_card_played(self, card: Card,
                       is_auto_play: bool = False) -> None:
        if card is self._active_card:
            self._plays_used += 1
            self._active_card = None

    def before_side_turn_start(self, player: Creature) -> None:
        if player is self.owner:
            self._plays_used = 0
            self._active_card = None


class FreeAttackPower(Power):
    """The owner's next N Attack cards cost 0. Playing any Attack consumes a
    stack; persists across turns.

    The stack is consumed in `before_card_played`, which is
    `Hook.BeforeCardPlayed` — the hook FreeAttackPower.cs:43 actually declares —
    and which the sim dispatches INSIDE the play-count loop (CardModel.cs:1929),
    once per `CardPlay`. The port used to hang it on `on_energy_spent`, which
    combat.py fires ONCE per logical play, outside `_resolve_card_play`: a
    Throwing-Axe- or Duplication-doubled Attack consumed two stacks in the game
    and one in the sim.

    Both of this power's hooks carry the same pile guard —
    `card.Pile?.Type is Hand or Play` (FreeAttackPower.cs:26-39, :48-59)."""

    id = "free_attack"
    name = "Free Attack"
    power_type = PowerType.BUFF

    # FreeAttackPower.cs:26-39 / :48-59 — the switch both hooks run.
    _LIVE_PILES = ("hand", "play")

    def _in_a_live_pile(self, card: Card) -> bool:
        combat = self.hooks.combat
        if combat is None:
            return True
        return combat.player.pile_type_of(card) in self._LIVE_PILES

    def modify_card_energy_cost_late(self, card: Card, cost: int) -> int:
        # FreeAttackPower.cs:14 is TryModifyEnergyCostInCombatLate: the Late
        # pass runs after Tangled's plain one, so the Attack is free
        # regardless of which power was applied first.
        #
        # The pile guard is load-bearing HERE, unlike on BeforeCardPlayed: the
        # cost hook is queried for cards in every pile (previews.py, the RL
        # observation, CardModel.CostsEnergyOrStars filters), and without it a
        # draw- or discard-pile Attack reads as free.
        from .cards import CardType
        if card.card_type == CardType.ATTACK and self._in_a_live_pile(card):
            return 0
        return cost

    def before_card_played(self, card: Card, target=None) -> None:
        from .cards import CardType
        if card.card_type == CardType.ATTACK and self._in_a_live_pile(card):
            self._tick()


class ViciousPower(Power):
    """Draw N cards whenever the owner applies Vulnerable."""

    id = "vicious"
    name = "Vicious"
    power_type = PowerType.BUFF

    def _maybe_draw(self, name: str, delta: int, applier: Creature | None) -> None:
        if name != "vulnerable" or delta <= 0 or applier is not self.owner:
            return
        from .cmds import DrawCmd
        DrawCmd.draw(self.owner, self.amount)

    def on_power_applied(
        self,
        name: str,
        target: Creature,
        amount: int,
        applier: Creature | None = None,
    ) -> None:
        self._maybe_draw(name, amount, applier)

    def on_power_amount_changed(
        self,
        name: str,
        target: Creature,
        delta: int,
        applier: Creature | None = None,
    ) -> None:
        self._maybe_draw(name, delta, applier)


class ToricToughnessPower(Power):
    """For the next N turns, gain the stored block after block is cleared at
    turn start. amount tracks turns left; the block value is set separately.

    Source: ToricToughnessPower.cs — AfterBlockCleared: GainBlock(Block,
    Unpowered), then Decrement. The game makes each application a separate
    instance (PowerInstanceType.Instanced, power_cmd/G5): re-applying now
    starts its own instance with its own turn counter and block value,
    rather than stacking the counter and overwriting the block on this one.
    """

    id = "toric_toughness"
    name = "Toric Toughness"
    power_type = PowerType.BUFF
    instance_type = PowerInstanceType.INSTANCED

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.block = 0

    def set_block(self, block: int) -> None:
        """Mirrors ToricToughnessPower.SetBlock (Amount is the turn counter)."""
        self.block = block

    def on_block_cleared(self, target: Creature) -> None:
        if target is not self.owner:
            return
        from .cmds import BlockCmd
        BlockCmd.apply(self.hooks, self.owner, self.block, props=ValueProp.UNPOWERED)
        self._tick()


# ── Overgrowth enemy powers ───────────────────────────────────────────────


class SlowPower(Power):
    """Owner takes +10% damage from powered attacks per card played this turn.

    The counter resets when the owner's side starts its turn (so it builds up
    over the player's whole turn), mirroring STS2's SlowPower DynamicVar.
    """

    id = "slow"
    name = "Slow"
    power_type = PowerType.DEBUFF

    def __init__(
        self,
        owner: Creature,
        amount: int,
        hooks: HookSystem,
        applier: Creature | None = None,
    ) -> None:
        super().__init__(owner, amount, hooks, applier)
        self._cards_this_turn = 0

    def on_card_played(self, card: Card,
                       is_auto_play: bool = False) -> None:
        self._cards_this_turn += 1

    def after_enemy_side_start(self) -> None:
        # SlowPower.cs:52 — AfterSideTurnStart, once for the side.
        if self.owner.side == "enemy":
            self._cards_this_turn = 0

    def modify_damage_multiplicative(
        self,
        target: Creature,
        amount: int,
        dealer: Creature | None,
        card: Card | None,
        props: ValueProp = ValueProp.NONE,
    ) -> float:
        if not is_powered_attack(props):   # SlowPower.cs
            return 1.0
        if target is self.owner and card is not None and not card.is_unpowered:
            return 1.0 + 0.1 * self._cards_this_turn
        return 1.0


class TerritorialPower(Power):
    """Owner gains N Strength at the end of its side's turn."""

    id = "territorial"
    name = "Territorial"
    power_type = PowerType.BUFF

    def on_enemy_side_end(self) -> None:
        if not self.owner.is_dead:
            from .cmds import PowerCmd
            PowerCmd.apply(self.hooks, self.owner, StrengthPower, self.amount)


class PlowPower(Power):
    """Ceremonial Beast's charge counter.

    When unblocked damage leaves the owner at or below N HP, the owner loses
    all Strength, is stunned (on_plow_broken), and this power is removed.
    """

    id = "plow"
    name = "Plow"
    power_type = PowerType.DEBUFF

    def on_damage_received(
        self,
        target: Creature,
        amount: int,
        dealer: Creature | None,
        card: Card | None,
        props: ValueProp = ValueProp.NONE,
    ) -> None:
        if target is not self.owner or amount <= 0 or self.owner.is_dead:
            return
        if self.owner.hp > self.amount:
            return
        from .cmds import PowerCmd
        PowerCmd.remove(self.hooks, self.owner, "strength")
        on_broken = getattr(self.owner, "on_plow_broken", None)
        if on_broken is not None:
            on_broken()
        self._expire()


class RingingPower(Power):
    """Afflicts every unafflicted card the player owns with Ringing: once any
    card has been played this turn, Ringing-afflicted cards cannot be played.
    Cards created mid-combat are afflicted too. Removed (clearing all Ringing
    afflictions) at the end of the owner's (player's) turn."""

    id = "ringing"
    name = "Ringing"
    power_type = PowerType.DEBUFF

    def __init__(
        self,
        owner: Creature,
        amount: int,
        hooks: HookSystem,
        applier: Creature | None = None,
    ) -> None:
        super().__init__(owner, amount, hooks, applier)
        self._card_played_this_turn = False
        from .afflictions import RingingAffliction
        from .cmds import CardCmd
        for card in getattr(owner, "all_cards", ()):
            if card.affliction is None:
                CardCmd.afflict(card, RingingAffliction, 1)

    def on_card_entered_combat(self, card: Card) -> None:
        if card.affliction is None:
            from .afflictions import RingingAffliction
            from .cmds import CardCmd
            CardCmd.afflict(card, RingingAffliction, 1)

    def should_play_card(self, card: Card, auto_play: bool = False) -> bool:
        from .afflictions import RingingAffliction
        if isinstance(card.affliction, RingingAffliction):
            return not self._card_played_this_turn
        return True

    def on_card_played(self, card: Card,
                       is_auto_play: bool = False) -> None:
        self._card_played_this_turn = True

    def before_side_turn_start(self, player: Creature) -> None:
        if player is self.owner:
            self._card_played_this_turn = False

    def after_player_turn_end(self, player: Creature) -> None:
        if player is self.owner:
            self._expire()

    def _expire(self) -> None:
        from .afflictions import RingingAffliction
        from .cmds import CardCmd
        for card in getattr(self.owner, "all_cards", ()):
            if isinstance(card.affliction, RingingAffliction):
                CardCmd.clear_affliction(card)
        super()._expire()


class ShrinkPower(Power):
    """Owner deals 30% less damage with powered attacks.

    A negative amount means infinite duration (Shrinker Beetle applies -1);
    positive amounts tick down at the end of the owner's side turn.
    Removed if the applier dies.
    """

    id = "shrink"
    name = "Shrink"
    power_type = PowerType.DEBUFF

    def modify_damage_multiplicative(
        self,
        target: Creature,
        amount: int,
        dealer: Creature | None,
        card: Card | None,
        props: ValueProp = ValueProp.NONE,
    ) -> float:
        if not is_powered_attack(props):   # ShrinkPower.cs
            return 1.0
        if dealer is self.owner and card is not None and not card.is_unpowered:
            return 0.7
        return 1.0

    def after_player_turn_end(self, player: Creature) -> None:
        if player is self.owner and self.amount > 0:
            self._tick()

    def on_enemy_side_end(self) -> None:
        if self.owner.side == "enemy" and self.amount > 0:
            self._tick()

    def on_death(self, creature: Creature,
                 was_removal_prevented: bool = False) -> None:
        if creature is self.applier:
            self._expire()


class InfestedPower(Power):
    """When the owner dies, 4 stunned Wrigglers join the fight."""

    id = "infested"
    name = "Infested"
    power_type = PowerType.BUFF

    def should_stop_combat_from_ending(self) -> bool:
        return True   # InfestedPower.cs:37-40

    def on_death(self, creature: Creature,
                 was_removal_prevented: bool = False) -> None:
        if creature is not self.owner:
            return
        combat = self.hooks.combat
        if combat is None:
            return
        from .cmds import CreatureCmd
        from .monsters.overgrowth.phrog_parasite import Wriggler
        for i in range(4):
            CreatureCmd.add(
                self.hooks,
                Wriggler(self.hooks, combat._rng, start_stunned=True, slot=i + 1),
            )
        self._expire()


class ConstrictPower(Power):
    """Owner takes N damage at the end of its side's turn. Removed if the
    applier dies."""

    id = "constrict"
    name = "Constrict"
    power_type = PowerType.DEBUFF

    def _squeeze(self) -> None:
        from .cmds import DamageCmd
        from .valueprops import DamageProps
        # Blockable, unpowered damage from a power (like Thorns). ConstrictPower
        # .cs:23's 5th argument is `base.Owner` — the squeeze is dealt BY the
        # creature it hurts, so `on_damage_dealt` (Hook.AfterDamageGiven) fires.
        # The port left the dealer None; same omission as ThornsPower's, closed
        # together under binding rule 3.
        DamageCmd.deal(
            self.hooks, self.owner, self.amount,
            dealer=self.owner, props=DamageProps.NON_CARD_UNPOWERED,
        )

    def after_player_turn_end(self, player: Creature) -> None:
        if player is self.owner:
            self._squeeze()

    def on_enemy_side_end(self) -> None:
        # ConstrictPower.cs:21 is `participants.Contains(base.Owner)` and
        # nothing else — no is_dead test. The port added one, which now
        # matters: a PREVENTED death leaves the creature dead at 0 HP and
        # retained in the combat (cmds.py `_resolve_death`) rather than floored
        # at 1, so an added `is_dead` guard silently stops squeezing a creature
        # the game still squeezes. `_side_participants` is the sim's
        # `participants` list and already excludes creatures that left.
        if self.owner.side == "enemy":
            combat = self.hooks.combat
            if combat is None or self.owner in combat._side_participants():
                self._squeeze()

    def on_death(self, creature: Creature,
                 was_removal_prevented: bool = False) -> None:
        # ConstrictPower.cs:29 — `!wasRemovalPrevented && creature ==
        # base.Applier`. The port ignored the flag it is handed, so a PREVENTED
        # death of the applier dropped the power in the sim and keeps it in the
        # game.
        if not was_removal_prevented and creature is self.applier:
            self._expire()


class TangledPower(Power):
    """Afflicts the player's Attack cards with Entangled: they cost N more
    energy while afflicted. Attack cards created mid-combat are afflicted too.
    Removed (clearing all Entangled afflictions) at the end of the owner's
    (player's) turn."""

    id = "tangled"
    name = "Tangled"
    power_type = PowerType.DEBUFF

    def __init__(
        self,
        owner: Creature,
        amount: int,
        hooks: HookSystem,
        applier: Creature | None = None,
    ) -> None:
        super().__init__(owner, amount, hooks, applier)
        from .cards import CardType
        from .afflictions import EntangledAffliction
        from .cmds import CardCmd
        for card in getattr(owner, "all_cards", ()):
            if card.affliction is None and card.card_type == CardType.ATTACK:
                CardCmd.afflict(card, EntangledAffliction, 1)

    def on_card_entered_combat(self, card: Card) -> None:
        from .cards import CardType
        if card.affliction is None and card.card_type == CardType.ATTACK:
            from .afflictions import EntangledAffliction
            from .cmds import CardCmd
            CardCmd.afflict(card, EntangledAffliction, 1)

    def modify_card_energy_cost(self, card: Card, cost: int) -> int:
        from .afflictions import EntangledAffliction
        if isinstance(card.affliction, EntangledAffliction):
            return cost + self.amount
        return cost

    def after_player_turn_end(self, player: Creature) -> None:
        if player is self.owner:
            self._expire()

    def _expire(self) -> None:
        from .afflictions import EntangledAffliction
        from .cmds import CardCmd
        for card in getattr(self.owner, "all_cards", ()):
            if isinstance(card.affliction, EntangledAffliction):
                CardCmd.clear_affliction(card)
        super()._expire()


class SlipperyPower(Power):
    """Each stack caps one hit's HP loss at 1, then is consumed. Fully blocked
    hits do not consume a stack."""

    id = "slippery"
    name = "Slippery"
    power_type = PowerType.BUFF

    def modify_hp_lost(
        self,
        target: Creature,
        amount: int,
        dealer: Creature | None,
        card: Card | None,
    ) -> int:
        if target is self.owner and amount >= 1:
            return 1
        return amount

    def on_damage_received(
        self,
        target: Creature,
        amount: int,
        dealer: Creature | None,
        card: Card | None,
        props: ValueProp = ValueProp.NONE,
    ) -> None:
        if target is self.owner and amount >= 1:
            self._tick()


class MinionPower(Power):
    """Marks the owner as a secondary enemy: its survival does not keep combat
    going once every primary enemy is dead (checked in CombatState)."""

    id = "minion"
    name = "Minion"
    power_type = PowerType.BUFF

    def should_power_be_removed_after_owner_death(self) -> bool:
        return False   # MinionPower.cs:15-18

    def should_owner_death_trigger_fatal(self) -> bool:
        # MinionPower.cs:20-23 — unconditional. Killing a minion never pays a
        # Fatal bonus, which is what stops Feed and Hand of Greed farming the
        # Fabricator's bots, the Queen's minions and the Ovicopter's eggs.
        return False


class IllusionPower(Power):
    """The owner cannot truly die: lethal damage leaves it at 1 HP, untargetable,
    and it spends its next turn reviving to full HP. Also marks it as a minion."""

    id = "illusion"
    name = "Illusion"
    power_type = PowerType.BUFF

    def should_power_be_removed_on_death(self, power) -> bool:
        """IllusionPower.cs:59-66 — the source's ONLY implementer of
        Hook.ShouldPowerBeRemovedOnDeath. An Illusion keeps its buffs
        (including this power), and keeps a debuff only if it is not an
        ITemporaryPower."""
        if power.owner is not self.owner:
            return True
        if power.power_type == PowerType.DEBUFF:
            return not getattr(power, 'is_temporary', False)
        return False

    def __init__(
        self,
        owner: Creature,
        amount: int,
        hooks: HookSystem,
        applier: Creature | None = None,
    ) -> None:
        super().__init__(owner, amount, hooks, applier)
        self.is_reviving = False
        if "minion" not in owner.powers:
            from .cmds import PowerCmd
            PowerCmd.apply(hooks, owner, MinionPower, 1)

    def should_remove_from_combat_after_death(self, creature: Creature) -> bool:
        # IllusionPower.cs:108-116. This is the ONLY death-side predicate the
        # power implements — it has no ShouldDie override at all, so the death
        # is REAL and only the removal is refused. The sim used to answer
        # `should_die` False, which took the prevented branch instead: the
        # corpse never fired AfterDeath with wasRemovalPrevented=false, so
        # Gremlin Horn (GremlinHorn.cs:24-32, no such guard) never paid out.
        return creature is not self.owner

    def on_death(self, creature: Creature,
                 was_removal_prevented: bool = False) -> None:
        # IllusionPower.cs:76-90 — the revive is armed from AfterDeath, on the
        # `!wasRemovalPrevented` arm and for the owner only.
        if was_removal_prevented or creature is not self.owner:
            return
        self.is_reviving = True

    def should_allow_hitting(self, target: Creature) -> bool:
        if target is self.owner and self.is_reviving:
            return False
        return True

    def revive(self) -> None:
        """Called by the owner's take_turn to perform the REVIVE move."""
        self.is_reviving = False
        from .cmds import CreatureCmd
        CreatureCmd.heal(self.hooks, self.owner, self.owner.max_hp - self.owner.hp)


class RavenousPower(Power):
    """When another creature on the owner's side dies, the owner spends its
    next turn devouring the corpse (stunned) and gains N Strength
    (Corpse Slug; mirrors RavenousPower.AfterDeath)."""

    id = "ravenous"
    name = "Ravenous"
    power_type = PowerType.BUFF

    def on_death(self, creature: Creature,
                 was_removal_prevented: bool = False) -> None:
        if (
            creature is self.owner
            or creature.side != self.owner.side
            or self.owner.is_dead
        ):
            return
        from .cmds import CreatureCmd, PowerCmd
        CreatureCmd.stun(self.hooks, self.owner)
        PowerCmd.apply(self.hooks, self.owner, StrengthPower, self.amount)


class SuckPower(Power):
    """Gain N Strength each time one of the owner's powered attack hits deals
    unblocked damage to the other side (Fossil Stalker; mirrors
    SuckPower.AfterAttack's per-hit UnblockedDamage check)."""

    id = "suck"
    name = "Suck"
    power_type = PowerType.BUFF

    def after_attack(self, dealer: Creature, card: Card | None = None,
                     results: list | None = None) -> None:
        # SuckPower.cs:22-46 is AfterAttack over the whole AttackCommand, not
        # AfterDamageReceived: it counts the HITS that dealt unblocked damage
        # and applies Amount * that count ONCE. Hanging it on the victim's
        # AfterDamageReceived also meant the killing-blow guard
        # (CreatureCmd.cs:392) silently skipped the last hit of a lethal attack.
        if dealer is not self.owner or not results:
            return
        hits = sum(1 for receiver, unblocked in results
                   if receiver.side != self.owner.side and unblocked > 0)
        if hits > 0:
            from .cmds import PowerCmd
            PowerCmd.apply(self.hooks, self.owner, StrengthPower,
                           self.amount * hits)


class ThieveryPower(Power):
    """The Gremlin Merc's gold theft (mirrors ThieveryPower.cs): after each
    of his attacks he calls steal(), taking min(amount, the player's gold)
    (PlayerCmd.LoseGold with GoldLossType.Stolen) and accumulating the total
    on the power. The combat tracks the debit (CombatState.gold_stolen);
    RunState.finish_combat settles the run's ledger. SurprisePower moves the
    accumulated total onto the Fat Gremlin's HeistPower when the Merc dies.

    InstanceType.Instanced (ThieveryPower.cs:17, power_cmd/G5): a second
    application would start its own instance with its own gold_stolen
    total. The only applier (GremlinMerc.AfterAddedToRoom) applies it once
    per Merc, so this never observably matters today."""

    id = "thievery"
    name = "Thievery"
    power_type = PowerType.BUFF
    instance_type = PowerInstanceType.INSTANCED

    def __init__(
        self,
        owner: Creature,
        amount: int,
        hooks: HookSystem,
        applier: Creature | None = None,
    ) -> None:
        super().__init__(owner, amount, hooks, applier)
        self.gold_stolen = 0

    def steal(self) -> None:
        """ThieveryPower.cs Steal(): no-op if the target is dead or broke."""
        combat = self.hooks.combat
        if combat is None or combat.player.is_dead:
            return
        available = combat.player_gold + combat.gold_gained - combat.gold_stolen
        amount = min(self.amount, available)
        if amount <= 0:
            return
        combat.gold_stolen += amount
        self.gold_stolen += amount


class HeistPower(Power):
    """Held by the Fat Gremlin that flees with the Merc's stolen gold
    (mirrors HeistPower.cs): when the owner dies, the stolen amount is queued
    as a reward-screen gold return (GoldReward with wasGoldStolenBack).
    Escape never fires BeforeDeath — the gold stays lost.

    InstanceType.Instanced (HeistPower.cs:15, power_cmd/G5): a second
    application would start its own instance with its own amount. The only
    applier (SurprisePower) applies it once per Fat Gremlin, so this never
    observably matters today."""

    id = "heist"
    name = "Heist"
    power_type = PowerType.BUFF
    instance_type = PowerInstanceType.INSTANCED

    def on_death(self, creature: Creature,
                 was_removal_prevented: bool = False) -> None:
        if creature is not self.owner or self.amount <= 0:
            return
        combat = self.hooks.combat
        if combat is None:
            return
        from .rewards import RewardExtra
        combat.pending_reward_extras.append(RewardExtra.of_gold(self.amount))


class SurprisePower(Power):
    """When the owner dies, a Sneaky Gremlin and a Fat Gremlin jump out of the
    crate and join the fight (Gremlin Merc; mirrors SurprisePower.AfterDeath
    + ShouldStopCombatFromEnding), and the Merc's ThieveryPower total moves
    onto the Fat Gremlin as a HeistPower — kill it before it flees to get the
    stolen gold back."""

    id = "surprise"
    name = "Surprise"
    power_type = PowerType.BUFF

    def should_stop_combat_from_ending(self) -> bool:
        """SurprisePower.cs:40-43 — an unconditional `return true`, the same
        shape as Adaptable/Infested/SteamEruption/Stock's overrides
        (creature_card_cmds/step8c, tier-2 Task 26). The sim had not ported
        it. Dormant in Ironclad scope: the two gremlins this power's own
        `on_death` spawns are appended to `combat.enemies` (CreatureCmd.add)
        before either of their constructors or the later HeistPower.apply
        call could read `is_ending`, and neither gremlin is a minion, so
        `_all_enemies_dead`'s primaries check already goes False on its own
        as soon as the first one joins — the veto never gets a chance to
        matter for this power's own encounter, unlike Stock's (which
        constructs its replacement's own power BEFORE adding it to combat)."""
        return True

    def on_death(self, creature: Creature,
                 was_removal_prevented: bool = False) -> None:
        if creature is not self.owner:
            return
        from .cmds import CreatureCmd, PowerCmd
        from .monsters.underdocks.gremlin_merc import FatGremlin, SneakyGremlin
        rng = self.hooks.combat._rng
        CreatureCmd.add(self.hooks, SneakyGremlin(self.hooks, rng))
        fat = FatGremlin(self.hooks, rng)
        CreatureCmd.add(self.hooks, fat)
        thievery = self.owner.powers.get("thievery")
        if thievery is not None and thievery.gold_stolen > 0:
            PowerCmd.apply(self.hooks, fat, HeistPower, thievery.gold_stolen)


class SmoggyPower(Power):
    """Once the player plays a Skill, every other unafflicted Skill they own is
    afflicted with Smog and cannot be played for the rest of the turn; Smog
    clears at the end of the player's turn (Living Fog; mirrors SmoggyPower)."""

    id = "smoggy"
    name = "Smoggy"
    power_type = PowerType.DEBUFF

    def __init__(
        self,
        owner: Creature,
        amount: int,
        hooks: HookSystem,
        applier: Creature | None = None,
    ) -> None:
        super().__init__(owner, amount, hooks, applier)
        self._skill_played_this_turn = False

    @staticmethod
    def _is_skill(card: Card) -> bool:
        from .cards import CardType
        return card.card_type == CardType.SKILL

    def _afflict(self, card: Card) -> None:
        from .afflictions import SmogAffliction
        from .cmds import CardCmd
        CardCmd.afflict(card, SmogAffliction, 1)

    def on_card_played(self, card: Card,
                       is_auto_play: bool = False) -> None:
        if not self._is_skill(card):
            return
        self._skill_played_this_turn = True
        for c in getattr(self.owner, "all_cards", ()):
            if self._is_skill(c) and c.affliction is None:
                self._afflict(c)

    def on_card_entered_combat(self, card: Card) -> None:
        if (
            self._is_skill(card)
            and card.affliction is None
            and self._skill_played_this_turn
        ):
            self._afflict(card)

    def should_play_card(self, card: Card, auto_play: bool = False) -> bool:
        from .afflictions import SmogAffliction
        return not isinstance(card.affliction, SmogAffliction)

    def before_side_turn_start(self, player: Creature) -> None:
        if player is self.owner:
            self._skill_played_this_turn = False

    def after_player_turn_end(self, player: Creature) -> None:
        if player is not self.owner:
            return
        from .afflictions import SmogAffliction
        from .cmds import CardCmd
        for c in getattr(self.owner, "all_cards", ()):
            if isinstance(c.affliction, SmogAffliction):
                CardCmd.clear_affliction(c)
        self._skill_played_this_turn = False


class SkittishPower(Power):
    """The first time each turn a card attack deals unblocked damage to the
    owner, the owner gains N block (Phantasmal Gardener; mirrors
    SkittishPower.AfterAttack — once per turn, unpowered block)."""

    id = "skittish"
    name = "Skittish"
    power_type = PowerType.BUFF

    def __init__(
        self,
        owner: Creature,
        amount: int,
        hooks: HookSystem,
        applier: Creature | None = None,
    ) -> None:
        super().__init__(owner, amount, hooks, applier)
        self._blocked_this_turn = False

    def on_damage_received(
        self,
        target: Creature,
        amount: int,
        dealer: Creature | None,
        card: Card | None,
        props: ValueProp = ValueProp.NONE,
    ) -> None:
        if (
            target is self.owner
            and not self._blocked_this_turn
            and card is not None
            and ValueProp.MOVE in props
            and amount > 0
            and not self.owner.is_dead
        ):
            self._blocked_this_turn = True
            from .cmds import BlockCmd
            BlockCmd.apply(
                self.hooks, self.owner, self.amount, props=ValueProp.UNPOWERED
            )

    def after_player_turn_end(self, player: Creature) -> None:
        # End of the opposing (player) side's turn resets the once-per-turn gate.
        self._blocked_this_turn = False


class AsleepPower(Power):
    """The owner sleeps for N of its turns, then wakes; taking unblocked damage
    wakes it immediately (removing its Plating) and it spends the next turn
    waking up (Lagavulin Matriarch; mirrors AsleepPower). Plating is removed
    before the final sleeping turn's block gain, so a natural wake also comes
    up without block. The owner must implement wake_up(stunned=...)."""

    id = "asleep"
    name = "Asleep"
    power_type = PowerType.BUFF

    def _remove_plating(self) -> None:
        from .cmds import PowerCmd
        PowerCmd.remove(self.hooks, self.owner, "plating")

    def on_damage_received(
        self,
        target: Creature,
        amount: int,
        dealer: Creature | None,
        card: Card | None,
        props: ValueProp = ValueProp.NONE,
    ) -> None:
        if target is self.owner and amount > 0:
            self._remove_plating()
            self._expire()
            self.owner.wake_up(stunned=True)

    def before_enemy_side_end_very_early(self) -> None:
        # AsleepPower.cs:38 — BeforeSideTurnEndVeryEarly, so the Plating is
        # gone before PlatingPower's _early grant on the final sleeping turn.
        # The sim had this on the enemy turn START, one whole slot early.
        if self.owner.side == "enemy" and self.amount <= 1:
            self._remove_plating()

    def on_enemy_side_end(self) -> None:
        # AsleepPower.cs:46 — AfterSideTurnEnd.
        if self.owner.side != "enemy":
            return
        self.amount -= 1
        self.hooks.on_power_amount_changed(self.id, self.owner, -1)
        if self.amount <= 0:
            self._expire()
            self.owner.wake_up(stunned=False)


class VigorPower(Power):
    """The owner's next powered attack deals +N damage per hit; the stacks
    held when the attack started are consumed once it finishes (Terror Eel,
    Prep Time, Akabeko; mirrors VigorPower.BeforeAttack/ModifyDamageAdditive/
    AfterAttack).

    The attack boundary comes from Monster._execute_attack for monsters and
    from CombatState._resolve_card_play for player Attack-card plays."""

    id = "vigor"
    name = "Vigor"
    power_type = PowerType.BUFF

    def __init__(
        self,
        owner: Creature,
        amount: int,
        hooks: HookSystem,
        applier: Creature | None = None,
    ) -> None:
        super().__init__(owner, amount, hooks, applier)
        self._amount_when_attack_started: int | None = None

    def modify_damage_additive(
        self,
        target: Creature,
        amount: int,
        dealer: Creature | None,
        card: Card | None,
        props: ValueProp = ValueProp.NONE,
    ) -> int:
        if not is_powered_attack(props):   # VigorPower.cs
            return 0
        if dealer is self.owner:
            return self.amount
        return 0

    def before_attack(self, dealer: Creature, card: Card | None = None) -> None:
        if dealer is not self.owner or self._amount_when_attack_started is not None:
            return
        # Mirrors VigorPower.cs BeforeAttack's
        # `if (!command.DamageProps.IsPoweredAttack()) return;` — an unpowered
        # attack (card.is_unpowered) neither grants nor consumes Vigor. card
        # is None for monster attacks, which are always powered (DamageProps.
        # monsterMove == ValueProp.Move), so they fall through to tracking.
        if card is not None and card.is_unpowered:
            return
        self._amount_when_attack_started = self.amount

    def after_attack(self, dealer: Creature, card: Card | None = None,
                     results: list | None = None) -> None:
        if dealer is not self.owner or self._amount_when_attack_started is None:
            return
        consumed = self._amount_when_attack_started
        self._amount_when_attack_started = None
        self.amount -= consumed
        self.hooks.on_power_amount_changed(self.id, self.owner, -consumed)
        if self.amount <= 0:
            self._expire()


class ShriekPower(Power):
    """When unblocked damage leaves the owner at or below N HP, the owner is
    stunned and screams TERROR next (Terror Eel; mirrors
    ShriekPower.AfterDamageReceived). The owner must implement
    trigger_terror()."""

    id = "shriek"
    name = "Shriek"
    power_type = PowerType.DEBUFF
    allow_negative = True

    def on_damage_received(
        self,
        target: Creature,
        amount: int,
        dealer: Creature | None,
        card: Card | None,
        props: ValueProp = ValueProp.NONE,
    ) -> None:
        if (
            target is self.owner
            and amount > 0
            and not self.owner.is_gone
            and self.owner.hp <= self.amount
        ):
            self.owner.trigger_terror()
            self._expire()


class HardenedShellPower(Power):
    """The owner cannot lose more than N HP per side-turn (Skulking Colony;
    mirrors HardenedShellPower.ModifyHpLostBeforeOstyLate — the cap counts
    unblocked damage and resets at the start of each side's turn)."""

    id = "hardened_shell"
    name = "Hardened Shell"
    power_type = PowerType.BUFF

    def __init__(
        self,
        owner: Creature,
        amount: int,
        hooks: HookSystem,
        applier: Creature | None = None,
    ) -> None:
        super().__init__(owner, amount, hooks, applier)
        self._damage_received_this_turn = 0

    def modify_hp_lost(
        self,
        target: Creature,
        amount: int,
        dealer: Creature | None,
        card: Card | None,
    ) -> int:
        if target is not self.owner or amount == 0:
            return amount
        return min(amount, self.amount - self._damage_received_this_turn)

    def on_damage_received(
        self,
        target: Creature,
        amount: int,
        dealer: Creature | None,
        card: Card | None,
        props: ValueProp = ValueProp.NONE,
    ) -> None:
        if target is self.owner and amount > 0:
            self._damage_received_this_turn += amount

    def before_side_turn_start(self, player: Creature) -> None:
        self._damage_received_this_turn = 0

    def before_enemy_side_start(self) -> None:
        # HardenedShellPower.cs:71 — BeforeSideTurnStart with NO participants
        # or side filter, so the counter resets at the start of BOTH sides'
        # turns. The sim's enemy leg was owner-filtered, which the per-creature
        # slot forced on it.
        self._damage_received_this_turn = 0


class SteamEruptionPower(Power):
    """A killing blow flips the owner into its ABOUT_TO_BLOW → EXPLODE
    sequence instead of ending the fight (Waterfall Giant).

    The game LETS THE DEATH HAPPEN — SteamEruptionPower overrides no ShouldDie
    — and then keeps the corpse: `AfterDeath` with `!wasRemovalPrevented`
    triggers the state (SteamEruptionPower.cs:15-21),
    `ShouldCreatureBeRemovedFromCombatAfterDeath` returns false for its owner
    (:28-35), `ShouldStopCombatFromEnding` holds the combat open (:23-26) and
    `ShouldPowerBeRemovedAfterOwnerDeath` keeps the power itself (:37-40).
    The sim used to prevent the death from `should_die`, which is
    `power/_death_prevention_branch`: it left the giant at 1 HP instead of 0
    and, because a prevented death takes the other arm, `Hook.AfterDeath`
    never fired for it at all. The owner must implement
    trigger_about_to_blow()."""

    id = "steam_eruption"
    name = "Steam Eruption"
    power_type = PowerType.BUFF

    def should_power_be_removed_after_owner_death(self) -> bool:
        return False   # SteamEruptionPower.cs:37-40

    def should_stop_combat_from_ending(self) -> bool:
        return True    # SteamEruptionPower.cs:23-26

    def should_remove_from_combat_after_death(self, creature: Creature) -> bool:
        return creature is not self.owner   # SteamEruptionPower.cs:28-35

    def on_death(self, creature: Creature,
                 was_removal_prevented: bool = False) -> None:
        if was_removal_prevented or creature is not self.owner:
            return
        self.owner.trigger_about_to_blow()
        # CreatureCmd.SetMaxAndCurrentHp(999999999) — the game's "infinite HP"
        # display while the giant winds up to explode.
        self.owner.hp = self.owner.max_hp = 999_999_999


# ── Hive enemy powers ─────────────────────────────────────────────────────


class ImbalancedPower(Power):
    """When one of the owner's attacks is fully blocked, the owner is thrown
    off balance and loses its next turn (Bowlbug Rock; mirrors
    ImbalancedPower.AfterDamageGiven's WasFullyBlocked check). The owner may
    define `is_off_balance` (BowlbugRock's move machine reads it); other
    owners are stunned directly."""

    id = "imbalanced"
    name = "Imbalanced"
    power_type = PowerType.DEBUFF

    def on_damage_dealt(
        self,
        dealer: Creature,
        target: Creature,
        amount: int,
        card: Card | None = None,
        props: ValueProp = ValueProp.NONE,
        was_fully_blocked: bool = False,
    ) -> None:
        """ImbalancedPower.AfterDamageGiven (ImbalancedPower.cs:17-30):
        `dealer == base.Owner && result.WasFullyBlocked` — nothing else.
        Moved off `on_damage_received` (power/_after_damage_given_
        substitution, tier-2 Task 26): that hook is the WRONG side (victim,
        not dealer) and is killing-blow guarded, where AfterDamageGiven is
        neither. The substitution's `target is not self.owner` guard and its
        `amount == 0 and ValueProp.MOVE in props` predicate are both dropped
        here — C# has no target check (it gets one dispatch per hit and self-
        filters on `dealer`, not `target`), and `WasFullyBlocked` is broader
        than a plain `amount == 0` (it also requires block to have been in
        play) and does not gate on MOVE at all."""
        if dealer is self.owner and was_fully_blocked:
            if hasattr(self.owner, "is_off_balance"):
                self.owner.is_off_balance = True
            else:
                from .cmds import CreatureCmd
                CreatureCmd.stun(self.hooks, self.owner)


class HardToKillPower(Power):
    """The owner cannot take more than N damage per hit (Exoskeleton; mirrors
    HardToKillPower.ModifyDamageCap)."""

    id = "hard_to_kill"
    name = "Hard to Kill"
    power_type = PowerType.BUFF

    def modify_damage_cap(
        self,
        target: Creature,
        dealer: Creature | None,
        card: Card | None,
    ) -> int | None:
        if target is self.owner:
            return self.amount
        return None


class TenderPower(Power):
    """Each card the owner plays this turn costs them 1 Strength and 1
    Dexterity; both are restored at the end of the owner's turn (Hunter
    Killer's Tenderizing Goop; mirrors TenderPower)."""

    id = "tender"
    name = "Tender"
    power_type = PowerType.DEBUFF

    def __init__(
        self,
        owner: Creature,
        amount: int,
        hooks: HookSystem,
        applier: Creature | None = None,
    ) -> None:
        super().__init__(owner, amount, hooks, applier)
        self._cards_played_this_turn = 0

    def on_card_played(self, card: Card,
                       is_auto_play: bool = False) -> None:
        self._cards_played_this_turn += 1
        from .cmds import PowerCmd
        PowerCmd.apply(self.hooks, self.owner, StrengthPower, -1)
        PowerCmd.apply(self.hooks, self.owner, DexterityPower, -1)

    def after_player_turn_end(self, player: Creature) -> None:
        if player is not self.owner or self._cards_played_this_turn == 0:
            return
        from .cmds import PowerCmd
        PowerCmd.apply(self.hooks, self.owner, StrengthPower, self._cards_played_this_turn)
        PowerCmd.apply(self.hooks, self.owner, DexterityPower, self._cards_played_this_turn)
        self._cards_played_this_turn = 0


class HatchPower(Power):
    """Visible countdown until a Tough Egg hatches; decrements at the end of
    the owner's turn (mirrors HatchPower — the hatch itself is the egg's
    HATCH move, this power is just the timer)."""

    id = "hatch"
    name = "Hatch"
    power_type = PowerType.BUFF

    def on_enemy_side_end(self) -> None:
        # HatchPower.cs:18 — AfterSideTurnEnd, so every egg's timer ticks after
        # the whole side has moved, not as each egg's own turn ends.
        if self.owner.side == "enemy":
            self._tick()


class SlumberPower(Power):
    """The owner sleeps for N of its turns; each point of unblocked damage
    received also counts down a turn. Waking from damage costs the owner a
    stunned turn; a natural wake does not (Slumbering Beetle; mirrors
    SlumberPower). The owner must implement wake_up(stunned=...)."""

    id = "slumber"
    name = "Slumber"
    power_type = PowerType.BUFF

    def _count_down(self, woke_from_damage: bool) -> None:
        self.amount -= 1
        self.hooks.on_power_amount_changed(self.id, self.owner, -1)
        if self.amount <= 0:
            self._expire()
            self.owner.wake_up(stunned=woke_from_damage)

    def on_damage_received(
        self,
        target: Creature,
        amount: int,
        dealer: Creature | None,
        card: Card | None,
        props: ValueProp = ValueProp.NONE,
    ) -> None:
        if target is self.owner and amount > 0:
            self._count_down(woke_from_damage=True)

    def on_enemy_side_end(self) -> None:
        # SlumberPower.cs:40 — AfterSideTurnEnd.
        if self.owner.side == "enemy":
            self._count_down(woke_from_damage=False)


class EscapeArtistPower(Power):
    """Visual timer for when the Thieving Hopper will escape; counts down to 1
    at the end of the owner's turn (mirrors EscapeArtistPower — the escape
    itself is the hopper's ESCAPE move)."""

    id = "escape_artist"
    name = "Escape Artist"
    power_type = PowerType.BUFF

    def on_enemy_side_end(self) -> None:
        # EscapeArtistPower.cs:21 — AfterSideTurnEnd.
        if self.owner.side == "enemy" and self.amount > 1:
            self.amount -= 1
            self.hooks.on_power_amount_changed(self.id, self.owner, -1)


class FlutterPower(Power):
    """The owner takes 50% damage from powered attacks; each hit that deals
    unblocked damage consumes a stack, and at 0 the owner falls out of the air
    stunned (Thieving Hopper; mirrors FlutterPower)."""

    id = "flutter"
    name = "Flutter"
    power_type = PowerType.BUFF

    def modify_damage_multiplicative(
        self,
        target: Creature,
        amount: int,
        dealer: Creature | None,
        card: Card | None,
        props: ValueProp = ValueProp.NONE,
    ) -> float:
        if not is_powered_attack(props):   # FlutterPower.cs
            return 1.0
        if target is self.owner:
            return 0.5
        return 1.0

    def on_damage_received(
        self,
        target: Creature,
        amount: int,
        dealer: Creature | None,
        card: Card | None,
        props: ValueProp = ValueProp.NONE,
    ) -> None:
        from .valueprops import is_powered_attack
        if target is not self.owner or amount <= 0 or not is_powered_attack(props):
            return
        self.amount -= 1
        self.hooks.on_power_amount_changed(self.id, self.owner, -1)
        if self.amount <= 0:
            self._expire()
            if hasattr(self.owner, "is_hovering"):
                self.owner.is_hovering = False
            from .cmds import CreatureCmd
            # FlutterPower.cs:47 — Stun(owner, StunnedMove,
            # StateLog.Last().GetNextState(owner, RunRng.MonsterAi)): the stun
            # replaces the telegraphed move, so the owner resumes at the move
            # AFTER it. GetNextState on a MoveState is
            # (FollowUpState?.Id ?? FollowUpStateId) — DETERMINISTIC
            # (MoveState.cs:67-70) — so the splice itself consumes no draw and
            # the branch, if any, is resolved by the post-stun roll. Walking
            # the machine here instead both drew a branch off the shared
            # combat random.Random and drew it a turn early.
            machine = getattr(self.owner, "machine", None)
            next_move_key = None
            if machine is not None:
                next_move_key = machine.state_log[-1].get_next_state(
                    self.owner, self.owner._move_rng
                )
            CreatureCmd.stun(self.hooks, self.owner, next_move_key=next_move_key)


class SwipePower(Power):
    """Holds the card(s) the Thieving Hopper stole (SwipePower.cs).

    Steal() removes the card from the run deck for good; BeforeDeath — only
    when the *owner* dies, never on escape — queues the deck version of each
    stolen card as a take-or-skip SpecialCardReward on the combat room
    (CombatRoom.AddExtraReward). Here: on_death appends a RewardExtra card
    entry to the combat's pending_reward_extras, carrying the run-deck origin
    of the stolen combat copy (the DeckVersion analogue); cards with no deck
    origin never come back (BeforeDeath's DeckVersion == null early-out).

    NOT switched to `instance_type = PowerInstanceType.INSTANCED`
    (PowerInstanceType.Instanced, SwipePower.cs:23; power_cmd/G5): each
    steal bundles into this SAME instance's `stolen_cards` today because
    `PowerCmd.apply`'s default (None) dispatch keeps finding it. Under the
    generic Instanced dispatch each steal would instead start a fresh
    instance with an empty `stolen_cards`, orphaning the earlier one(s) from
    `target.powers` — and `RunState.finish_combat` (run.py) walks an escaped
    hopper's deck-removal reconciliation through `enemy.powers.get("swipe")`
    alone, so any steal but the last would silently stay in the run deck.
    The current one-bucket approximation is what that walk depends on."""

    id = "swipe"
    name = "Swipe"
    power_type = PowerType.BUFF

    def __init__(
        self,
        owner: Creature,
        amount: int,
        hooks: HookSystem,
        applier: Creature | None = None,
    ) -> None:
        super().__init__(owner, amount, hooks, applier)
        self.stolen_cards: list[Card] = []

    def on_death(self, creature: Creature,
                 was_removal_prevented: bool = False) -> None:
        if creature is not self.owner:
            return
        combat = self.hooks.combat
        if combat is None:
            return
        from .rewards import RewardExtra
        for card in self.stolen_cards:
            origin = combat.deck_card_origins.get(id(card))
            if origin is not None:
                combat.pending_reward_extras.append(RewardExtra.of_card(origin))

    def hand_off_stolen_origins(self) -> None:
        """Record this power's stolen cards' deck origins on the combat, so
        RunState.finish_combat can remove them from the run deck once this
        power is gone — the sim's own reconciliation-at-combat-end substitute
        for C#'s immediate `CardPileCmd.RemoveFromDeck` at steal time
        (SwipePower.cs:75). `SwipePower` does not override
        ShouldPowerBeRemovedAfterOwnerDeath, so the game strips it like any
        other power on death or escape; C# needs no hand-off because the deck
        removal already happened at steal time.

        Shared by the two paths that make this power disappear: death
        (`on_removed`, below — CreatureCmd.cs:533-537's AfterRemoved) and
        escape (`ThievingHopper._escape`, called BEFORE `CreatureCmd.escape`'s
        silent strip — creature_card_cmds/G13 — removes the power with no
        `on_removed` call).
        """
        combat = self.hooks.combat
        if combat is None:
            return
        for card in self.stolen_cards:
            origin = combat.deck_card_origins.get(id(card))
            if origin is not None:
                combat.stolen_deck_origins.append(origin)

    def on_removed(self, owner: Creature) -> None:
        """AfterRemoved, awaited for each power a DEATH strips
        (CreatureCmd.cs:533-537). Hands off before this power is gone."""
        self.hand_off_stolen_origins()


class BurrowedPower(Power):
    """The owner's block persists between turns; when its block is broken by
    an attack it is dug out of the ground and loses its next turn (Tunneler;
    mirrors BurrowedPower). The owner must implement get_stunned()."""

    id = "burrowed"
    name = "Burrowed"
    power_type = PowerType.BUFF

    def should_clear_block(self, creature: Creature) -> bool:
        if creature is self.owner:
            return False
        return True

    def on_block_broken(
        self, target: Creature, dealer: Creature | None = None,
        card: Card | None = None,
    ) -> None:
        if target is not self.owner:
            return
        # BurrowedPower.cs:24-36, in order and now clause for clause:
        #   tunneler.GetStunned()
        #   CreatureCmd.Stun(Owner, tunneler.StillDizzyMove, "BITE_MOVE")
        #   PowerCmd.Remove<BurrowedPower>(Owner)
        # and AfterRemoved (:38-40) then dumps the block.
        #
        # `GetStunned()` is Tunneler.cs:130-134 -- `IsStunned = true` plus a
        # TriggerAnim -- and `IsStunned`'s only readers in the whole source are
        # two animator predicates (Tunneler.cs:162-163), so it is presentation.
        # THE STATE CHANGE IS THE SECOND CALL, and the port did not make it: it
        # called the monster's own `get_stunned()`, which forces the REGISTERED
        # DIZZY_MOVE state. `CreatureCmd.Stun` goes through
        # `Creature.StunInternal` (Creature.cs:524-544), which builds a SYNTHETIC
        # move with `MustPerformOnceBeforeTransitioning = true` and
        # `FollowUpStateId = nextMoveId` -- so without it the machine could
        # transition away before the stunned turn was ever performed and the
        # Tunneler would not lose its turn at all. It also never set `stunned`.
        #
        # Note the registered DIZZY_MOVE state has NO incoming edge in the
        # source's own machine (BITE -> BURROW -> BELOW -> BELOW is the whole
        # graph, Tunneler.cs:69-85), so the synthetic state is the only way in.
        from .cmds import BlockCmd, CreatureCmd

        get_stunned = getattr(self.owner, "get_stunned", None)
        if get_stunned is not None:
            get_stunned()
        CreatureCmd.stun(self.hooks, self.owner, next_move_key="BITE_MOVE")
        self._expire()
        # BurrowedPower.cs:38-41 — AfterRemoved:
        # `CreatureCmd.LoseBlock(oldOwner, 999999999m)` (creature_card_cmds/
        # step18). Dormant on today's only ported caller: block is already 0
        # by the time this handler runs (it fires FROM the break), so the
        # re-fire this verb adds over the old raw `block = 0` assignment
        # never triggers here — but it is what a second, non-self-zeroing
        # LoseBlock(all) caller would need.
        BlockCmd.lose_block(self.hooks, self.owner, 999999999)


class ReattachPower(Power):
    """A Decimillipede segment cannot truly die while another segment stands:
    it withers (unhittable, no move) and reattaches two of its turns later
    with N HP. Killing the last standing segment kills the whole millipede
    (mirrors ReattachPower's ShouldOwnerDeathTriggerFatal — a withered segment
    counts as dead for that check)."""

    id = "reattach"
    name = "Reattach"
    power_type = PowerType.BUFF

    def should_power_be_removed_after_owner_death(self) -> bool:
        return False   # ReattachPower.cs:98-101

    def should_owner_death_trigger_fatal(self) -> bool:
        # ReattachPower.cs:106-109 — "Killing Decimillipede Segment shouldn't
        # trigger fatal unless all other segments are dead too."
        return self._all_others_down()

    def __init__(
        self,
        owner: Creature,
        amount: int,
        hooks: HookSystem,
        applier: Creature | None = None,
    ) -> None:
        super().__init__(owner, amount, hooks, applier)
        self.is_reviving = False

    def _other_segments(self) -> list[Creature]:
        combat = self.hooks.combat
        if combat is None:
            return []
        return [
            e for e in combat.enemies
            if e is not self.owner and "reattach" in e.powers
        ]

    def _all_others_down(self) -> bool:
        # AreAllOtherSegmentsDead: a withered segment sits at 0 HP, so plain
        # IsDead already covers it.
        return all(s.is_dead for s in self._other_segments())

    def should_remove_from_combat_after_death(self, creature: Creature) -> bool:
        # ShouldCreatureBeRemovedFromCombatAfterDeath — the segment's corpse
        # never leaves the combat, so it can reattach later.
        return creature is not self.owner

    def on_death(self, creature: Creature,
                 was_removal_prevented: bool = False) -> None:
        # AfterDeath: the segment withers (hidden DEAD move, unhittable) unless
        # every other segment is already down, in which case the death stands
        # and the fight is over.
        if creature is not self.owner or self.is_reviving:
            return
        if self._all_others_down():
            return
        self.is_reviving = True
        self.owner.enter_dead_state()

    def should_allow_hitting(self, target: Creature) -> bool:
        if target is self.owner and self.is_reviving:
            return False
        return True

    def do_reattach(self) -> None:
        """Called by the owner's REATTACH move: come back with N HP."""
        if self._all_others_down():
            return  # mirrors DoReattach's AreAllOtherSegmentsDead guard
        self.is_reviving = False
        self.owner.retained_after_death = False
        delta = self.amount - self.owner.hp
        self.owner.hp = self.amount
        self.hooks.on_hp_changed(self.owner, delta)


class PersonalHivePower(Power):
    """Whenever a powered attack hits the owner, N Dazed cards are shuffled
    into the attacker's draw pile — even if the hit was fully blocked
    (Entomancer; mirrors PersonalHivePower.AfterDamageReceived)."""

    id = "personal_hive"
    name = "Personal Hive"
    power_type = PowerType.BUFF

    def on_damage_received(
        self,
        target: Creature,
        amount: int,
        dealer: Creature | None,
        card: Card | None,
        props: ValueProp = ValueProp.NONE,
    ) -> None:
        from .valueprops import is_powered_attack
        if (
            target is not self.owner
            or dealer is None
            or dealer.side != "player"
            or not is_powered_attack(props)
        ):
            return
        from .cards import DazedCard
        from .cmds import CardPileCmd
        for _ in range(self.amount):
            CardPileCmd.add_to_draw(self.hooks, dealer, DazedCard())


class VitalSparkPower(Power):
    """Afflicts every Skill the player owns with Tainted N: playing a Tainted
    card gives the player Tainted N (take +N attack damage until end of the
    enemy turn). Skills created mid-combat are afflicted too; stacking the
    power raises every affliction's amount; the afflictions clear when the
    owner dies (Infested Prism; mirrors VitalSparkPower)."""

    id = "vital_spark"
    name = "Vital Spark"
    power_type = PowerType.BUFF

    @staticmethod
    def _is_skill(card: Card) -> bool:
        from .cards import CardType
        return card.card_type == CardType.SKILL

    def _afflict(self, card: Card) -> None:
        from .afflictions import TaintedAffliction
        from .cmds import CardCmd
        CardCmd.afflict(card, TaintedAffliction, self.amount)

    def _player_cards(self):
        combat = self.hooks.combat
        return combat.player.all_cards if combat is not None else ()

    def on_combat_start(self) -> None:
        for card in self._player_cards():
            if self._is_skill(card) and card.affliction is None:
                self._afflict(card)

    def on_card_entered_combat(self, card: Card) -> None:
        if self._is_skill(card) and card.affliction is None:
            self._afflict(card)

    def on_card_played(self, card: Card,
                       is_auto_play: bool = False) -> None:
        from .afflictions import TaintedAffliction
        if isinstance(card.affliction, TaintedAffliction):
            combat = self.hooks.combat
            if combat is not None:
                from .cmds import PowerCmd
                PowerCmd.apply(self.hooks, combat.player, TaintedPower, self.amount)

    def on_stack(self, amount: int) -> None:
        super().on_stack(amount)
        # AfterPowerAmountChanged: sync every Tainted affliction to the new amount.
        from .afflictions import TaintedAffliction
        for card in self._player_cards():
            if isinstance(card.affliction, TaintedAffliction):
                card.affliction.amount = self.amount

    def on_death(self, creature: Creature,
                 was_removal_prevented: bool = False) -> None:
        if creature is not self.owner:
            return
        from .afflictions import TaintedAffliction
        from .cmds import CardCmd
        for card in self._player_cards():
            if isinstance(card.affliction, TaintedAffliction):
                CardCmd.clear_affliction(card)
        self._expire()


class TaintedPower(Power):
    """The owner takes +N damage from powered attacks; removed at the end of
    the enemy turn (applied by VitalSparkPower when a Tainted Skill is
    played; mirrors TaintedPower)."""

    id = "tainted"
    name = "Tainted"
    power_type = PowerType.DEBUFF

    def modify_damage_additive(
        self,
        target: Creature,
        amount: int,
        dealer: Creature | None,
        card: Card | None,
        props: ValueProp = ValueProp.NONE,
    ) -> int:
        if not is_powered_attack(props):   # TaintedPower.cs
            return 0
        if target is self.owner:
            return self.amount
        return 0

    def on_enemy_side_end(self) -> None:
        self._expire()


class BackAttackLeftPower(Power):
    """Marker power for SurroundedPower (the Kaiser Crab's left arm)."""

    id = "back_attack_left"
    name = "Back Attack (Left)"
    power_type = PowerType.BUFF


class BackAttackRightPower(Power):
    """Marker power for SurroundedPower (the Kaiser Crab's right arm)."""

    id = "back_attack_right"
    name = "Back Attack (Right)"
    power_type = PowerType.BUFF


class CrabRagePower(Power):
    """When a teammate dies, the owner gains 6 Strength and 99 block, then
    this power is removed (Kaiser Crab; mirrors CrabRagePower)."""

    id = "crab_rage"
    name = "Crab Rage"
    power_type = PowerType.BUFF

    STRENGTH_GAIN = 6
    BLOCK_GAIN = 99

    def on_death(self, creature: Creature,
                 was_removal_prevented: bool = False) -> None:
        if creature is self.owner or creature.side != self.owner.side:
            return
        from .cmds import BlockCmd, PowerCmd
        from .valueprops import ValueProp as VP
        PowerCmd.apply(self.hooks, self.owner, StrengthPower, self.STRENGTH_GAIN)
        BlockCmd.apply(self.hooks, self.owner, self.BLOCK_GAIN, props=VP.UNPOWERED)
        self._expire()


class SurroundedPower(Power):
    """Kaiser Crab: the player faces one arm; the other arm's attacks deal
    50% more damage. Playing ANY targeted card (or potion) at a crab turns
    the player to face it — regardless of whether the card deals damage;
    when an arm dies the player faces the survivor.

    Source: SurroundedPower.cs — BeforeCardPlayed: `if (cardPlay.Target !=
    null && cardPlay.Card.Owner == base.Owner.Player) await UpdateDirection
    (cardPlay.Target);`. The trigger is the targeted card *play*, not
    damage dealt — a non-damaging targeted Skill (e.g. Tremble) flips
    facing just as an Attack does."""

    id = "surrounded"
    name = "Surrounded"
    power_type = PowerType.DEBUFF

    def __init__(
        self,
        owner: Creature,
        amount: int,
        hooks: HookSystem,
        applier: Creature | None = None,
    ) -> None:
        super().__init__(owner, amount, hooks, applier)
        self.facing = "right"

    def modify_damage_multiplicative(
        self,
        target: Creature,
        amount: int,
        dealer: Creature | None,
        card: Card | None,
        props: ValueProp = ValueProp.NONE,
    ) -> float:
        if target is not self.owner or dealer is None:
            return 1.0
        if self.facing == "right" and "back_attack_left" in dealer.powers:
            return 1.5
        if self.facing == "left" and "back_attack_right" in dealer.powers:
            return 1.5
        return 1.0

    def _update_direction(self, target: Creature) -> None:
        if self.facing == "right" and "back_attack_left" in target.powers:
            self.facing = "left"
        elif self.facing == "left" and "back_attack_right" in target.powers:
            self.facing = "right"

    def before_card_played(self, card: Card, target: Creature | None = None) -> None:
        # cardPlay.Card.Owner == base.Owner.Player is always true here: the
        # sim is single-player and Surrounded is only ever applied to the
        # player, so every played card belongs to this power's owner.
        if target is not None:
            self._update_direction(target)

    def before_potion_used(self, potion, target: Creature | None) -> None:
        # SurroundedPower.cs:82 is BeforePotionUsed, not After.
        if target is not None:
            self._update_direction(target)

    def on_death(self, creature: Creature,
                 was_removal_prevented: bool = False) -> None:
        if creature.side == self.owner.side:
            return
        combat = self.hooks.combat
        if combat is None:
            return
        living = [e for e in combat.enemies if not e.is_gone]
        if living and all("back_attack_left" in e.powers for e in living):
            self._update_direction(living[0])
        elif living and all("back_attack_right" in e.powers for e in living):
            self._update_direction(living[0])


class SandpitPower(Power):
    """The Insatiable's devour timer: counts down at the start of the owner's
    turn; when it runs out the player is eaten — killed outright (mirrors
    SandpitPower.AfterRemoved). Frantic Escape adds a stack, delaying it.

    InstanceType.Instanced (SandpitPower.cs:37, power_cmd/G5): a second
    LIQUIFY would start its own independent countdown rather than merging
    into this one's — either one reaching 0 still eats the player. Frantic
    Escape's own re-application bypasses this entirely and goes straight to
    ModifyAmount on the found instance (FranticEscape.cs:38-42, mirrored by
    FranticEscapeCard.on_play calling PowerCmd.modify_amount directly), so
    it is unaffected."""

    id = "sandpit"
    name = "Sandpit"
    power_type = PowerType.BUFF
    instance_type = PowerInstanceType.INSTANCED

    def after_enemy_side_start_late(self) -> None:
        # SandpitPower.cs:70 — AfterSideTurnStartLATE, gated on
        # `side == CombatSide.Enemy` with no owner or participants filter at
        # all, so the countdown is guaranteed last among the side-start
        # listeners. The sim ran it on the per-enemy turn start, where the
        # phase did not exist and the order was whatever registration gave.
        self._tick()

    def _expire(self) -> None:
        owner_gone = self.owner.is_gone
        combat = self.hooks.combat
        super()._expire()
        if owner_gone or combat is None:
            return
        target = combat.player
        if not target.is_dead:
            from .cmds import CreatureCmd
            CreatureCmd.kill(self.hooks, target)


class DisintegrationPower(Power):
    """The owner takes N unpowered damage at the end of each of their turns
    (Knowledge Demon's Curse of Knowledge; mirrors DisintegrationPower)."""

    id = "disintegration"
    name = "Disintegration"
    power_type = PowerType.DEBUFF

    def after_player_turn_end_late(self, player: Creature) -> None:
        if player is not self.owner:
            return
        from .cmds import DamageCmd
        from .valueprops import DamageProps
        DamageCmd.deal(
            self.hooks, self.owner, self.amount, props=DamageProps.NON_CARD_UNPOWERED
        )


class MindRotPower(Power):
    """The owner draws N fewer cards at the start of each turn (Knowledge
    Demon's Curse of Knowledge; mirrors MindRotPower)."""

    id = "mind_rot"
    name = "Mind Rot"
    power_type = PowerType.DEBUFF

    def modify_hand_draw(self, player: Creature, count: int) -> int:
        if player is self.owner:
            return max(0, count - self.amount)
        return count


class SlothPower(Power):
    """The owner can only play N cards per turn (Knowledge Demon's Curse of
    Knowledge; mirrors SlothPower)."""

    id = "sloth"
    name = "Sloth"
    power_type = PowerType.DEBUFF

    def __init__(
        self,
        owner: Creature,
        amount: int,
        hooks: HookSystem,
        applier: Creature | None = None,
    ) -> None:
        super().__init__(owner, amount, hooks, applier)
        self._cards_played_this_turn = 0

    def should_play_card(self, card: Card, auto_play: bool = False) -> bool:
        return self._cards_played_this_turn < self.amount

    def on_card_played(self, card: Card,
                       is_auto_play: bool = False) -> None:
        self._cards_played_this_turn += 1

    def before_side_turn_start(self, player: Creature) -> None:
        if player is self.owner:
            self._cards_played_this_turn = 0


class WasteAwayPower(Power):
    """The owner gains N less energy at the start of each turn (Knowledge
    Demon's Curse of Knowledge; mirrors WasteAwayPower)."""

    id = "waste_away"
    name = "Waste Away"
    power_type = PowerType.DEBUFF

    def modify_max_energy(self, player: Creature, amount: int) -> int:
        if player is self.owner:
            return amount - self.amount
        return amount


# ── Event-card powers (Trash Heap / Endless Conveyor) ─────────────────────


class FeedingFrenzyPower(TemporaryStrengthPower):
    """Temporary Strength from Feeding Frenzy (Endless Conveyor's Seapunk
    Salad card): granted on play, reverted at the end of the owner's turn.

    Source: FeedingFrenzyPower.cs (a TemporaryStrengthPower)."""

    id = "feeding_frenzy"
    name = "Feeding Frenzy"
    power_type = PowerType.BUFF


class DiamondDiademPower(Power):
    """Powered attack damage against the owner is HALVED; removed after the
    enemy side's turn ends (DiamondDiademPower.cs — granted by Diamond Diadem
    when the owner ended their turn having played few cards)."""

    id = "diamond_diadem"
    name = "Diamond Diadem"
    power_type = PowerType.BUFF

    def modify_damage_multiplicative(
        self,
        target: Creature,
        amount: int,
        dealer: Creature | None,
        card: Card | None,
        props: ValueProp = ValueProp.NONE,
    ) -> float:
        # DiamondDiademPower.cs:27-30 self-gates. This comment used to read
        # "the powered-attack gate is applied by the damage pipeline caller",
        # which was true until damage_pipeline/G3 pushed the gate into the
        # listeners — after that the halving applied to Poison, Thorns, a Fire
        # Potion and Disintegration, which the game does not halve.
        if target is not self.owner:
            return 1.0
        if not is_powered_attack(props):
            return 1.0
        return 0.5

    def on_enemy_side_end(self) -> None:
        self._expire()


class DrawCardsNextTurnPower(Power):
    """Draw N extra cards at the start of the owner's next turn, then remove
    (Relax; mirrors DrawCardsNextTurnPower.ModifyHandDraw + the turn-start
    removal). Counter-stacked, so replaying stacks the pending draws."""

    id = "draw_cards_next_turn"
    name = "Draw Cards Next Turn"
    power_type = PowerType.BUFF

    def modify_hand_draw(self, player: Creature, count: int) -> int:
        if player is not self.owner:
            return count
        # DrawCardsNextTurnPower.cs:28 — `AmountOnTurnStart == 0` means this
        # stack was applied DURING the current turn's own setup window (a
        # power that did not exist yet at Creature.BeforeTurnStart snapshots
        # at the type's zero default, Creature.cs:673-679) rather than one
        # already sitting on the owner when the turn began — so it neither
        # draws nor expires (see after_side_turn_start below) this turn, only
        # the next one. `getattr` because the snapshot lives on the instance,
        # not declared on Power.__init__ — see `Creature.
        # snapshot_powers_on_turn_start`.
        if getattr(self, "amount_on_turn_start", 0) == 0:
            return count
        return count + self.amount

    def after_side_turn_start(self, player: Creature) -> None:
        # DrawCardsNextTurnPower.cs:35-38 — the SAME AmountOnTurnStart guard
        # on the removal side, so a stack applied this turn's own setup
        # window is never drawn AND never expires this turn; it survives to
        # actually take effect (and then expire) next turn instead.
        if player is self.owner and getattr(self, "amount_on_turn_start", 0) != 0:
            self._expire()


class EnergyNextTurnPower(Power):
    """Gain N energy at the start of the owner's next turn, then remove
    (Outmaneuver; mirrors EnergyNextTurnPower.AfterEnergyReset → GainEnergy +
    Remove). Counter-stacked, so replaying stacks the pending energy."""

    id = "energy_next_turn"
    name = "Energy Next Turn"
    power_type = PowerType.BUFF

    def on_energy_reset(self, player: Creature) -> None:
        if player is not self.owner:
            return
        from .cmds import EnergyCmd
        EnergyCmd.gain(self.hooks, self.owner, self.amount)
        self._expire()


class ReboundPower(Power):
    """The owner's next N card plays go on top of the draw pile instead of the
    discard pile; removed at the end of the owner's turn (Rebound; mirrors
    ReboundPower.ModifyCardPlayResultPileTypeAndPosition + AfterSideTurnEnd).

    Rebound applies this during its own resolution, so — matching the game's
    ordering — the Rebound card itself is the first play redirected."""

    id = "rebound"
    name = "Rebound"
    power_type = PowerType.BUFF

    def on_card_played(self, card: Card,
                       is_auto_play: bool = False) -> None:
        player = self.owner
        # ModifyCardPlayResultPileTypeAndPosition only redirects Discard → Draw
        # top (power cards leave combat, exhausted cards are already gone).
        if card not in getattr(player, "discard_pile", ()):
            return
        player.discard_pile.remove(card)
        player.draw_pile.append(card)  # list end = top of draw pile
        self._tick()

    def after_player_turn_end(self, player: Creature) -> None:
        if player is self.owner:
            self._expire()


class HelloWorldPower(Power):
    """At the start of each of the owner's turns (before the hand draw), add N
    distinct random Common cards from the character pool to the hand
    (Hello World; mirrors HelloWorldPower.BeforeHandDraw). Counter-stacked."""

    id = "hello_world"
    name = "Hello World"
    power_type = PowerType.BUFF

    def on_player_turn_start(self, player: Creature) -> None:
        # HelloWorldPower.cs:19-27 gates AND counts on `base.AmountOnTurnStart`
        # — NOT `base.Amount` — so a stack applied during this turn's own
        # setup window (never snapshotted; the type's zero default,
        # Creature.cs:673-679) grants nothing this turn, and an amount that
        # somehow changed after the snapshot still generates the SNAPSHOTTED
        # count. `getattr` because the snapshot lives on the instance, not
        # declared on Power.__init__ — see `Creature.
        # snapshot_powers_on_turn_start`.
        snapshot = getattr(self, "amount_on_turn_start", 0)
        if player is not self.owner or snapshot < 1:
            return
        from .cards import CardRarity, make_card
        from .cards.pool import pool_card_ids
        from .cmds import CardPileCmd
        combat = self.hooks.combat
        if combat is None:
            return
        commons = [
            cid for cid in pool_card_ids(pool=combat.card_pool)
            if make_card(cid).rarity == CardRarity.COMMON
        ]
        if not commons:
            return
        n = min(snapshot, len(commons))
        # `CardFactory.GetDistinctForCombat(..., Rng.CombatCardGeneration)`
        # (HelloWorldPower.cs:23-27) ends in `TakeRandom(count, rng)`, which is
        # `collection.ToList().UnstableShuffle(rng).Take(count)`
        # (IEnumerableExtensions.cs:17-20): a FULL Fisher-Yates shuffle of the
        # candidates on the CombatCardGeneration stream, then the first N.
        # `random.sample` on the shared rng is a different algorithm on a
        # different stream.
        pool = list(commons)
        combat.combat_rng.card_gen.shuffle(pool)
        for cid in pool[:n]:
            CardPileCmd.add_to_hand(self.hooks, player, make_card(cid))


# ── Glory (Act 3) card / enemy powers ──────────────────────────────────────


class StranglePower(Power):
    """For the rest of this turn, whenever the applier plays a card the owner
    takes [amount] unblockable, unpowered damage. Removed at the end of the
    owner's side turn.

    Source: StranglePower.cs — BeforeCardPlayed records the amount for each card
    the applier plays (so it never triggers on the card that applied it), and
    AfterCardPlayed deals that amount to the owner. Applied to a target by the
    Mad Science card's Choking rider (Tinker Time event).

    InstanceType.InstancedPerApplier (StranglePower.cs:29, power_cmd/G5): a
    second application from the SAME applier still stacks onto this
    instance (unchanged); one from a DIFFERENT applier starts its own
    instance instead of merging. The only ported applier is the player, so
    a second applier never observably matters today."""

    id = "strangle"
    name = "Strangle"
    power_type = PowerType.DEBUFF
    instance_type = PowerInstanceType.INSTANCED_PER_APPLIER

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # Cards seen at BeforeCardPlayed → the Strangle amount at that moment
        # (mirrors the source's amountsForPlayedCards). A card only triggers
        # Strangle if it was recorded here, so the card that applied Strangle —
        # already past its BeforeCardPlayed — never triggers it on itself.
        self._amounts: dict[int, int] = {}

    def before_card_played(self, card: Card, target: Creature | None = None) -> None:
        self._amounts[id(card)] = self.amount

    def on_card_played(self, card: Card,
                       is_auto_play: bool = False) -> None:
        amount = self._amounts.pop(id(card), None)
        if amount is None or self.owner.is_gone:
            return
        from .cmds import DamageCmd
        from .valueprops import DamageProps
        DamageCmd.deal(
            self.hooks, self.owner, amount, props=DamageProps.NON_CARD_HP_LOSS
        )

    def on_enemy_side_end(self) -> None:
        self._expire()


class CuriousPower(Power):
    """Power cards cost [amount] less energy (minimum 0).

    Source: CuriousPower.cs — TryModifyEnergyCostInCombat reduces the owner's
    Power cards by Amount, floored at 0. Applied by the Mad Science card's
    Curious rider (Tinker Time event)."""

    id = "curious"
    name = "Curious"
    power_type = PowerType.BUFF

    def modify_card_energy_cost(self, card: Card, cost: int) -> int:
        from .cards import CardType
        if card.card_type != CardType.POWER or cost <= 0:
            return cost
        return max(0, cost - self.amount)


class ImprovementPower(Power):
    """After combat, upgrade [amount] random upgradable deck cards.

    Source: ImprovementPower.cs:17-31 — AfterCombatEnd. Applied by the Mad
    Science card's Improvement rider (the Act-3 Glory event Tinker Time).

    The pile it reads is `PileType.Deck.GetPile(Owner.Player)`: the RUN deck, not
    this combat's copy of it. That is why the effect is dispatched from
    `RunState.finish_combat` and not from the combat-level `on_combat_end` — a
    `CombatState` holds no run back-reference by design, and `Hook.AfterCombatEnd`
    reaches this power from the RUN's walk anyway, because
    `runState.IterateHookListeners(combatState)` appends the whole combat
    listener list while `childCombatState` is still set (seam/hook_dispatch
    step 18).
    """

    id = "improvement"
    name = "Improvement"
    power_type = PowerType.BUFF

    def after_combat_end(self, run) -> None:
        from .cmds import CardCmd

        # `.Where(c => c.IsUpgradable)` is evaluated ONCE, before the loop, and
        # each pick is removed from that candidate list rather than the list
        # being re-filtered — so the picks are distinct, and `Amount` larger than
        # the candidate pool is not an error (`if (list.Count == 0) break`).
        candidates = [c for c in run.deck if c.is_upgradable]
        # `Owner.Player.RunState.Rng.CombatCardSelection` — the per-player
        # CombatCardSelection stream, which is `combat_rng.card_selection` here
        # and NOT the shared `combat._rng`. Six earlier powers in this seam took
        # their draw off the wrong object; this is the trap power/improvement/g1
        # was recorded to warn about, and it is now a real draw rather than a
        # note.
        rng = self.hooks.combat.combat_rng.card_selection
        for _ in range(self.amount):
            if not candidates:
                break
            card = rng.choice(candidates)
            candidates.remove(card)
            # CardCmd.Upgrade, so the per-card IsUpgradable re-test and the
            # MaxUpgradeLevel guard apply. `hooks=None`: CardCmd.Upgrade's outer
            # `!IsEnding` is a COMBAT guard, and this is a run-level effect
            # running after the fight — passing the finished combat's hooks would
            # let a stale ending flag swallow the upgrade.
            CardCmd.upgrade(None, card)


class BattlewornDummyTimeLimitPower(Power):
    """At the end of the owner's turn, count down; at 0 the owner flees.

    Source: BattlewornDummyTimeLimitPower.cs — AfterSideTurnEnd decrements while
    Amount > 1, otherwise flags the encounter as RanOutOfTime and Escapes the
    owner. Applied to the Battle Friend dummies (Battleworn Dummy event); if the
    player cannot destroy the dummy in time it escapes and no reward is given."""

    id = "battleworn_dummy_time_limit"
    name = "Time Limit"
    power_type = PowerType.BUFF

    def on_enemy_side_end(self) -> None:
        # BattlewornDummyTimeLimitPower.cs:19 — AfterSideTurnEnd.
        if self.owner.side != "enemy":
            return
        if self.amount > 1:
            self.amount -= 1
            self.hooks.on_power_amount_changed(self.id, self.owner, -1)
            return
        encounter = getattr(self.hooks.combat, "encounter", None)
        if encounter is not None and hasattr(encounter, "ran_out_of_time"):
            encounter.ran_out_of_time = True
        from .cmds import CreatureCmd
        CreatureCmd.escape(self.hooks, self.owner)


# ── Glory (Act 3) enemy powers ─────────────────────────────────────────────


class PaperCutsPower(Power):
    """When one of the owner's powered attacks deals unblocked damage to the
    player, the player loses N max HP (Scroll of Biting; mirrors
    PaperCutsPower.AfterDamageGiven)."""

    id = "paper_cuts"
    name = "Paper Cuts"
    power_type = PowerType.BUFF

    def on_damage_dealt(
        self,
        dealer: Creature,
        target: Creature,
        amount: int,
        card: Card | None = None,
        props: ValueProp = ValueProp.NONE,
        was_fully_blocked: bool = False,
    ) -> None:
        """PaperCutsPower.AfterDamageGiven (PaperCutsPower.cs:16-23):
        `dealer == base.Owner && target.IsPlayer && props.IsPoweredAttack() &&
        result.UnblockedDamage > 0` — all four guards were already faithful
        on the substitution (power/_after_damage_given_substitution, tier-2
        Task 26); `amount` here is `hp_lost`, the same value
        `UnblockedDamage` is. Only the hook was wrong: `on_damage_received`
        is the victim-side event and is killing-blow guarded, so a lethal
        Scroll of Biting hit never cost the player max HP in the sim though
        it does in the game. `on_damage_dealt` is dealer-side and not
        killing-blow guarded, matching AfterDamageGiven."""
        from .valueprops import is_powered_attack
        if (
            dealer is self.owner
            and target.side == "player"
            and amount > 0
            and is_powered_attack(props)
        ):
            from .cmds import CreatureCmd
            # PaperCutsPower.cs:20 — `isFromCard: false`.
            CreatureCmd.lose_max_hp(self.hooks, target, self.amount, from_card=False)


class StockPower(Power):
    """When the owner dies, a fresh Axebot spawns in its place with one fewer
    Stock (Axebot; mirrors StockPower.AfterDeath + ShouldStopCombatFromEnding).
    The replacement boots up before attacking."""

    id = "stock"
    name = "Stock"
    power_type = PowerType.BUFF

    def should_stop_combat_from_ending(self) -> bool:
        """StockPower.cs:28-31 — an unconditional `return true`, and the sim
        had not ported it. It is what holds the fight open across the death:
        `CombatManager.IsEnding` consults Hook.ShouldStopCombatFromEnding
        (CombatManager.cs:196), so without it the last Axebot's death makes the
        combat "ending" and every command the respawn issues is refused."""
        return True

    def on_death(self, creature: Creature,
                 was_removal_prevented: bool = False) -> None:
        if creature is not self.owner or self.amount <= 0:
            return
        combat = self.hooks.combat
        if combat is None:
            return
        from .cmds import CreatureCmd
        from .monsters.glory.axebot import Axebot
        CreatureCmd.add(
            self.hooks,
            Axebot(self.hooks, combat._rng, stock=self.amount - 1, respawn=True),
        )
        self._expire()


class RampartPower(Power):
    """At the start of the player's turn, every Turret Operator ally gains N
    block (Living Shield; mirrors RampartPower.AfterSideTurnStart)."""

    id = "rampart"
    name = "Rampart"
    power_type = PowerType.BUFF

    def after_side_turn_start(self, player: Creature) -> None:
        combat = self.hooks.combat
        if combat is None:
            return
        # RampartPower.cs:23 — `side != CombatSide.Player ||
        # CombatManager.Instance.PlayersTakingExtraTurn.Count > 0` -> return.
        # The block is refused on a player's EXTRA turn, and the sim had no such
        # flag at all: hold Pael's Eye, end a turn without playing a card, and
        # the sim re-blocked the Turret Operator where the game leaves it bare.
        if combat.players_taking_extra_turn:
            return
        from .cmds import BlockCmd
        from .monsters.glory.turret_operator import TurretOperator
        for enemy in combat.enemies:
            if isinstance(enemy, TurretOperator) and not enemy.is_gone:
                BlockCmd.apply(self.hooks, enemy, self.amount, props=ValueProp.UNPOWERED)


class GalvanicPower(Power):
    """Afflicts every Power card the player owns with Galvanized; playing a
    Galvanized card deals N (unpowered) damage to the player (Globe Head;
    mirrors GalvanicPower). Power cards created mid-combat are afflicted too."""

    id = "galvanic"
    name = "Galvanic"
    power_type = PowerType.BUFF

    @staticmethod
    def _is_power(card: Card) -> bool:
        from .cards import CardType
        return card.card_type == CardType.POWER

    def _afflict(self, card: Card) -> None:
        from .afflictions import GalvanizedAffliction
        from .cmds import CardCmd
        CardCmd.afflict(card, GalvanizedAffliction, self.amount)

    def _player_cards(self):
        combat = self.hooks.combat
        return combat.player.all_cards if combat is not None else ()

    def on_combat_start(self) -> None:
        for card in self._player_cards():
            if self._is_power(card) and card.affliction is None:
                self._afflict(card)

    def on_card_entered_combat(self, card: Card) -> None:
        if self._is_power(card) and card.affliction is None:
            self._afflict(card)

    def on_card_played(self, card: Card,
                       is_auto_play: bool = False) -> None:
        from .afflictions import GalvanizedAffliction
        if not isinstance(card.affliction, GalvanizedAffliction):
            return
        combat = self.hooks.combat
        if combat is None:
            return
        from .cmds import DamageCmd
        from .valueprops import DamageProps
        DamageCmd.deal(
            self.hooks, combat.player, self.amount, props=DamageProps.NON_CARD_UNPOWERED
        )


class SoarPower(Power):
    """The owner takes 50% damage from powered attacks (Owl Magistrate; mirrors
    SoarPower.ModifyDamageMultiplicative). Applied while flying, removed on the
    dive (Verdict)."""

    id = "soar"
    name = "Soar"
    power_type = PowerType.BUFF

    def modify_damage_multiplicative(
        self,
        target: Creature,
        amount: int,
        dealer: Creature | None,
        card: Card | None,
        props: ValueProp = ValueProp.NONE,
    ) -> float:
        if not is_powered_attack(props):   # SoarPower.cs
            return 1.0
        if target is self.owner:
            return 0.5
        return 1.0


class _PossessPower(Power):
    """Base for the Lost/Forgotten possession powers: track the stat the owner
    drains from the player and give it back when the owner dies (mirrors
    PossessStrengthPower / PossessSpeedPower)."""

    _stat_id: str

    def __init__(
        self,
        owner: Creature,
        amount: int,
        hooks: HookSystem,
        applier: Creature | None = None,
    ) -> None:
        super().__init__(owner, amount, hooks, applier)
        self._stolen: dict[Creature, int] = {}

    def _track(self, name: str, target: Creature, delta: int, applier: Creature | None) -> None:
        if (
            applier is self.owner
            and name == self._stat_id
            and target.side == "player"
            and delta < 0
        ):
            self._stolen[target] = self._stolen.get(target, 0) + delta

    def on_power_applied(
        self, name: str, target: Creature, amount: int, applier: Creature | None = None
    ) -> None:
        self._track(name, target, amount, applier)

    def on_power_amount_changed(
        self, name: str, target: Creature, delta: int, applier: Creature | None = None
    ) -> None:
        self._track(name, target, delta, applier)

    def _stat_power(self) -> type[Power]:
        raise NotImplementedError

    def on_death(self, creature: Creature,
                 was_removal_prevented: bool = False) -> None:
        if creature is not self.owner:
            return
        from .cmds import PowerCmd
        for target, amount in self._stolen.items():
            PowerCmd.apply(self.hooks, target, self._stat_power(), -amount)
        self._stolen.clear()
        self._expire()


class PossessStrengthPower(_PossessPower):
    """When the owner dies, all the Strength it drained from the player is
    returned (The Lost; mirrors PossessStrengthPower)."""

    id = "possess_strength"
    name = "Possess Strength"
    power_type = PowerType.BUFF
    _stat_id = "strength"

    def _stat_power(self) -> type[Power]:
        return StrengthPower


class PossessSpeedPower(_PossessPower):
    """When the owner dies, all the Dexterity it drained from the player is
    returned (The Forgotten; mirrors PossessSpeedPower)."""

    id = "possess_speed"
    name = "Possess Speed"
    power_type = PowerType.BUFF
    _stat_id = "dexterity"

    def _stat_power(self) -> type[Power]:
        return DexterityPower


class DampenPower(Power):
    """When applied, downgrades every upgraded card the player owns by one
    level; the upgrades are restored once every caster who applied this
    instance has died (Magi Knight; mirrors DampenPower). StackType.None (not
    Single); a caster re-applying Dampen to an existing instance never reaches
    PowerCmd.Apply at all -- the applier itself dedupes by checking for an
    existing instance first and calling `add_caster` directly instead
    (MagiKnight.DampenMove; mirrored by MagiKnight._dampen in knights.py) --
    so the default additive on_stack is unreachable through the only known
    applier, and Amount is unread elsewhere."""

    id = "dampen"
    name = "Dampen"
    power_type = PowerType.DEBUFF

    def __init__(
        self,
        owner: Creature,
        amount: int,
        hooks: HookSystem,
        applier: Creature | None = None,
    ) -> None:
        super().__init__(owner, amount, hooks, applier)
        self._downgraded: dict[Card, int] = {}
        # DampenPower.cs:15 `casters` HashSet<Creature> -- every creature
        # that has cast Dampen onto this owner while THIS instance has been
        # active, populated through `add_caster` (mirrors the public,
        # non-override `AddCaster`, DampenPower.cs:73-76). The power only
        # expires once the set is empty (see on_death) -- monster/magi_knight/g1.
        self._casters: set[Creature] = set()
        for card in getattr(owner, "all_cards", ()):
            if card.upgrade_level > 0 and card not in self._downgraded:
                self._downgraded[card] = card.upgrade_level
                # DampenPower.cs:35 goes through CardCmd.Downgrade, which
                # refuses while the combat is ending (CardCmd.cs:214).
                from .cmds import CardCmd
                CardCmd.downgrade(hooks, card)

    def add_caster(self, creature: Creature) -> None:
        """DampenPower.cs:73-76 `AddCaster` -- public, not an override, so the
        harness would not otherwise see it called. `MagiKnight.DampenMove`
        calls this for every Dampen cast, whether or not that particular
        application is the one that created the power (MagiKnight.cs:82-92,
        mirrored by `MagiKnight._dampen`)."""
        self._casters.add(creature)

    def on_death(self, creature: Creature,
                 was_removal_prevented: bool = False) -> None:
        # DampenPower.cs:41-56: a `wasRemovalPrevented` death does not touch
        # the caster set at all. Otherwise remove the dying creature from
        # `casters`; only once the set is EMPTY does the power expire
        # (`PowerCmd.Remove(this)`) -- a second live caster keeps the
        # downgrade in place after the first caster dies.
        if was_removal_prevented:
            return
        if creature in self._casters:
            self._casters.discard(creature)
            if not self._casters:
                self._expire()

    def _expire(self) -> None:
        for card, level in self._downgraded.items():
            while card.upgrade_level < level:
                card.upgrade()
        self._downgraded.clear()
        super()._expire()


class HexPower(Power):
    """Afflicts every unafflicted card the player owns with Hexed, making it
    Ethereal for as long as this power lives; removed when the applier dies
    (Spectral Knight; mirrors HexPower). Cards created mid-combat are afflicted
    too.

    The game grants Ethereal through TryModifyKeywordsInCombat; the sim has no
    keyword-modifier hook, so this sets the card's is_ethereal flag directly
    (on per-combat card copies) and restores it when Hex is removed."""

    id = "hex"
    name = "Hex"
    power_type = PowerType.DEBUFF

    def _afflict(self, card: Card) -> None:
        from .afflictions import HexedAffliction
        from .cmds import CardCmd
        if CardCmd.afflict(card, HexedAffliction, self.amount) is not None:
            card._hex_prev_ethereal = card.is_ethereal
            card.is_ethereal = True

    def __init__(
        self,
        owner: Creature,
        amount: int,
        hooks: HookSystem,
        applier: Creature | None = None,
    ) -> None:
        super().__init__(owner, amount, hooks, applier)
        for card in getattr(owner, "all_cards", ()):
            if card.affliction is None:
                self._afflict(card)

    def on_card_entered_combat(self, card: Card) -> None:
        if card.affliction is None:
            self._afflict(card)

    def on_death(self, creature: Creature,
                 was_removal_prevented: bool = False) -> None:
        if creature is self.applier:
            self._expire()

    def _expire(self) -> None:
        from .afflictions import HexedAffliction
        from .cmds import CardCmd
        for card in getattr(self.owner, "all_cards", ()):
            if isinstance(card.affliction, HexedAffliction):
                card.is_ethereal = getattr(card, "_hex_prev_ethereal", False)
                CardCmd.clear_affliction(card)
        super()._expire()


class HighVoltagePower(Power):
    """The owner gains N Strength at the end of its side's turn (Zapbot;
    mirrors HighVoltagePower.AfterSideTurnEnd)."""

    id = "high_voltage"
    name = "High Voltage"
    power_type = PowerType.BUFF

    def on_enemy_side_end(self) -> None:
        if not self.owner.is_dead:
            from .cmds import PowerCmd
            PowerCmd.apply(self.hooks, self.owner, StrengthPower, self.amount)


class WitheringPresencePower(Power):
    """Every N cards the player plays, a Wither status card is added to their
    hand — matched to the Aeonglass's Increasing-Intensity upgrade count
    (mirrors WitheringPresencePower). The display counter starts at N (6).

    InstanceType.Instanced (WitheringPresencePower.cs:26, power_cmd/G5): the
    game creates one instance per opponent (Aeonglass.cs:78-83), each with
    its own counter. A second application here would start its own instance
    too; with one player there is only ever one opponent, so this never
    observably matters today."""

    id = "withering_presence"
    name = "Withering Presence"
    power_type = PowerType.BUFF
    instance_type = PowerInstanceType.INSTANCED

    def __init__(
        self,
        owner: Creature,
        amount: int,
        hooks: HookSystem,
        applier: Creature | None = None,
    ) -> None:
        super().__init__(owner, amount, hooks, applier)
        self._cards_left = amount

    def on_card_played(self, card: Card,
                       is_auto_play: bool = False) -> None:
        combat = self.hooks.combat
        if combat is None:
            return
        self._cards_left -= 1
        if self._cards_left > 0:
            return
        self._cards_left = self.amount
        from .cards import WitherCard
        from .cmds import CardPileCmd
        wither = WitherCard()
        # Fake-upgraded by the Aeonglass's own
        # `_AeonglassWitherListener.on_card_generated_for_combat` (monsters/
        # glory/aeonglass.py), fired from `add_to_hand`'s
        # AfterCardGeneratedForCombat dispatch -- WitheringPresencePower.cs:
        # 55's real Wither is matched only via that hook (the hover-tip at
        # WitheringPresencePower.cs:37 is a separate, preview-only site with
        # no sim analogue here). Not open-coded: the Aeonglass's registered
        # `_AeonglassWitherListener` must still be live for this to fire,
        # exactly as in C#.
        CardPileCmd.add_to_hand(self.hooks, combat.player, wither)


class ChainsOfBindingPower(Power):
    """Afflicts up to N cards the player draws each turn with Bound; only one
    Bound card can be played per turn. Bound afflictions clear at the end of
    the player's turn (the Queen's Puppet Strings; mirrors
    ChainsOfBindingPower)."""

    id = "chains_of_binding"
    name = "Chains of Binding"
    power_type = PowerType.DEBUFF

    def __init__(
        self,
        owner: Creature,
        amount: int,
        hooks: HookSystem,
        applier: Creature | None = None,
    ) -> None:
        super().__init__(owner, amount, hooks, applier)
        self._bound_played = False
        self._afflicted_this_turn = 0

    def on_card_drawn(self, card: Card, from_hand_draw: bool = False) -> None:
        if card.affliction is None and self._afflicted_this_turn < self.amount:
            from .afflictions import BoundAffliction
            from .cmds import CardCmd
            CardCmd.afflict(card, BoundAffliction, self.amount)
            self._afflicted_this_turn += 1

    def should_play_card(self, card: Card, auto_play: bool = False) -> bool:
        from .afflictions import BoundAffliction
        if isinstance(card.affliction, BoundAffliction) and self._bound_played:
            return False
        return True

    def on_card_played(self, card: Card,
                       is_auto_play: bool = False) -> None:
        from .afflictions import BoundAffliction
        if isinstance(card.affliction, BoundAffliction):
            self._bound_played = True

    def on_player_turn_end(self, player: Creature) -> None:
        if player is not self.owner:
            return
        self._bound_played = False
        self._afflicted_this_turn = 0
        from .afflictions import BoundAffliction
        from .cmds import CardCmd
        for card in getattr(self.owner, "all_cards", ()):
            if isinstance(card.affliction, BoundAffliction):
                CardCmd.clear_affliction(card)


class AdaptablePower(Power):
    """The Test Subject cannot truly die while this power is present: a killing
    blow instead makes it untargetable and forces its Respawn move, in which it
    revives at its next form's HP (mirrors AdaptablePower + TestSubject)."""

    id = "adaptable"
    name = "Adaptable"
    power_type = PowerType.BUFF

    def should_stop_combat_from_ending(self) -> bool:
        return True   # AdaptablePower.cs:53-56

    def should_power_be_removed_after_owner_death(self) -> bool:
        return False   # AdaptablePower.cs:67-70

    def __init__(
        self,
        owner: Creature,
        amount: int,
        hooks: HookSystem,
        applier: Creature | None = None,
    ) -> None:
        super().__init__(owner, amount, hooks, applier)
        self.is_reviving = False

    def should_remove_from_combat_after_death(self, creature: Creature) -> bool:
        # AdaptablePower.cs:58-66 — the only death-side predicate the power
        # implements. There is no ShouldDie override, so the Test Subject
        # really dies and is merely kept in the combat. See IllusionPower.
        return creature is not self.owner

    def on_death(self, creature: Creature,
                 was_removal_prevented: bool = False) -> None:
        # AdaptablePower.cs:32-39 — AfterDeath, `!wasRemovalPrevented` arm,
        # owner only: arm the revive and force the boss's dead state.
        if was_removal_prevented or creature is not self.owner:
            return
        self.is_reviving = True
        self.owner.trigger_dead_state()

    def should_allow_hitting(self, target: Creature) -> bool:
        if target is self.owner and self.is_reviving:
            return False
        return True

    def do_revive(self) -> None:
        self.is_reviving = False


class PainfulStabsPower(Power):
    """Each of the owner's powered-attack hits that deals unblocked damage to
    the player shuffles N Wounds into the player's discard (Test Subject phase
    2; mirrors PainfulStabsPower.AfterAttack — N Wounds per hit == amount ×
    hit-count)."""

    id = "painful_stabs"
    name = "Painful Stabs"
    power_type = PowerType.BUFF

    def should_power_be_removed_after_owner_death(self) -> bool:
        return False   # PainfulStabsPower.cs:24-27

    def after_attack(self, dealer: Creature, card: Card | None = None,
                     results: list | None = None) -> None:
        # PainfulStabsPower.cs:34-68 is AfterAttack: it groups the command's
        # results by player receiver, counts that receiver's hits with unblocked
        # damage, and adds Amount * count Wounds once per receiver. Hosting it
        # on AfterDamageReceived put it behind the killing-blow guard.
        if dealer is not self.owner or not results:
            return
        from .cards import WoundCard
        from .cmds import CardPileCmd
        by_receiver: dict[int, tuple] = {}
        for receiver, unblocked in results:
            if receiver.side != "player" or unblocked <= 0:
                continue
            key = id(receiver)
            got = by_receiver.get(key)
            by_receiver[key] = (receiver, (got[1] if got else 0) + 1)
        for receiver, hits in by_receiver.values():
            for _ in range(self.amount * hits):
                CardPileCmd.add_to_discard(self.hooks, receiver, WoundCard())


class NemesisPower(Power):
    """At the end of every other enemy side turn, the owner gains Intangible 1;
    on the turns in between it loses it (Test Subject phase 3; mirrors
    NemesisPower.AfterSideTurnEnd)."""

    id = "nemesis"
    name = "Nemesis"
    power_type = PowerType.BUFF

    def __init__(
        self,
        owner: Creature,
        amount: int,
        hooks: HookSystem,
        applier: Creature | None = None,
    ) -> None:
        super().__init__(owner, amount, hooks, applier)
        self._should_apply = False

    def on_enemy_side_end(self) -> None:
        if self.owner.is_dead:
            return
        self._should_apply = not self._should_apply
        from .cmds import PowerCmd
        if self._should_apply:
            PowerCmd.apply(self.hooks, self.owner, IntangiblePower, 1)
        elif "intangible" in self.owner.powers:
            PowerCmd.remove(self.hooks, self.owner, "intangible")


# ── Colorless card powers ──────────────────────────────────────────────────


class AutomationPower(Power):
    """Every 10 cards drawn, gain N energy (mirrors AutomationPower's
    internal cards-left counter; the counter resets to 10 after firing).

    InstanceType.Instanced (AutomationPower.cs:27, power_cmd/G5): a second
    play starts its own instance with its own fresh cards_left, rather than
    merging into this one's."""

    id = "automation"
    name = "Automation"
    power_type = PowerType.BUFF
    instance_type = PowerInstanceType.INSTANCED
    CARDS_PER_TRIGGER = 10

    def __init__(
        self,
        owner: Creature,
        amount: int,
        hooks: HookSystem,
        applier: Creature | None = None,
    ) -> None:
        super().__init__(owner, amount, hooks, applier)
        self.cards_left = self.CARDS_PER_TRIGGER

    def on_card_drawn(self, card: Card, from_hand_draw: bool = False) -> None:
        from .cmds import EnergyCmd
        self.cards_left -= 1
        if self.cards_left <= 0:
            EnergyCmd.gain(self.hooks, self.owner, self.amount)
            self.cards_left = self.CARDS_PER_TRIGGER


class CalamityPower(Power):
    """After the owner plays an Attack, add N random Attacks from the
    character pool to the hand (with replacement, mirroring CalamityPower's
    CardFactory.GetForCombat call)."""

    id = "calamity"
    name = "Calamity"
    power_type = PowerType.BUFF

    def on_card_played(self, card: Card,
                       is_auto_play: bool = False) -> None:
        from .cards import CardType
        from .cards.pool import random_pool_cards
        from .cmds import CardPileCmd
        if card.card_type != CardType.ATTACK:
            return
        combat = self.hooks.combat
        if combat is None or combat.is_over:
            return
        for new_card in random_pool_cards(
            combat._rng, self.amount, CardType.ATTACK, pool=combat.card_pool
        ):
            CardPileCmd.add_to_hand(self.hooks, combat.player, new_card)


class DarkShacklesPower(TemporaryStrengthPower):
    """Temporary Strength LOSS from Dark Shackles: restored at the end of the
    owner's side turn (the source subclasses TemporaryStrengthPower with
    IsPositive=false, exactly like Mangle)."""

    id = "dark_shackles"
    name = "Dark Shackles"
    power_type = PowerType.DEBUFF
    _sign = -1


class EntropyPower(Power):
    """At the start of each of the owner's turns (after the draw), transform
    N cards from the hand into random cards (mirrors EntropyPower's
    AfterPlayerTurnStart hand selection + CardCmd.TransformToRandom)."""

    id = "entropy"
    name = "Entropy"
    power_type = PowerType.BUFF

    def on_player_turn_started(self, player: Creature) -> None:
        from .cmds import CardCmd, CardSelectCmd
        if player is not self.owner:
            return
        chosen = CardSelectCmd.from_hand(
            self.hooks, player, "transform", count=self.amount
        )
        for card in chosen:
            CardCmd.transform_to_random(self.hooks, player, card)


class RetainHandPower(Power):
    """The owner's hand is not discarded at the end of the turn for N turns
    (Equilibrium / Salvo; mirrors RetainHandPower.ShouldFlush). The stack
    ticks once per round — the game decrements at the player side's end,
    after the flush decision; the sim's equivalent post-flush slot is the
    enemy side's end."""

    id = "retain_hand"
    name = "Retain Hand"
    power_type = PowerType.BUFF

    def should_flush_hand(self) -> bool:
        return False

    def on_enemy_side_end(self) -> None:
        self._tick()


class FastenPower(Power):
    """Block gained from Defend-tagged cards is raised by N (mirrors
    FastenPower.ModifyBlockAdditive gating on CardTag.Defend; unpowered
    block never reaches the additive pipeline)."""

    id = "fasten"
    name = "Fasten"
    power_type = PowerType.BUFF

    def modify_block_additive(
        self, target: Creature, amount: int, card: Card | None,
        props: ValueProp = ValueProp.NONE,
    ) -> int:
        if not is_powered_card_or_monster_move_block(props):   # FastenPower.cs:26
            return 0
        if target is self.owner and card is not None and "defend" in card.tags:
            return self.amount
        return 0


class MayhemPower(Power):
    """At the start of the owner's turn (after the draw), auto-play the top
    N cards of the draw pile (mirrors MayhemPower's
    CardPileCmd.AutoPlayFromDrawPile in the auto pre-play phase)."""

    id = "mayhem"
    name = "Mayhem"
    power_type = PowerType.BUFF

    def after_auto_pre_play_phase_entered(self, player: Creature) -> None:
        # MayhemPower.cs:20 is one call: `CardPileCmd.AutoPlayFromDrawPile(
        # choiceContext, Owner.Player, Amount, CardPilePosition.Top,
        # forceExhaust: false)`, and that verb is TWO-PHASE
        # (CardPileCmd.cs:931-966). The sim interleaved — pick, play, pick,
        # play — so at Mayhem 2 the first card's effect could change which card
        # was played second, where the game commits both picks up front and
        # holds the second in PileType.Play while the first resolves.
        from .cmds import CardPileCmd

        if player is not self.owner:
            return
        CardPileCmd.auto_play_from_draw_pile(
            self.hooks, player, self.amount, position="top",
            force_exhaust=False)


class NostalgiaPower(Power):
    """The first N Attacks or Skills played each turn return to the top of
    the draw pile instead of the discard pile (mirrors NostalgiaPower's
    ModifyCardPlayResultPileTypeAndPosition)."""

    id = "nostalgia"
    name = "Nostalgia"
    power_type = PowerType.BUFF

    def modify_card_play_result_pile(self, card: Card, pile: str) -> str:
        from .cards import CardType
        from .history import CardPlayStartedEntry
        if pile != "discard" or card.card_type not in (
            CardType.ATTACK, CardType.SKILL
        ):
            return pile
        combat = self.hooks.combat
        # NostalgiaPower.cs:31-42 counts `History.CardPlaysStarted`, NOT
        # CardPlaysFinished. The hook runs from CardModel.cs:1922, before this
        # card's own started row is pushed (:1930), so the current play is still
        # not counted against the allowance — but an OUTER play whose OnPlay
        # auto-played this card IS, because its row went in before it called us.
        # Counting finished plays instead sent BOTH cards to the top of the draw
        # pile where the game sends only the outer one.
        started = sum(
            1
            for e in combat.history.of_type(CardPlayStartedEntry, this_turn=True)
            if e.card.card_type in (CardType.ATTACK, CardType.SKILL)
        )
        if started >= self.amount:
            return pile
        return "draw_top"


class PanachePower(Power):
    """Every 5 cards played after this power, deal N unpowered damage to ALL
    enemies; the 5-count resets when it fires and at the end of the turn
    (mirrors PanachePower — the Panache play itself is not counted).

    InstanceType.Instanced (PanachePower.cs:35, power_cmd/G5): a second play
    starts its own instance with its own fresh cards_left, rather than
    merging into this one's."""

    id = "panache"
    name = "Panache"
    power_type = PowerType.BUFF
    instance_type = PowerInstanceType.INSTANCED
    CARDS_PER_TRIGGER = 5

    def __init__(
        self,
        owner: Creature,
        amount: int,
        hooks: HookSystem,
        applier: Creature | None = None,
    ) -> None:
        super().__init__(owner, amount, hooks, applier)
        self.cards_left = self.CARDS_PER_TRIGGER
        # The card play that applied this power fires on_card_played after
        # registration; skip it (mirrors PanachePower's alreadyApplied flag).
        self._already_applied = False

    def on_card_played(self, card: Card,
                       is_auto_play: bool = False) -> None:
        from .cmds import DamageCmd
        from .valueprops import DamageProps
        if not self._already_applied:
            self._already_applied = True
            return
        self.cards_left -= 1
        if self.cards_left > 0:
            return
        self.cards_left = self.CARDS_PER_TRIGGER
        combat = self.hooks.combat
        if combat is None or combat.is_over:
            return
        for enemy in [e for e in combat.enemies if not e.is_gone]:
            DamageCmd.deal(
                self.hooks, enemy, self.amount, dealer=self.owner,
                props=DamageProps.NON_CARD_UNPOWERED,
            )

    def after_player_turn_end(self, player: Creature) -> None:
        if player is self.owner:
            self.cards_left = self.CARDS_PER_TRIGGER


class NoBlockPower(Power):
    """The owner gains NO block from cards for N turns (Panic Button's
    drawback; mirrors NoBlockPower.ModifyBlockMultiplicative returning 0 for
    card-sourced block). Decrements at the end of the enemy side's turn —
    the game uses PowerCmd.Decrement directly, so there is no first-tick
    skip."""

    id = "no_block"
    name = "No Block"
    power_type = PowerType.DEBUFF

    def modify_block_multiplicative(
        self, target: Creature, amount: int, card: Card | None,
        props: ValueProp = ValueProp.NONE,
    ) -> float:
        if ValueProp.UNPOWERED in props:   # NoBlockPower.cs:36-39
            return 1.0
        if target is self.owner and card is not None:
            return 0.0
        return 1.0

    def on_enemy_side_end(self) -> None:
        self._tick()


class PrepTimePower(Power):
    """At the start of each of the owner's turns, gain N Vigor (mirrors
    PrepTimePower.AfterSideTurnStart)."""

    id = "prep_time"
    name = "Prep Time"
    power_type = PowerType.BUFF

    def after_side_turn_start(self, player: Creature) -> None:
        from .cmds import PowerCmd
        if player is self.owner:
            PowerCmd.apply(self.hooks, self.owner, VigorPower, self.amount)


class RollingBoulderPower(Power):
    """At the start of each of the owner's turns, deal N unpowered damage to
    ALL enemies, then N grows by 5 (mirrors RollingBoulderPower's
    AfterPlayerTurnStart damage + SetAmount).

    InstanceType.Instanced (RollingBoulderPower.cs:24, power_cmd/G5): a
    second play starts its own instance with its own growing amount, rather
    than merging into this one's."""

    id = "rolling_boulder"
    name = "Rolling Boulder"
    power_type = PowerType.BUFF
    instance_type = PowerInstanceType.INSTANCED
    INCREMENT = 5

    def on_player_turn_started(self, player: Creature) -> None:
        from .cmds import DamageCmd
        from .valueprops import DamageProps
        if player is not self.owner:
            return
        combat = self.hooks.combat
        if combat is None or combat.is_over:
            return
        for enemy in [e for e in combat.enemies if not e.is_gone]:
            DamageCmd.deal(
                self.hooks, enemy, self.amount, dealer=self.owner,
                props=DamageProps.NON_CARD_UNPOWERED,
            )
        if combat._all_enemies_dead() and not combat.is_over:
            combat._end_combat(player_won=True)
        self.amount += self.INCREMENT
        self.hooks.on_power_amount_changed(self.id, self.owner, self.INCREMENT)


class StratagemPower(Power):
    """Whenever the discard pile is shuffled into the draw pile, choose N
    cards from the draw pile and put them into the hand (mirrors
    StratagemPower.AfterShuffle)."""

    id = "stratagem"
    name = "Stratagem"
    power_type = PowerType.BUFF

    def on_shuffle(self, player: Creature) -> None:
        from .cmds import CardSelectCmd
        chosen = CardSelectCmd.from_pile(
            self.hooks, player.draw_pile, "from_draw", count=self.amount
        )
        for card in chosen:
            if len(player.hand) >= player.MAX_HAND_SIZE:
                break
            player.draw_pile.remove(card)
            player.hand.append(card)


class TheBombPower(Power):
    """After N turns, deal the stored damage to ALL enemies (mirrors
    TheBombPower). The game instances the power (PowerInstanceType.Instanced)
    so several bombs tick independently; the sim keeps a list of
    (turns_left, damage) fuses inside one power, with `amount` showing the
    shortest fuse.

    NOT switched to `instance_type = PowerInstanceType.INSTANCED`
    (power_cmd/G5): that dispatch skips `on_stack` entirely on a second
    application, which is exactly the method this class's own bombs-list
    already uses to reproduce independent-fuse damage correctly (below).
    Routing it through the generic path would silence `on_stack` and lose
    that workaround for no gain — the per-instance STATE that workaround
    doesn't reproduce (one power_list entry where the game has two) is a
    full_env.py observation-encoding limit the generic path doesn't fix
    either, since it also only ever exposes the newest instance."""

    id = "the_bomb"
    name = "The Bomb"
    power_type = PowerType.BUFF
    DEFAULT_DAMAGE = 40

    def __init__(
        self,
        owner: Creature,
        amount: int,
        hooks: HookSystem,
        applier: Creature | None = None,
    ) -> None:
        super().__init__(owner, amount, hooks, applier)
        self.bombs: list[list[int]] = [[amount, self.DEFAULT_DAMAGE]]

    def on_stack(self, amount: int) -> None:
        self.bombs.append([amount, self.DEFAULT_DAMAGE])
        self.amount = min(turns for turns, _ in self.bombs)

    def set_damage(self, damage: int) -> None:
        """Set the newest bomb's damage (mirrors TheBombPower.SetDamage; the
        card calls this right after applying the power)."""
        self.bombs[-1][1] = damage

    def on_player_turn_end(self, player: Creature) -> None:
        from .cmds import DamageCmd
        from .valueprops import DamageProps
        if player is not self.owner:
            return
        combat = self.hooks.combat
        exploding = [b for b in self.bombs if b[0] <= 1]
        self.bombs = [b for b in self.bombs if b[0] > 1]
        for bomb in self.bombs:
            bomb[0] -= 1
        for _, damage in exploding:
            if combat is None or combat.is_over:
                break
            for enemy in [e for e in combat.enemies if not e.is_gone]:
                DamageCmd.deal(
                    self.hooks, enemy, damage, dealer=self.owner,
                    props=DamageProps.NON_CARD_UNPOWERED,
                )
            if combat._all_enemies_dead() and not combat.is_over:
                combat._end_combat(player_won=True)
        if not self.bombs:
            self._expire()
        else:
            self.amount = min(turns for turns, _ in self.bombs)


class TheGambitPower(Power):
    """If the owner takes unblocked attack damage, they die (The Gambit's
    drawback; mirrors TheGambitPower.AfterDamageReceived). StackType.Single
    only hides the Amount display; Amount still accumulates on
    re-application, but nothing reads it here."""

    id = "the_gambit"
    name = "The Gambit"
    power_type = PowerType.DEBUFF

    def on_damage_received(
        self,
        target: Creature,
        amount: int,
        dealer: Creature | None = None,
        card: Card | None = None,
        props: ValueProp = ValueProp.NONE,
    ) -> None:
        from .cmds import CreatureCmd
        from .valueprops import is_powered_attack
        if target is not self.owner or amount <= 0 or not is_powered_attack(props):
            return
        self._expire()
        CreatureCmd.kill(self.hooks, self.owner)


class BlockNextTurnPower(Power):
    """When the owner's block is next cleared, regain N block (unpowered)
    and remove this power (Prolong; mirrors BlockNextTurnPower's
    AfterBlockCleared)."""

    id = "block_next_turn"
    name = "Blocked Off"
    power_type = PowerType.BUFF

    def on_block_cleared(self, target: Creature) -> None:
        from .cmds import BlockCmd
        if target is not self.owner:
            return
        self._expire()
        BlockCmd.apply(
            self.hooks, self.owner, self.amount, props=ValueProp.UNPOWERED
        )


class ConfusedPower(Power):
    """Whenever the owner draws a card, that card's cost becomes a random
    0-3 for the rest of the combat. StackType.Single only hides the Amount
    display; Amount still accumulates on re-application, but nothing reads
    it here.

    Source: ConfusedPower.cs — AfterCardDrawn sets EnergyCost.SetThisCombat
    (NextInt(4)), skipping X-cost cards (EnergyCost.Canonical < 0). Applied
    by Snecko Eye at the start of every combat.

    The draw is NAMED: NextEnergyCost (ConfusedPower.cs:47-54) ends in
    `base.Owner.Player.RunState.Rng.CombatEnergyCosts.NextInt(4)`, which is
    `combat_rng.energy` here — the shared legacy Random in RL mode and the
    CombatEnergyCosts stream in a parity run (relic/_off_stream_draw).
    """

    id = "confused"
    name = "Confused"
    power_type = PowerType.DEBUFF

    def on_card_drawn(self, card: Card, from_hand_draw: bool = False) -> None:
        if card.energy_cost_x:      # EnergyCost.Canonical < 0
            return
        combat = self.hooks.combat
        if combat is None:
            return
        card.set_cost_this_combat(combat.combat_rng.energy.randrange(4))


# ── Potion powers ────────────────────────────────────────────────────────
# Powers whose only source is a potion (Models/Powers/*.cs, applied from
# Models/Potions/*.cs).


class ClarityPower(Power):
    """Draw 1 extra card at the start of each of the owner's next N turns
    (Clarity).

    Source: ClarityPower.cs — ModifyHandDraw returns count + 1 (flat, NOT the
    stack count) and AfterSideTurnStart decrements. The game's side-turn-start
    hook runs *after* SetupPlayerTurn's draw (CombatManager.cs:522 vs :654), so
    the sim's post-draw slot (on_player_turn_started) is the matching one.
    """

    id = "clarity"
    name = "Clarity"
    power_type = PowerType.BUFF

    def modify_hand_draw(self, player: Creature, count: int) -> int:
        if player is not self.owner:
            return count
        return count + 1

    def after_side_turn_start(self, player: Creature) -> None:
        if player is self.owner:
            self._tick()


class DuplicationPower(Power):
    """The owner's next N card plays happen twice (Duplicator).

    Source: DuplicationPower.cs — ModifyCardPlayCount + 1 with
    AfterModifyingCardPlayCount decrementing, then AfterSideTurnEnd removes
    whatever is left. The game fires the after-hook immediately after the
    modifier chain and before the plays resolve, so consuming the stack inside
    the modifier is exact.
    """

    id = "duplication"
    name = "Duplication"
    power_type = PowerType.BUFF

    def modify_card_play_count(
        self, card: Card, target: Creature | None, count: int
    ) -> int:
        # `card.Owner.Creature != Owner` — every card in the sim belongs to the
        # player, so the check reduces to the owner being the player.
        combat = self.hooks.combat
        if combat is None or self.owner is not combat.player:
            return count
        self._tick()
        return count + 1

    def after_player_turn_end(self, player: Creature) -> None:
        if player is self.owner:
            self._expire()


class GigantificationPower(Power):
    """The owner's next Attack card deals TRIPLE damage (Gigantification
    Potion).

    Source: GigantificationPower.cs — BeforeAttack latches the first powered
    Attack-card command, ModifyDamageMultiplicative returns 3 for it (and for
    any powered card attack while nothing is latched, which is what makes the
    card's damage preview read triple), AfterAttack clears the latch and
    decrements.
    """

    id = "gigantification"
    name = "Gigantification"
    power_type = PowerType.BUFF
    MULTIPLIER = 3

    def __init__(
        self,
        owner: Creature,
        amount: int,
        hooks: HookSystem,
        applier: Creature | None = None,
    ) -> None:
        super().__init__(owner, amount, hooks, applier)
        self._card_to_modify: Card | None = None

    def before_attack(self, dealer: Creature, card: Card | None = None) -> None:
        from .cards import CardType
        if dealer is not self.owner or self._card_to_modify is not None:
            return
        if card is None or card.card_type != CardType.ATTACK or card.is_unpowered:
            return
        self._card_to_modify = card

    def modify_damage_multiplicative(
        self,
        target: Creature,
        amount: int,
        dealer: Creature | None = None,
        card: Card | None = None,
        props: ValueProp = ValueProp.NONE,
    ) -> float:
        if not is_powered_attack(props):   # GigantificationPower.cs
            return 1.0
        # `cardSource == null` / wrong owner → no multiplier. Unpowered damage
        # never reaches this hook in the sim (DamageCmd gates it), matching the
        # source's IsPoweredAttack guard.
        if card is None or dealer is not self.owner:
            return 1.0
        if self._card_to_modify is None or card is self._card_to_modify:
            return float(self.MULTIPLIER)
        return 1.0

    def after_attack(self, dealer: Creature, card: Card | None = None,
                     results: list | None = None) -> None:
        if card is not None and card is self._card_to_modify:
            self._card_to_modify = None
            self._tick()


class BufferPower(Power):
    """Prevent the next N instances of HP loss (Lucky Tonic).

    Source: BufferPower.cs — ModifyHpLostAfterOstyLate returns 0 for the owner
    and AfterModifyingHpLostAfterOsty decrements. Only listeners that actually
    changed the amount are notified, so a hit fully absorbed by block leaves
    the stack alone.
    """

    id = "buffer"
    name = "Buffer"
    power_type = PowerType.BUFF

    def modify_hp_lost_late(
        # BufferPower.cs:20 is ModifyHpLostAfterOstyLate, and its own
        # source comment is the record's proof that the Late pass is
        # load-bearing: other listeners may reduce the amount to 0 first.
        self,
        target: Creature,
        amount: int,
        dealer: Creature | None = None,
        card: Card | None = None,
    ) -> int:
        if target is not self.owner:
            return amount
        return 0

    def after_modify_hp_lost(self, target: Creature) -> None:
        self._tick()


class RadiancePower(Power):
    """Gain 1 energy at the start of each of the owner's next N turns
    (Radiant Tincture).

    Source: RadiancePower.cs — AfterEnergyReset gains EnergyVar(1) and
    decrements.
    """

    id = "radiance"
    name = "Radiance"
    power_type = PowerType.BUFF
    ENERGY = 1

    def on_energy_reset(self, player: Creature) -> None:
        if player is not self.owner:
            return
        from .cmds import EnergyCmd
        EnergyCmd.gain(self.hooks, self.owner, self.ENERGY)
        self._tick()


class DemisePower(Power):
    """At the end of the owner's side turn it loses N HP (Powdered Demise).

    Source: DemisePower.cs — AfterSideTurnEnd damages the owner for Amount
    (Unblockable | Unpowered) with no dealer. The stack never decrements, so
    the damage repeats every turn.
    """

    id = "demise"
    name = "Demise"
    power_type = PowerType.DEBUFF

    def _fire(self) -> None:
        from .cmds import DamageCmd
        from .valueprops import DamageProps
        DamageCmd.deal(
            self.hooks, self.owner, self.amount, props=DamageProps.NON_CARD_HP_LOSS
        )

    def after_player_turn_end(self, player: Creature) -> None:
        if player is self.owner:
            self._fire()

    def on_enemy_side_end(self) -> None:
        if self.owner.side == "enemy":
            self._fire()


class ShacklingPotionPower(TemporaryStrengthPower):
    """Temporary Strength LOSS from the Shackling Potion: restored at the end
    of the owner's side turn (the source subclasses TemporaryStrengthPower with
    IsPositive=false, exactly like Dark Shackles)."""

    id = "shackling_potion"
    name = "Shackling Potion"
    power_type = PowerType.DEBUFF
    _sign = -1


# ── Registry ─────────────────────────────────────────────────────────────

ALL_POWERS: dict[str, type[Power]] = {
    cls.id: cls
    for cls in [
        StrengthPower,
        DexterityPower,
        BarricadePower,
        RegenPower,
        RitualPower,
        DemonFormPower,
        FeelNoPainPower,
        DarkEmbracePower,
        EnragePower,
        RupturePower,
        CurlUpPower,
        ArtifactPower,
        ThornsPower,
        IntangiblePower,
        AggressionPower,
        NoDrawPower,
        NoEnergyGainPower,
        ColossusPower,
        CorruptionPower,
        CrimsonMantlePower,
        CrueltyPower,
        FlameBarrierPower,
        ToricToughnessPower,
        HellraiserPower,
        InfernoPower,
        JuggernautPower,
        JugglingPower,
        SetupStrikePower,
        ManglePower,
        ReptileTrinketPower,
        OneTwoPunchPower,
        PyrePower,
        RagePower,
        StampedePower,
        PlatingPower,
        UnmovablePower,
        FreeAttackPower,
        ViciousPower,
        VulnerablePower,
        WeakPower,
        FrailPower,
        PoisonPower,
        SlowPower,
        TerritorialPower,
        PlowPower,
        RingingPower,
        ShrinkPower,
        InfestedPower,
        ConstrictPower,
        TangledPower,
        SlipperyPower,
        MinionPower,
        IllusionPower,
        RavenousPower,
        SuckPower,
        SurprisePower,
        SmoggyPower,
        SkittishPower,
        AsleepPower,
        VigorPower,
        ShriekPower,
        HardenedShellPower,
        SteamEruptionPower,
        ImbalancedPower,
        HardToKillPower,
        TenderPower,
        HatchPower,
        SlumberPower,
        EscapeArtistPower,
        FlutterPower,
        SwipePower,
        BurrowedPower,
        ReattachPower,
        PersonalHivePower,
        VitalSparkPower,
        TaintedPower,
        BackAttackLeftPower,
        BackAttackRightPower,
        CrabRagePower,
        SurroundedPower,
        SandpitPower,
        DisintegrationPower,
        MindRotPower,
        SlothPower,
        WasteAwayPower,
        FeedingFrenzyPower,
        DiamondDiademPower,
        DrawCardsNextTurnPower,
        EnergyNextTurnPower,
        ReboundPower,
        HelloWorldPower,
        StranglePower,
        CuriousPower,
        ImprovementPower,
        BattlewornDummyTimeLimitPower,
        PaperCutsPower,
        StockPower,
        RampartPower,
        GalvanicPower,
        SoarPower,
        PossessStrengthPower,
        PossessSpeedPower,
        DampenPower,
        HexPower,
        HighVoltagePower,
        WitheringPresencePower,
        ChainsOfBindingPower,
        AdaptablePower,
        PainfulStabsPower,
        NemesisPower,
        ThieveryPower,
        HeistPower,
        # Colorless card powers
        AutomationPower,
        CalamityPower,
        DarkShacklesPower,
        EntropyPower,
        RetainHandPower,
        FastenPower,
        MayhemPower,
        NostalgiaPower,
        PanachePower,
        NoBlockPower,
        PrepTimePower,
        RollingBoulderPower,
        StratagemPower,
        TheBombPower,
        TheGambitPower,
        BlockNextTurnPower,
        ConfusedPower,
        # Potion powers
        ClarityPower,
        DuplicationPower,
        GigantificationPower,
        BufferPower,
        RadiancePower,
        DemisePower,
        ShacklingPotionPower,
        FlexPotionPower,
        SpeedPotionPower,
    ]
}
