"""Wave B02 ascension-gated monster stats: FatGremlin, FlailKnight, Flyconid,
Fogmog, FossilStalker, FrogKnight, FuzzyWurmCrawler, GasBomb. Sources:
FatGremlin.cs, FlailKnight.cs, Flyconid.cs, Fogmog.cs, FossilStalker.cs,
FrogKnight.cs, FuzzyWurmCrawler.cs, GasBomb.cs."""
from __future__ import annotations

import random

from sts2_rl.combat import CombatState
from sts2_rl.monsters.base import Encounter


# ---------------------------------------------------------------------------
# FatGremlin -- ToughEnemies HP only (14/18 vs 13/17 base)
# ---------------------------------------------------------------------------

def _fat_gremlin_combat(asc: int, seed: int = 0):
    from sts2_rl.monsters.underdocks.gremlin_merc import FatGremlin
    enc = Encounter(id="test_fat_gremlin", monster_classes=[FatGremlin])
    return CombatState(rng=random.Random(seed), encounter=enc, ascension=asc)


def test_fat_gremlin_tough_hp():
    seen_asc8 = set()
    for seed in range(30):
        hp0 = _fat_gremlin_combat(0, seed).enemy.max_hp
        hp7 = _fat_gremlin_combat(7, seed).enemy.max_hp
        hp8 = _fat_gremlin_combat(8, seed).enemy.max_hp
        assert 13 <= hp0 <= 17
        assert 13 <= hp7 <= 17  # asc 7 < ToughEnemies(8)
        assert 14 <= hp8 <= 18
        seen_asc8.add(hp8)
    assert seen_asc8 & {17, 18}  # values unreachable under the asc-0 range


# ---------------------------------------------------------------------------
# FlailKnight -- ToughEnemies HP (108 vs 101) + DeadlyEnemies FLAIL/RAM dmg
# ---------------------------------------------------------------------------

def _flail_knight_combat(asc: int):
    from sts2_rl.monsters.hive.flail_knight import FlailKnight
    enc = Encounter(id="test_flail_knight", monster_classes=[FlailKnight])
    return CombatState(rng=random.Random(0), encounter=enc, ascension=asc)


def test_flail_knight_tough_hp():
    cs0 = _flail_knight_combat(0)
    cs7 = _flail_knight_combat(7)
    cs8 = _flail_knight_combat(8)
    assert cs0.enemy.max_hp == 101
    assert cs7.enemy.max_hp == 101  # asc 7 < ToughEnemies(8)
    assert cs8.enemy.max_hp == 108


def test_flail_knight_deadly_ram_damage():
    # FlailKnight.cs:40 RamDamage -- GetValueIfAscension(DeadlyEnemies, 17, 15).
    # FlailKnight starts on RAM_MOVE (initial state), so the telegraphed intent
    # is checked directly against RamDamage at both asc levels.
    cs0 = _flail_knight_combat(0)
    cs9 = _flail_knight_combat(9)
    assert cs0.enemy.machine.current.intent.damage == 15
    assert cs9.enemy.machine.current.intent.damage == 17

    hp_before0 = cs0.player.hp
    cs0.end_turn()
    assert cs0.player.hp == hp_before0 - 15

    hp_before9 = cs9.player.hp
    cs9.end_turn()
    assert cs9.player.hp == hp_before9 - 17


# ---------------------------------------------------------------------------
# Flyconid -- ToughEnemies HP (51/53 vs 47/49) + DeadlyEnemies SMASH/SPORE dmg
# ---------------------------------------------------------------------------

def _flyconid_combat(asc: int, seed: int = 0):
    from sts2_rl.monsters.overgrowth.flyconid import Flyconid
    enc = Encounter(id="test_flyconid", monster_classes=[Flyconid])
    return CombatState(rng=random.Random(seed), encounter=enc, ascension=asc)


def test_flyconid_tough_hp():
    seen_asc8 = set()
    for seed in range(30):
        hp0 = _flyconid_combat(0, seed).enemy.max_hp
        hp7 = _flyconid_combat(7, seed).enemy.max_hp
        hp8 = _flyconid_combat(8, seed).enemy.max_hp
        assert 47 <= hp0 <= 49
        assert 47 <= hp7 <= 49  # asc 7 < ToughEnemies(8)
        assert 51 <= hp8 <= 53
        seen_asc8.add(hp8)
    assert seen_asc8 & {52, 53}  # values unreachable under the asc-0 range


def test_flyconid_deadly_smash_damage():
    # Flyconid.cs:24 SmashDamage -- GetValueIfAscension(DeadlyEnemies, 12, 11).
    # Loop seeds until the INITIAL RandomBranchState rolls SMASH (one of the
    # two equal-weight choices), then compare current_intent's damage at
    # asc 0 vs asc 9 for the SAME move key.
    found = False
    for seed in range(20):
        cs0 = _flyconid_combat(0, seed)
        if cs0.enemy._move_key != "SMASH":
            continue
        cs9 = _flyconid_combat(9, seed)
        assert cs9.enemy._move_key == "SMASH"
        assert cs0.enemy.current_intent.damage == 11
        assert cs9.enemy.current_intent.damage == 12
        found = True
        break
    assert found, "no seed in range(20) rolled SMASH as the initial move"


# ---------------------------------------------------------------------------
# Fogmog -- ToughEnemies HP (78 vs 74) + DeadlyEnemies SWIPE/HEADBUTT dmg
# ---------------------------------------------------------------------------

def _fogmog_combat(asc: int):
    from sts2_rl.monsters.overgrowth.fogmog import Fogmog
    enc = Encounter(id="test_fogmog", monster_classes=[Fogmog])
    return CombatState(rng=random.Random(0), encounter=enc, ascension=asc)


def test_fogmog_tough_hp():
    cs0 = _fogmog_combat(0)
    cs7 = _fogmog_combat(7)
    cs8 = _fogmog_combat(8)
    assert cs0.enemy.max_hp == 74
    assert cs7.enemy.max_hp == 74  # asc 7 < ToughEnemies(8)
    assert cs8.enemy.max_hp == 78


def test_fogmog_deadly_swipe_damage():
    # Fogmog.cs:32 SwipeDamage -- GetValueIfAscension(DeadlyEnemies, 9, 8).
    # ILLUSION_MOVE (turn 1, a summon) is always followed by SWIPE_MOVE
    # (turn 2), so end_turn twice and compare the resulting player HP.
    cs0 = _fogmog_combat(0)
    cs9 = _fogmog_combat(9)
    cs0.end_turn()  # ILLUSION_MOVE: no damage
    cs9.end_turn()
    assert cs0.enemy.machine.current.intent.damage == 8
    assert cs9.enemy.machine.current.intent.damage == 9

    hp_before0 = cs0.player.hp
    cs0.end_turn()  # SWIPE_MOVE
    assert cs0.player.hp == hp_before0 - 8

    hp_before9 = cs9.player.hp
    cs9.end_turn()
    assert cs9.player.hp == hp_before9 - 9


# ---------------------------------------------------------------------------
# FossilStalker -- ToughEnemies HP (54/56 vs 51/53) + DeadlyEnemies
# TACKLE/LATCH/LASH dmg
# ---------------------------------------------------------------------------

def _fossil_stalker_combat(asc: int, seed: int = 0):
    from sts2_rl.monsters.underdocks.fossil_stalker import FossilStalker
    enc = Encounter(id="test_fossil_stalker", monster_classes=[FossilStalker])
    return CombatState(rng=random.Random(seed), encounter=enc, ascension=asc)


def test_fossil_stalker_tough_hp():
    seen_asc8 = set()
    for seed in range(20):
        hp7 = _fossil_stalker_combat(7, seed).enemy.max_hp
        hp8 = _fossil_stalker_combat(8, seed).enemy.max_hp
        assert 51 <= hp7 <= 53  # asc 7 < ToughEnemies(8)
        assert 54 <= hp8 <= 56
        seen_asc8.add(hp8)
    assert seen_asc8 & {55, 56}  # values unreachable under the asc-0 range


def test_fossil_stalker_deadly_latch_damage():
    # FossilStalker.cs:35 LatchDamage -- GetValueIfAscension(DeadlyEnemies,
    # 14, 12). LATCH_MOVE is the starting move.
    cs0 = _fossil_stalker_combat(0)
    cs9 = _fossil_stalker_combat(9)
    assert cs0.enemy.machine.current.intent.damage == 12
    assert cs9.enemy.machine.current.intent.damage == 14


# ---------------------------------------------------------------------------
# FrogKnight -- ToughEnemies HP (199 vs 191) + DeadlyEnemies TONGUE_LASH dmg
# ---------------------------------------------------------------------------

def _frog_knight_combat(asc: int):
    from sts2_rl.monsters.glory.frog_knight import FrogKnight
    enc = Encounter(id="test_frog_knight", monster_classes=[FrogKnight])
    return CombatState(rng=random.Random(0), encounter=enc, ascension=asc)


def test_frog_knight_tough_hp():
    cs7 = _frog_knight_combat(7)
    cs8 = _frog_knight_combat(8)
    assert cs7.enemy.max_hp == 191  # asc 7 < ToughEnemies(8)
    assert cs8.enemy.max_hp == 199


def test_frog_knight_deadly_tongue_lash_damage():
    # FrogKnight.cs:39 TongueLashDamage -- GetValueIfAscension(DeadlyEnemies,
    # 14, 13). TONGUE_LASH is the starting move.
    cs0 = _frog_knight_combat(0)
    cs9 = _frog_knight_combat(9)
    assert cs0.enemy.machine.current.intent.damage == 13
    assert cs9.enemy.machine.current.intent.damage == 14


# ---------------------------------------------------------------------------
# FuzzyWurmCrawler -- ToughEnemies HP (58/59 vs 55/57) + DeadlyEnemies
# ACID_GOOP dmg
# ---------------------------------------------------------------------------

def _fuzzy_wurm_combat(asc: int, seed: int = 0):
    from sts2_rl.monsters.fuzzy_wurm_crawler import FuzzyWurmCrawler
    enc = Encounter(id="test_fuzzy_wurm", monster_classes=[FuzzyWurmCrawler])
    return CombatState(rng=random.Random(seed), encounter=enc, ascension=asc)


def test_fuzzy_wurm_crawler_tough_hp():
    seen_asc8 = set()
    for seed in range(20):
        hp7 = _fuzzy_wurm_combat(7, seed).enemy.max_hp
        hp8 = _fuzzy_wurm_combat(8, seed).enemy.max_hp
        assert 55 <= hp7 <= 57  # asc 7 < ToughEnemies(8)
        assert 58 <= hp8 <= 59
        seen_asc8.add(hp8)
    assert seen_asc8  # sanity: the loop ran


def test_fuzzy_wurm_crawler_deadly_damage():
    # FuzzyWurmCrawler.cs:33 AcidGoopDamage -- GetValueIfAscension(
    # DeadlyEnemies, 6, 4). FIRST_ACID_GOOP is the starting move.
    cs0 = _fuzzy_wurm_combat(0)
    cs9 = _fuzzy_wurm_combat(9)
    assert cs0.enemy.current_intent.damage == 4
    assert cs9.enemy.current_intent.damage == 6


# ---------------------------------------------------------------------------
# GasBomb -- ToughEnemies HP (8 vs 7) + DeadlyEnemies EXPLODE dmg
# ---------------------------------------------------------------------------

def _gas_bomb_combat(asc: int):
    from sts2_rl.monsters.underdocks.living_fog import GasBomb
    enc = Encounter(id="test_gas_bomb", monster_classes=[GasBomb])
    return CombatState(rng=random.Random(0), encounter=enc, ascension=asc)


def test_gas_bomb_tough_hp():
    cs7 = _gas_bomb_combat(7)
    cs8 = _gas_bomb_combat(8)
    assert cs7.enemy.max_hp == 7  # asc 7 < ToughEnemies(8)
    assert cs8.enemy.max_hp == 8


def test_gas_bomb_deadly_explode_damage():
    # GasBomb.cs:32 ExplodeDamage -- GetValueIfAscension(DeadlyEnemies, 9, 8).
    # EXPLODE_MOVE is the sole move.
    cs0 = _gas_bomb_combat(0)
    cs9 = _gas_bomb_combat(9)
    assert cs0.enemy.machine.current.intent.damage == 8
    assert cs9.enemy.machine.current.intent.damage == 9


# ═════════════════════════════════════════════════════════════════════════
# GlobeHead (GlobeHead.cs) — ToughEnemies HP; DeadlyEnemies damage x3
# ═════════════════════════════════════════════════════════════════════════

def _globe_head_combat(asc: int, seed: int = 0):
    from sts2_rl.monsters.glory.globe_head import GlobeHead
    enc = Encounter(id="test_globe_head", monster_classes=[GlobeHead])
    return CombatState(rng=random.Random(seed), encounter=enc, ascension=asc)


def test_globe_head_tough_hp():
    # GlobeHead.cs:29-31 -- MinInitialHp/MaxInitialHp == 158/148 (equal min/max).
    assert _globe_head_combat(0).enemy.max_hp == 148
    assert _globe_head_combat(7).enemy.max_hp == 148  # asc 7 < ToughEnemies(8)
    assert _globe_head_combat(8).enemy.max_hp == 158


def test_globe_head_deadly_damage():
    # GlobeHead.cs:35 ShockingSlapDamage -- GetValueIfAscension(DeadlyEnemies,
    # 14, 13). SHOCKING_SLAP is the initial move, so its intent is checked
    # directly.
    cs0, cs9 = _globe_head_combat(0), _globe_head_combat(9)
    assert cs0.enemy.machine.current.intent.damage == 13
    assert cs9.enemy.machine.current.intent.damage == 14


# ═════════════════════════════════════════════════════════════════════════
# GremlinMerc (GremlinMerc.cs) — ToughEnemies HP AND ToughEnemies damage
# (source gates the damage sites on ToughEnemies, not DeadlyEnemies)
# ═════════════════════════════════════════════════════════════════════════

def _gremlin_merc_combat(asc: int, seed: int = 0):
    from sts2_rl.monsters.underdocks.gremlin_merc import GremlinMerc
    enc = Encounter(id="test_gremlin_merc", monster_classes=[GremlinMerc])
    return CombatState(rng=random.Random(seed), encounter=enc, ascension=asc)


def test_gremlin_merc_tough_hp():
    # GremlinMerc.cs:28-30 -- MinInitialHp/MaxInitialHp: ToughEnemies(51,53)
    # vs base(47,49).
    seen_asc8 = set()
    for seed in range(30):
        hp0 = _gremlin_merc_combat(0, seed).enemy.max_hp
        hp7 = _gremlin_merc_combat(7, seed).enemy.max_hp
        hp8 = _gremlin_merc_combat(8, seed).enemy.max_hp
        assert 47 <= hp0 <= 49
        assert 47 <= hp7 <= 49  # asc 7 < ToughEnemies(8)
        assert 51 <= hp8 <= 53
        seen_asc8.add(hp8)
    assert seen_asc8 & {51, 52, 53}


def test_gremlin_merc_tough_damage():
    # GremlinMerc.cs:36 GimmeDamage reads ToughEnemies(8, 7) -- NOT
    # DeadlyEnemies, per source. Checked at asc 8 vs asc 0. GIMME_MOVE is the
    # initial move.
    cs0, cs8 = _gremlin_merc_combat(0), _gremlin_merc_combat(8)
    assert cs0.enemy.machine.current.intent.damage == 7
    assert cs8.enemy.machine.current.intent.damage == 8


# ═════════════════════════════════════════════════════════════════════════
# Guardbot (Guardbot.cs, sim: monsters/glory/fabricator.py) — ToughEnemies HP
# only; no Deadly-gated value on Guardbot itself.
# ═════════════════════════════════════════════════════════════════════════

def _guardbot_combat(asc: int, seed: int = 0):
    from sts2_rl.monsters.glory.fabricator import Guardbot
    enc = Encounter(id="test_guardbot", monster_classes=[Guardbot])
    return CombatState(rng=random.Random(seed), encounter=enc, ascension=asc)


def test_guardbot_tough_hp():
    # Guardbot.cs:21-23 -- MinInitialHp/MaxInitialHp: ToughEnemies(17,21)
    # vs base(16,20).
    seen_asc8 = set()
    for seed in range(30):
        hp0 = _guardbot_combat(0, seed).enemy.max_hp
        hp7 = _guardbot_combat(7, seed).enemy.max_hp
        hp8 = _guardbot_combat(8, seed).enemy.max_hp
        assert 16 <= hp0 <= 20
        assert 16 <= hp7 <= 20  # asc 7 < ToughEnemies(8)
        assert 17 <= hp8 <= 21
        seen_asc8.add(hp8)
    assert seen_asc8 & {17, 18, 19, 20, 21}


# ═════════════════════════════════════════════════════════════════════════
# HauntedShip (HauntedShip.cs) — ToughEnemies HP; DeadlyEnemies damage x2
# ═════════════════════════════════════════════════════════════════════════

def _haunted_ship_combat(asc: int, seed: int = 0):
    from sts2_rl.monsters.underdocks.haunted_ship import HauntedShip
    enc = Encounter(id="test_haunted_ship", monster_classes=[HauntedShip])
    return CombatState(rng=random.Random(seed), encounter=enc, ascension=asc)


def test_haunted_ship_tough_hp():
    # HauntedShip.cs:25-27 -- MinInitialHp/MaxInitialHp == 67/63 (equal min/max).
    assert _haunted_ship_combat(0).enemy.max_hp == 63
    assert _haunted_ship_combat(7).enemy.max_hp == 63  # asc 7 < ToughEnemies(8)
    assert _haunted_ship_combat(8).enemy.max_hp == 67


def test_haunted_ship_deadly_damage():
    # HauntedShip.cs:31 SwipeDamage reads DeadlyEnemies(14, 13). The opening
    # move is HAUNT_MOVE (no damage); its follow-up is SWIPE_MOVE, whose
    # intent is checked directly off the machine's state graph.
    cs0, cs9 = _haunted_ship_combat(0), _haunted_ship_combat(9)
    assert cs0.enemy.machine.current.follow_up.intent.damage == 13
    assert cs9.enemy.machine.current.follow_up.intent.damage == 14
