from __future__ import annotations
from pathlib import Path
import pytest
from sts2_rl.conformance.recording import parse_recording, EnemyState

REC = Path(__file__).resolve().parents[2] / "RunReplays" / "RunReplays" / "Resources"
pytestmark = pytest.mark.skipif(not REC.exists(), reason="RunReplays recordings not present")

R1 = REC / "89U21BV1TZ" / "floor_18" / "actions.sts2replay"


def test_header_parsed():
    rec = parse_recording(R1)
    assert rec.seed == "89U21BV1TZ"
    assert rec.ascension == 1
    assert rec.character == "IRONCLAD"
    assert rec.acts == ["ACT.OVERGROWTH", "ACT.HIVE", "ACT.GLORY"]


def test_first_command_and_annotation():
    rec = parse_recording(R1)
    c0 = rec.commands[0]
    assert c0.name == "ChooseEventOption" and c0.args == ["1"]
    play = next(c for c in rec.commands if c.name == "PlayCard")
    assert play.annotation.card_name == "CARD.DEFEND_IRONCLAD"
    assert play.annotation.card_id == 65198830
    assert play.annotation.hand == ["Defend", "Strike", "Defend", "Defend", "Strike"]
    assert play.annotation.enemies == [EnemyState("Fuzzy Wurm Crawler", 57, 57)]


def test_negative_and_multi_args():
    rec = parse_recording(R1)
    proceed = rec.commands[1]
    assert proceed.name == "ChooseEventOption" and proceed.args == ["-1"]
    targeted = next(c for c in rec.commands if c.name == "PlayCard" and len(c.args) == 2)
    assert targeted.args == ["1", "1"]


def test_multi_enemy_annotation():
    rec = parse_recording(R1)
    # "Enemies: [Twig Slime (S) 8/8, Twig Slime (M) 26/26, Leaf Slime (S) 11/11]"
    cmd = next(c for c in rec.commands
               if c.annotation and c.annotation.enemies
               and len(c.annotation.enemies) == 3)
    names = [e.name for e in cmd.annotation.enemies]
    assert "Twig Slime (S)" in names and "Leaf Slime (S)" in names


@pytest.mark.parametrize("d", sorted(p.name for p in REC.iterdir()))
def test_all_recordings_parse(d):
    for floor in ("floor_18", "floor_34", "floor_49"):
        rec = parse_recording(REC / d / floor / "actions.sts2replay")
        assert rec.seed == d and rec.commands
