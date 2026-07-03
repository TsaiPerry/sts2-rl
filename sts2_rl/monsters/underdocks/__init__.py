"""Act 2 "Underdocks" enemies (the act's full encounter list: Corpse Slugs,
Cultists, Fossil Stalker, Gremlin Merc, Haunted Ship, Lagavulin Matriarch,
Living Fog, Phantasmal Gardeners, Punch Construct, Seapunk, Sewer Clam,
Skulking Colony, Sludge Spinner, Soul Fysh, Terror Eel, Toadpoles,
Two-Tailed Rats, Waterfall Giant)."""
from ..base import Encounter, Intent, Monster, MoveType

from .corpse_slug import CorpseSlug, CORPSE_SLUGS_NORMAL, CORPSE_SLUGS_WEAK
from .cultists import CalcifiedCultist, DampCultist, CULTISTS_NORMAL
from .fossil_stalker import FossilStalker, FOSSIL_STALKER_NORMAL
from .gremlin_merc import (
    FatGremlin,
    GremlinMerc,
    SneakyGremlin,
    GREMLIN_MERC_NORMAL,
)
from .haunted_ship import HauntedShip, HAUNTED_SHIP_NORMAL
from .lagavulin_matriarch import LagavulinMatriarch, LAGAVULIN_MATRIARCH_BOSS
from .living_fog import GasBomb, LivingFog, LIVING_FOG_NORMAL
from .phantasmal_gardener import PhantasmalGardener, PHANTASMAL_GARDENERS_ELITE
from .punch_construct import PunchConstruct, PUNCH_CONSTRUCT_NORMAL
from .seapunk import Seapunk, SEAPUNK_NORMAL, SEAPUNK_WEAK
from .sewer_clam import SewerClam, SEWER_CLAM_NORMAL
from .skulking_colony import SkulkingColony, SKULKING_COLONY_ELITE
from .sludge_spinner import SludgeSpinner, SLUDGE_SPINNER_WEAK
from .soul_fysh import SoulFysh, SOUL_FYSH_BOSS
from .terror_eel import TerrorEel, TERROR_EEL_ELITE
from .toadpole import Toadpole, TOADPOLES_WEAK
from .two_tailed_rat import TwoTailedRat, TWO_TAILED_RATS_NORMAL
from .waterfall_giant import WaterfallGiant, WATERFALL_GIANT_BOSS

ENCOUNTERS: dict[str, Encounter] = {
    # Weak
    "corpse_slugs_weak":        CORPSE_SLUGS_WEAK,
    "seapunk_weak":             SEAPUNK_WEAK,
    "sludge_spinner":           SLUDGE_SPINNER_WEAK,
    "toadpoles":                TOADPOLES_WEAK,
    # Normal
    "corpse_slugs_normal":      CORPSE_SLUGS_NORMAL,
    "cultists":                 CULTISTS_NORMAL,
    "fossil_stalker":           FOSSIL_STALKER_NORMAL,
    "gremlin_merc":             GREMLIN_MERC_NORMAL,
    "haunted_ship":             HAUNTED_SHIP_NORMAL,
    "living_fog":               LIVING_FOG_NORMAL,
    "punch_construct":          PUNCH_CONSTRUCT_NORMAL,
    "seapunk_normal":           SEAPUNK_NORMAL,
    "sewer_clam":               SEWER_CLAM_NORMAL,
    "two_tailed_rats":          TWO_TAILED_RATS_NORMAL,
    # Elite
    "phantasmal_gardeners":     PHANTASMAL_GARDENERS_ELITE,
    "skulking_colony":          SKULKING_COLONY_ELITE,
    "terror_eel":               TERROR_EEL_ELITE,
    # Boss
    "lagavulin_matriarch":      LAGAVULIN_MATRIARCH_BOSS,
    "soul_fysh":                SOUL_FYSH_BOSS,
    "waterfall_giant":          WATERFALL_GIANT_BOSS,
}

__all__ = [
    # base re-exports
    "MoveType", "Intent", "Monster", "Encounter",
    # monsters
    "CalcifiedCultist", "CorpseSlug", "DampCultist", "FatGremlin",
    "FossilStalker", "GasBomb", "GremlinMerc", "HauntedShip",
    "LagavulinMatriarch", "LivingFog", "PhantasmalGardener",
    "PunchConstruct", "Seapunk", "SewerClam", "SkulkingColony",
    "SludgeSpinner", "SneakyGremlin", "SoulFysh", "TerrorEel", "Toadpole",
    "TwoTailedRat", "WaterfallGiant",
    # encounters
    "CORPSE_SLUGS_NORMAL", "CORPSE_SLUGS_WEAK", "CULTISTS_NORMAL",
    "FOSSIL_STALKER_NORMAL", "GREMLIN_MERC_NORMAL", "HAUNTED_SHIP_NORMAL",
    "LAGAVULIN_MATRIARCH_BOSS", "LIVING_FOG_NORMAL",
    "PHANTASMAL_GARDENERS_ELITE", "PUNCH_CONSTRUCT_NORMAL",
    "SEAPUNK_NORMAL", "SEAPUNK_WEAK", "SEWER_CLAM_NORMAL",
    "SKULKING_COLONY_ELITE", "SLUDGE_SPINNER_WEAK", "SOUL_FYSH_BOSS",
    "TERROR_EEL_ELITE", "TOADPOLES_WEAK", "TWO_TAILED_RATS_NORMAL",
    "WATERFALL_GIANT_BOSS",
    "ENCOUNTERS",
]
