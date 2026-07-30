"""Command layer — the verbs that mutate combat state, mirroring STS2's Cmd
classes (DamageCmd, CreatureCmd, PowerCmd, ...).

All effects go through a Cmd rather than touching hp/block/powers directly;
that is what keeps hook dispatch correct. The centrepiece is
`DamageCmd.deal`, the full typed damage pipeline (powered modifiers → cap →
on_attacked → block → modify_hp_lost → apply → death check → post-damage
events). Other Cmds cover block, healing/kill/stun/escape/add, applying and
removing powers, strength, drawing, exhausting, afflicting cards, moving
generated cards between piles, in-combat card selection, and energy gain.

Each Cmd is a namespace of @staticmethods taking the `HookSystem` (and usually
a target) explicitly — there is no Cmd instance state.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from .valueprops import DamageProps, ValueProp, is_powered_attack

if TYPE_CHECKING:
    from .afflictions import Affliction
    from .cards import Card
    from .creatures import Creature
    from .hooks import HookSystem
    from .player import PlayerCombatState
    from .powers import Power, PowerType


def is_over_or_ending(hooks: HookSystem) -> bool:
    """`CombatManager.Instance.IsOverOrEnding` as a command sees it.

    Nearly every command in the CreatureCmd / CardCmd / CardPileCmd / PowerCmd
    seams opens with one of these two predicates and returns an empty, zero or
    no-op result. The window they guard is real and not the same as "the combat
    object is gone": `IsEnding` goes true the moment the last primary enemy
    dies, which is BEFORE `CheckWinCondition` tears the fight down, so the
    killing blow's own card is still resolving inside it.

    Out of combat there is nothing to guard: C# would answer `!IsInProgress` ==
    true, but every guard that consults it is additionally qualified by "the
    pile is a combat pile" or is only reachable in combat, so `False` here and
    an explicit pile test at the one asymmetric site (`CardCmd.afflict`) is the
    faithful pair.
    """
    # `getattr` on the property too: `hooks.combat` is duck-typed and the
    # event room-entry layout hangs a cut-down stand-in there (a stream bundle
    # with no creatures) purely to roll monster HP. That object is not a combat
    # in progress in any sense, so nothing about it is ending.
    return getattr(getattr(hooks, "combat", None), "is_over_or_ending", False)


def is_ending(hooks: HookSystem) -> bool:
    """`CombatManager.Instance.IsEnding` — the narrower of the two.

    PowerCmd.Apply/ModifyAmount, CardCmd.Transform and CardPileCmd.Add use this
    one, and the difference is deliberate: `IsEnding` opens with
    `if (!IsInProgress) return false` (CombatManager.cs:184-187), so these
    commands still work out of combat. That is what keeps the deck transformers
    and the event card-adds alive.
    """
    return getattr(getattr(hooks, "combat", None), "is_ending", False)


def can_receive_powers(hooks: HookSystem, target: Creature) -> bool:
    """`Creature.CanReceivePowers` (Creature.cs:308-322), both clauses.

    `CombatState == null` (the corpse was REMOVED) OR a listener refusing
    `Hook.ShouldAllowHitting`. Note what is NOT here: `IsDead`. The property's
    doc comment spells the difference out against `IsHittable` — "a creature is
    not hittable if it's dead, but dead creatures can still have powers applied
    to them" — which is why a removal-vetoed corpse keeps taking debuffs.
    """
    return (not target.is_removed_from_combat
            and hooks.should_allow_hitting(target))


def should_trigger_fatal(target: Creature) -> bool:
    """`cardPlay.Target.Powers.All(p => p.ShouldOwnerDeathTriggerFatal())`,
    the test Feed.cs:38 and HandOfGreed.cs:49 both take BEFORE their attack.

    `PowerModel.ShouldOwnerDeathTriggerFatal` defaults to true
    (PowerModel.cs:646) and exactly two non-mock powers override it, both
    ported: MinionPower unconditionally (MinionPower.cs:20-23) and
    ReattachPower unless every other segment is already down
    (ReattachPower.cs:106-109). This is NOT death prevention -- the creature
    really dies; only the Fatal payout is suppressed -- which is why the
    `is_dead` check the two cards already had does not cover it.
    """
    return all(p.should_owner_death_trigger_fatal()
               for p in target.powers.values())


def is_hittable(hooks: HookSystem, target: Creature) -> bool:
    """`Creature.IsHittable` (Creature.cs:285-299) — `!IsDead &&
    Hook.ShouldAllowHitting`. The stricter of the pair: this one DOES exclude a
    corpse, which is what makes `CombatState.HittableEnemies` (CombatState.cs:142)
    a smaller set than "the enemies still in the fight"."""
    return not target.is_gone and hooks.should_allow_hitting(target)


def _resolve_death(hooks: HookSystem, target: Creature) -> None:
    """CreatureCmd.KillWithoutCheckingWinCondition's two arms
    (CreatureCmd.cs:504-570), shared by every path that can bring a creature to
    0 HP.

    Both arms dispatch `Hook.AfterDeath` — the real one with
    `wasRemovalPrevented: false` (CreatureCmd.cs:519), the prevented one with
    `true` (CreatureCmd.cs:566) — and neither floors the creature's HP. The
    prevented creature is left DEAD AT 0 and the preventer is expected to heal
    it; C# then re-kills it if nobody did.
    """
    preventer: list = []
    if hooks.should_die(target, preventer):
        # CreatureCmd.cs:508 — the death stands; a listener may still keep the
        # corpse in the combat rather than removing it (Decimillipede's
        # ReattachPower).
        target.retained_after_death = (
            not hooks.should_remove_from_combat_after_death(target)
        )
        hooks.on_death(target, False)
        _strip_powers_after_death(hooks, target)
    else:
        # CreatureCmd.cs:565-570. The creature stays at 0 HP: `AfterDeath`
        # fires with wasRemovalPrevented=True, then the preventer is notified
        # so a healing one (Fairy in a Bottle) can top it up. The sim used to
        # floor it at 1 HP here, which is the HP number conformance asserts on
        # and the reason Feed never scored a kill on the Test Subject.
        #
        # The else-arm contains no removal logic at all, so a creature whose
        # death is prevented always stays in the fight: dead at 0 HP and still
        # taking its turns, which is how Illusion's and Adaptable's revive
        # moves get to run. Same shape as a withered Decimillipede segment.
        target.retained_after_death = True
        hooks.on_death(target, True)
        hooks.after_preventing_death(preventer, target)


def _strip_powers_after_death(hooks: HookSystem, target: Creature) -> None:
    """Creature.RemoveAllPowersAfterDeath (Creature.cs:668-671) + the
    `AfterRemoved` tail CreatureCmd.cs:533-537 awaits for each stripped power.

    Strip is the DEFAULT: `PowerModel.ShouldPowerBeRemovedAfterOwnerDeath`
    returns true (PowerModel.cs:637-640) and only six non-mock powers override
    it, while `Hook.ShouldPowerBeRemovedOnDeath` has exactly one implementer in
    the whole game (IllusionPower.cs:59-66). Escape strips silently and takes a
    different path — this is the death arm only.
    """
    doomed = [p for p in list(target.powers.values())
              if p.should_power_be_removed_after_owner_death()
              and hooks.should_power_be_removed_on_death(p)]
    for power in doomed:
        power._expire()
    for power in doomed:
        power.on_removed(target)


class DamageResult:
    """`DamageResult` (DamageResult.cs) as the two cards that read one need it.

    `TotalDamage` is `BlockedDamage + UnblockedDamage` (:63-64) and
    `OverkillDamage` is the excess beyond the target's HP, so
    `TotalDamage + OverkillDamage` -- the quantity Fisticuffs and Omnislice
    both sum -- is the ENTIRE post-modifier damage the attack put out.

    `DamageCmd.deal`'s int return is `hp_lost`, which is the post-block,
    post-`modify_hp_lost` amount and is never clamped to the target's HP, so it
    already equals `UnblockedDamage + OverkillDamage`. The only missing term
    was the BLOCKED one, and that is what this object carries back.
    """

    __slots__ = ("blocked_damage", "hp_lost")

    def __init__(self) -> None:
        self.blocked_damage = 0
        self.hp_lost = 0

    @property
    def total_plus_overkill(self) -> int:
        """`r.TotalDamage + r.OverkillDamage`."""
        return self.blocked_damage + self.hp_lost


class DamageCmd:
    @staticmethod
    def deal(
        hooks: HookSystem,
        target: Creature,
        amount: int,
        dealer: Creature | None = None,
        card: Card | None = None,
        props: ValueProp | None = None,
        result: "DamageResult | None" = None,
    ) -> int:
        """Full damage pipeline. Returns actual HP lost (after block and modifiers).

        props types the damage (mirrors STS2 ValueProp). When omitted it is
        inferred: card/monster attack damage (MOVE), downgraded to unpowered
        for cards marked is_unpowered.
        """
        if props is None:
            if card is not None and card.is_unpowered:
                props = DamageProps.CARD_UNPOWERED
            else:
                props = DamageProps.CARD  # == MONSTER_MOVE
        # CreatureCmd.cs:242-245, the FIRST statement of CreatureCmd.Damage:
        # a dead dealer deals nothing — the call returns an empty DamageResult
        # per target rather than running the pipeline. Reachable now that
        # ThornsPower names its dealer: a multi-hit attacker killed by the
        # first hit's reflect must not land the rest of the attack.
        if dealer is not None and dealer.is_dead:
            return 0
        if not hooks.should_allow_hitting(target):
            return 0

        # 1. The source card's own enchantment first, then the listener passes.
        #    Hook.ModifyDamage (Hook.cs:1487-1499) folds EnchantDamageAdditive
        #    and then EnchantDamageMultiplicative into the running amount
        #    BEFORE either listener loop, so a Corrupted Strike (base 6) with
        #    Strength 3 is 6*1.5 = 9 then +3 = 12, not 6+3 = 9 then *1.5 = 13.
        ench = card.enchantment if card is not None else None
        if ench is not None:
            amount += ench.enchant_damage_additive(amount, props)
            amount *= ench.enchant_damage_multiplicative(amount, props)

        # 2. Additive then multiplicative modifiers (Strength, Vulnerable, Weak).
        #    EVERY listener is called for EVERY damage: ModifyDamageInternal
        #    (Hook.cs:2515-2538) has no props gate and leaves the
        #    IsPoweredAttack test to each implementation. Hoisting it here
        #    silently dropped the listeners that deliberately do NOT gate on
        #    Unpowered — Vambrace.cs:59-63, PaelsLegion.cs:132-134 and
        #    UnmovablePower.cs:27-30 all self-gate on Move ALONE.
        dmg_modifiers: list = []
        amount = hooks.modify_damage_additive(
            target, amount, dealer, card, dmg_modifiers, props)
        amount = int(hooks.modify_damage_multiplicative(
            target, amount, dealer, card, dmg_modifiers, props))
        if dmg_modifiers:
            hooks.after_modify_damage_amount(dmg_modifiers, target)

        # 3. Damage cap (e.g. Intangible: cap at 1) — applies to all damage types
        cap = hooks.modify_damage_cap(target, dealer, card)
        if cap is not None:
            amount = min(amount, cap)

        amount = max(0, amount)

        # 4. Pre-block hit event for attacks (e.g. CurlUp triggers even when
        #    block absorbs). Non-move damage (Poison, Thorns) is not a "hit".
        if amount > 0 and ValueProp.MOVE in props:
            hooks.on_attacked(target, amount, dealer, card)

        # 4b. Hook.BeforeDamageReceived (CreatureCmd.cs:263) — after the
        #     modifier passes, before block absorption, and NOT subject to the
        #     killing-blow skip. Thorns reflects from here.
        hooks.before_damage_received(target, amount, dealer, card, props)

        # 5. Block absorption (skipped for unblockable HP loss like Poison)
        hp_lost = amount
        if target.block > 0 and ValueProp.UNBLOCKABLE not in props:
            absorbed = min(target.block, amount)
            target.block -= absorbed
            hp_lost -= absorbed
            if result is not None:
                result.blocked_damage = absorbed   # DamageResult.BlockedDamage
            # WasBlockBroken (CreatureCmd.cs): Block <= 0 && blockedDamage > 0
            # — an exact break counts; overflow damage is not required.
            if target.block == 0:
                hooks.on_block_broken(target, dealer, card)

        # 6. HP-loss modifiers applied after block (e.g. Torii: cap at 1, Tungsten Rod: -1)
        if hp_lost > 0:
            modifiers: list = []
            hp_lost = hooks.modify_hp_lost(target, hp_lost, dealer, card, modifiers)
            hooks.after_modify_hp_lost(modifiers, target)
        if result is not None:
            result.hp_lost = hp_lost

        # 7. Apply HP loss
        if hp_lost > 0:
            old_hp = target.hp
            target.hp = max(0, target.hp - hp_lost)
            hooks.on_hp_changed(target, target.hp - old_hp)

            # 8. Death check — listeners can prevent death (e.g. Fairy in a Bottle)
            if target.hp <= 0:
                _resolve_death(hooks, target)

        # 9. Post-damage events. A killing blow skips the victim's
        #    AfterDamageReceived (CreatureCmd.cs:392 — `!WasTargetKilled ||
        #    !IsDead`): the hit that kills a creature does not trigger its
        #    on-damage-received powers (e.g. PersonalHive shuffles no Dazed on
        #    the hit that kills its owner). AfterDamageGiven (on_damage_dealt)
        #    is not guarded and still fires on the kill.
        if not target.is_dead:
            hooks.on_damage_received(target, hp_lost, dealer, card, props)
        if dealer is not None and hp_lost > 0:
            hooks.on_damage_dealt(dealer, target, hp_lost, card)

        # AttackCommand.Results: every hit of the attack currently bracketed by
        # before_attack / after_attack, for the listeners that read them
        # (SuckPower.cs:28-41, PainfulStabsPower.cs:40-44).
        if hooks._attack_results is not None:
            hooks._attack_results.append((target, hp_lost))

        return hp_lost


class BlockCmd:
    @staticmethod
    def apply(
        hooks: HookSystem,
        target: Creature,
        amount: int,
        card: Card | None = None,
        props: ValueProp | None = None,
    ) -> int:
        """Apply block through the hook pipeline. Returns final block gained.

        `Hook.ModifyBlock` (Hook.cs:1310-1340) calls every listener for every
        block gain and lets each self-gate on props; Dexterity, Frail and
        Fasten do, while Vambrace, Pael's Legion and Unmovable deliberately
        gate on Move ALONE and so must still run for Unpowered block.
        """
        # CreatureCmd.cs:637-640 — the whole command is skipped once the combat
        # is over or ending, hooks and all.
        if is_over_or_ending(hooks):
            return 0
        if props is None:
            props = ValueProp.MOVE
        # The source card's own enchantment folds in before either listener
        # loop (Hook.cs:1315-1320), like the damage side.
        ench = card.enchantment if card is not None else None
        if ench is not None:
            amount += ench.enchant_block_additive(amount, props)
            amount *= ench.enchant_block_multiplicative(amount, props)
        blk_modifiers: list = []
        amount = hooks.modify_block_additive(
            target, amount, card, blk_modifiers, props)
        amount = int(hooks.modify_block_multiplicative(
            target, amount, card, blk_modifiers, props))
        amount = max(0, amount)
        # CreatureCmd.cs:644-646 — Max(modifiedAmount, 0) and then
        # Hook.AfterModifyingBlockAmount, BOTH before the `if (modifiedAmount
        # > 0m)` block that calls GainBlockInternal (:647-651). The dispatch
        # is unconditional; it is the LISTENERS that open on `<= 0`.
        if blk_modifiers:
            hooks.after_modify_block_amount(blk_modifiers, target, amount, card)
        target.block += amount
        hooks.on_block_gained(target, amount, card)
        return amount


class CreatureCmd:
    """Creature-level verbs beyond plain damage (mirrors STS2's CreatureCmd)."""

    @staticmethod
    def heal(hooks: HookSystem, target: Creature, amount: int) -> int:
        """Heal up to amount HP, capped at max HP. Returns HP actually restored.

        `CreatureCmd.Heal` (CreatureCmd.cs:691-697) has NO dead-creature guard
        — its only early return is `IsEnding && !IsPlayer`. The sim's old
        `if target.is_dead: return 0` was safe only while a prevented death was
        floored at 1 HP; now that the corpse is left at 0 (CreatureCmd.cs:565),
        that guard would block the very revives it exists for — Illusion's
        REVIVE move and Adaptable's respawn both heal a creature that is dead
        at 0 and retained in combat.
        """
        combat = getattr(hooks, "combat", None)
        if (combat is not None and getattr(combat, "is_over", False)
                and target.side != "player"):
            return 0
        healed = min(amount, target.max_hp - target.hp)
        if healed > 0:
            target.hp += healed
            hooks.on_hp_changed(target, healed)
        return healed

    @staticmethod
    def gain_max_hp(hooks: HookSystem, target: Creature, amount: int) -> None:
        """Raise max HP, then heal the same amount (mirrors
        CreatureCmd.GainMaxHp: SetMaxHp followed by Heal). Used by Fruit
        Juice; RunState.gain_max_hp is the out-of-combat twin."""
        if amount <= 0:
            return
        target.max_hp += amount
        CreatureCmd.heal(hooks, target, amount)

    @staticmethod
    def lose_max_hp(hooks: HookSystem, target: Creature, amount: int) -> None:
        """Reduce max HP by amount, clamping current HP down to it (mirrors
        CreatureCmd.LoseMaxHp: both max and current HP drop). Max HP floors at
        1. Used by Paper Cuts (Scroll of Biting)."""
        if amount <= 0:
            return
        target.max_hp = max(1, target.max_hp - amount)
        if target.hp > target.max_hp:
            old_hp = target.hp
            target.hp = target.max_hp
            hooks.on_hp_changed(target, target.hp - old_hp)

    @staticmethod
    def kill(hooks: HookSystem, target: Creature) -> None:
        """Set HP to 0 through the death-prevention pipeline (mirrors Kill)."""
        if target.is_dead:
            return
        old_hp = target.hp
        target.hp = 0
        hooks.on_hp_changed(target, -old_hp)
        _resolve_death(hooks, target)

    @staticmethod
    def stun(hooks: HookSystem, target: Creature, next_move_key: str | None = None) -> None:
        """Stun a creature: it skips its next turn (mirrors CreatureCmd.Stun).

        next_move_key overrides the move performed after the stunned turn (the
        source's nextMoveId); by default the creature repeats the move it was
        telegraphing (`StateLog.Last().Id`, Creature.cs:531-535).

        For a MachineMonster this is a MACHINE operation, not a boolean:
        Creature.StunInternal force-sets a real synthetic "STUNNED" MoveState
        through SetMoveImmediate, which REFUSES the override while the pending
        move is pinned by MustPerformOnceBeforeTransitioning
        (MonsterModel.cs:420-432) — that is also what stops a second stun
        landing on an already-stunned creature. Hand-rolled monsters have no
        machine and keep the `_move_key` override.
        """
        machine = getattr(target, "machine", None)
        if machine is not None:
            if not machine.current.can_transition_away:
                return
            target._current_move = machine.stun(next_move_key)
        elif next_move_key is not None and hasattr(target, "_move_key"):
            target._move_key = next_move_key
        target.stunned = True
        hooks.on_stunned(target)

    @staticmethod
    def escape(hooks: HookSystem, creature: Creature) -> None:
        """Remove a creature from combat without killing it (mirrors Escape).

        Escaped creatures no longer act, cannot be targeted, and count as gone
        for the win condition.
        """
        if creature.is_dead or creature.escaped:
            return
        creature.escaped = True
        hooks.on_creature_escaped(creature)
        # Escaping can end the fight (mirrors CheckWinCondition after Escape).
        combat = hooks.combat
        if combat is not None and not combat.is_over and combat._all_enemies_dead():
            combat._end_combat(player_won=True)

    @staticmethod
    def add(
        hooks: HookSystem, creature: Creature, index: int | None = None,
        slot_name: str | None = None,
    ) -> None:
        """Add a creature to combat mid-fight (mirrors CreatureCmd.Add), firing
        the added-to-combat hook so powers can react.

        `slot_name` is the NAMED `Encounter.Slots` entry the spawn occupies, and
        it is how the game decides position: CreatureCmd.cs:68-69 calls
        CombatState.AddCreature (which APPENDS, CombatState.cs:534-547) and then
        CombatManager.AddCreature, which runs `_state.SortEnemiesBySlotName()`
        whenever `creature.SlotName != null` (CombatManager.cs:841-851) — sorting
        the whole enemy list by `Encounter.Slots.IndexOf(SlotName)`
        (CombatState.cs:495-501). Pass it and the re-sort happens here too.

        `index` is the older, positional escape hatch for spawns whose position
        the sim had to approximate before the slot row existed; None appends,
        which is right for every spawn with no slot rule.
        """
        combat = hooks.combat
        if combat is None:
            return
        # Parity: roll the spawn's unique HP on the Niche stream BEFORE it joins
        # the enemy list, mirroring CombatState.CreateCreature (SetUniqueMonster-
        # HpValue against the creatures already on the side) then AddCreature.
        # The HP roll excludes sibling MaxHps for uniqueness and so is
        # insertion-order-independent (same existing enemy set either way).
        combat.assign_parity_hp(creature)
        # Stable creature id (CombatState.CombatId), continuing the combat's
        # counter — assigned in ATTACH (creation) order regardless of the slot
        # the creature is inserted at, so recorded targets stay valid.
        counter = getattr(combat, "_net_id_counter", None)
        if counter is not None:
            creature.net_id = counter
            combat._net_id_counter = counter + 1
        if index is None:
            combat.enemies.append(creature)
        else:
            combat.enemies.insert(index, creature)
        if slot_name is not None:
            creature.slot_name = slot_name
            combat.sort_enemies_by_slot_name()
        # CreatureCmd.cs:70 — AfterCreatureAdded runs after the slot re-sort
        # and before Hook.AfterCreatureAddedToCombat (:80). It rolls the
        # spawn's opening move only on the player side; a summon that happens
        # during the enemy's own turn (every monster SUMMON move) is left on
        # UNSET_MOVE for the next player-turn-start pass to pick up.
        combat.after_creature_added(creature)
        hooks.on_creature_added(creature)


class PowerCmd:
    @staticmethod
    def apply(
        hooks: HookSystem,
        target: Creature,
        power_cls: type[Power],
        amount: int,
        applier: Creature | None = None,
    ) -> None:
        """
        Apply a power to a creature.

        Debuffs are intercepted by Artifact (one stack consumed per debuff blocked).
        If the power is already present on the target, on_stack() is called instead
        of creating a new instance.
        """
        from .powers import PowerType

        # PowerCmd.cs:69-72 — Apply<T> opens on `IsEnding -> return null`, and
        # ModifyAmount re-tests it for the stacking branch (:217-220). The sim
        # has ONE code path, so the single entry guard covers both C# sites.
        # `IsEnding`, not `IsOverOrEnding`: that is what lets the out-of-combat
        # callers through.
        if is_ending(hooks):
            return

        # PowerCmd.Apply<T> refuses to apply anything to a creature
        # CanReceivePowers says no to (PowerCmd.cs:73-76). Round 6 wired the
        # ShouldAllowHitting half; the `CombatState == null` half arrived with
        # round 7, and it is what the ten card sites in this family were
        # standing in for with a hand-rolled `if not target.is_gone:`. That
        # stand-in was wrong in both directions: it refused a removal-vetoed
        # corpse the game still powers, and — for every OTHER caller, which had
        # no guard at all — it let an ordinary corpse be powered.
        if not can_receive_powers(hooks, target):
            return

        # C# PowerCmd.Apply runs the "given" power-amount modifiers
        # (Hook.ModifyPowerAmountGiven — e.g. Unsettling Lamp's first-debuff
        # latch + double) BEFORE Artifact negates the debuff
        # (ArtifactPower.TryModifyPowerAmountReceived, which fires later on the
        # "received" side). So a debuff card whose debuff Artifact fully eats
        # STILL spends the Lamp's once-per-combat activation (it latched on that
        # card), and a later debuff card is not doubled. Running
        # modify_power_amount before the Artifact early-return mirrors that
        # ordering; the doubled amount is simply discarded when the debuff is
        # then blocked.
        amount = hooks.modify_power_amount(power_cls, target, amount, applier)

        # ArtifactPower.cs:24 tests `canonicalPower.GetTypeForAmount(amount)`,
        # not the static Type: a negative-amount application of a Buff-typed
        # allow_negative power (Strength/Dexterity) is a Debuff by C#'s rule.
        if power_cls.type_for_amount(amount) == PowerType.DEBUFF:
            artifact = target.powers.get("artifact")
            if artifact is not None:
                artifact.amount -= 1
                hooks.on_power_amount_changed("artifact", target, -1)
                if artifact.amount <= 0:
                    artifact._expire()
                return  # debuff blocked (Lamp already latched above)

        if power_cls.id in target.powers:
            existing = target.powers[power_cls.id]
            old_amount = existing.amount
            existing.on_stack(amount)
            hooks.on_power_amount_changed(
                power_cls.id, target, existing.amount - old_amount, applier
            )
            # Mirrors ModifyAmount → ShouldRemoveDueToAmount: stacking to 0
            # removes the power (or to <= 0 for powers that can't go negative).
            if existing.amount == 0 or (
                existing.amount < 0 and not existing.allow_negative
            ):
                existing._expire()
                return
            power = existing
        else:
            # PowerCmd.cs:133 — CanReceivePowers is re-tested HERE, after the
            # given/received modifier chains have run, because any listener
            # they invoked could have changed the target's hittability in the
            # meantime (a revival latching mid-application). The sim tested it
            # only at the entry. C# re-tests it on the NEW-power path alone:
            # Apply<T> routes an existing instance to ModifyAmount, which never
            # consults CanReceivePowers at all.
            if not can_receive_powers(hooks, target):
                return
            power = power_cls(owner=target, amount=amount, hooks=hooks, applier=applier)
            target.powers[power_cls.id] = power
            hooks.register(power)
            hooks.on_power_applied(power_cls.id, target, amount, applier)
            # Debuffs landing on the player skip their first duration tick.
            # This belongs to the NEW-power branch only: C# sets
            # SkipNextDurationTick in Apply (PowerCmd.cs:144-147) and
            # ModifyAmount (PowerCmd.cs:215-271) never touches it. Setting it
            # at function scope re-armed the flag on every re-stack, so a
            # second Vulnerable or Weak stack applied in the same turn skipped
            # a tick it should have taken and the debuff expired a turn late.
            if (target.side == "player"
                    and power_cls.power_type == PowerType.DEBUFF):
                power.skip_next_tick = True

    @staticmethod
    def modify_amount(hooks: HookSystem, power, offset: int) -> None:
        """PowerCmd.ModifyAmount (PowerCmd.cs:215-271), as reached from
        `Decrement` (:179-182) and so from `TickDownDuration` (:190-200).

        The sim's duration ticks used to mutate `power.amount` directly, which
        is why `ModifyAmount`'s `IsEnding` guard (:217-220) never reached them
        (power_cmd G6's carried observation). They route through here now, so
        a tick in the ending window is refused exactly as a fresh application
        is.

        This is the DECREMENT path only, and it deliberately does NOT run the
        `ModifyPowerAmountGiven` / `ModifyPowerAmountReceived` chains that
        `ModifyAmount` runs at :229-233. Wiring them in is blocked on
        power_cmd/G2: the sim's Unsettling Lamp is missing C#'s `amount <= 0`
        early bail, so it would double a -1 duration tick into -2. G2 is a
        separate open entry; adding the chains before it is fixed would ship a
        known regression.
        """
        if is_ending(hooks):
            return
        power.amount += offset
        hooks.on_power_amount_changed(power.id, power.owner, offset)
        # :247-250 — `if (power.ShouldRemoveDueToAmount()) await Remove(power)`.
        if power.amount <= 0:
            power._expire()

    @staticmethod
    def remove(
        hooks: HookSystem,
        target: Creature,
        power_id: str,
    ) -> None:
        """Remove a power from a creature by ID."""
        power = target.powers.pop(power_id, None)
        if power is not None:
            try:
                hooks.unregister(power)
            except ValueError:
                pass


class StrengthCmd:
    @staticmethod
    def apply(
        hooks: HookSystem,
        target: Creature,
        amount: int,
        card: Card | None = None,
    ) -> int:
        """Apply strength via the hook pipeline. Returns final strength gained."""
        from .powers import StrengthPower
        amount = hooks.modify_strength_given(target, amount, card)
        PowerCmd.apply(hooks, target, StrengthPower, amount)
        return amount


class DrawCmd:
    @staticmethod
    def draw(player: PlayerCombatState, count: int) -> None:
        """Draw count cards mid-turn (from_hand_draw=False). Hooks fire inside player._draw."""
        player._draw(count, from_hand_draw=False)


class ExhaustCmd:
    @staticmethod
    def exhaust(
        hooks: HookSystem,
        player: PlayerCombatState,
        card: Card,
    ) -> None:
        """Move a card from the hand or discard pile to the exhaust pile."""
        if card in player.hand:
            player.hand.remove(card)
        elif card in player.discard_pile:
            player.discard_pile.remove(card)
        player.exhaust_pile.append(card)
        hooks.on_card_exhausted(card)


class CardCmd:
    @staticmethod
    def downgrade(hooks: HookSystem | None, card: Card) -> None:
        """`CardCmd.Downgrade` (CardCmd.cs:212-223).

        The whole verb sits inside `if (!CombatManager.Instance.IsEnding)`, so
        a downgrade fired by the killing blow does not land — the same window
        `creature_card_cmds` guard G14 covers for the other commands. `IsEnding`
        rather than `IsOverOrEnding`, so the two out-of-combat callers
        (Reflections, Welcome to Wongo's) are unaffected; pass `hooks=None`
        there, which answers False for exactly that reason.

        The `DowngradedCards` run-history append the verb also does (:217-220)
        is telemetry and has no sim surface.
        """
        if is_ending(hooks):
            return
        card.downgrade()

    @staticmethod
    def upgrade(hooks: HookSystem | None, card: Card) -> None:
        """`CardCmd.Upgrade` (CardCmd.cs:265-290), the per-card body.

        Two guards, and the sim's bare `card.upgrade()` had neither: the whole
        verb sits inside `if (!IsEnding)`, and each card is skipped when
        `IsUpgradable` is false -- `CurrentUpgradeLevel < MaxUpgradeLevel`
        (CardModel.cs:785-789). The second one matters far more than it looks:
        35 of the pool's cards have MaxUpgradeLevel 0 (every Curse, Status and
        Quest card), and C# THROWS if CurrentUpgradeLevel is ever set above
        MaxUpgradeLevel (CardModel.cs:773-776) -- so an unguarded `+= 1`
        produced a state the source treats as impossible, and one the
        conformance runner compares against the save as an (id, upgrade_level)
        pair.

        The `UpgradedCards` run-history append (:279-282) is telemetry;
        `FinalizeUpgradeInternal` (:284) clears preview state the sim has none of.
        """
        if is_ending(hooks) or not card.is_upgradable:
            return
        card.upgrade()

    @staticmethod
    def afflict(
        card: Card,
        affliction_cls: type[Affliction],
        amount: int,
    ) -> Affliction | None:
        """Attach an affliction to a card (mirrors CardCmd.Afflict).

        A card holds at most one affliction: an unafflicted card gets a new
        instance, re-applying the same type stacks the amount, and a card
        afflicted with a different type is left untouched (returns None).
        """
        # CardCmd.cs:627-634, the seam's one ASYMMETRIC liveness guard: refuse
        # when the combat is over or ending AND the card sits in a combat pile,
        # but allow it for a card that does not (a deck card being afflicted
        # out of combat, which is the same command).
        combat = card.combat
        if getattr(combat, "is_over_or_ending", False):
            player = combat.player
            if any(card in pile for pile in (player.hand, player.draw_pile,
                                             player.discard_pile,
                                             player.exhaust_pile)):
                return None
        if card.affliction is None:
            affliction = affliction_cls(amount)
            affliction.card = card
            card.affliction = affliction
            return affliction
        if isinstance(card.affliction, affliction_cls):
            card.affliction.amount += amount
            return card.affliction
        return None

    @staticmethod
    def clear_affliction(card: Card) -> None:
        """Remove a card's affliction if it has one (mirrors ClearAffliction)."""
        card.affliction = None

    @staticmethod
    def transform_to_random(
        hooks: HookSystem,
        player: PlayerCombatState,
        card: Card,
    ) -> Card | None:
        """Transform a card mid-combat into a random other card (mirrors
        CardCmd.TransformToRandom with isInCombat=true; Entropy).

        The replacement is rolled from the original's transform options
        (see cards.pool.transform_options_in_combat), takes the original's
        place in whichever pile holds it, and becomes a hook listener; the
        original leaves the combat entirely.
        """
        from .cards import make_card
        from .cards.pool import transform_options_in_combat

        # CardCmd.cs:371-374 — `IsEnding -> empty`. The out-of-combat deck
        # transformers (RunState.transform_card) share the C# command and are
        # deliberately unaffected: `IsEnding` is false with no combat running.
        if is_ending(hooks):
            return None
        options = transform_options_in_combat(card, hooks.combat.card_pool)
        if not options:
            return None
        # `CardCmd.TransformToRandom(item, RunState.Rng.CombatCardSelection)`
        # (EntropyPower.cs:31) — the caller names the stream, and Entropy is
        # the only in-combat caller.
        replacement = make_card(
            hooks.combat.combat_rng.card_selection.choice(options))
        for pile_name, pile in (
            ("hand", player.hand), ("draw", player.draw_pile),
            ("discard", player.discard_pile), ("exhaust", player.exhaust_pile),
        ):
            if card in pile:
                pile[pile.index(card)] = replacement
                break
        else:
            return None
        try:
            hooks.unregister(card)
        except ValueError:
            pass
        CardPileCmd._enter_combat(hooks, replacement)
        # CardCmd.cs:447-450, in this order, and shared by both branches of the
        # pile-type test above them:
        #
        #   await Hook.AfterCardChangedPiles(runState, combatState,
        #                                    replacement2, pile2.Type, null);
        #   pile2.InvokeCardAddFinished();
        #   original.AfterTransformedFrom();
        #   replacement2.AfterTransformedTo();
        #
        # `clonedBy` is a literal `null` here — a transform is not a clone, so
        # Bing Bong's `clonedBy == null` test passes for a transformed card
        # where it fails for one Bing Bong itself added (BingBong.cs:31).
        #
        # InvokeCardAddFinished (:448) has NO sim counterpart and needs none:
        # it is `CardAddFinished?.Invoke()` (CardPile.cs:179-182) and the event's
        # only subscriber in the whole source is NCombatCardPile.cs:83-106, a
        # presentation node that animates the card into the pile.
        hooks.after_card_changed_piles(replacement, pile_name, None)
        card.after_transformed_from()
        replacement.after_transformed_to()
        return replacement


class CardPileCmd:
    @staticmethod
    def _refuses_combat_add(hooks: HookSystem, player: PlayerCombatState) -> bool:
        """CardPileCmd.Add's three refusals for a COMBAT pile, all of which sit
        upstream of the actual pile move (the move is at CardPileCmd.cs:408+,
        after the last of them):

          :312-319  `newPile.IsCombatPile && IsEnding` -> every result
                    success = false, so nothing is added;
          :329-340  per card, `creature.IsDead` -> success = false. A SEPARATE
                    refusal: a power holding the fight open leaves IsEnding
                    false while the owner is dead, and the card is still
                    dropped;
          :398-401  `newPile.IsCombatPile && !IsInProgress` -> return.

        The sim's three pile helpers moved the card unconditionally.
        """
        combat = getattr(hooks, "combat", None)
        if combat is None:
            return False
        return getattr(combat, "is_over_or_ending", False) or player.is_dead

    @staticmethod
    def _enter_combat(hooks: HookSystem, card: Card) -> None:
        """Register a newly created card as a hook listener (cards listen for
        their whole combat lifetime, mirroring CardModel = AbstractModel) and
        fire the entered-combat hook so active powers can afflict it.

        The card's ENCHANTMENT is registered with it, exactly as
        `CombatState.__init__` does for the starting deck. C# needs no such
        step — `CombatState.IterateHookListeners` re-enumerates from the piles
        on every dispatch and adds `cardModel.Enchantment`
        (CombatState.cs:462-465) — but the sim registers once, so a card
        created MID-combat used to arrive with an inert enchantment. Since
        `create_clone` began carrying the enchantment onto copies
        (enchantment/EG2), that was not merely a dead listener but a crash:
        Corrupted and Sown reach the engine through `self.combat.hooks` in
        their `on_play`, and on a copy `combat` was None.
        """
        card.combat = hooks.combat
        hooks.register(card)
        if card.enchantment is not None:
            card.enchantment.combat = hooks.combat
            if card.enchantment not in hooks._listeners:
                hooks.register(card.enchantment)
        hooks.on_card_entered_combat(card)

    @staticmethod
    def add_to_discard(
        hooks: HookSystem,
        player: PlayerCombatState,
        card: Card,
    ) -> None:
        """Add a newly created card to the player's discard pile (mirrors
        CardPileCmd.AddToCombatAndPreview)."""
        if CardPileCmd._refuses_combat_add(hooks, player):
            return
        player.discard_pile.append(card)
        CardPileCmd._enter_combat(hooks, card)

    @staticmethod
    def add_to_draw(
        hooks: HookSystem,
        player: PlayerCombatState,
        card: Card,
    ) -> None:
        """Add a newly created card to a random position in the player's draw
        pile (mirrors AddGeneratedCardToCombat with PileType.Draw,
        CardPilePosition.Random).

        Parity (CardPileCmd.cs:514): the random slot is drawn from the SHUFFLE
        stream — ``Rng.Shuffle.NextInt(Cards.Count + 1)`` — not the shared run
        rng. The game pile counts index 0 = top (next drawn); the sim stores its
        top at the END (the parity reshuffle reverses game order, player.py),
        so a game index ``p`` lands at sim index ``count - p``. Legacy keeps its
        byte-for-byte shared-rng insertion."""
        if CardPileCmd._refuses_combat_add(hooks, player):
            return
        crng = hooks.combat.combat_rng
        count = len(player.draw_pile)
        if crng.is_parity:
            p = crng.shuffle.randrange(count + 1)   # game index, 0 = top
            player.draw_pile.insert(count - p, card)
        else:
            player.draw_pile.insert(hooks.combat._rng.randrange(count + 1), card)
        CardPileCmd._enter_combat(hooks, card)

    @staticmethod
    def auto_play_from_draw_pile(
        hooks: HookSystem,
        player: PlayerCombatState,
        count: int,
        position: str = "top",
        force_exhaust: bool = False,
    ) -> None:
        """`CardPileCmd.AutoPlayFromDrawPile` (CardPileCmd.cs:931-966), and it is
        TWO-PHASE — which is the whole reason it exists as one helper.

        Phase 1 (:939-955) pulls all `count` picks out of the draw pile and into
        `PileType.Play`, one `ShuffleIfNecessary` per pick, breaking on an empty
        pile. Phase 2 (:956-965) plays them, setting `ExhaustOnNextPlay =
        forceExhaust` on each first and breaking if the owner has died.

        So every pick is COMMITTED before any of them resolves: a draw, a
        reshuffle or a pile redirect the first card causes cannot change which
        card is played second, and because the waiting cards sit in PileType.Play
        a reshuffle the first one triggers excludes them (bug class 7, pile
        limbo). Both sim callers interleaved instead — Havoc and Mayhem picked
        and played one card per iteration.

        `force_exhaust` is applied through `exhaust_on_next_play`, not by moving
        the card by hand: that is what routes it through the normal result-pile
        path, so an unplayable pick reaches `CardCmd.Exhaust`
        (CardModel.cs:2098-2101) and a Power card still vanishes to
        `PileType.None` (:2071-2074).
        """
        combat = hooks.combat
        if is_over_or_ending(hooks) or player.is_dead:
            return                                  # CardPileCmd.cs:933-936
        cards: list[Card] = []
        for _ in range(count):
            player.shuffle_if_necessary()           # :939
            pile = player.draw_pile
            if not pile:
                break                               # :949-952, `break` not continue
            if position == "top":
                card = pile[-1]                     # the sim stores top LAST
            elif position == "bottom":
                card = pile[0]
            else:
                # `Rng.CombatCardSelection.NextItem(drawPile.Cards)` (:942) over
                # the game's top-first orientation, so the index means the same
                # thing in both engines.
                card = combat.combat_rng.card_selection.choice(list(reversed(pile)))
            cards.append(card)
            # `await Add(cardModel, PileType.Play)` (:954) — the card leaves the
            # draw pile now and is in no pile a reshuffle can see.
            pile.remove(card)
        for card in cards:
            if player.is_dead:
                break                               # :958-964
            card.exhaust_on_next_play = force_exhaust
            combat.auto_play_card(card)

    @staticmethod
    def add_to_hand(
        hooks: HookSystem,
        player: PlayerCombatState,
        card: Card,
    ) -> None:
        """Add a newly created card to the player's hand (overflow goes to the
        discard pile) (mirrors CardPileCmd.AddGeneratedCardToCombat with
        PileType.Hand)."""
        if CardPileCmd._refuses_combat_add(hooks, player):
            return
        if len(player.hand) < player.MAX_HAND_SIZE:
            player.hand.append(card)
        else:
            player.discard_pile.append(card)
        CardPileCmd._enter_combat(hooks, card)


class CardSelectCmd:
    """In-combat card selection (mirrors the game's CardSelectCmd). The actual
    choice is made by CombatState.select_cards — random by default, or by an
    installed card_selector."""

    @staticmethod
    def from_hand(
        hooks: HookSystem,
        player: PlayerCombatState,
        purpose: str,
        count: int = 1,
        predicate=None,
    ) -> list[Card]:
        """Pick up to count cards from the hand (mirrors CardSelectCmd.FromHand)."""
        candidates = [c for c in player.hand if predicate is None or predicate(c)]
        return hooks.combat.select_cards(purpose, candidates, count)

    @staticmethod
    def from_pile(
        hooks: HookSystem,
        pile: list[Card],
        purpose: str,
        count: int = 1,
        predicate=None,
    ) -> list[Card]:
        """Pick up to count cards from any pile (mirrors FromCombatPile)."""
        candidates = [c for c in pile if predicate is None or predicate(c)]
        return hooks.combat.select_cards(purpose, candidates, count)


class EnergyCmd:
    @staticmethod
    def gain(
        hooks: HookSystem,
        player: PlayerCombatState,
        amount: int,
    ) -> None:
        """Gain bonus energy mid-turn (from cards or effects, not turn reset)."""
        amount = hooks.modify_energy_gain(player, amount)
        player.energy += amount
