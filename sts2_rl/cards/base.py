from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..afflictions import Affliction
    from ..combat import CombatCtx


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


class Card(ABC):
    id: str
    name: str
    card_type: CardType
    rarity: CardRarity
    target_type: TargetType = TargetType.ANY_ENEMY
    is_playable: bool = True
    is_ethereal: bool = False
    has_turn_end_in_hand_effect: bool = False
    is_unpowered: bool = False
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
        # Cost override lasting the rest of the combat (mirrors
        # EnergyCost.SetThisCombat, used by the Slither enchantment); cleared
        # by reset_combat_state at combat setup.
        self._cost_this_combat: int | None = None
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
        base = self._energy_cost if self._cost_this_combat is None else self._cost_this_combat
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
        self.reset_turn_cost_modifiers()

    def add_cost_this_turn(self, delta: int) -> None:
        """Change this card's cost until the end of the turn (mirrors
        EnergyCost.AddThisTurn, e.g. Stomp's per-attack discount)."""
        self._cost_delta_this_turn += delta

    def set_free_this_turn(self) -> None:
        """Make this card cost 0 until the end of the turn (mirrors
        SetToFreeThisTurn, e.g. Infernal Blade's generated attack)."""
        self._free_this_turn = True

    def reset_turn_cost_modifiers(self) -> None:
        """Clear per-turn cost modifiers (called at player turn start)."""
        self._cost_delta_this_turn = 0
        self._free_this_turn = False

    @abstractmethod
    def on_play(self, ctx: CombatCtx, target_idx: int | None = None) -> None: ...

    def on_turn_end_in_hand(self, ctx: CombatCtx) -> None:
        pass

    def __repr__(self) -> str:
        suffix = "+" * self.upgrade_level if self.upgrade_level > 0 else ""
        return f"{self.name}{suffix}"
