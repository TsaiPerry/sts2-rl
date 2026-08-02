"""SP2 Task 6: RunState carries the game's parity RNG streams.

When constructed with a string seed, RunState seats a RunRngSet (12 map/economy
streams) and a PlayerRngSet (3 per-player streams), both seeded from the seed's
deterministic hash (single-player slot 0 => player seed == run seed). Without a
string seed the streams are absent and the legacy random.Random path is
unchanged, so every pre-SP2 test keeps its exact draw sequence."""
from __future__ import annotations

import random

from sts2_rl.rng import PlayerRngSet, RunRngSet, deterministic_hash_code
from sts2_rl.run import RunState

SEED = "89U21BV1TZ"
SEED_HASH = 2221240958  # deterministic_hash_code("89U21BV1TZ") & 0xFFFFFFFF


def test_string_seed_seats_parity_streams():
    run = RunState(string_seed=SEED)
    assert isinstance(run.rng_set, RunRngSet)
    assert isinstance(run.player_rng, PlayerRngSet)
    # Single-player slot 0: both sets share the run seed.
    assert run.rng_set.seed == SEED_HASH
    assert run.player_rng.seed == SEED_HASH
    assert run.string_seed == SEED
    assert deterministic_hash_code(SEED) & 0xFFFFFFFF == SEED_HASH


def test_no_string_seed_leaves_streams_absent():
    # Legacy construction path (the whole existing suite) gets no parity
    # streams and keeps its random.Random exactly as before.
    run = RunState(rng=random.Random(0))
    assert run.rng_set is None
    assert run.player_rng is None
    assert run.string_seed is None


def test_string_seed_does_not_disturb_legacy_rng():
    # Seating the parity streams must consume none of the legacy rng's draws,
    # so two runs built from equal random.Random states — one with a string
    # seed, one without — leave those RNGs at the same position.
    #
    # The merged relic grab bag is no longer the probe for this: a parity run
    # re-seats it from the UpFront-shuffled per-rarity deques (so pulls are a
    # deterministic function of the seed instead of an unseeded shuffle), while
    # the legacy run keeps its own random.Random order. The legacy shuffle
    # still runs in both, which is what this asserts.
    a, b = random.Random(1234), random.Random(1234)
    RunState(rng=a, string_seed=SEED)
    RunState(rng=b)
    assert a.random() == b.random()
    assert a.getstate() == b.getstate()


def test_string_seed_seats_the_grab_bag_from_the_parity_deques():
    # With parity streams the pull bag is the concatenation of the player
    # grab bag's per-rarity deques, so `pull_relic_from_front` scanning it for
    # the rolled rarity IS RelicGrabBag.PullFromFront — and the same seed always
    # yields the same relics (an unseeded shuffle made every replay differ).
    first = RunState(string_seed=SEED)
    second = RunState(string_seed=SEED)
    assert first.relic_grab_bag == second.relic_grab_bag
    assert first.relic_grab_bag
    expected = [
        rid.split(".", 1)[-1].lower()
        for deque in first.player_relic_bag.values()
        for rid in deque
    ]
    # Every bag entry is a ported relic, in deque order (unported ids dropped).
    assert first.relic_grab_bag == [r for r in expected
                                    if r in set(first.relic_grab_bag)]


# ═════════════════════════════════════════════════════════════════════════
# GAP-QUEUE 47 — relic/_off_stream_draw: a relic that names a stream in C#
# must ADVANCE that stream's counter, not the legacy shared random.Random.
#
# These are counter assertions only. Out-of-combat draws on the unseeded
# shared rng make gameplay deltas nondeterministic, so gameplay output is
# never the pin here (see docs: "conformance replay determinism").
# ═════════════════════════════════════════════════════════════════════════

def _parity_run():
    from sts2_rl.rng import RunRngType
    run = RunState(string_seed=SEED)
    assert run.rng_set.counters()[RunRngType.NICHE] == 0
    return run


def test_astrolabe_rolls_its_transforms_on_niche():
    # Astrolabe.cs:25 — CreateRandomCardForTransform(..., RunState.Rng.Niche),
    # once per transformed card (CardsVar(3)).
    run = _parity_run()
    run.add_relic("astrolabe")
    assert run.rng_set.niche.counter == 3


def test_new_leaf_rolls_its_transform_on_niche():
    # NewLeaf.cs:27 — CardCmd.TransformToRandom(item, RunState.Rng.Niche).
    run = _parity_run()
    run.add_relic("new_leaf")
    assert run.rng_set.niche.counter == 1


def test_sere_talon_draws_its_curses_on_niche():
    # SereTalon.cs:39-45 — Rng.Niche.NextItem(availableCurses) per curse,
    # removed after each pick (Curses = 2).
    run = _parity_run()
    run.add_relic("sere_talon")
    assert run.rng_set.niche.counter == 2


def test_war_hammer_shuffles_on_niche():
    # WarHammer.cs:26 — StableShuffle(RunState.Rng.Niche) over the upgradable
    # deck cards: one UnstableShuffle == len-1 draws.
    from sts2_rl.rooms import RoomType
    run = _parity_run()
    run.add_relic("war_hammer")
    upgradable = len([c for c in run.deck if c.is_upgradable])
    for relic in run.relics:
        relic.after_combat_end(run, RoomType.ELITE)
    assert run.rng_set.niche.counter == upgradable - 1


def test_sand_castle_shuffles_on_niche():
    # SandCastle.cs:24 — StableShuffle(RunState.Rng.Niche).
    run = _parity_run()
    upgradable = len([c for c in run.deck if c.is_upgradable])
    run.add_relic("sand_castle")
    assert run.rng_set.niche.counter == upgradable - 1


def test_war_paint_and_whetstone_shuffle_on_niche():
    from sts2_rl.cards import CardType
    for rid, card_type in (("war_paint", CardType.SKILL),
                           ("whetstone", CardType.ATTACK)):
        run = _parity_run()
        n = len([c for c in run.deck
                 if c.card_type == card_type and c.is_upgradable])
        run.add_relic(rid)
        assert run.rng_set.niche.counter == n - 1, rid


def test_lost_coffer_draws_its_potion_on_the_rewards_stream():
    # LostCoffer.cs:21 — PotionReward with no rng override, so
    # PotionFactory.CreateRandomPotionOutOfCombat spends TWO PlayerRng.Rewards
    # draws (NextFloat for the rarity band, NextItem inside it). The card half
    # is the control.
    from sts2_rl.rewards import RarityOddsType, create_reward_cards

    control = RunState(string_seed=SEED)
    create_reward_cards(control, RarityOddsType.REGULAR, mutate_pity=False)
    card_half = control.player_rng.rewards.counter

    run = RunState(string_seed=SEED)
    run.add_relic("lost_coffer")
    assert run.player_rng.rewards.counter == card_half + 2


def test_toolbox_generates_its_options_on_combat_card_generation():
    # Toolbox.cs:27 — GetDistinctForCombat(..., Rng.CombatCardGeneration).
    from sts2_rl.combat import CombatState
    from sts2_rl.relics import make_relic
    from sts2_rl.rng import RunRngSet

    rs = RunRngSet(SEED)
    before = rs.combat_card_generation.counter
    CombatState(rng_set=rs, relics=[make_relic("toolbox")])
    assert rs.combat_card_generation.counter > before


def test_choices_paradox_generates_its_options_on_combat_card_generation():
    # ChoicesParadox.cs:34 — GetDistinctForCombat(..., CombatCardGeneration).
    from sts2_rl.combat import CombatState
    from sts2_rl.relics import make_relic
    from sts2_rl.rng import RunRngSet

    rs = RunRngSet(SEED)
    plain = RunRngSet(SEED)
    CombatState(rng_set=plain)
    CombatState(rng_set=rs, relics=[make_relic("choices_paradox")])
    assert (rs.combat_card_generation.counter
            > plain.combat_card_generation.counter)


def test_glass_eye_never_rolls_for_upgrade():
    # R14/R11: this test's old name and its docstring were wrong. GlassEye.cs:29
    # calls `ForNonCombatWithUniformOdds(...).WithFlags(NoRarityModification)`,
    # and `ForNonCombatWithUniformOdds` ITSELF ORs `NoUpgradeRoll`
    # (CardCreationOptions.cs:160-163) — a fact hidden behind the one visible
    # `.WithFlags(...)` call. Under that flag `CardFactory.CreateForReward`
    # skips `RollForUpgrade` wholesale, INCLUDING its `rng.NextFloat()` draw
    # (CardFactory.cs:98-102/290). Five 3-card screens, uniform odds (no
    # rarity roll either) = 15 NextItem picks only, never 30.
    run = RunState(string_seed=SEED)
    assert run.player_rng.rewards.counter == 0
    run.add_relic("glass_eye")
    assert run.player_rng.rewards.counter == 15
