"""Wave b05 ascension spot tests: Queen, Rocket, ScrollOfBiting, Seapunk,
SewerClam, ShrinkerBeetle, SkulkingColony, SlimedBerserker,
SlitheringStrangler, SludgeSpinner, SlumberingBeetle, SnappingJaxfruit."""
import random

from sts2_rl.combat import CombatState
from sts2_rl.monsters.base import Encounter


def _combat(cls, asc: int, seed: int = 0, **kwargs):
    enc = Encounter(id=f"test_{cls.__name__.lower()}", monster_classes=[cls])
    return CombatState(rng=random.Random(seed), encounter=enc, ascension=asc)


# ---------------------------------------------------------------------- Queen
def test_queen_tough_hp():
    from sts2_rl.monsters.glory.queen import Queen
    cs0 = _combat(Queen, 0)
    cs7 = _combat(Queen, 7)
    cs8 = _combat(Queen, 8)
    assert cs0.enemy.max_hp == 400
    assert cs7.enemy.max_hp == 400
    assert cs8.enemy.max_hp == 419


def test_queen_deadly_execution_damage():
    from sts2_rl.monsters.glory.queen import Queen
    cs0 = _combat(Queen, 0)
    cs9 = _combat(Queen, 9)
    assert cs0.enemy._execution_dmg() == 15
    assert cs9.enemy._execution_dmg() == 18


# --------------------------------------------------------------------- Rocket
def test_rocket_tough_hp():
    from sts2_rl.monsters.hive.kaiser_crab import Rocket
    cs0 = _combat(Rocket, 0)
    cs7 = _combat(Rocket, 7)
    cs8 = _combat(Rocket, 8)
    assert cs0.enemy.max_hp == 199
    assert cs7.enemy.max_hp == 199
    assert cs8.enemy.max_hp == 209


def test_rocket_deadly_laser_damage():
    from sts2_rl.monsters.hive.kaiser_crab import Rocket
    cs0 = _combat(Rocket, 0)
    cs9 = _combat(Rocket, 9)
    assert cs0.enemy._laser_dmg() == 31
    assert cs9.enemy._laser_dmg() == 35


# --------------------------------------------------------------- ScrollOfBiting
def test_scroll_of_biting_tough_hp():
    from sts2_rl.monsters.glory.scroll_of_biting import ScrollOfBiting
    seen_asc8 = set()
    for seed in range(30):
        hp0 = _combat(ScrollOfBiting, 0, seed).enemy.max_hp
        hp7 = _combat(ScrollOfBiting, 7, seed).enemy.max_hp
        hp8 = _combat(ScrollOfBiting, 8, seed).enemy.max_hp
        assert 30 <= hp0 <= 37
        assert 30 <= hp7 <= 37
        assert 33 <= hp8 <= 39
        seen_asc8.add(hp8)
    assert seen_asc8 & {38, 39}


def test_scroll_of_biting_deadly_chomp_damage():
    from sts2_rl.monsters.glory.scroll_of_biting import ScrollOfBiting
    cs0 = _combat(ScrollOfBiting, 0)
    cs9 = _combat(ScrollOfBiting, 9)
    assert cs0.enemy._chomp_dmg() == 14
    assert cs9.enemy._chomp_dmg() == 16


# -------------------------------------------------------------------- Seapunk
def test_seapunk_tough_hp():
    from sts2_rl.monsters.underdocks.seapunk import Seapunk
    seen_asc8 = set()
    for seed in range(30):
        hp0 = _combat(Seapunk, 0, seed).enemy.max_hp
        hp7 = _combat(Seapunk, 7, seed).enemy.max_hp
        hp8 = _combat(Seapunk, 8, seed).enemy.max_hp
        assert 44 <= hp0 <= 46
        assert 44 <= hp7 <= 46
        assert 47 <= hp8 <= 49
        seen_asc8.add(hp8)
    assert seen_asc8 & {48, 49}


def test_seapunk_deadly_sea_kick_damage():
    from sts2_rl.monsters.underdocks.seapunk import Seapunk
    cs0 = _combat(Seapunk, 0)
    cs9 = _combat(Seapunk, 9)
    assert cs0.enemy._sea_kick_dmg() == 11
    assert cs9.enemy._sea_kick_dmg() == 13


# ------------------------------------------------------------------ SewerClam
def test_sewer_clam_tough_hp():
    from sts2_rl.monsters.underdocks.sewer_clam import SewerClam
    cs0 = _combat(SewerClam, 0)
    cs7 = _combat(SewerClam, 7)
    cs8 = _combat(SewerClam, 8)
    assert cs0.enemy.max_hp == 56
    assert cs7.enemy.max_hp == 56
    assert cs8.enemy.max_hp == 58


def test_sewer_clam_deadly_jet_damage():
    from sts2_rl.monsters.underdocks.sewer_clam import SewerClam
    cs0 = _combat(SewerClam, 0)
    cs9 = _combat(SewerClam, 9)
    assert cs0.enemy._jet_dmg() == 10
    assert cs9.enemy._jet_dmg() == 11


# -------------------------------------------------------------- ShrinkerBeetle
def test_shrinker_beetle_tough_hp():
    from sts2_rl.monsters.overgrowth.shrinker_beetle import ShrinkerBeetle
    seen_asc8 = set()
    for seed in range(30):
        hp0 = _combat(ShrinkerBeetle, 0, seed).enemy.max_hp
        hp7 = _combat(ShrinkerBeetle, 7, seed).enemy.max_hp
        hp8 = _combat(ShrinkerBeetle, 8, seed).enemy.max_hp
        assert 38 <= hp0 <= 40
        assert 38 <= hp7 <= 40
        assert 40 <= hp8 <= 42
        seen_asc8.add(hp8)
    assert seen_asc8 & {41, 42}


def test_shrinker_beetle_deadly_stomp_damage():
    from sts2_rl.monsters.overgrowth.shrinker_beetle import ShrinkerBeetle
    cs0 = _combat(ShrinkerBeetle, 0)
    cs9 = _combat(ShrinkerBeetle, 9)
    assert cs0.enemy._stomp_dmg() == 13
    assert cs9.enemy._stomp_dmg() == 14


# ------------------------------------------------------------- SkulkingColony
def test_skulking_colony_tough_hp():
    from sts2_rl.monsters.underdocks.skulking_colony import SkulkingColony
    cs0 = _combat(SkulkingColony, 0)
    cs7 = _combat(SkulkingColony, 7)
    cs8 = _combat(SkulkingColony, 8)
    assert cs0.enemy.max_hp == 75
    assert cs7.enemy.max_hp == 75
    assert cs8.enemy.max_hp == 80


def test_skulking_colony_deadly_zoom_damage():
    from sts2_rl.monsters.underdocks.skulking_colony import SkulkingColony
    cs0 = _combat(SkulkingColony, 0)
    cs9 = _combat(SkulkingColony, 9)
    assert cs0.enemy._zoom_dmg() == 14
    assert cs9.enemy._zoom_dmg() == 16


# ------------------------------------------------------------- SlimedBerserker
def test_slimed_berserker_tough_hp():
    from sts2_rl.monsters.glory.slimed_berserker import SlimedBerserker
    cs0 = _combat(SlimedBerserker, 0)
    cs7 = _combat(SlimedBerserker, 7)
    cs8 = _combat(SlimedBerserker, 8)
    assert cs0.enemy.max_hp == 261
    assert cs7.enemy.max_hp == 261
    assert cs8.enemy.max_hp == 281


def test_slimed_berserker_deadly_smother_damage():
    from sts2_rl.monsters.glory.slimed_berserker import SlimedBerserker
    cs0 = _combat(SlimedBerserker, 0)
    cs9 = _combat(SlimedBerserker, 9)
    assert cs0.enemy._smother_dmg() == 30
    assert cs9.enemy._smother_dmg() == 33


# --------------------------------------------------------- SlitheringStrangler
def test_slithering_strangler_tough_hp():
    from sts2_rl.monsters.overgrowth.slithering_strangler import SlitheringStrangler
    seen_asc8 = set()
    for seed in range(30):
        hp0 = _combat(SlitheringStrangler, 0, seed).enemy.max_hp
        hp7 = _combat(SlitheringStrangler, 7, seed).enemy.max_hp
        hp8 = _combat(SlitheringStrangler, 8, seed).enemy.max_hp
        assert 53 <= hp0 <= 55
        assert 53 <= hp7 <= 55
        assert 54 <= hp8 <= 56
        seen_asc8.add(hp8)
    assert seen_asc8 & {56}


def test_slithering_strangler_deadly_lash_damage():
    from sts2_rl.monsters.overgrowth.slithering_strangler import SlitheringStrangler
    cs0 = _combat(SlitheringStrangler, 0)
    cs9 = _combat(SlitheringStrangler, 9)
    assert cs0.enemy._lash_dmg() == 12
    assert cs9.enemy._lash_dmg() == 13


# ------------------------------------------------------------------ SludgeSpinner
def test_sludge_spinner_tough_hp():
    from sts2_rl.monsters.underdocks.sludge_spinner import SludgeSpinner
    seen_asc8 = set()
    for seed in range(30):
        hp0 = _combat(SludgeSpinner, 0, seed).enemy.max_hp
        hp7 = _combat(SludgeSpinner, 7, seed).enemy.max_hp
        hp8 = _combat(SludgeSpinner, 8, seed).enemy.max_hp
        assert 37 <= hp0 <= 39
        assert 37 <= hp7 <= 39
        assert 41 <= hp8 <= 42
        seen_asc8.add(hp8)
    assert seen_asc8 & {41, 42}


def test_sludge_spinner_deadly_slam_damage():
    from sts2_rl.monsters.underdocks.sludge_spinner import SludgeSpinner
    cs0 = _combat(SludgeSpinner, 0)
    cs9 = _combat(SludgeSpinner, 9)
    assert cs0.enemy._slam_dmg() == 11
    assert cs9.enemy._slam_dmg() == 12


# ---------------------------------------------------------------- SlumberingBeetle
def test_slumbering_beetle_tough_hp():
    from sts2_rl.monsters.hive.slumbering_beetle import SlumberingBeetle
    cs0 = _combat(SlumberingBeetle, 0)
    cs7 = _combat(SlumberingBeetle, 7)
    cs8 = _combat(SlumberingBeetle, 8)
    assert cs0.enemy.max_hp == 86
    assert cs7.enemy.max_hp == 86
    assert cs8.enemy.max_hp == 89


def test_slumbering_beetle_deadly_rollout_damage():
    from sts2_rl.monsters.hive.slumbering_beetle import SlumberingBeetle
    cs0 = _combat(SlumberingBeetle, 0)
    cs9 = _combat(SlumberingBeetle, 9)
    assert cs0.enemy._rollout_dmg() == 16
    assert cs9.enemy._rollout_dmg() == 18


# --------------------------------------------------------------- SnappingJaxfruit
def test_snapping_jaxfruit_tough_hp():
    from sts2_rl.monsters.overgrowth.snapping_jaxfruit import SnappingJaxfruit
    seen_asc8 = set()
    for seed in range(30):
        hp0 = _combat(SnappingJaxfruit, 0, seed).enemy.max_hp
        hp7 = _combat(SnappingJaxfruit, 7, seed).enemy.max_hp
        hp8 = _combat(SnappingJaxfruit, 8, seed).enemy.max_hp
        assert 31 <= hp0 <= 33
        assert 31 <= hp7 <= 33
        assert 34 <= hp8 <= 36
        seen_asc8.add(hp8)
    assert seen_asc8 & {34, 35, 36}


def test_snapping_jaxfruit_deadly_damage():
    from sts2_rl.monsters.overgrowth.snapping_jaxfruit import SnappingJaxfruit
    cs0 = _combat(SnappingJaxfruit, 0)
    cs9 = _combat(SnappingJaxfruit, 9)
    assert cs0.enemy._dmg() == 3
    assert cs9.enemy._dmg() == 4
