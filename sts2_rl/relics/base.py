"""Relic base class, rarity enum, and the id→class registry.

Mirrors STS2's RelicModel (src/Core/Models/Relics). Every relic subclasses
`Relic` and, like powers and cards, is a hook listener for the whole combat
(mirrors RelicModel.ShouldReceiveCombatHooks): it overrides only the hook
methods it needs and the HookSystem calls them by duck-typing. Pass relics to
`CombatState(relics=[...])`; `attach()` wires the combat back-reference and
registers the listener.

Hook mapping from the game (see CombatManager.SetupPlayerTurn):
  BeforeSideTurnStart (player)          → on_player_turn_start (pre-draw)
  AfterBlockCleared                     → on_block_cleared
  AfterEnergyReset                      → on_energy_reset
  ModifyHandDraw                        → modify_hand_draw
  AfterPlayerTurnStart(Late) /
  AfterSideTurnStart (player, post-draw)→ on_player_turn_started (post-draw)
  BeforeSideTurnEnd / AfterSideTurnEnd  → on_player_turn_end
  AfterCombatVictory                    → on_combat_end(player_won=True)

Relics whose entire effect lives outside combat (gold, map, deck edits, card
rewards, rest sites, potion rewards) are registered as documented no-op stubs
so the full pool is constructible; they simply have no hook methods. The sim
runs a single combat, so per-run counters (Girya lifts, Happy Flower's carry-
over turn counter) are per-combat / constructor-injected.
"""
from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

from ..valueprops import ValueProp

if TYPE_CHECKING:
    from ..combat import CombatState
    from ..creatures import Creature
    from ..hooks import HookSystem
    from ..monsters import Monster
    from ..player import PlayerCombatState


class RelicRarity(Enum):
    STARTER = "starter"
    COMMON = "common"
    UNCOMMON = "uncommon"
    RARE = "rare"
    SHOP = "shop"
    EVENT = "event"
    ANCIENT = "ancient"


# RelicModel.MerchantCost by rarity (non-ascension values). Ancient/Starter/
# Event relics are never shop-stocked, so their nominal price is astronomical.
_MERCHANT_COST_BY_RARITY: dict[RelicRarity, int] = {
    RelicRarity.COMMON: 175,
    RelicRarity.UNCOMMON: 225,
    RelicRarity.RARE: 275,
    RelicRarity.SHOP: 200,
    RelicRarity.ANCIENT: 999_999_999,
    RelicRarity.STARTER: 999_999_999,
    RelicRarity.EVENT: 999_999_999,
}


class RestSiteOption:
    """An extra rest-site action provided by a relic (mirrors RestSiteOption /
    Hook.TryModifyRestSiteOptions — Pael's Growth's Clone, Pumpkin Candle's
    Kindle, Meat Cleaver's Cook). `key` mirrors the source's OptionId;
    `on_select(run)` performs the effect (RestSiteOption.OnSelect)."""

    def __init__(self, key: str, on_select) -> None:
        self.key = key
        self.on_select = on_select

    def __repr__(self) -> str:
        return f"RestSiteOption({self.key})"


_RELIC_CLASSES: dict[str, type[Relic]] = {}


def register_relic(cls: type[Relic]) -> type[Relic]:
    _RELIC_CLASSES[cls.id] = cls
    return cls


def make_relic(relic_id: str) -> Relic:
    return _RELIC_CLASSES[relic_id]()


class Relic:
    """Base class for all relics, mirroring STS2's RelicModel.

    Subclasses override hook methods as needed; the hook system calls them via
    hasattr duck-typing. `attach` must be called before combat starts (done by
    CombatState.__init__ for relics passed to the constructor).
    """

    id: str
    name: str
    rarity: RelicRarity
    # RelicModel.IsAllowedInShops — a handful of relics (Amethyst Aubergine,
    # Bowler Hat, Lucky Fysh, Old Coin, The Courier) opt out of shop stock.
    is_allowed_in_shops: bool = True
    # RelicModel.AddsPet — the relic brings an event pet (Pael's Legion).
    # Player.HasEventPet gates Pael's Legion option at the Pael shrine.
    adds_pet: bool = False

    def __init__(self) -> None:
        self.combat: CombatState | None = None
        # RelicModel.IsWax (Toy Box): a wax copy of a relic; every 3rd combat
        # Toy Box melts one (the sim removes it from the run's relics).
        self.is_wax = False

    @property
    def merchant_cost(self) -> int:
        """RelicModel.MerchantCost: base gold price before the shop's ±15%
        jitter. Ancient/Starter/Event relics are effectively unbuyable."""
        return _MERCHANT_COST_BY_RARITY[self.rarity]

    def after_obtained(self, run) -> None:
        """RelicModel.AfterObtained: out-of-combat pickup effect (default
        no-op). RunState.add_relic invokes it. Golden Compass uses it to
        regenerate the current act's map as a golden path."""

    def attach(self, combat: CombatState) -> None:
        self.combat = combat
        combat.hooks.register(self)

    # RelicModel.IsAllowedAtNeow — Neow's positive/curse pools filter on this
    # (Kaleidoscope needs other characters' card pools, Massive Scroll is
    # multiplayer-only; both are never offerable in the single-character sim).
    is_allowed_at_neow: bool = True

    # ── Run-level reward / room hooks (duck-typed over run.relics, like the
    #    map pipeline below; defaults mirror the AbstractModel no-ops) ──────

    def should_force_potion_reward(self, run, room_type) -> bool:
        """Hook.ShouldForcePotionReward — force a potion into combat rewards."""
        return False

    def modify_combat_rewards(self, run, rewards) -> None:
        """Hook.ModifyRewards / TryModifyRewards — mutate a just-generated
        CombatRewards (Lava Rock adds relics to the act-1 boss rewards)."""

    def modify_card_reward_options(self, run, cards) -> None:
        """Hook.TryModifyCardRewardOptionsLate — mutate a card reward's
        options in place (Silver Crucible upgrades them, Silken Tress
        enchants them)."""

    def should_generate_treasure(self, run) -> bool:
        """Hook.ShouldGenerateTreasure — Silver Crucible skips the chest in
        the first treasure room entered."""
        return True

    def after_room_entered(self, run, point, room_type) -> None:
        """RelicModel.AfterRoomEntered."""

    def after_shop_entered(self, run, shop) -> None:
        """Fired when a merchant room's inventory has been stocked (the
        merchant branch of RelicModel.AfterRoomEntered — Lord's Parasol buys
        the whole inventory). `shop` is the sts2_rl.shop.MerchantInventory."""

    def after_item_purchased(self, run, entry, gold_spent) -> None:
        """RelicModel.AfterItemPurchased — fires after any successful
        merchant purchase (card, relic, potion, or card removal), with the
        gold actually spent. `entry` is the sts2_rl.shop.MerchantEntry that
        was bought (Maw Bank deactivates on the first `gold_spent > 0`)."""

    def after_card_added_to_deck(self, run, card) -> None:
        """RelicModel.AfterCardChangedPiles, filtered to a card entering the
        run's deck pile (Darkstone Periapt's +6 Max HP on a gained Curse)."""

    def modify_run_hp_loss(self, run, amount: int) -> int:
        """RelicModel.ModifyHpLostAfterOsty for out-of-combat HP loss: the
        game dispatches Hook.ModifyHpLost over the run state (CreatureCmd.cs),
        so event damage (RunState.lose_hp) goes through relics too (Tungsten
        Rod). Combat HP loss uses the combat-side modify_hp_lost hook.
        Chain hook — return the new amount."""
        return amount

    def after_rest_site_heal(self, run) -> None:
        """RelicModel.AfterRestSiteHeal (Stone Humidifier's +5 max HP)."""

    def modify_rest_site_options(self, run, options: "list[RestSiteOption]") -> None:
        """RelicModel.TryModifyRestSiteOptions — append extra rest-site
        actions (Pael's Growth's Clone, Pumpkin Candle's Kindle, Meat
        Cleaver's Cook). The driver surfaces them after Heal/Smith/Leave."""

    def modify_rest_site_heal_rewards(self, run, rewards) -> None:
        """RelicModel.TryModifyRestSiteHealRewards — mutate the reward
        screen offered after taking the rest site's heal option (Dream
        Catcher's 3-card choice). `rewards` is a rewards.CombatRewards, like
        modify_combat_rewards; RunState.rest_heal_rewards builds it."""

    def after_combat_end(self, run, room_type) -> None:
        """RelicModel.AfterCombatEnd, dispatched by RunState.finish_combat
        when the caller passes the room type (Fishing Rod's upgrade cycle)."""

    def should_allow_free_travel(self) -> bool:
        """RelicModel.ShouldAllowFreeTravel (Winged Boots)."""
        return False

    def on_free_travel_used(self, run) -> None:
        """Consume a free-travel charge (the source detects non-child travel
        in AfterRoomEntered; the sim tells the relic directly)."""

    # ── Run-level map hooks (see Card for the mirrored pipeline) ──────────

    def modify_generated_map(self, run, act_map, act_index):
        """AbstractModel.ModifyGeneratedMap."""
        return act_map

    def modify_generated_map_late(self, run, act_map, act_index):
        """AbstractModel.ModifyGeneratedMapLate."""
        return act_map

    def after_map_generated(self, run, act_map, act_index) -> None:
        """AbstractModel.AfterMapGenerated."""

    def modify_unknown_map_point_room_types(self, run, room_types):
        """AbstractModel.ModifyUnknownMapPointRoomTypes."""
        return room_types

    # ── Convenience reads ────────────────────────────────────────────────

    @property
    def player(self) -> PlayerCombatState:
        return self.combat.player

    @property
    def hooks(self) -> HookSystem:
        return self.combat.hooks

    @property
    def turn(self) -> int:
        return self.combat.turn

    def living_enemies(self) -> list[Monster]:
        """Mirrors ICombatState.HittableEnemies (the sim's DamageCmd applies
        the should_allow_hitting predicate on top)."""
        return [e for e in self.combat.enemies if not e.is_gone]

    def _check_win(self) -> None:
        """End combat if a relic effect just killed the last enemy (mirrors
        the CheckWinCondition that follows game commands). Needed because
        relic damage can fire outside play_card/end_turn's own checks."""
        if not self.combat.is_over and self.combat._all_enemies_dead():
            self.combat._end_combat(player_won=True)

    def __repr__(self) -> str:
        return self.name
