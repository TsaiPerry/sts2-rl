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
  AfterCombatVictoryEarly               → on_combat_end_early(player_won=True)
  AfterCombatVictory                    → on_combat_end(player_won=True)

A relic instance lives on RunState.relics and is re-attached to every new
CombatState, so anything it latches during a fight would otherwise last the
whole run. C# resets that state at the combat boundary (AfterCombatEnd /
BeforeCombatStart / AfterRoomEntered(CombatRoom)); `attach` runs the sim's
mirror of it, `reset_for_combat`.

Relics whose entire effect lives outside combat (gold, map, deck edits, card
rewards, rest sites, potion rewards) once had no sim system to live in and
were registered as documented no-op stubs so the full pool is constructible.
That premise expired as the run layer grew a gold ledger, a potion belt, rest
sites and card rewards; the remaining stubs are the ones whose system is still
genuinely absent, and each says which. The sim runs a single combat, so
per-run counters (Girya lifts, Happy Flower's carry-over turn counter) are
per-combat / constructor-injected.
"""
from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

from ..hooks import CAT_RELIC
from ..rest_site import RestSiteOption
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


# RelicModel.IsBeforeAct3TreasureChest (RelicModel.cs:452-456): the shared
# helper for relics that stop spawning at the Act 3 treasure chest. The floor
# is 38 in multiplayer and 41 in single player; the sim is single player.
_ACT3_TREASURE_CHEST_FLOOR = 41


def is_before_act3_treasure_chest(run) -> bool:
    """`RelicModel.IsBeforeAct3TreasureChest` — `runState.TotalFloor < 41`."""
    return run.total_floor < _ACT3_TREASURE_CHEST_FLOOR


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
    # After its owner's powers in the dispatch walk
    # (CombatState.IterateHookListeners, CombatState.cs:428-435).
    hook_category = CAT_RELIC
    # RelicModel.IsAllowedInShops — a handful of relics (Amethyst Aubergine,
    # Bowler Hat, Lucky Fysh, Old Coin, The Courier) opt out of shop stock.
    is_allowed_in_shops: bool = True
    # RelicModel.AddsPet — the relic brings an event pet (Pael's Legion).
    # Player.HasEventPet gates Pael's Legion option at the Pael shrine.
    adds_pet: bool = False
    # RelicModel.HasUponPickupEffect — the relic did its whole thing on
    # pickup (Strawberry); mirrored per relic from the source's overrides.
    has_upon_pickup_effect: bool = False
    # RelicModel.SpawnsPets (Byrdpip) — pet-spawning relics.
    spawns_pets: bool = False

    def __init__(self) -> None:
        self.combat: CombatState | None = None
        # RelicModel.IsWax (Toy Box): a wax copy of a relic; every 3rd combat
        # Toy Box melts one (the sim removes it from the run's relics).
        self.is_wax = False

    # RelicModel.MerchantCost is virtual: a relic may pin its own price
    # regardless of rarity (the Fake Merchant's knock-offs are all 50).
    merchant_cost_override: int | None = None

    @property
    def merchant_cost(self) -> int:
        """RelicModel.MerchantCost: base gold price before the shop's ±15%
        jitter. Ancient/Starter/Event relics are effectively unbuyable unless
        the relic overrides the price itself."""
        if self.merchant_cost_override is not None:
            return self.merchant_cost_override
        return _MERCHANT_COST_BY_RARITY[self.rarity]

    @property
    def is_used_up(self) -> bool:
        """RelicModel.IsUsedUp: a limited-use relic already spent (default
        False; relics with uses override — Winged Boots, Lizard Tail, …)."""
        return False

    @property
    def is_tradable(self) -> bool:
        """RelicModel.IsTradable — eligible for the trade events (Ranwid the
        Elder, Relic Trader): not used up, no upon-pickup effect, no pets,
        and not Starter/Event/Ancient rarity. The source also excludes
        melted wax copies; the sim removes melted relics from the run
        entirely, so (like the game) unmelted wax copies stay tradable."""
        if self.is_used_up or self.has_upon_pickup_effect or self.spawns_pets:
            return False
        return self.rarity not in (
            RelicRarity.STARTER, RelicRarity.EVENT, RelicRarity.ANCIENT,
        )

    def after_obtained(self, run) -> None:
        """RelicModel.AfterObtained: out-of-combat pickup effect (default
        no-op). RunState.add_relic invokes it. Golden Compass uses it to
        regenerate the current act's map as a golden path."""

    def undo_after_obtained(self, run) -> None:
        """Reverse `after_obtained` (default no-op). Has no counterpart in the
        game — nothing there ever un-picks a relic. It exists for the
        conformance runner, which lets the sim grant a node's relic and then
        swaps it for the one the save says was really picked: without an undo,
        a discarded max-HP relic (Mango, Pear, …) leaves its +MaxHp behind and
        the player-state parity check reads high for the rest of the run. Only
        relics whose pickup mutates run state outside `run.relics` need it."""

    def reset_for_combat(self) -> None:
        """Clear the relic's per-combat state (default no-op).

        C# resets it at the combat boundary and spells the boundary three
        different ways — `AfterCombatEnd` (Red Skull, Vambrace, Centennial
        Puzzle, Ruined Helmet, Pael's Tears, Pael's Eye, Pael's Legion,
        Diamond Diadem, Joss Paper), `BeforeCombatStart` (Belt Buckle) and
        `AfterRoomEntered(CombatRoom)` (Permafrost, Burning Sticks) — all of
        which bracket the same fight. The sim hangs one reset off `attach`,
        which is the only place a relic learns about a new CombatState, so it
        also covers the hole `AfterCombatEnd` alone leaves: a combat that ends
        inside `play_card` on the player's own turn never reaches
        `on_player_turn_end`, which is where Diamond Diadem's counter would
        otherwise have been cleared."""

    def attach(self, combat: CombatState) -> None:
        self.combat = combat
        self.reset_for_combat()
        combat.hooks.register(self)

    @classmethod
    def is_allowed(cls, run) -> bool:
        """RelicModel.IsAllowed(runState) (RelicModel.cs:434-437) — whether the
        relic may be in a pool at all. `RelicGrabBag.GetAvailableDeque` calls
        `RemoveDisallowedRelicsFromDeques` before every pull, permanently
        dropping the relics this rejects (RelicGrabBag.cs:218-270).

        A classmethod because the sim's pools hold ids and consult the class
        (`ALL_RELICS[relic_id]`), exactly as `is_allowed_in_shops` is consulted
        — the game asks the canonical model, which has no per-instance state
        either. Events use the same shape (`events.base.Event.is_allowed`)."""
        return True

    @classmethod
    def is_allowed_at_neow(cls, run) -> bool:
        """RelicModel.IsAllowedAtNeow — Neow's positive/curse pools filter on
        this.

        It DEFAULTS to `IsAllowed(player.RunState)` (RelicModel.cs:443-446).
        The sim modelled the two as independent members, which is the trap the
        gap entry names: a relic that opts out of pools via `is_allowed` would
        still be offerable at Neow. Kaleidoscope overrides it directly (it
        needs other characters' card pools); Massive Scroll needs no override
        because its `is_allowed` is already False (multiplayer-only).
        """
        return cls.is_allowed(run)

    # ── Run-level reward / room hooks (duck-typed over run.relics, like the
    #    map pipeline below; defaults mirror the AbstractModel no-ops) ──────

    def should_force_potion_reward(self, run, room_type) -> bool:
        """Hook.ShouldForcePotionReward — force a potion into combat rewards."""
        return False

    def modify_combat_rewards(self, run, rewards) -> None:
        """Hook.TryModifyRewards — mutate a just-generated CombatRewards
        (Lava Rock adds relics to the act-1 boss rewards). The FIRST of the
        two complete passes Hook.ModifyRewards makes (Hook.cs:1981-1999)."""

    def modify_combat_rewards_late(self, run, rewards) -> None:
        """Hook.TryModifyRewardsLate — the second complete pass, which sees
        everything the first one added (Driftwood flags the card reward
        rerollable)."""

    def modify_card_reward_options(self, run, cards) -> None:
        """Hook.TryModifyCardRewardOptions — mutate a card reward's options in
        place. The FIRST of the two complete passes
        Hook.TryModifyCardRewardOptions makes (Hook.cs:1444-1466); Lasting
        Candy adds an option here."""

    def modify_card_reward_options_late(self, run, cards) -> None:
        """Hook.TryModifyCardRewardOptionsLate — the second complete pass, so
        it sees the options the first one added (Silver Crucible upgrades
        them, Silken Tress enchants them, the egg relics upgrade their own
        card type)."""

    def modify_merchant_card_results(self, run, cards) -> None:
        """Hook.ModifyMerchantCardCreationResults (MerchantCardEntry.cs:92) —
        mutate the merchant's just-stocked card in place, before its price is
        calculated (the egg relics upgrade their card type on the shelf)."""

    def modify_card_being_added_to_deck(self, run, card):
        """Hook.ModifyCardBeingAddedToDeck (CardPileCmd.cs:501) — runs just
        before a card lands in the deck, whatever its source. Return a
        replacement card (the egg relics hand back an upgraded one) or None to
        leave it alone."""
        return None

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

    def modify_gold_gained(self, run, amount: float) -> float:
        """RelicModel.ModifyGoldGained — chain-modify a gold gain before it
        lands (Ectoplasm returns 0: you can never gain gold)."""
        return amount

    def should_procure_potion(self, run, potion) -> bool:
        """RelicModel.ShouldProcurePotion — False refuses the potion outright
        (Sozu)."""
        return True

    def modify_run_hp_loss(self, run, amount: int) -> int:
        """RelicModel.ModifyHpLostAfterOsty for out-of-combat HP loss: the
        game dispatches Hook.ModifyHpLost over the run state (CreatureCmd.cs),
        so event damage (RunState.lose_hp) goes through relics too (Tungsten
        Rod). Combat HP loss uses the combat-side modify_hp_lost hook.
        Chain hook — return the new amount."""
        return amount

    def modify_rest_site_heal_amount(self, run, amount: int) -> int:
        """RelicModel.ModifyRestSiteHealAmount — chain-modify the rest site's
        heal before it is applied (Regal Pillow's +15). C# dispatches it over
        the whole run's listeners from HealRestSiteOption.cs:60-63 and
        MendRestSiteOption.cs:58, both of which start from MaxHp * 0.3."""
        return amount

    def after_rest_site_heal(self, run) -> None:
        """RelicModel.AfterRestSiteHeal (Stone Humidifier's +5 max HP)."""

    def modify_rest_site_options(self, run, options: "list[RestSiteOption]") -> None:
        """RelicModel.TryModifyRestSiteOptions — append extra rest-site
        actions (Pael's Growth's Clone, Pumpkin Candle's Kindle, Meat
        Cleaver's Cook, Shovel's Dig, Girya's Lift). The driver surfaces
        them after Heal/Smith/Leave."""

    def should_disable_remaining_rest_site_options(self, run) -> bool:
        """RelicModel.ShouldDisableRemainingRestSiteOptions — default True
        (a rest-site visit ends after one action). Miniature Tent returns
        False so the visit continues until Leave or the options run out."""
        return True

    def modify_rest_site_heal_rewards(self, run, rewards) -> None:
        """RelicModel.TryModifyRestSiteHealRewards — mutate the reward
        screen offered after taking the rest site's heal option (Dream
        Catcher's 3-card choice). `rewards` is a rewards.CombatRewards, like
        modify_combat_rewards; RunState.rest_heal_rewards builds it."""

    def after_combat_end_early(self, run, room_type) -> None:
        """RelicModel.AfterCombatVictoryEarly at the run level — the FIRST of
        the two complete passes Hook.AfterCombatVictory makes (Hook.cs:340-352),
        so it sees the state the plain pass is about to change. MeatOnTheBone
        .cs:47 is the source's only implementer and rides the combat-level
        `on_combat_end_early`; nothing on the run-level walk needs it yet
        (SwordOfStone.cs:40 and WarHammer.cs:19 are both plain
        AfterCombatVictory)."""

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
