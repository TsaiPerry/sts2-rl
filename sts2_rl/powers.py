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
    ]
}
