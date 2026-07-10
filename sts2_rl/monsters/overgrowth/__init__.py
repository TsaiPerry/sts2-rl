from ..base import Encounter, Intent, Monster, MoveType

from .bygone_effigy import BygoneEffigy, BYGONE_EFFIGY_ELITE
from .byrdonis import Byrdonis, BYRDONIS_ELITE
from .ceremonial_beast import CeremonialBeast, CEREMONIAL_BEAST_BOSS
from .cubex_construct import CubexConstruct, CUBEX_CONSTRUCT_NORMAL
from .flyconid import Flyconid, FLYCONID_NORMAL
from .fogmog import EyeWithTeeth, Fogmog, FOGMOG_NORMAL
from .fuzzy_wurm_crawler import FuzzyWurmCrawler, FUZZY_WURM_ENCOUNTER
from .inklets import Inklet, INKLETS_NORMAL
from .mawler import Mawler, MAWLER_NORMAL
from .nibbit import Nibbit, NIBBITS_NORMAL, NIBBITS_WEAK
from .overgrowth_crawlers import OVERGROWTH_CRAWLERS_NORMAL
from .phrog_parasite import PhrogParasite, Wriggler, PHROG_PARASITE_ELITE
from .ruby_raiders import (
    AxeRubyRaider,
    AssassinRubyRaider,
    BruteRubyRaider,
    CrossbowRubyRaider,
    TrackerRubyRaider,
    RUBY_RAIDERS_NORMAL,
)
from .shrinker_beetle import ShrinkerBeetle, SHRINKER_BEETLE_WEAK
from .slimes import LeafSlimeS, TwigSlimeS, LeafSlimeM, TwigSlimeM, SLIMES_NORMAL, SLIMES_WEAK
from .slithering_strangler import SlitheringStrangler, SLITHERING_STRANGLER_NORMAL
from .snapping_jaxfruit import SnappingJaxfruit, SNAPPING_JAXFRUIT_NORMAL
from .the_kin import KinFollower, KinPriest, THE_KIN_BOSS
from .vantom import Vantom, VANTOM_BOSS
from .vine_shambler import VineShambler, VINE_SHAMBLER_NORMAL

ENCOUNTERS: dict[str, Encounter] = {
    # Weak
    "nibbits_weak":          NIBBITS_WEAK,
    "slimes_weak":           SLIMES_WEAK,
    "shrinker_beetle_weak":  SHRINKER_BEETLE_WEAK,
    "fuzzy_wurm_weak":       FUZZY_WURM_ENCOUNTER,
    # Normal
    "nibbits_normal":        NIBBITS_NORMAL,
    "slimes_normal":         SLIMES_NORMAL,
    "inklets_normal":        INKLETS_NORMAL,
    "mawler_normal":         MAWLER_NORMAL,
    "cubex_construct":       CUBEX_CONSTRUCT_NORMAL,
    "flyconid":              FLYCONID_NORMAL,
    "fogmog":                FOGMOG_NORMAL,
    "overgrowth_crawlers":   OVERGROWTH_CRAWLERS_NORMAL,
    "ruby_raiders":          RUBY_RAIDERS_NORMAL,
    "slithering_strangler":  SLITHERING_STRANGLER_NORMAL,
    "snapping_jaxfruit":     SNAPPING_JAXFRUIT_NORMAL,
    "vine_shambler":         VINE_SHAMBLER_NORMAL,
    # Elite
    "bygone_effigy":         BYGONE_EFFIGY_ELITE,
    "byrdonis":              BYRDONIS_ELITE,
    "phrog_parasite":        PHROG_PARASITE_ELITE,
    # Boss
    "ceremonial_beast":      CEREMONIAL_BEAST_BOSS,
    "the_kin":               THE_KIN_BOSS,
    "vantom":                VANTOM_BOSS,
}

BOSS_ENCOUNTER_KEYS: frozenset[str] = frozenset({
    "ceremonial_beast", "the_kin", "vantom",
})

__all__ = [
    # base re-exports
    "MoveType", "Intent", "Monster", "Encounter",
    # monsters
    "BygoneEffigy", "Byrdonis", "CeremonialBeast", "CubexConstruct",
    "EyeWithTeeth", "Flyconid", "Fogmog", "FuzzyWurmCrawler",
    "Inklet", "KinFollower", "KinPriest", "Mawler", "Nibbit",
    "PhrogParasite", "ShrinkerBeetle", "SlitheringStrangler", "SnappingJaxfruit",
    "LeafSlimeS", "TwigSlimeS", "LeafSlimeM", "TwigSlimeM",
    "AxeRubyRaider", "AssassinRubyRaider", "BruteRubyRaider",
    "CrossbowRubyRaider", "TrackerRubyRaider",
    "Vantom", "VineShambler", "Wriggler",
    # encounters
    "BYGONE_EFFIGY_ELITE", "BYRDONIS_ELITE", "CEREMONIAL_BEAST_BOSS",
    "CUBEX_CONSTRUCT_NORMAL", "FLYCONID_NORMAL", "FOGMOG_NORMAL",
    "FUZZY_WURM_ENCOUNTER", "INKLETS_NORMAL", "MAWLER_NORMAL",
    "NIBBITS_NORMAL", "NIBBITS_WEAK", "OVERGROWTH_CRAWLERS_NORMAL",
    "PHROG_PARASITE_ELITE", "RUBY_RAIDERS_NORMAL", "SHRINKER_BEETLE_WEAK",
    "SLIMES_NORMAL", "SLIMES_WEAK", "SLITHERING_STRANGLER_NORMAL",
    "SNAPPING_JAXFRUIT_NORMAL", "THE_KIN_BOSS", "VANTOM_BOSS",
    "VINE_SHAMBLER_NORMAL",
    "ENCOUNTERS", "BOSS_ENCOUNTER_KEYS",
]
