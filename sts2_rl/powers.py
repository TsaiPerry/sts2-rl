from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

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
        heal = min(self.amount, self.owner.max_hp - self.owner.hp)
        if heal > 0:
            self.owner.hp += heal
            self.hooks.on_hp_changed(self.owner, heal)
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
    """Gain 1 Strength whenever the owner loses HP from damage."""

    id = "rupture"
    name = "Rupture"
    power_type = PowerType.BUFF

    def on_damage_received(
        self,
        target: Creature,
        amount: int,
        dealer: Creature | None,
        card: Card | None,
    ) -> None:
        if target is self.owner and amount > 0:
            from .cmds import StrengthCmd
            StrengthCmd.apply(self.hooks, self.owner, 1)


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
    """Reflect N unblockable damage to the attacker when the owner is hit."""

    id = "thorns"
    name = "Thorns"
    power_type = PowerType.BUFF

    def on_damage_received(
        self,
        target: Creature,
        amount: int,
        dealer: Creature | None,
        card: Card | None,
    ) -> None:
        if target is not self.owner or dealer is None:
            return
        # Bypass block — apply HP loss directly to the attacker
        old_hp = dealer.hp
        dealer.hp = max(0, dealer.hp - self.amount)
        hp_lost = old_hp - dealer.hp
        if hp_lost > 0:
            self.hooks.on_hp_changed(dealer, -hp_lost)
            if dealer.hp <= 0 and self.hooks.should_die(dealer):
                self.hooks.on_death(dealer)


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
    """Target takes 50% more damage. Ticks at the end of the enemy's turn."""

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
        if target is self.owner:
            return 1.5
        return 1.0

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
        old_hp = self.owner.hp
        self.owner.hp = max(0, self.owner.hp - self.amount)
        hp_lost = old_hp - self.owner.hp
        if hp_lost > 0:
            self.hooks.on_hp_changed(self.owner, -hp_lost)
            if self.owner.hp <= 0:
                if self.hooks.should_die(self.owner):
                    self.hooks.on_death(self.owner)
                else:
                    self.owner.hp = 1
        self.hooks.on_damage_received(self.owner, hp_lost, None, None)
        self._tick()

    def on_enemy_turn_start(self, enemy: Creature) -> None:
        if self.owner is enemy:
            self._apply_poison()

    def on_player_turn_start(self, player: Creature) -> None:
        if self.owner is player:
            self._apply_poison()


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
        from .monsters.overgrowth.phrog_parasite import Wriggler
        for i in range(4):
            combat.enemies.append(
                Wriggler(self.hooks, combat._rng, start_stunned=True, slot=i + 1)
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
        DamageCmd.deal(self.hooks, self.owner, self.amount)

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
        healed = self.owner.max_hp - self.owner.hp
        if healed > 0:
            self.owner.hp = self.owner.max_hp
            self.hooks.on_hp_changed(self.owner, healed)


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
