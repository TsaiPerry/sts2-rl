"""Card enchantments, mirroring STS2's EnchantmentModel
(src/Core/Models/Enchantments) — only the ones granted by implemented events.

An enchantment is attached to exactly one card (CardModel.Enchantment) and
lives on it for the rest of the run. In combat it is a hook listener like the
card itself: CombatState registers `card.enchantment` at setup (with a combat
back-reference) and resets its per-combat status, mirroring how the game
clones canonical enchantments into each combat with Status = Normal.

Eligibility (EnchantmentModel.CanEnchant): not a Status/Curse/Quest card, not
an Unplayable deck card, and at most one enchantment per card. Subclasses add
their own restrictions (Slither excludes X-cost cards).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .cards import Card
    from .combat import CombatState
    from .creatures import Creature


_ENCHANTMENT_CLASSES: dict[str, type[Enchantment]] = {}


def register_enchantment(cls: type[Enchantment]) -> type[Enchantment]:
    _ENCHANTMENT_CLASSES[cls.id] = cls
    return cls


def make_enchantment(enchantment_id: str) -> Enchantment:
    return _ENCHANTMENT_CLASSES[enchantment_id]()


class Enchantment:
    """Base class for enchantments (mirrors EnchantmentModel)."""

    id: str
    name: str

    def __init__(self, amount: int = 1) -> None:
        self.amount = amount
        # Mirrors EnchantmentStatus: Disabled after a once-per-combat effect
        # fires; reset to Normal each combat (the game re-clones the canonical
        # enchantment, whose status is always Normal).
        self.disabled = False
        self.card: Card | None = None
        self.combat: CombatState | None = None

    @classmethod
    def can_enchant(cls, card: Card) -> bool:
        """Mirrors EnchantmentModel.CanEnchant: no Status/Curse/Quest cards,
        no Unplayable deck cards, one enchantment per card."""
        from .cards import CardType

        if card.card_type in (CardType.STATUS, CardType.CURSE, CardType.QUEST):
            return False
        if not card.is_playable:
            return False
        return card.enchantment is None

    def attach(self, card: Card) -> None:
        """Attach this enchantment to a card for the rest of the run."""
        if not self.can_enchant(card):
            raise ValueError(f"{self.name} cannot enchant {card!r}")
        self.card = card
        card.enchantment = self

    def reset(self) -> None:
        """Reset per-combat status (called by CombatState at setup)."""
        self.disabled = False

    def __repr__(self) -> str:
        return self.name


@register_enchantment
class SownEnchantment(Enchantment):
    """Sown — the first time the enchanted card is played each combat, gain
    [amount] energy.

    Source: Sown.cs — OnPlay: if Status == Normal, GainEnergy(Amount), then
    Status = Disabled. Granted by the Sapphire Seed event (amount 1).
    """

    id = "sown"
    name = "Sown"

    def before_card_played(self, card: Card, target: Creature | None = None) -> None:
        if card is not self.card or self.disabled:
            return
        from .cmds import EnergyCmd

        EnergyCmd.gain(self.combat.hooks, self.combat.player, self.amount)
        self.disabled = True


@register_enchantment
class SlitherEnchantment(Enchantment):
    """Slither — whenever the enchanted card is drawn, its cost becomes a
    random value from 0 to 3 for the rest of the combat.

    Source: Slither.cs — AfterCardDrawn: EnergyCost.SetThisCombat(NextInt(4));
    CanEnchant additionally excludes Unplayable and X-cost cards. Granted by
    the Wood Carvings event.
    """

    id = "slither"
    name = "Slither"

    @classmethod
    def can_enchant(cls, card: Card) -> bool:
        return super().can_enchant(card) and not card.energy_cost_x

    def on_card_drawn(self, card: Card, from_hand_draw: bool = False) -> None:
        if card is not self.card:
            return
        card.set_cost_this_combat(self.combat._rng.randrange(4))


@register_enchantment
class SteadyEnchantment(Enchantment):
    """Steady — the enchanted card gains Retain.

    Source: Steady.cs — OnEnchant: AddKeyword(Retain). Granted by the
    Waterlogged Scriptorium event (Tentacle Quill / Prickly Sponge). Retain is
    a static card property, so this sets it at enchant time and re-asserts it
    each combat (the card is deep-copied per combat).
    """

    id = "steady"
    name = "Steady"

    def attach(self, card: Card) -> None:
        super().attach(card)
        card.retain = True

    def reset(self) -> None:
        super().reset()
        if self.card is not None:
            self.card.retain = True


@register_enchantment
class SpiralEnchantment(Enchantment):
    """Spiral — the enchanted card is played 1 extra time.

    Source: Spiral.cs — EnchantPlayCount: original + Times(1). CanEnchant is
    restricted to Basic cards tagged Strike or Defend. Granted by the
    Spiraling Whirlpool event.
    """

    id = "spiral"
    name = "Spiral"

    @classmethod
    def can_enchant(cls, card: Card) -> bool:
        from .cards import CardRarity

        if not super().can_enchant(card):
            return False
        return card.rarity == CardRarity.BASIC and (
            "strike" in card.tags or "defend" in card.tags
        )

    def modify_card_play_count(self, card: Card, target, count: int) -> int:
        if card is self.card:
            return count + self.amount
        return count


@register_enchantment
class PerfectFitEnchantment(Enchantment):
    """Perfect Fit — after the draw pile is reshuffled, this card is placed on
    top of the draw pile (drawn next).

    Source: PerfectFit.cs — ModifyShuffleOrder (non-initial): move the card to
    the front of the shuffle. Granted by the Field of Man-Sized Holes event.
    The sim draws from the end of draw_pile, so "top" = list end.
    """

    id = "perfect_fit"
    name = "Perfect Fit"

    def on_shuffle(self, player) -> None:
        if self.card is not None and self.card in player.draw_pile:
            player.draw_pile.remove(self.card)
            player.draw_pile.append(self.card)  # list end = top of draw pile


@register_enchantment
class SoulsEnchantment(Enchantment):
    """Souls — removes the enchanted card's Exhaust keyword.

    Source: SoulsPower.cs — CanEnchant additionally requires the card to have
    Exhaust; OnEnchant removes it. Granted by the Grave of the Forgotten event
    (Confront). Exhaust is a static card property, so this clears it at enchant
    time and re-asserts the clear each combat (the card is deep-copied per
    combat)."""

    id = "souls"
    name = "Souls"

    @classmethod
    def can_enchant(cls, card: Card) -> bool:
        return super().can_enchant(card) and card.exhausts

    def attach(self, card: Card) -> None:
        super().attach(card)
        card.exhausts = False

    def reset(self) -> None:
        super().reset()
        if self.card is not None:
            self.card.exhausts = False


@register_enchantment
class GlamEnchantment(Enchantment):
    """Glam — the first time the enchanted card is played each combat, it is
    played [amount] extra time(s).

    Source: Glam.cs — EnchantPlayCount: original + Times(1) while not used;
    AfterCardPlayed (own card): mark used, Status = Disabled. Granted by
    Silken Tress on the first card reward's options.
    """

    id = "glam"
    name = "Glam"

    def modify_card_play_count(self, card: Card, target, count: int) -> int:
        if card is self.card and not self.disabled:
            return count + self.amount
        return count

    def on_card_played(self, card: Card) -> None:
        if card is self.card:
            self.disabled = True


@register_enchantment
class ImbuedEnchantment(Enchantment):
    """Imbued — the enchanted Skill auto-plays itself on turn 1.

    Source: Imbued.cs — CanEnchantCardType == Skill; AfterAutoPrePlayPhase-
    Entered (turn ≤ 1) auto-plays the card. The sim fires it from the post-draw
    turn-start slot (on_player_turn_started) on turn 1. Granted by Electric
    Shrymp (Orobas). ShouldStartAtBottomOfDrawPile is cosmetic and not modeled.
    """

    id = "imbued"
    name = "Imbued"

    @classmethod
    def can_enchant(cls, card: Card) -> bool:
        from .cards import CardType

        return super().can_enchant(card) and card.card_type == CardType.SKILL

    def on_player_turn_started(self, player) -> None:
        if (
            self.card is not None
            and self.combat.turn == 1
            and self.card in player.hand
        ):
            self.combat.auto_play(self.card)


@register_enchantment
class GoopyEnchantment(Enchantment):
    """Goopy — the enchanted Defend card gains Exhaust and, each time it is
    played, permanently grants +1 additional Block on later plays.

    Source: Goopy.cs — CanEnchant requires the Defend tag; OnEnchant adds
    Exhaust; EnchantBlockAdditive returns Amount-1; AfterCardPlayed (own card)
    Amount++. Granted by Pael's Claw (amount 1). The sim grows Amount within a
    combat; run-level persistence of the growth (the game syncs DeckVersion)
    is a documented simplification of the per-combat-cloned enchantment model.
    """

    id = "goopy"
    name = "Goopy"

    @classmethod
    def can_enchant(cls, card: Card) -> bool:
        return super().can_enchant(card) and "defend" in card.tags

    def attach(self, card: Card) -> None:
        super().attach(card)
        card.exhausts = True

    def reset(self) -> None:
        super().reset()
        if self.card is not None:
            self.card.exhausts = True

    def modify_block_additive(self, target, amount: int, card: Card | None) -> int:
        if card is self.card:
            return self.amount - 1
        return 0

    def on_card_played(self, card: Card) -> None:
        if card is self.card:
            self.amount += 1


@register_enchantment
class TezcatarasEmberEnchantment(Enchantment):
    """Tezcatara's Ember — the enchanted card costs 0, gains Eternal, and deals
    +3 damage on powered attacks.

    Source: TezcatarasEmber.cs — OnEnchant sets cost to 0 and adds Eternal;
    EnchantDamageAdditive returns DamageVar(3) on powered attacks. Granted by
    Nutritious Soup on Basic Strikes.
    """

    id = "tezcataras_ember"
    name = "Tezcatara's Ember"
    damage = 3

    def attach(self, card: Card) -> None:
        super().attach(card)
        card._energy_cost = 0
        card.eternal = True

    def reset(self) -> None:
        super().reset()
        if self.card is not None:
            self.card._energy_cost = 0
            self.card.eternal = True

    def modify_damage_additive(self, target, amount: int, dealer, card: Card | None) -> int:
        # DamageCmd only calls this hook for powered attacks.
        if card is self.card:
            return self.damage
        return 0


@register_enchantment
class SwiftEnchantment(Enchantment):
    """Swift — the first time the enchanted card is played each combat, draw
    [amount] cards.

    Source: Swift.cs — OnPlay: if Status Normal, Draw(Amount), Status Disabled.
    Granted by Beautiful Bracelet (amount 3).
    """

    id = "swift"
    name = "Swift"

    def on_card_played(self, card: Card) -> None:
        if card is self.card and not self.disabled:
            from .cmds import DrawCmd

            DrawCmd.draw(self.combat.player, self.amount)
            self.disabled = True


@register_enchantment
class InstinctEnchantment(Enchantment):
    """Instinct — the enchanted Attack deals double damage.

    Source: Instinct.cs — CanEnchantCardType == Attack; EnchantDamage-
    Multiplicative returns 2 on powered attacks. Granted by Tri-Boomerang.
    """

    id = "instinct"
    name = "Instinct"

    @classmethod
    def can_enchant(cls, card: Card) -> bool:
        from .cards import CardType

        return super().can_enchant(card) and card.card_type == CardType.ATTACK

    def modify_damage_multiplicative(
        self, target, amount: int, dealer, card: Card | None
    ) -> float:
        # DamageCmd only calls this hook for powered attacks.
        if card is self.card:
            return 2
        return 1


@register_enchantment
class SharpEnchantment(Enchantment):
    """Sharp — the enchanted Attack deals +[amount] damage.

    Source: Sharp.cs — CanEnchantCardType == Attack; EnchantDamageAdditive
    returns Amount on powered attacks. Granted by the Self Help Book event
    (amount 2).
    """

    id = "sharp"
    name = "Sharp"

    @classmethod
    def can_enchant(cls, card: Card) -> bool:
        from .cards import CardType

        return super().can_enchant(card) and card.card_type == CardType.ATTACK

    def modify_damage_additive(self, target, amount: int, dealer, card: Card | None) -> int:
        # DamageCmd only calls this hook for powered attacks.
        if card is self.card:
            return self.amount
        return 0


@register_enchantment
class NimbleEnchantment(Enchantment):
    """Nimble — the enchanted card gains +[amount] Block.

    Source: Nimble.cs — CanEnchant additionally requires CardModel.GainsBlock
    (an explicit per-card declaration in the source, mirrored as
    `Card.gains_block`); EnchantBlockAdditive returns Amount. Granted by the
    Self Help Book event (amount 2).
    """

    id = "nimble"
    name = "Nimble"

    @classmethod
    def can_enchant(cls, card: Card) -> bool:
        return super().can_enchant(card) and card.gains_block

    def modify_block_additive(self, target, amount: int, card: Card | None) -> int:
        if card is self.card:
            return self.amount
        return 0


@register_enchantment
class VigorousEnchantment(Enchantment):
    """Vigorous — the FIRST play of the enchanted Attack deals +[amount]
    damage; afterwards the bonus is spent for the rest of the combat.

    Source: Vigorous.cs — CanEnchantCardType == Attack; EnchantDamageAdditive
    returns Amount only while Status == Normal and the attack is powered;
    AfterCardPlayed (own card) sets Status = Disabled. Granted by the Stone
    of All Time event (amount 8).
    """

    id = "vigorous"
    name = "Vigorous"

    @classmethod
    def can_enchant(cls, card: Card) -> bool:
        from .cards import CardType

        return super().can_enchant(card) and card.card_type == CardType.ATTACK

    def modify_damage_additive(self, target, amount: int, dealer, card: Card | None) -> int:
        # DamageCmd only calls this hook for powered attacks.
        if card is self.card and not self.disabled:
            return self.amount
        return 0

    def on_card_played(self, card: Card) -> None:
        if card is self.card:
            self.disabled = True


@register_enchantment
class CorruptedEnchantment(Enchantment):
    """Corrupted — the enchanted Attack deals 1.5x damage, but playing it
    costs you 2 HP.

    Source: Corrupted.cs — CanEnchantCardType == Attack;
    EnchantDamageMultiplicative returns 1.5 on powered attacks; OnPlay deals
    2 Unblockable|Unpowered|Move damage to the card's owner. Granted by the
    Symbiote event (amount 1).
    """

    id = "corrupted"
    name = "Corrupted"
    self_damage = 2

    @classmethod
    def can_enchant(cls, card: Card) -> bool:
        from .cards import CardType

        return super().can_enchant(card) and card.card_type == CardType.ATTACK

    def modify_damage_multiplicative(
        self, target, amount: int, dealer, card: Card | None
    ) -> float:
        # DamageCmd only calls this hook for powered attacks.
        if card is self.card:
            return 1.5
        return 1

    def before_card_played(self, card: Card, target: Creature | None = None) -> None:
        if card is not self.card:
            return
        from .cmds import DamageCmd
        from .valueprops import ValueProp

        DamageCmd.deal(
            self.combat.hooks, self.combat.player, self.self_damage,
            props=ValueProp.UNBLOCKABLE | ValueProp.UNPOWERED | ValueProp.MOVE,
            card=card,
        )


@register_enchantment
class CloneEnchantment(Enchantment):
    """Clone — inert on its own; marks a card for the Clone rest-site option
    (Pael's Growth) to duplicate. Source: Clone.cs (no combat behavior).
    """

    id = "clone"
    name = "Clone"


ALL_ENCHANTMENTS: dict[str, type[Enchantment]] = dict(_ENCHANTMENT_CLASSES)
