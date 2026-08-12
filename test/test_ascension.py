"""Ascension plumbing: cumulative level checks reach run- and combat-side code."""
import random

from sts2_rl.actmap import AscensionLevel
from sts2_rl.rewards import CardRarityOdds, RarityOddsType, roll_gold_reward
from sts2_rl.rooms import RoomType
from sts2_rl.run import RunState
from sts2_rl.shop import MerchantCardRemovalEntry


def _run(asc: int) -> RunState:
    run = RunState(rng=random.Random(0))
    run.start_act("overgrowth", ascension=asc)
    return run


# ═════════════════════════════════════════════════════════════════════════
# Level 2 — WearyTraveler (AncientEventModel.cs:180-183)
# ═════════════════════════════════════════════════════════════════════════

def test_weary_traveler_heal_reduced():
    # AncientEventModel.BeforeEventStarted: `amount = MaxHp - CurrentHp`,
    # scaled `*= 0.8m` under WearyTraveler BEFORE the heal — not a post-heal
    # truncation. Damage the run first so there's a missing-HP amount to see.
    # NeowEvent.begin() zeroes HP first (the run-start revive), which would
    # swallow the pre-existing damage — reach the shared AncientEvent.begin
    # heal directly instead, the way the ancient.py module docstring does.
    from sts2_rl.events import make_event

    run2 = RunState(rng=random.Random(0))
    run2.start_act("overgrowth", ascension=2)
    run2.hp = run2.max_hp - 10  # missing 10 HP
    from sts2_rl.events.ancient import AncientEvent
    AncientEvent.begin(make_event("neow", run2))
    assert run2.hp == run2.max_hp - 2  # healed floor(10 * 0.8) = 8

    run0 = RunState(rng=random.Random(0))
    run0.start_act("overgrowth", ascension=0)
    run0.hp = run0.max_hp - 10
    AncientEvent.begin(make_event("neow", run0))
    assert run0.hp == run0.max_hp  # full heal, no ascension


# ═════════════════════════════════════════════════════════════════════════
# Level 3 — Poverty (EncounterModel.cs:75-97, AscensionHelper.cs:12)
# ═════════════════════════════════════════════════════════════════════════

def test_poverty_scales_combat_gold():
    run3 = _run(3)
    rng = random.Random(0)
    for _ in range(100):
        assert 7 <= roll_gold_reward(rng, RoomType.MONSTER, run=run3) <= 15  # 0.75*(10,20)
        assert 26 <= roll_gold_reward(rng, RoomType.ELITE, run=run3) <= 33   # 0.75*(35,45)
        assert roll_gold_reward(rng, RoomType.BOSS, run=run3) == 75         # 0.75*100

    run2 = _run(2)
    rng2 = random.Random(0)
    for _ in range(100):
        assert 10 <= roll_gold_reward(rng2, RoomType.MONSTER, run=run2) <= 20
        assert roll_gold_reward(rng2, RoomType.BOSS, run=run2) == 100


# ═════════════════════════════════════════════════════════════════════════
# Level 4 — TightBelt (AscensionManager.cs:56-59)
# ═════════════════════════════════════════════════════════════════════════

def test_tight_belt_shrinks_belt():
    assert _run(4).max_potions == _run(3).max_potions - 1
    assert _run(4).potions == [None] * _run(4).max_potions


# ═════════════════════════════════════════════════════════════════════════
# Level 5 — AscendersBane (AscensionManager.cs:60-65)
# ═════════════════════════════════════════════════════════════════════════

def test_ascenders_bane_in_starting_deck():
    deck5 = [type(c).__name__ for c in _run(5).deck]
    assert "AscendersBaneCard" in deck5
    assert "AscendersBaneCard" not in [type(c).__name__ for c in _run(4).deck]


# ═════════════════════════════════════════════════════════════════════════
# Level 6 — Inflation (MerchantCardRemovalEntry.cs:20-22)
# ═════════════════════════════════════════════════════════════════════════

def test_inflation_raises_removal_cost():
    run6 = _run(6)
    entry6 = MerchantCardRemovalEntry(run6)
    assert entry6.cost == 100
    run6.card_shop_removals_used = 1
    entry6._calc_cost()
    assert entry6.cost == 150

    run5 = _run(5)
    entry5 = MerchantCardRemovalEntry(run5)
    assert entry5.cost == 75
    run5.card_shop_removals_used = 1
    entry5._calc_cost()
    assert entry5.cost == 100


# ═════════════════════════════════════════════════════════════════════════
# Level 7 — Scarcity (CardRarityOdds.cs:13-41, CardFactory.cs:23)
# ═════════════════════════════════════════════════════════════════════════

def test_scarcity_rarity_odds():
    from sts2_rl.rewards import upgraded_card_odd_scaling

    # Uncommon is a `const` in the source (regularUncommonOdds=0.37,
    # eliteUncommonOdds=0.4, shopUncommonOdds=0.37) — NOT ascension-gated;
    # only Rare and the (dead, display-only) Common slot swap under Scarcity.
    run7 = _run(7)
    odds7 = CardRarityOdds(random.Random(0), run=run7)
    assert odds7._odds(RarityOddsType.REGULAR) == (0.0149, 0.37, 0.615)
    assert odds7.GROWTH == 0.005
    assert odds7._odds(RarityOddsType.ELITE) == (0.05, 0.40, 0.549)
    assert odds7._odds(RarityOddsType.SHOP) == (0.045, 0.37, 0.585)
    assert upgraded_card_odd_scaling(run7) == 0.125

    run6 = _run(6)
    odds6 = CardRarityOdds(random.Random(0), run=run6)
    assert odds6._odds(RarityOddsType.REGULAR) == (0.03, 0.37, 0.60)
    assert odds6.GROWTH == 0.01
    assert upgraded_card_odd_scaling(run6) == 0.25


def test_run_stores_ascension_and_cumulative_check():
    run = _run(4)
    assert run.ascension == 4
    assert run.has_ascension(AscensionLevel.SWARMING_ELITES)      # level 1
    assert run.has_ascension(AscensionLevel.TIGHT_BELT)           # level 4
    assert not run.has_ascension(AscensionLevel.ASCENDERS_BANE)   # level 5


def test_ascension_defaults_to_zero():
    run = RunState(rng=random.Random(0))
    run.start_act("overgrowth")
    assert run.ascension == 0
    assert not run.has_ascension(AscensionLevel.SWARMING_ELITES)


def test_create_combat_sets_hooks_ascension_before_monsters_spawn():
    """Regression: CombatState.__init__ spawns monsters (encounter.
    create_monsters) DURING construction, so hooks.ascension must be seeded
    into the constructor rather than mutated on the returned CombatState —
    otherwise every ascension-gated monster stat roll would see 0."""
    from sts2_rl.monsters.base import Encounter, Monster

    seen_ascension = []

    class _RecordingMonster(Monster):
        min_hp = 10
        max_hp = 10

        def __init__(self, hooks, rng=None):
            seen_ascension.append(hooks.ascension)
            super().__init__(hooks, rng or random.Random())

        @property
        def current_intent(self):
            raise NotImplementedError

        def take_turn(self, ctx):
            raise NotImplementedError

    encounter = Encounter(id="recording_monster", monster_classes=[_RecordingMonster])

    run = RunState(rng=random.Random(0))
    run.start_act("overgrowth", ascension=8)
    combat = run.create_combat(encounter)

    assert seen_ascension == [8]
    assert combat.hooks.ascension == 8


# ═════════════════════════════════════════════════════════════════════════
# Level 8/9 — ToughEnemies/DeadlyEnemies pathfinder (Chomper.cs:28-32)
# ═════════════════════════════════════════════════════════════════════════

def _chomper_combat(asc: int):
    from sts2_rl.combat import CombatState
    from sts2_rl.monsters.base import Encounter
    from sts2_rl.monsters.hive.chomper import Chomper

    enc = Encounter(id="test_chomper", monster_classes=[Chomper])
    return CombatState(rng=random.Random(0), encounter=enc, ascension=asc)


def _chomper_combat_seeded(asc: int, seed: int):
    from sts2_rl.combat import CombatState
    from sts2_rl.monsters.base import Encounter
    from sts2_rl.monsters.hive.chomper import Chomper

    enc = Encounter(id="test_chomper", monster_classes=[Chomper])
    return CombatState(rng=random.Random(seed), encounter=enc, ascension=asc)


def test_chomper_tough_hp():
    # Chomper.cs:28-30 -- MinInitialHp/MaxInitialHp read AscensionHelper.
    # GetValueIfAscension(ToughEnemies, 63/67, 60/64). Sweep seeds so the
    # asc-8 range is actually exercised beyond the [60,64] asc-0 overlap
    # (a single seed can coincidentally land in [63,64] and pass either way).
    seen_asc8 = set()
    for seed in range(30):
        hp0 = _chomper_combat_seeded(0, seed).enemy.max_hp
        hp7 = _chomper_combat_seeded(7, seed).enemy.max_hp
        hp8 = _chomper_combat_seeded(8, seed).enemy.max_hp
        assert 60 <= hp0 <= 64
        assert 60 <= hp7 <= 64  # asc 7 < ToughEnemies(8)
        assert 63 <= hp8 <= 67
        seen_asc8.add(hp8)
    assert seen_asc8 & {65, 66, 67}  # values unreachable under the asc-0 range


def test_chomper_deadly_damage():
    # Chomper.cs:32 -- ClampDamage reads GetValueIfAscension(DeadlyEnemies,
    # 9, 8) dynamically, at both the telegraphed Intent (:58) and the
    # executed attack (:69). Check both sites, at both asc levels.
    cs0, cs9 = _chomper_combat(0), _chomper_combat(9)
    assert cs0.enemy.machine.current.intent.damage == 8
    assert cs9.enemy.machine.current.intent.damage == 9

    cs0.end_turn()  # CLAMP_MOVE is the sole starting move (single Chomper)
    assert cs0.player.hp == 80 - 8 * 2
    cs9.end_turn()
    assert cs9.player.hp == 80 - 9 * 2
