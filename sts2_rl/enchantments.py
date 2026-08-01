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

from .hooks import CAT_CARD
from .valueprops import is_powered_attack

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
    # The game reaches an enchantment through the card that owns it
    # (CombatState.cs:462-465 adds it immediately after the card), so it shares
    # the card slot. `HookSystem._ordered` emits it right after its own card as
    # part of the pile walk; this is only the fallback slot hint for an
    # enchantment whose card is in no pile.
    hook_category = CAT_CARD
    # Rides on a card rather than sitting in a pile itself: `HookSystem` counts
    # these so it can splice the four piles in wholesale when there are none.
    hook_is_card_rider = True

    def hook_contains(self) -> bool:
        """`CombatState.Contains`' EnchantmentModel arm (CombatState.cs:589):
        `HasCard && !Card.HasBeenRemovedFromState && Card.Owner.IsActiveForHooks`.

        `HasCard` is `_card != null` (EnchantmentModel.cs:154) — an enchantment
        detached from its card is not a listener even while it is still
        registered.
        """
        card = self.card
        return card is not None and card.hook_contains()

    # Hook.ModifyDamage / Hook.ModifyBlock apply the SOURCE CARD's enchantment
    # to the running amount before either listener loop (Hook.cs:1487-1499,
    # 1315-1320), so these are not hooks and are never dispatched: DamageCmd /
    # BlockCmd call them directly on `card.enchantment`. Defaults are no-ops.

    def on_play(self, card: Card, target: Creature | None = None) -> None:
        """EnchantmentModel.OnPlay — CardModel.cs:1937-1945 calls it DIRECTLY
        inside the per-Replay loop, after the card's own OnPlay (:1931) and
        before Hook.AfterCardPlayed (:1959). It is not a hook.

        The sim wired its two implementers to `before_card_played`, which is
        wrong twice over: the position (a Corrupted Strike with Rupture 1 dealt
        10 in the sim and 9 in the game, because the self-damage fired first
        and Rupture's +1 Strength landed on the Strike) and the count (under
        Throwing Axe the card is played twice and the game takes 4 self-damage
        where the sim took 2).
        """

    def enchant_damage_additive(self, amount: int, props) -> int:
        return 0

    def enchant_damage_multiplicative(self, amount: int, props) -> float:
        return 1

    def enchant_block_additive(self, amount: int, props) -> int:
        return 0

    def enchant_block_multiplicative(self, amount: int, props) -> float:
        return 1

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

    def modify_shuffle_order(self, player, cards: list,
                             is_initial_shuffle: bool) -> None:
        """`AbstractModel.ModifyShuffleOrder` — mutate the shuffled list IN
        PLACE. No-op by default; Perfect Fit is the sim's only implementer."""

    def modify_card(self) -> None:
        """Mirrors EnchantmentModel.ModifyCard (EnchantmentModel.cs:355-364)
        -> OnEnchant: run this enchantment's modification logic on its card.
        The game calls it when the card is first enchanted, when a downgrade
        re-derives the card from its canonical model
        (CardModel.DowngradeInternal, CardModel.cs:2145) and after a load; the
        sim calls it from the same places plus the per-combat reset. No-op by
        default -- only enchantments that mutate a static card property
        override it."""

    def clone_preserving_mutability(self) -> "Enchantment":
        """Mirrors AbstractModel.ClonePreservingMutability for the enchantment
        copy CardModel.DeepCloneFields makes (CardModel.cs:1204-1209): a fresh,
        unattached instance carrying the source's Amount and Status
        (MemberwiseClone keeps _status; DeepCloneFields only nulls _card)."""
        clone = make_enchantment(self.id)
        clone.amount = self.amount
        clone.disabled = self.disabled
        return clone

    def attach(self, card: Card) -> None:
        """`CardCmd.Enchant` -> `CardModel.EnchantInternal` (CardModel.cs:1491-1498)
        PLUS `ModifyCard` — the normal enchant path, which is the only one that
        checks CanEnchant."""
        if not self.can_enchant(card):
            raise ValueError(f"{self.name} cannot enchant {card!r}")
        self.attach_internal(card)
        self.modify_card()

    def attach_internal(self, card: Card) -> None:
        """`CardModel.EnchantInternal` alone (CardModel.cs:1491-1498), i.e.
        `Enchantment = e; e.ApplyInternal(this, amount)` — no CanEnchant test
        and NO `ModifyCard`.

        This is the form `DeepCloneFields` uses (CardModel.cs:1204-1209), and
        `EnchantmentModel.ModifyCard`'s own doc comment says why in as many
        words: "It is NOT called when a card is cloned, because the
        enchantment's effects will already be reflected in the card's values."
        Re-running it on a clone is not merely redundant — it is unreachable
        for the enchantments whose `CanEnchant` tests a property their own
        `ModifyCard` clears, which is Souls (it removes Exhaust from a card
        that must have had it).
        """
        self.card = card
        card.enchantment = self
        # The game's enchantment has NO combat field: it reaches the combat
        # through `base.Card.Owner.Creature` (Adroit.cs:21), i.e. off the card
        # it is attached to. The sim caches the pointer instead, so the cache
        # has to be re-derived whenever the attachment moves — otherwise a
        # mid-combat clone's enchantment copy (cards/base.py's `create_clone`
        # -> `attach_internal`) is left with `combat = None` and every OnPlay
        # that needs the combat raises. A run-level enchant sets it to None,
        # which is right; combat setup then fills it in (combat.py).
        self.combat = card.combat

    def reset(self) -> None:
        """Reset per-combat status (called by CombatState at setup)."""
        self.disabled = False
        if self.card is not None:
            self.modify_card()

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

    def on_play(self, card: Card, target: Creature | None = None) -> None:
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
        # Slither.cs:55-62 rolls on `Owner.RunState.Rng.CombatEnergyCosts.
        # NextInt(4)`. The port used `combat._rng`, the shared combat Random, so a
        # parity run both took a number off a stream the game never touches AND
        # failed to advance CombatEnergyCosts — desyncing every later cost roll,
        # Snecko Oil included. potions.py already uses `combat_rng.energy` for
        # Snecko Oil, which is the SAME C# call. Legacy maps every accessor onto
        # the one shared Random, so nothing changes for RL play.
        card.set_cost_this_combat(self.combat.combat_rng.energy.randrange(4))


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

    def modify_card(self) -> None:
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

    def modify_shuffle_order(self, player, cards: list,
                             is_initial_shuffle: bool) -> None:
        # PerfectFit.cs:10-16 — `if (!isInitialShuffle && cards.Contains(Card))
        # { cards.Remove(Card); cards.Insert(0, Card); }`. The initial-shuffle
        # early return is the source's, and the sim's list is top-at-END, so
        # C#'s Insert(0) is an append here.
        #
        # This used to be `on_shuffle` = Hook.AfterShuffle, a DIFFERENT hook
        # (CardPileCmd.cs:917, after the pile is rebuilt). The substitution
        # worked for a lone enchanted card and broke for two, because which of
        # two competing listeners lands its card on top is decided by DISPATCH
        # ORDER — see HookSystem.modify_shuffle_order.
        if is_initial_shuffle or self.card is None:
            return
        if self.card in cards:
            cards.remove(self.card)
            cards.append(self.card)


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

    def modify_card(self) -> None:
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

    def on_card_played(self, card: Card,
                       is_auto_play: bool = False) -> None:
        if card is self.card:
            self.disabled = True


@register_enchantment
class ImbuedEnchantment(Enchantment):
    """Imbued — the enchanted Skill auto-plays itself on turn 1.

    Source: Imbued.cs — CanEnchantCardType == Skill; AfterAutoPrePlayPhase-
    Entered (turn ≤ 1) auto-plays the card. The sim fires it from the post-draw
    turn-start slot (on_player_turn_started) on turn 1. Granted by Electric
    Shrymp (Orobas).
    """

    id = "imbued"
    name = "Imbued"
    # Imbued.cs:11 is the ONLY ShouldStartAtBottomOfDrawPile implementer in the
    # whole decompiled game, and it is not cosmetic: CombatManager.cs:657-663
    # sinks the card before the turn-1 Innate pass, so it never occupies an
    # opening-hand slot. Observed over 30 seeds with a 9-Strike + 1-Imbued-
    # Defend deck, the sim's turn-1 hand was 4 cards in 17 of them.
    should_start_at_bottom_of_draw_pile = True

    @classmethod
    def can_enchant(cls, card: Card) -> bool:
        from .cards import CardType

        return super().can_enchant(card) and card.card_type == CardType.SKILL

    def after_auto_pre_play_phase_entered(self, player) -> None:
        """Imbued.cs:19-25 — AfterAutoPrePlayPhaseEntered, guarded only by
        `player == Card.Owner && TurnNumber <= 1`.

        The sim carried an extra `self.card in player.hand` clause C# does not
        have. That was survivable while the card could turn up in the opening
        hand; once the turn-1 ShouldStartAtBottomOfDrawPile pass was ported
        (turn_structure/G14) the card is guaranteed NOT to be in hand, and the
        extra clause turned Imbued into a no-op. The bottom-of-pile pass exists
        precisely SO the card is auto-played from the draw pile rather than
        occupying an opening-hand slot — `CardCmd.AutoPlay` takes it from
        whichever pile holds it.
        """
        if self.card is None or self.combat is None:
            return
        if self.combat.turn > 1:
            return
        self.combat.auto_play_card(self.card)


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

    def modify_card(self) -> None:
        self.card.exhausts = True

    def enchant_block_additive(self, amount: int, props) -> int:
        return self.amount - 1

    def on_card_played(self, card: Card,
                       is_auto_play: bool = False) -> None:
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

    def modify_card(self) -> None:
        self.card._energy_cost = 0
        self.card.eternal = True

    def enchant_damage_additive(self, amount: int, props) -> int:
        return self.damage if is_powered_attack(props) else 0


@register_enchantment
class SwiftEnchantment(Enchantment):
    """Swift — the first time the enchanted card is played each combat, draw
    [amount] cards.

    Source: Swift.cs — OnPlay: if Status Normal, Draw(Amount), Status Disabled.
    Granted by Beautiful Bracelet (amount 3).
    """

    id = "swift"
    name = "Swift"

    def on_play(self, card: Card, target: Creature | None = None) -> None:
        # Swift.cs:15 is EnchantmentModel.OnPlay — the third of the three
        # ports of that slot. It drew from on_card_played, i.e. during the
        # AfterCardPlayed dispatch in the CAT_CARD slot, after every power,
        # relic and potion listener; C# draws before all of them.
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

    def enchant_damage_multiplicative(self, amount: int, props) -> float:
        return 2 if is_powered_attack(props) else 1


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

    def enchant_damage_additive(self, amount: int, props) -> int:
        return self.amount if is_powered_attack(props) else 0


@register_enchantment
class AdroitEnchantment(Enchantment):
    """Adroit — playing the enchanted card also gains [amount] Block.

    Source: Adroit.cs — CanonicalVars BlockVar(0, Move); RecalculateValues sets
    `Block.BaseValue = Amount`; OnPlay is `CreatureCmd.GainBlock(Owner.Creature,
    DynamicVars.Block, cardPlay)`. There is NO CanEnchantCardType override, so
    the base CanEnchant is the whole filter. Granted by Kifuda (amount 3).
    """

    id = "adroit"
    name = "Adroit"

    def on_play(self, card: Card, target: Creature | None = None) -> None:
        # `DynamicVars.Block` is the enchantment's own Block var, which
        # RecalculateValues keeps equal to Amount -- so the block is the
        # enchantment's amount, not the card's printed block. It is a
        # ValueProp.Move gain, i.e. the block modifiers apply, which is what
        # BlockCmd.apply already does.
        if card is not self.card:
            return
        from .cmds import BlockCmd

        BlockCmd.apply(self.combat.hooks, self.combat.player, self.amount,
                       card=card)


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

    def enchant_block_additive(self, amount: int, props) -> int:
        return self.amount


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

    def enchant_damage_additive(self, amount: int, props) -> int:
        if self.disabled or not is_powered_attack(props):
            return 0
        return self.amount

    def on_card_played(self, card: Card,
                       is_auto_play: bool = False) -> None:
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

    def enchant_damage_multiplicative(self, amount: int, props) -> float:
        return 1.5 if is_powered_attack(props) else 1

    def on_play(self, card: Card, target: Creature | None = None) -> None:
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


@register_enchantment
class RoyallyApprovedEnchantment(Enchantment):
    """Royally Approved — the enchanted Attack or Skill gains Innate and
    Retain.

    Source: RoyallyApproved.cs — `CanEnchantCardType` is
    `(uint)(cardType - 1) <= 1u`, i.e. exactly {Attack, Skill}; `OnEnchant`
    adds CardKeyword.Innate and CardKeyword.Retain. Granted by Royal Stamp.

    Both keywords are static card properties, so this is a `modify_card`
    (EnchantmentModel.ModifyCard -> OnEnchant), re-applied wherever the game
    re-derives a card from its canonical model.
    """

    id = "royally_approved"
    name = "Royally Approved"

    @classmethod
    def can_enchant(cls, card: Card) -> bool:
        from .cards import CardType

        return super().can_enchant(card) and card.card_type in (
            CardType.ATTACK, CardType.SKILL)

    def modify_card(self) -> None:
        if self.card is None:
            return
        self.card.innate = True
        self.card.retain = True


ALL_ENCHANTMENTS: dict[str, type[Enchantment]] = dict(_ENCHANTMENT_CLASSES)
