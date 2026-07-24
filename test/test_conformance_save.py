from __future__ import annotations
from pathlib import Path
import pytest
from sts2_rl.conformance.save import parse_save
from sts2_rl.rng import RunRngType, PlayerRngType

REC = Path(__file__).resolve().parents[2] / "RunReplays" / "RunReplays" / "Resources"
pytestmark = pytest.mark.skipif(not REC.exists(), reason="RunReplays saves not present")
S1 = REC / "89U21BV1TZ" / "floor_18" / "run.save"


def test_save_rng_block():
    o = parse_save(S1)
    assert o.run_seed == "89U21BV1TZ"
    assert o.player_seed == 2221240958
    assert o.ascension == 1
    assert o.run_counters[RunRngType.UP_FRONT] == 413
    assert o.run_counters[RunRngType.UNKNOWN_MAP_POINT] == 3
    assert o.player_counters[PlayerRngType.REWARDS] == 141
    assert o.player_counters[PlayerRngType.SHOPS] == 56


def test_save_encounter_lists():
    o = parse_save(S1)
    assert o.encounter_ids_by_act[0]["normal"][0] == "ENCOUNTER.FUZZY_WURM_CRAWLER_WEAK"
    assert o.acts == ["ACT.OVERGROWTH", "ACT.HIVE", "ACT.GLORY"]


@pytest.mark.parametrize("d", sorted(p.name for p in REC.iterdir()))
def test_all_saves_parse(d):
    for floor in ("floor_18", "floor_34", "floor_49"):
        o = parse_save(REC / d / floor / "run.save")
        assert len(o.run_counters) == 12 and len(o.player_counters) == 3
        assert o.run_seed == d


def test_save_oracle_carries_full_player_state():
    o = parse_save(S1)
    assert o.gold > 0
    assert len(o.deck) >= 10                      # starter deck + act-1 picks
    assert all(cid.startswith("CARD.") for cid, _ in o.deck)
    assert all(isinstance(up, int) for _, up in o.deck)
    assert o.relic_ids and o.relic_ids[0] == "RELIC.BURNING_BLOOD"
    assert all(isinstance(s, int) and pid.startswith("POTION.")
               for s, pid in o.potion_slots.items())
    assert all(eid.startswith("EVENT.") for eid in o.events_seen)
