"""Cards granted only by events — not part of any reward pool.

Sources: ByrdonisEgg.cs (Byrdonis Nest), Peck.cs and ToricToughness.cs
(Wood Carvings), plus the Act-2 (Underdocks / Hive) event cards —
UltimateStrike/UltimateDefend (Amalgamator), Exterminate/Squash (Bugslayer),
Metamorphosis (Spirit Grafter), Enlightenment (Zen Weaver), FeedingFrenzy
(Endless Conveyor), and LanternKey (The Lantern Key). The Trash Heap card pool
lives in trash_heap_cards.py.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class ByrdonisEggCard(Card):
    """Quest — Unplayable. Taken from the Byrdonis Nest event; in the game it
    adds a "Hatch" rest-site option (pet). The sim has no rest sites, so in
    combat it is simply an unplayable card clogging the deck.

    Source: ByrdonisEgg.cs
      Cost -1 | Quest | Quest | TargetType.None | Unplayable | MaxUpgradeLevel 0
    """
    id = "byrdonis_egg"
    name = "Byrdonis Egg"
    card_type = CardType.QUEST
    rarity = CardRarity.QUEST
    target_type = TargetType.NONE
    is_playable = False
    max_upgrade_level = 0
    is_unpowered = True
    can_be_generated_by_modifiers = False

    def _init_vars(self) -> None:
        self._energy_cost = 0

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        pass


@register_card
class PeckCard(Card):
    """Attack (Event, 1E) — deal 2 damage 3 times.

    Source: Peck.cs
      Cost 1 | Attack | Event | TargetType.AnyEnemy
      OnPlay: Attack(2) × Repeat(3)
      OnUpgrade: repeat +1 (→ 4 hits)
    Granted by Wood Carvings (Bird), transforming a Basic card.
    """
    id = "peck"
    name = "Peck"
    card_type = CardType.ATTACK
    rarity = CardRarity.EVENT
    target_type = TargetType.ANY_ENEMY

    def _init_vars(self) -> None:
        self._energy_cost = 1
        self._damage = 2
        self._hits = 3

    def _on_upgrade(self) -> None:
        self._hits += 1

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import DamageCmd
        target = ctx.resolve_target(target_idx)
        for _ in range(self._hits):
            if target.is_gone or ctx.player.is_dead:
                break
            DamageCmd.deal(ctx.hooks, target, self._damage, dealer=ctx.player, card=self)


@register_card
class ToricToughnessCard(Card):
    """Skill (Event, 2E) — gain 5 block; for the next 2 turns, gain 5 block
    after your block is cleared.

    Source: ToricToughness.cs
      Cost 2 | Skill | Event | TargetType.Self
      OnPlay: GainBlock(5, Move), then Apply ToricToughnessPower(2 turns)
              carrying the block actually gained
      OnUpgrade: block +2 (→ 7)
    Granted by Wood Carvings (Torus), transforming a Basic card.
    """
    id = "toric_toughness"
    name = "Toric Toughness"
    card_type = CardType.SKILL
    rarity = CardRarity.EVENT
    target_type = TargetType.SELF

    def _init_vars(self) -> None:
        self._energy_cost = 2
        self._block = 5
        self._turns = 2

    def _on_upgrade(self) -> None:
        self._block += 2

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import BlockCmd, PowerCmd
        from ..powers import ToricToughnessPower
        gained = BlockCmd.apply(ctx.hooks, ctx.player, self._block, card=self)
        PowerCmd.apply(
            ctx.hooks, ctx.player, ToricToughnessPower, self._turns, applier=ctx.player
        )
        power = ctx.player.powers.get("toric_toughness")
        if power is not None:
            power.set_block(gained)


@register_card
class UltimateStrikeCard(Card):
    """Attack (Uncommon, 1E) — deal 14 damage. Tagged Strike.

    Source: UltimateStrike.cs — Damage 14 (Move), OnUpgrade +6. Granted by the
    Amalgamator event (Combine Strikes).
    """
    id = "ultimate_strike"
    name = "Ultimate Strike"
    card_type = CardType.ATTACK
    rarity = CardRarity.UNCOMMON
    target_type = TargetType.ANY_ENEMY
    tags = frozenset({"strike"})

    def _init_vars(self) -> None:
        self._energy_cost = 1
        self._damage = 14

    def _on_upgrade(self) -> None:
        self._damage += 6

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import DamageCmd
        DamageCmd.deal(
            ctx.hooks, ctx.resolve_target(target_idx), self._damage,
            dealer=ctx.player, card=self,
        )


@register_card
class UltimateDefendCard(Card):
    """Skill (Uncommon, 1E) — gain 11 block. Tagged Defend.

    Source: UltimateDefend.cs — Block 11 (Move), OnUpgrade +4. Granted by the
    Amalgamator event (Combine Defends).
    """
    id = "ultimate_defend"
    name = "Ultimate Defend"
    card_type = CardType.SKILL
    rarity = CardRarity.UNCOMMON
    target_type = TargetType.SELF
    tags = frozenset({"defend"})

    def _init_vars(self) -> None:
        self._energy_cost = 1
        self._block = 11

    def _on_upgrade(self) -> None:
        self._block += 4

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import BlockCmd
        BlockCmd.apply(ctx.hooks, ctx.player, self._block, card=self)


@register_card
class ExterminateCard(Card):
    """Attack (Event, 1E) — deal 3 damage 4 times to ALL enemies.

    Source: Exterminate.cs — Damage 3 (Move) × Repeat 4, TargetAllEnemies,
    OnUpgrade damage +1. Granted by the Bugslayer event.
    """
    id = "exterminate"
    name = "Exterminate"
    card_type = CardType.ATTACK
    rarity = CardRarity.EVENT
    target_type = TargetType.ALL_ENEMIES
    handles_own_routing = True

    def _init_vars(self) -> None:
        self._energy_cost = 1
        self._damage = 3
        self._hits = 4

    def _on_upgrade(self) -> None:
        self._damage += 1

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import DamageCmd
        for _ in range(self._hits):
            for enemy in list(ctx.combat.enemies):
                if enemy.is_gone:
                    continue
                DamageCmd.deal(ctx.hooks, enemy, self._damage, dealer=ctx.player, card=self)
            if ctx.combat._all_enemies_dead() or ctx.player.is_dead:
                break


@register_card
class SquashCard(Card):
    """Attack (Event, 1E) — deal 10 damage and apply 2 Vulnerable.

    Source: Squash.cs — Damage 10 (Move), Vulnerable 2, OnUpgrade damage +2 /
    Vulnerable +1. Granted by the Bugslayer event.
    """
    id = "squash"
    name = "Squash"
    card_type = CardType.ATTACK
    rarity = CardRarity.EVENT
    target_type = TargetType.ANY_ENEMY

    def _init_vars(self) -> None:
        self._energy_cost = 1
        self._damage = 10
        self._vulnerable = 2

    def _on_upgrade(self) -> None:
        self._damage += 2
        self._vulnerable += 1

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import DamageCmd, PowerCmd
        from ..powers import VulnerablePower
        target = ctx.resolve_target(target_idx)
        DamageCmd.deal(ctx.hooks, target, self._damage, dealer=ctx.player, card=self)
        if not target.is_gone:
            PowerCmd.apply(
                ctx.hooks, target, VulnerablePower, self._vulnerable, applier=ctx.player
            )


@register_card
class MetamorphosisCard(Card):
    """Skill (Event, 2E, Exhaust) — add 3 random Attacks to your draw pile;
    they cost 0 this combat.

    Source: Metamorphosis.cs — CardsVar 3, add GetForCombat Attacks (free this
    combat) to the draw pile, OnUpgrade +2. Granted by the Spirit Grafter
    event. (The game draws from the character pool; the sim uses the Ironclad
    combat pool.)
    """
    id = "metamorphosis"
    name = "Metamorphosis"
    card_type = CardType.SKILL
    rarity = CardRarity.EVENT
    target_type = TargetType.SELF
    exhausts = True

    def _init_vars(self) -> None:
        self._energy_cost = 2
        self._cards = 3

    def _on_upgrade(self) -> None:
        self._cards += 2

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cards import CardType as _CT
        from ..cards.pool import random_pool_cards
        from ..cmds import CardPileCmd
        for card in random_pool_cards(ctx.combat._rng, self._cards, _CT.ATTACK):
            card.set_cost_this_combat(0)
            CardPileCmd.add_to_draw(ctx.hooks, ctx.player, card)


@register_card
class EnlightenmentCard(Card):
    """Skill (Event, 0E, Exhaust) — reduce the cost of every card in your hand
    to 1 this turn (this combat when upgraded).

    Source: Enlightenment.cs — hand cards' EnergyCost.SetThisTurnOrUntilPlayed
    (1, reduceOnly), or SetThisCombat when upgraded. Granted by the Zen Weaver
    event.
    """
    id = "enlightenment"
    name = "Enlightenment"
    card_type = CardType.SKILL
    rarity = CardRarity.EVENT
    target_type = TargetType.SELF
    exhausts = True

    def _init_vars(self) -> None:
        self._energy_cost = 0

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        for card in ctx.player.hand:
            if card.energy_cost <= 1:
                continue  # reduceOnly: never raise a cost
            if self.upgrade_level > 0:
                card.set_cost_this_combat(1)
            else:
                card.add_cost_this_turn(1 - card.energy_cost)


@register_card
class FeedingFrenzyCard(Card):
    """Skill (Event, 0E) — gain 5 temporary Strength (lost at end of turn).

    Source: FeedingFrenzy.cs — apply FeedingFrenzyPower (a TemporaryStrength)
    5, OnUpgrade +2. Added to the deck by the Endless Conveyor event (Seapunk
    Salad dish).
    """
    id = "feeding_frenzy"
    name = "Feeding Frenzy"
    card_type = CardType.SKILL
    rarity = CardRarity.EVENT
    target_type = TargetType.SELF

    def _init_vars(self) -> None:
        self._energy_cost = 0
        self._strength = 5

    def _on_upgrade(self) -> None:
        self._strength += 2

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import PowerCmd
        from ..powers import FeedingFrenzyPower
        PowerCmd.apply(
            ctx.hooks, ctx.player, FeedingFrenzyPower, self._strength, applier=ctx.player
        )


@register_card
class LanternKeyCard(Card):
    """Quest — Unplayable. Kept from The Lantern Key event (Keep the Key).

    Source: LanternKey.cs — Cost -1 | Quest | Quest | Unplayable |
    MaxUpgradeLevel 0. In the game it redirects the next Act-3 event to War
    Historian Repy; the sim has no map, so it is an inert unplayable card.
    """
    id = "lantern_key"
    name = "Lantern Key"
    card_type = CardType.QUEST
    rarity = CardRarity.QUEST
    target_type = TargetType.SELF
    is_playable = False
    max_upgrade_level = 0
    is_unpowered = True
    can_be_generated_by_modifiers = False

    def _init_vars(self) -> None:
        self._energy_cost = 0

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        pass
