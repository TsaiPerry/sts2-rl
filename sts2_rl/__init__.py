"""sts2_rl — a pure-Python simulation of Slay the Spire 2 combat.

The engine models one STS2 combat with full fidelity to the decompiled game
(see CLAUDE.md and MODULES.md), wrapped in a Gymnasium environment for training
RL agents. This module re-exports the public API — the combat driver, the
command and hook layers, and the commonly used creatures/cards/potions/powers.
The full power and potion catalogues are reachable via the `ALL_POWERS` /
`ALL_POTIONS` registries; `make_card` / `make_potion` build any card/potion by
id.
"""
from __future__ import annotations

# ── Environment ──────────────────────────────────────────────────────────────
from .env import STS2CombatEnv
from .full_env import STS2FullCombatEnv

# ── Combat engine ────────────────────────────────────────────────────────────
from .combat import CombatState, CombatCtx
from .creatures import Creature
from .player import PlayerCombatState
from .hooks import HookSystem

# ── Command layer ────────────────────────────────────────────────────────────
from .cmds import DamageCmd, BlockCmd, StrengthCmd, PowerCmd, CreatureCmd
from .valueprops import ValueProp, DamageProps

# ── Previews (pure reads of the numbers the game displays) ───────────────────
from .previews import (
    AttackPreview,
    preview_incoming_damage,
    preview_total_incoming,
    card_base_damage,
    preview_card_damage,
    preview_card_block,
    preview_card_energy_cost,
)

# ── Card selection (deterministic CombatState.card_selector heuristic) ───────
from .selectors import scripted_card_selector

# ── Evaluation (OBS_PLAN Phase 4: lethal probes, win-rate evals, ablation) ───
from .full_env import AblatedObsEnv, numeric_obs_indices, obs_segments, obs_slices
from .probes import (
    PROBES,
    Probe,
    ProbeResult,
    lethal_oracle,
    probe_accuracy,
    probe_dummy,
    run_probe,
    run_probes,
)
from .evaluation import (
    WinRateReport,
    ablation_transform,
    evaluate_probes,
    evaluate_win_rate,
    masked_random_policy,
    model_policy,
    probe_summary,
)

# ── Cards ────────────────────────────────────────────────────────────────────
from .cards import (
    Card,
    StrikeCard,
    DefendCard,
    SweepCard,
    BreakthroughCard,
    make_card,
    register_card,
)

# ── Monsters ─────────────────────────────────────────────────────────────────
from .monsters import (
    Monster,
    Intent,
    Encounter,
    FuzzyWurmCrawler,
    FUZZY_WURM_ENCOUNTER,
    Nibbit,
    NIBBITS_NORMAL,
    NIBBITS_WEAK,
)
from .monsters.base import MoveType
from .monsters.state_machine import (
    MachineMonster,
    MonsterMoveStateMachine,
    MonsterState,
    MoveState,
    MoveRepeatType,
    RandomBranchState,
    ConditionalBranchState,
)

# ── Relics (see ALL_RELICS / make_relic for the full catalogue) ──────────────
from .relics import (
    Relic,
    RelicRarity,
    make_relic,
    register_relic,
    ALL_RELICS,
)

# ── Potions (see ALL_POTIONS / make_potion for the full catalogue) ───────────
from .potions import (
    Potion,
    FirePotion,
    BlockPotion,
    StrengthPotion,
    BloodPotion,
    WeakPotion,
    make_potion,
    ALL_POTIONS,
)

# ── Powers (see ALL_POWERS for the full catalogue) ───────────────────────────
from .powers import (
    Power,
    PowerType,
    # Buffs
    StrengthPower,
    DexterityPower,
    BarricadePower,
    RegenPower,
    RitualPower,
    DemonFormPower,
    FeelNoPainPower,
    DarkEmbracePower,
    EnragePower,
    RupturePower,
    CurlUpPower,
    ArtifactPower,
    ThornsPower,
    IntangiblePower,
    # Debuffs
    VulnerablePower,
    WeakPower,
    FrailPower,
    PoisonPower,
    ALL_POWERS,
)

# ── Run layer, map, enchantments & events ────────────────────────────────────
from .run import RunState, ironclad_starting_deck
from .actmap import (
    ActMapConfig,
    AscensionLevel,
    MapPoint,
    MapPointType,
    MapPointTypeCounts,
    StandardMap,
    SpoilsActMap,
    golden_path_map,
    ACT_MAP_CONFIGS,
    OVERGROWTH_MAP,
    UNDERDOCKS_MAP,
    HIVE_MAP,
    GLORY_MAP,
)
from .rooms import (
    ActRooms,
    RoomResolution,
    RoomSet,
    RoomType,
    UnknownOdds,
    act_rooms,
)
from .shop import (
    MerchantInventory,
    MerchantCardEntry,
    MerchantRelicEntry,
    MerchantPotionEntry,
    MerchantCardRemovalEntry,
)
from .enchantments import (
    Enchantment,
    SownEnchantment,
    SlitherEnchantment,
    make_enchantment,
    ALL_ENCHANTMENTS,
)
from .events import (
    Event,
    EventOption,
    make_event,
    register_event,
    allowed_events,
    ALL_EVENTS,
    OVERGROWTH_EVENTS,
    UNDERDOCKS_EVENTS,
    HIVE_EVENTS,
    GLORY_EVENTS,
)

__all__ = [
    # Environment
    "STS2CombatEnv",
    "STS2FullCombatEnv",
    # Combat engine
    "CombatState",
    "CombatCtx",
    "Creature",
    "PlayerCombatState",
    "HookSystem",
    # Command layer
    "DamageCmd",
    "BlockCmd",
    "StrengthCmd",
    "PowerCmd",
    "CreatureCmd",
    "ValueProp",
    "DamageProps",
    # Previews
    "AttackPreview",
    "preview_incoming_damage",
    "preview_total_incoming",
    "card_base_damage",
    "preview_card_damage",
    "preview_card_block",
    "preview_card_energy_cost",
    # Card selection
    "scripted_card_selector",
    # Evaluation
    "AblatedObsEnv",
    "numeric_obs_indices",
    "obs_segments",
    "obs_slices",
    "PROBES",
    "Probe",
    "ProbeResult",
    "lethal_oracle",
    "probe_accuracy",
    "probe_dummy",
    "run_probe",
    "run_probes",
    "WinRateReport",
    "ablation_transform",
    "evaluate_probes",
    "evaluate_win_rate",
    "masked_random_policy",
    "model_policy",
    "probe_summary",
    # Cards
    "Card",
    "StrikeCard",
    "DefendCard",
    "SweepCard",
    "BreakthroughCard",
    "make_card",
    "register_card",
    # Monsters
    "Monster",
    "Intent",
    "Encounter",
    "MoveType",
    "FuzzyWurmCrawler",
    "FUZZY_WURM_ENCOUNTER",
    "Nibbit",
    "NIBBITS_NORMAL",
    "NIBBITS_WEAK",
    "MachineMonster",
    "MonsterMoveStateMachine",
    "MonsterState",
    "MoveState",
    "MoveRepeatType",
    "RandomBranchState",
    "ConditionalBranchState",
    # Relics
    "Relic",
    "RelicRarity",
    "make_relic",
    "register_relic",
    "ALL_RELICS",
    # Potions
    "Potion",
    "FirePotion",
    "BlockPotion",
    "StrengthPotion",
    "BloodPotion",
    "WeakPotion",
    "make_potion",
    "ALL_POTIONS",
    # Powers
    "Power",
    "PowerType",
    "StrengthPower",
    "DexterityPower",
    "BarricadePower",
    "RegenPower",
    "RitualPower",
    "DemonFormPower",
    "FeelNoPainPower",
    "DarkEmbracePower",
    "EnragePower",
    "RupturePower",
    "CurlUpPower",
    "ArtifactPower",
    "ThornsPower",
    "IntangiblePower",
    "VulnerablePower",
    "WeakPower",
    "FrailPower",
    "PoisonPower",
    "ALL_POWERS",
    # Run layer, map, enchantments & events
    "RunState",
    "ironclad_starting_deck",
    "ActMapConfig",
    "AscensionLevel",
    "MapPoint",
    "MapPointType",
    "MapPointTypeCounts",
    "StandardMap",
    "SpoilsActMap",
    "golden_path_map",
    "ACT_MAP_CONFIGS",
    "OVERGROWTH_MAP",
    "UNDERDOCKS_MAP",
    "HIVE_MAP",
    "GLORY_MAP",
    "ActRooms",
    "RoomResolution",
    "RoomSet",
    "RoomType",
    "UnknownOdds",
    "act_rooms",
    "MerchantInventory",
    "MerchantCardEntry",
    "MerchantRelicEntry",
    "MerchantPotionEntry",
    "MerchantCardRemovalEntry",
    "Enchantment",
    "SownEnchantment",
    "SlitherEnchantment",
    "make_enchantment",
    "ALL_ENCHANTMENTS",
    "Event",
    "EventOption",
    "make_event",
    "register_event",
    "allowed_events",
    "ALL_EVENTS",
    "OVERGROWTH_EVENTS",
    "UNDERDOCKS_EVENTS",
    "HIVE_EVENTS",
    "GLORY_EVENTS",
]
