"""stale_triage classifies stale audit records: class (a) = every cited line
span byte-identical at the same line numbers vs the text the record's hash was
taken over; class (b) = anything else. Receipts, not vibes."""
from pathlib import Path
import importlib.util

_TOOL = Path(__file__).resolve().parents[1] / "audit" / "tools" / "stale_triage.py"
spec = importlib.util.spec_from_file_location("stale_triage", _TOOL)
st = importlib.util.module_from_spec(spec)
spec.loader.exec_module(st)


def test_spans_identical_true_for_same_lines():
    old = "a\nb\nc\nd\n"
    new = "a\nb\nc\nd\nE\n"          # append-only
    assert st.span_identical(old, new, 2, 3)      # lines 2-3 = "b","c"


def test_spans_identical_false_when_lines_moved():
    old = "a\nb\nc\n"
    new = "X\na\nb\nc\n"             # same content, shifted one line
    assert not st.span_identical(old, new, 2, 3)


def test_classify_all_spans_identical_is_class_a():
    rec = {"unit": "relic/example",
           "sim_source": {"path": "sts2_rl/x.py", "sha256": "S"},
           "hooks": {"H": {"verdict": "faithful", "maps_to": "sts2_rl/x.py:2-3"}}}
    texts = {("sts2_rl/x.py", "S"): "a\nb\nc\nd\n"}
    current = {"sts2_rl/x.py": "a\nb\nc\nd\nE\n"}
    out = st.classify_record(rec, historical=texts.get, current=current.get)
    assert out["class"] == "a"


def test_classify_missing_historical_text_is_class_b():
    rec = {"unit": "relic/example",
           "sim_source": {"path": "sts2_rl/x.py", "sha256": "NOPE"},
           "hooks": {}}
    out = st.classify_record(rec, historical=lambda k: None,
                             current={"sts2_rl/x.py": "a\n"}.get)
    assert out["class"] == "b"
    assert "historical" in out["reason"]
