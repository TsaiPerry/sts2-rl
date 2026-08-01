from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import TYPE_CHECKING

from ..hooks import CAT_CARD

if TYPE_CHECKING:
    from ..afflictions import Affliction
    from ..combat import CombatCtx
    from ..rest_site import RestSiteOption


class CardType(Enum):
    ATTACK = "attack"
    SKILL = "skill"
    POWER = "power"
    STATUS = "status"
    CURSE = "curse"
    QUEST = "quest"


class CardRarity(Enum):
    BASIC = "basic"
    COMMON = "common"
    UNCOMMON = "uncommon"
    RARE = "rare"
    ANCIENT = "ancient"
    TOKEN = "token"
    STATUS = "status"
    CURSE = "curse"
    EVENT = "event"
    QUEST = "quest"


class TargetType(Enum):
    ANY_ENEMY = "any_enemy"
    ALL_ENEMIES = "all_enemies"
    RANDOM_ENEMY = "random_enemy"
    SELF = "self"
    NONE = "none"


_CARD_CLASSES: dict[str, type[Card]] = {}


def register_card(cls: type[Card]) -> type[Card]:
    _CARD_CLASSES[cls.id] = cls
    return cls


def make_card(card_id: str) -> Card:
    return _CARD_CLASSES[card_id]()


def create_clone(card: Card) -> Card:
    """Mirrors CardModel.CreateClone (CardModel.cs:2168) -> MutableClone ->
    DeepCloneFields: a copy of the card at the same upgrade level that also
    carries a live COPY of the source's enchantment (CardModel.cs:1204-1209 --
    ClonePreservingMutability, then EnchantInternal at the source's Amount) and
    of its affliction (CardModel.cs:1210-1215).

    The game's clone starts as a memberwise copy, so an enchantment's static
    card modification is already baked into it and ModifyCard is deliberately
    NOT re-run (EnchantmentModel.cs:350-353); the sim rebuilds the card from
    its class instead, so the copy re-runs the enchantment's modification to
    reach the same state.

    THE COPY IS MEMBERWISE, and that is the whole point. `ClonePreservingMutability`
    is `AbstractModel.MutableClone` (AbstractModel.cs:162-169) — a memberwise
    copy — and only THEN `DeepCloneFields` (CardModel.cs:1193-1216) and
    `AfterCloned` (:1218-1239). So everything the card was carrying comes
    across by default and the two override passes only re-point what must not
    be shared. The sim used to REBUILD from the class and replay upgrades,
    which silently dropped every per-instance edit that was not a printed
    number: the live keyword set (`_keywords = GetKeywordsWithSources(
    KeywordSources.Local)`, :1196-1200 — Music Box's Ethereal), the cloned
    `_energyCost` and its `_localModifiers` (:1202 -> CardEnergyCost.cs:411-421 —
    SetThisCombat / AddThisTurn / free-this-turn), the cloned `_dynamicVars`
    (:1201 — Rampage's and Thrash's accumulated damage) and `BaseReplayCount`
    (Hidden Gem). Copying `__dict__` is the sim's memberwise pass.

    Clones only exist in combat -- CreateClone throws for a card outside a
    combat pile (CardModel.cs:2170-2173). Run-level copies go through
    ICardScope.CloneCard instead (relics/paels_growth.py, run.py's per-combat
    deck copy); that is the SAME `ClonePreservingMutability`
    (CombatState.cs:188-193), minus the two lines CreateClone adds on top.
    """
    clone = type(card)()
    clone.__dict__.update(card.__dict__)
    # `AfterCloned` (CardModel.cs:1218-1239) re-points what a memberwise copy
    # must not share: CurrentTarget, CurrentPlayIndex, DeckVersion,
    # HasBeenRemovedFromState and every event handler. The COMBAT
    # BACK-REFERENCE IS NOT ON THAT LIST — `CardModel.CombatState`
    # (CardModel.cs:1017-1028) is derived from `_owner`, which neither
    # AfterCloned nor DeepCloneFields touches, so the clone reaches the combat
    # exactly as its source does and `__dict__` carrying it over is correct.
    # Clearing it here (as this function did when it was first written) left
    # every clone combat-less: harmless for Sharp, which only adds damage, but
    # Adroit's OnPlay is `CreatureCmd.GainBlock(base.Card.Owner.Creature, ...)`
    # and raised AttributeError on the copy.
    #
    # What must be cleared is only the two ATTACHMENTS, so the copy does not
    # hold the source's own enchantment/affliction objects.
    clone.enchantment = None
    clone.affliction = None
    # DeepCloneFields' two tail blocks (CardModel.cs:1204-1215):
    # `ClonePreservingMutability` on each, then `EnchantInternal` /
    # `AfflictInternal` at the same Amount. `attach_INTERNAL`, not `attach`:
    # the game's clone is memberwise, so the enchantment's static card
    # modification is already baked into the copy and ModifyCard is
    # deliberately NOT re-run — EnchantmentModel.cs:350-353 says so, and Souls
    # is why it matters (its CanEnchant demands the Exhaust its own ModifyCard
    # removes, so a clone that re-ran the normal path would be refused).
    if card.enchantment is not None:
        card.enchantment.clone_preserving_mutability().attach_internal(clone)
    if card.affliction is not None:
        affliction = type(card.affliction)(card.affliction.amount)
        affliction.card = clone
        clone.affliction = affliction
    # CardModel.cs:2178 — CreateClone's own tail, the one thing it does that
    # plain CloneCard does not. (Out of combat the flag is always False, so the
    # run-level callers are unaffected.)
    clone.exhaust_on_next_play = False
    return clone


class Card(ABC):
    id: str
    name: str
    card_type: CardType
    rarity: CardRarity
    # Last in its owner's slice of the dispatch walk: C# walks the cards of
    # AllPiles after powers, relics, potions and orbs
    # (CombatState.IterateHookListeners, CombatState.cs:449-467).
    hook_category = CAT_CARD
    target_type: TargetType = TargetType.ANY_ENEMY
    is_playable: bool = True
    is_ethereal: bool = False
    has_turn_end_in_hand_effect: bool = False
    is_unpowered: bool = False
    # CardModel.GainsBlock — declared per card in the source (NOT derivable
    # from `base_block`: Entrench/Fisticuffs gain block with no printed
    # number, and Feel No Pain's number belongs to its power, not the card).
    # Nimble's CanEnchant gates on it.
    gains_block: bool = False
    # Exhaust keyword: the card goes to the exhaust pile instead of the
    # discard pile after being played (mirrors CardKeyword.Exhaust).
    exhausts: bool = False
    # Innate keyword: starts on top of the draw pile, and the first-turn hand
    # draw is raised to include all innate cards (mirrors CardKeyword.Innate).
    innate: bool = False
    # Retain keyword: the card is not discarded by the end-of-turn hand flush
    # (mirrors CardKeyword.Retain). Read through `should_retain_this_turn`,
    # which also honours single-turn Retain.
    retain: bool = False
    # Sly keyword (CardKeyword.Sly). Read through `is_sly_this_turn`. No sim
    # content grants or consumes Sly yet; the keyword exists so the
    # single-turn variant EndOfTurnCleanup clears has something to fall back
    # to, exactly as CardModel.IsSlyThisTurn (:619-629) does.
    sly: bool = False
    # Eternal keyword: the card cannot be removed from the deck (mirrors
    # CardKeyword.Eternal → IsRemovable). Deck removal happens between
    # combats, so this flag has no effect inside the sim; it is kept for
    # fidelity with the source card definitions.
    eternal: bool = False
    # X-cost (mirrors HasEnergyCostX): the card costs ALL remaining energy;
    # play_card stores the amount spent in captured_x for on_play to read
    # (mirrors EnergyCost.CapturedXValue / ResolveEnergyXValue).
    energy_cost_x: bool = False
    # Mirrors CardModel.CanBeGeneratedByModifiers: whether the card can be
    # picked when a random curse is generated (CursedRun modifier, Neow's
    # Bones / Sere Talon relics all filter the curse pool by this).
    can_be_generated_by_modifiers: bool = True
    # Mirrors CardModel.CanBeGeneratedInCombat: whether in-combat card
    # generation (CardFactory.FilterForCombat — Infernal Blade, Discovery,
    # Jack of All Trades, ...) may create this card. Out-of-run effects
    # (Alchemize's potion, Hand of Greed's gold, Hidden Gem) opt out.
    can_be_generated_in_combat: bool = True
    # Card tags (mirrors CardModel.Tags, e.g. "strike" for Perfected Strike).
    tags: frozenset[str] = frozenset()
    # Mirrors CardModel.MaxUpgradeLevel (0 for statuses/curses — they can
    # never be upgraded, e.g. by Armaments).
    max_upgrade_level: int = 1
    # When True, play_card calls on_play once for ALL_ENEMIES cards; the card
    # iterates enemies itself (needed when a card has a one-time setup step
    # alongside per-enemy damage, e.g. Breakthrough's self-damage).
    handles_own_routing: bool = False

    def __init__(self) -> None:
        self.upgrade_level: int = 0
        self._energy_cost: int = 0
        # X value captured when an X-cost card is played (energy spent).
        self.captured_x: int = 0
        # Per-turn cost modifiers. LocalCostModifierExpiration.EndOfTurn
        # (LocalCostModifierExpiration.cs:20), so CardEnergyCost.EndOfTurnCleanup
        # (:331-335) drops them — at the end of the turn, not the start of the
        # next one. Mirror EnergyCost.AddThisTurn and SetToFreeThisTurn.
        self._cost_delta_this_turn: int = 0
        self._free_this_turn: bool = False
        # Absolute cost override lasting until the end of the turn (mirrors
        # EnergyCost.SetThisTurnOrUntilPlayed, used by Snecko Oil's cost
        # randomisation); cleared by end_of_turn_cleanup.
        self._cost_this_turn: int | None = None
        # CardModel._exhaustOnNextPlay / _hasSingleTurnRetain /
        # _hasSingleTurnSly (CardModel.cs:559-629). All three are cleared by
        # EndOfTurnCleanup (:1612-1614); the first is ALSO consumed by the play
        # that honours it (:2076-2078).
        self.exhaust_on_next_play: bool = False
        self._has_single_turn_retain: bool = False
        self._has_single_turn_sly: bool = False
        # Cost override lasting the rest of the combat (mirrors
        # EnergyCost.SetThisCombat, used by the Slither enchantment); cleared
        # by reset_combat_state at combat setup.
        self._cost_this_combat: int | None = None
        # Extra plays granted for the rest of the combat (mirrors
        # CardModel.BaseReplayCount, raised by Hidden Gem); seeds the play
        # count alongside the enchantment replay hooks (Spiral/Glam).
        self.base_replay_count: int = 0
        # `CardPlay.Resources.EnergyValue` (ResourceInfo.cs:9-16) — the amount of
        # energy this card COST when it was played, which is NOT the same as
        # EnergySpent: the struct's own doc comment says "if you auto-play a
        # 3-energy-cost card, this will be 3, while EnergySpent will be 0". The
        # sim collapsed the two into the single integer `on_energy_spent` carries,
        # so an auto-play looked free to every reader of EnergyValue. Set by
        # play_card / auto_play_card for the duration of the play, alongside
        # `captured_x` and `current_play_index`, because the sim has no CardPlay
        # object to hang it on.
        self.energy_value: int = 0
        # At most one affliction per card (mirrors CardModel.Affliction).
        self.affliction: "Affliction | None" = None
        # At most one enchantment per card (mirrors CardModel.Enchantment).
        # Attached out of combat (events); registered as a hook listener by
        # CombatState so it can react to its card being drawn/played.
        self.enchantment = None
        # Back-reference to the owning combat (mirrors CardModel.CombatState),
        # set when the card is registered as a hook listener; lets card-level
        # hook methods reach combat state (Stomp, Drum of Battle, Howl).
        self.combat = None
        self._init_vars()

    def _init_vars(self) -> None:
        pass

    def _on_upgrade(self) -> None:
        pass

    def upgrade(self) -> None:
        self.upgrade_level += 1
        self._on_upgrade()

    # CardKeyword.cs — the enum in full, minus `None`. `is_playable` is
    # Unplayable inverted. `DowngradeInternal` rebuilds the whole SET from the
    # canonical model, so every one of these has to come back to its class
    # default no matter which of them a given `_on_upgrade` touched.
    _KEYWORD_ATTRS = ("exhausts", "is_ethereal", "innate", "is_playable",
                      "retain", "sly", "eternal")

    def enchanted_replay_count(self) -> int:
        """`CardModel.GetEnchantedReplayCount()` (CardModel.cs:1129-1132) —
        `Enchantment?.EnchantPlayCount(BaseReplayCount) ?? BaseReplayCount`.

        Note the null branch: it returns BaseReplayCount, NOT zero. So a card
        that is already replaying for ANY reason — including one a previous
        Hidden Gem raised — reports a non-zero count.
        """
        if self.enchantment is None:
            return self.base_replay_count
        return self.enchantment.modify_card_play_count(
            self, None, self.base_replay_count)

    def _after_downgraded(self) -> None:
        """`CardModel.AfterDowngraded` (CardModel.cs:2150-2155) — "gives cards
        a chance to add extra cleanup logic for downgrades. No-op by default."

        The three cards that override it (Maul, Rampage, Thrash) all do the
        same thing: re-add the damage their own plays accumulated, which the
        rebuild-from-canonical above has just thrown away. Rampage.cs:24-26
        says so in as many words — "Required so we can restore the extra
        damage amount after a downgrade (ie Magiknight)".
        """

    def downgrade(self) -> None:
        """`CardModel.DowngradeInternal` (CardModel.cs:2134-2148).

        The game re-derives the card from its canonical model rather than
        unwinding deltas, and does it in a fixed order: level to ZERO (:2137,
        not a decrement); dynamic vars from canonical (:2139); energy cost
        (:2140); **the whole keyword set from canonical** (:2143);
        `AfterDowngraded()` (:2144); `Enchantment?.ModifyCard()` (:2145).

        The sim's stand-in for "re-derive from canonical" is re-running
        `_init_vars`, which rebuilds only what a card happens to set there.
        That was enough for the numbers and NOT enough for the keywords: an
        `_on_upgrade` that writes `self.innate = True` creates an INSTANCE
        attribute shadowing the class default, and re-running `_init_vars`
        never removes it. Five of the pool's cards were sticky that way
        (aggression, apparition, hello_world, juggling, wish). Deleting the
        instance shadows first is the sim's `_keywords = cardModel.
        GetKeywordsWithSources(KeywordSources.Local).ToHashSet()`.
        """
        if self.upgrade_level <= 0:
            return
        self.upgrade_level = 0
        for attr in self._KEYWORD_ATTRS:
            self.__dict__.pop(attr, None)
        self._init_vars()
        self._after_downgraded()
        # The rebuild wiped whatever the enchantment had done to the card, so
        # re-run its modification logic — CardModel.DowngradeInternal does the
        # same right after re-deriving from the canonical model
        # (`Enchantment?.ModifyCard()`, CardModel.cs:2145).
        if self.enchantment is not None:
            self.enchantment.modify_card()

    @property
    def is_upgradable(self) -> bool:
        """Mirrors CardModel.IsUpgradable (upgrade level below the max)."""
        return self.upgrade_level < self.max_upgrade_level

    # ── Declarative base stats (machine-readable card numbers) ───────────
    # Cards store their printed numbers as instance vars set in _init_vars
    # and mutated by _on_upgrade (self._damage / self._hits / self._block /
    # self._hp_loss, plus one card-specific "magic" amount) — the repo-wide
    # convention. These properties expose that convention as a uniform read
    # API (mirrors the game's dynamic card vars, CardModel.
    # UpdateDynamicVarPreview reads the same numbers), so upgrades are
    # reflected automatically. Cards whose damage is computed from combat
    # state (Body Slam, Bully, Ashen Strike, Perfected Strike) define
    # calc_damage(ctx, target) instead; previews.card_base_damage prefers it.

    # Attr names that hold a card's principal secondary number ("magic
    # number"), in priority order; magic_number exposes the first present.
    _MAGIC_ATTRS = (
        "_vulnerable", "_weak", "_frail", "_strength", "_power_amount",
        "_power", "_plating", "_cards", "_energy", "_energy_gain", "_heal",
        "_extra", "_increase", "_attacks", "_repeat",
    )

    @property
    def base_damage(self) -> int | None:
        """Printed per-hit attack damage before modifiers; None if the card
        deals no enemy damage (or computes it — see calc_damage)."""
        return getattr(self, "_damage", None)

    @property
    def base_hits(self) -> int:
        """How many times the attack damage is dealt (1 for single hits)."""
        return getattr(self, "_hits", 1)

    @property
    def base_block(self) -> int | None:
        """Printed block gained before modifiers; None if the card grants none."""
        return getattr(self, "_block", None)

    @property
    def base_hp_loss(self) -> int:
        """Self HP-loss drawback printed on the card (Offering, Hemokinesis)."""
        return getattr(self, "_hp_loss", 0)

    @property
    def base_gold(self) -> int | None:
        """Printed gold amount before modifiers (Debt's drain, Spoils Map's
        payout, Hand of Greed's kill bonus); None if the card has no gold
        var. Mirrors base_hp_loss's shape -- GoldVar has no home anywhere
        else in this API, and is not one of the MAGIC_ATTRS (gold is not a
        combat "magic number" any more than damage/block/hp_loss are)."""
        return getattr(self, "_gold", None)

    @property
    def magic_number(self) -> int | None:
        """The card's principal secondary number (Vulnerable stacks, cards
        drawn, Strength gained, ...); None if it has no such number."""
        for attr in self._MAGIC_ATTRS:
            value = getattr(self, attr, None)
            if value is not None:
                return value
        return None

    @property
    def energy_cost(self) -> int:
        # CardEnergyCost.GetWithModifiers short-circuits on `if (_base < 0)
        # return num;` (CardEnergyCost.cs:100-103) BEFORE any local modifier
        # is even consulted -- an unplayable card's canonical -1 (the 29
        # unplayable curse/status/quest cards, e.g. Wound.cs `base(-1, ...)`)
        # is immune to every cost modifier and is read back verbatim. This
        # must be the FIRST check: _free_this_turn / _cost_this_turn /
        # _cost_this_combat / _cost_delta_this_turn all mirror LocalCostModifier
        # state that the game either never adds (SetThisCombat/SetThisTurn's
        # own `cost != 0 || Canonical >= 0` guards) or adds inertly, since
        # GetWithModifiers would never reach it either way.
        if self._energy_cost < 0:
            return self._energy_cost
        if self._free_this_turn:
            return 0
        if self._cost_this_turn is not None:
            base = self._cost_this_turn
        elif self._cost_this_combat is not None:
            base = self._cost_this_combat
        else:
            base = self._energy_cost
        return max(0, base + self._cost_delta_this_turn)

    def costs_energy(self, hooks=None) -> bool:
        """`CardModel.CostsEnergyOrStars(includeGlobalModifiers: true)`
        (CardModel.cs:1578-1592) — `!EnergyCost.CostsX &&
        EnergyCost.GetWithModifiers(CostModifiers.All) > 0`, i.e. the cost the
        player would actually pay RIGHT NOW, GLOBAL modifiers included. (The
        star half is Regent-only and the sim has no stars.)

        `self.energy_cost` is the LOCAL half alone — CostModifiers.Local, the
        free-this-turn / cost-this-turn / cost-this-combat / per-turn-delta
        stack. The GLOBAL half is `Hook.ModifyEnergyCostInCombat`
        (CardEnergyCost.cs:116-119), which the sim dispatches as
        `modify_card_energy_cost`. A filter that reads `energy_cost` alone calls
        a card 'costing' that Corruption has already made free.
        """
        if self.energy_cost_x:
            return False
        cost = self.energy_cost
        if hooks is not None:
            cost = hooks.modify_card_energy_cost(self, cost)
        return cost > 0

    def costs_energy_before_modifiers(self) -> bool:
        """`EnergyCost.GetWithModifiers(CostModifiers.None) > 0` — the PRINTED
        cost with no modifier of either kind, which is how MummifiedHand.cs:32
        builds the candidate list it prefers."""
        return self._energy_cost > 0

    def set_cost_this_combat(self, cost: int) -> None:
        """Override this card's base cost for the rest of the combat (mirrors
        EnergyCost.SetThisCombat, e.g. the Slither enchantment's random cost)."""
        self._cost_this_combat = cost

    def reset_combat_state(self) -> None:
        """Clear per-combat card state (called by CombatState at setup, since
        a run reuses the same Card objects across combats)."""
        self._cost_this_combat = None
        self.captured_x = 0
        self.base_replay_count = 0
        # CardModel.CurrentPlayIndex — which iteration of the play-count loop
        # is resolving (CardModel.cs:1906). 0 for an ordinary single play.
        self.current_play_index = 0
        # Every per-TURN state too: the sim reuses Card objects across combats,
        # where the game builds a fresh CardModel per combat.
        self.end_of_turn_cleanup()

    def add_cost_this_turn(self, delta: int) -> None:
        """Change this card's cost until the end of the turn (mirrors
        EnergyCost.AddThisTurn, e.g. Stomp's per-attack discount)."""
        self._cost_delta_this_turn += delta

    def set_cost_this_turn(self, cost: int) -> None:
        """Override this card's cost until the end of the turn (mirrors
        EnergyCost.SetThisTurnOrUntilPlayed, e.g. Snecko Oil's randomised
        costs). The game's modifier also expires when the card is played; the
        sim only tracks the end-of-turn half, which differs solely for a card
        played and returned to hand in the same turn."""
        self._cost_this_turn = cost

    def set_free_this_turn(self) -> None:
        """Make this card cost 0 until the end of the turn (mirrors
        SetToFreeThisTurn, e.g. Infernal Blade's generated attack)."""
        self._free_this_turn = True

    def reset_turn_cost_modifiers(self) -> None:
        """CardEnergyCost.EndOfTurnCleanup (CardEnergyCost.cs:331-335) — drop
        every LocalCostModifier whose expiration includes EndOfTurn."""
        self._cost_delta_this_turn = 0
        self._free_this_turn = False
        self._cost_this_turn = None

    # ── The three single-turn card states EndOfTurnCleanup clears ─────────
    @property
    def should_retain_this_turn(self) -> bool:
        """CardModel.ShouldRetainThisTurn (CardModel.cs:590-600) — the Retain
        keyword, OR a single-turn grant that is still in its turn."""
        return self.retain or self._has_single_turn_retain

    @property
    def is_sly_this_turn(self) -> bool:
        """CardModel.IsSlyThisTurn (CardModel.cs:619-629)."""
        return self.sly or self._has_single_turn_sly

    def give_single_turn_retain(self) -> None:
        """CardModel.GiveSingleTurnRetain (CardModel.cs:1347-1350) — "Will be
        cleared at the end of the turn"."""
        self._has_single_turn_retain = True

    def give_single_turn_sly(self) -> None:
        """CardModel.GiveSingleTurnSly (CardModel.cs:1356-1359)."""
        self._has_single_turn_sly = True

    def end_of_turn_cleanup(self) -> None:
        """CardModel.EndOfTurnCleanup (CardModel.cs:1610-1623).

        Run for EVERY card in EVERY pile, twice a round: once from
        EndEnemyTurnInternal (CombatManager.cs:1254) and once from
        FlushPlayerHand (:1346).
        """
        self.exhaust_on_next_play = False
        self._has_single_turn_retain = False
        self._has_single_turn_sly = False
        self.reset_turn_cost_modifiers()

    @abstractmethod
    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None: ...

    def on_turn_end_in_hand(self, ctx: CombatCtx) -> None:
        pass

    # ── Run-level map hooks (AbstractModel map-generation callbacks) ──────
    # Cards in the deck can rewrite the freshly generated act map, exactly
    # like relics; RunState.start_act runs deck cards and relics through
    # this pipeline (mirrors Hook.ModifyGeneratedMap / *Late /
    # AfterMapGenerated / ModifyUnknownMapPointRoomTypes). Defaults are
    # no-ops so only the Spoils Map card overrides them.

    def modify_generated_map(self, run, act_map, act_index):
        """AbstractModel.ModifyGeneratedMap: replace/edit the map, early pass."""
        return act_map

    def modify_generated_map_late(self, run, act_map, act_index):
        """AbstractModel.ModifyGeneratedMapLate: second pass, after all early
        modifiers have run (e.g. read a node the early pass created)."""
        return act_map

    def after_map_generated(self, run, act_map, act_index) -> None:
        """AbstractModel.AfterMapGenerated: react once the map is final."""

    def modify_next_event(self, run, event_id):
        """`AbstractModel.ModifyNextEvent` (AbstractModel.cs:1892) — swap the
        event a "?" node is about to serve. Dispatched by `Hook.ModifyNextEvent`
        (Hook.cs:1830-1836), whose ONE call site is `ActModel.PullNextEvent`
        (ActModel.cs:437-443): EnsureNextEventIsValid, then this chain, then
        `AddVisitedEvent` on the MODIFIED event. The sim passes and returns an
        event ID where C# passes an EventModel."""
        return event_id

    def after_transformed_from(self) -> None:
        """`CardModel.AfterTransformedFrom` (CardModel.cs:1625-1627) — called on
        the card that LEFT, after the replacement is in place
        (CardCmd.cs:449). A virtual no-op in the source too; SovereignBlade.cs
        :187 is its only override in the whole game, and it is unported."""

    def after_transformed_to(self) -> None:
        """`CardModel.AfterTransformedTo` (CardModel.cs:1629-1631) — called on
        the card that ARRIVED (CardCmd.cs:450). A virtual no-op with ZERO
        overrides anywhere in the decompiled source: a pure extension point,
        carried so the transform command's tail has the shape it has."""

    # `AbstractModel.AfterCardChangedPiles(card, oldPileType, clonedBy)` is
    # deliberately NOT declared as a base no-op here — see
    # HookSystem.after_card_changed_piles. `_each` skips listeners that do not
    # define the hook, so leaving it off `Card` keeps a pile move from calling
    # one dead method per card in the piles; a card that wants it just defines
    # `after_card_changed_piles(self, card, pile, cloned_by)`.

    def modify_unknown_map_point_room_types(self, run, room_types):
        """AbstractModel.ModifyUnknownMapPointRoomTypes: restrict the room
        types a "?" node may roll into."""
        return room_types

    def after_combat_end(self, run) -> None:
        """`AbstractModel.AfterCombatEnd(CombatRoom)` as the RUN dispatches it.

        `Hook.AfterCombatEnd` walks `runState.IterateHookListeners`
        (Hook.cs:328-335), which yields the DECK as well as the relics, and it
        fires from `EndCombatInternal` (CombatManager.cs:988) on every combat
        end -- win or loss, and before `Hook.AfterCombatVictory`. The sim keeps
        the run deck separate from each combat's copy of it, so a card sitting
        in `run.deck` is exactly a card whose `Pile.Type == PileType.Deck`,
        which is the condition Guilty tests. Dispatched by
        `RunState.finish_combat`.
        """

    # ── Run-level rest-site hook (mirrors Relic.modify_rest_site_options) ──
    # A deck-resident quest card can add a rest-site option the same way a
    # relic does (Byrdonis Egg's Hatch). RunState.rest_site_options() scans
    # the deck before the relics (mirrors IterateHookListeners's order).

    def modify_rest_site_options(self, run, options: "list[RestSiteOption]") -> None:
        """AbstractModel.TryModifyRestSiteOptions: append an extra rest-site
        action (default no-op)."""

    def __repr__(self) -> str:
        suffix = "+" * self.upgrade_level if self.upgrade_level > 0 else ""
        return f"{self.name}{suffix}"
