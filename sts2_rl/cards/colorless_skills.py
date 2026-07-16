"""Colorless Skill cards (ColorlessCardPool.cs).

One class per card, numbers transcribed from src/Core/Models/Cards/<Name>.cs.
The pool's 11 multiplayer-only cards are excluded (FilterForPlayerCount).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class AlchemizeCard(Card):
    """Skill (Rare, 1E) — obtain a random potion. Exhaust.

    Source: Alchemize.cs — PotionCmd.TryToProcure(random potion); a full
    belt keeps nothing. CanBeGeneratedInCombat=false. OnUpgrade: cost -1.
    """
    id = "alchemize"
    name = "Alchemize"
    card_type = CardType.SKILL
    rarity = CardRarity.RARE
    target_type = TargetType.SELF
    exhausts = True
    can_be_generated_in_combat = False

    def _init_vars(self) -> None:
        self._energy_cost = 1

    def _on_upgrade(self) -> None:
        self._energy_cost = max(0, self._energy_cost - 1)

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..potions import random_potion
        player = ctx.player
        if len(player.potions) < player.max_potions:
            player.potions.append(random_potion(ctx.combat._rng))


@register_card
class AnointedCard(Card):
    """Skill (Rare, 1E) — draw random Rare cards from your draw pile until
    your hand is full. Exhaust.

    Source: Anointed.cs — TakeRandom(10 - hand count) over the draw pile's
    Rare cards, moved to the hand. OnUpgrade: gains Retain.
    """
    id = "anointed"
    name = "Anointed"
    card_type = CardType.SKILL
    rarity = CardRarity.RARE
    target_type = TargetType.SELF
    exhausts = True

    def _init_vars(self) -> None:
        self._energy_cost = 1
        self.retain = False

    def _on_upgrade(self) -> None:
        self.retain = True

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        player = ctx.player
        space = player.MAX_HAND_SIZE - len(player.hand)
        rares = [c for c in player.draw_pile if c.rarity == CardRarity.RARE]
        for card in ctx.combat._rng.sample(rares, min(space, len(rares))):
            player.draw_pile.remove(card)
            player.hand.append(card)


@register_card
class BeatDownCard(Card):
    """Skill (Rare, 3E) — play 3 random Attacks from your discard pile.

    Source: BeatDown.cs — shuffle the discard pile's playable Attacks, take
    CardsVar(3), CardCmd.AutoPlay each (AnyEnemy cards hit a random enemy).
    OnUpgrade +1.
    """
    id = "beat_down"
    name = "Beat Down"
    card_type = CardType.SKILL
    rarity = CardRarity.RARE
    target_type = TargetType.RANDOM_ENEMY

    def _init_vars(self) -> None:
        self._energy_cost = 3
        self._cards = 3

    def _on_upgrade(self) -> None:
        self._cards += 1

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        candidates = [
            c for c in ctx.player.discard_pile
            if c.card_type == CardType.ATTACK and c.is_playable
        ]
        ctx.combat._rng.shuffle(candidates)
        for card in candidates[: self._cards]:
            if ctx.combat.is_over or ctx.player.is_dead:
                break
            ctx.combat.auto_play_card(card)


@register_card
class CatastropheCard(Card):
    """Skill (Uncommon, 2E) — play 2 random cards from your draw pile.

    Source: Catastrophe.cs — for each of CardsVar(2): a random playable
    draw-pile card (falling back to any draw-pile card), CardCmd.AutoPlay.
    OnUpgrade +1.
    """
    id = "catastrophe"
    name = "Catastrophe"
    card_type = CardType.SKILL
    rarity = CardRarity.UNCOMMON
    target_type = TargetType.SELF

    def _init_vars(self) -> None:
        self._energy_cost = 2
        self._cards = 2

    def _on_upgrade(self) -> None:
        self._cards += 1

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        for _ in range(self._cards):
            if ctx.combat.is_over or ctx.player.is_dead:
                break
            playable = [c for c in ctx.player.draw_pile if c.is_playable]
            options = playable or ctx.player.draw_pile
            if not options:
                break
            ctx.combat.auto_play_card(ctx.combat._rng.choice(options))


@register_card
class DarkShacklesCard(Card):
    """Skill (Uncommon, 0E) — an enemy loses 9 Strength this turn. Exhaust.

    Source: DarkShackles.cs — DarkShacklesPower 9 (a TemporaryStrengthPower
    with IsPositive=false). OnUpgrade +6.
    """
    id = "dark_shackles"
    name = "Dark Shackles"
    card_type = CardType.SKILL
    rarity = CardRarity.UNCOMMON
    target_type = TargetType.ANY_ENEMY
    exhausts = True

    def _init_vars(self) -> None:
        self._energy_cost = 0
        self._strength = 9

    def _on_upgrade(self) -> None:
        self._strength += 6

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import PowerCmd
        from ..powers import DarkShacklesPower
        target = ctx.resolve_target(target_idx)
        PowerCmd.apply(
            ctx.hooks, target, DarkShacklesPower, self._strength, applier=ctx.player
        )


@register_card
class DiscoveryCard(Card):
    """Skill (Uncommon, 1E) — choose 1 of 3 random cards from your character
    pool to add to your hand; it costs 0 this turn. Exhaust.

    Source: Discovery.cs — GetDistinctForCombat(character pool, 3), choose-a-
    card screen, SetToFreeThisTurn, add to hand. OnUpgrade: no Exhaust.
    """
    id = "discovery"
    name = "Discovery"
    card_type = CardType.SKILL
    rarity = CardRarity.UNCOMMON
    target_type = TargetType.SELF

    def _init_vars(self) -> None:
        self._energy_cost = 1
        self.exhausts = True

    def _on_upgrade(self) -> None:
        self.exhausts = False

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from .pool import random_pool_cards
        from ..cmds import CardPileCmd
        options = random_pool_cards(ctx.combat._rng, 3, distinct=True)
        chosen = ctx.combat.select_cards("obtain", options, 1)
        for card in chosen:
            card.set_free_this_turn()
            CardPileCmd.add_to_hand(ctx.hooks, ctx.player, card)


@register_card
class EquilibriumCard(Card):
    """Skill (Uncommon, 2E) — gain 13 block; retain your hand this turn.

    Source: Equilibrium.cs — Block 13 (Move) + RetainHandPower 1. OnUpgrade
    block +3.
    """
    id = "equilibrium"
    name = "Equilibrium"
    card_type = CardType.SKILL
    rarity = CardRarity.UNCOMMON
    target_type = TargetType.SELF

    def _init_vars(self) -> None:
        self._energy_cost = 2
        self._block = 13

    def _on_upgrade(self) -> None:
        self._block += 3

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import BlockCmd, PowerCmd
        from ..powers import RetainHandPower
        BlockCmd.apply(ctx.hooks, ctx.player, self._block, card=self)
        PowerCmd.apply(ctx.hooks, ctx.player, RetainHandPower, 1, applier=ctx.player)


@register_card
class FinesseCard(Card):
    """Skill (Uncommon, 0E) — gain 4 block; draw 1 card.

    Source: Finesse.cs — Block 4 (Move), Draw 1, OnUpgrade block +3.
    """
    id = "finesse"
    name = "Finesse"
    card_type = CardType.SKILL
    rarity = CardRarity.UNCOMMON
    target_type = TargetType.SELF

    def _init_vars(self) -> None:
        self._energy_cost = 0
        self._block = 4
        self._cards = 1

    def _on_upgrade(self) -> None:
        self._block += 3

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import BlockCmd, DrawCmd
        BlockCmd.apply(ctx.hooks, ctx.player, self._block, card=self)
        DrawCmd.draw(ctx.player, self._cards)


@register_card
class HiddenGemCard(Card):
    """Skill (Rare, 1E) — a random playable card in your draw pile is played
    2 additional times this combat.

    Source: HiddenGem.cs — pick a random draw-pile card (no Unplayable, no
    Curse/Quest, no enchanted replay; Attacks/Skills/Powers preferred) and
    raise its BaseReplayCount by 2. CanBeGeneratedInCombat=false.
    OnUpgrade +1.
    """
    id = "hidden_gem"
    name = "Hidden Gem"
    card_type = CardType.SKILL
    rarity = CardRarity.RARE
    target_type = TargetType.SELF
    can_be_generated_in_combat = False

    def _init_vars(self) -> None:
        self._energy_cost = 1
        self._replay = 2

    def _on_upgrade(self) -> None:
        self._replay += 1

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        eligible = [
            c for c in ctx.player.draw_pile
            if c.is_playable
            and c.card_type not in (CardType.CURSE, CardType.QUEST)
            and not self._has_replay_enchantment(c)
        ]
        preferred = [
            c for c in eligible
            if c.card_type in (CardType.ATTACK, CardType.SKILL, CardType.POWER)
        ]
        options = preferred or eligible
        if not options:
            return
        card = ctx.combat._rng.choice(options)
        card.base_replay_count += self._replay

    @staticmethod
    def _has_replay_enchantment(card: Card) -> bool:
        """GetEnchantedReplayCount() >= 1: Spiral/Glam already replay it."""
        return card.enchantment is not None and card.enchantment.id in (
            "spiral", "glam"
        )


@register_card
class ImpatienceCard(Card):
    """Skill (Uncommon, 0E) — if you have no Attacks in hand, draw 2 cards.

    Source: Impatience.cs — CardsVar 2, OnUpgrade +1.
    """
    id = "impatience"
    name = "Impatience"
    card_type = CardType.SKILL
    rarity = CardRarity.UNCOMMON
    target_type = TargetType.SELF

    def _init_vars(self) -> None:
        self._energy_cost = 0
        self._cards = 2

    def _on_upgrade(self) -> None:
        self._cards += 1

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import DrawCmd
        if not any(c.card_type == CardType.ATTACK for c in ctx.player.hand):
            DrawCmd.draw(ctx.player, self._cards)


@register_card
class JackOfAllTradesCard(Card):
    """Skill (Uncommon, 0E) — add 1 random Colorless card to your hand.
    Exhaust.

    Source: JackOfAllTrades.cs — GetDistinctForCombat over the Colorless
    pool minus Jack of All Trades itself. OnUpgrade +1.
    """
    id = "jack_of_all_trades"
    name = "Jack of All Trades"
    card_type = CardType.SKILL
    rarity = CardRarity.UNCOMMON
    target_type = TargetType.SELF
    exhausts = True

    def _init_vars(self) -> None:
        self._energy_cost = 0
        self._cards = 1

    def _on_upgrade(self) -> None:
        self._cards += 1

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from .pool import COLORLESS_POOL, random_pool_cards
        from ..cmds import CardPileCmd
        for card in random_pool_cards(
            ctx.combat._rng, self._cards, distinct=True,
            pool=COLORLESS_POOL, exclude_ids={self.id},
        ):
            CardPileCmd.add_to_hand(ctx.hooks, ctx.player, card)


@register_card
class MasterOfStrategyCard(Card):
    """Skill (Rare, 0E) — draw 3 cards. Exhaust.

    Source: MasterOfStrategy.cs — CardsVar 3, OnUpgrade +1.
    """
    id = "master_of_strategy"
    name = "Master of Strategy"
    card_type = CardType.SKILL
    rarity = CardRarity.RARE
    target_type = TargetType.SELF
    exhausts = True

    def _init_vars(self) -> None:
        self._energy_cost = 0
        self._cards = 3

    def _on_upgrade(self) -> None:
        self._cards += 1

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import DrawCmd
        DrawCmd.draw(ctx.player, self._cards)


@register_card
class PanicButtonCard(Card):
    """Skill (Uncommon, 0E) — gain 30 block; you cannot gain block from
    cards for 2 turns. Exhaust.

    Source: PanicButton.cs — Block 30 (Move) + NoBlockPower 2. OnUpgrade
    block +10.
    """
    id = "panic_button"
    name = "Panic Button"
    card_type = CardType.SKILL
    rarity = CardRarity.UNCOMMON
    target_type = TargetType.SELF
    exhausts = True

    def _init_vars(self) -> None:
        self._energy_cost = 0
        self._block = 30
        self._turns = 2

    def _on_upgrade(self) -> None:
        self._block += 10

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import BlockCmd, PowerCmd
        from ..powers import NoBlockPower
        BlockCmd.apply(ctx.hooks, ctx.player, self._block, card=self)
        PowerCmd.apply(
            ctx.hooks, ctx.player, NoBlockPower, self._turns, applier=ctx.player
        )


@register_card
class ProductionCard(Card):
    """Skill (Uncommon, 0E) — gain 2 energy. Exhaust.

    Source: Production.cs — EnergyVar 2, OnUpgrade +1.
    """
    id = "production"
    name = "Production"
    card_type = CardType.SKILL
    rarity = CardRarity.UNCOMMON
    target_type = TargetType.SELF
    exhausts = True

    def _init_vars(self) -> None:
        self._energy_cost = 0
        self._energy_gain = 2

    def _on_upgrade(self) -> None:
        self._energy_gain += 1

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import EnergyCmd
        EnergyCmd.gain(ctx.hooks, ctx.player, self._energy_gain)


@register_card
class ProlongCard(Card):
    """Skill (Uncommon, 0E) — next turn, regain your current block after it
    is cleared. Exhaust.

    Source: Prolong.cs — BlockNextTurnPower(current block). OnUpgrade: no
    Exhaust.
    """
    id = "prolong"
    name = "Prolong"
    card_type = CardType.SKILL
    rarity = CardRarity.UNCOMMON
    target_type = TargetType.SELF

    def _init_vars(self) -> None:
        self._energy_cost = 0
        self.exhausts = True

    def _on_upgrade(self) -> None:
        self.exhausts = False

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import PowerCmd
        from ..powers import BlockNextTurnPower
        if ctx.player.block > 0:
            PowerCmd.apply(
                ctx.hooks, ctx.player, BlockNextTurnPower, ctx.player.block,
                applier=ctx.player,
            )


@register_card
class PurityCard(Card):
    """Skill (Uncommon, 0E) — Retain. Exhaust up to 3 cards from your hand.
    Exhaust.

    Source: Purity.cs — hand selection (0..3) → CardCmd.Exhaust each.
    OnUpgrade +2 (→ 5).
    """
    id = "purity"
    name = "Purity"
    card_type = CardType.SKILL
    rarity = CardRarity.UNCOMMON
    target_type = TargetType.SELF
    retain = True
    exhausts = True

    def _init_vars(self) -> None:
        self._energy_cost = 0
        self._cards = 3

    def _on_upgrade(self) -> None:
        self._cards += 2

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import CardSelectCmd, ExhaustCmd
        chosen = CardSelectCmd.from_hand(
            ctx.hooks, ctx.player, "exhaust", count=self._cards
        )
        for card in chosen:
            ExhaustCmd.exhaust(ctx.hooks, ctx.player, card)


@register_card
class RestlessnessCard(Card):
    """Skill (Uncommon, 0E) — Retain. If this is your only card in hand,
    draw 2 cards and gain 2 energy.

    Source: Restlessness.cs — draws happen one at a time, then GainEnergy.
    OnUpgrade +1/+1.
    """
    id = "restlessness"
    name = "Restlessness"
    card_type = CardType.SKILL
    rarity = CardRarity.UNCOMMON
    target_type = TargetType.SELF
    retain = True

    def _init_vars(self) -> None:
        self._energy_cost = 0
        self._cards = 2
        self._energy_gain = 2

    def _on_upgrade(self) -> None:
        self._cards += 1
        self._energy_gain += 1

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import DrawCmd, EnergyCmd
        if ctx.player.hand:
            return  # the played card has left the hand; anything else fails it
        for _ in range(self._cards):
            DrawCmd.draw(ctx.player, 1)
        EnergyCmd.gain(ctx.hooks, ctx.player, self._energy_gain)


@register_card
class ScrawlCard(Card):
    """Skill (Rare, 1E) — draw cards until your hand is full. Exhaust.

    Source: Scrawl.cs — Draw(10 - hand count). OnUpgrade: gains Retain.
    """
    id = "scrawl"
    name = "Scrawl"
    card_type = CardType.SKILL
    rarity = CardRarity.RARE
    target_type = TargetType.SELF
    exhausts = True

    def _init_vars(self) -> None:
        self._energy_cost = 1
        self.retain = False

    def _on_upgrade(self) -> None:
        self.retain = True

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import DrawCmd
        DrawCmd.draw(ctx.player, ctx.player.MAX_HAND_SIZE - len(ctx.player.hand))


@register_card
class SecretTechniqueCard(Card):
    """Skill (Rare, 0E) — choose a Skill from your draw pile and put it into
    your hand. Exhaust.

    Source: SecretTechnique.cs — FromCombatPile(draw, filter Skill).
    OnUpgrade: no Exhaust.
    """
    id = "secret_technique"
    name = "Secret Technique"
    card_type = CardType.SKILL
    rarity = CardRarity.RARE
    target_type = TargetType.SELF

    _WANTED_TYPE = CardType.SKILL

    def _init_vars(self) -> None:
        self._energy_cost = 0
        self.exhausts = True

    def _on_upgrade(self) -> None:
        self.exhausts = False

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import CardSelectCmd
        player = ctx.player
        chosen = CardSelectCmd.from_pile(
            ctx.hooks, player.draw_pile, "from_draw", count=1,
            predicate=lambda c: c.card_type == self._WANTED_TYPE,
        )
        for card in chosen:
            if len(player.hand) >= player.MAX_HAND_SIZE:
                break
            player.draw_pile.remove(card)
            player.hand.append(card)


@register_card
class SecretWeaponCard(SecretTechniqueCard):
    """Skill (Rare, 0E) — choose an Attack from your draw pile and put it
    into your hand. Exhaust.

    Source: SecretWeapon.cs — FromCombatPile(draw, filter Attack).
    OnUpgrade: no Exhaust.
    """
    id = "secret_weapon"
    name = "Secret Weapon"

    _WANTED_TYPE = CardType.ATTACK


@register_card
class ShockwaveCard(Card):
    """Skill (Uncommon, 2E) — apply 3 Weak and 3 Vulnerable to ALL enemies.
    Exhaust.

    Source: Shockwave.cs — Power 3 of each to every hittable enemy.
    OnUpgrade +2.
    """
    id = "shockwave"
    name = "Shockwave"
    card_type = CardType.SKILL
    rarity = CardRarity.UNCOMMON
    target_type = TargetType.ALL_ENEMIES
    exhausts = True
    handles_own_routing = True

    def _init_vars(self) -> None:
        self._energy_cost = 2
        self._power_amount = 3

    def _on_upgrade(self) -> None:
        self._power_amount += 2

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import PowerCmd
        from ..powers import VulnerablePower, WeakPower
        for enemy in [e for e in ctx.enemies if not e.is_gone]:
            PowerCmd.apply(
                ctx.hooks, enemy, WeakPower, self._power_amount, applier=ctx.player
            )
            PowerCmd.apply(
                ctx.hooks, enemy, VulnerablePower, self._power_amount,
                applier=ctx.player,
            )


@register_card
class SplashCard(Card):
    """Skill (Uncommon, 1E) — choose 1 of 3 random Attacks from other
    characters' pools to add to your hand; it costs 0 this turn.

    Source: Splash.cs — with a single unlocked character the own pool is NOT
    removed from the candidate pools, so the single-character sim draws from
    the Ironclad pool. Upgraded Splash upgrades the 3 options.
    """
    id = "splash"
    name = "Splash"
    card_type = CardType.SKILL
    rarity = CardRarity.UNCOMMON
    target_type = TargetType.SELF

    def _init_vars(self) -> None:
        self._energy_cost = 1

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from .pool import random_pool_cards
        from ..cmds import CardPileCmd
        options = random_pool_cards(
            ctx.combat._rng, 3, CardType.ATTACK, distinct=True
        )
        if self.upgrade_level > 0:
            for card in options:
                if card.is_upgradable:
                    card.upgrade()
        chosen = ctx.combat.select_cards("obtain", options, 1)
        for card in chosen:
            card.set_free_this_turn()
            CardPileCmd.add_to_hand(ctx.hooks, ctx.player, card)


@register_card
class TheBombCard(Card):
    """Skill (Uncommon, 2E) — in 3 turns, deal 40 damage to ALL enemies.

    Source: TheBomb.cs — TheBombPower(3 turns).SetDamage(40). OnUpgrade
    damage +10.
    """
    id = "the_bomb"
    name = "The Bomb"
    card_type = CardType.SKILL
    rarity = CardRarity.UNCOMMON
    target_type = TargetType.SELF

    def _init_vars(self) -> None:
        self._energy_cost = 2
        self._turns = 3
        self._damage = 40

    def _on_upgrade(self) -> None:
        self._damage += 10

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import PowerCmd
        from ..powers import TheBombPower
        PowerCmd.apply(
            ctx.hooks, ctx.player, TheBombPower, self._turns, applier=ctx.player
        )
        power = ctx.player.powers.get("the_bomb")
        if power is not None:
            power.set_damage(self._damage)


@register_card
class TheGambitCard(Card):
    """Skill (Rare, 0E) — gain 50 block; if you take unblocked attack damage,
    you die.

    Source: TheGambit.cs — Block 50 (Move) + TheGambitPower. OnUpgrade
    block +25.
    """
    id = "the_gambit"
    name = "The Gambit"
    card_type = CardType.SKILL
    rarity = CardRarity.RARE
    target_type = TargetType.SELF

    def _init_vars(self) -> None:
        self._energy_cost = 0
        self._block = 50

    def _on_upgrade(self) -> None:
        self._block += 25

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import BlockCmd, PowerCmd
        from ..powers import TheGambitPower
        BlockCmd.apply(ctx.hooks, ctx.player, self._block, card=self)
        PowerCmd.apply(ctx.hooks, ctx.player, TheGambitPower, 1, applier=ctx.player)


@register_card
class ThinkingAheadCard(Card):
    """Skill (Uncommon, 0E) — draw 2 cards; put a card from your hand on top
    of your draw pile. Exhaust.

    Source: ThinkingAhead.cs — Draw 2, then a hand selection moves 1 card to
    the top of the draw pile. OnUpgrade: no Exhaust.
    """
    id = "thinking_ahead"
    name = "Thinking Ahead"
    card_type = CardType.SKILL
    rarity = CardRarity.UNCOMMON
    target_type = TargetType.SELF

    def _init_vars(self) -> None:
        self._energy_cost = 0
        self._cards = 2
        self.exhausts = True

    def _on_upgrade(self) -> None:
        self.exhausts = False

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import CardSelectCmd, DrawCmd
        DrawCmd.draw(ctx.player, self._cards)
        chosen = CardSelectCmd.from_hand(
            ctx.hooks, ctx.player, "to_draw_top", count=1
        )
        for card in chosen:
            ctx.player.hand.remove(card)
            ctx.player.draw_pile.append(card)  # end of list = top of pile
