"""Powers — buffs and debuffs, mirroring STS2's PowerModel (src/Core/Models/
Powers).

Every power subclasses `Power` and overrides only the hook methods it needs;
the HookSystem calls them by duck-typing. `PowerCmd.apply` (cmds.py) handles
stacking, Artifact interception of debuffs, and registration; `_tick` /
`_tick_duration` handle duration decrement and `_expire` unregisters.

Organised into sections: Buffs, Debuffs, Ironclad card powers, Overgrowth
(Act 1) enemy powers, and Hive (Act 2) enemy powers, followed by the
`ALL_POWERS` id→class registry at the bottom.
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
    held when the attack started are consumed once it finishes (Terror Eel;
    mirrors VigorPower.BeforeAttack/ModifyDamageAdditive/AfterAttack).

    The attack boundary comes from Monster._execute_attack, so only monster
    attacks consume Vigor — nothing in the sim grants the player Vigor."""

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
    ]
}
