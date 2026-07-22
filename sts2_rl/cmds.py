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

        # 1. Additive then multiplicative modifiers (Strength, Vulnerable, Weak).
        #    Only powered attacks are modified (mirrors IsPoweredAttack checks).
        if is_powered_attack(props):
            amount = amount + hooks.modify_damage_additive(target, amount, dealer, card)
            amount = int(amount * hooks.modify_damage_multiplicative(target, amount, dealer, card))

        # 2. Damage cap (e.g. Intangible: cap at 1) — applies to all damage types
        cap = hooks.modify_damage_cap(target, dealer, card)
        if cap is not None:
            amount = min(amount, cap)

        amount = max(0, amount)

        # 3. Pre-block hit event for attacks (e.g. CurlUp triggers even when
        #    block absorbs). Non-move damage (Poison, Thorns) is not a "hit".
        if amount > 0 and ValueProp.MOVE in props:
            hooks.on_attacked(target, amount, dealer, card)

        # 4. Block absorption (skipped for unblockable HP loss like Poison)
        hp_lost = amount
        if target.block > 0 and ValueProp.UNBLOCKABLE not in props:
            absorbed = min(target.block, amount)
            target.block -= absorbed
            hp_lost -= absorbed
            # WasBlockBroken (CreatureCmd.cs): Block <= 0 && blockedDamage > 0
            # — an exact break counts; overflow damage is not required.
            if target.block == 0:
                hooks.on_block_broken(target, dealer, card)

        # 5. HP-loss modifiers applied after block (e.g. Torii: cap at 1, Tungsten Rod: -1)
        if hp_lost > 0:
            hp_lost = hooks.modify_hp_lost(target, hp_lost, dealer, card)

        # 6. Apply HP loss
        if hp_lost > 0:
            old_hp = target.hp
            target.hp = max(0, target.hp - hp_lost)
            hooks.on_hp_changed(target, target.hp - old_hp)

            # 7. Death check — listeners can prevent death (e.g. Fairy in a Bottle)
            if target.hp <= 0:
                if hooks.should_die(target):
                    hooks.on_death(target)
                else:
                    target.hp = 1

        # 8. Post-damage events
        hooks.on_damage_received(target, hp_lost, dealer, card, props)
        if dealer is not None and hp_lost > 0:
            hooks.on_damage_dealt(dealer, target, hp_lost, card)

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

        Unpowered block (e.g. Block Potion) skips Dexterity/Frail modifiers,
        mirroring STS2's IsPoweredCardOrMonsterMoveBlock check.
        """
        if props is None:
            props = ValueProp.MOVE
        if is_powered_attack(props):  # same Move-and-not-Unpowered rule as damage
            amount = amount + hooks.modify_block_additive(target, amount, card)
            amount = int(amount * hooks.modify_block_multiplicative(target, amount, card))
        amount = max(0, amount)
        target.block += amount
        hooks.on_block_gained(target, amount, card)
        return amount


class CreatureCmd:
    """Creature-level verbs beyond plain damage (mirrors STS2's CreatureCmd)."""

    @staticmethod
    def heal(hooks: HookSystem, target: Creature, amount: int) -> int:
        """Heal up to amount HP, capped at max HP. Returns HP actually restored."""
        if target.is_dead:
            return 0
        healed = min(amount, target.max_hp - target.hp)
        if healed > 0:
            target.hp += healed
            hooks.on_hp_changed(target, healed)
        return healed

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
        if hooks.should_die(target):
            hooks.on_death(target)
        else:
            target.hp = 1

    @staticmethod
    def stun(hooks: HookSystem, target: Creature, next_move_key: str | None = None) -> None:
        """Stun a creature: it skips its next turn (mirrors CreatureCmd.Stun).

        next_move_key optionally overrides the move performed after the stunned
        turn (the source's nextMoveId); by default the creature resumes its
        pattern where it left off.
        """
        target.stunned = True
        if next_move_key is not None and hasattr(target, "_move_key"):
            target._move_key = next_move_key
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
    def add(hooks: HookSystem, creature: Creature) -> None:
        """Add a creature to combat mid-fight (mirrors CreatureCmd.Add), firing
        the added-to-combat hook so powers can react."""
        combat = hooks.combat
        if combat is None:
            return
        # Parity: roll the spawn's unique HP on the Niche stream BEFORE it joins
        # the enemy list, mirroring CombatState.CreateCreature (SetUniqueMonster-
        # HpValue against the creatures already on the side) then AddCreature.
        combat.assign_parity_hp(creature)
        combat.enemies.append(creature)
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

        if power_cls.power_type == PowerType.DEBUFF:
            artifact = target.powers.get("artifact")
            if artifact is not None:
                artifact.amount -= 1
                hooks.on_power_amount_changed("artifact", target, -1)
                if artifact.amount <= 0:
                    artifact._expire()
                return  # debuff blocked

        amount = hooks.modify_power_amount(power_cls, target, amount, applier)

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

        # Debuffs landing on the player skip their first duration tick
        # (mirrors PowerCmd.Apply setting SkipNextDurationTick).
        if target.side == "player" and power_cls.power_type == PowerType.DEBUFF:
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

        options = transform_options_in_combat(card)
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
        fire the entered-combat hook so active powers can afflict it."""
        card.combat = hooks.combat
        hooks.register(card)
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
