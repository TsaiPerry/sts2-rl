"""Act 2 "Hive" enemies (the parallel Act 2 — the game picks Hive or
Underdocks). Full encounter list: Bowlbugs, Chompers, Decimillipede,
Entomancer, Exoskeletons, Hunter Killer, Infested Prisms, Kaiser Crab,
Knowledge Demon, Louse Progenitor, Mytes, Ovicopter, Slumbering Beetle,
Spiny Toad, The Insatiable, The Obscura, Thieving Hopper, Tunneler."""
from ..base import Encounter, Intent, Monster, MoveType

from .bowlbugs import (
    BowlbugEgg,
    BowlbugNectar,
    BowlbugRock,
    BowlbugSilk,
    BOWLBUGS_NORMAL,
    BOWLBUGS_WEAK,
)
from .chomper import Chomper, CHOMPERS_NORMAL
from .decimillipede import (
    DecimillipedeSegment,
    DecimillipedeSegmentBack,
    DecimillipedeSegmentFront,
    DecimillipedeSegmentMiddle,
    DECIMILLIPEDE_ELITE,
)
from .entomancer import Entomancer, ENTOMANCER_ELITE
from .flail_knight import (
    FlailKnight,
    MysteriousKnight,
    MYSTERIOUS_KNIGHT_EVENT_ENCOUNTER,
)
from .exoskeleton import Exoskeleton, EXOSKELETONS_NORMAL, EXOSKELETONS_WEAK
from .hunter_killer import HunterKiller, HUNTER_KILLER_NORMAL
from .infested_prism import InfestedPrism, INFESTED_PRISMS_ELITE
from .kaiser_crab import Crusher, Rocket, KAISER_CRAB_BOSS
from .knowledge_demon import KnowledgeDemon, KNOWLEDGE_DEMON_BOSS
from .louse_progenitor import LouseProgenitor, LOUSE_PROGENITOR_NORMAL
from .myte import Myte, MYTES_NORMAL
from .ovicopter import Ovicopter, ToughEgg, OVICOPTER_NORMAL
from .slumbering_beetle import SlumberingBeetle, SLUMBERING_BEETLE_NORMAL
from .spiny_toad import SpinyToad, SPINY_TOAD_NORMAL
from .the_insatiable import TheInsatiable, THE_INSATIABLE_BOSS
from .the_obscura import Parafright, TheObscura, THE_OBSCURA_NORMAL
from .thieving_hopper import ThievingHopper, THIEVING_HOPPER_WEAK
from .tunneler import Tunneler, TUNNELER_WEAK

ENCOUNTERS: dict[str, Encounter] = {
    # Weak
    "bowlbugs_weak":            BOWLBUGS_WEAK,
    "exoskeletons_weak":        EXOSKELETONS_WEAK,
    "thieving_hopper":          THIEVING_HOPPER_WEAK,
    "tunneler":                 TUNNELER_WEAK,
    # Normal
    "bowlbugs_normal":          BOWLBUGS_NORMAL,
    "chompers":                 CHOMPERS_NORMAL,
    "exoskeletons_normal":      EXOSKELETONS_NORMAL,
    "hunter_killer":            HUNTER_KILLER_NORMAL,
    "louse_progenitor":         LOUSE_PROGENITOR_NORMAL,
    "mytes":                    MYTES_NORMAL,
    "ovicopter":                OVICOPTER_NORMAL,
    "slumbering_beetle":        SLUMBERING_BEETLE_NORMAL,
    "spiny_toad":               SPINY_TOAD_NORMAL,
    "the_obscura":              THE_OBSCURA_NORMAL,
    # Elite
    "decimillipede":            DECIMILLIPEDE_ELITE,
    "entomancer":               ENTOMANCER_ELITE,
    "infested_prisms":          INFESTED_PRISMS_ELITE,
    # Boss
    "kaiser_crab":              KAISER_CRAB_BOSS,
    "knowledge_demon":          KNOWLEDGE_DEMON_BOSS,
    "the_insatiable":           THE_INSATIABLE_BOSS,
}

__all__ = [
    # base re-exports
    "MoveType", "Intent", "Monster", "Encounter",
    # monsters
    "BowlbugEgg", "BowlbugNectar", "BowlbugRock", "BowlbugSilk", "Chomper",
    "Crusher", "DecimillipedeSegment", "DecimillipedeSegmentBack",
    "DecimillipedeSegmentFront", "DecimillipedeSegmentMiddle", "Entomancer",
    "Exoskeleton", "FlailKnight", "MysteriousKnight", "HunterKiller",
    "InfestedPrism", "KnowledgeDemon",
    "LouseProgenitor", "Myte", "Ovicopter", "Parafright", "Rocket",
    "SlumberingBeetle", "SpinyToad", "TheInsatiable", "TheObscura",
    "ThievingHopper", "ToughEgg", "Tunneler",
    # encounters
    "BOWLBUGS_NORMAL", "BOWLBUGS_WEAK", "CHOMPERS_NORMAL",
    "DECIMILLIPEDE_ELITE", "ENTOMANCER_ELITE", "EXOSKELETONS_NORMAL",
    "EXOSKELETONS_WEAK", "HUNTER_KILLER_NORMAL", "INFESTED_PRISMS_ELITE",
    "KAISER_CRAB_BOSS", "KNOWLEDGE_DEMON_BOSS", "LOUSE_PROGENITOR_NORMAL",
    "MYTES_NORMAL", "OVICOPTER_NORMAL", "SLUMBERING_BEETLE_NORMAL",
    "SPINY_TOAD_NORMAL", "THE_INSATIABLE_BOSS", "THE_OBSCURA_NORMAL",
    "THIEVING_HOPPER_WEAK", "TUNNELER_WEAK",
    "MYSTERIOUS_KNIGHT_EVENT_ENCOUNTER",
    "ENCOUNTERS",
]
