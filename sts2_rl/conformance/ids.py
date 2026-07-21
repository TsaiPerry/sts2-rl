"""Sim pool key → game ModelId maps for the SP2 conformance oracles (Task 8b).

The parity oracles compare the sim's pre-rolled pools against a run.save's
per-act id lists, so we need each sim key's game id.

Events map cleanly: ``EVENT.<UPPER(key)>`` (the sim event keys are the
snake_case of the game event class, and the game id is
``EVENT.<SNAKE_UPPER(className)>`` — the two agree). Encounters do NOT: the sim
dropped the tier suffix for unambiguous normals/elites/bosses (``chompers``,
``queen``) but kept ``_weak``, and keeps ``_normal`` where a weak variant would
collide (``bowlbugs_normal``). So encounters use an explicit dict transcribed
from each act's ``GenerateAllEncounters`` (game id =
``ENCOUNTER.<SNAKE_UPPER(className)>``). Every entry is validated against
run.save by test/test_conformance_pools.py."""
from __future__ import annotations

# Overrides for any event whose class-name snake_case differs from
# ``key.upper()`` (none known today; the oracle would flag one).
EVENT_ID_OVERRIDES: dict[str, str] = {}


def event_game_id(key: str) -> str:
    return EVENT_ID_OVERRIDES.get(key, "EVENT." + key.upper())


# sim key -> "ENCOUNTER.<SNAKE_UPPER(className)>", per act's GenerateAllEncounters.
ENCOUNTER_GAME_IDS: dict[str, str] = {
    # ── Overgrowth ──────────────────────────────────────────────
    "fuzzy_wurm_weak": "ENCOUNTER.FUZZY_WURM_CRAWLER_WEAK",
    "nibbits_weak": "ENCOUNTER.NIBBITS_WEAK",
    "shrinker_beetle_weak": "ENCOUNTER.SHRINKER_BEETLE_WEAK",
    "slimes_weak": "ENCOUNTER.SLIMES_WEAK",
    "cubex_construct": "ENCOUNTER.CUBEX_CONSTRUCT_NORMAL",
    "flyconid": "ENCOUNTER.FLYCONID_NORMAL",
    "fogmog": "ENCOUNTER.FOGMOG_NORMAL",
    "inklets_normal": "ENCOUNTER.INKLETS_NORMAL",
    "mawler_normal": "ENCOUNTER.MAWLER_NORMAL",
    "nibbits_normal": "ENCOUNTER.NIBBITS_NORMAL",
    "overgrowth_crawlers": "ENCOUNTER.OVERGROWTH_CRAWLERS",
    "ruby_raiders": "ENCOUNTER.RUBY_RAIDERS_NORMAL",
    "slimes_normal": "ENCOUNTER.SLIMES_NORMAL",
    "slithering_strangler": "ENCOUNTER.SLITHERING_STRANGLER_NORMAL",
    "snapping_jaxfruit": "ENCOUNTER.SNAPPING_JAXFRUIT_NORMAL",
    "vine_shambler": "ENCOUNTER.VINE_SHAMBLER_NORMAL",
    "bygone_effigy": "ENCOUNTER.BYGONE_EFFIGY_ELITE",
    "byrdonis": "ENCOUNTER.BYRDONIS_ELITE",
    "phrog_parasite": "ENCOUNTER.PHROG_PARASITE_ELITE",
    "ceremonial_beast": "ENCOUNTER.CEREMONIAL_BEAST_BOSS",
    "the_kin": "ENCOUNTER.THE_KIN_BOSS",
    "vantom": "ENCOUNTER.VANTOM_BOSS",
    # ── Underdocks ──────────────────────────────────────────────
    "corpse_slugs_weak": "ENCOUNTER.CORPSE_SLUGS_WEAK",
    "seapunk_weak": "ENCOUNTER.SEAPUNK_WEAK",
    "sludge_spinner": "ENCOUNTER.SLUDGE_SPINNER_WEAK",
    "toadpoles": "ENCOUNTER.TOADPOLES_WEAK",
    "corpse_slugs_normal": "ENCOUNTER.CORPSE_SLUGS_NORMAL",
    "cultists": "ENCOUNTER.CULTISTS_NORMAL",
    "fossil_stalker": "ENCOUNTER.FOSSIL_STALKER_NORMAL",
    "gremlin_merc": "ENCOUNTER.GREMLIN_MERC_NORMAL",
    "haunted_ship": "ENCOUNTER.HAUNTED_SHIP_NORMAL",
    "living_fog": "ENCOUNTER.LIVING_FOG_NORMAL",
    "punch_construct": "ENCOUNTER.PUNCH_CONSTRUCT_NORMAL",
    "seapunk_normal": "ENCOUNTER.SEAPUNK_NORMAL",
    "sewer_clam": "ENCOUNTER.SEWER_CLAM_NORMAL",
    "two_tailed_rats": "ENCOUNTER.TWO_TAILED_RATS_NORMAL",
    "phantasmal_gardeners": "ENCOUNTER.PHANTASMAL_GARDENERS_ELITE",
    "skulking_colony": "ENCOUNTER.SKULKING_COLONY_ELITE",
    "terror_eel": "ENCOUNTER.TERROR_EEL_ELITE",
    "lagavulin_matriarch": "ENCOUNTER.LAGAVULIN_MATRIARCH_BOSS",
    "soul_fysh": "ENCOUNTER.SOUL_FYSH_BOSS",
    "waterfall_giant": "ENCOUNTER.WATERFALL_GIANT_BOSS",
    # ── Hive ────────────────────────────────────────────────────
    "bowlbugs_weak": "ENCOUNTER.BOWLBUGS_WEAK",
    "exoskeletons_weak": "ENCOUNTER.EXOSKELETONS_WEAK",
    "thieving_hopper": "ENCOUNTER.THIEVING_HOPPER_WEAK",
    "tunneler": "ENCOUNTER.TUNNELER_WEAK",
    "bowlbugs_normal": "ENCOUNTER.BOWLBUGS_NORMAL",
    "chompers": "ENCOUNTER.CHOMPERS_NORMAL",
    "exoskeletons_normal": "ENCOUNTER.EXOSKELETONS_NORMAL",
    "hunter_killer": "ENCOUNTER.HUNTER_KILLER_NORMAL",
    "louse_progenitor": "ENCOUNTER.LOUSE_PROGENITOR_NORMAL",
    "mytes": "ENCOUNTER.MYTES_NORMAL",
    "ovicopter": "ENCOUNTER.OVICOPTER_NORMAL",
    "slumbering_beetle": "ENCOUNTER.SLUMBERING_BEETLE_NORMAL",
    "spiny_toad": "ENCOUNTER.SPINY_TOAD_NORMAL",
    "the_obscura": "ENCOUNTER.THE_OBSCURA_NORMAL",
    "decimillipede": "ENCOUNTER.DECIMILLIPEDE_ELITE",
    "entomancer": "ENCOUNTER.ENTOMANCER_ELITE",
    "infested_prisms": "ENCOUNTER.INFESTED_PRISMS_ELITE",
    "kaiser_crab": "ENCOUNTER.KAISER_CRAB_BOSS",
    "knowledge_demon": "ENCOUNTER.KNOWLEDGE_DEMON_BOSS",
    "the_insatiable": "ENCOUNTER.THE_INSATIABLE_BOSS",
    # ── Glory ───────────────────────────────────────────────────
    "devoted_sculptor": "ENCOUNTER.DEVOTED_SCULPTOR_WEAK",
    "scrolls_of_biting_weak": "ENCOUNTER.SCROLLS_OF_BITING_WEAK",
    "turret_operator": "ENCOUNTER.TURRET_OPERATOR_WEAK",
    "axebots": "ENCOUNTER.AXEBOTS_NORMAL",
    "construct_menagerie": "ENCOUNTER.CONSTRUCT_MENAGERIE_NORMAL",
    "fabricator": "ENCOUNTER.FABRICATOR_NORMAL",
    "frog_knight": "ENCOUNTER.FROG_KNIGHT_NORMAL",
    "globe_head": "ENCOUNTER.GLOBE_HEAD_NORMAL",
    "owl_magistrate": "ENCOUNTER.OWL_MAGISTRATE_NORMAL",
    "scrolls_of_biting_normal": "ENCOUNTER.SCROLLS_OF_BITING_NORMAL",
    "slimed_berserker": "ENCOUNTER.SLIMED_BERSERKER_NORMAL",
    "the_lost_and_forgotten": "ENCOUNTER.THE_LOST_AND_FORGOTTEN_NORMAL",
    "knights": "ENCOUNTER.KNIGHTS_ELITE",
    "mecha_knight": "ENCOUNTER.MECHA_KNIGHT_ELITE",
    "soul_nexus": "ENCOUNTER.SOUL_NEXUS_ELITE",
    "aeonglass": "ENCOUNTER.AEONGLASS_BOSS",
    "queen": "ENCOUNTER.QUEEN_BOSS",
    "test_subject": "ENCOUNTER.TEST_SUBJECT_BOSS",
}


def encounter_game_id(key: str) -> str:
    return ENCOUNTER_GAME_IDS[key]


# ACT.<NAME> id (run.save / recording) -> sim act name (rooms.act_rooms key).
ACT_SIM_NAME: dict[str, str] = {
    "ACT.OVERGROWTH": "overgrowth",
    "ACT.UNDERDOCKS": "underdocks",
    "ACT.HIVE": "hive",
    "ACT.GLORY": "glory",
}
