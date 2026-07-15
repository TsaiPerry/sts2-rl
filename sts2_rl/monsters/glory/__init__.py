"""Act 3 "Glory" enemies (Glory.cs). Full encounter list: Devoted Sculptor,
Scrolls of Biting, Turret Operator, Axebots, Construct Menagerie, Fabricator,
Frog Knight, Globe Head, Owl Magistrate, Slimed Berserker, The Lost & Forgotten,
Knights, Mecha Knight, Soul Nexus, Aeonglass, Queen, Test Subject — plus the
Battle Friend training dummies of the Battleworn Dummy event."""
from ..base import Encounter, Intent, Monster, MoveType

from .aeonglass import Aeonglass, AEONGLASS_BOSS
from .axebot import Axebot, AXEBOTS_NORMAL
from .battle_friend import (
    BattleFriendV1,
    BattleFriendV2,
    BattleFriendV3,
    BATTLEWORN_DUMMY_SETTING_1,
    BATTLEWORN_DUMMY_SETTING_2,
    BATTLEWORN_DUMMY_SETTING_3,
)
from .construct_menagerie import CONSTRUCT_MENAGERIE_NORMAL
from .devoted_sculptor import DevotedSculptor, DEVOTED_SCULPTOR_WEAK
from .fabricator import (
    Fabricator,
    Guardbot,
    Noisebot,
    Stabbot,
    Zapbot,
    FABRICATOR_NORMAL,
)
from .frog_knight import FrogKnight, FROG_KNIGHT_NORMAL
from .globe_head import GlobeHead, GLOBE_HEAD_NORMAL
from .knights import MagiKnight, SpectralKnight, KNIGHTS_ELITE
from .mecha_knight import MechaKnight, MECHA_KNIGHT_ELITE
from .owl_magistrate import OwlMagistrate, OWL_MAGISTRATE_NORMAL
from .queen import Queen, TorchHeadAmalgam, QUEEN_BOSS
from .scroll_of_biting import (
    ScrollOfBiting,
    SCROLLS_OF_BITING_NORMAL,
    SCROLLS_OF_BITING_WEAK,
)
from .slimed_berserker import SlimedBerserker, SLIMED_BERSERKER_NORMAL
from .soul_nexus import SoulNexus, SOUL_NEXUS_ELITE
from .test_subject import TestSubject, TEST_SUBJECT_BOSS
from .the_lost_and_forgotten import (
    TheForgotten,
    TheLost,
    THE_LOST_AND_FORGOTTEN_NORMAL,
)
from .turret_operator import LivingShield, TurretOperator, TURRET_OPERATOR_WEAK

# The Knights elite reuses the Flail Knight (implemented for the Hive act's
# Lantern Key event) and the Construct Menagerie reuses the Act-1/Act-2
# constructs.
from ..hive.flail_knight import FlailKnight
from ..overgrowth.cubex_construct import CubexConstruct
from ..underdocks.punch_construct import PunchConstruct

ENCOUNTERS: dict[str, Encounter] = {
    # Weak
    "devoted_sculptor":         DEVOTED_SCULPTOR_WEAK,
    "scrolls_of_biting_weak":   SCROLLS_OF_BITING_WEAK,
    "turret_operator":          TURRET_OPERATOR_WEAK,
    # Normal
    "axebots":                  AXEBOTS_NORMAL,
    "construct_menagerie":      CONSTRUCT_MENAGERIE_NORMAL,
    "fabricator":               FABRICATOR_NORMAL,
    "frog_knight":              FROG_KNIGHT_NORMAL,
    "globe_head":               GLOBE_HEAD_NORMAL,
    "owl_magistrate":           OWL_MAGISTRATE_NORMAL,
    "scrolls_of_biting_normal": SCROLLS_OF_BITING_NORMAL,
    "slimed_berserker":         SLIMED_BERSERKER_NORMAL,
    "the_lost_and_forgotten":   THE_LOST_AND_FORGOTTEN_NORMAL,
    # Elite
    "knights":                  KNIGHTS_ELITE,
    "mecha_knight":             MECHA_KNIGHT_ELITE,
    "soul_nexus":               SOUL_NEXUS_ELITE,
    # Boss
    "aeonglass":                AEONGLASS_BOSS,
    "queen":                    QUEEN_BOSS,
    "test_subject":             TEST_SUBJECT_BOSS,
}

__all__ = [
    "MoveType", "Intent", "Monster", "Encounter",
    # monsters
    "Aeonglass", "Axebot", "CubexConstruct", "DevotedSculptor", "Fabricator",
    "FlailKnight", "FrogKnight", "GlobeHead", "Guardbot", "LivingShield",
    "MagiKnight", "MechaKnight", "Noisebot", "OwlMagistrate", "PunchConstruct",
    "Queen", "ScrollOfBiting", "SlimedBerserker", "SoulNexus", "SpectralKnight",
    "Stabbot", "TestSubject", "TheForgotten", "TheLost", "TorchHeadAmalgam",
    "TurretOperator", "Zapbot",
    "BattleFriendV1", "BattleFriendV2", "BattleFriendV3",
    # encounters
    "AEONGLASS_BOSS", "AXEBOTS_NORMAL", "CONSTRUCT_MENAGERIE_NORMAL",
    "DEVOTED_SCULPTOR_WEAK", "FABRICATOR_NORMAL", "FROG_KNIGHT_NORMAL",
    "GLOBE_HEAD_NORMAL", "KNIGHTS_ELITE", "MECHA_KNIGHT_ELITE",
    "OWL_MAGISTRATE_NORMAL", "QUEEN_BOSS", "SCROLLS_OF_BITING_NORMAL",
    "SCROLLS_OF_BITING_WEAK", "SLIMED_BERSERKER_NORMAL", "SOUL_NEXUS_ELITE",
    "TEST_SUBJECT_BOSS", "THE_LOST_AND_FORGOTTEN_NORMAL", "TURRET_OPERATOR_WEAK",
    "BATTLEWORN_DUMMY_SETTING_1", "BATTLEWORN_DUMMY_SETTING_2",
    "BATTLEWORN_DUMMY_SETTING_3",
    "ENCOUNTERS",
]
