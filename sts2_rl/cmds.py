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


class DamageCmd:
    @staticmethod
    def deal(
        hooks: HookSystem,
        target: Creature,
        amount: int,
        dealer: Creature | None = None,
        card: Card | None = None,
        props: ValueProp | None = None,
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
        amount = amount + hooks.modify_damage_additive(
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
            # WasBlockBroken (CreatureCmd.cs): Block <= 0 && blockedDamage > 0
            # — an exact break counts; overflow damage is not required.
            if target.block == 0:
                hooks.on_block_broken(target, dealer, card)

        # 6. HP-loss modifiers applied after block (e.g. Torii: cap at 1, Tungsten Rod: -1)
        if hp_lost > 0:
            modifiers: list = []
            hp_lost = hooks.modify_hp_lost(target, hp_lost, dealer, card, modifiers)
            hooks.after_modify_hp_lost(modifiers, target)

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
        if props is None:
            props = ValueProp.MOVE
        # The source card's own enchantment folds in before either listener
        # loop (Hook.cs:1315-1320), like the damage side.
        ench = card.enchantment if card is not None else None
        if ench is not None:
            amount += ench.enchant_block_additive(amount, props)
            amount *= ench.enchant_block_multiplicative(amount, props)
        blk_modifiers: list = []
        amount = amount + hooks.modify_block_additive(
            target, amount, card, blk_modifiers, props)
        amount = int(hooks.modify_block_multiplicative(
            target, amount, card, blk_modifiers, props))
        amount = max(0, amount)
        target.block += amount
        if blk_modifiers:
            hooks.after_modify_block_amount(blk_modifiers, target, card)
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
        hooks: HookSystem, creature: Creature, index: int | None = None
    ) -> None:
        """Add a creature to combat mid-fight (mirrors CreatureCmd.Add), firing
        the added-to-combat hook so powers can react.

        `index` is the enemy-list slot to insert at (mirrors the game placing a
        spawn into a named Encounter slot — e.g. Ovicopter's eggs fill the slots
        before it); None appends (the default for spawns with no slot rule)."""
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

        # PowerCmd.Apply<T> refuses to apply anything to a creature
        # CanReceivePowers says no to (PowerCmd.cs:73-76), and CanReceivePowers
        # reuses Hook.ShouldAllowHitting (Creature.cs:308-322). The sim wired
        # that predicate into DamageCmd.deal but not here, so a *debuff*
        # landed where damage would not: Vulnerable stuck to a reviving Test
        # Subject, and the AoE power potions applied to an Eye with Teeth
        # mid-Illusion-revival that C#'s HittableEnemies excludes.
        if not hooks.should_allow_hitting(target):
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

        options = transform_options_in_combat(card, hooks.combat.card_pool)
        if not options:
            return None
        replacement = make_card(hooks.combat._rng.choice(options))
        for pile in (
            player.hand, player.draw_pile, player.discard_pile,
            player.exhaust_pile,
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
        return replacement


class CardPileCmd:
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
        crng = hooks.combat.combat_rng
        count = len(player.draw_pile)
        if crng.is_parity:
            p = crng.shuffle.randrange(count + 1)   # game index, 0 = top
            player.draw_pile.insert(count - p, card)
        else:
            player.draw_pile.insert(hooks.combat._rng.randrange(count + 1), card)
        CardPileCmd._enter_combat(hooks, card)

    @staticmethod
    def add_to_hand(
        hooks: HookSystem,
        player: PlayerCombatState,
        card: Card,
    ) -> None:
        """Add a newly created card to the player's hand (overflow goes to the
        discard pile) (mirrors CardPileCmd.AddGeneratedCardToCombat with
        PileType.Hand)."""
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
