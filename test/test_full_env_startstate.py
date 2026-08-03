"""Phase-3 Task 1 — start-state pass-through for ``STS2FullCombatEnv``.

Covers the new keyword-only kwargs (``relics``, ``max_hp``, ``current_hp``,
``deck_cards``, ``potion_slots``): default-path equivalence, mutual
exclusion, fresh-instance-per-reset, and that the new state actually shows
up in the obs / action mask (not just in ``CombatState``'s internals).

Run with:  py -m pytest test/test_full_env_startstate.py -v
"""
from __future__ import annotations

import copy

import numpy as np
import pytest

from sts2_rl import STS2FullCombatEnv, make_card, make_relic
from sts2_rl.cmds import CardCmd
from sts2_rl.full_env import (
    COMBAT_POTION_BASE,
    DEFAULT_DECK_IDS,
    MAX_ENEMIES,
    RELIC_INDEX,
    combat_obs_layout,
)
from sts2_rl import full_env as full_env_module
from sts2_rl.snapshots import (
    CardSnap,
    RelicSnap,
    Snapshot,
    SnapshotDataset,
    encounter_registry,
    save_snapshots,
)


# ── 1. Default path is unchanged ─────────────────────────────────────────────


def test_default_path_calls_combatstate_with_todays_arguments(monkeypatch):
    """With none of the new kwargs, `_new_state` must hand `CombatState`
    the same *effective* deck/potions/relics/hp as before this task: the
    id-built deck, potions=None, and relics/max_hp/current_hp left at
    CombatState's own defaults (None) -- exactly what "not a parameter"
    meant before this task widened the constructor (inv-A's Q1)."""
    captured = {}
    real_combat_state = full_env_module.CombatState

    def capturing(*args, **kwargs):
        captured.update(kwargs)
        return real_combat_state(*args, **kwargs)

    monkeypatch.setattr(full_env_module, "CombatState", capturing)

    env = STS2FullCombatEnv()
    env.reset(seed=0)

    assert captured["relics"] is None
    assert captured["max_hp"] is None
    assert captured["current_hp"] is None
    assert captured["potions"] is None
    # I1 fix (phase-3): the default path must NOT pass a `max_potions`
    # value of its own -- it stays at `None` so `CombatState`/
    # `PlayerCombatState` fall back to their own default (3), exactly as
    # before this kwarg's plumbing existed.
    assert captured["max_potions"] is None
    assert [c.id for c in captured["starting_deck"]] == DEFAULT_DECK_IDS
    # None of the deck cards carry any upgrade/enchantment/affliction --
    # the id-only `make_card` path, untouched.
    assert all(c.upgrade_level == 0 for c in captured["starting_deck"])


# ── 2. Mutual exclusion ──────────────────────────────────────────────────────


def test_deck_and_deck_cards_are_mutually_exclusive():
    with pytest.raises(ValueError):
        STS2FullCombatEnv(deck=["strike"], deck_cards=[make_card("strike")])


def test_potions_and_potion_slots_are_mutually_exclusive():
    with pytest.raises(ValueError):
        STS2FullCombatEnv(potions=["block_potion"], potion_slots=[None, "block_potion"])


def test_mutual_exclusion_guard_is_a_real_check_not_a_tautology():
    """Mutation check (RED demonstration lives in the scratch script this
    test's docstring points at: scratchpad/p3-task1-mutation-check.py,
    which monkeypatches `full_env._check_mutually_exclusive` to a no-op and
    shows the two tests above stop raising). Here we additionally assert
    the *positive* half directly: passing only one of each pair is legal."""
    STS2FullCombatEnv(deck=["strike"])  # no error
    STS2FullCombatEnv(deck_cards=[make_card("strike")])  # no error
    STS2FullCombatEnv(potions=["block_potion"])  # no error
    STS2FullCombatEnv(potion_slots=[None, "block_potion"])  # no error


# ── 3. Fresh instances per reset ─────────────────────────────────────────────


def test_deck_cards_and_relics_are_copied_fresh_per_reset():
    template_card = make_card("strike")
    assert template_card.upgrade_level == 0
    template_relic = make_relic("girya")
    template_relic.times_lifted = 1

    env = STS2FullCombatEnv(
        deck_cards=[template_card] + [make_card("defend") for _ in range(4)],
        relics=[template_relic],
    )

    obs1, _ = env.reset(seed=0)
    state1 = env._state
    # Mutate episode 1's live state via real engine calls (not raw attribute
    # pokes): upgrade a deck card, tick the relic counter the same way
    # RestSiteOption's LIFT does (Girya._lift, girya.py:42-43).
    live_card = next(c for c in state1.player.all_cards if c.id == "strike")
    CardCmd.upgrade(state1.hooks, live_card)
    assert live_card.upgrade_level == 1
    live_relic = state1.relics[0]
    live_relic._lift()
    live_relic._lift()
    assert live_relic.times_lifted == 3

    # The TEMPLATES handed to the constructor must be untouched (they are
    # reused by every future reset).
    assert template_card.upgrade_level == 0
    assert template_relic.times_lifted == 1

    env.reset(seed=1)
    state2 = env._state
    assert all(c.upgrade_level == 0 for c in state2.player.all_cards if c.id == "strike")
    assert state2.relics[0].times_lifted == 1
    assert state2.relics[0] is not live_relic


# ── 4. New kwargs are live: relics / hp / potion slots ──────────────────────


def test_relics_show_up_in_relic_obs_rows():
    relic = make_relic("girya")
    relic.times_lifted = 2
    env = STS2FullCombatEnv(relics=[relic])
    obs, _ = env.reset(seed=0)

    layout = combat_obs_layout(env._card_obs)
    relic_ids_slice = layout.i_slices["player.relics.ids"]
    relic_f_slice = layout.f_slices["player.relics.f"]
    ids = obs["i"][relic_ids_slice]
    floats = obs["f"][relic_f_slice].reshape(-1, 2)

    expected_id = RELIC_INDEX["girya"] + 1  # oid() = vocab index + 1
    assert expected_id in ids
    row = int(list(ids).index(expected_id))
    assert floats[row][0] == pytest.approx(2 / 10.0)


def test_hp_and_max_hp_are_live_in_state_and_obs():
    env = STS2FullCombatEnv(max_hp=50, current_hp=30)
    obs, _ = env.reset(seed=0)
    assert env._state.player.max_hp == 50
    assert env._state.player.hp == 30

    layout = combat_obs_layout(env._card_obs)
    hp_ratio = float(obs["f"][layout.f_slices["player.hp_ratio"]][0])
    assert hp_ratio == pytest.approx(30 / 50)


def test_potion_slots_preserve_gaps_in_state_and_action_mask():
    env = STS2FullCombatEnv(potion_slots=[None, "block_potion"])
    env.reset(seed=0)
    state = env._state

    assert state.player.potions[0] is None
    assert state.player.potions[1] is not None
    assert state.player.potions[1].id == "block_potion"

    mask = env.action_masks()
    slot0_actions = mask[COMBAT_POTION_BASE + 0 * MAX_ENEMIES: COMBAT_POTION_BASE + 1 * MAX_ENEMIES]
    slot1_actions = mask[COMBAT_POTION_BASE + 1 * MAX_ENEMIES: COMBAT_POTION_BASE + 2 * MAX_ENEMIES]
    assert not slot0_actions.any(), "an empty belt slot must never be a legal potion action"
    assert slot1_actions.any(), "a filled belt slot must have at least one legal action"


def test_potion_slots_show_up_in_potions_obs_rows():
    env = STS2FullCombatEnv(potion_slots=[None, "block_potion"])
    obs, _ = env.reset(seed=0)
    layout = combat_obs_layout(env._card_obs)
    ids = obs["i"][layout.i_slices["potions.ids"]]
    assert ids[0] == 0  # PAD -- slot 0 is a genuine gap
    assert ids[1] != 0  # slot 1 is populated


# ── 4b. I1 fix (final review) — `max_potions` thread-through ────────────────
#
# `_new_state` (full_env.py) never used to pass `max_potions` to
# `CombatState`, so `PlayerCombatState.__init__` (player.py:138) clipped ANY
# rebuilt belt to its 3-slot default -- a 5-slot `potion_slots`/snapshot
# belt with a potion in slot 4 silently rebuilt to an EMPTY 3-slot belt.
# Mutation-check evidence: scratchpad/p3-task1-i1-mutation-check.py
# (monkeypatches `full_env._new_state`'s `CombatState(...)` call to drop
# `max_potions` and shows both tests below go RED).


def test_potion_slots_kwarg_five_slot_belt_survives_rebuild():
    env = STS2FullCombatEnv(
        potion_slots=[None, None, None, "block_potion", None]
    )
    env.reset(seed=0)
    state = env._state

    assert len(state.player.potions) == 5
    assert state.player.max_potions == 5
    assert state.player.potions[0] is None
    assert state.player.potions[1] is None
    assert state.player.potions[2] is None
    assert state.player.potions[3] is not None
    assert state.player.potions[3].id == "block_potion"
    assert state.player.potions[4] is None


def test_potion_slots_five_slot_belt_shows_up_in_potions_obs_rows():
    env = STS2FullCombatEnv(
        potion_slots=[None, None, None, "block_potion", None]
    )
    obs, _ = env.reset(seed=0)
    layout = combat_obs_layout(env._card_obs)
    ids = obs["i"][layout.i_slices["potions.ids"]]
    # MAX_POTION_ROWS (10) comfortably covers a 5-slot belt: no cap/
    # truncation, every slot gets its own real row.
    assert ids[0] == 0
    assert ids[1] == 0
    assert ids[2] == 0
    assert ids[3] != 0  # the populated slot
    assert ids[4] == 0


# ── 5. Phase-3 Task 3 — snapshot-mode sampling ───────────────────────────────
#
# Mutation-check evidence for this section lives in
# scratchpad/p3-task3-mutation-check.py (runtime monkeypatch only, per
# lane-rules.md -- never an edit-then-restore of a tracked file).

_ENCOUNTER_IDS = list(encounter_registry())


def _two_snapshots() -> tuple[Snapshot, Snapshot]:
    """Two snapshots that are distinguishable at the obs level: different
    hp/max_hp AND different encounters (so both a vitals-row and an
    enemy-identity assertion can tell them apart)."""
    snap_a = Snapshot(
        deck=(CardSnap("strike", False, None, None),) * 5,
        relics=(RelicSnap("girya", 2),),
        hp=30, max_hp=50,
        potion_slots=(None, "block_potion"),
        act=1, encounter_id=_ENCOUNTER_IDS[0],
        provenance={"seed": "a", "floor": 1, "episode_decisions": 0},
    )
    snap_b = Snapshot(
        deck=(CardSnap("defend", False, None, None),) * 5,
        relics=(),
        hp=9, max_hp=9,
        potion_slots=(None, None),
        act=1, encounter_id=_ENCOUNTER_IDS[1],
        provenance={"seed": "b", "floor": 2, "episode_decisions": 0},
    )
    return snap_a, snap_b


def _write_dataset(tmp_path) -> str:
    snap_a, snap_b = _two_snapshots()
    path = str(tmp_path / "snaps.jsonl")
    save_snapshots(path, [snap_a, snap_b])
    return path


def test_snapshots_kwarg_is_mutually_exclusive_with_every_start_state_kwarg():
    path = "unused-path.jsonl"  # never opened -- the ValueError fires first
    for kwargs in (
        dict(deck=["strike"]),
        dict(potions=["block_potion"]),
        dict(deck_cards=[make_card("strike")]),
        dict(relics=[make_relic("girya")]),
        dict(max_hp=10),
        dict(current_hp=10),
        dict(potion_slots=[None]),
        dict(encounter=full_env_module.DEFAULT_ENCOUNTERS[0]),
        dict(encounters=[full_env_module.DEFAULT_ENCOUNTERS[0]]),
    ):
        with pytest.raises(ValueError):
            STS2FullCombatEnv(snapshots=path, **kwargs)


def test_snapshots_kwarg_accepts_a_preloaded_dataset_or_a_path(tmp_path):
    from sts2_rl.snapshots import load_snapshots

    path = _write_dataset(tmp_path)
    dataset = load_snapshots(path)

    env_path = STS2FullCombatEnv(snapshots=path)
    env_dataset = STS2FullCombatEnv(snapshots=dataset)
    o_path, _ = env_path.reset(seed=0)
    o_dataset, _ = env_dataset.reset(seed=0)
    assert np.array_equal(o_path["f"], o_dataset["f"])
    assert np.array_equal(o_path["i"], o_dataset["i"])


def test_snapshot_sampling_reads_from_the_dedicated_snap_rng_not_self_rng(
    tmp_path, monkeypatch
):
    """Positive proof of Locked decision 3: the sample draw comes from
    `env._snap_rng`, never `env._rng`. This is the assertion the mutation
    check (a) in the scratch script flips to RED by aliasing the two."""
    path = _write_dataset(tmp_path)
    captured: dict = {}
    real_sample = SnapshotDataset.sample

    def spy_sample(self, rng):
        captured["rng"] = rng
        return real_sample(self, rng)

    monkeypatch.setattr(SnapshotDataset, "sample", spy_sample)

    env = STS2FullCombatEnv(snapshots=path)
    env.reset(seed=0)

    assert captured["rng"] is env._snap_rng
    assert captured["rng"] is not env._rng


def test_non_snapshot_reset_never_touches_snapshot_sampling(monkeypatch):
    """Non-snapshot path is unaffected by the new machinery's mere
    existence: `SnapshotDataset.sample` must never be called when no
    `snapshots=` kwarg was given, for any number of resets."""

    def boom(self, rng):
        raise AssertionError(
            "SnapshotDataset.sample must not be called in non-snapshot mode"
        )

    monkeypatch.setattr(SnapshotDataset, "sample", boom)

    env = STS2FullCombatEnv()
    env.reset(seed=0)   # must not raise
    env.reset(seed=1)
    env.reset()          # unseeded reset too


def test_snapshot_mode_same_seed_same_dataset_is_deterministic(tmp_path):
    path = _write_dataset(tmp_path)

    env1 = STS2FullCombatEnv(snapshots=path)
    obs1, _ = env1.reset(seed=7)
    env2 = STS2FullCombatEnv(snapshots=path)
    obs2, _ = env2.reset(seed=7)

    assert np.array_equal(obs1["f"], obs2["f"])
    assert np.array_equal(obs1["i"], obs2["i"])


def test_snapshot_mode_samples_both_snapshots_across_resets(tmp_path):
    path = _write_dataset(tmp_path)
    env = STS2FullCombatEnv(snapshots=path)

    seen_max_hp: set[int] = set()
    for seed in range(30):
        env.reset(seed=seed)
        seen_max_hp.add(env._state.player.max_hp)
        if len(seen_max_hp) == 2:
            break

    assert seen_max_hp == {50, 9}, (
        f"expected both snapshots' distinct max_hp (50, 9) to be sampled "
        f"within 30 seeded resets, got {seen_max_hp}"
    )


def test_snapshot_mode_builds_combat_from_the_snapshot_facts(tmp_path):
    path = _write_dataset(tmp_path)
    env = STS2FullCombatEnv(snapshots=path)

    seen_encounters: set[str] = set()
    for seed in range(30):
        env.reset(seed=seed)
        state = env._state
        assert state.player.max_hp in (50, 9)
        if state.player.max_hp == 50:
            assert state.player.hp == 30
            assert len(state.relics) == 1 and state.relics[0].id == "girya"
            assert all(c.id == "strike" for c in state.player.all_cards)
            assert state.player.potions[0] is None
            assert state.player.potions[1] is not None
            assert state.player.potions[1].id == "block_potion"
        else:
            assert state.player.hp == 9
            assert len(state.relics) == 0
            assert all(c.id == "defend" for c in state.player.all_cards)
        seen_encounters.add(state.encounter.id)
    assert seen_encounters == set(_ENCOUNTER_IDS[:2])


def test_snapshot_mode_two_resets_on_the_same_snapshot_do_not_share_state(tmp_path):
    """Isolation: even when two resets land on the identical `Snapshot`
    object (the dataset never grows), the rebuilt engine objects must be
    independent -- mutating episode 1's cards/relics must not leak into
    episode 2. Regression target for mutation check (b) (alias-instead-of-
    fresh-build)."""
    path = str(tmp_path / "one_snap.jsonl")
    snap = Snapshot(
        deck=(CardSnap("strike", False, None, None),) * 5,
        relics=(RelicSnap("girya", 1),),
        hp=40, max_hp=40,
        potion_slots=(None,),
        act=1, encounter_id=_ENCOUNTER_IDS[0],
        provenance={"seed": "only", "floor": 1, "episode_decisions": 0},
    )
    save_snapshots(path, [snap])  # single-entry dataset -- every sample is this one

    env = STS2FullCombatEnv(snapshots=path)
    env.reset(seed=0)
    state1 = env._state
    live_card = next(c for c in state1.player.all_cards if c.id == "strike")
    CardCmd.upgrade(state1.hooks, live_card)
    assert live_card.upgrade_level == 1
    state1.relics[0]._lift()
    assert state1.relics[0].times_lifted == 2

    env.reset(seed=1)
    state2 = env._state
    assert state2 is not state1
    assert all(c.upgrade_level == 0 for c in state2.player.all_cards if c.id == "strike")
    assert state2.relics[0].times_lifted == 1
    assert state2.relics[0] is not state1.relics[0]
    assert state2.player.all_cards[0] is not state1.player.all_cards[0]


def test_snapshot_five_slot_potion_belt_survives_rebuild(tmp_path):
    """I1 fix, snapshot path: `build_start_state`'s `potion_slots` goes
    through the identical `max_potions` thread-through as the `potion_slots`
    kwarg path above -- a 5-slot snapshot belt must not get clipped back to
    3 by `PlayerCombatState`'s default."""
    path = str(tmp_path / "five_slot.jsonl")
    snap = Snapshot(
        deck=(CardSnap("strike", False, None, None),) * 5,
        relics=(),
        hp=40, max_hp=40,
        potion_slots=(None, None, None, "block_potion", None),
        act=1, encounter_id=_ENCOUNTER_IDS[0],
        provenance={"seed": "five", "floor": 1, "episode_decisions": 0},
    )
    save_snapshots(path, [snap])

    env = STS2FullCombatEnv(snapshots=path)
    env.reset(seed=0)
    state = env._state

    assert len(state.player.potions) == 5
    assert state.player.max_potions == 5
    assert state.player.potions[0] is None
    assert state.player.potions[1] is None
    assert state.player.potions[2] is None
    assert state.player.potions[3] is not None
    assert state.player.potions[3].id == "block_potion"
    assert state.player.potions[4] is None
