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

    def before_card_played(self, card: Card) -> None:
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


ALL_ENCHANTMENTS: dict[str, type[Enchantment]] = dict(_ENCHANTMENT_CLASSES)
