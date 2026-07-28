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

    Clones only exist in combat -- CreateClone throws for a card outside a
    combat pile (CardModel.cs:2170-2173). Run-level copies go through
    ICardScope.CloneCard instead (relics/paels_growth.py, run.py's per-combat
    deck copy)."""
    clone = type(card)()
    for _ in range(card.upgrade_level):
        clone.upgrade()
    if card.enchantment is not None:
        card.enchantment.clone_preserving_mutability().attach(clone)
    if card.affliction is not None:
        affliction = type(card.affliction)(card.affliction.amount)
        affliction.card = clone
        clone.affliction = affliction
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
    # (mirrors CardKeyword.Retain / ShouldRetainThisTurn).
    retain: bool = False
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
        # Per-turn cost modifiers, cleared at the start of each player turn
        # (mirror EnergyCost.AddThisTurn and SetToFreeThisTurn).
        self._cost_delta_this_turn: int = 0
        self._free_this_turn: bool = False
        # Absolute cost override lasting until the end of the turn (mirrors
        # EnergyCost.SetThisTurnOrUntilPlayed, used by Snecko Oil's cost
        # randomisation); cleared by reset_turn_cost_modifiers.
        self._cost_this_turn: int | None = None
        # Cost override lasting the rest of the combat (mirrors
        # EnergyCost.SetThisCombat, used by the Slither enchantment); cleared
        # by reset_combat_state at combat setup.
        self._cost_this_combat: int | None = None
        # Extra plays granted for the rest of the combat (mirrors
        # CardModel.BaseReplayCount, raised by Hidden Gem); seeds the play
        # count alongside the enchantment replay hooks (Spiral/Glam).
        self.base_replay_count: int = 0
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

    def downgrade(self) -> None:
        """Mirrors CardCmd.Downgrade: drop one upgrade level. A run reuses the
        same Card object, so rather than track per-upgrade deltas we rebuild the
        printed numbers from base (_init_vars) and re-apply the upgrades up to
        the new level — the same re-derive-from-canonical approach the game
        uses. No-op at level 0.

        Cards whose _on_upgrade toggles a keyword flag (Innate/Exhaust/...) must
        also initialise that flag in _init_vars so the rebuild is exact."""
        if self.upgrade_level <= 0:
            return
        target = self.upgrade_level - 1
        self.upgrade_level = 0
        self._init_vars()
        for _ in range(target):
            self.upgrade()
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
        "_vulnerable", "_weak", "_strength", "_power_amount", "_power",
        "_plating", "_cards", "_energy", "_energy_gain", "_heal", "_extra",
        "_increase", "_attacks", "_repeat",
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
        if self._free_this_turn:
            return 0
        if self._cost_this_turn is not None:
            base = self._cost_this_turn
        elif self._cost_this_combat is not None:
            base = self._cost_this_combat
        else:
            base = self._energy_cost
        return max(0, base + self._cost_delta_this_turn)

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
        self.reset_turn_cost_modifiers()

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
        """Clear per-turn cost modifiers (called at player turn start)."""
        self._cost_delta_this_turn = 0
        self._free_this_turn = False
        self._cost_this_turn = None

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

    def modify_unknown_map_point_room_types(self, run, room_types):
        """AbstractModel.ModifyUnknownMapPointRoomTypes: restrict the room
        types a "?" node may roll into."""
        return room_types

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
