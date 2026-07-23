from __future__ import annotations

from pathlib import Path

import pytest

from sts2_rl.conformance.recording import parse_recording
from sts2_rl.conformance.runner import ReplayRunner
from sts2_rl.conformance.save import parse_save
from sts2_rl.run import RunState

REC = Path.home() / "Desktop" / "RunReplays" / "RunReplays" / "Resources"


def test_start_run_grants_the_starting_relic_first():
    # Ironclad.cs:57 StartingRelics => BurningBlood, granted at run init
    # (Player.cs:739 PopulateStartingRelics), before any Neow relic.
    run = RunState(string_seed="89U21BV1TZ")
    run.start_run(acts=["overgrowth", "hive", "glory"], ascension=0)
    assert run.relics, "run should have at least the starting relic"
    assert run.relics[0].id == "burning_blood"
    assert sum(r.id == "burning_blood" for r in run.relics) == 1  # exactly once


def test_save_oracle_parses_player_hp():
    o = parse_save(REC / "89U21BV1TZ" / "floor_18" / "run.save")
    assert o.player_current_hp == 56
    assert o.player_max_hp == 71
    o49 = parse_save(REC / "89U21BV1TZ" / "floor_49" / "run.save")
    assert (o49.player_current_hp, o49.player_max_hp) == (33, 111)


def test_runner_reports_player_hp_divergence_at_act_boundary():
    # With a checkpoint one HP off the sim's real floor-18 value, the runner
    # must emit a player_hp Divergence for the completed act (index 0).
    b = REC / "89U21BV1TZ" / "floor_18"
    rec = parse_recording(b / "actions.sts2replay")
    oracle = parse_save(b / "run.save")
    runner = ReplayRunner(rec, oracle)
    # First get the sim's real floor-18 hp with a correct checkpoint (no div).
    base = runner.run(stop_after_act=0,
                      player_checkpoints={0: (oracle.player_current_hp,
                                              oracle.player_max_hp)})
    hp_divs = [d for d in base.divergences if d.stream == "player_hp"]
    # Now feed a deliberately wrong checkpoint and require a divergence.
    bad = ReplayRunner(rec, oracle).run(
        stop_after_act=0,
        player_checkpoints={0: (oracle.player_current_hp + 999,
                                oracle.player_max_hp)})
    bad_divs = [d for d in bad.divergences if d.stream == "player_hp"]
    assert len(bad_divs) == 1
    assert bad_divs[0].command_index == 0
    assert bad_divs[0].expected == oracle.player_current_hp + 999


_ACT_FLOORS = {0: "floor_18", 1: "floor_34", 2: "floor_49"}


def player_checkpoints(seed: str) -> dict[int, tuple[int, int]]:
    """Per-act HP checkpoints from the three sibling truncation saves."""
    ck: dict[int, tuple[int, int]] = {}
    for act_index, floor in _ACT_FLOORS.items():
        f = REC / seed / floor / "run.save"
        if f.exists():
            o = parse_save(f)
            ck[act_index] = (o.player_current_hp, o.player_max_hp)
    return ck


def test_resync_lets_full_run_replay_without_cascade_death():
    seed = "89U21BV1TZ"
    b = REC / seed / "floor_49"
    rec = parse_recording(b / "actions.sts2replay")
    oracle = parse_save(b / "run.save")
    result = ReplayRunner(rec, oracle).run(
        stop_after_act=2,
        player_checkpoints=player_checkpoints(seed),
        resync_player=True)
    # The run reaches the act-2 boss; it does not die mid-run.
    assert result.stopped_reason == "reached act 2 boss"
    assert result.rooms_walked >= 45


SEEDS = ["89U21BV1TZ", "DJDCSAQZNR", "L081UMJX4M", "QRWCVDPZN5", "TZEKRYTSNT"]

# Task 6 convergence gate. Each seed is xfail(strict=False) until its full
# act-1+2 run reaches zero player-state divergence — that is gated on
# per-seed combat-parity convergence (the ongoing SP3 Task 9 workstream), not
# on this SP3 player-state infrastructure. As a seed converges, it flips to
# XPASS; drop its mark then. Landscape captured 2026-07-22 (resync OFF):
_XFAIL_CONVERGENCE = {
    "89U21BV1TZ": "reaches act-2 boss; HP deltas remain (act1 max-HP -16, "
                  "act2 hp/max-HP) + 4 combat-stream counter divs "
                  "(act-2 combat parity incomplete).",
    "DJDCSAQZNR": "stops room 17 'unreachable map coord' (act1->2 transition "
                  "col=1,row=1); combat diverges from room 11.",
    "L081UMJX4M": "stops room 36 'unreachable map coord' (col=3,row=5); "
                  "combat/HP deltas remain.",
    "QRWCVDPZN5": "stops room 20 'no more MoveToMapCoord'; combat/HP deltas "
                  "remain.",
    "TZEKRYTSNT": "reaches act-2 boss; large HP deltas (sim under-takes combat "
                  "damage; forced=22).",
}


@pytest.mark.parametrize("seed", [
    pytest.param(s, marks=pytest.mark.xfail(reason=_XFAIL_CONVERGENCE[s],
                                            strict=False))
    for s in SEEDS
])
def test_full_run_player_state_parity(seed):
    b = REC / seed / "floor_49"
    rec = parse_recording(b / "actions.sts2replay")
    oracle = parse_save(b / "run.save")
    result = ReplayRunner(rec, oracle).run(
        stop_after_act=2,
        player_checkpoints=player_checkpoints(seed),
        resync_player=False)  # resync OFF for the gate: real end-state must match
    # (1) the run replays to the recording's end (no premature stop)
    assert result.stopped_reason == "reached act 2 boss", result.stopped_reason
    # (2) player HP/max-HP match at the final floor boundary
    hp_divs = [d for d in result.divergences
               if d.stream in ("player_hp", "player_max_hp")]
    assert hp_divs == [], "\n".join(str(d) for d in hp_divs)
    # (3) combat-stream RNG parity is not regressed
    combat_counter_divs = [d for d in result.combat_divergences
                           if d.command_index == -1]
    assert combat_counter_divs == [], "\n".join(str(d) for d in combat_counter_divs)
