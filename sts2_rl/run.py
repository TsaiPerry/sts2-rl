"""RunState — the minimal out-of-combat run layer that events act on.

Mirrors the single-player slice of the game's Player/IRunState: current and
max HP, gold, the deck, relics, potions, and the relic grab bag. Events
(sts2_rl.events) mutate this state; combats are entered with
`create_combat(...)` and their outcome synced back with `finish_combat(...)`.

Faithful mechanics ported from the source:
  - starting stats: 80 HP, 99 gold, 5×Strike + 4×Defend + Bash
    (Ironclad.cs: StartingHp/StartingGold/StartingDeck)
  - rest-site heal: 30% of max HP, truncated (HealRestSiteOption.cs)
  - relic grab bag: rarity roll <0.5 Common, <0.83 Uncommon, else Rare, then
    the first bag relic of that rarity is pulled and removed for the rest of
    the run (RelicFactory.RollRarity / PullNextRelicFromFront)
  - card transformation: a random different card of Common/Uncommon/Rare
    rarity from the character pool replaces the original in place
    (CardFactory.GetDefaultTransformationOptions / GetFilteredTransformationOptions)
  - gold amounts truncate toward zero and gains require amount > 0
    (PlayerCmd.GainGold/LoseGold `(int)amount` casts)

Deliberate simplifications: run-level hook dispatch covers only the relic
hooks the ported pool needs (reward/room hooks, after_item_purchased,
after_card_added_to_deck, modify_run_hp_loss — Tungsten Rod does reduce
event HP loss), no unlock state (every implemented relic/potion/card is in
its pool), and the game's Colorless transform pool for Quest/Event-rarity
originals falls back to the character pool.
"""
from __future__ import annotations

import copy
import random
from typing import TYPE_CHECKING, Callable

from .cards import Card, CardRarity, make_card
from .cards.base import _CARD_CLASSES
from .characters import Character, DEFAULT_CHARACTER, get_character
from .combat import CombatState
from .potions import Potion, _POTION_CLASSES
from .relic_pools import populate_relic_grab_bags
from .relics import ALL_RELICS, Relic, RelicRarity, make_relic
from .rng import PlayerRngSet, RunRngSet
from .rewards import (
    TREASURE_GOLD,
    CardRarityOdds,
    CombatRewards,
    PotionRewardOdds,
    RewardExtra,
    apply_reward_modifiers,
    generate_combat_rewards,
)

if TYPE_CHECKING:
    from .actmap import ActMapConfig, MapPoint, StandardMap
    from .monsters import Encounter
    from .rooms import RoomResolution, RoomSet, RoomType, UnknownOdds


# Rarities eligible for the relic grab bag (starter/shop/event/ancient relics
# never come from the bag — they have dedicated sources).
_BAG_RARITIES = (RelicRarity.COMMON, RelicRarity.UNCOMMON, RelicRarity.RARE)

# Rarities a transform can produce (GetFilteredTransformationOptions keeps
# Common/Uncommon/Rare only).
_TRANSFORM_RARITIES = (CardRarity.COMMON, CardRarity.UNCOMMON, CardRarity.RARE)

# Default IRunState.CurrentActIndex per act, from each ActModel's Index:
# Overgrowth and Underdocks are BOTH act 1 (index 0 — Underdocks is the
# unlock-gated alternate Act 1, per Underdocks.cs Index=0/IsDefault=false),
# Hive is act 2, Glory act 3. Used to gate map modifiers like Spoils Map
# (SpoilsActIndex = 1) and the reward-card upgrade odds (act_index × 0.25).
_DEFAULT_ACT_INDEX = {
    "overgrowth": 0,
    "underdocks": 0,
    "hive": 1,
    "glory": 2,
}

# The act at each index of a run (ModelDb.ActsByIndex, everything unlocked):
# index 0 rolls uniformly between the default and alternate Act 1
# (ActModel.GetRandomList → rng.NextItem over the unlocked acts at index 0).
_ACTS_BY_INDEX: list[list[str]] = [
    ["overgrowth", "underdocks"],
    ["hive"],
    ["glory"],
]


def roll_relic_rarity(rng) -> RelicRarity:
    """RelicFactory.RollRarity: <0.5 Common, <0.83 Uncommon, else Rare. The SP2
    parity path passes a game ``Rng`` (``NextFloat``); the legacy RL path a
    ``random.Random`` (``random()``)."""
    from .rng import Rng

    roll = rng.next_float() if isinstance(rng, Rng) else rng.random()
    if roll < 0.5:
        return RelicRarity.COMMON
    if roll < 0.83:
        return RelicRarity.UNCOMMON
    return RelicRarity.RARE


def build_starting_deck(character: "str | Character" = DEFAULT_CHARACTER) -> list[Card]:
    """A character's ``CharacterModel.StartingDeck``, in the source's order.

    The order is not cosmetic: the deck is dealt in it and the combat-start
    ``UnstableShuffle`` is order-dependent."""
    return [make_card(cid) for cid in get_character(character).starting_deck]


def ironclad_starting_deck() -> list[Card]:
    """Ironclad.cs StartingDeck: 5 Strikes, 4 Defends, 1 Bash.

    Kept as a named helper (it is part of the package's public surface); the
    roster itself now lives in ``characters.CHARACTERS["ironclad"]``."""
    return build_starting_deck("ironclad")


class RunState:
    # Ironclad's numbers, kept as class constants for the callers that read
    # them. The live values come from `self.character` — see __init__.
    STARTING_HP = 80       # Ironclad.cs StartingHp
    STARTING_GOLD = 99     # Ironclad.cs StartingGold
    MAX_POTIONS = 3        # Player potionSlotCount

    def __init__(
        self,
        rng: random.Random | None = None,
        deck: list[Card] | None = None,
        max_hp: int | None = None,
        hp: int | None = None,
        gold: int | None = None,
        relics: list[Relic] | None = None,
        potions: list[Potion] | None = None,
        card_selector: Callable[[str, list[Card], int], list[Card]] | None = None,
        total_floor: int = 0,
        string_seed: str | None = None,
        character: "str | Character" = DEFAULT_CHARACTER,
    ) -> None:
        # The character being played (CharacterModel). Every character-dependent
        # value below — starting HP/gold/deck/relics, the card pool content
        # generation draws from, which relics and potions can appear — reads off
        # this row. Defaults to Ironclad, so every existing caller and every
        # recorded RNG draw is unchanged.
        self.character = get_character(character)
        self.rng = rng or random.Random()
        # ── Parity RNG (SP2) ─────────────────────────────────────────────
        # With a string seed, seat the game's separated streams: the 12
        # per-run streams (RunRngSet) and the 3 per-player streams
        # (PlayerRngSet). Single-player slot 0 => the player seed equals the
        # run seed (deterministic_hash_code(string_seed) & 0xFFFFFFFF). These
        # are seeded independently of `self.rng`, so seating them consumes
        # none of the legacy random.Random's draws — map/economy call sites
        # migrate onto them incrementally (Tasks 7-9) while combat stays on
        # `self.rng`. Absent (None) when no string seed is given, leaving the
        # pre-SP2 draw sequence untouched.
        self.string_seed = string_seed
        if string_seed is not None:
            self.rng_set = RunRngSet(string_seed)
            self.player_rng = PlayerRngSet(self.rng_set.seed)
        else:
            self.rng_set = None
            self.player_rng = None
        # Lazily seated by `crystal_sphere_rng` (see its docstring).
        self._crystal_sphere_rng = None
        # Optional (minigame) -> (x, y, tool) click policy for the Crystal
        # Sphere. The conformance runner installs one to replay a recording's
        # `CrystalSphereClick` commands; unset, the event falls back to the
        # source's own automated rule (CrystalSphereScreenHandler.cs:82-104).
        self.crystal_sphere_clicks = None
        # How many rooms have been entered this run (IRunState.TotalFloor).
        # Used by event gates like Punch-Off (>= 6); the sim has no map, so the
        # caller sets this when it matters.
        self.total_floor = total_floor
        self.deck: list[Card] = (
            deck if deck is not None else build_starting_deck(self.character)
        )
        self.max_hp = max_hp if max_hp is not None else self.character.starting_hp
        self.hp = hp if hp is not None else self.max_hp
        self.gold = gold if gold is not None else self.character.starting_gold
        self.relics: list[Relic] = list(relics or [])
        # Potion belt: Player.cs's `_potionSlots` is a FIXED-LENGTH
        # List<PotionModel?> sized to MaxPotionCount, empty slots holding null
        # (Player.cs:~20, MaxPotionCount => _potionSlots.Count). It is never
        # compacted — using/discarding a potion nulls its slot in place
        # (DiscardPotionInternal) and a new one fills the first null slot
        # (AddPotionInternal: `slotIndex = _potionSlots.IndexOf(null)`).
        # `potions` here mirrors PotionSlots (nulls preserved); `held_potions`
        # below mirrors the null-filtered `Potions` property. A plain
        # (gap-free) caller list is placed left-to-right starting at slot 0;
        # a list that already carries `None` gaps (e.g. RunState.potions
        # handed to create_combat, or a conformance resync) keeps those gaps
        # at the same indices. Phial Holster / Alchemical Coffer grow the
        # belt via add_potion_slots (SetMaxPotionCountInternal's grow path;
        # its shrink path is unported — nothing in ported content shrinks the
        # belt).
        self.max_potions = self.MAX_POTIONS
        self.potions: list[Potion | None] = [None] * self.max_potions
        for i, p in enumerate(list(potions or [])[: self.max_potions]):
            self.potions[i] = p
        # NMerchantRoom.FoulPotionThrown: a Foul Potion thrown at the merchant
        # drives him off (FoulPotion.cs:79-88), closing his stall for good.
        self.merchant_driven_off = False
        # Out-of-combat card chooser with the same signature as
        # CombatState.card_selector: (purpose, candidates, count) -> cards.
        # None = uniform random with the run RNG.
        self.card_selector = card_selector
        # Relic grab bag (RelicGrabBag): every bag-eligible relic in a random
        # order; pulled relics never reappear this run.
        # `owns_relic` keeps another character's relics out: `relics/`
        # auto-imports every module into ALL_RELICS, so without it a ported
        # Defect relic would be rollable in an Ironclad run. The scan ORDER is
        # deliberately still ALL_RELICS' — the shuffle below consumes it, so
        # rebuilding the list from a pool roster would change every Ironclad
        # relic pull even though the membership is identical.
        self.relic_grab_bag: list[str] = [
            relic_id for relic_id, cls in ALL_RELICS.items()
            if cls.rarity in _BAG_RARITIES and self.owns_relic(cls)
        ]
        self.rng.shuffle(self.relic_grab_bag)
        # ── SP2 parity relic grab bags (Task 8d) ─────────────────────────
        # RunManager.InitializeNewRun shuffles the shared + player relic grab
        # bags on the UpFront stream at run start — UpFront's very first
        # consumer, landing its counter at 230 for a fully-unlocked Ironclad
        # run (before the shared-ancient subset rolls, Task 8f). These
        # game-complete per-rarity deques (relic_pools.py) supersede the legacy
        # merged bag above for reward pulls once Task 9 rewires them; for now
        # they exist so the UpFront draw count is game-exact. Gated on rng_set
        # so the legacy (non-parity) path keeps its exact random.Random draws.
        self.shared_relic_bag: dict[str, list[str]] | None = None
        self.player_relic_bag: dict[str, list[str]] | None = None
        if self.rng_set is not None:
            self.shared_relic_bag, self.player_relic_bag = populate_relic_grab_bags(
                self.rng_set.up_front, self.character.relic_pool)
            # Re-seat the merged pull bag from those deques, in bucket-insertion
            # order. `pull_relic_from_front` scans it for the first relic of the
            # rolled rarity, which over a rarity-grouped list IS
            # RelicGrabBag.PullFromFront (the front of that rarity's deque). It
            # also replaces a `random.Random()` shuffle that, with no seed, made
            # every parity replay hand out different chest/elite relics — a
            # max-HP one (Mango, Pear, …) then moved the player's max HP even
            # after the conformance runner reconciled the relic list.
            # NOTE: only the ORDER source changes here. Reproducing the game's
            # exact bucket order/identities is still open (relic_pools.py:
            # "identities become a reward-pull oracle in Task 9"), so the relic
            # a parity run pulls is deterministic but not yet game-exact.
            self.relic_grab_bag = [
                rid.split(".", 1)[-1].lower()
                for deque in self.player_relic_bag.values()
                for rid in deque
                if rid.split(".", 1)[-1].lower() in ALL_RELICS
            ]
        # A separate bag of Shop-rarity relics (never in the normal grab bag)
        # for the merchant's Shop-rarity slot (RelicFactory.PullNextRelicFromBack
        # with RelicRarity.Shop). Built + shuffled lazily on first shop access
        # so constructing a run consumes no extra RNG (seed parity with the
        # existing tests, which never open a shop).
        self._shop_relic_bag: list[str] | None = None
        # Player.ExtraFields.CardShopRemovalsUsed — raises the removal price.
        self.card_shop_removals_used = 0
        # Per-run reward pity state (PlayerOdds in the source): the drifting
        # card-rarity offset and the potion-drop threshold. Both roll on the
        # per-player Rewards stream in the SP2 parity path (PlayerOddsSet seeds
        # CardRarityOdds/PotionRewardOdds with PlayerRng.Rewards); the legacy RL
        # path keeps them on the shared run.rng. Constructing them draws no RNG,
        # so run-construction seed parity is preserved.
        odds_rng = self.player_rng.rewards if self.player_rng is not None else self.rng
        self.card_rarity_odds = CardRarityOdds(odds_rng)
        self.potion_reward_odds = PotionRewardOdds(odds_rng)
        # Post-combat "extras" carried out of the last finished combat, awaiting
        # the reward screen (mirrors a CombatRoom's ExtraRewards being folded in
        # by RewardsSet.WithRewardsFromRoom). finish_combat fills it;
        # generate_combat_rewards drains it. First entry type: Thieving Hopper's
        # returned card.
        self.pending_reward_extras: list["RewardExtra"] = []
        # R10: `TreasureRoom.DoExtraRewardsIfNeeded`'s otherwise-empty,
        # Room=Treasure reward set (TreasureRoom.cs:75-97) — stashed by
        # enter_point's TREASURE branch only when a hook actually added
        # something to it, and drained by the driver's TREASURE room
        # resolution. None the rest of the time (the common case today).
        self.pending_treasure_extra_rewards: "CombatRewards | None" = None
        # ── Run / act sequencing (populated by start_run) ────────────────
        # The full act list, rolled once at run start (ActModel.GetRandomList);
        # empty until start_run is called (single-act tests use start_act).
        self.act_list: list[str] = []
        # Parity (SP2): every act's rooms pre-rolled on the UpFront stream at
        # run start (RunManager.GenerateRooms), indexed by act — start_act just
        # retrieves this act's set. None on the legacy path, where start_act
        # rolls each act's rooms lazily on self.rng. Filled by
        # _generate_all_act_rooms, alongside the shared-ancient subsets it deals.
        self._act_room_sets: "list[RoomSet] | None" = None
        self._shared_ancient_subsets: dict[str, tuple[str, ...]] = {}
        # True once the final act's boss is beaten (RunManager's victory).
        self.victory = False
        # ── Map / act state (populated by start_act) ─────────────────────
        self.act_config: "ActMapConfig | None" = None
        self.act_index = 0            # IRunState.CurrentActIndex
        self.ascension = 0
        self._is_final_act = False
        self._has_second_boss = False
        self.map: StandardMap | None = None
        self.room_set: RoomSet | None = None
        self.unknown_odds: UnknownOdds | None = None
        self.current_point: MapPoint | None = None
        # (point, room_type) for every point entered this act, in order.
        self.map_history: list[tuple[MapPoint, RoomType]] = []
        # Event ids seen this run (RunState.VisitedEventIds) — feeds
        # RoomSet.EnsureNextEventIsValid.
        self.visited_event_ids: set[str] = set()

    # ── Economy RNG streams (SP2 parity) ─────────────────────────────────

    @property
    def rewards_rng(self):
        """The per-player Rewards stream (reward gold/cards/potions/relic-rarity
        rolls) in the SP2 parity path, else the shared legacy run.rng."""
        return self.player_rng.rewards if self.player_rng is not None else self.rng

    @property
    def crystal_sphere_rng(self):
        """SIM-ONLY stream for the Crystal Sphere click policy.

        The game has no such stream: a cell click is human input, so
        `CrystalSphereMinigame.CellClicked` consumes no run RNG whatsoever.
        The sim still has to invent a click, and drawing it from any parity
        stream would shift every placement and reward draw after it. So it
        draws here — off a name the game never uses, seeded from the run seed
        — which keeps a seeded run reproducible while making a collision with
        a parity counter impossible by construction. Legacy (no rng_set) runs
        have no parity contract and stay on the shared `run.rng`. A
        conformance replay overrides the policy outright
        (`run.crystal_sphere_clicks`) and never reaches this."""
        if self.rng_set is None:
            return self.rng
        if self._crystal_sphere_rng is None:
            from .rng import Rng
            self._crystal_sphere_rng = Rng(
                self.rng_set.seed, name="crystal_sphere_clicks")
        return self._crystal_sphere_rng

    @property
    def shops_rng(self):
        """The per-player Shops stream (merchant on-sale/card-pick/cost-jitter/
        potion rolls) in the SP2 parity path, else the shared legacy run.rng."""
        return self.player_rng.shops if self.player_rng is not None else self.rng

    # ── HP ───────────────────────────────────────────────────────────────

    @property
    def is_dead(self) -> bool:
        return self.hp <= 0

    @property
    def side(self) -> str:
        """Creature.Side for the out-of-combat player. The run state stands in
        for the player's Creature in the run-level hook pass below (the belt's
        `should_die` is written against a Creature and asks for its side)."""
        return "player"

    def heal(self, amount: int) -> int:
        """Heal up to amount, capped at max HP. Returns HP restored."""
        healed = max(0, min(int(amount), self.max_hp - self.hp))
        self.hp += healed
        return healed

    def lose_hp(self, amount: int) -> None:
        """Unblockable, unpowered event damage (CreatureCmd.Damage with
        ValueProp.Unblockable | Unpowered). Can kill. Relic HP-loss
        modifiers (Tungsten Rod's ModifyHpLostAfterOsty) apply — the game's
        Hook.ModifyHpLost dispatches over the run state."""
        loss = int(amount)
        for relic in list(self.relics):
            loss = relic.modify_run_hp_loss(self, loss)
        # Creature.LoseHpInternal (Creature.cs:450): `CurrentHp =
        # Max(CurrentHp - n, 0)` — HP never goes negative.
        self.hp = max(0, self.hp - max(0, int(loss)))
        if self.is_dead:
            self._resolve_death()

    def _resolve_death(self, recursion: int = 0) -> None:
        """CreatureCmd.Damage's `Kill(killedCreatures)` tail
        (CreatureCmd.cs:409) for an out-of-combat HP loss, i.e.
        KillWithoutCheckingWinCondition's death-prevention arms
        (CreatureCmd.cs:504-570): `Hook.ShouldDie` runs over
        `RunState.IterateHookListeners(null)`, and a listener that answers
        False becomes the `preventer` handed to `Hook.AfterPreventingDeath`.

        The game's run-level listener walk (RunState.cs:545-596) yields the
        deck, the relics, the modifiers/badges AND the **potion belt**; the
        belt is the only one of them with a ported death listener (Fairy in a
        Bottle), so the pass iterates the belt alone.
        """
        preventer = None
        for listener in self.held_potions:
            should_die = getattr(listener, "should_die", None)
            if should_die is not None and not should_die(self):
                preventer = listener
                break
        if preventer is None:
            return
        after = getattr(preventer, "after_preventing_death", None)
        if after is not None:
            after(self)
        # CreatureCmd.cs:568-571 — a preventer that did not actually heal the
        # creature gets re-killed (the game throws at 10 recursions).
        if self.is_dead and recursion < 10:
            self._resolve_death(recursion + 1)

    def kill(self) -> None:
        self.hp = 0

    def rest_site_heal_amount(self) -> int:
        """HealRestSiteOption.GetHealAmount (HealRestSiteOption.cs:60-63):
        GetBaseHealAmount (30% of max HP, truncated) run through
        Hook.ModifyRestSiteHealAmount over the run's listeners — Regal
        Pillow's +15. MendRestSiteOption.cs:58 chains the same hook over the
        same base."""
        amount = self.max_hp * 3 // 10
        for relic in list(self.relics):
            amount = relic.modify_rest_site_heal_amount(self, amount)
        return amount

    def gain_max_hp(self, amount: int) -> None:
        """CreatureCmd.GainMaxHp: raise max HP, then heal the same amount."""
        self.max_hp += int(amount)
        self.heal(int(amount))

    def lose_max_hp(self, amount: int) -> None:
        """CreatureCmd.LoseMaxHp (CreatureCmd.cs:811-826).

        The new max is computed UNFLOORED, the overflow above it is dealt as
        real (Unblockable | Unpowered) damage — so the HP-loss hooks run and a
        max-HP loss bigger than the player's HP genuinely kills — and only then
        is max HP set to `Max(1, newMaxHp)`. `SetMaxHp` ends in
        Creature.SetMaxHpInternal (Creature.cs:493-501), whose
        `CurrentHp = Min(CurrentHp, MaxHp)` is what actually clamps.
        """
        new_max = self.max_hp - int(amount)
        if new_max < self.hp:
            self.lose_hp(self.hp - new_max)
        self.max_hp = max(1, new_max)
        self.hp = min(self.hp, self.max_hp)

    # ── Gold ─────────────────────────────────────────────────────────────

    def gain_gold(self, amount: float) -> None:
        """PlayerCmd.GainGold (PlayerCmd.cs:140-170): truncate toward zero;
        no-op unless positive.

        Hook.ModifyGoldGained runs first (Ectoplasm zeroes it), and the
        `if (!(amount > 0m)) return;` bail at :146-149 tests the MODIFIED
        amount — so a zeroed gain skips the whole tail, `AfterGoldGained`
        included. The hook then fires AFTER the balance moves (:168-169), so
        Dragon Fruit reads the new total.
        """
        for relic in list(self.relics):
            amount = relic.modify_gold_gained(self, amount)
        gained = int(amount)
        if amount > 0:
            self.gold += gained
            for relic in list(self.relics):
                relic.after_gold_gained(self, gained)

    def lose_gold(self, amount: float) -> None:
        """PlayerCmd.LoseGold: truncate; gold never goes below 0."""
        self.gold = max(0, self.gold - int(amount))

    # ── Deck ─────────────────────────────────────────────────────────────

    def add_card(self, card: Card) -> Card:
        # Hook.ModifyCardBeingAddedToDeck (CardPileCmd.cs:501) runs BEFORE the
        # card joins the deck and may swap in a replacement — the egg relics
        # substitute an upgraded clone for their card type.
        for relic in list(self.relics):
            replacement = relic.modify_card_being_added_to_deck(self, card)
            if replacement is not None:
                card = replacement
        self.deck.append(card)
        # RelicModel.AfterCardChangedPiles for the deck pile (Darkstone
        # Periapt's Max HP on a gained Curse).
        for relic in list(self.relics):
            relic.after_card_added_to_deck(self, card)
        return card

    def remove_cards(self, cards: list[Card]) -> None:
        """CardPileCmd.RemoveFromDeck (CardPileCmd.cs:52-70) — one card at a
        time, each firing `Hook.BeforeCardRemoved` BEFORE it is unlinked."""
        for card in cards:
            self.before_card_removed(card)
            # CardPileCmd.cs:79 — the third C# site that sets
            # CardModel.HasBeenRemovedFromState (CardModel.cs:948), completing
            # the flag the Card arm of CombatState.Contains reads
            # (CombatState.cs:593). Dormant: a card removed from the deck is
            # never registered as a listener in a later combat.
            card.has_been_removed_from_state = True
            self.deck.remove(card)

    def before_card_removed(self, card: Card) -> None:
        """Hook.BeforeCardRemoved (Hook.cs:299-305) over
        RunState.IterateHookListeners — which yields the DECK as well as the
        relics, because the hook's only implementer in the whole decompiled
        game is a card: SpoilsMap.cs:100-116 unpins its treasure-node quest
        when the card leaves the deck. Called by every deck removal, so a
        removal path that bypasses it silently strands the quest marker."""
        for listener in list(self.deck) + list(self.relics):
            fn = getattr(listener, "before_card_removed", None)
            if fn is not None:
                fn(self, card)

    def removable_cards(self) -> list[Card]:
        """CardModel.IsRemovable: everything except Eternal cards."""
        return [c for c in self.deck if not c.eternal]

    def transformable_cards(self) -> list[Card]:
        """The transform SCREEN's pool. CardSelectCmd.FromDeckForTransformation
        (CardSelectCmd.cs:487) filters `c.Type != CardType.Quest &&
        c.IsTransformable`, and for a card sitting in the Deck pile
        `IsTransformable` is just `IsRemovable` (`!Eternal`,
        CardModel.cs:739-750) — so the screen is the removal pool MINUS the
        Quest cards.

        A gate that counts `IsTransformable` directly (MorphicGrove.cs:26) has
        no Quest clause and must use `removable_cards` instead."""
        from .cards import CardType
        return [c for c in self.deck
                if c.card_type != CardType.QUEST and not c.eternal]

    def upgradable_cards(self) -> list[Card]:
        return [c for c in self.deck if c.is_upgradable]

    def select_cards(
        self,
        purpose: str,
        candidates: list[Card],
        count: int = 1,
        min_select: int | None = None,
    ) -> list[Card]:
        """Out-of-combat card selection (mirrors CardSelectCmd.FromDeck*).

        purpose is a short label ("transform", "upgrade", "remove",
        "enchant") so a selector policy can distinguish contexts. Delegates to
        self.card_selector when installed; otherwise picks uniformly at
        random with the run RNG.

        `min_select` is CardSelectorPrefs.MinSelect (CardSelectorPrefs.cs:25),
        ported up from the in-combat twin (CombatState.select_cards,
        combat.py) which already models it. Defaults to `None`, preserving
        today's behaviour for every existing caller: `count` is both the
        maximum AND (via the fallback below) the exact number returned.

        Deliberately NOT threaded into the `self.card_selector(purpose,
        candidates, count)` call: that 3-argument shape is a public contract
        dozens of hand-rolled test callables and `RunDriver._card_selector`
        already implement, and changing its arity would break every one of
        them. Whether an installed selector may decline (return fewer than
        `count`) is expressed the same way the in-combat side and the sim's
        two prior instances of this exact mechanism (relic/gambling_chip G3,
        relics/claws.py's "transform_optional") already express it: a
        purpose string registered in `driver.SKIPPABLE_PURPOSES`, not a
        value threaded through the call. Kifuda uses "enchant_optional" for
        this reason (relics/kifuda.py) — see that file and
        driver.SKIPPABLE_PURPOSES for the citation.

        `min_select` DOES change the SELECTORLESS fallback below (no
        `card_selector` installed at all — a bare RunState, e.g. a unit test
        or a headless smoke run): C# has no such path (CardSelectCmd always
        shows a UI screen, consults an installed `Selector`, or waits on the
        network — never silently completes on its own), so like combat.py's
        equivalent fallback this is a sim-only headless completion, not a
        game behaviour to match byte-for-byte. It mirrors combat.py's shape:
        a uniform random count in [min_select, count] rather than always
        `count`, so "confirm fewer" stays possible even with no policy
        attached (derived from `CardSelectCmd.cs:576`'s shortcut and the
        `Selector.GetSelectedCards(list, MinSelect, MaxSelect)` call at
        `:582` — the closest C# analogue to "let something else decide how
        many, within the range").
        """
        if count <= 0 or not candidates:
            return []
        count = min(count, len(candidates))
        if self.card_selector is not None:
            chosen = list(self.card_selector(purpose, list(candidates), count))[:count]
            return [c for c in chosen if c in candidates]
        floor = count if min_select is None else min(min_select, len(candidates))
        if floor < count:
            count = self.rng.randint(floor, count)
        if count <= 0:
            return []
        return self.rng.sample(candidates, count)

    def select_option(self, purpose: str, count: int) -> int:
        """A generic pick-one-of-N choice that is not a card selection
        (Scroll Boxes' choose-a-bundle screen). Delegates to
        self.option_selector — a callable (purpose, count) -> index — when
        installed; otherwise uniform random with the run RNG."""
        if count <= 0:
            raise ValueError("select_option needs at least one option")
        selector = getattr(self, "option_selector", None)
        if selector is not None:
            idx = int(selector(purpose, count))
            if 0 <= idx < count:
                return idx
        return self.rng.randrange(count)

    def offer_rewards(self, rewards) -> None:
        """`RewardsSet.Offer` for a whole reward set built outside a room —
        `RewardsCmd.OfferCustom` (RewardsCmd.cs:47-50).

        Each `CardReward` on the set is its own pick-one-of-N screen taken
        separately, so a set with five of them (Glass Eye) is five decisions.
        Delegates to `self.rewards_offerer` — the callable the driver installs,
        which surfaces every screen through the REWARD_CARD decision and knows
        about Driftwood's reroll and Pael's Wing's sacrifice. With no offerer
        attached (bare RunState, unit tests) it falls back to the same
        pick-one-per-group loop through `select_cards`.

        Offer-time backstop (R10): dispatches `apply_reward_modifiers` before
        doing anything else, mirroring `Offer()`'s own repeat call to
        `GenerateWithoutOffering` (RewardsSet.cs:159). Every real caller
        already dispatched at its construction site, so this is normally a
        harmless repeat (`CombatRewards.generated` guards it) — but it is what
        makes the selectorless fallback loop below safe for a set nobody
        generated yet, and it covers `self.rewards_offerer` being unset
        (bare RunState) the same way `driver._offer_rewards` covers the
        installed-driver case.
        """
        apply_reward_modifiers(self, rewards)
        offerer = getattr(self, "rewards_offerer", None)
        if offerer is not None:
            offerer(rewards)
            return
        for group in list(rewards.card_rewards):
            if not group.cards:
                continue
            for card in self.select_cards("card_reward", list(group.cards), 1):
                self.add_card(card)

    def offer_relic(self, relic: Relic | str) -> Relic | None:
        """RewardsCmd.OfferCustom with a RelicReward — a take-or-SKIP screen.

        `WithSkippingDisallowed` (RewardsSet.cs:115) has exactly one caller in
        the whole source, NeowsBones.cs:43, so every other relic offer is
        declinable. RelicReward.Populate has already run by then — a declined
        relic still LEAVES the grab bag — and only RelicReward.OnSelect
        (RelicReward.cs:109-115) reaches RelicCmd.Obtain, so a declined relic
        never joins the list and never runs its AfterObtained; OnSkipped
        (RelicReward.cs:117-123) records `wasPicked: false` instead.

        Delegates to self.reward_selector — a callable (kind, item) -> bool —
        when installed (the driver surfaces it as a REWARD_RELIC decision).
        With no selector attached there is nobody to decline, so the offer
        resolves as a take. Returns the obtained relic, or None if declined.
        """
        if isinstance(relic, str):
            relic = make_relic(relic)
        selector = getattr(self, "reward_selector", None)
        if selector is not None and not selector("relic", relic):
            return None
        return self.add_relic(relic)

    def offer_potion(self, potion: Potion) -> bool:
        """RewardsCmd.OfferCustom with a PotionReward — the same take-or-skip
        screen for a potion (PotionReward.OnSelect / OnSkipped). Returns
        whether it was kept; add_potion can still refuse it (Sozu, full
        belt)."""
        selector = getattr(self, "reward_selector", None)
        if selector is not None and not selector("potion", potion):
            return False
        return self.add_potion(potion)

    def transform_card(
        self, card: Card, into: Card | None = None, *, pick_rng=None
    ) -> Card:
        """Transform a deck card (CardCmd.TransformToRandom / TransformTo).

        With `into` set, the replacement is exact (Wood Carvings' Peck /
        Toric Toughness). Otherwise a random different Common/Uncommon/Rare
        card from the original's pool is rolled (GetDefaultTransformationOptions:
        Colorless cards and Quest/Event/Ancient/Token cards roll from the
        Colorless pool, Curses from the curse pool without the rarity filter,
        everything else from the character pool).

        Deck placement: the game's `CardCmd.Transform` on a **Deck** pile REMOVES
        the original and **appends** the replacement at the END of the deck
        (`AddInternal(replacement)` with no index; `FloorAddedToDeck =
        TotalFloor` — CardCmd.cs:437); only combat-pile transforms re-insert at
        the original index, and every `transform_card` caller here is a
        deck-level (out-of-combat) transform. Because the combat-start
        `UnstableShuffle` is order-dependent, this end-placement is what keeps
        the post-transform draw order in parity (Pandora's Box appends its 8
        rolls after the deck's existing cards). The legacy RL path keeps the
        in-place replace byte-for-byte (its shuffle order-depends on the deck
        too, and its reward/transform sequence is the unchecked legacy stream).

        `pick_rng` is the game stream the replacement is rolled on
        (`CreateRandomCardForTransform`'s Rng arg): the game routes different
        transformers through different streams (Pandora's Box => Niche), so the
        caller passes it and the roll is a game-faithful `NextItem` over the
        pool-order options. None (legacy runs, or callers not yet parity-wired)
        keeps the shared-rng `choice`.
        """
        if into is None:
            from .cards import COLORLESS_POOL, CURSE_POOL, CardType
            pool, rarity_filter = self.card_pool, True
            if card.card_type == CardType.CURSE:
                pool, rarity_filter = CURSE_POOL, False
            elif (
                card.id in COLORLESS_POOL
                or card.card_type == CardType.QUEST
                or card.rarity in
                (CardRarity.EVENT, CardRarity.ANCIENT, CardRarity.TOKEN)
            ):
                pool = COLORLESS_POOL
            options = [
                card_id for card_id in pool
                if (not rarity_filter
                    or _CARD_CLASSES[card_id].rarity in _TRANSFORM_RARITIES)
                and card_id != card.id
            ]
            if pick_rng is not None:
                into = make_card(pick_rng.next_item(options))
            else:
                into = make_card(self.rng.choice(options))
        # A Deck-pile transform IS a deck entry: CardCmd.Transform runs the same
        # two hooks CardPileCmd.Add does — Hook.ModifyCardBeingAddedToDeck
        # before the insert (CardCmd.cs:430; the egg relics hand back an
        # upgraded replacement) and Hook.AfterCardChangedPiles after it
        # (CardCmd.cs:447; Bing Bong, Book of Five Rings, Darkstone Periapt,
        # Lucky Fysh).
        for relic in list(self.relics):
            replacement = relic.modify_card_being_added_to_deck(self, into)
            if replacement is not None:
                into = replacement
        if self.rng_set is not None:
            # Parity: remove the original (by identity — duplicate basics compare
            # equal) and append the replacement at the deck's end.
            for i, c in enumerate(self.deck):
                if c is card:
                    del self.deck[i]
                    break
            self.deck.append(into)
        else:
            idx = self.deck.index(card)
            self.deck[idx] = into
        for relic in list(self.relics):
            relic.after_card_added_to_deck(self, into)
        return into

    # ── Potions ──────────────────────────────────────────────────────────

    def add_potion(self, potion: Potion, slot: int | None = None) -> bool:
        """Fill the first open belt slot. Returns whether it was kept.

        Hook.ShouldProcurePotion gates it first (Sozu refuses every potion).
        Mirrors Player.cs AddPotionInternal: `slotIndex =
        _potionSlots.IndexOf(null)` — fails if no slot is null (belt full).

        `slot` names an EXPLICIT belt index, which is the other form
        `PotionCmd.TryToProcure` takes: Alchemical Coffer snapshots the belt size
        before growing it and procures into `originalSlotCount + i`
        (AlchemicalCoffer.cs:22-27), so its four potions land in the NEW slots and
        leave the old ones empty. Slot identity is observable — a UsePotion replay
        command names a slot and the conformance runner diffs `floor_potions` slot
        by slot.
        """
        if not all(r.should_procure_potion(self, potion) for r in self.relics):
            return False
        if slot is not None:
            if not (0 <= slot < len(self.potions)) or self.potions[slot] is not None:
                return False
            self.potions[slot] = potion
            return True
        if not self.has_open_potion_slot:
            return False
        self.potions[self.potions.index(None)] = potion
        return True

    def discard_potion(self, potion: Potion) -> None:
        """Null the potion's belt slot (Player.cs DiscardPotionInternal) — the
        other slots keep their positions; the belt is never compacted."""
        self.potions[self.potions.index(potion)] = None

    def use_potion(self, slot: int) -> bool:
        """Drink the belt potion in `slot` OUTSIDE combat. Returns whether it
        was used.

        `PotionUsage.AnyTime` (Blood Potion, Entropic Brew, Foul Potion, Fruit
        Juice) leaves the Use button live on the map, and `OnUseWrapper` is
        written for it — `PotionModel.cs:294,298,334,336` all null-check the
        combat state. So the wrapper reduces out of combat to :293
        `RemoveBeforeUse` and :327 `OnUse`: the History entry (:336) is
        combat-scoped, and both `AfterPotionUsed` implementers open with
        `CombatManager.Instance.IsInProgress` (BeltBuckle.cs:79-85,
        ReptileTrinket.cs:22-30), so the dispatch has no ported listener here.
        The in-combat path is CombatState.use_potion.
        """
        if slot < 0 or slot >= len(self.potions):
            return False
        potion = self.potions[slot]
        if potion is None:
            return False
        from .potions import USAGE_ANY_TIME
        if potion.usage != USAGE_ANY_TIME:
            return False
        self.potions[slot] = None               # RemoveBeforeUse
        potion.use_out_of_combat(self)
        return True

    def add_potion_slots(self, count: int) -> None:
        """Grow the belt by `count` null slots (Player.cs
        SetMaxPotionCountInternal's grow path — Phial Holster / Alchemical
        Coffer). The shrink path is unported: nothing in ported content
        shrinks the belt."""
        self.max_potions += count
        self.potions.extend([None] * count)

    @property
    def held_potions(self) -> list[Potion]:
        """The potions actually held, in slot order, with empty slots
        filtered out (Player.cs `Potions => _potionSlots.Where(p => p !=
        null)`)."""
        return [p for p in self.potions if p is not None]

    @property
    def has_open_potion_slot(self) -> bool:
        """Mirrors Player.cs `HasOpenPotionSlots => _potionSlots.Any(p => p
        == null)`."""
        return None in self.potions

    # ── Character scoping ────────────────────────────────────────────────
    #
    # The game reaches content through `SharedXPool ∪ Player.Character.XPool`,
    # so one character's relics and potions are simply unreachable in another's
    # run. The sim's registries are global (`relics/` auto-imports every module
    # into ALL_RELICS; @register_potion fills _POTION_CLASSES), so these two
    # predicates are what re-impose the game's scoping on every registry scan.
    # A class with `character = None` is shared and always owned.

    def owns_relic(self, relic_cls) -> bool:
        """Whether this run's character can be offered `relic_cls`."""
        return relic_cls.character in (None, self.character.id)

    def owns_potion(self, potion_cls) -> bool:
        """Whether this run's character can be offered `potion_cls`."""
        return potion_cls.character in (None, self.character.id)

    @property
    def card_pool(self) -> tuple[str, ...]:
        """The character's CardPool — what card generation draws from."""
        return self.character.card_pool

    @property
    def potion_pool(self) -> tuple[tuple[str, str], ...]:
        """GetPotionOptions: the character's potion pool, then the shared one."""
        from .potion_pools import character_potion_pool

        return character_potion_pool(self.character)

    def _reward_potion_classes(self) -> list:
        """The reward-pool potion classes this character can be offered, in the
        id order the legacy RL path has always used."""
        return sorted(
            (
                c for c in _POTION_CLASSES.values()
                if c.in_reward_pool and self.owns_potion(c)
            ),
            key=lambda c: c.id,
        )

    def random_potion(self) -> Potion:
        """A uniformly random potion from the implemented pool (approximates
        the character + shared potion pools of PotionReward)."""
        return self.rng.choice(self._reward_potion_classes())()

    def random_potions(self, count: int, distinct: bool = False) -> list[Potion]:
        """Several random potions from the reward pool (shop stock). With
        `distinct`, avoid repeating a potion id while the pool allows it
        (PotionFactory.CreateRandomPotionsOutOfCombat blacklists picks)."""
        pool = self._reward_potion_classes()
        if not pool:
            return []
        if not distinct:
            return [self.rng.choice(pool)() for _ in range(count)]
        chosen: list[Potion] = []
        available = list(pool)
        for _ in range(count):
            if not available:
                available = list(pool)
            cls = self.rng.choice(available)
            available.remove(cls)
            chosen.append(cls())
        return chosen

    # ── Relics ───────────────────────────────────────────────────────────

    def add_relic(self, relic: Relic | str) -> Relic:
        if isinstance(relic, str):
            relic = make_relic(relic)
        self.relics.append(relic)
        # RelicCmd.Obtain → RelicModel.AfterObtained (out-of-combat pickup
        # effect, e.g. Golden Compass regenerating the map).
        relic.after_obtained(self)
        return relic

    def has_available_relics(self) -> bool:
        """RelicGrabBag.HasAvailableRelics for this run."""
        return bool(self.relic_grab_bag)

    def pull_relic_from_front(
        self,
        rarity: RelicRarity | None = None,
        shop_legal: bool = False,
        rarity_rng=None,
    ) -> Relic | None:
        """RelicFactory.PullNextRelicFromFront: roll rarity (<0.5 Common,
        <0.83 Uncommon, else Rare), pull the first bag relic of that rarity.
        Falls back to the front of the bag when no relic matches the rolled
        rarity (the game substitutes a fallback relic); None if the bag is
        empty.

        `rarity` pins the rarity instead of rolling it, and `shop_legal`
        applies an IsAllowedInShops filter — together they are the source's
        PullNextRelicFromFront(player, rarity, filter) overload, which
        Welcome to Wongo's uses for its bargain-bin and featured relics.

        `rarity_rng` is the stream the rarity NextFloat comes off — the game
        picks it per caller, and the default overload is
        `PullNextRelicFromFront(player)` -> `RollRarity(player)` ->
        `player.PlayerRng.Rewards` (RelicFactory.cs:28/82), so an unspecified
        stream means the Rewards one. Callers on another stream pass it (the
        treasure chest's synchronizer is built with
        `State.Rng.TreasureRoomRelics`). `rewards_rng` is itself the legacy
        shared run RNG when there is no parity rng_set, so the RL path is
        unchanged."""
        # RelicGrabBag.GetAvailableDeque calls RemoveDisallowedRelicsFromDeques
        # before every pull (RelicGrabBag.cs:218-270), which drops the relics
        # RelicModel.IsAllowed rejects PERMANENTLY from the deques. Without it
        # every floor-gated relic stayed offerable at every floor — at
        # total_floor 60 the bag still yielded toxic_egg, which the game stops
        # offering after floor 40.
        self._drop_disallowed_from_grab_bag()
        if not self.relic_grab_bag:
            return None
        if rarity is None:
            rarity = roll_relic_rarity(
                rarity_rng if rarity_rng is not None else self.rewards_rng)
        for relic_id in self.relic_grab_bag:
            cls = ALL_RELICS[relic_id]
            if cls.rarity == rarity and (not shop_legal or cls.is_allowed_in_shops):
                self.relic_grab_bag.remove(relic_id)
                return make_relic(relic_id)
        return make_relic(self.relic_grab_bag.pop(0))

    def pull_relic_from_back(
        self, rarity: RelicRarity, blacklist: set[str] | None = None
    ) -> Relic | None:
        """RelicFactory.PullNextRelicFromBack: pull the last shop-legal relic of
        `rarity` (Shop rarity draws from the shop-relic bag, the rest from the
        grab bag), skipping ids in `blacklist`. Used by the merchant; a pulled
        relic never reappears this run. None if the matching bag is empty."""
        blacklist = blacklist or set()
        self._drop_disallowed_from_grab_bag()
        bag = (
            self._get_shop_relic_bag()
            if rarity == RelicRarity.SHOP
            else self.relic_grab_bag
        )
        for relic_id in reversed(bag):
            cls = ALL_RELICS[relic_id]
            if (
                cls.rarity == rarity
                and cls.is_allowed_in_shops
                and relic_id not in blacklist
            ):
                bag.remove(relic_id)
                return make_relic(relic_id)
        return None

    def _drop_disallowed_from_grab_bag(self) -> None:
        """RelicGrabBag.RemoveDisallowedRelicsFromDeques (RelicGrabBag.cs:218-270)
        — run before every pull, and PERMANENT: a relic whose
        `RelicModel.IsAllowed` is false is removed from the deque, not skipped.
        """
        self.relic_grab_bag[:] = [
            rid for rid in self.relic_grab_bag if ALL_RELICS[rid].is_allowed(self)
        ]

    def _get_shop_relic_bag(self) -> list[str]:
        """The shuffled Shop-rarity relic bag, built on first use."""
        if self._shop_relic_bag is None:
            self._shop_relic_bag = [
                relic_id for relic_id, cls in ALL_RELICS.items()
                if cls.rarity == RelicRarity.SHOP and cls.is_allowed_in_shops
                and cls.is_allowed(self) and self.owns_relic(cls)
            ]
            self.rng.shuffle(self._shop_relic_bag)
        return self._shop_relic_bag

    def obtain_relic_from_grab_bag(self, rarity_rng=None) -> Relic | None:
        """Pull from the bag front and add it to the run's relics."""
        relic = self.pull_relic_from_front(rarity_rng=rarity_rng)
        if relic is not None:
            self.add_relic(relic)
        return relic

    # ── Map / travel (actmap.py + rooms.py) ──────────────────────────────

    def start_run(
        self,
        acts: list[str] | None = None,
        ascension: int = 0,
    ) -> StandardMap:
        """Roll the run's act list and enter its first act.

        Mirrors StartRunLobby → ActModel.GetRandomList: the list is fixed at
        run start; index 0 is a uniform pick between Overgrowth and the
        unlocked alternate Underdocks, then Hive, then Glory. All four acts
        are wired into the run's room sequencing, so the default is the full
        act 1 → 2 → 3 arc (the trailing-act trim is a no-op now but stays as a
        guard for any future map-only act); pass `acts` explicitly to override.
        """
        # Character starting relics (CharacterModel.StartingRelics, granted at
        # run init by Player.PopulateStartingRelics), in the source's order.
        # Granted in every run — the game always grants them. Ironclad's is
        # Burning Blood (Ironclad.cs:57), which heals 6 HP after each won combat
        # (relics/burning_blood.py).
        for relic_id in self.character.starting_relics:
            if not any(r.id == relic_id for r in self.relics):
                self.add_relic(relic_id)
        if acts is None:
            from .rooms import act_has_rooms

            acts = [self.rng.choice(options) for options in _ACTS_BY_INDEX]
            while acts and not act_has_rooms(acts[-1]):
                acts.pop()
        if not acts:
            raise ValueError("acts must name at least one act")
        self.act_list = list(acts)
        self.victory = False
        if self.rng_set is not None:
            self._generate_all_act_rooms(ascension)
        return self.start_act(
            self.act_list[0],
            ascension=ascension,
            is_final_act=len(self.act_list) == 1,
            act_index=0,
        )

    def _generate_all_act_rooms(self, ascension: int) -> None:
        """RunManager.GenerateRooms — pre-roll every act's rooms on the UpFront
        stream at run start (parity path only).

        Shuffle UnlockState.SharedAncients, hand each act after the first a
        random prefix of what's left (`NextInt(remaining + 1)`), then generate
        each act's RoomSet in order; the final act also draws its DoubleBoss
        second boss (Asc 10) from the same stream. This is UpFront's second
        consumer after the relic grab bags, landing its counter where run.save
        records it at the first floor boundary (e.g. 413 for 89U21BV1TZ).
        start_act then retrieves these sets by act index (_generate_rooms).
        """
        from .actmap import ACT_MAP_CONFIGS, AscensionLevel
        from .rooms import SHARED_ANCIENTS, RoomSet, act_rooms

        up = self.rng_set.up_front
        remaining = list(SHARED_ANCIENTS)
        up.shuffle(remaining)
        self._shared_ancient_subsets = {}
        for name in self.act_list[1:]:
            take = up.next_int(len(remaining) + 1)
            self._shared_ancient_subsets[name] = tuple(remaining[:take])
            remaining = remaining[take:]

        double_boss = ascension >= AscensionLevel.DOUBLE_BOSS
        last = len(self.act_list) - 1
        self._act_room_sets = []
        for i, name in enumerate(self.act_list):
            rooms = act_rooms(name)
            cfg = ACT_MAP_CONFIGS[name]
            ancient_pool = (
                *rooms.ancient_keys,
                *self._shared_ancient_subsets.get(name, ()),
            )
            room_set = RoomSet.generate(
                rooms, up, cfg.num_rooms, cfg.num_weak_encounters,
                ancient_pool=ancient_pool,
            )
            if i == last and double_boss:
                # RunManager.GenerateRooms rolls the second boss here, not in
                # ActModel.GenerateRooms: NextItem over the boss pool minus the
                # primary (the RoomSet parity path leaves SecondBoss unset).
                others = [k for k in rooms.boss_keys if k != room_set.boss_key]
                if others:
                    room_set.second_boss_key = up.next_item(others)
            self._act_room_sets.append(room_set)

    @property
    def current_act_number(self) -> int:
        """1-based position in the act list (display; act_index is 0-based)."""
        return self.act_index + 1

    @property
    def at_run_end(self) -> bool:
        """The run is over: dead, or the final act's boss was beaten."""
        return self.is_dead or self.victory

    def advance_act(self) -> StandardMap:
        """RunManager.EnterNextAct: move to the next act in the rolled list —
        a fresh map and room queues, the "?"-odds reset to base (done in
        start_act), and NO heal or boss-relic step in between. Call after the
        current act's boss is beaten (at_act_end)."""
        if not self.act_list:
            raise RuntimeError("Call start_run before advance_act")
        next_index = self.act_index + 1
        if next_index >= len(self.act_list):
            raise RuntimeError("Already in the final act")
        return self.start_act(
            self.act_list[next_index],
            ascension=self.ascension,
            is_final_act=next_index == len(self.act_list) - 1,
            act_index=next_index,
        )

    def complete_run(self) -> None:
        """Mark the run won (the final act's boss is beaten). The game rolls
        into TheArchitect victory event; the sim just flags it."""
        self.victory = True

    def start_act(
        self,
        act: str | ActMapConfig = "overgrowth",
        ascension: int = 0,
        is_final_act: bool = False,
        act_index: int | None = None,
    ) -> StandardMap:
        """Generate the act's map and room queues and stand at the Ancient.

        Mirrors the game's act entry: StandardActMap.CreateFor +
        ActModel.GenerateRooms + UnknownMapPointOdds.ResetToBase. The game
        rolls all acts' rooms at run start from dedicated RNG streams; the
        sim rolls per-act from the single shared run RNG (map first, then
        rooms), per the repo's one-RNG convention.

        `ascension` is the run's cumulative ascension level; it changes the
        map only via SwarmingElites (Asc 1+, 8 elites) and DoubleBoss (Asc
        10, a second boss). DoubleBoss applies only when `is_final_act` is
        set (RunManager adds the second boss to the last act only).

        `act_index` is the run's CurrentActIndex (0-based), gating map
        modifiers like Spoils Map; it defaults from the act name.
        """
        from .actmap import ACT_MAP_CONFIGS, AscensionLevel

        config = ACT_MAP_CONFIGS[act] if isinstance(act, str) else act
        self.act_config = config
        self.ascension = ascension
        self.act_index = (
            act_index if act_index is not None
            else _DEFAULT_ACT_INDEX.get(config.name, 0)
        )
        self._is_final_act = is_final_act
        self._has_second_boss = (
            is_final_act and ascension >= AscensionLevel.DOUBLE_BOSS
        )
        self.map = self._generate_map()
        self._generate_rooms()
        self.current_point = self.map.starting_point
        # Standing at the Ancient IS entering it: RunManager.CreateRoom turns a
        # `MapPointType.Ancient` point into an **EventRoom** (PullAncient), and
        # RunManager.cs:1129 marks *every* entered room visited, so RoomSet.
        # MarkVisited(RoomType.Event) bumps this act's `eventsVisited` before
        # any "?" node is walked. Only PullNextEvent (the "?" nodes) records
        # VisitedEventIds, so the ancient's bump is a pure queue skip: the
        # first event node serves `events[1]`. The shrine itself is fired by
        # the driver (_maybe_run_ancient / the run-start Neow), which is why
        # this can't live in enter_point. Acts with no ancient node
        # (RoomSet.HasAncient false — the legacy path, where the driver rolls
        # the shrine outside the room set) skip the bump.
        if self.room_set is not None and self.room_set.ancient_key is not None:
            from .rooms import RoomType as _RoomType

            self.room_set.mark_visited(_RoomType.EVENT)
        self.map_history = []
        self._last_room_types: list[RoomType] = []
        return self.map

    # ── Map generation pipeline (RunManager.GenerateMap) ─────────────────

    def _map_listeners(self):
        """AbstractModel hook listeners for map generation — the run's deck
        cards and relics (mirrors IRunState.IterateHookListeners for this
        pass, RunState.cs:545-576).

        hook_dispatch/guard12 (round 14, LABEL F2): this used to return
        `[*self.relics, *self.deck]`, relic-first. RunState.IterateHookListeners
        builds its list deck-FIRST (RunState.cs:548-562: every deck card, plus
        its enchantment if any, per player) and only then appends
        relics/potions (:563-576, also skipped entirely here since a map-hook
        walk always passes `childCombatState == null` in the callers this
        mirrors). The order is observable, not just a call-count difference:
        `SpoilsMapCard.modify_generated_map` (cards/spoils_map.py) and
        `GoldenCompass.modify_generated_map` (relics/golden_compass.py) both
        REPLACE the generated act map wholesale rather than merging, so
        whichever listener runs LAST wins outright when both target the same
        act. `LanternKeyCard` (cards/event_cards.py) contends with
        `GoldenCompass.modify_unknown_map_point_room_types` the same way.

        Enchantments are NOT appended here (unlike RunState.cs:557-560's
        `if (card.Enchantment != null) list.Add(card.Enchantment)`): no ported
        `Enchantment` subclass implements any of the three map hooks this
        feeds (`modify_generated_map[_late]`, `modify_next_event`,
        `modify_unknown_map_point_room_types` — grepped across
        sts2_rl/enchantments.py), so the omission is dormant today, not a
        second live gap; flagged in the round-14 R1 report rather than fixed
        here since sts2_rl/enchantments.py is outside this lane's footprint.
        """
        return [*self.deck, *self.relics]

    def _map_rng(self):
        """The RNG the act's map layout is carved from.

        Parity path (SP2): StandardActMap.CreateFor seeds a fresh transient
        `new Rng(runState.Rng.Seed, $"act_{CurrentActIndex + 1}_map")` per
        generation — independent of every other stream and NOT serialized in
        run.save (so map layout is verified structurally, not by a counter).
        The GameRandomAdapter presents this stream through the random.Random
        API the faithful actmap.py port already speaks. Without a string seed,
        fall back to the legacy shared random.Random (pre-SP2 behavior)."""
        if self.rng_set is None:
            return self.rng
        from .rng import GameRandomAdapter, Rng

        return GameRandomAdapter(
            Rng(self.rng_set.seed, name=f"act_{self.act_index + 1}_map")
        )

    def _generate_map(self):
        """RunManager.GenerateMap: build the base act map, then run it through
        the relic/card modifier pipeline (Spoils Map, Golden Compass)."""
        from .actmap import StandardMap

        base = StandardMap(
            rng=self._map_rng(),
            config=self.act_config,
            ascension=self.ascension,
            has_second_boss=self._has_second_boss,
        )
        listeners = self._map_listeners()
        act_map = base
        for listener in listeners:  # Hook.ModifyGeneratedMap
            act_map = listener.modify_generated_map(self, act_map, self.act_index)
        # Hook.ModifyGeneratedMapLate. NOTE THE MISMATCH, because it is a real one
        # and it is not this function's to resolve: `grep -rn
        # ModifyGeneratedMapLate src/` outside AbstractModel.cs/Hook.cs returns
        # three lines — the two implementers (SpoilsMap.cs:63, FurCoat.cs:58) and
        # ONE dispatch, at RunManager.cs:740, inside `if (SavedMapsToLoad != null
        # && ...)`, the branch that DESERIALIZES a saved ActMap. The branch that
        # GENERATES a map (RunManager.cs:743-747) runs ModifyGeneratedMap and
        # AfterMapGenerated ONLY; the Late hook exists to re-attach quests/shape
        # to a loaded map, and the sim has no save-load at all.
        #
        # The pass is kept because card/spoils_map folds work into this hook that
        # the sim needs on a fresh generation (it records the Treasure coord that
        # `after_map_generated` then pins its quest to), and how that should be
        # reconciled with the source is the CARD stream's entry, not Fur Coat's.
        # Fur Coat instead no longer OVERRIDES the hook — see relics/fur_coat.py,
        # where relic/fur_coat/g2 is closed.
        for listener in listeners:  # Hook.ModifyGeneratedMapLate
            act_map = listener.modify_generated_map_late(
                self, act_map, self.act_index
            )
        for listener in listeners:  # Hook.AfterMapGenerated
            listener.after_map_generated(self, act_map, self.act_index)
        return act_map

    def _generate_rooms(self) -> None:
        """ActModel.GenerateRooms + UnknownMapPointOdds.ResetToBase.

        Parity runs pre-roll every act on the UpFront stream at start_run
        (_generate_all_act_rooms), so here we simply retrieve this act's set.
        The legacy path rolls it lazily on the shared run RNG.
        """
        from .rooms import RoomSet, UnknownOdds, act_rooms

        if self._act_room_sets is not None:
            self.room_set = self._act_room_sets[self.act_index]
        else:
            rooms = act_rooms(self.act_config.name)
            self.room_set = RoomSet.generate(
                rooms,
                self.rng,
                self.act_config.num_rooms,
                self.act_config.num_weak_encounters,
                has_second_boss=self._has_second_boss,
            )
        if self.unknown_odds is None:
            self.unknown_odds = UnknownOdds()
        else:
            self.unknown_odds.reset_to_base()

    def regenerate_map(self) -> None:
        """RunManager.GenerateMap called mid-act (Golden Compass' pickup effect):
        rebuild only the map through the modifier pipeline and return to the
        Ancient. The room queues and "?"-odds are left intact, as in the source
        (rooms are rolled once per act). No-op before an act has started."""
        if self.act_config is None:
            return
        self.map = self._generate_map()
        self.current_point = self.map.starting_point
        self.map_history = []
        self._last_room_types = []

    @property
    def at_act_end(self) -> bool:
        """True once standing on a terminal boss node (the boss on a normal
        act, or the second boss under DoubleBoss). Callers loop travel
        until this holds."""
        return self.current_point is not None and not self.current_point.children

    def travelable_points(self) -> list[MapPoint]:
        """MapTravel.GetTravelablePointsFrom: the current point's children —
        plus, while a relic grants free travel (Winged Boots'
        ShouldAllowFreeTravel), every point on the next row — in a stable
        order."""
        if self.current_point is None:
            raise RuntimeError("Call start_act before traveling")
        points = set(self.current_point.children)
        if any(r.should_allow_free_travel() for r in self.relics):
            points.update(self.map.points_in_row(self.current_point.row + 1))
        return sorted(points, key=lambda p: (p.col, p.row))

    def enter_point(self, point: MapPoint) -> RoomResolution:
        """Travel to a child point and resolve its room (the sim's
        RunManager.EnterMapPointInternal).

        Combat rooms return the encounter to fight (drive it with
        create_combat / finish_combat, then generate_combat_rewards); event
        rooms return the built Event; treasure grants a grab-bag relic plus
        42–52 gold (and any Spoils Map quest payout); shops return a stocked
        MerchantInventory (resolution.shop) to buy from; rest sites return
        bare so the caller picks rest_heal() or an upgrade.
        """
        from .events import make_event
        from .rooms import (
            MapPointType,
            RoomResolution,
            RoomType,
            build_room_type_blacklist,
            roll_room_type,
        )

        if self.current_point is None or self.room_set is None:
            raise RuntimeError("Call start_act before traveling")
        if point not in self.travelable_points():
            raise ValueError(f"{point} is not reachable from {self.current_point}")
        # Travel to a non-child point consumes a free-travel charge
        # (Winged Boots; the source detects it in AfterRoomEntered).
        if point not in self.current_point.children:
            for relic in self.relics:
                if relic.should_allow_free_travel():
                    relic.on_free_travel_used(self)
                    break

        # Blacklist is computed from the point being left: its rooms and
        # its children (RunManager builds it before moving).
        blacklist = build_room_type_blacklist(
            self._last_room_types, self.current_point.children
        )
        allowed = (
            self._unknown_allowed_room_types(blacklist)
            if point.point_type == MapPointType.UNKNOWN
            else None
        )
        # "?"-node resolution draws on the run's UnknownMapPoint stream in the
        # SP2 parity path (RunOddsSet's dedicated Rng), else the legacy RNG.
        # Only Unknown points consume it, so passing it for every point is
        # harmless (roll_room_type ignores rng for fixed types).
        room_type_rng = (
            self.rng_set.unknown_map_point
            if self.rng_set is not None
            else self.rng
        )
        room_type = roll_room_type(
            point.point_type, self.unknown_odds, room_type_rng, blacklist, allowed
        )
        self.current_point = point
        self.total_floor += 1  # IRunState.TotalFloor: rooms entered this run
        resolution = RoomResolution(
            point=point, map_point_type=point.point_type, room_type=room_type
        )
        # RelicModel.AfterRoomEntered fires as the room is entered, before its
        # contents resolve (Silver Crucible counts treasure rooms here).
        for relic in list(self.relics):
            relic.after_room_entered(self, point, room_type)
        if room_type == RoomType.MONSTER:
            resolution.encounter = self.room_set.next_normal_encounter
        elif room_type == RoomType.ELITE:
            resolution.encounter = self.room_set.next_elite_encounter
        elif room_type == RoomType.BOSS:
            resolution.encounter = self.room_set.next_boss_encounter
        elif room_type == RoomType.EVENT:
            self.room_set.ensure_next_event_is_valid(self)
            event_id = self.room_set.next_event_id
            # `Hook.ModifyNextEvent` (Hook.cs:1830-1836). Its ONE call site is
            # ActModel.PullNextEvent (ActModel.cs:437-443), which is exactly this
            # shape: EnsureNextEventIsValid, then the hook chain, then
            # `AddVisitedEvent(eventModel)` -- so the hook sits between the pull
            # and the visited-set add, and the event RECORDED as visited is the
            # MODIFIED one. The Lantern Key is the source's only implementer, and
            # it is why an event whose own IsAllowed is False can still be served.
            for listener in self._map_listeners():
                event_id = listener.modify_next_event(self, event_id)
            if event_id is not None:
                resolution.event = make_event(event_id, self)
                self.visited_event_ids.add(event_id)
        elif room_type == RoomType.TREASURE:
            # Treasure chest (OneOffSynchronizer): a grab-bag relic plus
            # 42–52 gold, both granted on entry, plus any Spoils Map payout.
            # Hook.ShouldGenerateTreasure can suppress the chest entirely
            # (Silver Crucible's first treasure room).
            if all(r.should_generate_treasure(self) for r in self.relics):
                # TreasureRoomRelicSynchronizer rolls the chest relic's rarity
                # on State.Rng.TreasureRoomRelics (RunManager.cs:413), one
                # NextFloat per player, then pulls from the grab bag front.
                resolution.relic = self.obtain_relic_from_grab_bag(
                    rarity_rng=(self.rng_set.treasure_room_relics
                                if self.rng_set is not None else None))
                # OneOffSynchronizer.DoTreasureRoomRewards: the chest gold is
                # NextInt(42, 53) on the per-player Rewards stream (parity), else
                # the legacy run.rng. (The relic itself is picked on the
                # uncompared TreasureRoomRelics stream — left on run.rng.)
                lo, hi = TREASURE_GOLD
                if self.rng_set is not None:
                    treasure_gold = self.rewards_rng.next_int_range(lo, hi + 1)
                else:
                    treasure_gold = self.rng.randint(lo, hi)
                self.gain_gold(treasure_gold)
                resolution.gold = treasure_gold
            resolution.gold += self._complete_map_point_quests(point)
            # `TreasureRoom.DoExtraRewardsIfNeeded` (TreasureRoom.cs:75-97),
            # called UNCONDITIONALLY after `DoNormalRewards` — even when
            # Hook.ShouldGenerateTreasure suppressed the chest above.
            # `RewardsCmd.GenerateForRoomEnd` -> `WithRewardsFromRoom(this)`
            # -> `GenerateWithoutOffering` fires `Hook.ModifyRewards`
            # (RewardsSet.cs:136) over an EMPTY base reward list
            # (`GenerateRewardsFor` returns [] for a TreasureRoom,
            # RewardsSet.cs:213-219 — it only throws for a room that is
            # neither CombatRoom nor TreasureRoom) with `Room` set to this
            # TreasureRoom — a dispatch the chest's own direct gold+relic
            # grant above never goes through. No ported relic is
            # Room==Treasure-sensitive today (every TryModifyRewards[Late]
            # implementer is gated to Monster/Elite/Boss, or only touches
            # EXISTING card_rewards groups, which stay empty here), so this
            # stays a no-op in practice — stashed for the driver to offer
            # only when a future one actually adds something.
            treasure_rewards = CombatRewards(
                room_type=RoomType.MONSTER, room=RoomType.TREASURE)
            apply_reward_modifiers(self, treasure_rewards)
            if not treasure_rewards.is_empty:
                self.pending_treasure_extra_rewards = treasure_rewards
        elif room_type == RoomType.SHOP:
            from .shop import MerchantInventory

            resolution.shop = MerchantInventory.create(self)
            # RelicModel.AfterRoomEntered's merchant branch needs the stocked
            # inventory (Lord's Parasol buys everything), so the sim fires a
            # dedicated hook once it exists.
            for relic in list(self.relics):
                relic.after_shop_entered(self, resolution.shop)
        self.room_set.mark_visited(room_type)
        self._last_room_types = [room_type]
        self.map_history.append((point, room_type))
        return resolution

    def _unknown_allowed_room_types(self, blacklist) -> set:
        """The room types a "?" node may roll into after every relic/card's
        ModifyUnknownMapPointRoomTypes (Golden Compass narrows this to Event)."""
        from .rooms import RoomType

        room_types = {
            RoomType.MONSTER,
            RoomType.ELITE,
            RoomType.TREASURE,
            RoomType.SHOP,
            RoomType.EVENT,
        } - set(blacklist)
        for listener in self._map_listeners():
            room_types = set(
                listener.modify_unknown_map_point_room_types(self, room_types)
            )
        return room_types

    def _complete_map_point_quests(self, point) -> int:
        """Trigger any quests attached to a just-entered point (Spoils Map's
        treasure payout). Returns the gold granted."""
        gold = 0
        for quest in list(getattr(point, "quests", [])):
            on_complete = getattr(quest, "on_quest_complete", None)
            if on_complete is not None:
                gold += on_complete(self)
        return gold

    def rest_site_options(self):
        """Hook.TryModifyRestSiteOptions over the run's deck cards then
        relics (mirrors IterateHookListeners's order): the extra rest-site
        actions beyond Heal/Smith/Leave (Byrdonis Egg's Hatch, Pael's
        Growth's Clone, Pumpkin Candle's Kindle, Meat Cleaver's Cook,
        Shovel's Dig, Girya's Lift)."""
        options: list = []
        for card in list(self.deck):
            card.modify_rest_site_options(self, options)
        for relic in list(self.relics):
            relic.modify_rest_site_options(self, options)
        return options

    def should_disable_remaining_rest_site_options(self) -> bool:
        """Hook.ShouldDisableRemainingRestSiteOptions: True (end the visit
        after one action) unless a relic says otherwise (Miniature Tent),
        in which case the visit continues."""
        return all(
            relic.should_disable_remaining_rest_site_options(self)
            for relic in self.relics
        )

    @property
    def has_event_pet(self) -> bool:
        """Player.HasEventPet — any relic with AddsPet (Pael's Legion)."""
        return any(r.adds_pet for r in self.relics)

    def rest_heal(self) -> int:
        """Take the rest site's heal option (30% of max HP, truncated), then
        fire Hook.AfterRestSiteHeal over the relics (Stone Humidifier)."""
        healed = self.heal(self.rest_site_heal_amount())
        for relic in list(self.relics):
            relic.after_rest_site_heal(self)
        return healed

    def rest_heal_rewards(self) -> CombatRewards:
        """HealRestSiteOption.ExecuteRestSiteHeal's Hook.ModifyRestSiteHealRewards
        step: relics may add rewards to the screen offered after the heal
        (Dream Catcher's 3-card choice, drawn from the Monster-room card pool
        via CardCreationOptions.ForRoom — same odds table as a Monster-room
        combat reward). Empty unless a relic populates it. Call after
        rest_heal(); the caller (driver._run_rest) offers it the same way it
        offers post-combat rewards."""
        from .rooms import RoomType

        rewards = CombatRewards(room_type=RoomType.MONSTER)
        for relic in list(self.relics):
            relic.modify_rest_site_heal_rewards(self, rewards)
        # ...and then RewardsCmd.OfferCustom hands the list to a RewardsSet,
        # whose GenerateWithoutOffering runs Hook.ModifyRewards over it like
        # any other screen (RewardsSet.cs:136) — that is how Driftwood's
        # reroll reaches a rest-site card choice. `rewards.room` stays None
        # here, which is what keeps the room-gated relics out (a custom set
        # never sets RewardsSet.Room).
        apply_reward_modifiers(self, rewards)
        return rewards

    def rest_upgrade(self) -> Card | None:
        """Take the rest site's smith option: upgrade one card chosen via
        the run's card selector (random without one)."""
        chosen = self.select_cards("upgrade", self.upgradable_cards(), 1)
        if not chosen:
            return None
        chosen[0].upgrade()
        return chosen[0]

    # ── Combat integration ───────────────────────────────────────────────

    def create_combat(self, encounter: Encounter, **kwargs) -> CombatState:
        """Enter a combat carrying this run's deck, relics, potions, and HP.

        The deck is deep-copied so in-combat mutations (upgrades, afflictions,
        cost changes) don't leak back — the game clones canonical cards into
        each combat the same way. Call finish_combat afterwards to sync the
        outcome back into the run.

        Each combat card remembers which run-deck card it was copied from
        (CombatState.deck_card_origins — the sim's CardModel.DeckVersion), so
        effects that touch the deck itself (Thieving Hopper's steal) can be
        reconciled by finish_combat.
        """
        deck_copy = copy.deepcopy(self.deck)
        # Parity: monster composition is picked from a per-encounter Rng seeded
        # from the run seed + current floor + the encounter's slug
        # (EncounterModel.GenerateMonstersWithSlots), NOT a shared stream. Legacy
        # runs pass None and keep their random.Random composition draws.
        encounter_selection_rng = None
        if self.rng_set is not None:
            from .rng import make_encounter_rng
            encounter_selection_rng = make_encounter_rng(
                self.rng_set.seed, self.total_floor, encounter.entry)
        combat = CombatState(
            starting_deck=deck_copy,
            rng=self.rng,
            rng_set=self.rng_set,   # None in legacy runs → legacy CombatRng
            encounter=encounter,
            encounter_selection_rng=encounter_selection_rng,
            potions=self.potions,
            relics=self.relics,
            card_selector=kwargs.pop("card_selector", self.card_selector),
            max_potions=kwargs.pop("max_potions", self.max_potions),
            max_hp=self.max_hp,
            current_hp=self.hp,
            # The run's balance is what in-combat thefts (Gremlin Merc's
            # Thievery) can take and Seal of Gold can spend — the game reads
            # Player.Gold live, so it must be visible from turn 1 (which
            # starts during construction).
            player_gold=self.gold,
            # In-combat generation draws from the character's CardPool.
            character=self.character,
            **kwargs,
        )
        combat.deck_card_origins = {
            id(copy_): orig for copy_, orig in zip(deck_copy, self.deck)
        }
        return combat

    def finish_combat(self, combat: CombatState, room_type: RoomType | None = None) -> None:
        """Sync a finished combat back into the run: HP, max HP (Feed), and
        remaining potions. Rewards are a separate step — call
        generate_combat_rewards(room_type) after a won fight.

        When `room_type` is passed and the player survived, fires
        RelicModel.AfterCombatEnd over the relics (Fishing Rod's every-3rd-
        monster-combat upgrade)."""
        self.max_hp = combat.player.max_hp
        self.hp = max(0, combat.player.hp)
        # A plain list copy preserves slot identity/gaps 1:1 (both sides are
        # the same fixed-length list[Potion | None] shape).
        self.potions = list(combat.player.potions)
        # In-combat gold gains (Hand of Greed) credit the run's ledger;
        # in-combat thefts (Gremlin Merc's Thievery — PlayerCmd.LoseGold
        # GoldLossType.Stolen) debit it. Steals are capped in-combat against
        # the live balance, so the net never goes below 0.
        self.gain_gold(combat.gold_gained)
        self.lose_gold(combat.gold_stolen)
        self.lose_gold(combat.gold_spent)
        # Thieving Hopper: SwipePower.Steal calls CardPileCmd.RemoveFromDeck at
        # steal time, so a stolen card leaves the run deck permanently — the
        # kill only *offers* it back (SpecialCardReward is take-or-skip), and
        # an escaped hopper keeps it for good. The sim deep-copies the deck
        # into each combat, so the removal is reconciled here through the
        # deck_card_origins map. Source: src/Core/Models/Powers/SwipePower.cs
        # (Steal / BeforeDeath).
        # A DEAD hopper no longer carries its SwipePower: the power is stripped
        # on death like any other (Creature.RemoveAllPowersAfterDeath), so it
        # hands its origins to the combat from `on_removed` instead. An ESCAPED
        # hopper keeps the power, and is still found by the walk below.
        for origin in combat.stolen_deck_origins:
            if origin in self.deck:
                self.deck.remove(origin)
        for enemy in combat.enemies:
            # Swipe is Instanced: one power per steal, so every instance has
            # to be walked, not just the first.
            for swipe in enemy.powers.instances("swipe"):
                if swipe.stolen_card is None:
                    continue
                origin = combat.deck_card_origins.get(id(swipe.stolen_card))
                if origin is not None and origin in self.deck:
                    self.deck.remove(origin)
        # Carry any post-combat extras (a dead hopper's returned card) into
        # the run for generate_combat_rewards to surface.
        self.pending_reward_extras.extend(combat.pending_reward_extras)
        # Hook.AfterCombatEnd (CombatManager.cs:988 -> Hook.cs:328-335) walks
        # the RUN's listeners, which include the deck -- and it fires before
        # Hook.AfterCombatVictory and regardless of the outcome. Guilty's
        # countdown is the sim's only deck-side implementer, and it is exactly
        # why the walk has to reach the deck at all.
        for card in list(self.deck):
            card.after_combat_end(self)
        # ...and then the COMBAT's listeners: while `childCombatState` is still
        # set, `RunState.IterateHookListeners(combatState)` appends the whole
        # combat listener list to the run walk (RunState.cs:588+;
        # seam/hook_dispatch step 18), which is how a POWER gets to see
        # AfterCombatEnd. Order within the combat list is allies before enemies
        # and, per creature, powers before relics (CombatState.cs:410-435 —
        # steps 1 and 2), so the player's powers come first.
        #
        # Powers only: the run's own relics are walked below under
        # AfterCombatVictory, and no ported potion, card-in-pile or orb
        # implements this hook. ImprovementPower is the one implementer, and it
        # needs the run because the pile it upgrades is the RUN deck.
        for creature in [combat.player, *combat.enemies]:
            for power in list(creature.powers.values()):
                fn = getattr(power, "after_combat_end", None)
                if fn is not None:
                    fn(self)
        if room_type is not None and not self.is_dead:
            # Hook.AfterCombatVictory (Hook.cs:340-352) makes TWO complete
            # passes over the listeners — AfterCombatVictoryEarly over all of
            # them, then AfterCombatVictory over all of them. MeatOnTheBone.cs
            # :47 is the source's only Early implementer and rides the
            # combat-level dispatch (on_combat_end_early), but the run-level
            # walk mirrors the same two phases.
            for relic in list(self.relics):
                relic.after_combat_end_early(self, room_type)
            for relic in list(self.relics):
                relic.after_combat_end(self, room_type)

    def generate_combat_rewards(
        self,
        room_type: RoomType,
        gold_proportion: float = 1.0,
        encounter: "Encounter | None" = None,
    ) -> CombatRewards:
        """The post-combat reward screen (RewardsSet.WithRewardsFromRoom):
        gold and any elite relic are granted immediately; the 3-card choice
        and the potion are left on the result for the caller to offer.
        `encounter` carries its Min/MaxGoldReward override when it has one.
        See rewards.py for the ported mechanics."""
        return generate_combat_rewards(
            self, room_type, gold_proportion, encounter)

    @property
    def is_final_act(self) -> bool:
        """Whether the current act is the run's last (its boss ends the run
        with no rewards). Set via start_act(is_final_act=True)."""
        return self._is_final_act

    def __repr__(self) -> str:
        return (
            f"RunState(hp={self.hp}/{self.max_hp}, gold={self.gold}, "
            f"deck={len(self.deck)} cards, relics={len(self.relics)}, "
            f"potions={len(self.held_potions)})"
        )
