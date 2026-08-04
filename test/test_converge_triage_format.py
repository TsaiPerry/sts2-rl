"""Pin the printed expected/got sense of the triage detectors: `expected` is
ALWAYS the oracle (save capture), `actual`/`got` is ALWAYS the sim, in every
detector. The historical confusion (GAP-QUEUE 'opposite senses' lesson) was
two different captures being compared, not an inversion — so the header must
name its capture."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from sts2_rl.conformance.comparators import Divergence


def test_hp_line_names_oracle_as_expected():
    from converge_triage import fmt_hp_line
    line = fmt_hp_line(Divergence("player_hp", 2, 67, 80, "act 2 boundary"))
    assert "expected 67" in line and "got 80" in line
    assert "sim high by 13" in line


def test_floor_line_names_oracle_as_expected():
    from converge_triage import fmt_floor_line
    line = fmt_floor_line(Divergence("floor_hp", 49, 80, 67, ""))
    assert "expected 80" in line and "got 67" in line
