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


SEEDS = ["89U21BV1TZ", "933T39V18D",
         "DJDCSAQZNR", "L081UMJX4M", "QRWCVDPZN5", "TZEKRYTSNT"]

# Task 6 convergence gate. Two of the six seeds are IRONCLAD runs — the single
# character this sim models (run.py: "This single-character sim is Ironclad";
# start_run always grants burning_blood + ironclad_starting_deck()) — and BOTH
# NOW PASS OUTRIGHT through act 2, so neither carries a mark any more. They
# converged on 2026-08-03 when the two REPLAY-HARNESS bugs behind the act-2
# wall were fixed:
#
#   1. `combat_card_db.py` reconstructed `NetCombatCardDb` ids post-draw
#      instead of stamping them as cards were ADDED, so 89U's turn-1 generated
#      cards (Blessed Antler's 3 Dazed into the draw pile at BeforeHandDraw,
#      Vexing Puzzlebox's card into the hand after the draw) got the wrong ids
#      and `PlayCard 26` resolved to a Dazed. 89U act-2 forced_combats 8 -> 5.
#   2. `StableShuffle`'s stabilizing sort is `List<T>.Sort()`, an UNSTABLE
#      introsort, and the sim used Python's stable `list.sort`. Two identical
#      un-upgraded Forgotten Rituals came out of a 20-plus-card turn-4
#      reshuffle in the opposite order from the game, so `PlayCard 12` named
#      the twin still in the draw pile. Ported in `sts2_rl/dotnet_sort.py`;
#      89U act-2 forced_combats 5 -> 0, and 933T's last force-win (its Test
#      Subject boss) and its room-593 `Inferno+` mismatch went with it.
#
# Measured after both, three identical runs: both seeds reach the act-2 boss
# with forced_combats=0, matching final-boundary HP/max-HP and no stream-counter
# divergence; 933T39V18D also reaches zero per-command mismatches, and
# 89U21BV1TZ reaches zero divergent floors under per-floor triage. (933T's
# per-floor triage still flags floors 47/49 — that path runs resync ON, which
# pins to floor-ENTRY snapshots and disagrees with this gate by construction;
# see the queue's `resync_floors` open-work item.) Anything that reopens the
# assertions below is a regression, which is what dropping the marks asserts.
#
# The other four seeds are DIFFERENT, un-ported characters (Regent / Silent /
# Necrobinder / Defect). None of their starting cards or relics exist in the
# sim, so every run replays with the wrong (Ironclad) deck: hands diverge from
# turn 1, combats force-win, the map path desyncs, and the run stops early or
# takes nonsense damage. These are NOT combat/map fidelity bugs — they cannot
# converge without porting whole characters, so they stay permanently xfail
# with the accurate reason. (See memory sp3-seeds-are-5-characters.)
_XFAIL_CONVERGENCE = {
    "DJDCSAQZNR": "un-ported character (CHARACTER.REGENT); sim is Ironclad-only "
                  "so the wrong starting deck/relics make the whole run diverge.",
    "L081UMJX4M": "un-ported character (CHARACTER.SILENT); sim is Ironclad-only "
                  "so the wrong starting deck/relics make the whole run diverge.",
    "QRWCVDPZN5": "un-ported character (CHARACTER.NECROBINDER); sim is "
                  "Ironclad-only so the wrong deck/relics make the run diverge.",
    "TZEKRYTSNT": "un-ported character (CHARACTER.DEFECT); sim is Ironclad-only "
                  "so the wrong starting deck/relics make the whole run diverge.",
}


@pytest.mark.parametrize("seed", [
    pytest.param(s, marks=(
        [pytest.mark.xfail(reason=_XFAIL_CONVERGENCE[s], strict=False)]
        if s in _XFAIL_CONVERGENCE else []))
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


def test_the_curse_of_knowledge_choice_is_taken_from_the_recording():
    """`CardSelectCmd.FromChooseACardScreen` mid-move — Knowledge Demon's
    Curse of Knowledge (KnowledgeDemon.cs:183) — is recorded as
    `SelectCardFromScreen N`, not as a grid pick.

    The replay driver only understood `SelectGridCard`/`SelectHandCards` at
    that seam, so the choice resolved to NOTHING: no Disintegration/MindRot
    power was applied, and the recorded command was then dispatched into an
    empty `_pending_screen_cards` and dropped. That is the whole of the 89U
    act-1 boundary divergence this test pins (rng_streams/G7): the sim ended
    act 1 six HP up because it never took the curse.

    Ground truth for the fight is the save's own per-room
    `map_point_history` (act 1's last point: damage_taken 18, hp_healed 6,
    63 -> 51).
    """
    seed = "89U21BV1TZ"
    b = REC / seed / "floor_49"
    rec = parse_recording(b / "actions.sts2replay")
    oracle = parse_save(b / "run.save")
    result = ReplayRunner(rec, oracle).run(
        stop_after_act=1,
        player_checkpoints=player_checkpoints(seed),
        resync_player=False)
    hp_divs = [d for d in result.divergences
               if d.stream in ("player_hp", "player_max_hp")]
    assert hp_divs == [], "\n".join(str(d) for d in hp_divs)
    assert result.forced_combats == 0
