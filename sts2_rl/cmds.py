from __future__ import annotations

from typing import TYPE_CHECKING

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
    ) -> int:
        """Full damage pipeline. Returns actual HP lost (after block and modifiers)."""
        if not hooks.should_allow_hitting(target):
            return 0

        # 1. Additive modifiers then multiplicative (e.g. Strength, Vulnerable, Weak)
        amount = amount + hooks.modify_damage_additive(target, amount, dealer, card)
        amount = int(amount * hooks.modify_damage_multiplicative(target, amount, dealer, card))

        # 2. Damage cap (e.g. Intangible: cap at 1)
        cap = hooks.modify_damage_cap(target, dealer, card)
        if cap is not None:
            amount = min(amount, cap)

        amount = max(0, amount)

        # 3. Pre-block hit event (e.g. CurlUp triggers even when block absorbs)
        if amount > 0:
            hooks.on_attacked(target, amount, dealer, card)

        # 4. Block absorption
        hp_lost = amount
        if target.block > 0:
            absorbed = min(target.block, amount)
            target.block -= absorbed
            hp_lost -= absorbed
            if target.block == 0 and hp_lost > 0:
                hooks.on_block_broken(target)

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
        hooks.on_damage_received(target, hp_lost, dealer, card)
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
    ) -> int:
        """Apply block through the hook pipeline. Returns final block gained."""
        amount = amount + hooks.modify_block_additive(target, amount, card)
        amount = int(amount * hooks.modify_block_multiplicative(target, amount, card))
        amount = max(0, amount)
        target.block += amount
        hooks.on_block_gained(target, amount)
        return amount


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

        if power_cls.id in target.powers:
            existing = target.powers[power_cls.id]
            old_amount = existing.amount
            existing.on_stack(amount)
            hooks.on_power_amount_changed(power_cls.id, target, existing.amount - old_amount)
        else:
            power = power_cls(owner=target, amount=amount, hooks=hooks, applier=applier)
            target.powers[power_cls.id] = power
            hooks.register(power)
            hooks.on_power_applied(power_cls.id, target, amount)

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


class CardPileCmd:
    @staticmethod
    def add_to_discard(
        hooks: HookSystem,
        player: PlayerCombatState,
        card: Card,
    ) -> None:
        """Add a newly created card to the player's discard pile, firing the
        entered-combat hook so active powers can afflict it (mirrors
        CardPileCmd.AddToCombatAndPreview)."""
        player.discard_pile.append(card)
        hooks.on_card_entered_combat(card)


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
