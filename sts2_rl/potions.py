"""Combat potions, mirroring STS2's PotionModel + PotionCmd (values taken from
the source models in src/Core/Models/Potions)."""
from __future__ import annotations

import random
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .combat import CombatCtx
    from .creatures import Creature


_POTION_CLASSES: dict[str, type[Potion]] = {}


def register_potion(cls: type[Potion]) -> type[Potion]:
    _POTION_CLASSES[cls.id] = cls
    return cls


def make_potion(potion_id: str) -> Potion:
    return _POTION_CLASSES[potion_id]()


class Potion:
    """Base class for potions. targeted potions require an enemy target."""

    id: str
    name: str
    targeted: bool = False
    # PotionModel.Rarity — drives the shop price (MerchantPotionEntry.GetCost:
    # Rare 100, Uncommon 75, else 50). Every implemented reward-pool potion is
    # Common in the source; kept as an attr so rarer potions price correctly.
    rarity: str = "common"
    # Mirrors whether a potion appears in the character/shared reward pools
    # (PotionReward). Event-only potions (Glowwater) set this False so the
    # sim's random_potion helper doesn't offer them.
    in_reward_pool: bool = True

    def use(self, ctx: CombatCtx, target: Creature | None = None) -> None:
        raise NotImplementedError

    def __repr__(self) -> str:
        return self.name


@register_potion
class FirePotion(Potion):
    """Deal 20 damage to target enemy (unpowered: not boosted by Strength or
    Vulnerable, but blockable — mirrors the source's ValueProp.Unpowered)."""

    id = "fire_potion"
    name = "Fire Potion"
    targeted = True
    DAMAGE = 20

    def use(self, ctx: CombatCtx, target: Creature | None = None) -> None:
        from .cmds import DamageCmd
        from .valueprops import DamageProps
        DamageCmd.deal(
            ctx.hooks,
            target or ctx.enemy,
            self.DAMAGE,
            dealer=ctx.player,
            props=DamageProps.NON_CARD_UNPOWERED,
        )


@register_potion
class BlockPotion(Potion):
    """Gain 12 block (unpowered: unaffected by Dexterity/Frail)."""

    id = "block_potion"
    name = "Block Potion"
    BLOCK = 12

    def use(self, ctx: CombatCtx, target: Creature | None = None) -> None:
        from .cmds import BlockCmd
        from .valueprops import DamageProps
        BlockCmd.apply(
            ctx.hooks, ctx.player, self.BLOCK, props=DamageProps.NON_CARD_UNPOWERED
        )


@register_potion
class StrengthPotion(Potion):
    """Gain 2 Strength."""

    id = "strength_potion"
    name = "Strength Potion"
    STRENGTH = 2

    def use(self, ctx: CombatCtx, target: Creature | None = None) -> None:
        from .cmds import StrengthCmd
        StrengthCmd.apply(ctx.hooks, ctx.player, self.STRENGTH)


@register_potion
class FlexPotion(Potion):
    """Gain 5 temporary Strength (lost at end of turn).

    Source: FlexPotion.cs — Common, CombatOnly, TargetType AnyPlayer,
    PowerVar<StrengthPower>(5); OnUse applies FlexPotionPower (a
    TemporaryStrengthPower) to the player."""

    id = "flex_potion"
    name = "Flex Potion"
    STRENGTH = 5

    def use(self, ctx: CombatCtx, target: Creature | None = None) -> None:
        from .cmds import PowerCmd
        from .powers import FlexPotionPower
        PowerCmd.apply(
            ctx.hooks, ctx.player, FlexPotionPower, self.STRENGTH, applier=ctx.player
        )


@register_potion
class SpeedPotion(Potion):
    """Gain 5 temporary Dexterity (lost at end of turn).

    Source: SpeedPotion.cs — Common, CombatOnly, TargetType AnyPlayer,
    PowerVar<DexterityPower>(5); OnUse applies SpeedPotionPower (a
    TemporaryDexterityPower) to the player."""

    id = "speed_potion"
    name = "Speed Potion"
    DEXTERITY = 5

    def use(self, ctx: CombatCtx, target: Creature | None = None) -> None:
        from .cmds import PowerCmd
        from .powers import SpeedPotionPower
        PowerCmd.apply(
            ctx.hooks, ctx.player, SpeedPotionPower, self.DEXTERITY, applier=ctx.player
        )


@register_potion
class TouchOfInsanity(Potion):
    """Choose a card in your hand that costs energy; it costs 0 for the rest of
    the combat.

    Source: TouchOfInsanity.cs — Uncommon, CombatOnly, TargetType Self. OnUse =
    CardSelectCmd.FromHand(1, filter: CostsEnergyOrStars) then
    SetToFreeThisCombat on the pick (== EnergyCost.SetThisCombat(0)). The
    recording captures the pick as a SelectHandCards command, resolved by the
    combat driver's card_selector; a lone candidate auto-resolves (no command)."""

    id = "touch_of_insanity"
    name = "Touch of Insanity"
    rarity = "uncommon"

    def use(self, ctx: CombatCtx, target: Creature | None = None) -> None:
        combat = ctx.combat
        # CostsEnergyOrStars: a non-X card whose cost is > 0 (the sim has no
        # star costs) — i.e. skip cards that are already free.
        candidates = [
            c for c in ctx.player.hand
            if not getattr(c, "energy_cost_x", False) and c.energy_cost > 0
        ]
        if not candidates:
            return
        for card in combat.select_cards("free_this_combat", candidates, 1):
            card.set_cost_this_combat(0)


@register_potion
class ExplosiveAmpoule(Potion):
    """Deal 10 damage to ALL enemies (unpowered).

    Source: ExplosiveAmpoule.cs — Common, CombatOnly, TargetType AllEnemies,
    DamageVar(10, ValueProp.Unpowered); OnUse damages
    `CombatState.HittableEnemies` in order."""

    id = "explosive_ampoule"
    name = "Explosive Ampoule"
    DAMAGE = 10

    def use(self, ctx: CombatCtx, target: Creature | None = None) -> None:
        from .cmds import DamageCmd
        from .valueprops import DamageProps
        for enemy in [e for e in ctx.enemies if not e.is_gone]:
            DamageCmd.deal(
                ctx.hooks,
                enemy,
                self.DAMAGE,
                dealer=ctx.player,
                props=DamageProps.NON_CARD_UNPOWERED,
            )


@register_potion
class GamblersBrew(Potion):
    """Discard any number of cards, then draw that many.

    Source: GamblersBrew.cs — Uncommon, CombatOnly, TargetType Self. OnUse =
    `CardSelectCmd.FromHandForDiscard(prefs(min 0, max 999999999))` then
    `CardCmd.DiscardAndDraw(picked, picked.Count)`. MinSelect 0 means the
    screen is always shown (never auto-resolved), so the recording always
    carries the pick as a `SelectHandCards` command; the discard hooks fire
    per card before the draw (the source defers only Sly autoplay)."""

    id = "gamblers_brew"
    name = "Gambler's Brew"
    rarity = "uncommon"

    def use(self, ctx: CombatCtx, target: Creature | None = None) -> None:
        player = ctx.player
        # MinSelect 0 / MaxSelect ~unbounded: "up to the whole hand".
        chosen = ctx.combat.select_cards(
            "discard_and_draw", list(player.hand), len(player.hand)
        )
        if not chosen:
            return
        for card in chosen:
            player.hand.remove(card)
            ctx.hooks.on_card_discarded(card)
            player.discard_pile.append(card)
        from .cmds import DrawCmd
        DrawCmd.draw(player, len(chosen))


@register_potion
class SwiftPotion(Potion):
    """Draw 3 cards.

    Source: SwiftPotion.cs — Common, CombatOnly, TargetType AnyPlayer,
    CardsVar(3); OnUse = `CardPileCmd.Draw(3, target.Player)`."""

    id = "swift_potion"
    name = "Swift Potion"
    CARDS = 3

    def use(self, ctx: CombatCtx, target: Creature | None = None) -> None:
        from .cmds import DrawCmd
        DrawCmd.draw(ctx.player, self.CARDS)


@register_potion
class StableSerum(Potion):
    """Your hand is not discarded for the next 2 turns.

    Source: StableSerum.cs — Uncommon, CombatOnly, TargetType AnyPlayer,
    RepeatVar(2); OnUse = `PowerCmd.Apply<RetainHandPower>(2)` on the target."""

    id = "stable_serum"
    name = "Stable Serum"
    rarity = "uncommon"
    TURNS = 2

    def use(self, ctx: CombatCtx, target: Creature | None = None) -> None:
        from .cmds import PowerCmd
        from .powers import RetainHandPower
        PowerCmd.apply(
            ctx.hooks, ctx.player, RetainHandPower, self.TURNS, applier=ctx.player
        )


@register_potion
class CureAll(Potion):
    """Gain 1 energy and draw 2 cards.

    Source: CureAll.cs — Uncommon, CombatOnly, TargetType AnyPlayer,
    EnergyVar(1) + CardsVar(2); OnUse = `PlayerCmd.GainEnergy(1)` then
    `CardPileCmd.Draw(2)`."""

    id = "cure_all"
    name = "Cure All"
    rarity = "uncommon"
    ENERGY = 1
    CARDS = 2

    def use(self, ctx: CombatCtx, target: Creature | None = None) -> None:
        from .cmds import DrawCmd, EnergyCmd
        EnergyCmd.gain(ctx.hooks, ctx.player, self.ENERGY)
        DrawCmd.draw(ctx.player, self.CARDS)


@register_potion
class BottledPotential(Potion):
    """Put your hand into the draw pile, shuffle, then draw 5.

    Source: BottledPotential.cs — Rare, CombatOnly, TargetType AnyPlayer,
    CardsVar(5). OnUse = `CardPileCmd.Add(Hand.Cards, PileType.Draw)` (the
    default CardPilePosition.Bottom, so no rng), `CardPileCmd.Shuffle` (ONE
    StableShuffle of discard+draw on Rng.Shuffle) and `CardPileCmd.Draw(5)`.
    The hand is *recycled*, not discarded — no on-discard hook fires."""

    id = "bottled_potential"
    name = "Bottled Potential"
    rarity = "rare"
    CARDS = 5

    def use(self, ctx: CombatCtx, target: Creature | None = None) -> None:
        from .cmds import DrawCmd
        player = ctx.player
        player.draw_pile.extend(player.hand)
        player.hand = []
        player.shuffle_draw_and_discard()
        DrawCmd.draw(player, self.CARDS)


@register_potion
class BloodPotion(Potion):
    """Heal 20% of max HP."""

    id = "blood_potion"
    name = "Blood Potion"
    HEAL_PERCENT = 20

    def use(self, ctx: CombatCtx, target: Creature | None = None) -> None:
        from .cmds import CreatureCmd
        heal = ctx.player.max_hp * self.HEAL_PERCENT // 100
        CreatureCmd.heal(ctx.hooks, ctx.player, heal)


@register_potion
class WeakPotion(Potion):
    """Apply 3 Weak to target enemy."""

    id = "weak_potion"
    name = "Weak Potion"
    targeted = True
    WEAK = 3

    def use(self, ctx: CombatCtx, target: Creature | None = None) -> None:
        from .cmds import PowerCmd
        from .powers import WeakPower
        PowerCmd.apply(
            ctx.hooks, target or ctx.enemy, WeakPower, self.WEAK, applier=ctx.player
        )


@register_potion
class GlowwaterPotion(Potion):
    """Exhaust your whole hand, then draw 10 cards.

    Source: GlowwaterPotion.cs — Event rarity, CombatOnly. Granted by the
    Drowning Beacon event (not part of the random reward pool)."""

    id = "glowwater"
    name = "Glowwater Potion"
    rarity = "event"
    in_reward_pool = False
    DRAW = 10

    def use(self, ctx: CombatCtx, target: Creature | None = None) -> None:
        from .cmds import DrawCmd, ExhaustCmd
        for card in list(ctx.player.hand):
            ExhaustCmd.exhaust(ctx.hooks, ctx.player, card)
        DrawCmd.draw(ctx.player, self.DRAW)


@register_potion
class PotionShapedRock(Potion):
    """Deal 15 damage to target enemy (unpowered).

    Source: PotionShapedRock.cs — Token rarity, CombatOnly, TargetType
    AnyEnemy, DamageVar(15, ValueProp.Unpowered). Procured each combat by
    Petrified Toad (not part of the random reward pool)."""

    id = "potion_shaped_rock"
    name = "Potion Shaped Rock"
    rarity = "token"
    targeted = True
    in_reward_pool = False
    DAMAGE = 15

    def use(self, ctx: CombatCtx, target: Creature | None = None) -> None:
        from .cmds import DamageCmd
        from .valueprops import DamageProps
        DamageCmd.deal(
            ctx.hooks,
            target or ctx.enemy,
            self.DAMAGE,
            dealer=ctx.player,
            props=DamageProps.NON_CARD_UNPOWERED,
        )


@register_potion
class FoulPotion(Potion):
    """Deal 12 damage to EVERY creature — enemies and yourself.

    Source: FoulPotion.cs — Event rarity, AnyTime usage. OnUse in combat
    damages `CombatState.Creatures` (all creatures on all sides, pets
    excepted — the sim has no pets) for DamageVar(12, Unpowered), so the
    thrower takes 12 too; the AllEnemies TargetType is display-only.

    Out of combat the potion is the shop/Fake Merchant "throw it at the
    merchant" tool: at a real shop it pays GoldVar(100) and drives the
    merchant off (`RunState.merchant_driven_off`), and at the Fake Merchant
    event it starts that fight. Granted by the Potion Courier event, and by
    the merchant himself as a Fake Merchant prerequisite.
    """

    id = "foul_potion"
    name = "Foul Potion"
    rarity = "event"
    in_reward_pool = False       # Event rarity: never a random reward roll
    DAMAGE = 12
    GOLD = 100

    def use(self, ctx: CombatCtx, target: Creature | None = None) -> None:
        from .cmds import DamageCmd
        from .valueprops import DamageProps

        # CombatState.Creatures = all creatures on all sides.
        for creature in [*ctx.enemies, ctx.player]:
            if creature.is_gone:
                continue
            DamageCmd.deal(
                ctx.hooks,
                creature,
                self.DAMAGE,
                dealer=ctx.player,
                props=DamageProps.NON_CARD_UNPOWERED,
            )


@register_potion
class SkillPotion(Potion):
    """Choose 1 of 3 generated Skills; add a free copy to your hand this turn.

    Source: SkillPotion.cs — GetDistinctForCombat(CardPool.GetUnlockedCards()
    .Where(Type == Skill), 3, Rng.CombatCardGeneration), then a canSkip
    choose-a-card screen; the pick is SetToFreeThisTurn and added to hand.
    Parity draws the three off the CombatCardGeneration stream (game
    UnstableShuffle) and defers the pick to the recording's
    `SelectCardFromScreen`; legacy adds the first candidate (the RL agent's own
    choice is unmodeled — the potion was an inert placeholder before)."""

    id = "skill_potion"
    name = "Skill Potion"

    def use(self, ctx: CombatCtx, target: Creature | None = None) -> None:
        from .cards.base import CardType
        from .cards.pool import get_distinct_for_combat_parity, random_pool_cards
        from .cmds import CardPileCmd

        combat = ctx.combat
        crng = combat.combat_rng
        if crng.is_parity:
            cards = get_distinct_for_combat_parity(crng.card_gen, 3, CardType.SKILL)
            combat.offer_screen_selection(cards)
        else:
            cards = random_pool_cards(combat._rng, 3, CardType.SKILL, distinct=True)
            if cards:
                cards[0].set_free_this_turn()
                CardPileCmd.add_to_hand(ctx.hooks, ctx.player, cards[0])


@register_potion
class AttackPotion(Potion):
    """Choose 1 of 3 generated Attacks; add a free copy to your hand this turn.

    Source: AttackPotion.cs — the Skill Potion above with `Type == Attack`:
    `GetDistinctForCombat(CardPool.GetUnlockedCards().Where(Type == Attack), 3,
    Rng.CombatCardGeneration)`, a canSkip choose-a-card screen, then
    SetToFreeThisTurn + add to hand."""

    id = "attack_potion"
    name = "Attack Potion"

    def use(self, ctx: CombatCtx, target: Creature | None = None) -> None:
        from .cards.base import CardType
        from .cards.pool import get_distinct_for_combat_parity, random_pool_cards
        from .cmds import CardPileCmd

        combat = ctx.combat
        crng = combat.combat_rng
        if crng.is_parity:
            cards = get_distinct_for_combat_parity(crng.card_gen, 3, CardType.ATTACK)
            combat.offer_screen_selection(cards)
        else:
            cards = random_pool_cards(combat._rng, 3, CardType.ATTACK, distinct=True)
            if cards:
                cards[0].set_free_this_turn()
                CardPileCmd.add_to_hand(ctx.hooks, ctx.player, cards[0])


ALL_POTIONS: dict[str, type[Potion]] = dict(_POTION_CLASSES)


def random_potion(rng: random.Random) -> Potion:
    """A uniformly random reward-pool potion (mirrors PotionFactory.
    CreateRandomPotionInCombat for the sim's implemented pool; Alchemize).
    Sorted by id so the pick is a pure function of the RNG state."""
    pool = sorted(
        (c for c in _POTION_CLASSES.values() if c.in_reward_pool),
        key=lambda c: c.id,
    )
    return rng.choice(pool)()
