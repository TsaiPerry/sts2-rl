from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .cards import Card
    from .creatures import Creature
    from .hooks import HookSystem
    from .player import PlayerCombatState


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

        # 1. Additive modifiers then multiplicative (e.g. Vulnerable, Weak)
        amount = amount + hooks.modify_damage_additive(target, amount, dealer, card)
        amount = int(amount * hooks.modify_damage_multiplicative(target, amount, dealer, card))

        # 2. Damage cap (e.g. Intangible: cap at 1)
        cap = hooks.modify_damage_cap(target, dealer, card)
        if cap is not None:
            amount = min(amount, cap)

        amount = max(0, amount)

        # 3. Block absorption
        hp_lost = amount
        if target.block > 0:
            absorbed = min(target.block, amount)
            target.block -= absorbed
            hp_lost -= absorbed
            if target.block == 0 and hp_lost > 0:
                # attack broke through block entirely
                hooks.on_block_broken(target)

        # 4. HP-loss modifiers applied after block (e.g. Torii: cap at 1, Tungsten Rod: -1)
        if hp_lost > 0:
            hp_lost = hooks.modify_hp_lost(target, hp_lost, dealer, card)

        # 5. Apply HP loss
        if hp_lost > 0:
            old_hp = target.hp
            target.hp = max(0, target.hp - hp_lost)
            hooks.on_hp_changed(target, target.hp - old_hp)

            # 6. Death check — listeners can prevent death (e.g. Fairy in a Bottle)
            if target.hp <= 0:
                if hooks.should_die(target):
                    hooks.on_death(target)
                else:
                    target.hp = 1

        # 7. Post-damage events
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


class StrengthCmd:
    @staticmethod
    def apply(
        hooks: HookSystem,
        target: Creature,
        amount: int,
        card: Card | None = None,
    ) -> int:
        """Apply strength through the hook pipeline. Returns final strength gained."""
        amount = hooks.modify_strength_given(target, amount, card)
        target.strength += amount
        hooks.on_power_applied("strength", target, amount)
        return amount


class DrawCmd:
    @staticmethod
    def draw(player: PlayerCombatState, count: int) -> None:
        """Draw count cards. Hooks (on_card_drawn, on_shuffle, should_draw) fire inside player._draw."""
        player._draw(count)


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
