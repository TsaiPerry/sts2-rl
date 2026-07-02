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
        return mult

    def on_enemy_side_end(self) -> None:
        self._tick()


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
        self._tick()


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
        self._tick()


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

    def on_block_gained(self, target: Creature, amount: int) -> None:
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
    from the combat's attack-play count, mirroring the CombatHistory seed in
    AfterApplied)."""

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
            combat.attacks_played_this_turn if combat is not None else 0
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
    first turn of combat). The game's enemies-start-with-block special case
    is not ported (no sim enemy starts with Plating)."""

    id = "plating"
    name = "Plating"
    power_type = PowerType.BUFF

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

    def should_play_card(self, card: Card) -> bool:
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
    ]
}
