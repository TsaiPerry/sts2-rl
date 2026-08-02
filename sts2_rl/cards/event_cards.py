"""Cards granted only by events — not part of any reward pool.

Sources: ByrdonisEgg.cs and ByrdSwoop.cs (Byrdonis Nest's Hatch, granted by
the Byrdpip relic — see relics/byrdpip.py), Peck.cs and ToricToughness.cs
(Wood Carvings), plus the Act-2 (Underdocks / Hive) event cards —
UltimateStrike/UltimateDefend (Amalgamator), Exterminate/Squash (Bugslayer),
Metamorphosis (Spirit Grafter), Enlightenment (Zen Weaver), FeedingFrenzy
(Endless Conveyor), and LanternKey (The Lantern Key). The Trash Heap card pool
lives in trash_heap_cards.py.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Card, CardRarity, CardType, TargetType, register_card
from ..rest_site import RestSiteOption

if TYPE_CHECKING:
    from ..combat import CombatCtx


@register_card
class ByrdonisEggCard(Card):
    """Quest — Unplayable. Taken from the Byrdonis Nest event. Adds a HATCH
    rest-site option (ByrdonisEgg.cs TryModifyRestSiteOptions): selecting it
    grants the Byrdpip relic, which transforms every Byrdonis Egg in the
    deck into ByrdSwoop (see relics/byrdpip.py).

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
        self._energy_cost = -1

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        pass

    def modify_rest_site_options(self, run, options) -> None:
        options.append(RestSiteOption("HATCH", lambda run: run.add_relic("byrdpip")))


@register_card
class ByrdSwoopCard(Card):
    """Attack (Event, 0E) — deal 14 damage. Granted by Byrdpip transforming
    every Byrdonis Egg in the deck (Hatch).

    Source: ByrdSwoop.cs — Damage 14 (Move), OnUpgrade +4.
    """
    id = "byrd_swoop"
    name = "Byrd Swoop"
    card_type = CardType.ATTACK
    rarity = CardRarity.EVENT
    target_type = TargetType.ANY_ENEMY

    def _init_vars(self) -> None:
        self._energy_cost = 0
        self._damage = 14

    def _on_upgrade(self) -> None:
        self._damage += 4

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        from ..cmds import DamageCmd
        DamageCmd.deal(
            ctx.hooks, ctx.resolve_target(target_idx), self._damage,
            dealer=ctx.player, card=self,
        )


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
    gains_block = True  # CardModel.GainsBlock
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
        # Instanced (ToricToughnessPower.cs): the block belongs to the
        # instance THIS play created, so take Apply's own result rather than
        # re-fetching by id, which is a FirstOrDefault over every instance.
        power = PowerCmd.apply(
            ctx.hooks, ctx.player, ToricToughnessPower, self._turns, applier=ctx.player
        )
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
    gains_block = True  # CardModel.GainsBlock
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
        # No liveness guard: C# applies this unconditionally and the only
        # gate is `Creature.CanReceivePowers` (Creature.cs:308-322), now
        # enforced inside PowerCmd.apply.
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
        for card in random_pool_cards(
            ctx.combat.combat_rng.card_gen, self._cards, _CT.ATTACK,
            pool=ctx.combat.card_pool,
        ):
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
                # Enlightenment.cs:21-24 registers an ABSOLUTE LocalCostModifier
                # of value 1 (CardEnergyCost.cs:197-203), not a delta computed
                # from the cost at this instant: a 3-cost card upgraded to base
                # 2 later in the same turn reads 1 in the game and 0 under a
                # relative -2. `set_cost_this_turn` is the absolute form.
                card.set_cost_this_turn(1)


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
    MaxUpgradeLevel 0. Two hooks, both gated on the Glory act: it forces every
    act-3 "?" node to roll an Event, and it redirects the next act-3 event to
    War Historian Repy (Hook.ModifyNextEvent). BOTH are ported.
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

    # LanternKey.cs:9 — `private const int _gloryActIndex = 2`.
    GLORY_ACT_INDEX = 2

    def _init_vars(self) -> None:
        self._energy_cost = -1

    def modify_unknown_map_point_room_types(self, run, room_types):
        """LanternKey.cs:21-28 — outside act 3 the set passes through; inside
        it, it is REPLACED by {Event} rather than filtered, so the key beats
        any other listener's narrowing."""
        from ..rooms import RoomType

        if run.act_index != self.GLORY_ACT_INDEX:
            return room_types
        return {RoomType.EVENT}

    def modify_next_event(self, run, event_id):
        """LanternKey.cs:29-36 — inside the Glory act the next event is REPLACED
        by War Historian Repy; outside it the incoming event passes through.

        That the target event's own `IsAllowed` is False is the POINT, not an
        obstacle: IsAllowed gates the random pool and this hook bypasses it, so
        any run carrying a Lantern Key into act 3 is routed there. The port used
        to justify omitting this with "the sim has no map", which was false twice
        over — the sim has a map, and it already dispatched the companion hook
        over the deck.
        """
        if run.act_index != self.GLORY_ACT_INDEX:
            return event_id
        return "war_historian_repy"

    def modify_unknown_map_point_room_types(self, run, room_types):
        """LanternKey.cs:21-28 — outside act 3 the set passes through; inside
        it, it is REPLACED by {Event} rather than filtered, so the key beats
        any other listener's narrowing."""
        from ..rooms import RoomType

        if run.act_index != self.GLORY_ACT_INDEX:
            return room_types
        return {RoomType.EVENT}

    def modify_next_event(self, run, event_id):
        """LanternKey.cs:29-36 — inside the Glory act the next event is REPLACED
        by War Historian Repy; outside it the incoming event passes through.

        That the target event's own `IsAllowed` is False is the POINT, not an
        obstacle: IsAllowed gates the random pool and this hook bypasses it, so
        any run carrying a Lantern Key into act 3 is routed there. The port used
        to justify omitting this with "the sim has no map", which was false twice
        over — the sim has a map, and it already dispatched the companion hook
        over the deck.
        """
        if run.act_index != self.GLORY_ACT_INDEX:
            return event_id
        return "war_historian_repy"

    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None:
        pass
