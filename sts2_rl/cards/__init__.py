from .base import Card, CardType, CardRarity, TargetType, register_card, make_card
from .pool import (
    COLORLESS_POOL,
    CURSE_POOL,
    IRONCLAD_POOL,
    curse_pool_ids,
    pool_card_ids,
    random_curses,
    random_pool_cards,
    transform_options_in_combat,
)
from .strike import StrikeCard
from .defend import DefendCard
from .burn import BurnCard
from .wound import WoundCard
from .wither import WitherCard
from .breakthrough import BreakthroughCard
from .sweep import SweepCard
from .slimed import SlimedCard
from .dazed import DazedCard
from .infection import InfectionCard
from .beckon import BeckonCard
from .toxic import ToxicCard
from .frantic_escape import FranticEscapeCard
from .knowledge_curses import (
    DisintegrationCard,
    MindRotCard,
    SlothCard,
    WasteAwayCard,
)
from .event_cards import (
    ByrdonisEggCard,
    ByrdSwoopCard,
    PeckCard,
    ToricToughnessCard,
    UltimateStrikeCard,
    UltimateDefendCard,
    ExterminateCard,
    SquashCard,
    MetamorphosisCard,
    EnlightenmentCard,
    FeedingFrenzyCard,
    LanternKeyCard,
)
from .trash_heap_cards import (
    CaltropsCard,
    ClashCard,
    DistractionCard,
    DualWieldCard,
    EntrenchCard,
    HelloWorldCard,
    OutmaneuverCard,
    ReboundCard,
    RipAndTearCard,
    StackCard,
)
from .apotheosis import ApotheosisCard
from .apparition import ApparitionCard
from .brightest_flame import BrightestFlameCard
from .wish import WishCard
from .luminesce import LuminesceCard
from .mad_science import MadScienceCard
from .maul import MaulCard
from .whistle import WhistleCard
from .relax import RelaxCard
from .soot import SootCard
from .neows_fury import NeowsFuryCard
from .spoils_map import SpoilsMapCard

# ── Colorless pool (ColorlessCardPool.cs, single-player slice) ────────────
from .colorless_attacks import (
    BolasCard,
    DramaticEntranceCard,
    FisticuffsCard,
    FlashOfSteelCard,
    GoldAxeCard,
    HandOfGreedCard,
    JackpotCard,
    MindBlastCard,
    OmnisliceCard,
    RendCard,
    SalvoCard,
    SeekerStrikeCard,
    ThrummingHatchetCard,
    VolleyCard,
)
from .colorless_skills import (
    AlchemizeCard,
    AnointedCard,
    BeatDownCard,
    CatastropheCard,
    DarkShacklesCard,
    DiscoveryCard,
    EquilibriumCard,
    FinesseCard,
    HiddenGemCard,
    ImpatienceCard,
    JackOfAllTradesCard,
    MasterOfStrategyCard,
    PanicButtonCard,
    ProductionCard,
    ProlongCard,
    PurityCard,
    RestlessnessCard,
    ScrawlCard,
    SecretTechniqueCard,
    SecretWeaponCard,
    ShockwaveCard,
    SplashCard,
    TheBombCard,
    TheGambitCard,
    ThinkingAheadCard,
)
from .colorless_powers import (
    AutomationCard,
    CalamityCard,
    EntropyCard,
    EternalArmorCard,
    FastenCard,
    MayhemCard,
    NostalgiaCard,
    PanacheCard,
    PrepTimeCard,
    ProwessCard,
    RollingBoulderCard,
    StratagemCard,
)

# ── Ironclad attacks ──────────────────────────────────────────────────────
from .anger import AngerCard
from .ashen_strike import AshenStrikeCard
from .bash import BashCard
from .bludgeon import BludgeonCard
from .body_slam import BodySlamCard
from .break_card import BreakCard
from .bully import BullyCard
from .cinder import CinderCard
from .conflagration import ConflagrationCard
from .dismantle import DismantleCard
from .feed import FeedCard
from .fiend_fire import FiendFireCard
from .fight_me import FightMeCard
from .giant_rock import GiantRockCard
from .headbutt import HeadbuttCard
from .hemokinesis import HemokinesisCard
from .howl_from_beyond import HowlFromBeyondCard
from .iron_wave import IronWaveCard
from .mangle import MangleCard
from .molten_fist import MoltenFistCard
from .pacts_end import PactsEndCard
from .perfected_strike import PerfectedStrikeCard
from .pillage import PillageCard
from .pommel_strike import PommelStrikeCard
from .rampage import RampageCard
from .setup_strike import SetupStrikeCard
from .spite import SpiteCard
from .stomp import StompCard
from .sword_boomerang import SwordBoomerangCard
from .tear_asunder import TearAsunderCard
from .thrash import ThrashCard
from .thunderclap import ThunderclapCard
from .twin_strike import TwinStrikeCard
from .unrelenting import UnrelentingCard
from .uppercut import UppercutCard
from .whirlwind import WhirlwindCard

# ── Ironclad skills ───────────────────────────────────────────────────────
from .armaments import ArmamentsCard
from .battle_trance import BattleTranceCard
from .blood_wall import BloodWallCard
from .bloodletting import BloodlettingCard
from .brand import BrandCard
from .burning_pact import BurningPactCard
from .cascade import CascadeCard
from .colossus import ColossusCard
from .dominate import DominateCard
from .drum_of_battle import DrumOfBattleCard
from .evil_eye import EvilEyeCard
from .expect_a_fight import ExpectAFightCard
from .flame_barrier import FlameBarrierCard
from .forgotten_ritual import ForgottenRitualCard
from .havoc import HavocCard
from .impervious import ImperviousCard
from .infernal_blade import InfernalBladeCard
from .not_yet import NotYetCard
from .offering import OfferingCard
from .one_two_punch import OneTwoPunchCard
from .primal_force import PrimalForceCard
from .rage import RageCard
from .second_wind import SecondWindCard
from .shrug_it_off import ShrugItOffCard
from .stoke import StokeCard
from .taunt import TauntCard
from .tremble import TrembleCard
from .true_grit import TrueGritCard

# ── Curses ────────────────────────────────────────────────────────────────
from .ascenders_bane import AscendersBaneCard
from .bad_luck import BadLuckCard
from .clumsy import ClumsyCard
from .curse_of_the_bell import CurseOfTheBellCard
from .debt import DebtCard
from .decay import DecayCard
from .doubt import DoubtCard
from .enthralled import EnthralledCard
from .folly import FollyCard
from .greed import GreedCard
from .guilty import GuiltyCard
from .injury import InjuryCard
from .normality import NormalityCard
from .poor_sleep import PoorSleepCard
from .regret import RegretCard
from .shame import ShameCard
from .spore_mind import SporeMindCard
from .writhe import WritheCard

# ── Ironclad powers ───────────────────────────────────────────────────────
from .aggression import AggressionCard
from .barricade_card import BarricadeCard
from .corruption import CorruptionCard
from .crimson_mantle import CrimsonMantleCard
from .cruelty import CrueltyCard
from .dark_embrace_card import DarkEmbraceCard
from .demon_form_card import DemonFormCard
from .feel_no_pain_card import FeelNoPainCard
from .hellraiser import HellraiserCard
from .inferno import InfernoCard
from .inflame import InflameCard
from .juggernaut import JuggernautCard
from .juggling import JugglingCard
from .pyre import PyreCard
from .rupture_card import RuptureCard
from .stampede import StampedeCard
from .stone_armor import StoneArmorCard
from .unmovable import UnmovableCard
from .vicious import ViciousCard

__all__ = [
    "Card",
    "CardType",
    "CardRarity",
    "TargetType",
    "register_card",
    "make_card",
    "IRONCLAD_POOL",
    "COLORLESS_POOL",
    "CURSE_POOL",
    "pool_card_ids",
    "curse_pool_ids",
    "random_pool_cards",
    "random_curses",
    "transform_options_in_combat",
    "StrikeCard",
    "DefendCard",
    "BurnCard",
    "WoundCard",
    "WitherCard",
    "BreakthroughCard",
    "SweepCard",
    "SlimedCard",
    "DazedCard",
    "InfectionCard",
    "ToxicCard",
    "FranticEscapeCard",
    "DisintegrationCard",
    "MindRotCard",
    "SlothCard",
    "WasteAwayCard",
    # Event cards
    "ByrdonisEggCard",
    "ByrdSwoopCard",
    "PeckCard",
    "ToricToughnessCard",
    "UltimateStrikeCard",
    "UltimateDefendCard",
    "ExterminateCard",
    "SquashCard",
    "MetamorphosisCard",
    "EnlightenmentCard",
    "FeedingFrenzyCard",
    "LanternKeyCard",
    "CaltropsCard",
    "ClashCard",
    "DistractionCard",
    "DualWieldCard",
    "EntrenchCard",
    "HelloWorldCard",
    "OutmaneuverCard",
    "ReboundCard",
    "RipAndTearCard",
    "StackCard",
    "MadScienceCard",
    "SpoilsMapCard",
    # Colorless attacks
    "BolasCard",
    "DramaticEntranceCard",
    "FisticuffsCard",
    "FlashOfSteelCard",
    "GoldAxeCard",
    "HandOfGreedCard",
    "JackpotCard",
    "MindBlastCard",
    "OmnisliceCard",
    "RendCard",
    "SalvoCard",
    "SeekerStrikeCard",
    "ThrummingHatchetCard",
    "VolleyCard",
    # Colorless skills
    "AlchemizeCard",
    "AnointedCard",
    "BeatDownCard",
    "CatastropheCard",
    "DarkShacklesCard",
    "DiscoveryCard",
    "EquilibriumCard",
    "FinesseCard",
    "HiddenGemCard",
    "ImpatienceCard",
    "JackOfAllTradesCard",
    "MasterOfStrategyCard",
    "PanicButtonCard",
    "ProductionCard",
    "ProlongCard",
    "PurityCard",
    "RestlessnessCard",
    "ScrawlCard",
    "SecretTechniqueCard",
    "SecretWeaponCard",
    "ShockwaveCard",
    "SplashCard",
    "TheBombCard",
    "TheGambitCard",
    "ThinkingAheadCard",
    # Colorless powers
    "AutomationCard",
    "CalamityCard",
    "EntropyCard",
    "EternalArmorCard",
    "FastenCard",
    "MayhemCard",
    "NostalgiaCard",
    "PanacheCard",
    "PrepTimeCard",
    "ProwessCard",
    "RollingBoulderCard",
    "StratagemCard",
    # Ironclad attacks
    "AngerCard",
    "AshenStrikeCard",
    "BashCard",
    "BludgeonCard",
    "BodySlamCard",
    "BreakCard",
    "BullyCard",
    "CinderCard",
    "ConflagrationCard",
    "DismantleCard",
    "FeedCard",
    "FiendFireCard",
    "FightMeCard",
    "GiantRockCard",
    "HeadbuttCard",
    "HemokinesisCard",
    "HowlFromBeyondCard",
    "IronWaveCard",
    "MangleCard",
    "MoltenFistCard",
    "PactsEndCard",
    "PerfectedStrikeCard",
    "PillageCard",
    "PommelStrikeCard",
    "RampageCard",
    "SetupStrikeCard",
    "SpiteCard",
    "StompCard",
    "SwordBoomerangCard",
    "TearAsunderCard",
    "ThrashCard",
    "ThunderclapCard",
    "TwinStrikeCard",
    "UnrelentingCard",
    "UppercutCard",
    "WhirlwindCard",
    # Ironclad skills
    "ArmamentsCard",
    "BattleTranceCard",
    "BloodWallCard",
    "BloodlettingCard",
    "BrandCard",
    "BurningPactCard",
    "CascadeCard",
    "ColossusCard",
    "DominateCard",
    "DrumOfBattleCard",
    "EvilEyeCard",
    "ExpectAFightCard",
    "FlameBarrierCard",
    "ForgottenRitualCard",
    "HavocCard",
    "ImperviousCard",
    "InfernalBladeCard",
    "NotYetCard",
    "OfferingCard",
    "OneTwoPunchCard",
    "PrimalForceCard",
    "RageCard",
    "SecondWindCard",
    "ShrugItOffCard",
    "StokeCard",
    "TauntCard",
    "TrembleCard",
    "TrueGritCard",
    # Curses
    "AscendersBaneCard",
    "BadLuckCard",
    "ClumsyCard",
    "CurseOfTheBellCard",
    "DebtCard",
    "DecayCard",
    "DoubtCard",
    "EnthralledCard",
    "FollyCard",
    "GreedCard",
    "GuiltyCard",
    "InjuryCard",
    "NormalityCard",
    "PoorSleepCard",
    "RegretCard",
    "ShameCard",
    "SporeMindCard",
    "WritheCard",
    # Ironclad powers
    "AggressionCard",
    "BarricadeCard",
    "CorruptionCard",
    "CrimsonMantleCard",
    "CrueltyCard",
    "DarkEmbraceCard",
    "DemonFormCard",
    "FeelNoPainCard",
    "HellraiserCard",
    "InfernoCard",
    "InflameCard",
    "JuggernautCard",
    "JugglingCard",
    "PyreCard",
    "RuptureCard",
    "StampedeCard",
    "StoneArmorCard",
    "UnmovableCard",
    "ViciousCard",
]
