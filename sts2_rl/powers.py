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

from .valueprops import ValueProp

if TYPE_CHECKING:
    from .cards import Card
    from .creatures import Creature
    from .hooks import HookSystem


class PowerType(Enum):
    BUFF = "buff"
    DEBUFF = "debuff"


class Power:
    """
    Base class for all powers/buffs/debuffs, mirroring STS2's PowerModel.

    Subclasses override hook methods as needed. The hook system calls them
    via hasattr duck-typing, so only overridden methods are called.
    """

    id: str
    name: str
    power_type: PowerType
    # Mirrors PowerModel.AllowNegative: powers that can hold a negative amount
    # (Strength, Dexterity). When stacking drops the amount to 0 (or below 0
    # for powers that don't allow negatives) the power is removed, mirroring
    # PowerCmd.ModifyAmount → ShouldRemoveDueToAmount.
    allow_negative = False

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

    # ── Internal helpers ─────────────────────────────────────────────────

    def _tick(self) -> None:
        """Decrement duration by 1; expire when it reaches 0."""
        self.amount -= 1
        self.hooks.on_power_amount_changed(self.id, self.owner, -1)
        if self.amount <= 0:
            self._expire()

    def _tick_duration(self) -> None:
        """_tick, but honouring skip_next_tick (mirrors PowerCmd.TickDownDuration —
        used by Vulnerable/Weak/Frail so a debuff applied to the player during
        the enemy turn survives its first side-end tick)."""
        if self.skip_next_tick:
            self.skip_next_tick = False
            return
        self._tick()

    def _expire(self) -> None:
        """Remove this power from owner.powers and unregister from the hook system."""
        self.owner.powers.pop(self.id, None)
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
    ) -> int:
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
    ) -> int:
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

    def on_enemy_turn_end(self, enemy: Creature) -> None:
        if self.owner is enemy:
            self._apply_regen()

    def on_player_turn_end(self, player: Creature) -> None:
        if self.owner is player:
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
        self._was_just_applied = (
            applier is not None and applier.side != owner.side
        )

    def _trigger(self) -> None:
        if self._was_just_applied:
            self._was_just_applied = False
            return
        from .cmds import StrengthCmd
        StrengthCmd.apply(self.hooks, self.owner, self.amount)

    def on_enemy_turn_end(self, enemy: Creature) -> None:
        if self.owner is enemy:
            self._trigger()

    def on_player_turn_end(self, player: Creature) -> None:
        if self.owner is player:
            self._trigger()


class DemonFormPower(Power):
    """Gain N Strength at the START of the owner's turn each turn."""

    id = "demon_form"
    name = "Demon Form"
    power_type = PowerType.BUFF

    def on_enemy_turn_start(self, enemy: Creature) -> None:
        if self.owner is enemy:
            from .cmds import StrengthCmd
            StrengthCmd.apply(self.hooks, self.owner, self.amount)

    def on_player_turn_start(self, player: Creature) -> None:
        if self.owner is player:
            from .cmds import StrengthCmd
            StrengthCmd.apply(self.hooks, self.owner, self.amount)


class FeelNoPainPower(Power):
    """Gain N block whenever a card is exhausted."""

    id = "feel_no_pain"
    name = "Feel No Pain"
    power_type = PowerType.BUFF

    def on_card_exhausted(self, card: Card) -> None:
        from .cmds import BlockCmd
        BlockCmd.apply(self.hooks, self.owner, self.amount)


class DarkEmbracePower(Power):
    """Draw 1 card whenever a card is exhausted. Owner must be the player."""

    id = "dark_embrace"
    name = "Dark Embrace"
    power_type = PowerType.BUFF

    def on_card_exhausted(self, card: Card) -> None:
        from .player import PlayerCombatState
        if isinstance(self.owner, PlayerCombatState):
            from .cmds import DrawCmd
            DrawCmd.draw(self.owner, 1)


class EnragePower(Power):
    """Gain N Strength whenever a Skill card is played."""

    id = "enrage"
    name = "Enrage"
    power_type = PowerType.BUFF

    def on_card_played(self, card: Card) -> None:
        from .cards import CardType
        if card.card_type == CardType.SKILL:
            from .cmds import StrengthCmd
            StrengthCmd.apply(self.hooks, self.owner, self.amount)


class RupturePower(Power):
    """Gain N Strength whenever the owner loses HP from damage."""

    id = "rupture"
    name = "Rupture"
    power_type = PowerType.BUFF

    def on_damage_received(
        self,
        target: Creature,
        amount: int,
        dealer: Creature | None,
        card: Card | None,
        props: ValueProp = ValueProp.NONE,
    ) -> None:
        if target is self.owner and amount > 0:
            from .cmds import StrengthCmd
            StrengthCmd.apply(self.hooks, self.owner, self.amount)


class CurlUpPower(Power):
    """Gain N block the first time the owner is hit. One-shot."""

    id = "curl_up"
    name = "Curl Up"
    power_type = PowerType.BUFF

    def on_damage_received(
        self,
        target: Creature,
        amount: int,
        dealer: Creature | None,
        card: Card | None,
        props: ValueProp = ValueProp.NONE,
    ) -> None:
        # Mirror STS2: block is granted after damage resolves (AfterDamageReceived),
        # so the triggering hit takes full damage before the block appears.
        if target is self.owner and dealer is not None:
            from .cmds import BlockCmd
            BlockCmd.apply(self.hooks, self.owner, self.amount)
            self._expire()


class ArtifactPower(Power):
    """
    Blocks the next N debuffs applied to the owner.

    This power has no active hook methods; it is intercepted by PowerCmd.apply
    before a debuff can be registered.
    """

    id = "artifact"
    name = "Artifact"
    power_type = PowerType.BUFF


class ThornsPower(Power):
    """Reflect N damage to the attacker when the owner is hit.

    The reflected damage is unpowered but blockable (STS2's ThornsPower deals
    ValueProp.Unpowered damage): the attacker's block absorbs it, Strength and
    Vulnerable do not modify it."""

    id = "thorns"
    name = "Thorns"
    power_type = PowerType.BUFF

    def on_damage_received(
        self,
        target: Creature,
        amount: int,
        dealer: Creature | None,
        card: Card | None,
        props: ValueProp = ValueProp.NONE,
    ) -> None:
        if target is not self.owner or dealer is None:
            return
        from .cmds import DamageCmd
        from .valueprops import DamageProps
        DamageCmd.deal(
            self.hooks, dealer, self.amount, props=DamageProps.NON_CARD_UNPOWERED
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
    ) -> float:
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
    ) -> float:
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
    ) -> float:
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

    def on_enemy_turn_start(self, enemy: Creature) -> None:
        if self.owner is enemy:
            self._apply_poison()

    def on_player_turn_start(self, player: Creature) -> None:
        if self.owner is player:
            self._apply_poison()


# ── Ironclad card powers ─────────────────────────────────────────────────


class AggressionPower(Power):
    """At the start of the owner's turn (before the hand draw), move N random
    Attack cards from the discard pile to the hand and upgrade them."""

    id = "aggression"
    name = "Aggression"
    power_type = PowerType.BUFF

    def on_player_turn_start(self, player: Creature) -> None:
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
    Removed at the end of the owner's turn. Does not stack."""

    id = "no_draw"
    name = "No Draw"
    power_type = PowerType.DEBUFF

    def on_stack(self, amount: int) -> None:
        pass  # PowerStackType.Single

    def should_draw(self, player: Creature, from_hand_draw: bool = False) -> bool:
        if from_hand_draw or player is not self.owner:
            return True
        return False

    def on_player_turn_end(self, player: Creature) -> None:
        if player is self.owner:
            self._expire()


class NoEnergyGainPower(Power):
    """Mid-turn energy gains are reduced to 0 (turn-start energy is unaffected).
    Removed at the end of the owner's turn. Does not stack."""

    id = "no_energy_gain"
    name = "No Energy Gain"
    power_type = PowerType.DEBUFF

    def on_stack(self, amount: int) -> None:
        pass  # PowerStackType.Single

    def modify_energy_gain(self, player: Creature, amount: int) -> int:
        if player is self.owner:
            return 0
        return amount

    def on_player_turn_end(self, player: Creature) -> None:
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
    ) -> float:
        if target is self.owner and dealer is not None and "vulnerable" in dealer.powers:
            return 0.5
        return 1.0

    def on_enemy_side_end(self) -> None:
        self._tick()


class CorruptionPower(Power):
    """Skill cards cost 0 and are exhausted when played. Does not stack."""

    id = "corruption"
    name = "Corruption"
    power_type = PowerType.BUFF

    def on_stack(self, amount: int) -> None:
        pass  # PowerStackType.Single

    def modify_card_energy_cost(self, card: Card, cost: int) -> int:
        from .cards import CardType
        if card.card_type == CardType.SKILL:
            return 0
        return cost

    def on_card_played(self, card: Card) -> None:
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

    def on_player_turn_start(self, player: Creature) -> None:
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
    target). Does not stack.

    The game caps consecutive auto-plays at 9 only against infinite-HP
    enemies, which the sim does not have."""

    id = "hellraiser"
    name = "Hellraiser"
    power_type = PowerType.BUFF

    def on_stack(self, amount: int) -> None:
        pass  # PowerStackType.Single

    def on_card_drawn(self, card: Card, from_hand_draw: bool = False) -> None:
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

    def on_player_turn_start(self, player: Creature) -> None:
        if player is self.owner and self.self_damage > 0:
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
        DamageCmd.deal(
            self.hooks, combat._rng.choice(living), self.amount,
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

    def on_card_played(self, card: Card) -> None:
        from .cards import CardType
        if card.card_type != CardType.ATTACK:
            return
        self._attacks_this_turn += 1
        if self._attacks_this_turn == 3:
            from .cmds import CardPileCmd
            for _ in range(self.amount):
                clone = type(card)()
                for _ in range(card.upgrade_level):
                    clone.upgrade()
                CardPileCmd.add_to_hand(self.hooks, self.owner, clone)

    def on_player_turn_end(self, player: Creature) -> None:
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

    def on_player_turn_end(self, player: Creature) -> None:
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

    def on_player_turn_end(self, player: Creature) -> None:
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

    def on_card_played(self, card: Card) -> None:
        from .cards import CardType
        if card.card_type == CardType.ATTACK:
            from .cmds import BlockCmd
            from .valueprops import ValueProp
            BlockCmd.apply(self.hooks, self.owner, self.amount, props=ValueProp.UNPOWERED)

    def on_player_turn_end(self, player: Creature) -> None:
        if player is self.owner:
            self._expire()


class StampedePower(Power):
    """When the owner ends their turn, auto-play N random playable Attacks
    from the hand (before turn-end card effects and the hand discard)."""

    id = "stampede"
    name = "Stampede"
    power_type = PowerType.BUFF

    def on_player_turn_end(self, player: Creature) -> None:
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
            combat.auto_play_card(combat._rng.choice(candidates))


class PlatingPower(Power):
    """Gain N block at the end of the owner's turn (before turn-end card
    effects); lose 1 stack at the start of the owner's turn (except on the
    first turn of combat). Enemies that start combat with Plating also start
    with the block (mirrors PlatingPower.BeforeSideTurnStart on round 1)."""

    id = "plating"
    name = "Plating"
    power_type = PowerType.BUFF

    def on_combat_start(self) -> None:
        if self.owner.side == "enemy":
            self._gain_block()

    def _gain_block(self) -> None:
        from .cmds import BlockCmd
        from .valueprops import ValueProp
        BlockCmd.apply(self.hooks, self.owner, self.amount, props=ValueProp.UNPOWERED)

    def _decay(self) -> None:
        combat = self.hooks.combat
        if combat is not None and combat.turn > 1:
            self._tick()

    def on_player_turn_end(self, player: Creature) -> None:
        if player is self.owner:
            self._gain_block()

    def on_player_turn_start(self, player: Creature) -> None:
        if player is self.owner:
            self._decay()

    def on_enemy_turn_end(self, enemy: Creature) -> None:
        if enemy is self.owner and not self.owner.is_dead:
            self._gain_block()

    def on_enemy_turn_start(self, enemy: Creature) -> None:
        if enemy is self.owner:
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
    ) -> float:
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

    def on_card_played(self, card: Card) -> None:
        if card is self._active_card:
            self._plays_used += 1
            self._active_card = None

    def on_player_turn_start(self, player: Creature) -> None:
        if player is self.owner:
            self._plays_used = 0
            self._active_card = None


class FreeAttackPower(Power):
    """The owner's next N Attack cards cost 0. Playing any Attack consumes a
    stack; persists across turns.

    The stack is consumed in on_energy_spent, which fires before the card
    resolves (mirrors BeforeCardPlayed) — so the stack Unrelenting applies
    during its own resolution is not consumed by Unrelenting itself.
    Auto-plays fire on_energy_spent with 0 energy, so they consume a stack
    just like the game's BeforeCardPlayed."""

    id = "free_attack"
    name = "Free Attack"
    power_type = PowerType.BUFF

    def modify_card_energy_cost(self, card: Card, cost: int) -> int:
        from .cards import CardType
        if card.card_type == CardType.ATTACK:
            return 0
        return cost

    def on_energy_spent(self, card: Card, amount: int) -> None:
        from .cards import CardType
        if card.card_type == CardType.ATTACK:
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
    instance (PowerInstanceType.Instanced); the sim keeps one instance per
    power id, so re-applying stacks the turn counter and overwrites the block
    value (an approximation that only matters with multiple copies active).
    """

    id = "toric_toughness"
    name = "Toric Toughness"
    power_type = PowerType.BUFF

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

    def on_card_played(self, card: Card) -> None:
        self._cards_this_turn += 1

    def on_enemy_turn_start(self, enemy: Creature) -> None:
        if enemy is self.owner:
            self._cards_this_turn = 0

    def modify_damage_multiplicative(
        self,
        target: Creature,
        amount: int,
        dealer: Creature | None,
        card: Card | None,
    ) -> float:
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

    def on_card_played(self, card: Card) -> None:
        self._card_played_this_turn = True

    def on_player_turn_start(self, player: Creature) -> None:
        if player is self.owner:
            self._card_played_this_turn = False

    def on_player_turn_end(self, player: Creature) -> None:
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
    ) -> float:
        if dealer is self.owner and card is not None and not card.is_unpowered:
            return 0.7
        return 1.0

    def on_player_turn_end(self, player: Creature) -> None:
        if player is self.owner and self.amount > 0:
            self._tick()

    def on_enemy_side_end(self) -> None:
        if self.owner.side == "enemy" and self.amount > 0:
            self._tick()

    def on_death(self, creature: Creature) -> None:
        if creature is self.applier:
            self._expire()


class InfestedPower(Power):
    """When the owner dies, 4 stunned Wrigglers join the fight."""

    id = "infested"
    name = "Infested"
    power_type = PowerType.BUFF

    def on_death(self, creature: Creature) -> None:
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
        # Blockable, unpowered damage from a power (like Thorns).
        DamageCmd.deal(
            self.hooks, self.owner, self.amount, props=DamageProps.NON_CARD_UNPOWERED
        )

    def on_player_turn_end(self, player: Creature) -> None:
        if player is self.owner:
            self._squeeze()

    def on_enemy_side_end(self) -> None:
        if self.owner.side == "enemy" and not self.owner.is_dead:
            self._squeeze()

    def on_death(self, creature: Creature) -> None:
        if creature is self.applier:
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

    def on_player_turn_end(self, player: Creature) -> None:
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


class IllusionPower(Power):
    """The owner cannot truly die: lethal damage leaves it at 1 HP, untargetable,
    and it spends its next turn reviving to full HP. Also marks it as a minion."""

    id = "illusion"
    name = "Illusion"
    power_type = PowerType.BUFF

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

    def should_die(self, creature: Creature) -> bool:
        if creature is self.owner:
            self.is_reviving = True
            return False
        return True

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

    def on_death(self, creature: Creature) -> None:
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
            dealer is self.owner
            and target.side != self.owner.side
            and amount > 0
            and is_powered_attack(props)
        ):
            from .cmds import PowerCmd
            PowerCmd.apply(self.hooks, self.owner, StrengthPower, self.amount)


class SurprisePower(Power):
    """When the owner dies, a Sneaky Gremlin and a Fat Gremlin jump out of the
    crate and join the fight (Gremlin Merc; mirrors SurprisePower.AfterDeath).
    The stolen-gold transfer (Thievery/Heist) is not ported — the sim has no
    gold."""

    id = "surprise"
    name = "Surprise"
    power_type = PowerType.BUFF

    def on_death(self, creature: Creature) -> None:
        if creature is not self.owner:
            return
        from .cmds import CreatureCmd
        from .monsters.underdocks.gremlin_merc import FatGremlin, SneakyGremlin
        rng = self.hooks.combat._rng
        CreatureCmd.add(self.hooks, SneakyGremlin(self.hooks, rng))
        CreatureCmd.add(self.hooks, FatGremlin(self.hooks, rng))


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

    def on_stack(self, amount: int) -> None:
        pass  # single-stack (PowerStackType.Single)

    @staticmethod
    def _is_skill(card: Card) -> bool:
        from .cards import CardType
        return card.card_type == CardType.SKILL

    def _afflict(self, card: Card) -> None:
        from .afflictions import SmogAffliction
        from .cmds import CardCmd
        CardCmd.afflict(card, SmogAffliction, 1)

    def on_card_played(self, card: Card) -> None:
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

    def on_player_turn_start(self, player: Creature) -> None:
        if player is self.owner:
            self._skill_played_this_turn = False

    def on_player_turn_end(self, player: Creature) -> None:
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

    def on_player_turn_end(self, player: Creature) -> None:
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

    def on_enemy_turn_start(self, enemy: Creature) -> None:
        # Mirrors BeforeSideTurnEndVeryEarly: drop Plating on the final
        # sleeping turn so no block is gained at that turn's end.
        if enemy is self.owner and self.amount <= 1:
            self._remove_plating()

    def on_enemy_turn_end(self, enemy: Creature) -> None:
        if enemy is not self.owner:
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
    ) -> int:
        if dealer is self.owner:
            return self.amount
        return 0

    def before_attack(self, dealer: Creature) -> None:
        if dealer is self.owner and self._amount_when_attack_started is None:
            self._amount_when_attack_started = self.amount

    def after_attack(self, dealer: Creature) -> None:
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

    def on_player_turn_start(self, player: Creature) -> None:
        self._damage_received_this_turn = 0

    def on_enemy_turn_start(self, enemy: Creature) -> None:
        if enemy is self.owner:
            self._damage_received_this_turn = 0


class SteamEruptionPower(Power):
    """While present, the owner cannot die: a killing blow instead flips it
    into its ABOUT_TO_BLOW → EXPLODE sequence (Waterfall Giant; mirrors
    SteamEruptionPower.AfterDeath / ShouldStopCombatFromEnding — the game
    lets the death happen but keeps the giant in combat at 999999999 HP; the
    sim prevents the death outright, which is observably the same). The owner
    must implement trigger_about_to_blow()."""

    id = "steam_eruption"
    name = "Steam Eruption"
    power_type = PowerType.BUFF

    def should_die(self, creature: Creature) -> bool:
        if creature is self.owner:
            self.owner.trigger_about_to_blow()
            return False
        return True

    def on_damage_received(
        self,
        target: Creature,
        amount: int,
        dealer: Creature | None,
        card: Card | None,
        props: ValueProp = ValueProp.NONE,
    ) -> None:
        # After a prevented death, restore the game's "infinite HP" display
        # (mirrors CreatureCmd.SetMaxAndCurrentHp(999999999)).
        if target is self.owner and getattr(self.owner, "is_about_to_blow", False):
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

    def on_stack(self, amount: int) -> None:
        pass  # PowerStackType.Single

    def on_damage_received(
        self,
        target: Creature,
        amount: int,
        dealer: Creature | None,
        card: Card | None,
        props: ValueProp = ValueProp.NONE,
    ) -> None:
        if (
            dealer is self.owner
            and target is not self.owner
            and amount == 0
            and ValueProp.MOVE in props
        ):
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

    def on_card_played(self, card: Card) -> None:
        self._cards_played_this_turn += 1
        from .cmds import PowerCmd
        PowerCmd.apply(self.hooks, self.owner, StrengthPower, -1)
        PowerCmd.apply(self.hooks, self.owner, DexterityPower, -1)

    def on_player_turn_end(self, player: Creature) -> None:
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

    def on_enemy_turn_end(self, enemy: Creature) -> None:
        if enemy is self.owner:
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

    def on_enemy_turn_end(self, enemy: Creature) -> None:
        if enemy is self.owner:
            self._count_down(woke_from_damage=False)


class EscapeArtistPower(Power):
    """Visual timer for when the Thieving Hopper will escape; counts down to 1
    at the end of the owner's turn (mirrors EscapeArtistPower — the escape
    itself is the hopper's ESCAPE move)."""

    id = "escape_artist"
    name = "Escape Artist"
    power_type = PowerType.BUFF

    def on_enemy_turn_end(self, enemy: Creature) -> None:
        if enemy is self.owner and self.amount > 1:
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
    ) -> float:
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
            CreatureCmd.stun(self.hooks, self.owner)
            # The stun replaces the telegraphed move: the owner resumes at the
            # move AFTER it (mirrors Stun(owner, StunnedMove,
            # StateLog.Last().GetNextState())).
            machine = getattr(self.owner, "machine", None)
            if machine is not None:
                self.owner._current_move = machine.roll_move(
                    self.owner, self.owner._rng
                )


class SwipePower(Power):
    """Holds the card(s) the Thieving Hopper stole. In the game, killing the
    owner returns the stolen card to the deck as a combat reward; the sim has
    no out-of-combat rewards, so the cards simply stay gone (they were removed
    from the combat piles when stolen)."""

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


class BurrowedPower(Power):
    """The owner's block persists between turns; when its block is broken by
    an attack it is dug out of the ground and loses its next turn (Tunneler;
    mirrors BurrowedPower). The owner must implement get_stunned()."""

    id = "burrowed"
    name = "Burrowed"
    power_type = PowerType.BUFF

    def on_stack(self, amount: int) -> None:
        pass  # PowerStackType.Single

    def should_clear_block(self, creature: Creature) -> bool:
        if creature is self.owner:
            return False
        return True

    def on_block_broken(self, target: Creature) -> None:
        if target is self.owner:
            self.owner.get_stunned()
            self._expire()
            self.owner.block = 0  # AfterRemoved: LoseBlock(all)


class ReattachPower(Power):
    """A Decimillipede segment cannot truly die while another segment stands:
    it withers (unhittable, no move) and reattaches two of its turns later
    with N HP. Killing the last standing segment kills the whole millipede
    (mirrors ReattachPower's ShouldOwnerDeathTriggerFatal — a withered segment
    counts as dead for that check)."""

    id = "reattach"
    name = "Reattach"
    power_type = PowerType.BUFF

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
        return all(
            s.is_dead or s.powers["reattach"].is_reviving
            for s in self._other_segments()
        )

    def should_die(self, creature: Creature) -> bool:
        if creature is not self.owner or self.is_reviving:
            return True
        if self._all_others_down():
            return True  # last segment standing: the death is real
        self.is_reviving = True
        self.owner.enter_dead_state()
        return False

    def should_allow_hitting(self, target: Creature) -> bool:
        if target is self.owner and self.is_reviving:
            return False
        return True

    def do_reattach(self) -> None:
        """Called by the owner's REATTACH move: come back with N HP."""
        if self._all_others_down():
            return  # mirrors DoReattach's AreAllOtherSegmentsDead guard
        self.is_reviving = False
        delta = self.amount - self.owner.hp
        self.owner.hp = self.amount
        self.hooks.on_hp_changed(self.owner, delta)

    def on_death(self, creature: Creature) -> None:
        # The last standing segment died for real: withered segments die too.
        if (
            creature is self.owner
            or not self.is_reviving
            or self.owner.is_dead
            or "reattach" not in creature.powers
            or not self._all_others_down()
        ):
            return
        self.is_reviving = False
        old_hp = self.owner.hp
        self.owner.hp = 0
        self.hooks.on_hp_changed(self.owner, -old_hp)
        self.hooks.on_death(self.owner)


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

    def on_card_played(self, card: Card) -> None:
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

    def on_death(self, creature: Creature) -> None:
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
    ) -> int:
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

    def on_death(self, creature: Creature) -> None:
        if creature is self.owner or creature.side != self.owner.side:
            return
        from .cmds import BlockCmd, PowerCmd
        from .valueprops import ValueProp as VP
        PowerCmd.apply(self.hooks, self.owner, StrengthPower, self.STRENGTH_GAIN)
        BlockCmd.apply(self.hooks, self.owner, self.BLOCK_GAIN, props=VP.UNPOWERED)
        self._expire()


class SurroundedPower(Power):
    """Kaiser Crab: the player faces one arm; the other arm's attacks deal
    50% more damage. Damaging a crab with a targeted card (or potion) turns
    the player to face it; when an arm dies the player faces the survivor.
    The game turns on any targeted card play — the sim approximates with
    single-target card damage (mirrors SurroundedPower)."""

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

    def on_stack(self, amount: int) -> None:
        pass  # PowerStackType.Single

    def modify_damage_multiplicative(
        self,
        target: Creature,
        amount: int,
        dealer: Creature | None,
        card: Card | None,
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

    def on_damage_received(
        self,
        target: Creature,
        amount: int,
        dealer: Creature | None,
        card: Card | None,
        props: ValueProp = ValueProp.NONE,
    ) -> None:
        from .cards import TargetType
        if (
            dealer is self.owner
            and card is not None
            and card.target_type == TargetType.ANY_ENEMY
        ):
            self._update_direction(target)

    def on_potion_used(self, potion, target: Creature | None) -> None:
        if target is not None:
            self._update_direction(target)

    def on_death(self, creature: Creature) -> None:
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
    SandpitPower.AfterRemoved). Frantic Escape adds a stack, delaying it."""

    id = "sandpit"
    name = "Sandpit"
    power_type = PowerType.BUFF

    def on_enemy_turn_start(self, enemy: Creature) -> None:
        if enemy is self.owner:
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

    def on_player_turn_end(self, player: Creature) -> None:
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

    def on_card_played(self, card: Card) -> None:
        self._cards_played_this_turn += 1

    def on_player_turn_start(self, player: Creature) -> None:
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

    def on_card_played(self, card: Card) -> None:
        player = self.owner
        # ModifyCardPlayResultPileTypeAndPosition only redirects Discard → Draw
        # top (power cards leave combat, exhausted cards are already gone).
        if card not in getattr(player, "discard_pile", ()):
            return
        player.discard_pile.remove(card)
        player.draw_pile.append(card)  # list end = top of draw pile
        self._tick()

    def on_player_turn_end(self, player: Creature) -> None:
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
        if player is not self.owner or self.amount < 1:
            return
        from .cards import CardRarity, make_card
        from .cards.pool import pool_card_ids
        from .cmds import CardPileCmd
        combat = self.hooks.combat
        if combat is None:
            return
        commons = [
            cid for cid in pool_card_ids()
            if make_card(cid).rarity == CardRarity.COMMON
        ]
        if not commons:
            return
        n = min(self.amount, len(commons))
        for cid in combat._rng.sample(commons, n):
            CardPileCmd.add_to_hand(self.hooks, player, make_card(cid))


# ── Glory (Act 3) card / enemy powers ──────────────────────────────────────


class StranglePower(Power):
    """For the rest of this turn, whenever the applier plays a card the owner
    takes [amount] unblockable, unpowered damage. Removed at the end of the
    owner's side turn.

    Source: StranglePower.cs — BeforeCardPlayed records the amount for each card
    the applier plays (so it never triggers on the card that applied it), and
    AfterCardPlayed deals that amount to the owner. Applied to a target by the
    Mad Science card's Choking rider (Tinker Time event)."""

    id = "strangle"
    name = "Strangle"
    power_type = PowerType.DEBUFF

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # Cards seen at BeforeCardPlayed → the Strangle amount at that moment
        # (mirrors the source's amountsForPlayedCards). A card only triggers
        # Strangle if it was recorded here, so the card that applied Strangle —
        # already past its BeforeCardPlayed — never triggers it on itself.
        self._amounts: dict[int, int] = {}

    def before_card_played(self, card: Card) -> None:
        self._amounts[id(card)] = self.amount

    def on_card_played(self, card: Card) -> None:
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

    Source: ImprovementPower.cs — AfterCombatEnd upgrades Amount random
    upgradable cards in the deck. Applied by the Mad Science card's Improvement
    rider (Tinker Time event). The sim fights over a deep-copied deck and does
    not sync card upgrades back to the run, so the after-combat upgrade is a
    documented no-op here (the power is modelled so the rider is constructible
    and its in-combat presence is faithful)."""

    id = "improvement"
    name = "Improvement"
    power_type = PowerType.BUFF


class BattlewornDummyTimeLimitPower(Power):
    """At the end of the owner's turn, count down; at 0 the owner flees.

    Source: BattlewornDummyTimeLimitPower.cs — AfterSideTurnEnd decrements while
    Amount > 1, otherwise flags the encounter as RanOutOfTime and Escapes the
    owner. Applied to the Battle Friend dummies (Battleworn Dummy event); if the
    player cannot destroy the dummy in time it escapes and no reward is given."""

    id = "battleworn_dummy_time_limit"
    name = "Time Limit"
    power_type = PowerType.BUFF

    def on_enemy_turn_end(self, enemy: Creature) -> None:
        if enemy is not self.owner:
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
            dealer is self.owner
            and target.side == "player"
            and amount > 0
            and is_powered_attack(props)
        ):
            from .cmds import CreatureCmd
            CreatureCmd.lose_max_hp(self.hooks, target, self.amount)


class StockPower(Power):
    """When the owner dies, a fresh Axebot spawns in its place with one fewer
    Stock (Axebot; mirrors StockPower.AfterDeath + ShouldStopCombatFromEnding).
    The replacement boots up before attacking."""

    id = "stock"
    name = "Stock"
    power_type = PowerType.BUFF

    def on_death(self, creature: Creature) -> None:
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

    def on_player_turn_start(self, player: Creature) -> None:
        combat = self.hooks.combat
        if combat is None:
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

    def on_card_played(self, card: Card) -> None:
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

    def on_stack(self, amount: int) -> None:
        pass  # PowerStackType.Single

    def modify_damage_multiplicative(
        self,
        target: Creature,
        amount: int,
        dealer: Creature | None,
        card: Card | None,
    ) -> float:
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

    def on_death(self, creature: Creature) -> None:
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
    level; the upgrades are restored when the applier dies (Magi Knight;
    mirrors DampenPower). Does not stack."""

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
        for card in getattr(owner, "all_cards", ()):
            if card.upgrade_level > 0 and card not in self._downgraded:
                self._downgraded[card] = card.upgrade_level
                card.downgrade()

    def on_stack(self, amount: int) -> None:
        pass  # PowerStackType.None

    def on_death(self, creature: Creature) -> None:
        if creature is not self.applier:
            return
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

    def on_stack(self, amount: int) -> None:
        pass  # PowerStackType.Single

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

    def on_death(self, creature: Creature) -> None:
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
    (mirrors WitheringPresencePower). The display counter starts at N (6)."""

    id = "withering_presence"
    name = "Withering Presence"
    power_type = PowerType.BUFF

    def __init__(
        self,
        owner: Creature,
        amount: int,
        hooks: HookSystem,
        applier: Creature | None = None,
    ) -> None:
        super().__init__(owner, amount, hooks, applier)
        self._cards_left = amount

    def on_card_played(self, card: Card) -> None:
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
        for _ in range(getattr(self.owner, "wither_upgrade_count", 0)):
            wither.fake_upgrade()
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

    def on_card_played(self, card: Card) -> None:
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

    def __init__(
        self,
        owner: Creature,
        amount: int,
        hooks: HookSystem,
        applier: Creature | None = None,
    ) -> None:
        super().__init__(owner, amount, hooks, applier)
        self.is_reviving = False

    def on_stack(self, amount: int) -> None:
        pass  # PowerStackType.Single

    def should_die(self, creature: Creature) -> bool:
        if creature is not self.owner:
            return True
        self.is_reviving = True
        self.owner.trigger_dead_state()
        return False

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
            dealer is self.owner
            and target.side == "player"
            and amount > 0
            and is_powered_attack(props)
        ):
            from .cards import WoundCard
            from .cmds import CardPileCmd
            for _ in range(self.amount):
                CardPileCmd.add_to_discard(self.hooks, target, WoundCard())


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

    def on_stack(self, amount: int) -> None:
        pass  # PowerStackType.Single

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
    internal cards-left counter; the counter resets to 10 after firing)."""

    id = "automation"
    name = "Automation"
    power_type = PowerType.BUFF
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

    def on_card_played(self, card: Card) -> None:
        from .cards import CardType
        from .cards.pool import random_pool_cards
        from .cmds import CardPileCmd
        if card.card_type != CardType.ATTACK:
            return
        combat = self.hooks.combat
        if combat is None or combat.is_over:
            return
        for new_card in random_pool_cards(combat._rng, self.amount, CardType.ATTACK):
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
        self, target: Creature, amount: int, card: Card | None
    ) -> int:
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

    def on_player_turn_started(self, player: Creature) -> None:
        if player is not self.owner:
            return
        combat = self.hooks.combat
        for _ in range(self.amount):
            if combat.is_over or player.is_dead:
                return
            if not player.draw_pile and player.discard_pile:
                player.reshuffle_discard_into_draw()
            if not player.draw_pile:
                return
            combat.auto_play_card(player.draw_pile[-1])


class NostalgiaPower(Power):
    """The first N Attacks or Skills played each turn return to the top of
    the draw pile instead of the discard pile (mirrors NostalgiaPower's
    ModifyCardPlayResultPileTypeAndPosition)."""

    id = "nostalgia"
    name = "Nostalgia"
    power_type = PowerType.BUFF

    def modify_card_play_result_pile(self, card: Card, pile: str) -> str:
        from .cards import CardType
        from .history import CardPlayedEntry
        if pile != "discard" or card.card_type not in (
            CardType.ATTACK, CardType.SKILL
        ):
            return pile
        combat = self.hooks.combat
        # Plays already finished this turn (the current play is recorded
        # after this hook, so it is not counted against the allowance).
        finished = sum(
            1
            for e in combat.history.of_type(CardPlayedEntry, this_turn=True)
            if e.card.card_type in (CardType.ATTACK, CardType.SKILL)
        )
        if finished >= self.amount:
            return pile
        return "draw_top"


class PanachePower(Power):
    """Every 5 cards played after this power, deal N unpowered damage to ALL
    enemies; the 5-count resets when it fires and at the end of the turn
    (mirrors PanachePower — the Panache play itself is not counted)."""

    id = "panache"
    name = "Panache"
    power_type = PowerType.BUFF
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

    def on_card_played(self, card: Card) -> None:
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

    def on_player_turn_end(self, player: Creature) -> None:
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
        self, target: Creature, amount: int, card: Card | None
    ) -> float:
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

    def on_player_turn_started(self, player: Creature) -> None:
        from .cmds import PowerCmd
        if player is self.owner:
            PowerCmd.apply(self.hooks, self.owner, VigorPower, self.amount)


class RollingBoulderPower(Power):
    """At the start of each of the owner's turns, deal N unpowered damage to
    ALL enemies, then N grows by 5 (mirrors RollingBoulderPower's
    AfterPlayerTurnStart damage + SetAmount)."""

    id = "rolling_boulder"
    name = "Rolling Boulder"
    power_type = PowerType.BUFF
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
    shortest fuse."""

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
    drawback; mirrors TheGambitPower.AfterDamageReceived). Single stack."""

    id = "the_gambit"
    name = "The Gambit"
    power_type = PowerType.DEBUFF

    def on_stack(self, amount: int) -> None:
        pass  # PowerStackType.Single

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
    ]
}
