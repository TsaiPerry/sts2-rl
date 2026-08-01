"""Combat potions, mirroring STS2's PotionModel + PotionCmd (values taken from
the source models in src/Core/Models/Potions)."""
from __future__ import annotations

import random
from typing import TYPE_CHECKING

from .hooks import CAT_POTION

if TYPE_CHECKING:
    from .combat import CombatCtx
    from .creatures import Creature


_POTION_CLASSES: dict[str, type[Potion]] = {}

# PotionUsage (PotionUsage.cs) — when the Use button is live.
USAGE_COMBAT_ONLY = "combat_only"
USAGE_ANY_TIME = "any_time"
USAGE_AUTOMATIC = "automatic"


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
    # After its owner's relics in the dispatch walk
    # (CombatState.IterateHookListeners, CombatState.cs:436-443).
    hook_category = CAT_POTION
    # `PotionModel.HasBeenRemovedFromState` (PotionModel.cs:202), set by
    # Discard (:221-224) and RemoveBeforeUse (:229-233).
    has_been_removed_from_state: bool = False
    # PotionModel.Rarity — drives the shop price (MerchantPotionEntry.GetCost:
    # Rare 100, Uncommon 75, else 50). Every implemented reward-pool potion is
    # Common in the source; kept as an attr so rarer potions price correctly.
    rarity: str = "common"
    # Mirrors whether a potion appears in the character/shared reward pools
    # (PotionReward). Event-only potions (Glowwater) set this False so the
    # sim's random_potion helper doesn't offer them.
    in_reward_pool: bool = True
    # Which character's PotionPool this potion belongs to, or None for
    # SharedPotionPool. `GetPotionOptions` is `Character.PotionPool ∪
    # SharedPotionPool`, so a character potion never appears in another
    # character's run; RunState's reward-pool scans consult this.
    character: str | None = None
    # PotionModel.Usage. COMBAT_ONLY is the default; ANY_TIME leaves the Use
    # button live outside combat too (OnUseWrapper is written for it —
    # PotionModel.cs:294,298,334,336 all null-check the combat state);
    # AUTOMATIC potions are fired by their own hook and never by the player
    # (the game disables the Use button, NPotionPopup.cs:131).
    usage: str = USAGE_COMBAT_ONLY
    # Back-reference to the combat this potion is sitting in a belt of (mirrors
    # PotionModel.Owner.Creature.CombatState), set while it is registered as a
    # hook listener — the same pattern as Card.combat. Only hook-listening
    # potions (Fairy in a Bottle) need it; `use` gets its ctx passed in.
    combat = None

    def hook_contains(self) -> bool:
        """`CombatState.Contains`' PotionModel arm (CombatState.cs:595):
        `!HasBeenRemovedFromState && Owner.IsActiveForHooks`."""
        if self.has_been_removed_from_state:
            return False
        combat = self.combat
        if combat is None:
            return True
        player = getattr(combat, "player", None)
        return player is None or player.is_active_for_hooks

    @property
    def automatic(self) -> bool:
        """PotionUsage.Automatic — CombatState.use_potion rejects it and the
        env masks its actions out."""
        return self.usage == USAGE_AUTOMATIC

    def use(self, ctx: CombatCtx, target: Creature | None = None) -> None:
        raise NotImplementedError

    def use_out_of_combat(self, run) -> None:
        """`OnUse`'s `combatState == null` arm, for a PotionUsage.AnyTime
        potion drunk on the map (RunState.use_potion). CombatOnly potions
        never reach it."""
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
        # TouchOfInsanity.cs:22 is an OR over BOTH cost views:
        # `CostsEnergyOrStars(includeGlobalModifiers: false) ||
        #  CostsEnergyOrStars(includeGlobalModifiers: true)`. The `false` arm
        # is CostModifiers.Local (Card.energy_cost here); the `true` arm is
        # CostModifiers.All, which adds Hook.ModifyEnergyCostInCombat
        # (CardEnergyCost.cs:116) — so a card made free THIS TURN but raised
        # globally by Spiked Gauntlets still counts as costing energy. The sim
        # has no star costs, so `CurrentStarCost` drops out of both arms.
        candidates = [
            c for c in ctx.player.hand
            if not getattr(c, "energy_cost_x", False)
            and (c.energy_cost > 0
                 or ctx.hooks.modify_card_energy_cost(c, c.energy_cost) > 0)
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
        # MinSelect 0 / MaxSelect ~unbounded: "up to the whole hand" — the
        # screen is always shown (CardSelectCmd.cs:708-711) and confirming
        # none is legal.
        chosen = ctx.combat.select_cards(
            "discard_any", list(player.hand), len(player.hand),
            min_select=0,   # GamblersBrew.cs:26 CardSelectorPrefs(prompt, 0, ...)
        )
        if not chosen:
            return
        # GamblersBrew.cs:27 is literally `CardCmd.DiscardAndDraw(picked,
        # picked.Count)`. This loop used to be open-coded here, and it fired
        # `AfterCardDiscarded` BEFORE the append where C# appends first
        # (CardCmd.cs:192-194) — the opposite of the way `relics/
        # gambling_chip.py` open-coded the same command. It also had no Sly
        # tail. creature_card_cmds/step50 + step51.
        from .cmds import CardCmd
        CardCmd.discard_and_draw(ctx.hooks, player, chosen, len(chosen))


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
    usage = USAGE_ANY_TIME
    HEAL_PERCENT = 20

    def use(self, ctx: CombatCtx, target: Creature | None = None) -> None:
        from .cmds import CreatureCmd
        heal = ctx.player.max_hp * self.HEAL_PERCENT // 100
        CreatureCmd.heal(ctx.hooks, ctx.player, heal)

    def use_out_of_combat(self, run) -> None:
        run.heal(run.max_hp * self.HEAL_PERCENT // 100)


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
    merchant" tool: at a real shop it drives the merchant off and pays
    GoldVar(100) (FoulPotion.cs:79-88), and at the Fake Merchant event it
    starts that fight (:89-108). Granted by the Potion Courier event, and by
    the merchant himself as a Fake Merchant prerequisite.
    """

    id = "foul_potion"
    name = "Foul Potion"
    rarity = "event"
    in_reward_pool = False       # Event rarity: never a random reward roll
    usage = USAGE_ANY_TIME
    DAMAGE = 12
    GOLD = 100

    def use(self, ctx: CombatCtx, target: Creature | None = None) -> None:
        from .cmds import DamageCmd
        from .valueprops import DamageProps

        # CombatState.Creatures is `_allies.Concat(_enemies)`
        # (CombatState.cs:70), so the THROWER is damaged first. The order is
        # observable at the edge: with the player and the last enemy both on
        # <= DAMAGE HP the game ends the run where killing the enemy first
        # would win the fight.
        for creature in [ctx.player, *ctx.enemies]:
            if creature.is_gone:
                continue
            DamageCmd.deal(
                ctx.hooks,
                creature,
                self.DAMAGE,
                dealer=ctx.player,
                props=DamageProps.NON_CARD_UNPOWERED,
            )

    def use_out_of_combat(self, run) -> None:
        # FoulPotion.cs:79-88, the MerchantRoom arm: the merchant is driven
        # off (NMerchantRoom.FoulPotionThrown) and the thrower gains GoldVar.
        # The Fake Merchant arm (:89-108) belongs to the event, which owns the
        # stall and the fight it starts.
        run.merchant_driven_off = True
        run.gain_gold(self.GOLD)


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

        crng = ctx.combat.combat_rng
        if crng.is_parity:
            cards = get_distinct_for_combat_parity(
                crng.card_gen, 3, CardType.SKILL, pool=ctx.combat.card_pool
            )
        else:
            cards = random_pool_cards(
                ctx.combat._rng, 3, CardType.SKILL, distinct=True,
                pool=ctx.combat.card_pool)
        _choose_a_card_screen(ctx, cards)


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

        crng = ctx.combat.combat_rng
        if crng.is_parity:
            cards = get_distinct_for_combat_parity(
                crng.card_gen, 3, CardType.ATTACK, pool=ctx.combat.card_pool
            )
        else:
            cards = random_pool_cards(
                ctx.combat._rng, 3, CardType.ATTACK, distinct=True,
                pool=ctx.combat.card_pool)
        _choose_a_card_screen(ctx, cards)


@register_potion
class DexterityPotion(Potion):
    """Gain 2 Dexterity.

    Source: DexterityPotion.cs — Common, CombatOnly, TargetType AnyPlayer,
    PowerVar<DexterityPower>(2)."""

    id = "dexterity_potion"
    name = "Dexterity Potion"
    DEXTERITY = 2

    def use(self, ctx: CombatCtx, target: Creature | None = None) -> None:
        from .cmds import PowerCmd
        from .powers import DexterityPower
        PowerCmd.apply(
            ctx.hooks, ctx.player, DexterityPower, self.DEXTERITY, applier=ctx.player
        )


@register_potion
class VulnerablePotion(Potion):
    """Apply 3 Vulnerable to target enemy.

    Source: VulnerablePotion.cs — Common, CombatOnly, TargetType AnyEnemy,
    PowerVar<VulnerablePower>(3)."""

    id = "vulnerable_potion"
    name = "Vulnerable Potion"
    targeted = True
    VULNERABLE = 3

    def use(self, ctx: CombatCtx, target: Creature | None = None) -> None:
        from .cmds import PowerCmd
        from .powers import VulnerablePower
        PowerCmd.apply(
            ctx.hooks,
            target or ctx.enemy,
            VulnerablePower,
            self.VULNERABLE,
            applier=ctx.player,
        )


@register_potion
class FyshOil(Potion):
    """Gain 1 Strength and 1 Dexterity.

    Source: FyshOil.cs — Uncommon, CombatOnly, TargetType AnyPlayer,
    PowerVar<StrengthPower>(1) + PowerVar<DexterityPower>(1); Strength first."""

    id = "fysh_oil"
    name = "Fysh Oil"
    rarity = "uncommon"
    STRENGTH = 1
    DEXTERITY = 1

    def use(self, ctx: CombatCtx, target: Creature | None = None) -> None:
        from .cmds import PowerCmd, StrengthCmd
        from .powers import DexterityPower
        StrengthCmd.apply(ctx.hooks, ctx.player, self.STRENGTH)
        PowerCmd.apply(
            ctx.hooks, ctx.player, DexterityPower, self.DEXTERITY, applier=ctx.player
        )


@register_potion
class LiquidBronze(Potion):
    """Gain 3 Thorns.

    Source: LiquidBronze.cs — Uncommon, CombatOnly, TargetType AnyPlayer,
    PowerVar<ThornsPower>(3)."""

    id = "liquid_bronze"
    name = "Liquid Bronze"
    rarity = "uncommon"
    THORNS = 3

    def use(self, ctx: CombatCtx, target: Creature | None = None) -> None:
        from .cmds import PowerCmd
        from .powers import ThornsPower
        PowerCmd.apply(
            ctx.hooks, ctx.player, ThornsPower, self.THORNS, applier=ctx.player
        )


@register_potion
class HeartOfIron(Potion):
    """Gain 7 Plating.

    Source: HeartOfIron.cs — Uncommon, CombatOnly, TargetType AnyPlayer,
    PowerVar<PlatingPower>(7)."""

    id = "heart_of_iron"
    name = "Heart of Iron"
    rarity = "uncommon"
    PLATING = 7

    def use(self, ctx: CombatCtx, target: Creature | None = None) -> None:
        from .cmds import PowerCmd
        from .powers import PlatingPower
        PowerCmd.apply(
            ctx.hooks, ctx.player, PlatingPower, self.PLATING, applier=ctx.player
        )


@register_potion
class RegenPotion(Potion):
    """Gain 5 Regen.

    Source: RegenPotion.cs — Uncommon, CombatOnly, TargetType AnyPlayer,
    PowerVar<RegenPower>(5). CanBeGeneratedInCombat=false (healing-adjacent),
    which potion_pools.NOT_GENERATED_IN_COMBAT already records."""

    id = "regen_potion"
    name = "Regen Potion"
    rarity = "uncommon"
    REGEN = 5

    def use(self, ctx: CombatCtx, target: Creature | None = None) -> None:
        from .cmds import PowerCmd
        from .powers import RegenPower
        PowerCmd.apply(
            ctx.hooks, ctx.player, RegenPower, self.REGEN, applier=ctx.player
        )


@register_potion
class MazalethsGift(Potion):
    """Gain 1 Ritual.

    Source: MazalethsGift.cs — Rare, CombatOnly, TargetType AnyPlayer,
    PowerVar<RitualPower>(1)."""

    id = "mazaleths_gift"
    name = "Mazaleth's Gift"
    rarity = "rare"
    RITUAL = 1

    def use(self, ctx: CombatCtx, target: Creature | None = None) -> None:
        from .cmds import PowerCmd
        from .powers import RitualPower
        PowerCmd.apply(
            ctx.hooks, ctx.player, RitualPower, self.RITUAL, applier=ctx.player
        )


@register_potion
class EnergyPotion(Potion):
    """Gain 2 energy.

    Source: EnergyPotion.cs — Common, CombatOnly, TargetType AnyPlayer,
    EnergyVar(2) → PlayerCmd.GainEnergy."""

    id = "energy_potion"
    name = "Energy Potion"
    ENERGY = 2

    def use(self, ctx: CombatCtx, target: Creature | None = None) -> None:
        from .cmds import EnergyCmd
        EnergyCmd.gain(ctx.hooks, ctx.player, self.ENERGY)


@register_potion
class Fortifier(Potion):
    """Triple your Block.

    Source: Fortifier.cs — Uncommon, CombatOnly, TargetType AnyPlayer;
    `CreatureCmd.GainBlock(target, target.Block * 2, ValueProp.Unpowered)` —
    twice the CURRENT block is *gained*, so the total ends up tripled (and
    nothing happens without block to begin with)."""

    id = "fortifier"
    name = "Fortifier"
    rarity = "uncommon"

    def use(self, ctx: CombatCtx, target: Creature | None = None) -> None:
        from .cmds import BlockCmd
        from .valueprops import DamageProps
        BlockCmd.apply(
            ctx.hooks,
            ctx.player,
            ctx.player.block * 2,
            props=DamageProps.NON_CARD_UNPOWERED,
        )


@register_potion
class ShipInABottle(Potion):
    """Gain 10 block; gain 10 block again next turn.

    Source: ShipInABottle.cs — Rare, CombatOnly, TargetType AnyPlayer,
    BlockVar(10, ValueProp.Unpowered): GainBlock now plus
    PowerCmd.Apply<BlockNextTurnPower>(10)."""

    id = "ship_in_a_bottle"
    name = "Ship in a Bottle"
    rarity = "rare"
    BLOCK = 10

    def use(self, ctx: CombatCtx, target: Creature | None = None) -> None:
        from .cmds import BlockCmd, PowerCmd
        from .powers import BlockNextTurnPower
        from .valueprops import DamageProps
        BlockCmd.apply(
            ctx.hooks, ctx.player, self.BLOCK, props=DamageProps.NON_CARD_UNPOWERED
        )
        PowerCmd.apply(
            ctx.hooks, ctx.player, BlockNextTurnPower, self.BLOCK, applier=ctx.player
        )


@register_potion
class BeetleJuice(Potion):
    """Target enemy's attacks deal 30% less damage for 4 turns.

    Source: BeetleJuice.cs — Rare, CombatOnly, TargetType AnyEnemy,
    RepeatVar(4) → PowerCmd.Apply<ShrinkPower>(4) (the DamageDecrease var is
    display-only; the 30% lives in ShrinkPower)."""

    id = "beetle_juice"
    name = "Beetle Juice"
    rarity = "rare"
    targeted = True
    TURNS = 4

    def use(self, ctx: CombatCtx, target: Creature | None = None) -> None:
        from .cmds import PowerCmd
        from .powers import ShrinkPower
        PowerCmd.apply(
            ctx.hooks,
            target or ctx.enemy,
            ShrinkPower,
            self.TURNS,
            applier=ctx.player,
        )


@register_potion
class PotionOfBinding(Potion):
    """Apply 1 Weak and 1 Vulnerable to ALL enemies.

    Source: PotionOfBinding.cs — Uncommon, CombatOnly, TargetType AllEnemies,
    PowerVar<VulnerablePower>(1) + PowerVar<WeakPower>(1) applied over
    `CombatState.HittableEnemies`, Weak first. (The source reads the two vars
    crosswise — Weak with the Vulnerable var and vice versa — which is
    invisible because both are 1.)"""

    id = "potion_of_binding"
    name = "Potion of Binding"
    rarity = "uncommon"
    WEAK = 1
    VULNERABLE = 1

    def use(self, ctx: CombatCtx, target: Creature | None = None) -> None:
        from .cmds import PowerCmd
        from .powers import VulnerablePower, WeakPower
        targets = [e for e in ctx.enemies if not e.is_gone]
        for enemy in targets:
            PowerCmd.apply(
                ctx.hooks, enemy, WeakPower, self.WEAK, applier=ctx.player
            )
        for enemy in targets:
            PowerCmd.apply(
                ctx.hooks, enemy, VulnerablePower, self.VULNERABLE, applier=ctx.player
            )


@register_potion
class Clarity(Potion):
    """Draw 1 card; draw 1 extra card at the start of each of your next 3 turns.

    Source: Clarity.cs — Uncommon, CombatOnly, TargetType AnyPlayer,
    ClarityPower(3) + CardsVar(1): the Draw(1) resolves BEFORE the power is
    applied, so it is not itself boosted."""

    id = "clarity"
    name = "Clarity Extract"
    rarity = "uncommon"
    CARDS = 1
    CLARITY = 3

    def use(self, ctx: CombatCtx, target: Creature | None = None) -> None:
        from .cmds import DrawCmd, PowerCmd
        from .powers import ClarityPower
        DrawCmd.draw(ctx.player, self.CARDS)
        PowerCmd.apply(
            ctx.hooks, ctx.player, ClarityPower, self.CLARITY, applier=ctx.player
        )


@register_potion
class Duplicator(Potion):
    """This turn, your next card is played an extra time.

    Source: Duplicator.cs — Uncommon, CombatOnly, TargetType Self,
    PowerCmd.Apply<DuplicationPower>(1)."""

    id = "duplicator"
    name = "Duplicator"
    rarity = "uncommon"
    STACKS = 1

    def use(self, ctx: CombatCtx, target: Creature | None = None) -> None:
        from .cmds import PowerCmd
        from .powers import DuplicationPower
        PowerCmd.apply(
            ctx.hooks, ctx.player, DuplicationPower, self.STACKS, applier=ctx.player
        )


@register_potion
class GigantificationPotion(Potion):
    """The next Attack you play deals triple damage.

    Source: GigantificationPotion.cs — Rare, CombatOnly, TargetType AnyPlayer,
    PowerVar<GigantificationPower>(1)."""

    id = "gigantification_potion"
    name = "Gigantification Potion"
    rarity = "rare"
    STACKS = 1

    def use(self, ctx: CombatCtx, target: Creature | None = None) -> None:
        from .cmds import PowerCmd
        from .powers import GigantificationPower
        PowerCmd.apply(
            ctx.hooks,
            ctx.player,
            GigantificationPower,
            self.STACKS,
            applier=ctx.player,
        )


@register_potion
class LuckyTonic(Potion):
    """Gain 1 Buffer (prevent the next instance of HP loss).

    Source: LuckyTonic.cs — Rare, CombatOnly, TargetType AnyPlayer,
    PowerVar<BufferPower>(1)."""

    id = "lucky_tonic"
    name = "Lucky Tonic"
    rarity = "rare"
    BUFFER = 1

    def use(self, ctx: CombatCtx, target: Creature | None = None) -> None:
        from .cmds import PowerCmd
        from .powers import BufferPower
        PowerCmd.apply(
            ctx.hooks, ctx.player, BufferPower, self.BUFFER, applier=ctx.player
        )


@register_potion
class RadiantTincture(Potion):
    """Gain 1 energy; gain 1 extra energy at the start of each of your next
    3 turns.

    Source: RadiantTincture.cs — Uncommon, CombatOnly, TargetType AnyPlayer,
    EnergyVar(1) + PowerVar<RadiancePower>(3): GainEnergy then Apply."""

    id = "radiant_tincture"
    name = "Radiant Tincture"
    rarity = "uncommon"
    ENERGY = 1
    RADIANCE = 3

    def use(self, ctx: CombatCtx, target: Creature | None = None) -> None:
        from .cmds import EnergyCmd, PowerCmd
        from .powers import RadiancePower
        EnergyCmd.gain(ctx.hooks, ctx.player, self.ENERGY)
        PowerCmd.apply(
            ctx.hooks, ctx.player, RadiancePower, self.RADIANCE, applier=ctx.player
        )


@register_potion
class PowderedDemise(Potion):
    """Target enemy loses 9 HP at the end of each of its turns.

    Source: PowderedDemise.cs — Uncommon, CombatOnly, TargetType AnyEnemy,
    DynamicVar("Demise", 9) → PowerCmd.Apply<DemisePower>(9)."""

    id = "powdered_demise"
    name = "Powdered Demise"
    rarity = "uncommon"
    targeted = True
    DEMISE = 9

    def use(self, ctx: CombatCtx, target: Creature | None = None) -> None:
        from .cmds import PowerCmd
        from .powers import DemisePower
        PowerCmd.apply(
            ctx.hooks,
            target or ctx.enemy,
            DemisePower,
            self.DEMISE,
            applier=ctx.player,
        )


@register_potion
class ShacklingPotion(Potion):
    """ALL enemies lose 7 Strength this turn.

    Source: ShacklingPotion.cs — Rare, CombatOnly, TargetType AllEnemies,
    PowerVar<StrengthPower>(7) applied as ShacklingPotionPower over
    `CombatState.HittableEnemies` (a TemporaryStrengthPower with
    IsPositive=false, so the Strength returns at the end of their turn)."""

    id = "shackling_potion"
    name = "Shackling Potion"
    rarity = "rare"
    STRENGTH = 7

    def use(self, ctx: CombatCtx, target: Creature | None = None) -> None:
        from .cmds import PowerCmd
        from .powers import ShacklingPotionPower
        for enemy in [e for e in ctx.enemies if not e.is_gone]:
            PowerCmd.apply(
                ctx.hooks,
                enemy,
                ShacklingPotionPower,
                self.STRENGTH,
                applier=ctx.player,
            )


@register_potion
class Ashwater(Potion):
    """Exhaust any number of cards in your hand.

    Source: Ashwater.cs — Uncommon, CombatOnly, TargetType Self;
    `CardSelectCmd.FromHand(prefs(min 0, max 999999999))` then `CardCmd.Exhaust`
    on each pick. MinSelect 0 means declining is legal (nothing is exhausted)."""

    id = "ashwater"
    name = "Ashwater"
    rarity = "uncommon"

    def use(self, ctx: CombatCtx, target: Creature | None = None) -> None:
        from .cmds import ExhaustCmd
        player = ctx.player
        # MinSelect 0: `FromHand`'s auto-resolve shortcut is `list.Count <=
        # prefs.MinSelect` (CardSelectCmd.cs:708-711), false for any non-empty
        # hand, so the screen is ALWAYS shown and confirming none is legal.
        # Its own purpose label keeps it off "exhaust", which is the
        # exhaust-exactly-N screens (Burning Pact, Fiend Fire).
        chosen = ctx.combat.select_cards(
            "exhaust_any", list(player.hand), len(player.hand),
            min_select=0,   # Ashwater.cs:30 CardSelectorPrefs(prompt, 0, ...)
        )
        for card in chosen:
            ExhaustCmd.exhaust(ctx.hooks, player, card)


@register_potion
class BlessingOfTheForge(Potion):
    """Upgrade every card in your hand for the rest of the combat.

    Source: BlessingOfTheForge.cs — Uncommon, CombatOnly, TargetType Self;
    `CardCmd.Upgrade` on each `IsUpgradable` card of PileType.Hand."""

    id = "blessing_of_the_forge"
    name = "Blessing of the Forge"
    rarity = "uncommon"

    def use(self, ctx: CombatCtx, target: Creature | None = None) -> None:
        for card in list(ctx.player.hand):
            if card.is_upgradable:
                card.upgrade()


@register_potion
class DistilledChaos(Potion):
    """Play the top 3 cards of your draw pile.

    Source: DistilledChaos.cs — Rare, CombatOnly, TargetType Self, RepeatVar(3)
    → `CardPileCmd.AutoPlayFromDrawPile(3, CardPilePosition.Top,
    forceExhaust: false)`: all three are pulled off the draw pile first (with a
    reshuffle when it runs dry), then auto-played in order."""

    id = "distilled_chaos"
    name = "Distilled Chaos"
    rarity = "rare"
    CARDS = 3

    def use(self, ctx: CombatCtx, target: Creature | None = None) -> None:
        # One statement in the source, like Cascade's and Havoc's: the whole
        # OnUse is `CardPileCmd.AutoPlayFromDrawPile(...)`. The inline
        # reimplementation this replaces parked its phase-1 picks in NO pile
        # (C# parks them in `PileType.Play`, CardPileCmd.cs:954) and broke on
        # `combat.is_over` where C# breaks only on the owner's death (:958).
        # Round 13, R5 — creature_card_cmds/step99's last residue.
        from .cmds import CardPileCmd
        CardPileCmd.auto_play_from_draw_pile(
            ctx.hooks, ctx.player, self.CARDS, position="top",
            force_exhaust=False)


@register_potion
class DropletOfPrecognition(Potion):
    """Choose a card in your draw pile and put it into your hand.

    Source: DropletOfPrecognition.cs — Rare, CombatOnly, TargetType Self;
    `CardSelectCmd.FromCombatPile(Draw, 1)` then `CardPileCmd.Add(card,
    PileType.Hand)`. The card keeps its cost (unlike Liquid Memories)."""

    id = "droplet_of_precognition"
    name = "Droplet of Precognition"
    rarity = "rare"

    def use(self, ctx: CombatCtx, target: Creature | None = None) -> None:
        player = ctx.player
        chosen = ctx.combat.select_cards(
            "from_draw", list(player.draw_pile), 1, is_draw_pile=True)
        for card in chosen:
            player.draw_pile.remove(card)
            player.hand.append(card)


@register_potion
class LiquidMemories(Potion):
    """Put a card from your discard pile into your hand; it is free this turn.

    Source: LiquidMemories.cs — Rare, CombatOnly, TargetType Self;
    `CardSelectCmd.FromCombatPile(Discard, 1)`, `SetToFreeThisTurn`, then
    `CardPileCmd.Add(card, PileType.Hand)`."""

    id = "liquid_memories"
    name = "Liquid Memories"
    rarity = "rare"

    def use(self, ctx: CombatCtx, target: Creature | None = None) -> None:
        player = ctx.player
        chosen = ctx.combat.select_cards("from_discard", list(player.discard_pile), 1)
        for card in chosen:
            player.discard_pile.remove(card)
            card.set_free_this_turn()
            player.hand.append(card)


@register_potion
class SneckoOil(Potion):
    """Draw 7 cards, then randomise the cost of the cards in your hand this turn.

    Source: SneckoOil.cs — Rare, CombatOnly, TargetType AnyPlayer, CardsVar(7):
    `CardPileCmd.Draw(7)`, then every non-X card in hand gets
    `EnergyCost.SetThisTurnOrUntilPlayed(Rng.CombatEnergyCosts.NextInt(4))` —
    one draw off the CombatEnergyCosts stream per card, in hand order."""

    id = "snecko_oil"
    name = "Snecko Oil"
    rarity = "rare"
    CARDS = 7

    def use(self, ctx: CombatCtx, target: Creature | None = None) -> None:
        from .cmds import DrawCmd
        player = ctx.player
        DrawCmd.draw(player, self.CARDS)
        energy_rng = ctx.combat.combat_rng.energy
        for card in list(player.hand):
            if card.energy_cost_x:
                continue
            card.set_cost_this_turn(energy_rng.randrange(4))


@register_potion
class SoldiersStew(Potion):
    """Every Strike card gains 1 Replay for the rest of the combat.

    Source: SoldiersStew.cs — Rare (IroncladPotionPool), CombatOnly, TargetType
    AnyPlayer; `BaseReplayCount++` on every card of
    `PlayerCombatState.AllCards` tagged `CardTag.Strike` (all piles, not just
    the hand)."""

    id = "soldiers_stew"
    name = "Soldier's Stew"
    rarity = "rare"

    def use(self, ctx: CombatCtx, target: Creature | None = None) -> None:
        for card in ctx.player.all_cards:
            if "strike" in card.tags:
                card.base_replay_count += 1


@register_potion
class ColorlessPotion(Potion):
    """Choose 1 of 3 generated Colorless cards; add a free copy to your hand
    this turn.

    Source: ColorlessPotion.cs — Common, CombatOnly, TargetType Self:
    `GetDistinctForCombat(ColorlessCardPool.GetUnlockedCards(), 3,
    Rng.CombatCardGeneration)`, a canSkip choose-a-card screen, then
    SetToFreeThisTurn + AddGeneratedCardToCombat(Hand). Same two paths as the
    Skill/Attack Potions: parity defers the pick to the recording's
    `SelectCardFromScreen`, legacy takes the first candidate."""

    id = "colorless_potion"
    name = "Colorless Potion"

    def use(self, ctx: CombatCtx, target: Creature | None = None) -> None:
        from .cards.pool import (
            COLORLESS_POOL,
            get_distinct_for_combat_parity,
            random_pool_cards,
        )

        crng = ctx.combat.combat_rng
        if crng.is_parity:
            cards = get_distinct_for_combat_parity(
                crng.card_gen, 3, None, COLORLESS_POOL
            )
        else:
            cards = random_pool_cards(
                ctx.combat._rng, 3, None, distinct=True, pool=COLORLESS_POOL
            )
        _choose_a_card_screen(ctx, cards)


@register_potion
class PowerPotion(Potion):
    """Choose 1 of 3 generated Powers; add a free copy to your hand this turn.

    Source: PowerPotion.cs — the Skill/Attack Potion shape with
    `Type == Power`: `GetDistinctForCombat(Character.CardPool.GetUnlockedCards()
    .Where(Type == Power), 3, Rng.CombatCardGeneration)`, a canSkip
    choose-a-card screen, then SetToFreeThisTurn + add to hand."""

    id = "power_potion"
    name = "Power Potion"

    def use(self, ctx: CombatCtx, target: Creature | None = None) -> None:
        from .cards.base import CardType
        from .cards.pool import get_distinct_for_combat_parity, random_pool_cards

        crng = ctx.combat.combat_rng
        if crng.is_parity:
            cards = get_distinct_for_combat_parity(
                crng.card_gen, 3, CardType.POWER, pool=ctx.combat.card_pool
            )
        else:
            cards = random_pool_cards(
                ctx.combat._rng, 3, CardType.POWER, distinct=True,
                pool=ctx.combat.card_pool)
        _choose_a_card_screen(ctx, cards)


@register_potion
class OrobicAcid(Potion):
    """Add a random Attack, Skill and Power to your hand; all free this turn.

    Source: OrobicAcid.cs — Rare, CombatOnly, TargetType Self: three separate
    `GetDistinctForCombat(pool.Where(Type == X), 1, Rng.CombatCardGeneration)`
    calls (Attack, then Skill, then Power — three draws off the stream), each
    pick SetToFreeThisTurn, then AddGeneratedCardsToCombat(Hand). No selection
    screen."""

    id = "orobic_acid"
    name = "Orobic Acid"
    rarity = "rare"

    def use(self, ctx: CombatCtx, target: Creature | None = None) -> None:
        from .cards.base import CardType
        from .cards.pool import get_distinct_for_combat_parity, random_pool_cards
        from .cmds import CardPileCmd

        combat = ctx.combat
        crng = combat.combat_rng
        cards = []
        for card_type in (CardType.ATTACK, CardType.SKILL, CardType.POWER):
            if crng.is_parity:
                cards += get_distinct_for_combat_parity(
                    crng.card_gen, 1, card_type, pool=combat.card_pool
                )
            else:
                cards += random_pool_cards(
                    combat._rng, 1, card_type, distinct=True,
                    pool=combat.card_pool,
                )
        for card in cards:
            card.set_free_this_turn()
            CardPileCmd.add_to_hand(ctx.hooks, ctx.player, card)


@register_potion
class FruitJuice(Potion):
    """Gain 5 Max HP.

    Source: FruitJuice.cs — Rare, AnyTime, TargetType AnyPlayer,
    MaxHpVar(5) → `CreatureCmd.GainMaxHp` (raise max HP, then heal as much).
    CanBeGeneratedInCombat=false."""

    id = "fruit_juice"
    name = "Fruit Juice"
    rarity = "rare"
    usage = USAGE_ANY_TIME
    MAX_HP = 5

    def use(self, ctx: CombatCtx, target: Creature | None = None) -> None:
        from .cmds import CreatureCmd
        CreatureCmd.gain_max_hp(ctx.hooks, ctx.player, self.MAX_HP)

    def use_out_of_combat(self, run) -> None:
        run.gain_max_hp(self.MAX_HP)


@register_potion
class EntropicBrew(Potion):
    """Fill all your empty potion slots with random potions.

    Source: EntropicBrew.cs — Rare, AnyTime, TargetType Self:
    `while (Owner.HasOpenPotionSlots)` create a
    `PotionFactory.CreateRandomPotionOutOfCombat(Rng.CombatPotionGeneration)`
    and `PotionCmd.TryToProcure` it, stopping when procurement fails. The
    brew's own slot was freed by RemoveBeforeUse, so it refills too.

    `CreateRandomPotionOutOfCombat` is deliberate even mid-combat
    (EntropicBrew.cs:23), so the three `CanBeGeneratedInCombat=false` potions
    (Fairy in a Bottle, Fruit Juice, Regen Potion) ARE reachable from the brew
    — the legacy arm used to call the in-combat factory, which filters exactly
    those three and picks uniformly instead of rolling a rarity."""

    id = "entropic_brew"
    name = "Entropic Brew"
    rarity = "rare"
    usage = USAGE_ANY_TIME

    def use(self, ctx: CombatCtx, target: Creature | None = None) -> None:
        from .potion_pools import (
            generate_random_potion,
            legacy_random_potion_out_of_combat,
        )
        player = ctx.player
        rng_set = ctx.combat.rng_set
        while player.has_open_potion_slot:
            if rng_set is not None:
                potion = generate_random_potion(
                    rng_set.combat_potion_generation,
                    pool=ctx.combat.potion_pool)
            else:
                potion = legacy_random_potion_out_of_combat(
                    ctx.combat._rng, pool=ctx.combat.potion_pool)
            if not try_to_procure(ctx.hooks, player, potion):
                break

    def use_out_of_combat(self, run) -> None:
        from .potion_pools import (
            generate_random_potion,
            legacy_random_potion_out_of_combat,
        )
        while run.has_open_potion_slot:
            if run.rng_set is not None:
                potion = generate_random_potion(
                    run.rng_set.combat_potion_generation,
                    pool=run.potion_pool)
            else:
                potion = legacy_random_potion_out_of_combat(
                    run.rng, pool=run.potion_pool)
            if not run.add_potion(potion):
                break


@register_potion
class FairyInABottle(Potion):
    """When your HP would drop to 0, this potion is discarded instead and you
    heal to 30% of your Max HP.

    Source: FairyInABottle.cs — Rare, PotionUsage.Automatic,
    CanBeGeneratedInCombat=false. `ShouldDie` is false for its owner only, and
    `AfterPreventingDeath` (:42-45) runs the FULL use wrapper —
    `await OnUseWrapper(...)`, not a bare OnUse — so RemoveBeforeUse discards
    it, `CreatureCmd.Heal(max(MaxHp * 0.3, 1))` runs, and
    `Hook.AfterPotionUsed` fires. A prevented death now leaves the creature
    dead at 0 HP (CreatureCmd.cs:565), so the heal lands the player exactly on
    30% of Max HP."""

    id = "fairy_in_a_bottle"
    name = "Fairy in a Bottle"
    rarity = "rare"
    usage = USAGE_AUTOMATIC
    HEAL_PERCENT = 30

    # ── Hook listener (the potion listens while it sits in the belt) ──────

    def should_die(self, creature: Creature) -> bool:
        return creature.side != "player"

    def after_preventing_death(self, creature: Creature) -> None:
        combat = self.combat
        if combat is None:
            # The OUT-OF-COMBAT arm. `AfterPreventingDeath` is dispatched by
            # CreatureCmd's Kill tail over RunState.IterateHookListeners
            # (RunState.cs:545-596) as well as the combat walk, so `creature`
            # here is the RunState — every event HP loss reaches it. The
            # wrapper is written for a null combat state: :294 reads it, and
            # :298/:334/:336/:340 null-check it, so out of combat OnUseWrapper
            # reduces to :293 RemoveBeforeUse and :327 OnUse. AfterPotionUsed
            # dispatches too, but both C# implementers (BeltBuckle.cs:79-85,
            # ReptileTrinket.cs:22-30) open on IsInProgress, so it has no
            # listener here — the same reasoning RunState.use_potion records.
            run = creature
            run.discard_potion(self)            # RemoveBeforeUse
            self.use_out_of_combat(run)
            return
        # OnUseWrapper (PotionModel.cs:291-342), not a bare OnUse: :293
        # RemoveBeforeUse, :327 OnUse, :338 Hook.AfterPotionUsed. Reptile
        # Trinket's 3 temporary Strength and Belt Buckle's Dexterity both hang
        # off that last dispatch.
        combat.player.discard_potion(self)      # RemoveBeforeUse
        self.use(combat._ctx(), creature)
        combat.hooks.on_potion_used(self, creature)

    def use(self, ctx: CombatCtx, target: Creature | None = None) -> None:
        from .cmds import CreatureCmd
        creature = target or ctx.player
        heal_to = max(creature.max_hp * self.HEAL_PERCENT // 100, 1)
        CreatureCmd.heal(ctx.hooks, creature, heal_to - creature.hp)

    def use_out_of_combat(self, run) -> None:
        """`OnUse`'s null-combat arm — `CreatureCmd.Heal(target,
        Max(MaxHp * 0.3m, 1m))` with the RunState as the target. The heal is
        BY that amount in C# and TO it here, which is the same number because
        CreatureCmd.cs:565 leaves a prevented death sitting on 0 HP; this
        potion is never executed by any other path (FairyInABottle.cs:19-22)."""
        run.heal(max(run.max_hp * self.HEAL_PERCENT // 100, 1) - run.hp)


def _choose_a_card_screen(ctx: CombatCtx, cards: list) -> None:
    """`CardSelectCmd.FromChooseACardScreen(..., canSkip: true)`
    (CardSelectCmd.cs:216-261) for the three-card generator potions.

    The generated cards go up as a screen and only the pick is added — the
    caller's `if (cardModel != null)` means declining adds nothing. Parity
    defers the pick to the recording's `SelectCardFromScreen`; the legacy arm
    resolves it inline through `CombatState.select_cards`, so the installed
    selector is the policy (it may return [] to take the skip). The legacy arm
    used to take `cards[0]` unconditionally, so the other two candidates did
    not exist and the screen could never be declined.
    """
    combat = ctx.combat
    combat.offer_screen_selection(cards)
    if combat.combat_rng.is_parity:
        return
    # `Selector.GetSelectedCards(cards, 0, 1)` + `ShowScreen(..., canSkip:
    # true)` (CardSelectCmd.cs:230,239): MinSelect 0, MaxSelect 1. The
    # `_optional` purpose is what puts the decline in front of a driver-mediated
    # policy (driver.SKIPPABLE_PURPOSES); `min_select=0` is what lets the
    # selectorless engine default reach it. Toolbox keeps the plain
    # "choose_a_card" purpose — its screen forbids the decline. `min_select=0`
    # already keeps `require_manual_confirmation` true here (0 != count 1), so
    # `has_shortcut=False` is redundant today, but FromChooseACardScreen has no
    # shortcut in C# at all (CardSelectCmd.cs:216-261) — pass it explicitly so
    # this doesn't rely on that coincidence.
    picked = combat.select_cards(
        "choose_a_card_optional", cards, 1, min_select=0, has_shortcut=False)
    combat.resolve_screen_selection(cards.index(picked[0]) if picked else None)


def try_to_procure(hooks, player, potion: Potion) -> bool:
    """PotionCmd.TryToProcure (PotionCmd.cs:28-54) for a combat-side source.

    The game has exactly ONE procure entry point and it is gated: the
    `Hook.ShouldProcurePotion` pass runs first (Sozu.cs:17-20 is its only
    implementer and refuses every potion for its owner), and a successful
    `AddPotionInternal` fires `Hook.AfterPotionProcured` (Belt Buckle drops
    its 2 Dexterity there — the half of "while you have no potions" that
    enforces the *no*). The sim used to split the operation: RunState.add_potion
    ran the gate, PlayerCombatState.add_potion ran neither half.

    Both hooks dispatch over `runState.IterateHookListeners(combatState)`
    (Hook.cs:972, :2408), i.e. the combat listener walk while a combat is in
    progress. The relic-side signature is `(run, potion)`; CombatState has no
    run handle, and the only implementer reads neither argument.
    """
    for _l, fn in hooks._each("should_procure_potion"):
        if not fn(None, potion):
            return False
    if not player.add_potion(potion):
        return False
    for _l, fn in hooks._each("after_potion_procured"):
        fn(potion)
    return True


ALL_POTIONS: dict[str, type[Potion]] = dict(_POTION_CLASSES)


def random_potion(rng: random.Random, owner=None) -> Potion:
    """A uniformly random reward-pool potion (mirrors PotionFactory.
    CreateRandomPotionInCombat for the sim's implemented pool; Alchemize).
    Sorted by id so the pick is a pure function of the RNG state."""
    # CreateRandomPotionInCombat filters `p.CanBeGeneratedInCombat` — the three
    # healing-adjacent potions are off the table in combat (the parity
    # generators read the same set).
    from .potion_pools import NOT_GENERATED_IN_COMBAT
    # `owner` is the run or combat whose character scopes the pool; None keeps
    # the whole implemented catalogue (bare-CombatState callers/tests).
    owns = owner.owns_potion if owner is not None else lambda cls: True
    pool = sorted(
        (
            c for c in _POTION_CLASSES.values()
            if c.in_reward_pool and c.id not in NOT_GENERATED_IN_COMBAT
            and owns(c)
        ),
        key=lambda c: c.id,
    )
    return rng.choice(pool)()
