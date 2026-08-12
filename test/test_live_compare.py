"""Task 16 STEP 1 (SpireBot live bot): the sim-vs-game obs diff tool's tests.

``sts2_rl/live/compare_obs.py`` joins a sim dump (``sim_obs_dump.py``) and a
game dump (both keyed on ``(floor, kind, decision_index)`` per that module's
docstring) and reports per-decision ``f``/``i`` mismatches by SEGMENT AND
FIELD, using the contract's ``layout`` block (offset/width per segment) to
turn a raw array index back into a name.
"""
import json

import pytest

from sts2_rl.live import compare_obs

# A tiny synthetic layout: f has 2 segments (widths 3 + 2 = 5), i has 2
# segments (widths 2 + 1 = 3). Mirrors the real contract.json's
# {"name", "offset", "width"} shape (see sts2_rl/live/contract.py:_seg_list).
_LAYOUT = {
    "f": [
        {"name": "run.hp_ratio", "offset": 0, "width": 3},
        {"name": "run.gold", "offset": 3, "width": 2},
    ],
    "i": [
        {"name": "combat.hand_ids", "offset": 0, "width": 2},
        {"name": "combat.enemy_hp", "offset": 2, "width": 1},
    ],
}


def _line(floor, kind, idx, f, i, act=0):
    return {"act": act, "floor": floor, "kind": kind, "decision_index": idx, "f": f, "i": i}


def _dump(*lines):
    return [dict(l) for l in lines]


# ---------------------------------------------------------------------------
# compare_dumps() — the core join+diff, independent of file I/O / CLI.
# ---------------------------------------------------------------------------


def test_identical_dumps_report_full_parity():
    sim = _dump(
        _line(1, "Map", 0, [0.5, 0.1, 0.2, 1.0, 3.0], [1, 2, 5]),
        _line(2, "Combat", 0, [0.9, 0.0, 0.0, 2.0, 4.0], [3, 4, 6]),
    )
    game = _dump(*sim)

    result = compare_obs.compare_dumps(sim, game, _LAYOUT)

    assert result.n_compared == 2
    assert result.mismatching_decisions == 0
    assert result.mismatches == []
    assert result.missing_in_sim == []
    assert result.missing_in_game == []
    assert compare_obs.exit_code(result) == 0


def test_f_mismatch_names_the_right_segment_and_offset():
    # index 3 in `f` is inside "run.gold" (offset 3, width 2) at local
    # offset 0 (global index 3 - segment offset 3 == 0).
    sim = _dump(_line(1, "Shop", 0, [0.5, 0.1, 0.2, 1.0, 3.0], [1, 2, 5]))
    game = _dump(_line(1, "Shop", 0, [0.5, 0.1, 0.2, 9.0, 3.0], [1, 2, 5]))

    result = compare_obs.compare_dumps(sim, game, _LAYOUT)

    assert result.n_compared == 1
    assert result.mismatching_decisions == 1
    assert len(result.mismatches) == 1
    m = result.mismatches[0]
    assert m["array"] == "f"
    assert m["index"] == 3
    assert m["segment"] == "run.gold"
    assert m["local_offset"] == 0
    assert m["sim_value"] == 1.0
    assert m["game_value"] == 9.0
    assert result.segment_histogram["f:run.gold"] == 1
    assert compare_obs.exit_code(result) != 0


def test_f_mismatch_within_tolerance_is_not_reported():
    sim = _dump(_line(1, "Shop", 0, [0.5, 0.1, 0.2, 1.0, 3.0], [1, 2, 5]))
    game = _dump(_line(1, "Shop", 0, [0.5, 0.1, 0.2, 1.0 + 1e-9, 3.0], [1, 2, 5]))

    result = compare_obs.compare_dumps(sim, game, _LAYOUT)

    assert result.mismatching_decisions == 0
    assert result.mismatches == []


def test_i_mismatch_is_exact_and_names_the_right_segment():
    # index 2 in `i` is inside "combat.enemy_hp" (offset 2, width 1) at
    # local offset 0.
    sim = _dump(_line(4, "Combat", 2, [0.0, 0.0, 0.0, 0.0, 0.0], [1, 2, 5]))
    game = _dump(_line(4, "Combat", 2, [0.0, 0.0, 0.0, 0.0, 0.0], [1, 2, 6]))

    result = compare_obs.compare_dumps(sim, game, _LAYOUT)

    assert result.mismatching_decisions == 1
    m = result.mismatches[0]
    assert m["array"] == "i"
    assert m["index"] == 2
    assert m["segment"] == "combat.enemy_hp"
    assert m["local_offset"] == 0
    assert m["sim_value"] == 5
    assert m["game_value"] == 6
    assert result.segment_histogram["i:combat.enemy_hp"] == 1


def test_multiple_mismatches_in_one_decision_all_reported_and_histogrammed():
    sim = _dump(_line(1, "Shop", 0, [0.5, 0.1, 0.2, 1.0, 3.0], [1, 2, 5]))
    game = _dump(_line(1, "Shop", 0, [9.5, 0.1, 0.2, 9.0, 3.0], [1, 2, 5]))

    result = compare_obs.compare_dumps(sim, game, _LAYOUT)

    assert result.mismatching_decisions == 1
    assert len(result.mismatches) == 2
    segs = {m["segment"] for m in result.mismatches}
    assert segs == {"run.hp_ratio", "run.gold"}


def test_missing_decision_in_game_is_always_a_failure():
    sim = _dump(
        _line(1, "Shop", 0, [0.0] * 5, [0, 0, 0]),
        _line(2, "Combat", 0, [0.0] * 5, [0, 0, 0]),
    )
    game = _dump(_line(1, "Shop", 0, [0.0] * 5, [0, 0, 0]))

    result = compare_obs.compare_dumps(sim, game, _LAYOUT)

    assert result.missing_in_game == [(0, 2, "Combat", 0)]
    assert compare_obs.exit_code(result) != 0


def test_missing_decision_in_sim_default_selectcards_carveout_does_not_fail():
    # Documented carve-out (sim_obs_dump.py's "OPEN QUESTION" section):
    # in-combat SelectCards decisions never get a sim line at all, so a
    # SelectCards-kind key present only in the game dump is expected, not a
    # gap, and by default must not flip the exit code — but ONLY at a floor
    # where the sim dump actually had a Combat-kind line (round-4 tightening:
    # a blanket carve-out hid a game-side stale-screen mislabel bug, see
    # compare_obs.py's module docstring).
    sim = _dump(
        _line(1, "Shop", 0, [0.0] * 5, [0, 0, 0]),
        _line(3, "Combat", 0, [0.0] * 5, [0, 0, 0]),
    )
    game = _dump(
        _line(1, "Shop", 0, [0.0] * 5, [0, 0, 0]),
        _line(3, "Combat", 0, [0.0] * 5, [0, 0, 0]),
        _line(3, "SelectCards", 1, [0.0] * 5, [0, 0, 0]),
    )

    result = compare_obs.compare_dumps(sim, game, _LAYOUT)

    assert result.missing_in_sim == [(0, 3, "SelectCards", 1)]
    assert result.missing_in_sim_carved_out == [(0, 3, "SelectCards", 1)]
    assert compare_obs.exit_code(result) == 0


def test_missing_selectcards_at_floor_with_no_sim_combat_is_not_carved():
    # Round-4 tightening: a SelectCards line missing from the sim dump at a
    # floor where the sim was NEVER in combat cannot be the documented
    # synchronous-resolution carve-out (that requires an actual sim combat
    # at the same floor) — it is much more likely a game-side stale-screen
    # mislabel (diag4-structural.md finding 1: a lingering
    # NCardGridSelectionScreen node hijacking Map/Event/Shop/Rest
    # classification) and must surface as a failure, not be silently hidden.
    # A trailing sim line at floor 4 (beyond the missing SelectCards' floor
    # 3) keeps this within the sim dump's coverage, so the round-7 "beyond
    # sim coverage" carve-out does not fire here — this test is pinning the
    # SEPARATE, older rule (no sim combat at that floor -> not the
    # synchronous-resolution carve-out), which must still catch this gap.
    sim = _dump(
        _line(1, "Shop", 0, [0.0] * 5, [0, 0, 0]),
        _line(4, "Shop", 0, [0.0] * 5, [0, 0, 0]),
    )
    game = _dump(
        _line(1, "Shop", 0, [0.0] * 5, [0, 0, 0]),
        _line(3, "SelectCards", 0, [0.0] * 5, [0, 0, 0]),
        _line(4, "Shop", 0, [0.0] * 5, [0, 0, 0]),
    )

    result = compare_obs.compare_dumps(sim, game, _LAYOUT)

    assert result.missing_in_sim == [(0, 3, "SelectCards", 0)]
    assert result.missing_in_sim_carved_out == []
    assert compare_obs.exit_code(result) == 1


def test_missing_decision_in_sim_non_carved_kind_is_a_failure():
    # A trailing sim line at floor 3 keeps this within the sim dump's
    # coverage, so the round-7 "beyond sim coverage" carve-out does not
    # fire — this test is pinning the separate rule that an ordinary kind
    # not on the carve-out list stays a failure.
    sim = _dump(
        _line(1, "Shop", 0, [0.0] * 5, [0, 0, 0]),
        _line(3, "Shop", 0, [0.0] * 5, [0, 0, 0]),
    )
    game = _dump(
        _line(1, "Shop", 0, [0.0] * 5, [0, 0, 0]),
        _line(2, "Rest", 0, [0.0] * 5, [0, 0, 0]),
        _line(3, "Shop", 0, [0.0] * 5, [0, 0, 0]),
    )

    result = compare_obs.compare_dumps(sim, game, _LAYOUT)

    assert result.missing_in_sim == [(0, 2, "Rest", 0)]
    assert result.missing_in_sim_carved_out == []
    assert compare_obs.exit_code(result) != 0


def test_allow_missing_sim_kind_extends_the_default_carveout_list():
    sim = _dump(_line(1, "Shop", 0, [0.0] * 5, [0, 0, 0]))
    game = _dump(
        _line(1, "Shop", 0, [0.0] * 5, [0, 0, 0]),
        _line(2, "Rest", 0, [0.0] * 5, [0, 0, 0]),
    )

    result = compare_obs.compare_dumps(
        sim, game, _LAYOUT, allow_missing_sim_kinds=("Rest",),
    )

    assert result.missing_in_sim_carved_out == [(0, 2, "Rest", 0)]
    assert compare_obs.exit_code(result) == 0


def test_max_report_caps_mismatch_list_but_not_the_histogram():
    lines_sim, lines_game = [], []
    for idx in range(5):
        lines_sim.append(_line(1, "Shop", idx, [0.0, 0.1, 0.2, 1.0, 3.0], [1, 2, 5]))
        lines_game.append(_line(1, "Shop", idx, [9.0, 0.1, 0.2, 1.0, 3.0], [1, 2, 5]))

    result = compare_obs.compare_dumps(
        lines_sim, lines_game, _LAYOUT, max_report=2,
    )

    assert result.mismatching_decisions == 5
    assert len(result.mismatches) == 2
    assert result.truncated is True
    assert result.segment_histogram["f:run.hp_ratio"] == 5


def test_different_act_does_not_join_even_with_identical_floor_kind_idx():
    # Same (floor, kind, decision_index) but different act must NOT be
    # treated as the same decision — this is exactly the act-1/act-2 folding
    # bug the (act, floor, kind, decision_index) key exists to fix.
    # A trailing sim line at act 1 floor 2 keeps act 1 floor 1 within the
    # sim dump's overall coverage, so the round-7 "beyond sim coverage"
    # carve-out does not fire — this test is pinning the join-key identity
    # rule, a real gap that must stay a failure.
    sim = _dump(
        _line(1, "Map", 0, [0.0] * 5, [0, 0, 0], act=0),
        _line(2, "Map", 0, [0.0] * 5, [0, 0, 0], act=1),
    )
    game = _dump(
        _line(1, "Map", 0, [0.0] * 5, [0, 0, 0], act=1),
        _line(2, "Map", 0, [0.0] * 5, [0, 0, 0], act=1),
    )

    result = compare_obs.compare_dumps(sim, game, _LAYOUT)

    assert result.n_compared == 1
    assert result.missing_in_game == [(0, 1, "Map", 0)]
    assert result.missing_in_sim == [(1, 1, "Map", 0)]
    assert result.missing_in_sim_carved_out == []
    assert compare_obs.exit_code(result) != 0


def test_load_jsonl_missing_act_field_raises_with_file_and_line(tmp_path):
    path = tmp_path / "old_format.jsonl"
    path.write_text(
        json.dumps({"floor": 1, "kind": "Map", "decision_index": 0, "f": [], "i": []}) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError) as excinfo:
        compare_obs._load_jsonl(path)

    msg = str(excinfo.value)
    assert str(path) in msg
    assert "1" in msg
    assert "act" in msg


def test_locate_field_finds_segment_and_local_offset():
    segs = _LAYOUT["f"]
    assert compare_obs._locate_field(segs, 0) == ("run.hp_ratio", 0)
    assert compare_obs._locate_field(segs, 2) == ("run.hp_ratio", 2)
    assert compare_obs._locate_field(segs, 3) == ("run.gold", 0)
    assert compare_obs._locate_field(segs, 4) == ("run.gold", 1)


def test_locate_field_out_of_range_raises():
    with pytest.raises(ValueError):
        compare_obs._locate_field(_LAYOUT["f"], 99)


# ---------------------------------------------------------------------------
# Round-6: RewardScreen sub-kind join. The game dump records reward
# decisions in actual recorded CLICK order (e.g. player claims the potion
# before picking the card); the sim's driver always asks in its own fixed
# sub-kind order (cards, then potion, then relic). Raw decision_index joins
# the two dumps' reward lines crookedly — sim's card-pick line lands on
# game's potion-claim line — producing pure ordering-artifact mismatches.
# The fix derives each RewardScreen line's sub-kind (reward_card /
# reward_potion / reward_relic) from the `phase` one-hot segment (mirrors
# `sts2_rl.run_env.PHASE_INDEX`, itself `list(DecisionKind)` order — see
# `driver.DecisionKind`) and joins by (sub-kind, per-sub-kind occurrence
# counter) instead of raw decision_index, for RewardScreen decisions only.
# ---------------------------------------------------------------------------

# phase one-hot occupies f[0:10], mirroring driver.DecisionKind's declared
# order: map, event, shop, rest, reward_card, reward_potion, combat,
# select_cards, select_option, reward_relic. f[10] is a dummy "content"
# field used to prove the join lines up the RIGHT reward sub-kind.
_REWARD_LAYOUT = {
    "f": [
        {"name": "phase", "offset": 0, "width": 10},
        {"name": "reward.content", "offset": 10, "width": 1},
    ],
    "i": [
        {"name": "reward.ids", "offset": 0, "width": 1},
    ],
}


def _phase_f(index, content):
    vec = [0.0] * 10
    vec[index] = 1.0
    vec.append(content)
    return vec


def test_reward_screen_joins_by_subkind_not_raw_index():
    # Game recorded potion-claim (idx0) BEFORE card-pick (idx1) — actual
    # click order. Sim's driver always asks cards first, so its idx0 is the
    # card-pick and idx1 is the potion. A raw decision_index join would pair
    # sim's card line against game's potion line (crossed content) even
    # though both dumps agree once matched by sub-kind.
    sim = _dump(
        _line(2, "RewardScreen", 0, _phase_f(4, 100.0), [7]),  # reward_card
        _line(2, "RewardScreen", 1, _phase_f(5, 22.0), [22]),  # reward_potion
    )
    game = _dump(
        _line(2, "RewardScreen", 0, _phase_f(5, 22.0), [22]),  # reward_potion (clicked first)
        _line(2, "RewardScreen", 1, _phase_f(4, 100.0), [7]),  # reward_card (clicked second)
    )

    result = compare_obs.compare_dumps(sim, game, _REWARD_LAYOUT)

    assert result.n_compared == 2
    assert result.mismatching_decisions == 0
    assert result.mismatches == []
    assert compare_obs.exit_code(result) == 0


def test_reward_screen_subkind_join_still_catches_real_mismatch():
    # Same sub-kind order swap as above, but the card's content genuinely
    # differs between sim and game — must still be caught once correctly
    # paired by sub-kind.
    sim = _dump(
        _line(2, "RewardScreen", 0, _phase_f(4, 100.0), [7]),
        _line(2, "RewardScreen", 1, _phase_f(5, 22.0), [22]),
    )
    game = _dump(
        _line(2, "RewardScreen", 0, _phase_f(5, 22.0), [22]),
        _line(2, "RewardScreen", 1, _phase_f(4, 999.0), [7]),  # content differs
    )

    result = compare_obs.compare_dumps(sim, game, _REWARD_LAYOUT)

    assert result.mismatching_decisions == 1
    assert result.mismatches[0]["segment"] == "reward.content"
    assert result.mismatches[0]["sim_value"] == 100.0
    assert result.mismatches[0]["game_value"] == 999.0


def test_reward_screen_repeated_subkind_uses_occurrence_counter():
    # Two card picks in a row (e.g. a two-card reward screen) must join
    # 0<->0 and 1<->1 by occurrence, not collapse onto one key.
    sim = _dump(
        _line(2, "RewardScreen", 0, _phase_f(4, 1.0), [1]),
        _line(2, "RewardScreen", 1, _phase_f(4, 2.0), [2]),
    )
    game = _dump(
        _line(2, "RewardScreen", 0, _phase_f(4, 1.0), [1]),
        _line(2, "RewardScreen", 1, _phase_f(4, 2.0), [2]),
    )

    result = compare_obs.compare_dumps(sim, game, _REWARD_LAYOUT)

    assert result.n_compared == 2
    assert result.mismatching_decisions == 0


def test_non_reward_kind_still_joins_by_raw_decision_index():
    # Sanity: the sub-kind join only applies to RewardScreen; every other
    # kind is untouched, including when the layout has no `phase` segment.
    sim = _dump(_line(1, "Shop", 0, [0.5, 0.1, 0.2, 1.0, 3.0], [1, 2, 5]))
    game = _dump(_line(1, "Shop", 0, [0.5, 0.1, 0.2, 9.0, 3.0], [1, 2, 5]))

    result = compare_obs.compare_dumps(sim, game, _LAYOUT)

    assert result.mismatching_decisions == 1
    assert result.mismatches[0]["segment"] == "run.gold"


def test_reward_subkind_helper_reads_phase_one_hot():
    f_segments = _REWARD_LAYOUT["f"]
    assert compare_obs._reward_subkind(_phase_f(4, 0.0), f_segments) == "reward_card"
    assert compare_obs._reward_subkind(_phase_f(5, 0.0), f_segments) == "reward_potion"
    assert compare_obs._reward_subkind(_phase_f(9, 0.0), f_segments) == "reward_relic"


# ---------------------------------------------------------------------------
# ROUND-9: RewardScreen click-order state artifact -- run.deck/potions/
# relics/gold and "other sub-kind" reward.* blocks must be excluded from
# comparison on RewardScreen lines (see compare_obs.py's ROUND-9 ADDENDUM).
# Layout mirrors the real contract's segment names closely enough to
# exercise the exclusion logic by name.
# ---------------------------------------------------------------------------
_CLICKORDER_LAYOUT = {
    "f": [
        {"name": "phase", "offset": 0, "width": 10},
        {"name": "run.gold", "offset": 10, "width": 1},
        {"name": "run.potions.f", "offset": 11, "width": 1},
        {"name": "run.deck.f", "offset": 12, "width": 1},
        {"name": "run.relics.f", "offset": 13, "width": 1},
        {"name": "reward.cards.f", "offset": 14, "width": 1},
        {"name": "reward.potion.f", "offset": 15, "width": 1},
        {"name": "reward.relic.f", "offset": 16, "width": 1},
    ],
    "i": [
        {"name": "run.potions.ids", "offset": 0, "width": 1},
        {"name": "run.deck.ids", "offset": 1, "width": 1},
        {"name": "run.relics.ids", "offset": 2, "width": 1},
        {"name": "reward.cards.ids", "offset": 3, "width": 1},
        {"name": "reward.potion.ids", "offset": 4, "width": 1},
        {"name": "reward.relic.ids", "offset": 5, "width": 1},
    ],
}


def _co_f(subkind_index, *, gold=0.0, potions=0.0, deck=0.0, relics=0.0,
          reward_cards=0.0, reward_potion=0.0, reward_relic=0.0):
    vec = [0.0] * 10
    vec[subkind_index] = 1.0
    vec += [gold, potions, deck, relics, reward_cards, reward_potion, reward_relic]
    return vec


def _co_i(*, potions=0, deck=0, relics=0, reward_cards=0, reward_potion=0, reward_relic=0):
    return [potions, deck, relics, reward_cards, reward_potion, reward_relic]


def test_reward_screen_run_state_delta_from_other_claim_is_excluded():
    # Game claimed the potion (id 22) before the card; sim's fixed order
    # asks the card first, so at the card sub-kind's line the sim's
    # run.potions is still empty while the game's already reflects the
    # claim (mirrors round-9 decode of act=0 floor=2 reward_card#0/
    # reward_potion#0 -- see the diagnosis notes).
    sim = _dump(
        _line(2, "RewardScreen", 0, _co_f(4, potions=0.0), _co_i(potions=0)),  # reward_card
        _line(2, "RewardScreen", 1, _co_f(5, deck=0.5), _co_i(deck=17)),  # reward_potion
    )
    game = _dump(
        _line(2, "RewardScreen", 0, _co_f(4, potions=1.0), _co_i(potions=22)),  # reward_card
        _line(2, "RewardScreen", 1, _co_f(5, deck=0.0), _co_i(deck=0)),  # reward_potion
    )

    result = compare_obs.compare_dumps(sim, game, _CLICKORDER_LAYOUT)

    assert result.n_compared == 2
    assert result.mismatching_decisions == 0
    assert result.mismatches == []
    assert compare_obs.exit_code(result) == 0


def test_reward_screen_own_subkind_reward_block_stays_strictly_compared():
    # The relic actually being OFFERED (this line's own sub-kind block) must
    # never be exempted -- round-9 decode found 5 genuine reward.relic.ids
    # divergences that must stay visible.
    sim = _dump(
        _line(2, "RewardScreen", 0, _co_f(9, reward_relic=7.0), _co_i(reward_relic=7)),
    )
    game = _dump(
        _line(2, "RewardScreen", 0, _co_f(9, reward_relic=143.0), _co_i(reward_relic=143)),
    )

    result = compare_obs.compare_dumps(sim, game, _CLICKORDER_LAYOUT)

    assert result.mismatching_decisions == 1
    segs = {m["segment"] for m in result.mismatches}
    assert "reward.relic.f" in segs
    assert "reward.relic.ids" in segs


def test_reward_screen_other_subkind_reward_block_is_excluded():
    # A still-pending (or already-claimed) OTHER sub-kind's reward offer
    # leaking into this line (e.g. reward.potion on a reward_card line) is
    # the same click-order artifact and must be excluded too.
    sim = _dump(
        _line(2, "RewardScreen", 0, _co_f(4, reward_potion=22.0), _co_i(reward_potion=22)),
    )
    game = _dump(
        _line(2, "RewardScreen", 0, _co_f(4, reward_potion=0.0), _co_i(reward_potion=0)),
    )

    result = compare_obs.compare_dumps(sim, game, _CLICKORDER_LAYOUT)

    assert result.mismatching_decisions == 0
    assert compare_obs.exit_code(result) == 0


def test_reward_screen_hp_delta_from_other_claim_is_excluded():
    # ROUND-9 ADDENDUM 2: decoded evidence at act=1 floor=8 idx=1 and
    # act=2 floor=13 idx=1 -- a relic claimed earlier on one side than the
    # other has already applied its HP/max-HP effect, so run.hp_abs and
    # run.max_hp_abs differ on a RewardScreen line for the exact same
    # click-order reason as run.deck/potions/relics.
    layout = {
        "f": _CLICKORDER_LAYOUT["f"] + [
            {"name": "run.hp_abs", "offset": 17, "width": 1},
            {"name": "run.max_hp_abs", "offset": 18, "width": 1},
        ],
        "i": _CLICKORDER_LAYOUT["i"],
    }
    sim = _dump(
        _line(2, "RewardScreen", 0, _co_f(9, reward_relic=7.0) + [0.62, 0.77], _co_i(reward_relic=7)),
    )
    game = _dump(
        _line(2, "RewardScreen", 0, _co_f(9, reward_relic=7.0) + [0.76, 0.84], _co_i(reward_relic=7)),
    )

    result = compare_obs.compare_dumps(sim, game, layout)

    assert result.mismatching_decisions == 0
    assert compare_obs.exit_code(result) == 0


def test_reward_screen_hp_ratio_delta_from_other_claim_is_excluded():
    # ROUND-9 ADDENDUM 3: decode found run.hp_ratio's remaining mismatches
    # sit at the exact same (act, floor, sub-kind) keys as the run.hp_abs
    # pair above -- the same click-order artifact, derived from hp_abs, so
    # it must be excluded the same way.
    layout = {
        "f": _CLICKORDER_LAYOUT["f"] + [
            {"name": "run.hp_ratio", "offset": 17, "width": 1},
        ],
        "i": _CLICKORDER_LAYOUT["i"],
    }
    sim = _dump(
        _line(2, "RewardScreen", 0, _co_f(9, reward_relic=7.0) + [0.40], _co_i(reward_relic=7)),
    )
    game = _dump(
        _line(2, "RewardScreen", 0, _co_f(9, reward_relic=7.0) + [0.45], _co_i(reward_relic=7)),
    )

    result = compare_obs.compare_dumps(sim, game, layout)

    assert result.mismatching_decisions == 0
    assert compare_obs.exit_code(result) == 0


def test_non_reward_screen_lines_still_strictly_compare_deck_and_gold():
    # Sanity: the exclusion is scoped to kind == "RewardScreen" only.
    sim = _dump(_line(2, "Shop", 0, [0.0] * 10 + [0.5, 0, 0, 0, 0, 0, 0], _co_i()))
    game = _dump(_line(2, "Shop", 0, [0.0] * 10 + [0.9, 0, 0, 0, 0, 0, 0], _co_i()))

    result = compare_obs.compare_dumps(sim, game, _CLICKORDER_LAYOUT)

    assert result.mismatching_decisions == 1
    assert result.mismatches[0]["segment"] == "run.gold"


# ---------------------------------------------------------------------------
# Round-7: "beyond sim coverage" carve-out. The sim's conformance-replay
# dump driver stops advancing once the recording's command list is
# exhausted (see sim_obs_dump.py), so its last emitted (act, floor) can sit
# BEFORE the game dump's true final floor -- the game dump keeps replaying
# real recorded rooms (e.g. an act-2 floor-16 Event) the sim never reaches.
# That tail is not a fidelity gap the sim could ever close by itself; it is
# carved out and reported separately from ordinary missing-in-sim failures.
# ---------------------------------------------------------------------------


def test_missing_in_sim_beyond_sim_coverage_is_carved_out():
    sim = _dump(
        _line(0, "Combat", 0, [0.5, 0.1, 0.2, 1.0, 3.0], [1, 2, 5]),
    )
    game = _dump(
        _line(0, "Combat", 0, [0.5, 0.1, 0.2, 1.0, 3.0], [1, 2, 5]),
        _line(1, "Event", 0, [0.9, 0.0, 0.0, 2.0, 4.0], [3, 4, 6]),
        _line(1, "Event", 1, [0.9, 0.0, 0.0, 2.0, 4.0], [3, 4, 6]),
    )

    result = compare_obs.compare_dumps(sim, game, _LAYOUT)

    assert result.missing_in_sim == [
        (0, 1, "Event", 0),
        (0, 1, "Event", 1),
    ]
    assert result.missing_in_sim_carved_out == [
        (0, 1, "Event", 0),
        (0, 1, "Event", 1),
    ]
    assert compare_obs.exit_code(result) == 0


def test_missing_in_sim_within_sim_coverage_stays_uncarved():
    # game has an extra line at a floor that is NOT beyond the sim's last
    # covered (act, floor) -- an ordinary gap, must stay a failure.
    sim = _dump(
        _line(0, "Combat", 0, [0.5, 0.1, 0.2, 1.0, 3.0], [1, 2, 5]),
        _line(1, "Map", 0, [0.9, 0.0, 0.0, 2.0, 4.0], [3, 4, 6]),
    )
    game = _dump(
        _line(0, "Combat", 0, [0.5, 0.1, 0.2, 1.0, 3.0], [1, 2, 5]),
        _line(0, "Event", 0, [0.9, 0.0, 0.0, 2.0, 4.0], [3, 4, 6]),
        _line(1, "Map", 0, [0.9, 0.0, 0.0, 2.0, 4.0], [3, 4, 6]),
    )

    result = compare_obs.compare_dumps(sim, game, _LAYOUT)

    assert result.missing_in_sim == [(0, 0, "Event", 0)]
    assert result.missing_in_sim_carved_out == []
    assert compare_obs.exit_code(result) == 1


# ---------------------------------------------------------------------------
# Round-6 addendum (task 1b): the sim's `_run_shop` driver always asks a
# final "leave the shop" Shop decision, but leaving a shop in the game is
# IMPLICIT (the next recorded command is a plain MapMoveCommand — nothing
# dispatches a "leave" click for DecisionDumper to record), so that ONE
# trailing sim Shop line can structurally never appear in a game dump. A
# missing-in-game Shop key is carved out only when it's the trailing
# (max-decision_index) Shop line at that (act, floor) AND the only
# missing-in-game Shop key there -- two-or-more missing Shop lines at one
# floor indicate a real undumped purchase and must stay a failure.
# ---------------------------------------------------------------------------


def test_missing_in_game_trailing_shop_leave_is_carved_out():
    sim = _dump(
        _line(3, "Shop", 0, [0.0] * 5, [0, 0, 0]),
        _line(3, "Shop", 1, [0.0] * 5, [0, 0, 0]),
    )
    game = _dump(_line(3, "Shop", 0, [0.0] * 5, [0, 0, 0]))

    result = compare_obs.compare_dumps(sim, game, _LAYOUT)

    assert result.missing_in_game == [(0, 3, "Shop", 1)]
    assert result.missing_in_game_carved_out == [(0, 3, "Shop", 1)]
    assert compare_obs.exit_code(result) == 0


def test_missing_in_game_two_shop_lines_stays_uncarved():
    # Mirrors the live act-2 floor-4 case: idx1 AND idx2 both missing --
    # idx2 alone (the trailing one) would qualify, but a SECOND missing
    # line means a real purchase went undumped, so NEITHER is carved.
    sim = _dump(
        _line(4, "Shop", 0, [0.0] * 5, [0, 0, 0], act=2),
        _line(4, "Shop", 1, [0.0] * 5, [0, 0, 0], act=2),
        _line(4, "Shop", 2, [0.0] * 5, [0, 0, 0], act=2),
    )
    game = _dump(_line(4, "Shop", 0, [0.0] * 5, [0, 0, 0], act=2))

    result = compare_obs.compare_dumps(sim, game, _LAYOUT)

    assert sorted(result.missing_in_game) == [
        (2, 4, "Shop", 1), (2, 4, "Shop", 2),
    ]
    assert result.missing_in_game_carved_out == []
    assert compare_obs.exit_code(result) != 0


def test_missing_in_game_non_trailing_shop_line_stays_uncarved():
    # Only ONE missing line, but it's NOT the trailing (max-index) Shop
    # decision -- an earlier Shop line missing from the game dump is a real
    # gap (e.g. an undumped purchase), not the implicit-leave structural
    # carve-out.
    sim = _dump(
        _line(3, "Shop", 0, [0.0] * 5, [0, 0, 0]),
        _line(3, "Shop", 1, [0.0] * 5, [0, 0, 0]),
    )
    game = _dump(_line(3, "Shop", 1, [0.0] * 5, [0, 0, 0]))

    result = compare_obs.compare_dumps(sim, game, _LAYOUT)

    assert result.missing_in_game == [(0, 3, "Shop", 0)]
    assert result.missing_in_game_carved_out == []
    assert compare_obs.exit_code(result) != 0


def test_missing_in_game_non_shop_kind_never_carved():
    sim = _dump(
        _line(1, "Shop", 0, [0.0] * 5, [0, 0, 0]),
        _line(2, "Combat", 0, [0.0] * 5, [0, 0, 0]),
    )
    game = _dump(_line(1, "Shop", 0, [0.0] * 5, [0, 0, 0]))

    result = compare_obs.compare_dumps(sim, game, _LAYOUT)

    assert result.missing_in_game == [(0, 2, "Combat", 0)]
    assert result.missing_in_game_carved_out == []
    assert compare_obs.exit_code(result) != 0


# ---------------------------------------------------------------------------
# format_report() — human-readable text, and a smoke check for the info a
# reviewer needs (segment name, values, summary counts).
# ---------------------------------------------------------------------------


def test_format_report_names_segment_in_text():
    sim = _dump(_line(1, "Shop", 0, [0.5, 0.1, 0.2, 1.0, 3.0], [1, 2, 5]))
    game = _dump(_line(1, "Shop", 0, [0.5, 0.1, 0.2, 9.0, 3.0], [1, 2, 5]))
    result = compare_obs.compare_dumps(sim, game, _LAYOUT)

    text = compare_obs.format_report(result)

    assert "run.gold" in text
    assert "floor=1" in text
    assert "Shop" in text
    assert "compared" in text.lower()


# ---------------------------------------------------------------------------
# CLI (main()) — full round trip through real files, including a real-shaped
# contract.json.
# ---------------------------------------------------------------------------


def _write_jsonl(path, lines):
    with open(path, "w", encoding="utf-8") as fh:
        for line in lines:
            fh.write(json.dumps(line) + "\n")


def test_cli_exits_zero_on_identical_dumps(tmp_path, capsys):
    contract_path = tmp_path / "contract.json"
    contract_path.write_text(json.dumps({"layout": _LAYOUT}), encoding="utf-8")

    sim = _dump(_line(1, "Shop", 0, [0.5, 0.1, 0.2, 1.0, 3.0], [1, 2, 5]))
    sim_path = tmp_path / "sim.jsonl"
    game_path = tmp_path / "game.jsonl"
    _write_jsonl(sim_path, sim)
    _write_jsonl(game_path, sim)

    code = compare_obs.main([str(sim_path), str(game_path), "--contract", str(contract_path)])

    assert code == 0
    out = capsys.readouterr().out
    assert "compared" in out.lower()


def test_cli_exits_nonzero_and_reports_segment_on_mismatch(tmp_path, capsys):
    contract_path = tmp_path / "contract.json"
    contract_path.write_text(json.dumps({"layout": _LAYOUT}), encoding="utf-8")

    sim_path = tmp_path / "sim.jsonl"
    game_path = tmp_path / "game.jsonl"
    _write_jsonl(sim_path, _dump(_line(1, "Shop", 0, [0.5, 0.1, 0.2, 1.0, 3.0], [1, 2, 5])))
    _write_jsonl(game_path, _dump(_line(1, "Shop", 0, [0.5, 0.1, 0.2, 9.0, 3.0], [1, 2, 5])))

    code = compare_obs.main([str(sim_path), str(game_path), "--contract", str(contract_path)])

    assert code != 0
    out = capsys.readouterr().out
    assert "run.gold" in out


# ---------------------------------------------------------------------------
# Round-13: the same trailing-leave shape exists for Rest — the sim's
# rest-site driver asks a final "use the remaining action or leave" Rest
# decision whenever actions remain (Miniature Tent's extra action makes
# this routine on 933T), while the game leaves via an interstitial
# ProceedToMap that PassiveDump skips. Same single-line + max-index rule,
# per kind, as the Shop carve-out.
# ---------------------------------------------------------------------------


def test_missing_in_game_trailing_rest_leave_is_carved_out():
    sim = _dump(
        _line(7, "Rest", 0, [0.0] * 5, [0, 0, 0], act=1),
        _line(7, "Rest", 1, [0.0] * 5, [0, 0, 0], act=1),
        _line(7, "Rest", 2, [0.0] * 5, [0, 0, 0], act=1),
    )
    game = _dump(
        _line(7, "Rest", 0, [0.0] * 5, [0, 0, 0], act=1),
        _line(7, "Rest", 1, [0.0] * 5, [0, 0, 0], act=1),
    )

    result = compare_obs.compare_dumps(sim, game, _LAYOUT)

    assert result.missing_in_game == [(1, 7, "Rest", 2)]
    assert result.missing_in_game_carved_out == [(1, 7, "Rest", 2)]
    assert compare_obs.exit_code(result) == 0


def test_missing_in_game_two_rest_lines_stays_uncarved():
    sim = _dump(
        _line(7, "Rest", 0, [0.0] * 5, [0, 0, 0], act=1),
        _line(7, "Rest", 1, [0.0] * 5, [0, 0, 0], act=1),
        _line(7, "Rest", 2, [0.0] * 5, [0, 0, 0], act=1),
    )
    game = _dump(_line(7, "Rest", 0, [0.0] * 5, [0, 0, 0], act=1))

    result = compare_obs.compare_dumps(sim, game, _LAYOUT)

    assert sorted(result.missing_in_game) == [
        (1, 7, "Rest", 1), (1, 7, "Rest", 2),
    ]
    assert result.missing_in_game_carved_out == []
    assert compare_obs.exit_code(result) != 0


# ---------------------------------------------------------------------------
# Round-13: out-of-combat multi-pick grid — sim asks once per pick, the game
# records the whole grid as ONE SelectGridCardCommand, so idx>=1 sim lines
# can never appear game-side. Carved only when the game dumped idx 0 at the
# same floor and the floor has no sim Combat lines.
# ---------------------------------------------------------------------------


def test_missing_in_game_multipick_grid_tail_is_carved_out():
    sim = _dump(
        _line(1, "SelectCards", 0, [0.0] * 5, [0, 0, 0], act=2),
        _line(1, "SelectCards", 1, [0.0] * 5, [0, 0, 0], act=2),
        _line(1, "SelectCards", 2, [0.0] * 5, [0, 0, 0], act=2),
    )
    game = _dump(_line(1, "SelectCards", 0, [0.0] * 5, [0, 0, 0], act=2))

    result = compare_obs.compare_dumps(sim, game, _LAYOUT)

    assert sorted(result.missing_in_game) == [
        (2, 1, "SelectCards", 1), (2, 1, "SelectCards", 2),
    ]
    assert sorted(result.missing_in_game_carved_out) == [
        (2, 1, "SelectCards", 1), (2, 1, "SelectCards", 2),
    ]
    assert compare_obs.exit_code(result) == 0


def test_missing_in_game_grid_tail_without_idx0_stays_uncarved():
    # No game idx-0 line at the floor — the grid itself went undumped, a
    # real gap, not the structural one-command fold.
    sim = _dump(
        _line(1, "SelectCards", 0, [0.0] * 5, [0, 0, 0], act=2),
        _line(1, "SelectCards", 1, [0.0] * 5, [0, 0, 0], act=2),
    )
    game = _dump(_line(2, "Map", 0, [0.0] * 5, [0, 0, 0], act=2))

    result = compare_obs.compare_dumps(sim, game, _LAYOUT)

    assert (2, 1, "SelectCards", 1) in result.missing_in_game
    assert (2, 1, "SelectCards", 1) not in result.missing_in_game_carved_out
    assert compare_obs.exit_code(result) != 0


# ---------------------------------------------------------------------------
# Round-13: unclaimed-reward carve-out — the sim asks about every PRESENT
# reward; the game dump only records CLAIMS. A reward the player proceeds
# past (potion left behind on a full belt — TooFull claim, SkipRewards
# interstitial, save records was_picked=false) can never yield a game line.
# Carved only when the game dumped at least one RewardScreen line at the
# floor (the screen was captured; only this sub-kind went unclaimed).
# ---------------------------------------------------------------------------


def test_missing_in_game_unclaimed_reward_subkind_is_carved_out():
    sim = _dump(
        _line(13, "RewardScreen", 0, _phase_f(9, 5.0), [5], act=2),   # relic
        _line(13, "RewardScreen", 1, _phase_f(4, 7.0), [7], act=2),   # card
        _line(13, "RewardScreen", 2, _phase_f(5, 22.0), [22], act=2), # potion (never claimed)
    )
    game = _dump(
        _line(13, "RewardScreen", 0, _phase_f(9, 5.0), [5], act=2),
        _line(13, "RewardScreen", 1, _phase_f(4, 7.0), [7], act=2),
    )

    result = compare_obs.compare_dumps(sim, game, _REWARD_LAYOUT)

    assert result.missing_in_game == [(2, 13, "RewardScreen", "reward_potion#0")]
    assert result.missing_in_game_carved_out == [
        (2, 13, "RewardScreen", "reward_potion#0")]
    assert compare_obs.exit_code(result) == 0


def test_missing_in_game_whole_reward_screen_stays_uncarved():
    # No game RewardScreen line at the floor at all — an entirely undumped
    # screen is a real capture gap, never the unclaimed-tail structural one.
    sim = _dump(_line(13, "RewardScreen", 0, _phase_f(5, 22.0), [22], act=2))
    game = _dump(_line(14, "Map", 0, _phase_f(0, 0.0), [0], act=2))

    result = compare_obs.compare_dumps(sim, game, _REWARD_LAYOUT)

    assert (2, 13, "RewardScreen", "reward_potion#0") in result.missing_in_game
    assert result.missing_in_game_carved_out == []
    assert compare_obs.exit_code(result) != 0


# ---------------------------------------------------------------------------
# Round-15: the reward-card UPGRADE field (float 0 of each 4-float row) is
# click-order-dependent on the line's OWN sub-kind — an egg relic claimed
# earlier on the same screen upgrades matching pending offers in place
# (CardReward.cs RelicObtained subscription + EggRelicHelper). Excluded on
# RewardScreen lines; ids and other floats stay strict.
# ---------------------------------------------------------------------------

_REWARD_CARDS_LAYOUT = {
    "f": [
        {"name": "phase", "offset": 0, "width": 10},
        {"name": "reward.cards.f", "offset": 10, "width": 8},
    ],
    "i": [
        {"name": "reward.cards.ids", "offset": 0, "width": 2},
    ],
}


def _reward_cards_f(upgrades, costs):
    vec = [0.0] * 10
    vec[4] = 1.0  # reward_card phase
    for u, c in zip(upgrades, costs):
        vec.extend([u, c, 0.0, 0.0])
    return vec


def test_reward_card_upgrade_field_is_click_order_excluded():
    sim = _dump(_line(15, "RewardScreen", 0,
                      _reward_cards_f([0.0, 0.0], [0.167, 0.167]), [7, 8]))
    game = _dump(_line(15, "RewardScreen", 0,
                       _reward_cards_f([0.0, 0.2], [0.167, 0.167]), [7, 8]))

    result = compare_obs.compare_dumps(sim, game, _REWARD_CARDS_LAYOUT)

    assert result.mismatching_decisions == 0
    assert compare_obs.exit_code(result) == 0


def test_reward_card_identity_and_cost_stay_strict():
    sim = _dump(_line(15, "RewardScreen", 0,
                      _reward_cards_f([0.0, 0.0], [0.167, 0.167]), [7, 8]))
    game = _dump(_line(15, "RewardScreen", 0,
                       _reward_cards_f([0.0, 0.0], [0.5, 0.167]), [7, 9]))

    result = compare_obs.compare_dumps(sim, game, _REWARD_CARDS_LAYOUT)

    assert result.mismatching_decisions == 1
    assert compare_obs.exit_code(result) != 0
